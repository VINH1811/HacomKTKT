const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const MODE_COPY = {
  package: {
    title: "Đối chiếu phụ lục và hồ sơ nhà thầu",
    formTitle: "Tài liệu cần đối chiếu",
    formHelp: "Các file Excel phải có định dạng .xlsx.",
    button: "Bắt đầu kiểm tra",
    hint: "Có thể chọn một file để đối chiếu riêng với phụ lục, hoặc nhiều file để so sánh thêm về giá."
  },
  bidders: {
    title: "So sánh ngang các hồ sơ nhà thầu",
    formTitle: "Hồ sơ nhà thầu cần so sánh",
    formHelp: "Chọn từ hai file Excel trở lên.",
    button: "Bắt đầu so sánh",
    hint: "Chọn từ hai file trở lên. Hệ thống không lấy nhà thầu đầu tiên làm chuẩn."
  },
  tender: {
    title: "Đối chiếu HSMT với các HSDT",
    formTitle: "Hồ sơ mời thầu và hồ sơ dự thầu",
    formHelp: "Chọn một HSMT và ít nhất một HSDT định dạng .xlsx.",
    button: "Bắt đầu đối chiếu",
    hint: "Chọn ít nhất một hồ sơ dự thầu. Bạn có thể đổi tên nhà thầu trước khi chạy."
  },
  ocr: {
    title: "Quét PDF hoặc ảnh scan sang Excel",
    formTitle: "Tài liệu scan cần số hóa",
    formHelp: "Có thể chọn nhiều PDF hoặc ảnh trong cùng một tác vụ.",
    button: "Bắt đầu quét tài liệu"
  }
};

let mode = "package";
let bidderFiles = [];
let ocrFiles = [];
let pollTimer = null;
let currentJobId = null;
let toastTimer = null;

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[char]);
}

function formatNumber(value, maximumFractionDigits = 0) {
  return Number(value || 0).toLocaleString("vi-VN", {maximumFractionDigits});
}

function fileSize(bytes) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function notify(message, type = "info") {
  const toast = $("#toast");
  if (type === "error") {
    toast.innerHTML = `
      <div class="toast-error-title">CẢNH BÁO LỖI PHÂN TÍCH FILE</div>
      <div class="toast-error-body">${escapeHtml(message)}</div>
      <button class="toast-error-close" type="button">Đóng</button>
    `;
  } else {
    toast.textContent = message;
  }
  toast.className = `toast show${type === "error" ? " error" : ""}`;
  clearTimeout(toastTimer);
  
  toast.onclick = () => {
    toast.className = "toast";
  };
  
  const duration = type === "error" ? 20000 : 3500;
  toastTimer = setTimeout(() => {
    toast.className = "toast";
  }, duration);
}

function setMode(nextMode) {
  mode = nextMode;
  $$(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.mode === mode));
  const copy = MODE_COPY[mode];
  $("#pageTitle").textContent = copy.title;
  $("#pageDescription").textContent = copy.description;
  $("#formTitle").textContent = copy.formTitle;
  $("#formHelp").textContent = copy.formHelp;
  $("#startButtonText").textContent = copy.button;
  $("#bidderHint").textContent = copy.hint || "";
  $("#comparisonFields").classList.toggle("hidden", mode === "ocr");
  $("#ocrFields").classList.toggle("hidden", mode !== "ocr");
  $("#packageFields").classList.toggle("hidden", mode !== "package");
  $("#tenderFields").classList.toggle("hidden", mode !== "tender");
  $("#progressPanel").classList.add("hidden");
  $("#resultPanel").classList.add("hidden");
  updatePackageBehavior();
  window.scrollTo({top: 0, behavior: "smooth"});
}

function updatePackageBehavior() {
  const note = $("#packageBehavior");
  const isPackage = mode === "package";
  note.classList.toggle("hidden", !isPackage);

  if (isPackage && bidderFiles.length === 1) {
    note.className = "mode-note single";
    note.textContent = "Chế độ 1 nhà thầu: hệ thống chỉ đối chiếu hạng mục, mã, đơn vị, khối lượng và yêu cầu trong PL01/PL02. Không so sánh giá với nhà thầu khác.";
  } else if (isPackage && bidderFiles.length >= 2) {
    note.className = "mode-note multi";
    note.textContent = `Chế độ ${bidderFiles.length} nhà thầu: mỗi file vẫn được đối chiếu riêng với phụ lục và hệ thống bổ sung so sánh giá ngang hàng giữa các nhà thầu.`;
  } else {
    note.className = isPackage ? "mode-note" : "mode-note hidden";
    note.textContent = "Chọn 1 file: kiểm tra hạng mục, mã, đơn vị, khối lượng và yêu cầu trong phụ lục. Chọn từ 2 file: hệ thống bổ sung so sánh giá giữa các nhà thầu.";
  }

  const disablePackagePrice = isPackage && bidderFiles.length < 2;
  ["#priceWarn", "#priceCritical"].forEach((selector) => {
    $(selector).disabled = disablePackagePrice;
    $(selector).title = disablePackagePrice
      ? "Ngưỡng giá chỉ dùng khi có từ hai hồ sơ nhà thầu."
      : "";
  });
}

function updateSingleFile(inputId, labelId) {
  const input = $(inputId);
  const label = $(labelId);
  const box = input.closest(".upload-box");
  const file = input.files[0];
  label.textContent = file ? `${file.name} · ${fileSize(file.size)}` : "Chưa chọn file";
  box.classList.toggle("has-file", Boolean(file));
}

function renderBidderFiles() {
  const container = $("#bidderList");
  if (!bidderFiles.length) {
    container.className = "selected-list empty-state";
    container.textContent = "Chưa có hồ sơ nhà thầu nào được chọn.";
    updatePackageBehavior();
    return;
  }
  container.className = "selected-list";
  container.innerHTML = bidderFiles.map((item, index) => `
    <div class="selected-file" data-index="${index}">
      <div class="file-info"><b>${escapeHtml(item.file.name)}</b><small>${fileSize(item.file.size)}</small></div>
      <input class="bidder-name" value="${escapeHtml(item.name)}" aria-label="Tên nhà thầu ${index + 1}">
      <button class="remove-file" type="button" data-remove-bidder="${index}" aria-label="Bỏ file">×</button>
    </div>`).join("");
  $$(".bidder-name").forEach((input, index) => input.addEventListener("input", () => bidderFiles[index].name = input.value));
  $$('[data-remove-bidder]').forEach((button) => button.addEventListener("click", () => {
    bidderFiles.splice(Number(button.dataset.removeBidder), 1);
    renderBidderFiles();
  }));
  updatePackageBehavior();
}

function renderOcrFiles() {
  const container = $("#ocrFileList");
  if (!ocrFiles.length) {
    container.className = "selected-list empty-state";
    container.textContent = "Chưa có tài liệu scan nào được chọn.";
    return;
  }
  container.className = "selected-list";
  container.innerHTML = ocrFiles.map((file, index) => `
    <div class="selected-file" data-index="${index}">
      <div class="file-info"><b>${escapeHtml(file.name)}</b><small>${fileSize(file.size)}</small></div>
      <span></span>
      <button class="remove-file" type="button" data-remove-ocr="${index}" aria-label="Bỏ file">×</button>
    </div>`).join("");
  $$('[data-remove-ocr]').forEach((button) => button.addEventListener("click", () => {
    ocrFiles.splice(Number(button.dataset.removeOcr), 1);
    renderOcrFiles();
  }));
}

function resetFiles() {
  ["#pl1", "#pl2", "#hsmt", "#bidderFiles", "#ocrFiles"].forEach((id) => { $(id).value = ""; });
  bidderFiles = [];
  ocrFiles = [];
  updateSingleFile("#pl1", "#pl1Name");
  updateSingleFile("#pl2", "#pl2Name");
  updateSingleFile("#hsmt", "#hsmtName");
  renderBidderFiles();
  renderOcrFiles();
  updatePackageBehavior();
}

function validateComparison() {
  const minimum = mode === "bidders" ? 2 : 1;
  if (bidderFiles.length < minimum) return `Cần chọn ít nhất ${minimum} hồ sơ nhà thầu.`;
  if (bidderFiles.some((item) => !item.name.trim())) return "Tên nhà thầu không được để trống.";
  if (mode === "package" && !$("#pl1").files[0] && !$("#pl2").files[0]) return "Cần chọn ít nhất Phụ lục 01 hoặc Phụ lục 02.";
  if (mode === "tender" && !$("#hsmt").files[0]) return "Cần chọn file hồ sơ mời thầu.";
  return "";
}

function buildComparisonData() {
  const data = new FormData();
  if (mode === "package") {
    if ($("#pl1").files[0]) data.append("pl1", $("#pl1").files[0]);
    if ($("#pl2").files[0]) data.append("pl2", $("#pl2").files[0]);
  }
  if (mode === "tender") data.append("hsmt", $("#hsmt").files[0]);
  bidderFiles.forEach((item) => { data.append("files", item.file); data.append("bidder_names", item.name.trim()); });
  data.append("price_warn_pct", Number($("#priceWarn").value || 10) / 100);
  data.append("price_critical_pct", Number($("#priceCritical").value || 25) / 100);
  data.append("quantity_warn_pct", Number($("#quantityWarn").value || 5) / 100);
  data.append("quantity_critical_pct", Number($("#quantityCritical").value || 15) / 100);
  return data;
}

function buildOcrData() {
  const data = new FormData();
  ocrFiles.forEach((file) => data.append("files", file));
  data.append("accuracy_mode", $("#accuracyMode").value);
  data.append("document_profile", $("#documentProfile").value);
  data.append("save_review_images", $("#saveReviewImages").checked ? "true" : "false");
  return data;
}

function setWorking(working) {
  $("#startButton").disabled = working;
  $("#resetButton").disabled = working;
  $$(".nav-item").forEach((button) => button.disabled = working);
}

function showProgress(initialMessage) {
  $("#progressPanel").classList.remove("hidden");
  $("#resultPanel").classList.add("hidden");
  $("#progressBar").style.width = "0%";
  $("#progressPercent").textContent = "0%";
  $("#progressMessage").textContent = initialMessage;
  $("#progressMode").textContent = MODE_COPY[mode].title;
  $("#progressPanel").scrollIntoView({behavior: "smooth", block: "center"});
}

async function submitWork(event) {
  event.preventDefault();
  let endpoint;
  let data;
  if (mode === "ocr") {
    if (!ocrFiles.length) return notify("Cần chọn ít nhất một PDF hoặc ảnh scan.", "error");
    endpoint = "/api/ocr";
    data = buildOcrData();
  } else {
    const error = validateComparison();
    if (error) return notify(error, "error");
    endpoint = mode === "package" ? "/api/compare-package" : mode === "bidders" ? "/api/compare-bidders" : "/api/compare-tender";
    data = buildComparisonData();
  }
  setWorking(true);
  showProgress("Đang tải tài liệu lên hệ thống...");
  try {
    const response = await fetch(endpoint, {method: "POST", body: data});
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || "Không thể tạo tác vụ.");
    currentJobId = payload.job_id;
    saveRecentJob({id: currentJobId, mode, title: MODE_COPY[mode].title, state: "running", createdAt: Date.now()});
    pollJob(currentJobId);
  } catch (error) {
    setWorking(false);
    $("#progressPanel").classList.add("hidden");
    notify(error.message, "error");
  }
}

async function pollJob(jobId) {
  clearTimeout(pollTimer);
  try {
    const response = await fetch(`/api/jobs/${jobId}`, {cache: "no-store"});
    const status = await response.json();
    if (!response.ok) throw new Error(status.detail || "Không đọc được trạng thái tác vụ.");
    const progress = Math.max(0, Math.min(100, Number(status.progress || 0)));
    $("#progressBar").style.width = `${progress}%`;
    $("#progressPercent").textContent = `${progress}%`;
    $("#progressMessage").textContent = status.message || "Đang xử lý...";
    if (status.state === "done") {
      const resultResponse = await fetch(`/api/jobs/${jobId}/result`, {cache: "no-store"});
      const result = await resultResponse.json();
      if (!resultResponse.ok) throw new Error(result.detail || "Không thể đọc kết quả.");
      setWorking(false);
      updateRecentJob(jobId, "done");
      renderResult(jobId, result);
      return;
    }
    if (status.state === "failed") {
      setWorking(false);
      updateRecentJob(jobId, "failed");
      throw new Error(status.message || "Tác vụ xử lý thất bại.");
    }
    pollTimer = setTimeout(() => pollJob(jobId), 1000);
  } catch (error) {
    setWorking(false);
    notify(error.message, "error");
  }
}

function resultLink(href, text, primary = false) {
  return `<a class="download-button ${primary ? "primary" : "secondary"}" href="${href}">${escapeHtml(text)}</a>`;
}

function renderResult(jobId, data) {
  $("#progressPanel").classList.add("hidden");
  $("#resultPanel").classList.remove("hidden");
  const isOcr = data.kind === "ocr";
  const resultMode = String(data.audit?.mode || "");
  const isPackageResult = resultMode.startsWith("PL01_") || resultMode.startsWith("PL02_");
  $("#resultTitle").textContent = isOcr ? "Đã hoàn tất quét tài liệu" : "Đã hoàn tất kiểm tra";
  if (isOcr) {
    $("#resultSubtitle").textContent = "Các file Excel đã được tạo; những ô chưa chắc chắn được liệt kê để xác nhận.";
  } else if (isPackageResult && data.summary?.peer_price_comparison_enabled) {
    $("#resultSubtitle").textContent = "Đã đối chiếu từng hồ sơ với phụ lục và bổ sung so sánh giá giữa các nhà thầu.";
  } else if (isPackageResult) {
    $("#resultSubtitle").textContent = "Đã đối chiếu hồ sơ nhà thầu với các nội dung có trong phụ lục; không thực hiện so sánh giá ngang hàng.";
  } else {
    $("#resultSubtitle").textContent = "Báo cáo tổng hợp và các file kết quả đã sẵn sàng.";
  }

  const files = data.files || {};
  const actions = [];
  if (files.package) actions.push(resultLink(`/api/jobs/${jobId}/download-package`, isOcr ? "Tải toàn bộ kết quả OCR" : "Tải toàn bộ kết quả", true));
  if (!isOcr || !files.package) actions.push(resultLink(`/api/jobs/${jobId}/download`, isOcr ? "Tải file Excel đầu tiên" : "Tải báo cáo tổng", !files.package));
  const individual = isOcr ? (files.ocr_files || {}) : (files.annotated_files || {});
  Object.entries(individual).forEach(([name, filename]) => actions.push(resultLink(`/api/jobs/${jobId}/download-file/${encodeURIComponent(filename)}`, `${isOcr ? "Tải OCR" : "Tải file đánh dấu"}: ${name}`)));
  $("#resultActions").innerHTML = actions.join("");

  const summary = data.summary || {};
  const metricRows = isOcr ? [
    ["Tài liệu", summary.file_count], ["Trang", summary.pages], ["Bảng", summary.tables], ["Dòng dữ liệu", summary.rows], ["Ô cần kiểm tra", summary.review_cells], ["Dòng cần kiểm tra", summary.review_rows]
  ] : [
    ["Nhà thầu", summary.bidder_count], ["Hạng mục", summary.total_reference_items], ["Dòng đối chiếu", summary.total_rows], ["Cần kiểm tra", summary.review_rows], ["Cảnh báo", summary.warning_rows], ["Bất thường", summary.critical_rows]
  ];
  $("#metrics").innerHTML = metricRows.map(([label, value]) => `<div class="metric"><b>${formatNumber(value)}</b><span>${escapeHtml(label)}</span></div>`).join("");

  const documents = data.documents || [];
  $("#documentResults").innerHTML = isOcr ? `<div class="block-title"><h3>Kết quả theo tài liệu</h3><span>${documents.length} tài liệu</span></div>` + documents.map((doc) => {
    const s = doc.summary || {};
    return `<div class="document-card"><div class="document-card-head"><div><h4>${escapeHtml(doc.source)}</h4><p>${escapeHtml(doc.output || "")}</p></div></div><div class="document-stats"><span>${formatNumber(s.pages)} trang</span><span>${formatNumber(s.tables)} bảng</span><span>${formatNumber(s.rows)} dòng</span><span>${formatNumber(s.review_cells)} ô cần xem lại</span><span>Độ tin cậy ${formatNumber(Number(s.average_confidence || 0) * 100, 1)}%</span></div></div>`;
  }).join("") : "";

  const warningsBlock = $("#warningsBlock");
  if (warningsBlock) {
    const warnings = data.warnings || [];
    warningsBlock.classList.toggle("hidden", !warnings.length);
    const warningCount = $("#warningCount");
    if (warningCount) warningCount.textContent = warnings.length ? `${warnings.length} cảnh báo` : "";
    const warningsEl = $("#warnings");
    if (warningsEl) warningsEl.innerHTML = warnings.slice(0, 100).map((warning) => `<div class="warning-item">${escapeHtml(warning)}</div>`).join("");
  }

  const anomalies = data.anomalies || [];
  $("#anomalyBlock").classList.toggle("hidden", !anomalies.length);
  $("#anomalyCount").textContent = anomalies.length ? `${anomalies.length} dòng hiển thị` : "";
  $("#anomalyRows").innerHTML = anomalies.map((row) => {
    const severityText = String(row.severity || "");
    const severityClass = severityText.includes("BẤT") ? "critical" : severityText.includes("CẢNH") ? "warning" : "review";
    return `<tr><td><span class="severity ${severityClass}">${escapeHtml(severityText)}</span></td><td>${escapeHtml(row.bidder)}</td><td>${escapeHtml(row.sheet)}</td><td>${escapeHtml(row.stt)}</td><td>${escapeHtml(row.name)}</td><td>${(row.flags || []).map(escapeHtml).join("<br>")}</td></tr>`;
  }).join("");
  $("#resultPanel").scrollIntoView({behavior: "smooth", block: "start"});
}

function getHistory() {
  try { return JSON.parse(localStorage.getItem("hsmt_recent_jobs") || "[]"); } catch { return []; }
}

function setHistory(items) {
  localStorage.setItem("hsmt_recent_jobs", JSON.stringify(items.slice(0, 8)));
  renderHistory();
}

function saveRecentJob(job) {
  const items = getHistory().filter((item) => item.id !== job.id);
  items.unshift(job);
  setHistory(items);
}

function updateRecentJob(id, state) {
  setHistory(getHistory().map((item) => item.id === id ? {...item, state} : item));
}

function renderHistory() {
  const container = $("#recentJobs");
  if (!container) return;
  const history = getHistory();
  if (!history.length) {
    container.className = "recent-jobs empty-state";
    container.textContent = "Chưa có tác vụ nào trên trình duyệt này.";
    return;
  }
  container.className = "recent-jobs";
  container.innerHTML = history.map((item) => `<div class="recent-job" data-job-id="${escapeHtml(item.id)}"><b>${escapeHtml(item.title)}</b><small>${new Date(item.createdAt).toLocaleString("vi-VN")} · ${item.state === "done" ? "Đã xong" : item.state === "failed" ? "Thất bại" : "Đang xử lý"}</small></div>`).join("");
  $$(".recent-job").forEach((card) => card.addEventListener("click", async () => {
    const id = card.dataset.jobId;
    try {
      const response = await fetch(`/api/jobs/${id}`);
      const status = await response.json();
      if (!response.ok) throw new Error(status.detail || "Tác vụ không còn tồn tại.");
      currentJobId = id;
      setMode(status.mode || "package");
      if (status.state === "done") {
        const result = await (await fetch(`/api/jobs/${id}/result`)).json();
        renderResult(id, result);
      } else if (status.state === "failed") {
        notify(status.message || "Tác vụ đã thất bại.", "error");
      } else {
        setWorking(true);
        showProgress(status.message || "Đang xử lý...");
        pollJob(id);
      }
    } catch (error) { notify(error.message, "error"); }
  }));
}

async function checkHealth() {
  try {
    const response = await fetch("/api/health", {cache: "no-store"});
    const data = await response.json();
    if (!response.ok) throw new Error();
    const healthDot = $("#healthDot");
    const sidebarStatusDot = $("#sidebarStatusDot");
    if (healthDot) healthDot.classList.add("online");
    if (sidebarStatusDot) sidebarStatusDot.classList.add("online");
  } catch {
    const healthDot = $("#healthDot");
    const sidebarStatusDot = $("#sidebarStatusDot");
    const healthText = $("#healthText");
    const sidebarStatus = $("#sidebarStatus");
    if (healthDot) healthDot.classList.add("offline");
    if (sidebarStatusDot) sidebarStatusDot.classList.add("offline");
    if (healthText) healthText.textContent = "Không kết nối được";
    if (sidebarStatus) sidebarStatus.textContent = "Mất kết nối";
  }
}

$$(".nav-item").forEach((button) => button.addEventListener("click", () => setMode(button.dataset.mode)));
[["#pl1", "#pl1Name"], ["#pl2", "#pl2Name"], ["#hsmt", "#hsmtName"]].forEach(([input, label]) => {
  const el = $(input);
  if (el) {
    el.addEventListener("change", () => {
      const file = el.files[0];
      if (file && !file.name.toLowerCase().endsWith(".xlsx")) {
        notify("Không đúng định dạng.", "error");
        el.value = "";
      }
      updateSingleFile(input, label);
    });
  }
});
[["#removePl1", "#pl1", "#pl1Name"], ["#removePl2", "#pl2", "#pl2Name"], ["#removeHsmt", "#hsmt", "#hsmtName"]].forEach(([removeBtnId, inputId, labelId]) => {
  const removeBtn = $(removeBtnId);
  if (removeBtn) {
    removeBtn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      const input = $(inputId);
      input.value = "";
      updateSingleFile(inputId, labelId);
    });
  }
});
const bidderFilesEl = $("#bidderFiles");
if (bidderFilesEl) {
  bidderFilesEl.addEventListener("change", (event) => {
    const existing = new Set(
      bidderFiles.map((item) => `${item.file.name}|${item.file.size}|${item.file.lastModified}`)
    );
    [...event.target.files].forEach((file) => {
      if (!file.name.toLowerCase().endsWith(".xlsx")) {
        notify("Không đúng định dạng.", "error");
        return;
      }
      const key = `${file.name}|${file.size}|${file.lastModified}`;
      if (!existing.has(key)) {
        bidderFiles.push({file, name: file.name.replace(/\.xlsx$/i, "")});
        existing.add(key);
      }
    });
    event.target.value = "";
    renderBidderFiles();
  });
}
const ocrFilesEl = $("#ocrFiles");
if (ocrFilesEl) {
  ocrFilesEl.addEventListener("change", (event) => {
    const allowedExtensions = [".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"];
    const validFiles = [];
    [...event.target.files].forEach((file) => {
      const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
      if (!allowedExtensions.includes(ext)) {
        notify("Không đúng định dạng.", "error");
        return;
      }
      validFiles.push(file);
    });
    ocrFiles = validFiles;
    event.target.value = "";
    renderOcrFiles();
  });
}
const workFormEl = $("#workForm");
if (workFormEl) {
  workFormEl.addEventListener("submit", submitWork);
}
const resetButtonEl = $("#resetButton");
if (resetButtonEl) {
  resetButtonEl.addEventListener("click", resetFiles);
}
const newTaskButtonEl = $("#newTaskButton");
if (newTaskButtonEl) {
  newTaskButtonEl.addEventListener("click", () => { resetFiles(); $("#resultPanel").classList.add("hidden"); window.scrollTo({top: 0, behavior: "smooth"}); });
}
const clearHistoryEl = $("#clearHistory");
if (clearHistoryEl) {
  clearHistoryEl.addEventListener("click", () => setHistory([]));
}

setMode("package");
renderHistory();
checkHealth();
