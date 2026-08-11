// PriceAdvisor UI logic matching index.html theme.
document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("predictForm");
  const itemNameInput = document.getElementById("paItemName");
  const warningChar = document.getElementById("warningChar");
  const progressPanel = document.getElementById("progressPanel");
  const progressBar = document.getElementById("progressBar");
  const progressMessage = document.getElementById("progressMessage");
  const resultPanel = document.getElementById("resultPanel");
  
  // Results Elements
  const resPriceLow = document.getElementById("resPriceLow");
  const resPriceHigh = document.getElementById("resPriceHigh");
  const resConfidence = document.getElementById("resConfidence");
  const resStatusBadge = document.getElementById("resStatusBadge");
  const resReasoning = document.getElementById("resReasoning");
  const anomalyAlert = document.getElementById("anomalyAlert");
  const reviewWarning = document.getElementById("reviewWarning");
  const ragCount = document.getElementById("ragCount");
  const ragRows = document.getElementById("ragRows");
  const ragSort = document.getElementById("ragSort");
  const ragBidder = document.getElementById("ragBidder");

  // Dữ liệu bảng RAG hiện tại (dùng để lọc/sắp xếp phía trình duyệt).
  let ragItems = [];
  let ragUnit = "";

  // New Market Price Elements
  const resMarketAvg = document.getElementById("resMarketAvg");
  const resMarketRange = document.getElementById("resMarketRange");
  const marketCount = document.getElementById("marketCount");
  const marketSnippetsList = document.getElementById("marketSnippetsList");
  const ddgSearchLink = document.getElementById("ddgSearchLink");

  const newPredictBtn = document.getElementById("newPredictBtn");
  const resetButton = document.getElementById("resetButton");

  let currentJobId = null;
  let currentSuggestedPrice = null;

  // Character length check
  itemNameInput.addEventListener("input", () => {
    const len = itemNameInput.value.trim().length;
    if (len > 0 && len < 10) {
      warningChar.style.display = "block";
    } else {
      warningChar.style.display = "none";
    }
  });

  // Reset form
  resetButton.addEventListener("click", () => {
    form.reset();
    warningChar.style.display = "none";
  });

  // Predict new item
  newPredictBtn.addEventListener("click", () => {
    resultPanel.classList.add("hidden");
    form.classList.remove("hidden");
    form.reset();
    warningChar.style.display = "none";
  });

  // Helper toast alert
  function showToast(message, isError = false) {
    const toast = document.getElementById("toast");
    if (!toast) return;
    toast.textContent = message;
    toast.className = "toast show" + (isError ? " error" : "");
    setTimeout(() => {
      toast.className = "toast";
    }, 4000);
  }

  // Handle Form Submission
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    
    const itemName = itemNameInput.value.trim();
    const unit = document.getElementById("paUnit").value.trim();
    const bidderPriceVal = document.getElementById("paBidderPrice").value;
    const bidderPrice = bidderPriceVal ? parseFloat(bidderPriceVal) : null;
    // Luôn dùng LLM nội bộ (Ollama) — người dùng không cần chọn backend.
    const backend = "ollama";
    const topK = parseInt(document.getElementById("paTopK").value) || 5;

    if (!itemName || !unit) {
      showToast("Vui lòng điền đầy đủ Tên vật tư và Đơn vị tính.", true);
      return;
    }

    // Show loading
    form.classList.add("hidden");
    progressPanel.classList.remove("hidden");
    progressBar.style.width = "30%";
    progressMessage.textContent = "Đang truy xuất CSDL thầu PostgreSQL / RAG...";

    try {
      // Step 1: Request predict API
      progressBar.style.width = "60%";
      progressMessage.textContent = "Mô hình AI đang thực thi suy luận ngữ cảnh...";
      
      const response = await fetch("/api/price-advisor/predict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          item_name: itemName,
          unit: unit,
          backend: backend,
          top_k: topK,
          bidder_price: bidderPrice
        })
      });

      if (!response.ok) {
        const errorText = await response.text();
        let errMsg = "Yêu cầu dự báo giá thất bại.";
        try {
          const errObj = JSON.parse(errorText);
          errMsg = errObj.detail || errMsg;
        } catch(c) {}
        throw new Error(errMsg);
      }

      const result = await response.json();
      progressBar.style.width = "100%";
      progressMessage.textContent = "Hoàn tất!";
      
      setTimeout(() => {
        progressPanel.classList.add("hidden");
        resultPanel.classList.remove("hidden");
        renderResults(result, bidderPrice, unit);
      }, 500);

    } catch (error) {
      console.error(error);
      progressPanel.classList.add("hidden");
      form.classList.remove("hidden");
      showToast(error.message, true);
    }
  });

  // Render Results HTML
  function renderResults(res, bidderPrice, unit) {
    // Reset classes
    resStatusBadge.className = "badge-status";
    anomalyAlert.classList.add("hidden");
    reviewWarning.classList.add("hidden");

    // Check status
    const status = res.status ? res.status.toLowerCase() : "failed";
    const isHardFailed = (res.price_low === null || status === "rejected" || status === "failed");

    if (isHardFailed) {
      // AI không đề xuất được, nhưng khoảng giá lịch sử nội bộ vẫn tra được từ
      // CSDL giá — bỏ trống cả bảng là vứt đi thông tin đang có sẵn.
      const hasHistory = res.history_count > 0;
      resPriceLow.textContent = hasHistory ? formatCurrency(res.history_min_price) : "N/A";
      resPriceHigh.textContent = hasHistory ? formatCurrency(res.history_max_price) : "N/A";

      resConfidence.textContent = "N/A";
      resStatusBadge.textContent = status.toUpperCase();
      resStatusBadge.className = "badge-status badge-review";

      // Nguyên nhân THẬT (LLM không gọi được, trả JSON hỏng...) thay vì câu
      // chung chung đổ lỗi cho dữ liệu tham chiếu.
      const cause = res.error_message || res.reasoning
        || "Không rõ nguyên nhân; xem nhật ký máy chủ.";
      let html = `⚠️ <b>Hệ thống chưa đề xuất được giá:</b> ${escapeHtmlPA(cause)}`;
      if (hasHistory) {
        html += `<br><b>Hai ô giá bên trên là khoảng giá lịch sử nội bộ</b> `
             + `(${res.history_count} bản ghi cùng đơn vị tính), chưa qua thẩm định của AI.`;
      }
      reviewWarning.classList.remove("hidden");
      reviewWarning.innerHTML = html;

      resReasoning.innerHTML = `<span style="color: var(--text-muted);">Không có báo cáo lập luận do giá trị bị từ chối hoặc thất bại.</span>`;
      document.getElementById("feedbackActions").classList.add("hidden");
    } else {
      currentJobId = "single_predict";
      currentSuggestedPrice = res.suggested_price;
      document.getElementById("feedbackActions").classList.remove("hidden");

      resPriceLow.textContent = formatCurrency(res.price_low);
      resPriceHigh.textContent = formatCurrency(res.price_high);
      
      resConfidence.textContent = `${(res.confidence * 100).toFixed(1)}%`;
      resStatusBadge.textContent = status.toUpperCase();
      
      if (status === "needs_review") {
        resStatusBadge.className = "badge-status badge-review";
        reviewWarning.classList.remove("hidden");
        reviewWarning.innerHTML = `⚠️ <b>Lưu ý đề xuất giá (Cần kiểm tra thêm):</b> ${res.reasoning || "Dữ liệu tham khảo nội bộ chưa đủ mạnh."}`;
      } else {
        resStatusBadge.className = "badge-status badge-validated";
      }
      
      resReasoning.textContent = res.reasoning || "Không có nội dung lập luận.";
    }

    // Update direct DuckDuckGo search link
    if (ddgSearchLink) {
      const itemVal = itemNameInput.value.trim();
      if (itemVal) {
        ddgSearchLink.href = `https://duckduckgo.com/?q=${encodeURIComponent('báo giá ' + itemVal)}&kl=vn-vi`;
        ddgSearchLink.style.display = "inline-block";
      } else {
        ddgSearchLink.style.display = "none";
      }
    }

    // Render Market Prices
    if (res.market_avg_price) {
      resMarketAvg.textContent = formatCurrency(res.market_avg_price) + " VNĐ";
      resMarketRange.textContent = `Cận: ${formatCurrency(res.market_min_price)} - ${formatCurrency(res.market_max_price)} VNĐ`;
    } else {
      // Phân biệt "bị chặn tạm thời" với "tra được nhưng không có giá" — trước
      // đây cả hai đều hiện cùng một câu nên người dùng tưởng vật tư không có
      // trên thị trường, trong khi thực ra chỉ là công cụ tìm kiếm đang chặn.
      const st = res.market_status || "no_prices";
      resMarketAvg.textContent = st === "blocked" ? "Tạm ngưng" : "N/A";
      resMarketRange.textContent =
        st === "blocked" ? "Tìm kiếm bị chặn — thử lại sau ít phút"
        : st === "error" ? "Không kết nối được công cụ tìm kiếm"
        : "Không tìm thấy giá trực tuyến";
    }

    // Render Market Snippets
    marketSnippetsList.innerHTML = "";
    const snippets = res.market_snippets || [];
    if (snippets.length === 0) {
      const st = res.market_status || "no_prices";
      marketCount.textContent = st === "blocked" ? "tạm ngưng" : "0 trích dẫn";
      const note = document.createElement("span");
      note.style.fontSize = "13px";
      note.style.textAlign = "center";
      note.style.color = st === "blocked" ? "#b7791f" : "var(--text-muted)";
      note.textContent = res.market_message
        || "Không tìm thấy báo giá thị trường trực tuyến phù hợp.";
      marketSnippetsList.appendChild(note);
    } else {
      marketCount.textContent = `${snippets.length} trích dẫn`;
      snippets.forEach(snip => {
        const item = document.createElement("div");
        item.style.fontSize = "13px";
        item.style.lineHeight = "1.5";
        item.style.padding = "6px 8px";
        item.style.borderBottom = "1px solid #edf2f7";
        item.style.color = "#2d3748";
        // Dùng textContent, không dùng innerHTML: nội dung này lấy từ web ngoài
        // nên chèn thẳng vào HTML sẽ thành lỗ hổng XSS.
        item.textContent = `🌐 ${snip}`;
        marketSnippetsList.appendChild(item);
      });
      if (marketSnippetsList.lastChild) {
        marketSnippetsList.lastChild.style.borderBottom = "none";
      }
    }

    // Render RAG Table
    ragRows.innerHTML = "";
    const items = res.similar_items || [];
    
    if (items.length === 0) {
      ragItems = [];
      ragUnit = unit;
      fillBidderFilter([]);
      ragCount.textContent = "0 mẫu tham chiếu";
      ragRows.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted);">Không tìm thấy báo giá tương đồng nào.</td></tr>`;
      return;
    }

    // Giữ dữ liệu gốc để lọc/sắp xếp lại mà không phải gọi lại API.
    // _ref là số thứ tự theo ĐỘ TƯƠNG ĐỒNG, giữ nguyên kể cả khi đổi cách sắp xếp.
    ragItems = items.map((item, idx) => ({ ...item, _ref: idx + 1 }));
    ragUnit = unit;
    fillBidderFilter(ragItems);
    renderRagRows();

    // Calculate mean of matching unit price for comparison (tính trên TOÀN BỘ mẫu,
    // không phụ thuộc bộ lọc đang chọn).
    let totalPrice = 0;
    let matchingUnitCount = 0;
    items.forEach((item) => {
      if (item.unit.trim().toLowerCase() === unit.trim().toLowerCase() && item.unit_price !== null) {
        totalPrice += item.unit_price;
        matchingUnitCount++;
      }
    });

    // Bidder Price Comparison Alert (Double Checking)
    if (bidderPrice !== null) {
      let comparisonHtml = "";
      
      // Part A: Compare against internal thầu average
      if (matchingUnitCount > 0) {
        const meanActual = totalPrice / matchingUnitCount;
        const pctDiff = ((bidderPrice - meanActual) / meanActual) * 100;
        
        if (Math.abs(pctDiff) <= 10) {
          comparisonHtml += `<p style="margin: 4px 0;">🟢 <b>Đặc điểm nội bộ:</b> Đơn giá nhà thầu chào (<b>${formatCurrency(bidderPrice)} VNĐ</b>) lệch <b>${pctDiff.toFixed(2)}%</b> so với trung bình thầu lịch sử (<b>${formatCurrency(meanActual)} VNĐ</b>). Nằm trong vùng an toàn.</p>`;
        } else if (pctDiff > 10) {
          comparisonHtml += `<p style="margin: 4px 0;">🟡 <b>Đặc điểm nội bộ:</b> Đơn giá nhà thầu chào (<b>${formatCurrency(bidderPrice)} VNĐ</b>) cao hơn <b>${pctDiff.toFixed(2)}%</b> so với trung bình thầu lịch sử (<b>${formatCurrency(meanActual)} VNĐ</b>). Ban KTKT nên đàm phán giảm giá.</p>`;
        } else {
          comparisonHtml += `<p style="margin: 4px 0;">🔴 <b>Đặc điểm nội bộ:</b> Đơn giá nhà thầu chào (<b>${formatCurrency(bidderPrice)} VNĐ</b>) thấp hơn <b>${Math.abs(pctDiff).toFixed(2)}%</b> so với trung bình thầu lịch sử (<b>${formatCurrency(meanActual)} VNĐ</b>). Cần kiểm tra kỹ chất lượng vật tư.</p>`;
        }
      } else {
        comparisonHtml += `<p style="margin: 4px 0; color: #64748b;">⚪ Không tìm thấy dữ liệu thầu lịch sử phù hợp cùng ĐVT để so sánh chéo.</p>`;
      }
      
      // Part B: Compare against online market average
      if (res.market_avg_price) {
        const marketMean = res.market_avg_price;
        const mPctDiff = ((bidderPrice - marketMean) / marketMean) * 100;
        
        if (Math.abs(mPctDiff) <= 15) {
          comparisonHtml += `<p style="margin: 4px 0;">🟢 <b>Đặc điểm thị trường:</b> Đơn giá nhà thầu chào lệch <b>${mPctDiff.toFixed(2)}%</b> so với giá thị trường trực tuyến (<b>${formatCurrency(marketMean)} VNĐ</b>). Khớp tốt với giá bán lẻ phổ biến.</p>`;
        } else if (mPctDiff > 15) {
          comparisonHtml += `<p style="margin: 4px 0;">🟡 <b>Đặc điểm thị trường:</b> Đơn giá nhà thầu chào cao hơn <b>${mPctDiff.toFixed(2)}%</b> so với giá thị trường trực tuyến (<b>${formatCurrency(marketMean)} VNĐ</b>). Thầu có biên lợi nhuận cao.</p>`;
        } else {
          comparisonHtml += `<p style="margin: 4px 0;">🔴 <b>Đặc điểm thị trường:</b> Đơn giá nhà thầu chào thấp hơn <b>${Math.abs(mPctDiff).toFixed(2)}%</b> so với giá thị trường trực tuyến (<b>${formatCurrency(marketMean)} VNĐ</b>). Cảnh báo nguy cơ chào thầu thiếu thiết bị hoặc mua hàng trôi nổi.</p>`;
        }
      } else {
        comparisonHtml += `<p style="margin: 4px 0; color: #64748b;">⚪ Không tìm thấy thông tin giá thị trường trực tuyến để so sánh đối chiếu.</p>`;
      }

      anomalyAlert.classList.remove("hidden");
      anomalyAlert.innerHTML = `<div>${comparisonHtml}</div>`;
      anomalyAlert.style.borderLeftColor = "#3b82f6";
      anomalyAlert.style.background = "#f0f9ff";
      anomalyAlert.style.color = "#1e3a8a";
    }
  }

  // --- Feedback Modal logic ---
  const modal = document.getElementById("feedbackModal");
  const modalClose = document.getElementById("modalClose");
  const modalTitle = document.getElementById("modalTitle");
  const feedbackAction = document.getElementById("feedbackAction");
  const feedbackPriceGrp = document.getElementById("feedbackPriceGroup");
  const feedbackPriceEl = document.getElementById("feedbackPrice");
  const feedbackNoteGrp = document.getElementById("feedbackNoteGroup");
  const feedbackNoteEl = document.getElementById("feedbackNote");
  const feedbackSubmit = document.getElementById("feedbackSubmitBtn");

  function openFeedbackModal(action, defaultPrice) {
    if (!modal) return;
    feedbackAction.value = action;
    if (feedbackNoteEl) feedbackNoteEl.value = "";
    
    if (action === "accepted") {
      if (modalTitle) modalTitle.textContent = "👍 Chấp nhận đơn giá gợi ý";
      if (feedbackPriceGrp) feedbackPriceGrp.style.display = "flex";
      if (feedbackPriceEl) feedbackPriceEl.value = defaultPrice ? Math.round(defaultPrice) : "";
      if (feedbackNoteGrp) feedbackNoteGrp.style.display = "flex";
      if (feedbackNoteEl) feedbackNoteEl.placeholder = "Ghi chú thêm (không bắt buộc)...";
    } else {
      if (modalTitle) modalTitle.textContent = "👎 Từ chối đơn giá gợi ý";
      if (feedbackPriceGrp) feedbackPriceGrp.style.display = "none";
      if (feedbackPriceEl) feedbackPriceEl.value = "";
      if (feedbackNoteGrp) feedbackNoteGrp.style.display = "flex";
      if (feedbackNoteEl) feedbackNoteEl.placeholder = "Nhập lý do từ chối (bắt buộc)...";
    }
    modal.style.display = "flex";
  }

  if (modalClose) {
    modalClose.addEventListener("click", () => { modal.style.display = "none"; });
  }
  window.addEventListener("click", (e) => {
    if (e.target === modal) modal.style.display = "none";
  });

  document.getElementById("btnAccept").addEventListener("click", () => {
    openFeedbackModal("accepted", currentSuggestedPrice);
  });
  document.getElementById("btnReject").addEventListener("click", () => {
    openFeedbackModal("rejected", null);
  });

  if (feedbackSubmit) {
    feedbackSubmit.addEventListener("click", async () => {
      const action = feedbackAction ? feedbackAction.value : "accepted";
      const note = feedbackNoteEl ? feedbackNoteEl.value.trim() : "";
      const price = feedbackPriceEl ? parseFloat(feedbackPriceEl.value) : NaN;

      if (action === "rejected" && !note) {
        showToast("Vui lòng nhập lý do từ chối.", true);
        return;
      }

      const payload = {
        job_id: currentJobId || "single_predict",
        item_id: "test_item_1",
        action: action,
        suggested_price: (action === "accepted" && !isNaN(price)) ? price : null,
        note: note
      };

      feedbackSubmit.disabled = true;
      feedbackSubmit.textContent = "Đang gửi...";
      
      try {
        const resp = await fetch("/api/price-advisor/feedback", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        if (resp.ok) {
          showToast("Gửi phản hồi thành công! Dữ liệu đã được lưu vào nhật ký đào tạo AI.", false);
          modal.style.display = "none";
          
          const btnA = document.getElementById("btnAccept");
          const btnR = document.getElementById("btnReject");
          
          if (action === "accepted") {
            btnA.style.background = "#047857"; // Dark green active
            btnR.style.background = "#ef4444"; // Reset danger
          } else {
            btnA.style.background = "#10b981"; // Reset success
            btnR.style.background = "#b91c1c"; // Dark red active
          }
        } else {
          const err = await resp.json().catch(() => ({}));
          showToast("Lỗi: " + (err.detail || "Không gửi được phản hồi"), true);
        }
      } catch (e) {
        showToast("Lỗi kết nối: " + e.message, true);
      } finally {
        feedbackSubmit.disabled = false;
        feedbackSubmit.textContent = "Gửi phản hồi";
      }
    });
  }

  // Format currency helper
  function formatCurrency(value) {
    if (value === null || value === undefined) return "N/A";
    return Math.round(value).toLocaleString("vi-VN");
  }

  // Thông báo lỗi có thể chứa ký tự đặc biệt từ máy chủ, phải thoát trước khi
  // chèn vào HTML.
  function escapeHtmlPA(text) {
    const div = document.createElement("div");
    div.textContent = String(text ?? "");
    return div.innerHTML;
  }

  // ---------------------------------------------------------------------
  // Bộ lọc / sắp xếp bảng RAG (xử lý ngay trên trình duyệt, không gọi lại API)
  // ---------------------------------------------------------------------

  function bidderOf(item) {
    return item.bidder && item.bidder !== "None" ? item.bidder : "";
  }

  /** Nạp danh sách nhà thầu có thật trong kết quả vào ô lọc. */
  function fillBidderFilter(items) {
    if (!ragBidder) return;
    const previous = ragBidder.value;
    const names = [...new Set(items.map(bidderOf).filter(Boolean))]
      .sort((a, b) => a.localeCompare(b, "vi"));
    const hasUnknown = items.some((item) => !bidderOf(item));

    ragBidder.innerHTML =
      `<option value="">Tất cả nhà thầu</option>` +
      names.map((n) => `<option value="${n}">${n}</option>`).join("") +
      (hasUnknown ? `<option value="__unknown__">Không rõ nhà thầu</option>` : "");

    // Giữ lựa chọn cũ nếu vẫn còn hợp lệ.
    ragBidder.value = [...ragBidder.options].some((o) => o.value === previous) ? previous : "";
  }

  /** Vẽ lại các dòng theo bộ lọc và kiểu sắp xếp đang chọn. */
  function renderRagRows() {
    if (!ragRows) return;
    const sortMode = ragSort ? ragSort.value : "default";
    const pick = ragBidder ? ragBidder.value : "";

    let rows = ragItems.slice();
    if (pick === "__unknown__") {
      rows = rows.filter((item) => !bidderOf(item));
    } else if (pick) {
      rows = rows.filter((item) => bidderOf(item) === pick);
    }

    // Dòng thiếu đơn giá luôn dồn xuống cuối để không chiếm đầu bảng khi sắp xếp.
    const priceOf = (item) => (typeof item.unit_price === "number" ? item.unit_price : null);
    if (sortMode === "price_desc" || sortMode === "price_asc") {
      const dir = sortMode === "price_desc" ? -1 : 1;
      rows.sort((a, b) => {
        const pa = priceOf(a), pb = priceOf(b);
        if (pa === null && pb === null) return a._ref - b._ref;
        if (pa === null) return 1;
        if (pb === null) return -1;
        return (pa - pb) * dir;
      });
    } else if (sortMode === "bidder") {
      rows.sort((a, b) => {
        const na = bidderOf(a), nb = bidderOf(b);
        if (!na && !nb) return a._ref - b._ref;
        if (!na) return 1;
        if (!nb) return -1;
        return na.localeCompare(nb, "vi") || a._ref - b._ref;
      });
    } else {
      rows.sort((a, b) => a._ref - b._ref);
    }

    if (ragCount) {
      ragCount.textContent = rows.length === ragItems.length
        ? `${ragItems.length} mẫu tham chiếu`
        : `${rows.length}/${ragItems.length} mẫu tham chiếu`;
    }

    if (!rows.length) {
      ragRows.innerHTML = `<tr><td colspan="6" style="text-align:center;color:var(--text-muted);">Không có mẫu nào khớp bộ lọc đang chọn.</td></tr>`;
      return;
    }

    ragRows.innerHTML = rows.map((item) => {
      const isSameUnit = String(item.unit || "").trim().toLowerCase() === String(ragUnit || "").trim().toLowerCase();
      const priceStr = item.unit_price !== null && item.unit_price !== undefined ? formatCurrency(item.unit_price) : "N/A";
      const brand = item.brand && item.brand !== "None" ? item.brand : "—";
      const bidder = bidderOf(item);
      const project = item.project_name && item.project_name !== "None" ? item.project_name : "";
      const spec = item.material_spec && item.material_spec !== "None" ? item.material_spec : "";
      return `
        <tr>
          <td><span style="font-weight:600;color:var(--text-muted);">REF-${item._ref}</span></td>
          <td><div style="font-weight:600;color:var(--text);">${item.item_name || ""}</div><small style="color:var(--text-muted);">${spec}</small></td>
          <td><span class="badge ${isSameUnit ? "success-badge" : "warning-badge"}">${item.unit || ""}</span></td>
          <td><b style="color:var(--text);">${priceStr} VNĐ</b></td>
          <td>${brand}</td>
          <td>${bidder
                ? `<div style="font-weight:600;color:var(--text);">${bidder}</div>${project ? `<small style="color:var(--text-muted);">${project}</small>` : ""}`
                : `<span style="color:var(--text-muted);">Không rõ nhà thầu</span>${project ? `<br><small style="color:var(--text-muted);">${project}</small>` : ""}`}</td>
        </tr>`;
    }).join("");
  }

  if (ragSort) ragSort.addEventListener("change", renderRagRows);
  if (ragBidder) ragBidder.addEventListener("change", renderRagRows);
});
