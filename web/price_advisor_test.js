// PriceAdvisor WEB test — v2.0 Premium UI
// Chạy sau khi HTML đã được inject vào DOM (đảm bảo bởi price_advisor_test_page.html)
(function(){
  var $ = function(sel){ return document.querySelector(sel); };

  var currentJobId = null;
  var currentSuggestedPrice = null;

  function escapeHtml(value){
    return String(value ?? '').replace(/[&<>"']/g, function(c){
      return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c];
    });
  }

  function fmtPrice(val){
    if(val == null || val === '') return 'Không rõ';
    return Number(val).toLocaleString('vi-VN') + ' đ';
  }

  // ─── Drag & Drop File Upload ───────────────────────────────────────────────
  var uploadZone = $('#paUploadZone');
  var fileInput  = $('#paTestFile');
  var fileInfo   = $('#paFileInfo');
  var fileName   = $('#paFileName');
  var fileRemove = $('#paFileRemove');

  function updateFileInfo(){
    if(fileInput && fileInput.files && fileInput.files.length){
      if(fileName) fileName.textContent = fileInput.files[0].name;
      if(fileInfo)   fileInfo.style.display   = 'flex';
      if(uploadZone) uploadZone.style.display = 'none';
    } else {
      if(fileInfo)   fileInfo.style.display   = 'none';
      if(uploadZone) uploadZone.style.display = 'flex';
    }
  }

  if(uploadZone && fileInput){
    uploadZone.addEventListener('click', function(){ fileInput.click(); });
    uploadZone.addEventListener('dragover', function(e){
      e.preventDefault();
      uploadZone.classList.add('dragover');
    });
    uploadZone.addEventListener('dragleave', function(){
      uploadZone.classList.remove('dragover');
    });
    uploadZone.addEventListener('drop', function(e){
      e.preventDefault();
      uploadZone.classList.remove('dragover');
      if(e.dataTransfer && e.dataTransfer.files.length){
        // Use DataTransfer to assign files to input
        try { fileInput.files = e.dataTransfer.files; } catch(ex){}
        updateFileInfo();
      }
    });
    fileInput.addEventListener('change', updateFileInfo);
  }

  if(fileRemove){
    fileRemove.addEventListener('click', function(e){
      e.stopPropagation();
      fileInput.value = '';
      updateFileInfo();
    });
  }

  // ─── Progress bar helper ─────────────────────────────────────────────────
  function setProgress(msg, pct, show){
    var container = $('#paProgressContainer');
    var msgEl     = $('#paProgressMsg');
    var pctEl     = $('#paProgressPct');
    var fillEl    = $('#paProgressBarFill');
    if(!container) return;
    container.style.display = show ? 'block' : 'none';
    if(msgEl)  msgEl.textContent  = msg;
    if(pctEl)  pctEl.textContent  = pct + '%';
    if(fillEl) fillEl.style.width = pct + '%';
  }

  // ─── Feedback Modal ────────────────────────────────────────────────────────
  var modal            = $('#paFeedbackModal');
  var modalClose       = $('#paModalClose');
  var modalTitle       = $('#paModalTitle');
  var feedbackAction   = $('#paFeedbackAction');
  var feedbackPriceGrp = $('#paFeedbackPriceGroup');
  var feedbackPriceEl  = $('#paFeedbackPrice');
  var feedbackNoteGrp  = $('#paFeedbackNoteGroup');
  var feedbackNoteEl   = $('#paFeedbackNote');
  var feedbackSubmit   = $('#paFeedbackSubmitBtn');

  function openFeedbackModal(action, defaultPrice){
    if(!modal) return;
    feedbackAction.value     = action;
    if(feedbackNoteEl) feedbackNoteEl.value = '';
    if(action === 'accepted'){
      if(modalTitle) modalTitle.textContent = '👍 Chấp nhận đơn giá gợi ý';
      if(feedbackPriceGrp) feedbackPriceGrp.style.display = 'block';
      if(feedbackPriceEl)  feedbackPriceEl.value = defaultPrice || '';
      if(feedbackNoteGrp)  feedbackNoteGrp.style.display  = 'block';
      if(feedbackNoteEl)   feedbackNoteEl.placeholder = 'Ghi chú thêm (không bắt buộc)...';
    } else {
      if(modalTitle) modalTitle.textContent = '👎 Từ chối đơn giá gợi ý';
      if(feedbackPriceGrp) feedbackPriceGrp.style.display = 'none';
      if(feedbackPriceEl)  feedbackPriceEl.value = '';
      if(feedbackNoteGrp)  feedbackNoteGrp.style.display  = 'block';
      if(feedbackNoteEl)   feedbackNoteEl.placeholder = 'Nhập lý do từ chối (bắt buộc)...';
    }
    modal.style.display = 'flex';
  }

  if(modalClose){
    modalClose.addEventListener('click', function(){ modal.style.display = 'none'; });
  }
  if(modal){
    modal.addEventListener('click', function(e){
      if(e.target === modal) modal.style.display = 'none';
    });
  }

  if(feedbackSubmit){
    feedbackSubmit.addEventListener('click', async function(){
      var action = feedbackAction ? feedbackAction.value : 'accepted';
      var note   = feedbackNoteEl ? feedbackNoteEl.value.trim() : '';
      var price  = feedbackPriceEl ? parseFloat(feedbackPriceEl.value) : NaN;

      if(action === 'rejected' && !note){
        alert('Vui lòng nhập lý do từ chối.');
        return;
      }

      var payload = {
        job_id: currentJobId,
        item_id: 'test_item_1',
        action: action,
        suggested_price: (action === 'accepted' && !isNaN(price)) ? price : null,
        note: note
      };

      feedbackSubmit.disabled = true;
      feedbackSubmit.textContent = 'Đang gửi...';
      try {
        var resp = await fetch('/api/price-advisor/feedback', {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify(payload)
        });
        if(resp.ok){
          alert('Gửi phản hồi thành công! Dữ liệu đã được lưu vào nhật ký đào tạo AI.');
          modal.style.display = 'none';
          var btnA = $('#paBtnAccept');
          var btnR = $('#paBtnReject');
          if(action === 'accepted'){
            if(btnA) btnA.className = 'pa-feedback-btn pa-feedback-accept active-accepted';
            if(btnR) btnR.className = 'pa-feedback-btn pa-feedback-reject';
          } else {
            if(btnA) btnA.className = 'pa-feedback-btn pa-feedback-accept';
            if(btnR) btnR.className = 'pa-feedback-btn pa-feedback-reject active-rejected';
          }
        } else {
          var err = await resp.json().catch(function(){return{};});
          alert('Lỗi: ' + (err.detail || 'Không gửi được phản hồi'));
        }
      } catch(e){
        alert('Lỗi kết nối: ' + e.message);
      } finally {
        feedbackSubmit.disabled = false;
        feedbackSubmit.textContent = 'Gửi phản hồi';
      }
    });
  }

  // ─── Render Result ─────────────────────────────────────────────────────────
  function renderResult(result){
    var placeholder = $('#paResultPlaceholder');
    var content     = $('#paResultContent');

    if(!result || !result.suggestions || !result.suggestions.length){
      if(placeholder){
        placeholder.style.display = 'flex';
        placeholder.innerHTML = '<div class="pa-result-placeholder-icon">⚠️</div>'
          + '<h4 style="margin:0;font-size:16px;font-weight:700;">Không có gợi ý</h4>'
          + '<p style="margin:0;font-size:13px;max-width:280px;line-height:1.4;">Không tìm thấy kết quả phù hợp. Hãy kiểm tra lại Ollama có đang chạy không.</p>';
      }
      if(content) content.style.display = 'none';
      return;
    }

    var s = result.suggestions[0];
    currentSuggestedPrice = s.suggested_price;

    if(placeholder) placeholder.style.display = 'none';
    if(content)     content.style.display = 'block';

    // Suggested Price
    var valEl = $('#paSuggestedValue');
    if(valEl) valEl.textContent = fmtPrice(s.suggested_price);

    var rangeEl = $('#paSuggestedRange');
    if(rangeEl){
      if(s.min_price != null && s.max_price != null){
        rangeEl.textContent = 'Khoảng giá phù hợp: ' + fmtPrice(s.min_price) + ' – ' + fmtPrice(s.max_price);
      } else {
        rangeEl.textContent = 'Khoảng giá phù hợp: Không xác định';
      }
    }

    // Confidence Ring
    var conf = typeof s.confidence === 'number' ? Math.round(s.confidence * 100) : 0;
    var confValEl = $('#paConfidenceVal');
    if(confValEl) confValEl.textContent = conf + '%';
    var circle = $('#paConfidenceCircle');
    if(circle){
      circle.setAttribute('stroke-dasharray', conf + ', 100');
      circle.setAttribute('stroke', conf >= 75 ? '#10b981' : conf >= 50 ? '#f59e0b' : '#ef4444');
    }

    // Status chip color
    var priceCard = document.querySelector('.pa-price-card');
    if(priceCard){
      priceCard.style.setProperty('--accent', conf >= 75 ? '#10b981' : conf >= 50 ? '#f59e0b' : '#ef4444');
    }

    // Reasoning
    var reasonEl = $('#paReasoningText');
    if(reasonEl) reasonEl.textContent = s.reasoning || 'Không có lý do chi tiết từ mô hình.';

    // Price comment
    var commentEl = $('#paPriceCommentText');
    if(commentEl) commentEl.textContent = s.price_comment || 'Chưa có nhận xét riêng về mức giá dự đoán.';

    // Status badge
    var statusBadge = $('#paResultStatus');
    if(statusBadge){
      var statusMap = {
        'validated':    {icon:'✅', text:'Đã xác nhận', color:'#059669'},
        'needs_review': {icon:'⚠️', text:'Cần xem lại', color:'#d97706'},
        'failed':       {icon:'❌', text:'Thất bại',    color:'#dc2626'},
        'pending':      {icon:'⏳', text:'Đang chờ',   color:'#64748b'}
      };
      var st = statusMap[s.status] || {icon:'ℹ️', text: s.status, color: '#64748b'};
      statusBadge.innerHTML = st.icon + ' ' + st.text;
      statusBadge.style.color = st.color;
    }

    // Feedback buttons
    var btnA = $('#paBtnAccept');
    var btnR = $('#paBtnReject');
    if(btnA){
      btnA.className = 'pa-feedback-btn pa-feedback-accept';
      btnA.onclick   = function(){ openFeedbackModal('accepted', currentSuggestedPrice); };
    }
    if(btnR){
      btnR.className = 'pa-feedback-btn pa-feedback-reject';
      btnR.onclick   = function(){ openFeedbackModal('rejected', null); };
    }

    // Similar Items
    var similarItems  = s.similar_items || [];
    var similarList   = $('#paSimilarList');
    var similarTitle  = $('#paSimilarTitle');
    if(similarTitle) similarTitle.textContent = 'Dữ liệu giá lịch sử tham khảo (RAG — ' + similarItems.length + ' mẫu)';
    if(similarList){
      if(!similarItems.length){
        similarList.innerHTML = '<div style="padding:24px;text-align:center;color:var(--pa-text-muted);font-size:13px;">Không tìm thấy dữ liệu giá tham khảo trùng khớp trong CSDL.</div>';
      } else {
        similarList.innerHTML = similarItems.map(function(item){
          var price = item.unit_price != null ? fmtPrice(item.unit_price) : 'Chưa có giá';
          var score = typeof item.similarity === 'number' ? Math.round(item.similarity * 100) : 0;
          var parts = [];
          if(item.project_name) parts.push(item.project_name);
          if(item.year)         parts.push('Năm: ' + item.year);
          if(item.brand)        parts.push('Hiệu: ' + item.brand);
          if(item.region)       parts.push(item.region);
          return '<div class="pa-similar-item">'
            + '<div class="pa-sim-left">'
            + '<div class="pa-sim-name">' + escapeHtml(item.item_name) + '</div>'
            + '<div class="pa-sim-meta">' + escapeHtml(parts.join(' • ')) + '</div>'
            + '</div>'
            + '<div class="pa-sim-right">'
            + '<div class="pa-sim-price">' + price + '</div>'
            + '<div class="pa-sim-score">' + score + '% khớp</div>'
            + '</div>'
            + '</div>';
        }).join('');
      }
    }
  }

  // ─── Main: Import & Run ─────────────────────────────────────────────────────
  function importAndRun(){
    var fileEl    = $('#paTestFile');
    var itemNameEl = $('#paTestItemName');
    var unitEl     = $('#paTestUnit');
    var noEmbedEl  = $('#paTestNoEmbed');
    var sheetEl    = $('#paTestSheet');
    var runBtn     = $('#paTestRunBtn');

    var file      = fileEl && fileEl.files ? fileEl.files[0] : null;
    var item_name = (itemNameEl ? itemNameEl.value : '').trim();
    var unit      = (unitEl ? unitEl.value : '').trim();
    var sheet     = (sheetEl ? sheetEl.value : '').trim() || null;

    if(!file)     { alert('Chưa chọn file Excel (.xlsx)'); return; }
    if(!item_name){ alert('Nhập tên hạng mục để test');    return; }
    if(!unit)     { alert('Nhập đơn vị tính');             return; }

    // Disable button during request
    if(runBtn){ runBtn.disabled = true; runBtn.textContent = 'Đang xử lý...'; }

    // Reset result panel
    var placeholder = $('#paResultPlaceholder');
    var content     = $('#paResultContent');
    if(placeholder){ 
      placeholder.style.display = 'flex';
      placeholder.innerHTML = '<div class="pa-result-placeholder-icon" style="animation:spin 1s linear infinite">⏳</div>'
        + '<h4 style="margin:0;font-size:16px;font-weight:700;">Đang xử lý...</h4>'
        + '<p style="margin:0;font-size:13px;max-width:280px;line-height:1.4;">Mô hình AI đang phân tích dữ liệu giá lịch sử. Vui lòng chờ.</p>';
    }
    if(content) content.style.display = 'none';

    setProgress('Đang tải lên và nạp dữ liệu Excel...', 15, true);

    var fd = new FormData();
    fd.append('file', file);
    fd.append('item_name', item_name);
    fd.append('unit', unit);
    if(sheet) fd.append('sheet', sheet);
    fd.append('no_embed', (noEmbedEl && noEmbedEl.checked) ? '1' : '0');

    fetch('/api/price-advisor/test/import', { method: 'POST', body: fd })
      .then(function(resp){
        if(!resp.ok) return resp.json().then(function(d){ throw new Error(d.detail || 'Import thất bại (HTTP ' + resp.status + ')'); });
        return resp.json();
      })
      .then(function(data){
        setProgress('Mô hình Qwen3:8b đang suy luận và dự đoán giá...', 60, true);
        currentJobId = data.job_id;

        var timer;
        function poll(){
          fetch('/api/price-advisor/test/result/' + encodeURIComponent(currentJobId), { cache: 'no-store' })
            .then(function(r){ return r.json(); })
            .then(function(d){
              if(d.state === 'done'){
                clearTimeout(timer);
                setProgress('Hoàn tất!', 100, true);
                setTimeout(function(){ setProgress('', 0, false); }, 1500);
                if(runBtn){ runBtn.disabled = false; runBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg> Dự đoán & Phân tích'; }
                renderResult(d.result);
              } else if(d.state === 'failed'){
                clearTimeout(timer);
                setProgress('', 0, false);
                if(runBtn){ runBtn.disabled = false; runBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg> Dự đoán & Phân tích'; }
                var placeholder2 = $('#paResultPlaceholder');
                if(placeholder2){
                  placeholder2.style.display = 'flex';
                  placeholder2.innerHTML = '<div class="pa-result-placeholder-icon">❌</div><h4 style="margin:0;color:#ef4444;">Lỗi xử lý</h4><p style="margin:0;font-size:13px;color:#64748b;">' + escapeHtml(d.message || 'Tác vụ thất bại.') + '</p>';
                }
              } else {
                timer = setTimeout(poll, 1200);
              }
            })
            .catch(function(err){
              setProgress('', 0, false);
              if(runBtn){ runBtn.disabled = false; runBtn.innerHTML = 'Dự đoán & Phân tích'; }
              alert('Lỗi polling: ' + err.message);
            });
        }
        poll();
      })
      .catch(function(err){
        setProgress('', 0, false);
        if(runBtn){ runBtn.disabled = false; runBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg> Dự đoán & Phân tích'; }
        alert('Lỗi: ' + err.message);
      });
  }

  // ─── Wire up button ────────────────────────────────────────────────────────
  var runBtn = $('#paTestRunBtn');
  if(runBtn){
    runBtn.addEventListener('click', importAndRun);
  }

  // Also expose globally in case called from elsewhere
  window.__paTestImportAndRun = importAndRun;

  // Add spin animation if not present
  if(!document.getElementById('paSpinStyle')){
    var style = document.createElement('style');
    style.id = 'paSpinStyle';
    style.textContent = '@keyframes spin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }';
    document.head.appendChild(style);
  }

})();
