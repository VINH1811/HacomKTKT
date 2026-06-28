from __future__ import annotations

import json
import re
import shutil
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Annotated, Any

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=False)

from security import configure_offline_environment, deny_external_network

configure_offline_environment()

from core.config import EnterpriseConfig
from core.models import CompareThresholds
from core.pipeline import compare_bidder_files, compare_tender_files
from core.reporter import export_consolidated_summary
from core.tender_package import compare_pl1_pl2_with_bidders
from ocr.config import OCRConfig
from ocr.pipeline import create_ocr_package, run_ocr_batch

IMAGES_DIR = BASE_DIR / "images"
WEB_DIR = BASE_DIR / "web"
DEFAULT_CONFIG = EnterpriseConfig.from_env()
JOBS_ROOT = (
    (BASE_DIR / DEFAULT_CONFIG.runtime_root).resolve()
    if not DEFAULT_CONFIG.runtime_root.is_absolute()
    else DEFAULT_CONFIG.runtime_root.resolve()
)
JOBS_ROOT.mkdir(parents=True, exist_ok=True)
_JOB_EXECUTOR = ThreadPoolExecutor(
    max_workers=max(1, DEFAULT_CONFIG.max_concurrent_jobs),
    thread_name_prefix="compare-job",
)
_STATUS_LOCK = threading.Lock()
_SAFE_FILENAME = re.compile(r"[^0-9A-Za-zÀ-ỹ._ -]+")

app = FastAPI(
    title="HSMT Enterprise AI — Professional Comparison & OCR",
    version="8.3.0",
    description="So sánh PL01/PL02/HSMT/HSDT, phát hiện bất thường và OCR PDF/ảnh scan sang Excel trong môi trường nội bộ.",
)


def _job_dir(job_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", job_id):
        raise HTTPException(400, "job_id không hợp lệ")
    return JOBS_ROOT / job_id


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    temp.replace(path)


def _read_status(job_id: str) -> dict[str, Any]:
    path = _job_dir(job_id) / "status.json"
    if not path.exists():
        raise HTTPException(404, "Không tìm thấy tác vụ")
    return json.loads(path.read_text(encoding="utf-8"))


def _update(job_id: str, **changes: Any) -> None:
    with _STATUS_LOCK:
        path = _job_dir(job_id) / "status.json"
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        data.update(changes)
        data["updated_at"] = time.time()
        _atomic_json(path, data)


def _sanitize(name: str, fallback: str) -> str:
    clean = _SAFE_FILENAME.sub("_", Path(name or fallback).name).strip(" .")
    return clean[:180] or fallback


async def _save_upload(
    upload: UploadFile,
    target: Path,
    limit_bytes: int,
    allowed_suffixes: set[str] | None = None,
) -> None:
    allowed = {suffix.lower() for suffix in (allowed_suffixes or {".xlsx"})}
    suffix = target.suffix.lower()
    if suffix not in allowed:
        accepted = ", ".join(sorted(allowed))
        raise HTTPException(400, f"Định dạng không hỗ trợ. Chỉ nhận: {accepted}")
    size = 0
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("wb") as stream:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > limit_bytes:
                    raise HTTPException(413, f"File vượt giới hạn {limit_bytes // (1024 * 1024)} MB")
                stream.write(chunk)
        if size == 0:
            raise HTTPException(400, "File tải lên rỗng")
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()


def _build_config(payload: dict[str, Any]) -> EnterpriseConfig:
    cfg = EnterpriseConfig.from_env()
    cfg.thresholds = CompareThresholds(
        price_warn_pct=float(payload.get("price_warn_pct", 0.10)),
        price_critical_pct=float(payload.get("price_critical_pct", 0.25)),
        price_warn_abs=float(payload.get("price_warn_abs", 100_000)),
        price_critical_abs=float(payload.get("price_critical_abs", 1_000_000)),
        quantity_warn_pct=float(payload.get("quantity_warn_pct", 0.05)),
        quantity_critical_pct=float(payload.get("quantity_critical_pct", 0.15)),
        name_review_score=float(payload.get("name_review_score", 0.78)),
        name_reject_score=float(payload.get("name_reject_score", 0.58)),
        material_review_score=float(payload.get("material_review_score", 0.72)),
        material_reject_score=float(payload.get("material_reject_score", 0.45)),
        brand_review_score=float(payload.get("brand_review_score", 0.80)),
        brand_reject_score=float(payload.get("brand_reject_score", 0.45)),
        origin_review_score=float(payload.get("origin_review_score", 0.85)),
        origin_reject_score=float(payload.get("origin_reject_score", 0.50)),
    )
    return cfg


def _result_preview(result, files: dict[str, Any] | None = None) -> dict[str, Any]:
    anomalies = []
    for row in result.rows:
        if row.severity.value == "OK":
            continue
        item = row.candidate or row.reference
        anomalies.append({
            "severity": row.severity.value,
            "score": round(row.anomaly_score, 1),
            "bidder": row.bidder,
            "sheet": item.sheet if item else "",
            "stt": item.stt if item else "",
            "name": item.item_name if item else "",
            "price_delta_pct": row.price_delta_pct,
            "quantity_delta_pct": row.quantity_delta_pct,
            "flags": row.flags[:8],
        })
        if len(anomalies) >= 250:
            break
    summary = result.summary
    return {
        "kind": "comparison",
        "summary": {
            "reference_name": summary.reference_name,
            "bidder_count": summary.bidder_count,
            "total_reference_items": summary.total_reference_items,
            "total_rows": summary.total_rows,
            "exact_matches": summary.exact_matches,
            "fuzzy_matches": summary.fuzzy_matches,
            "missing_items": summary.missing_items,
            "extra_items": summary.extra_items,
            "review_rows": summary.review_rows,
            "warning_rows": summary.warning_rows,
            "critical_rows": summary.critical_rows,
            "total_reference_amount": summary.total_reference_amount,
            "bidder_totals": summary.bidder_totals,
            "peer_price_comparison_enabled": bool(result.audit.get("peer_price_comparison_enabled", False)),
            "peer_comparison_scope": str(result.audit.get("peer_comparison_scope", "")),
        },
        "warnings": result.warnings[:300],
        "audit": result.audit,
        "files": files or {},
        "anomalies": anomalies,
    }



def format_job_error_message(exc: Exception, request: dict[str, Any] | None) -> str:
    exc_str = str(exc)
    exc_type = type(exc).__name__
    
    file_match = re.search(r"Không đọc được file '([^']+)'", exc_str)
    if file_match:
        target_filename = file_match.group(1)
        original_filename = target_filename
        
        if request:
            if target_filename == request.get("pl1_file"):
                original_filename = request.get("pl1_original") or "Phụ lục 01"
            elif target_filename == request.get("pl2_file"):
                original_filename = request.get("pl2_original") or "Phụ lục 02"
            elif target_filename == request.get("hsmt_file"):
                original_filename = request.get("hsmt_original") or "HSMT"
            else:
                for entry in request.get("bidders", []):
                    if entry.get("file") == target_filename:
                        original_filename = entry.get("original_name") or entry.get("name") or target_filename
                        break
        
        if original_filename == target_filename:
            original_filename = re.sub(r'^\d{3}_', '', original_filename)
            
        underlying_type = ""
        underlying_message = ""
        underlying_match = re.search(r"Không đọc được file '[^']+' \([^)]+\):\s*([^:]+):\s*(.*)", exc_str)
        if underlying_match:
            underlying_type = underlying_match.group(1).strip()
            underlying_message = underlying_match.group(2).strip()
        else:
            cause = exc.__cause__ or exc.__context__
            if cause:
                underlying_type = type(cause).__name__
                underlying_message = str(cause)
                
        if not underlying_type:
            underlying_type = exc_type
            underlying_message = exc_str
            
        if "xlsx" in underlying_message.lower() and ("valueerror" in underlying_type.lower() or "invalidfileexception" in underlying_type.lower()):
            return f"File '{original_filename}' không đúng định dạng Excel. Hệ thống nhận file .xlsx. Hãy Save As file .xls/.xlsb thành .xlsx trước khi chạy."
            
        if "encrypted" in underlying_message.lower() or "password" in underlying_message.lower() or "encrypted" in underlying_type.lower() or "password" in underlying_type.lower():
            return f"File '{original_filename}' bị khóa hoặc bảo vệ bằng mật khẩu. Vui lòng gỡ bỏ mật khẩu trước khi chạy."
            
        if "badzipfile" in underlying_type.lower() or "zipfile.badzipfile" in underlying_type.lower() or "not a zip" in underlying_message.lower():
            return f"File '{original_filename}' không phải là file Excel."
            
        if underlying_type in {"AttributeError", "TypeError", "NameError", "KeyError", "IndexError", "ZeroDivisionError", "UnboundLocalError"}:
            return "lỗi file"
            
        return f"File '{original_filename}' không đúng định dạng Excel."

    if exc_type in {"AttributeError", "TypeError", "NameError", "KeyError", "IndexError", "ZeroDivisionError", "UnboundLocalError"}:
        return "lỗi file"
        
    return "lỗi file"


def _run_job(job_id: str, mode: str, request: dict[str, Any]) -> None:
    folder = _job_dir(job_id)
    started = time.perf_counter()
    try:
        _update(job_id, state="running", progress=8, message="Đang đọc song song các workbook")
        cfg = _build_config(request)
        with deny_external_network(cfg.strict_privacy and not cfg.allow_network):
            if mode == "ocr":
                ocr_cfg = OCRConfig.from_env()
                ocr_cfg.accuracy_mode = str(request.get("accuracy_mode", ocr_cfg.accuracy_mode))
                ocr_cfg.document_profile = str(request.get("document_profile", ocr_cfg.document_profile))
                ocr_cfg.save_review_images = bool(request.get("save_review_images", True))
                input_paths = [folder / entry["file"] for entry in request["files"]]

                def ocr_progress(progress: int, message: str) -> None:
                    _update(job_id, state="running", progress=max(8, min(96, progress)), message=message)

                documents = run_ocr_batch(
                    input_paths,
                    output_dir=folder,
                    config=ocr_cfg,
                    progress_callback=ocr_progress,
                )
                output_files: dict[str, str] = {}
                display_names: list[str] = []
                seen_names: dict[str, int] = {}
                for document, entry in zip(documents, request["files"]):
                    original = str(entry.get("original_name") or document.source_path.name)
                    seen_names[original] = seen_names.get(original, 0) + 1
                    count = seen_names[original]
                    if count > 1:
                        original_path = Path(original)
                        display_name = f"{original_path.stem} ({count}){original_path.suffix}"
                    else:
                        display_name = original
                    display_names.append(display_name)
                    output_files[display_name] = f"{document.source_path.stem}_OCR.xlsx"
                package_path = create_ocr_package(documents, folder)
                preview = {
                    "kind": "ocr",
                    "summary": {
                        "file_count": len(documents),
                        "pages": sum(document.summary.get("pages", 0) for document in documents),
                        "tables": sum(document.summary.get("tables", 0) for document in documents),
                        "rows": sum(document.summary.get("rows", 0) for document in documents),
                        "review_cells": sum(document.summary.get("review_cells", 0) for document in documents),
                        "review_rows": sum(document.summary.get("review_rows", 0) for document in documents),
                        "average_confidence": (
                            sum(float(document.summary.get("average_confidence", 0.0)) for document in documents)
                            / max(len(documents), 1)
                        ),
                    },
                    "documents": [
                        {
                            "source": display_name,
                            "output": output_files[display_name],
                            "summary": document.summary,
                            "warnings": document.warnings[:30],
                        }
                        for document, display_name in zip(documents, display_names)
                    ],
                    "warnings": [
                        f"{display_name}: {warning}"
                        for document, display_name in zip(documents, display_names)
                        for warning in document.warnings[:20]
                    ][:200],
                    "files": {"ocr_files": output_files, "package": package_path.name},
                    "anomalies": [],
                }
                _atomic_json(folder / "result.json", preview)
                first_output = next(iter(output_files.values()), "")
                elapsed = time.perf_counter() - started
                _update(
                    job_id,
                    state="done",
                    progress=100,
                    message=f"Hoàn tất OCR trong {elapsed:.1f} giây",
                    report=first_output,
                    package=package_path.name,
                    ocr_files=output_files,
                    elapsed_seconds=round(elapsed, 3),
                )
                return
            elif mode == "package":
                pairs = [(entry["name"], folder / entry["file"]) for entry in request["bidders"]]
                _update(job_id, progress=20, message="Đang đọc PL01/PL02 và hồ sơ nhà thầu ")
                outputs = compare_pl1_pl2_with_bidders(
                    folder / request["pl1_file"] if request.get("pl1_file") else None,
                    folder / request["pl2_file"] if request.get("pl2_file") else None,
                    pairs,
                    output_dir=folder,
                    config=cfg,
                )
                result = outputs.result
                report = outputs.report_path
                files = {
                    "package": outputs.package_zip.name,
                    "annotated_files": {name: path.name for name, path in outputs.annotated_files.items()},
                }
                extra_status = {
                    "package": outputs.package_zip.name,
                    "annotated_files": files["annotated_files"],
                }
            elif mode == "bidders":
                pairs = [(entry["name"], folder / entry["file"]) for entry in request["bidders"]]
                report = folder / "Bao_cao_so_sanh_ngang_cac_nha_thau.xlsx"
                _update(job_id, progress=25, message="Đang tạo danh mục đồng thuận ngang hàng")
                result = compare_bidder_files(pairs, output_path=report, config=cfg)
                files = {}
                extra_status = {}
            elif mode == "tender":
                pairs = [(entry["name"], folder / entry["file"]) for entry in request["bidders"]]
                report = folder / "Bao_cao_so_sanh_HSMT_HSDT.xlsx"
                _update(job_id, progress=25, message="Đang đối chiếu HSMT với các HSDT")
                result = compare_tender_files(
                    folder / request["hsmt_file"],
                    pairs,
                    output_path=report,
                    config=cfg,
                )
                files = {}
                extra_status = {}
            else:
                raise ValueError(f"Chế độ không hỗ trợ: {mode}")

        _update(job_id, progress=92, message="Đang hoàn thiện báo cáo và file đánh dấu")

        # File tổng hợp riêng theo đúng format bảng chào giá tổng hợp: các nhà
        # thầu xếp cạnh nhau, ô giá lệch nhiều được đánh dấu trực tiếp. Không có
        # cột phân tích (Mức độ, Điểm bất thường).
        if mode in {"package", "bidders", "tender"}:
            summary_path = folder / "Bang_tong_hop_chao_gia_da_danh_dau.xlsx"
            export_consolidated_summary(result, summary_path)
            files = {**files, "summary_file": summary_path.name}
            extra_status = {**extra_status, "summary_file": summary_path.name}
            package_name = str(extra_status.get("package", ""))
            if package_name and (folder / package_name).exists():
                with zipfile.ZipFile(folder / package_name, "a", compression=zipfile.ZIP_DEFLATED) as archive:
                    archive.write(summary_path, summary_path.name)

        preview = _result_preview(result, files)
        _atomic_json(folder / "result.json", preview)
        elapsed = time.perf_counter() - started
        _update(
            job_id,
            state="done",
            progress=100,
            message=f"Hoàn tất trong {elapsed:.1f} giây",
            report=report.name,
            elapsed_seconds=round(elapsed, 3),
            **extra_status,
        )
    except Exception as exc:
        friendly_message = format_job_error_message(exc, request)
        _update(
            job_id,
            state="failed",
            progress=100,
            message=friendly_message,
            error_type=type(exc).__name__,
        )


def _cleanup_expired() -> None:
    cutoff = time.time() - DEFAULT_CONFIG.job_retention_hours * 3600
    for folder in JOBS_ROOT.iterdir():
        if not folder.is_dir():
            continue
        try:
            if folder.stat().st_mtime < cutoff:
                shutil.rmtree(folder, ignore_errors=True)
        except OSError:
            continue


def _new_job(mode: str) -> tuple[str, Path]:
    job_id = uuid.uuid4().hex
    folder = JOBS_ROOT / job_id
    folder.mkdir(parents=True, exist_ok=False)
    now = time.time()
    _atomic_json(folder / "status.json", {
        "job_id": job_id,
        "mode": mode,
        "state": "queued",
        "progress": 0,
        "message": "Đã xếp hàng xử lý",
        "created_at": now,
        "updated_at": now,
    })
    return job_id, folder


def _validate_bidder_uploads(files: list[UploadFile], bidder_names: list[str], minimum: int) -> None:
    if len(files) < minimum or len(files) != len(bidder_names):
        raise HTTPException(400, f"Cần ít nhất {minimum} file và tên nhà thầu tương ứng")


@app.get("/api/health")
def health() -> dict[str, Any]:
    ocr_cfg = OCRConfig.from_env()
    return {
        "status": "ok",
        "version": "8.3.0",
        "privacy": "local-only" if DEFAULT_CONFIG.strict_privacy else "local",
        "deployment": "standalone",
        "package_mode": True,
        "ocr_mode": True,
        "excel_engine": DEFAULT_CONFIG.excel_read_engine,
        "job_workers": DEFAULT_CONFIG.max_concurrent_jobs,
        "excel_read_workers": DEFAULT_CONFIG.excel_read_workers,
        "excel_write_workers": DEFAULT_CONFIG.excel_write_workers,
        "ocr_device": ocr_cfg.device,
        "ocr_accuracy": ocr_cfg.accuracy_mode,
        "ocr_orientation_probe": ocr_cfg.orientation_semantic_probe,
    }


@app.post("/api/ocr", status_code=202)
async def ocr_api(
    files: Annotated[list[UploadFile], File(...)],
    accuracy_mode: Annotated[str, Form()] = "balanced",
    document_profile: Annotated[str, Form()] = "dense_boq",
    save_review_images: Annotated[bool, Form()] = True,
):
    _cleanup_expired()
    if not files:
        raise HTTPException(400, "Chưa chọn PDF hoặc ảnh scan")
    if accuracy_mode not in {"fast", "balanced", "high", "ultra"}:
        raise HTTPException(400, "Mức độ OCR không hợp lệ")
    if document_profile not in {"dense_boq", "generic_table", "document"}:
        raise HTTPException(400, "Loại tài liệu không hợp lệ")

    job_id, folder = _new_job("ocr")
    limit = DEFAULT_CONFIG.max_upload_mb * 1024 * 1024
    allowed = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"}
    entries: list[dict[str, str]] = []
    try:
        for index, upload in enumerate(files, start=1):
            original = _sanitize(upload.filename or "", f"scan_{index}.pdf")
            suffix = Path(original).suffix.lower() or ".pdf"
            filename = f"{index:03d}_{Path(original).stem}{suffix}"
            target = folder / filename
            await _save_upload(upload, target, limit, allowed_suffixes=allowed)
            entries.append({"file": target.name, "original_name": original})
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise

    request = {
        "files": entries,
        "accuracy_mode": accuracy_mode,
        "document_profile": document_profile,
        "save_review_images": save_review_images,
    }
    _atomic_json(folder / "request.json", request)
    _JOB_EXECUTOR.submit(_run_job, job_id, "ocr", request)
    return {"job_id": job_id, "status_url": f"/api/jobs/{job_id}"}


@app.post("/api/compare-package", status_code=202)
async def compare_package_api(
    files: Annotated[list[UploadFile], File(...)],
    bidder_names: Annotated[list[str], Form(...)],
    pl1: Annotated[UploadFile | None, File()] = None,
    pl2: Annotated[UploadFile | None, File()] = None,
    price_warn_pct: Annotated[float, Form()] = 0.10,
    price_critical_pct: Annotated[float, Form()] = 0.25,
    quantity_warn_pct: Annotated[float, Form()] = 0.05,
    quantity_critical_pct: Annotated[float, Form()] = 0.15,
):
    _cleanup_expired()
    _validate_bidder_uploads(files, bidder_names, 1)
    if pl1 is None and pl2 is None:
        raise HTTPException(400, "Cần tải ít nhất Phụ lục 01 hoặc Phụ lục 02")
    job_id, folder = _new_job("package")
    limit = DEFAULT_CONFIG.max_upload_mb * 1024 * 1024
    try:
        pl1_target = None
        pl2_target = None
        if pl1 is not None:
            pl1_target = folder / "000_PHU_LUC_01.xlsx"
            await _save_upload(pl1, pl1_target, limit)
        if pl2 is not None:
            pl2_target = folder / "001_PHU_LUC_02.xlsx"
            await _save_upload(pl2, pl2_target, limit)
        entries = []
        for index, (upload, name) in enumerate(zip(files, bidder_names), start=2):
            original = _sanitize(upload.filename or "", f"bidder_{index}.xlsx")
            target = folder / f"{index:03d}_{original}"
            await _save_upload(upload, target, limit)
            entries.append({
                "name": name.strip() or Path(original).stem,
                "file": target.name,
                "original_name": upload.filename or original
            })
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise

    request = {
        "pl1_file": pl1_target.name if pl1_target else "",
        "pl1_original": pl1.filename if pl1 else "",
        "pl2_file": pl2_target.name if pl2_target else "",
        "pl2_original": pl2.filename if pl2 else "",
        "bidders": entries,
        "price_warn_pct": price_warn_pct,
        "price_critical_pct": price_critical_pct,
        "quantity_warn_pct": quantity_warn_pct,
        "quantity_critical_pct": quantity_critical_pct,
    }
    _atomic_json(folder / "request.json", request)
    _JOB_EXECUTOR.submit(_run_job, job_id, "package", request)
    return {"job_id": job_id, "status_url": f"/api/jobs/{job_id}"}


@app.post("/api/compare-bidders", status_code=202)
async def compare_bidders_api(
    files: Annotated[list[UploadFile], File(...)],
    bidder_names: Annotated[list[str], Form(...)],
    price_warn_pct: Annotated[float, Form()] = 0.10,
    price_critical_pct: Annotated[float, Form()] = 0.25,
    quantity_warn_pct: Annotated[float, Form()] = 0.05,
    quantity_critical_pct: Annotated[float, Form()] = 0.15,
):
    _cleanup_expired()
    _validate_bidder_uploads(files, bidder_names, 2)
    job_id, folder = _new_job("bidders")
    limit = DEFAULT_CONFIG.max_upload_mb * 1024 * 1024
    entries = []
    try:
        for index, (upload, name) in enumerate(zip(files, bidder_names)):
            original = _sanitize(upload.filename or "", f"bidder_{index}.xlsx")
            target = folder / f"{index:03d}_{original}"
            await _save_upload(upload, target, limit)
            entries.append({
                "name": name.strip() or Path(original).stem,
                "file": target.name,
                "original_name": upload.filename or original
            })
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    request = {
        "bidders": entries,
        "price_warn_pct": price_warn_pct,
        "price_critical_pct": price_critical_pct,
        "quantity_warn_pct": quantity_warn_pct,
        "quantity_critical_pct": quantity_critical_pct,
    }
    _atomic_json(folder / "request.json", request)
    _JOB_EXECUTOR.submit(_run_job, job_id, "bidders", request)
    return {"job_id": job_id, "status_url": f"/api/jobs/{job_id}"}


@app.post("/api/compare-tender", status_code=202)
async def compare_tender_api(
    hsmt: Annotated[UploadFile, File(...)],
    files: Annotated[list[UploadFile], File(...)],
    bidder_names: Annotated[list[str], Form(...)],
    price_warn_pct: Annotated[float, Form()] = 0.10,
    price_critical_pct: Annotated[float, Form()] = 0.25,
    quantity_warn_pct: Annotated[float, Form()] = 0.05,
    quantity_critical_pct: Annotated[float, Form()] = 0.15,
):
    _cleanup_expired()
    _validate_bidder_uploads(files, bidder_names, 1)
    job_id, folder = _new_job("tender")
    limit = DEFAULT_CONFIG.max_upload_mb * 1024 * 1024
    try:
        hsmt_target = folder / "000_HSMT.xlsx"
        await _save_upload(hsmt, hsmt_target, limit)
        entries = []
        for index, (upload, name) in enumerate(zip(files, bidder_names), start=1):
            original = _sanitize(upload.filename or "", f"bidder_{index}.xlsx")
            target = folder / f"{index:03d}_{original}"
            await _save_upload(upload, target, limit)
            entries.append({
                "name": name.strip() or Path(original).stem,
                "file": target.name,
                "original_name": upload.filename or original
            })
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    request = {
        "hsmt_file": hsmt_target.name,
        "hsmt_original": hsmt.filename,
        "bidders": entries,
        "price_warn_pct": price_warn_pct,
        "price_critical_pct": price_critical_pct,
        "quantity_warn_pct": quantity_warn_pct,
        "quantity_critical_pct": quantity_critical_pct,
    }
    _atomic_json(folder / "request.json", request)
    _JOB_EXECUTOR.submit(_run_job, job_id, "tender", request)
    return {"job_id": job_id, "status_url": f"/api/jobs/{job_id}"}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    return _read_status(job_id)


@app.get("/api/jobs/{job_id}/result")
def job_result(job_id: str):
    folder = _job_dir(job_id)
    status = _read_status(job_id)
    if status.get("state") != "done":
        raise HTTPException(409, "Tác vụ chưa hoàn tất")
    path = folder / "result.json"
    if not path.exists():
        raise HTTPException(404, "Không có bản xem trước")
    return JSONResponse(json.loads(path.read_text(encoding="utf-8")))


@app.get("/api/jobs/{job_id}/download")
def job_download(job_id: str):
    folder = _job_dir(job_id)
    status = _read_status(job_id)
    if status.get("state") != "done":
        raise HTTPException(409, "Tác vụ chưa hoàn tất")
    report = folder / str(status.get("report", "Bao_cao_so_sanh.xlsx"))
    if not report.exists():
        raise HTTPException(404, "Không tìm thấy báo cáo")
    return FileResponse(
        report,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=report.name,
    )


@app.get("/api/jobs/{job_id}/download-package")
def job_download_package(job_id: str):
    folder = _job_dir(job_id)
    status = _read_status(job_id)
    if status.get("state") != "done":
        raise HTTPException(409, "Tác vụ chưa hoàn tất")
    filename = Path(str(status.get("package", ""))).name
    path = folder / filename
    if not filename or not path.exists():
        raise HTTPException(404, "Tác vụ này không có gói ZIP")
    download_name = "Ket_qua_OCR_PDF_sang_Excel.zip" if status.get("mode") == "ocr" else "Ket_qua_so_sanh_va_file_da_danh_dau.zip"
    return FileResponse(path, media_type="application/zip", filename=download_name)


@app.get("/api/jobs/{job_id}/download-file/{filename}")
def job_download_file(job_id: str, filename: str):
    folder = _job_dir(job_id)
    status = _read_status(job_id)
    if status.get("state") != "done":
        raise HTTPException(409, "Tác vụ chưa hoàn tất")
    safe = Path(filename).name
    allowed = {str(status.get("report", "")), str(status.get("package", "")), str(status.get("summary_file", ""))}
    allowed.update((status.get("annotated_files") or {}).values())
    allowed.update((status.get("ocr_files") or {}).values())
    if safe not in allowed:
        raise HTTPException(403, "File không thuộc kết quả tác vụ")
    path = folder / safe
    if not path.exists():
        raise HTTPException(404, "Không tìm thấy file")
    media = "application/zip" if path.suffix.lower() == ".zip" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return FileResponse(path, media_type=media, filename=safe)


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str):
    folder = _job_dir(job_id)
    if not folder.exists():
        raise HTTPException(404, "Không tìm thấy tác vụ")
    shutil.rmtree(folder, ignore_errors=True)
    return {"deleted": True}


# -----------------------------------------------------------------------------
# Static assets
# -----------------------------------------------------------------------------
# Route order matters in Starlette/FastAPI. The dedicated image directory must
# be mounted before the catch-all web mount at "/"; otherwise requests such as
# /images/Logodung.png would be looked up inside the web directory.
if not WEB_DIR.is_dir():
    raise RuntimeError(f"Không tìm thấy thư mục giao diện: {WEB_DIR}")

if not IMAGES_DIR.is_dir():
    raise RuntimeError(f"Không tìm thấy thư mục hình ảnh: {IMAGES_DIR}")

app.mount(
    "/images",
    StaticFiles(directory=str(IMAGES_DIR)),
    name="images",
)

# Luôn đặt mount "/" cuối cùng vì đây là route bắt toàn bộ giao diện web.
app.mount(
    "/",
    StaticFiles(directory=str(WEB_DIR), html=True),
    name="web",
)
