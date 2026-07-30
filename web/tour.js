/* ---------------------------------------------------------------------------
   Tour hướng dẫn "chỉ tận tay": làm mờ cả trang, chiếu sáng đúng ô đang nói tới,
   một con trỏ chuột chỉ thẳng vào ô đó, kèm thẻ ghi chú đầy đủ.

   Cách trang gọi:
     window.HacomTour.init({
       steps: [...]                       // danh sách bước cố định
       stepsFor: () => [...]              // hoặc hàm trả về bước theo ngữ cảnh
       autoKey: "tour_price_advisor"      // tự chạy lần đầu, lưu cờ vào localStorage
     });

   Mỗi bước: { el: "#css-selector", title: "...", body: "html", spot: "padding px" }
   Bước có selector không tìm thấy hoặc đang bị ẩn sẽ tự bị bỏ qua.
   --------------------------------------------------------------------------- */
(function () {
  "use strict";

  var GAP = 14;        // khoảng cách giữa vùng sáng và thẻ ghi chú
  var EDGE = 12;       // lề tối thiểu so với biên cửa sổ

  // Kích thước hộp SVG con trỏ và toạ độ ĐẦU NHỌN bên trong hộp đó.
  // Đầu nhọn ở (5.5, 2.2) trong viewBox 24 -> quy đổi sang pixel thực tế.
  var HAND_SIZE = 34;
  var TIP_X = 5.5 / 24 * HAND_SIZE;   // ~7.8px
  var TIP_Y = 2.2 / 24 * HAND_SIZE;   // ~3.1px
  var cfg = null;
  var steps = [];
  var idx = 0;
  var nodes = null;
  var running = false;

  /* Phần tử có thực sự hiển thị không.
     Trang này ẩn ô bằng `.hidden { display: none !important }` nên chỉ cần xét
     display/visibility và việc phần tử có chiếm chỗ trên trang.
     KHÔNG xét opacity: nhiều ô có animation hiện dần, lúc tour lọc thì opacity
     còn bằng 0 và sẽ bị loại oan (đã gặp với hai ô Phụ lục 01/02). */
  function visible(el) {
    if (!el) return false;
    if (!el.getClientRects().length) return false;
    var s = window.getComputedStyle(el);
    return s.display !== "none" && s.visibility !== "hidden";
  }

  function build() {
    if (nodes) return nodes;
    var d = document;
    // Gắn vào <html>, KHÔNG gắn vào <body>: body có `opacity: 0` kèm animation
    // fadeInBody nên mọi con của nó bị mờ theo, và body tạo ngữ cảnh xếp lớp làm
    // vùng làm mờ của tour bị cắt, không phủ hết màn hình.
    function mk(cls, parent) {
      var n = d.createElement("div");
      n.className = cls;
      (parent || d.documentElement).appendChild(n);
      return n;
    }
    nodes = {};
    nodes.blocker = mk("tour-blocker");
    nodes.spot = mk("tour-spot");
    nodes.hand = mk("tour-hand");
    nodes.hand.innerHTML =
      '<svg viewBox="0 0 24 24" width="34" height="34" aria-hidden="true">' +
      '<path d="M5.5 2.2 18.6 12l-5.6.6 3 6.1-2.7 1.3-3-6.1-3.9 4.1z" ' +
      'fill="#fff" stroke="#e1262f" stroke-width="1.5" stroke-linejoin="round"/></svg>';

    nodes.card = mk("tour-card");
    nodes.card.setAttribute("role", "dialog");
    nodes.card.setAttribute("aria-live", "polite");
    nodes.card.innerHTML =
      '<div class="tour-card-head">' +
        '<span class="tour-step-count"></span>' +
        '<button type="button" class="tour-x" aria-label="Đóng hướng dẫn">&times;</button>' +
      '</div>' +
      '<h4 class="tour-title"></h4>' +
      '<div class="tour-body"></div>' +
      '<div class="tour-dots"></div>' +
      '<div class="tour-actions">' +
        '<button type="button" class="tour-btn tour-skip">Bỏ qua</button>' +
        '<div class="tour-actions-right">' +
          '<button type="button" class="tour-btn tour-prev">← Trước</button>' +
          '<button type="button" class="tour-btn tour-next primary">Tiếp →</button>' +
        '</div>' +
      '</div>';

    nodes.count = nodes.card.querySelector(".tour-step-count");
    nodes.title = nodes.card.querySelector(".tour-title");
    nodes.body = nodes.card.querySelector(".tour-body");
    nodes.dots = nodes.card.querySelector(".tour-dots");
    nodes.prev = nodes.card.querySelector(".tour-prev");
    nodes.next = nodes.card.querySelector(".tour-next");

    nodes.prev.addEventListener("click", function () { go(idx - 1); });
    nodes.next.addEventListener("click", function () { go(idx + 1); });
    nodes.card.querySelector(".tour-skip").addEventListener("click", stop);
    nodes.card.querySelector(".tour-x").addEventListener("click", stop);
    // Bấm ra vùng mờ cũng sang bước tiếp — thói quen quen thuộc của người dùng.
    nodes.blocker.addEventListener("click", function () { go(idx + 1); });
    return nodes;
  }

  /* Đặt vùng sáng + con trỏ + thẻ ghi chú quanh phần tử của bước hiện tại. */
  function place() {
    var step = steps[idx];
    var el = document.querySelector(step.el);
    if (!el) return stop();

    var pad = step.spot === undefined ? 6 : step.spot;
    var r = el.getBoundingClientRect();
    var top = r.top - pad, left = r.left - pad;
    var w = r.width + pad * 2, h = r.height + pad * 2;

    var s = nodes.spot.style;
    s.top = top + "px"; s.left = left + "px";
    s.width = w + "px"; s.height = h + "px";

    // Thẻ ghi chú: ưu tiên đặt dưới vùng sáng, nếu không đủ chỗ thì đặt lên trên.
    var card = nodes.card;
    card.style.visibility = "hidden";
    card.style.top = "0px"; card.style.left = "0px";
    var cw = card.offsetWidth, ch = card.offsetHeight;
    var vh = window.innerHeight, vw = window.innerWidth;

    var below = top + h + GAP;
    var above = top - GAP - ch;
    var cardTop, arrowUp;
    if (below + ch <= vh - EDGE) { cardTop = below; arrowUp = true; }
    else if (above >= EDGE) { cardTop = above; arrowUp = false; }
    else { cardTop = Math.max(EDGE, Math.min(vh - ch - EDGE, top)); arrowUp = true; }

    var cardLeft = left + w / 2 - cw / 2;
    cardLeft = Math.max(EDGE, Math.min(vw - cw - EDGE, cardLeft));

    card.style.top = cardTop + "px";
    card.style.left = cardLeft + "px";
    card.classList.toggle("arrow-up", arrowUp);
    card.classList.toggle("arrow-down", !arrowUp);
    card.style.visibility = "visible";

    // Con trỏ chuột.
    //
    // Đầu nhọn của mũi tên KHÔNG nằm ở góc hộp SVG mà ở toạ độ (5.5, 2.2) trong
    // viewBox 24, tức lệch vào trong. Muốn chỉ đúng thì phải đặt hộp lùi lại
    // đúng khoảng lệch đó, nếu không đầu nhọn luôn trượt ra ngoài mục tiêu.
    //
    // Mũi tên chỉ theo hướng trên-trái, nên thân nó đổ về phía dưới-phải. Vì
    // vậy con trỏ phải đứng ở phía đối diện thẻ ghi chú, và khi thẻ nằm trên
    // thì phải xoay 180° — nếu không nó chỉ ra ngoài, ngược hướng ô cần chỉ.
    var hand = nodes.hand;
    var hs = hand.style;
    // Điểm cần chỉ vào: nằm trên cạnh vùng sáng, lệch trái một chút cho tự
    // nhiên, và không vượt quá nửa chiều rộng với ô hẹp.
    var tipX = left + Math.min(34, w / 2);
    var tipY;

    if (arrowUp) {
      // Thẻ nằm DƯỚI -> con trỏ đứng TRÊN, xoay 180° để chúc xuống vào ô.
      tipY = top;
      hand.classList.add("flip");
      hs.left = (tipX - (HAND_SIZE - TIP_X)) + "px";
      hs.top = (tipY - (HAND_SIZE - TIP_Y)) + "px";
    } else {
      // Thẻ nằm TRÊN -> con trỏ đứng DƯỚI, giữ hướng gốc để hất lên vào ô.
      tipY = top + h;
      hand.classList.remove("flip");
      hs.left = (tipX - TIP_X) + "px";
      hs.top = (tipY - TIP_Y) + "px";
    }
  }

  function render() {
    var step = steps[idx];
    nodes.count.textContent = "Bước " + (idx + 1) + "/" + steps.length;
    nodes.title.textContent = step.title;
    nodes.body.innerHTML = step.body;

    var dots = "";
    for (var i = 0; i < steps.length; i++) {
      dots += '<i class="tour-dot' + (i === idx ? " on" : "") + '"></i>';
    }
    nodes.dots.innerHTML = dots;

    nodes.prev.disabled = idx === 0;
    nodes.next.textContent = idx === steps.length - 1 ? "Xong ✓" : "Tiếp →";

    var el = document.querySelector(step.el);
    if (!el) return stop();
    el.scrollIntoView({ behavior: "smooth", block: "center", inline: "nearest" });
    // Chờ cuộn xong mới đo toạ độ, nếu đo ngay sẽ lệch vị trí.
    setTimeout(place, 320);
  }

  function go(n) {
    if (n < 0) return;
    if (n >= steps.length) return stop();
    idx = n;
    render();
  }

  function onKey(e) {
    if (e.key === "Escape") stop();
    else if (e.key === "ArrowRight" || e.key === "Enter") { e.preventDefault(); go(idx + 1); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); go(idx - 1); }
  }
  function onMove() { if (running) place(); }

  function start() {
    var list = cfg.stepsFor ? cfg.stepsFor() : cfg.steps;
    // Chỉ giữ những bước có phần tử đang hiển thị trên trang.
    steps = (list || []).filter(function (st) { return visible(document.querySelector(st.el)); });
    if (!steps.length) {
      if (window.HacomTour.onEmpty) window.HacomTour.onEmpty();
      return false;
    }
    build();
    running = true;
    document.documentElement.classList.add("tour-on");
    window.addEventListener("keydown", onKey);
    window.addEventListener("resize", onMove);
    window.addEventListener("scroll", onMove, true);
    go(0);
    return true;
  }

  function stop() {
    if (!running) return;
    running = false;
    document.documentElement.classList.remove("tour-on");
    window.removeEventListener("keydown", onKey);
    window.removeEventListener("resize", onMove);
    window.removeEventListener("scroll", onMove, true);
    if (cfg && cfg.autoKey) {
      try { localStorage.setItem(cfg.autoKey, "1"); } catch (err) { /* chế độ riêng tư */ }
    }
  }

  window.HacomTour = {
    init: function (options) {
      cfg = options || {};
      // Tự chạy lần đầu vào trang; các lần sau phải bấm nút mới chạy.
      if (cfg.autoKey) {
        var seen = false;
        try { seen = localStorage.getItem(cfg.autoKey) === "1"; } catch (err) { seen = true; }
        if (!seen) setTimeout(start, 700);
      }
    },
    start: start,
    stop: stop,
    isRunning: function () { return running; },
    reset: function () {
      if (cfg && cfg.autoKey) { try { localStorage.removeItem(cfg.autoKey); } catch (err) {} }
    }
  };
})();
