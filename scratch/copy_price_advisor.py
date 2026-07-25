import shutil
from pathlib import Path
import json

# Paths
src_root = Path(r"c:\KHMT\HacomHolding\HacomKTKT")
dst_root = Path(r"c:\KHMT\HacomHoldings\HacomKTKT")

print("=== COPYING PRICE ADVISOR MODULE ===")

# 1. Copy core/price_advisor
src_core = src_root / "core" / "price_advisor"
dst_core = dst_root / "core" / "price_advisor"
if dst_core.exists():
    shutil.rmtree(dst_core)
shutil.copytree(src_core, dst_core)
print("✓ Copied core/price_advisor")

# 2. Copy web files
for f in ["price_advisor.html", "price_advisor_ui.js", "price_advisor_test.js", "price_advisor_test_page.html", "price_advisor_test_ui.html"]:
    src_f = src_root / "web" / f
    dst_f = dst_root / "web" / f
    if src_f.exists():
        shutil.copy2(src_f, dst_f)
        print(f"✓ Copied web/{f}")

# 3. Copy scripts
for f in ["preprocess_raw_data.py", "import_price_data.py"]:
    src_f = src_root / "scripts" / f
    dst_f = dst_root / "scripts" / f
    shutil.copy2(src_f, dst_f)
    print(f"✓ Copied scripts/{f}")

# 4. Copy scratch tools
dst_scratch = dst_root / "scratch"
dst_scratch.mkdir(exist_ok=True)
for f in ["clear_price_records.py", "query_hanger_prices.py", "test_advisor_item.py"]:
    src_f = src_root / "scratch" / f
    dst_f = dst_scratch / f
    if src_f.exists():
        shutil.copy2(src_f, dst_f)
        print(f"✓ Copied scratch/{f}")

# 5. Append/Merge .env
src_env_path = src_root / ".env"
dst_env_path = dst_root / ".env"

if src_env_path.exists():
    src_env_content = src_env_path.read_text(encoding="utf-8")
    pa_lines = [line for line in src_env_content.splitlines() if "PRICE_ADVISOR_" in line]
    
    if dst_env_path.exists():
        dst_env_content = dst_env_path.read_text(encoding="utf-8")
        existing_keys = [line.split("=")[0].strip() for line in dst_env_content.splitlines() if "=" in line]
        lines_to_add = []
        for line in pa_lines:
            if not line.strip() or line.startswith("#"):
                continue
            key = line.split("=")[0].strip()
            if key not in existing_keys:
                lines_to_add.append(line)
        if lines_to_add:
            with open(dst_env_path, "a", encoding="utf-8") as f:
                f.write("\n# PriceAdvisor configurations\n" + "\n".join(lines_to_add) + "\n")
            print("✓ Appended PriceAdvisor configurations to .env")
        else:
            print("✓ .env already has PriceAdvisor configuration keys")
    else:
        shutil.copy2(src_env_path, dst_env_path)
        print("✓ Created .env file in destination")

# 6. Patch app.py
print("\n=== PATCHING app.py ===")
app_path = dst_root / "app.py"
app_content = app_path.read_text(encoding="utf-8")

# A. Insert imports if not already present
import_marker = "from ocr.config import OCRConfig"
import_str = "from core.price_advisor import PriceAdvisor, PriceAdvisorConfig, SuggestionStatus"
if import_str not in app_content:
    app_content = app_content.replace(import_marker, f"{import_str}\n{import_marker}")
    print("✓ Added PriceAdvisor imports to app.py")

# B. Insert environmental default configurations if not present
env_default_marker = "from security import configure_offline_environment"
env_default_str = """# Fallback DB settings for PriceAdvisor test endpoints.
# This avoids Postgres connection/auth issues when only Ollama/LLM testing.
import os
os.environ.setdefault("PRICE_ADVISOR_DB_PROVIDER", "sqlite")
os.environ.setdefault("PRICE_ADVISOR_DB_PATH", str(BASE_DIR / "data" / "price_db.sqlite"))
"""
if "PRICE_ADVISOR_DB_PATH" not in app_content:
    app_content = app_content.replace(env_default_marker, f"{env_default_str}\n{env_default_marker}")
    print("✓ Added DB provider environment defaults to app.py")

# C. Insert helper function _run_price_advisor if not present
helper_marker = "def format_job_error_message(exc: Exception, request: dict[str, Any] | None) -> str:"
helper_str = """def _run_price_advisor(job_id: str) -> None:
    folder = _job_dir(job_id)
    try:
        _atomic_json(folder / "pa_status.json", {"state": "running", "progress": 0, "message": "Khởi động AI..."})
        pa = PriceAdvisor()
        if not pa.is_ready:
            _atomic_json(folder / "pa_status.json", {"state": "failed", "message": "PriceAdvisor chưa được bật hoặc thiếu API Key"})
            return
            
        result_path = folder / "result.json"
        if not result_path.exists():
            _atomic_json(folder / "pa_status.json", {"state": "failed", "message": "Không tìm thấy kết quả đối chiếu"})
            return
            
        preview = json.loads(result_path.read_text(encoding="utf-8"))
        anomalies = preview.get("anomalies", [])
        
        # Lọc các hạng mục để gửi AI (ưu tiên các mục có cảnh báo giá hoặc thiếu giá)
        items = []
        for a in anomalies:
            flags = str(a.get("flags", [])).lower()
            if "giá" in flags or "thiếu" in flags or a.get("price_delta_pct") is not None:
                items.append({
                    "item_id": a.get("item_id", ""),
                    "item_name": a.get("name", ""),
                    "unit": a.get("unit", ""),
                })
        
        # Nếu không có mục nào có flag giá, lấy 50 mục đầu tiên
        if not items:
            items = [{"item_id": a.get("item_id", ""), "item_name": a.get("name", ""), "unit": a.get("unit", "")} for a in anomalies[:50]]

        def pa_progress(pct: int, msg: str) -> None:
            _atomic_json(folder / "pa_status.json", {"state": "running", "progress": pct, "message": msg})
            
        pa_res = pa.suggest_prices(items, job_id=job_id, progress_callback=pa_progress)
        _atomic_json(folder / "pa_result.json", pa_res.to_dict())
        _atomic_json(folder / "pa_status.json", {"state": "done", "progress": 100, "message": "Hoàn tất gợi ý giá"})
        
    except Exception as exc:
        _atomic_json(folder / "pa_status.json", {"state": "failed", "message": f"Lỗi gọi AI: {exc}"})

"""
if "def _run_price_advisor" not in app_content:
    app_content = app_content.replace(helper_marker, f"{helper_str}\n{helper_marker}")
    print("✓ Added _run_price_advisor helper function to app.py")

# D. Insert the auto-trigger check inside _run_job
job_trigger_marker = """        preview = _result_preview(result, files)
        _atomic_json(folder / "result.json", preview)"""
job_trigger_str = """        pa_config = PriceAdvisorConfig.from_env()
        if pa_config.enabled and pa_config.auto_trigger and mode in {"package", "tender", "bidders"}:
            _JOB_EXECUTOR.submit(_run_price_advisor, job_id)"""
if "auto_trigger" not in app_content:
    app_content = app_content.replace(job_trigger_marker, f"{job_trigger_marker}\n{job_trigger_str}")
    print("✓ Added auto-trigger check inside _run_job in app.py")

# E. Add API Endpoints
endpoint_marker = "@app.post(\"/api/ocr\", status_code=202)"
endpoints_str = """class PriceSuggestRequest(BaseModel):
    job_id: str


class PriceFeedbackRequest(BaseModel):
    job_id: str
    item_id: str
    action: str
    suggested_price: float | None = None
    note: str = ""


@app.post("/api/price-advisor/suggest", status_code=202)
def trigger_price_advisor_api(req: PriceSuggestRequest):
    job_id = req.job_id
    folder = _job_dir(job_id)
    if not folder.exists():
        raise HTTPException(404, "Không tìm thấy tác vụ")
    
    pa_config = PriceAdvisorConfig.from_env()
    if not pa_config.enabled:
        raise HTTPException(400, "PriceAdvisor chưa được bật")
        
    _JOB_EXECUTOR.submit(_run_price_advisor, job_id)
    return {"job_id": job_id, "status": "started"}


@app.get("/api/price-advisor/suggest/{job_id}")
def get_price_suggestions(job_id: str):
    folder = _job_dir(job_id)
    status_path = folder / "pa_status.json"
    result_path = folder / "pa_result.json"
    
    status = {"state": "pending", "progress": 0, "message": "Chưa bắt đầu"}
    if status_path.exists():
        status = json.loads(status_path.read_text(encoding="utf-8"))
        
    result = None
    if result_path.exists():
        result = json.loads(result_path.read_text(encoding="utf-8"))
        
    return {"status": status, "result": result}


@app.post("/api/price-advisor/feedback")
def submit_price_feedback(req: PriceFeedbackRequest):
    pa = PriceAdvisor()
    if not pa.is_ready:
        raise HTTPException(400, "PriceAdvisor chưa được bật")
    pa.record_feedback(req.job_id, req.item_id, req.action, req.suggested_price, req.note)
    return {"success": True}


@app.get("/api/price-advisor/stats")
def get_price_advisor_stats():
    pa = PriceAdvisor()
    try:
        return pa.get_stats()
    except Exception as exc:
        raise HTTPException(500, f"Lỗi kết nối CSDL Giá: {exc}")


class PAPredictRequest(BaseModel):
    item_name: str
    unit: str
    backend: str = "ollama"
    top_k: int = 5
    bidder_price: float | None = None

@app.post("/api/price-advisor/predict")
def pa_predict_api(req: PAPredictRequest):
    pa_config = PriceAdvisorConfig.from_env()
    if not pa_config.enabled:
        raise HTTPException(400, "PriceAdvisor chưa được bật")
        
    # Override settings based on request selection
    if req.backend == "gemini":
        pa_config.llm_provider = "google"
        pa_config.llm_model = "gemini-3.5-flash"
    elif req.backend == "ollama":
        pa_config.llm_provider = "ollama"
        
    try:
        pa = PriceAdvisor(pa_config)
        pa._ensure_initialized()
        
        # 1. Fetch online market prices via DuckDuckGo (Web Search RAG)
        from core.price_advisor.market_price import MarketPriceFetcher
        market_res = MarketPriceFetcher.fetch_market_prices(req.item_name, req.unit)
        
        # Get internal similar items
        query_embedding = pa._embedder.embed_text(req.item_name) if pa._embedder else []
        similar_items = pa._db.search_similar(
            query_embedding,
            top_k=req.top_k,
            query_text=req.item_name
        )
        
        if req.backend == "deterministic":
            # Filter matches by unit (case-insensitive)
            filtered = [item for item in similar_items if item.record.unit.strip().lower() == req.unit.strip().lower()]
            prices = [item.record.unit_price for item in filtered if item.record.unit_price is not None]
            
            if prices:
                min_p = float(min(prices))
                max_p = float(max(prices))
                mean_p = float(sum(prices) / len(prices))
                eps = 0.05
                price_low = min_p * (1 - eps)
                price_high = max_p * (1 + eps)
                confidence = 0.8
                reasoning = f"Tính toán bằng thuật toán thống kê Python (Deterministic) trên {len(prices)} báo giá tham chiếu khớp ĐVT."
                status = "validated"
            else:
                price_low = None
                price_high = None
                confidence = 0.0
                reasoning = "Không có mẫu tham chiếu nào khớp đơn vị tính."
                status = "needs_review"
                
            return {
                "status": status,
                "price_low": price_low,
                "price_high": price_high,
                "confidence": confidence,
                "reasoning": reasoning,
                "similar_items": [item.to_dict() for item in similar_items],
                "market_min_price": market_res["min_price"],
                "market_max_price": market_res["max_price"],
                "market_avg_price": market_res["avg_price"],
                "market_snippets": market_res["snippets"],
            }
        else:
            # Prepare context for LLM, inserting the Web Search RAG data
            context = pa._guard.build_safe_prompt_context(
                item_name=req.item_name,
                item_unit=req.unit,
                similar_items=similar_items,
            )
            # Inject the market data
            context["giá_thị_trường_web"] = market_res
            
            suggestion = pa._llm.query_price(
                context=context,
                item_id="test_item_1",
                item_name=req.item_name,
                unit=req.unit,
            )
            suggestion.similar_items = similar_items
            
            # Ghi log huấn luyện LLM local (chỉ khi gọi LLM không lỗi)
            if suggestion.status != SuggestionStatus.FAILED:
                output_response = {
                    "min_price": suggestion.min_price,
                    "max_price": suggestion.max_price,
                    "suggested_price": suggestion.suggested_price,
                    "confidence": suggestion.confidence,
                    "reasoning": suggestion.reasoning,
                }
                pa._db.log_llm_query(
                    job_id="single_predict",
                    item_id="test_item_1",
                    item_name=req.item_name,
                    unit=req.unit,
                    input_context=context,
                    output_response=output_response,
                    suggested_price=suggestion.suggested_price,
                    confidence=suggestion.confidence,
                    reasoning=suggestion.reasoning,
                    llm_provider=pa._config.llm_provider,
                    llm_model=pa._config.llm_model,
                )
                
            # Validate suggestion against similar items
            suggestion = pa._validator.validate(suggestion, similar_items)
            
            return {
                "status": suggestion.status.value,
                "price_low": suggestion.min_price,
                "price_high": suggestion.max_price,
                "suggested_price": suggestion.suggested_price,
                "confidence": suggestion.confidence,
                "reasoning": suggestion.reasoning,
                "similar_items": [item.to_dict() for item in suggestion.similar_items],
                "market_min_price": market_res["min_price"],
                "market_max_price": market_res["max_price"],
                "market_avg_price": market_res["avg_price"],
                "market_snippets": market_res["snippets"],
            }
    except Exception as exc:
        raise HTTPException(500, f"Lỗi dự đoán giá: {exc}")


from core.price_advisor.test_runner import import_excel_to_price_db, make_test_workspace, run_price_advisor_test
from core.price_advisor.test_api_models import PriceAdvisorExcelTestResult


@app.post("/api/price-advisor/test/import")
async def pa_test_import(
    file: Annotated[UploadFile, File(...)],
    item_name: Annotated[str, Form(...)],
    unit: Annotated[str, Form(...)],
    sheet: Annotated[str | None, Form()] = None,
    no_embed: Annotated[bool, Form()] = False,
):
    pa_config = PriceAdvisorConfig.from_env()
    if not pa_config.enabled:
        raise HTTPException(400, "PriceAdvisor chưa được bật")

    test_job_id, work_dir = make_test_workspace(DEFAULT_CONFIG.runtime_root if hasattr(DEFAULT_CONFIG, 'runtime_root') else (BASE_DIR / 'runtime'))

    job_dir = work_dir
    excel_path = job_dir / (file.filename or "upload.xlsx")

    data = await file.read()
    excel_path.write_bytes(data)

    import_result = import_excel_to_price_db(
        excel_path=excel_path,
        config=pa_config,
        work_dir=job_dir,
        sheet=sheet,
        no_embed=bool(no_embed),
    )

    items = [
        {
            "item_id": "test_item_1",
            "item_name": item_name,
            "unit": unit,
        }
    ]

    try:
        pa_res = run_price_advisor_test(config=pa_config, items=items, job_id=test_job_id)
    except Exception as exc:
        raise HTTPException(500, f"Test runner thất bại: {exc}")

    result_payload = {
        "state": "done",
        "message": "OK",
        "result": pa_res,
        "import": import_result,
    }
    (job_dir / "pa_test_result.json").write_text(
        json.dumps(result_payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    return {"job_id": test_job_id}


@app.get("/api/price-advisor/test/result/{job_id}")
def pa_test_result(job_id: str):
    from core.price_advisor.test_runner import make_test_workspace

    candidate_dirs = []
    runtime_root = DEFAULT_CONFIG.runtime_root if hasattr(DEFAULT_CONFIG, 'runtime_root') else (BASE_DIR / 'runtime')
    if isinstance(runtime_root, Path):
        candidate_dirs.append(runtime_root / "price_advisor_tests" / job_id)
    else:
        candidate_dirs.append(BASE_DIR / "runtime" / "price_advisor_tests" / job_id)

    result_path = None
    for d in candidate_dirs:
        p = d / "pa_test_result.json"
        if p.exists():
            result_path = p
            break

    if result_path is None:
        return PriceAdvisorExcelTestResult(
            job_id=job_id, state="pending", message="Chưa sẵn sàng", result=None
        ).model_dump()

    payload = json.loads(result_path.read_text(encoding="utf-8"))
    return PriceAdvisorExcelTestResult(
        job_id=job_id,
        state=payload.get("state", "done"),
        message=payload.get("message", "OK"),
        result=payload.get("result"),
    ).model_dump()

"""
if "/api/price-advisor" not in app_content:
    app_content = app_content.replace(endpoint_marker, f"{endpoints_str}\n\n{endpoint_marker}")
    print("✓ Added PriceAdvisor API endpoints to app.py")

app_path.write_text(app_content, encoding="utf-8")


# 7. Patch index.html
print("\n=== PATCHING index.html ===")
index_path = dst_root / "web" / "index.html"
index_content = index_path.read_text(encoding="utf-8")

sidebar_button_str = """        <button class="nav-item" onclick="window.location.href='/price_advisor.html'" type="button">
          <span class="nav-icon"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="1" x2="12" y2="23"></line><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path></svg></span><span><b>Dự đoán giá AI</b><small>Tư vấn đơn giá vật tư MEP</small></span>
        </button>"""

if "price_advisor.html" not in index_content:
    index_content = index_content.replace("      </nav>", f"{sidebar_button_str}\n      </nav>")
    index_path.write_text(index_content, encoding="utf-8")
    print("✓ Added 'Dự đoán giá AI' button to index.html sidebar")
else:
    print("✓ index.html sidebar already contains the link")

print("\n=== COPY AND INTEGRATION COMPLETE ===")
