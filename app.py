from __future__ import annotations

import json
import logging
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
from pydantic import BaseModel
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=False)

logger = logging.getLogger(__name__)

# Fallback DB settings for PriceAdvisor test endpoints.
# This avoids Postgres connection/auth issues when only Ollama/LLM testing.
import os
os.environ.setdefault("PRICE_ADVISOR_DB_PROVIDER", "sqlite")
os.environ.setdefault("PRICE_ADVISOR_DB_PATH", str(BASE_DIR / "data" / "price_db.sqlite"))

from security import configure_offline_environment, deny_external_network

configure_offline_environment()

from core.config import EnterpriseConfig
from core.dossier_check import (
    DEFAULT_CHECKLIST,
    evaluate_dossier,
    export_dossier_report,
    load_checklist,
)
from core.hsmt_checklist import (
    SUPPORTED_SUFFIXES as HSMT_SUPPORTED_SUFFIXES,
    build_from_file as build_hsmt_checklist,
    to_checklist_items as hsmt_to_checklist_items,
)
from core.excel_io import diagnose_excel_file
from core.bidder_name import guess_bidder_name, strip_shared_tokens
from core.models import CompareThresholds, UserFacingError
from core.pipeline import compare_bidder_files, compare_tender_files
from core.reporter import export_consolidated_summary
from core.rfi_tracker import (
    STATUS_ANSWERED as RFI_ANSWERED,
    STATUS_NOT_FOUND as RFI_NOT_FOUND,
    STATUS_UNANSWERED as RFI_UNANSWERED,
    export_rfi_report,
    track_rfi,
)
from core.tender_package import compare_pl1_pl2_with_bidders
from core.version_compare import (
    PRICE_ISSUE_FIXED as VC_ISSUE_FIXED,
    PRICE_ISSUE_NEW as VC_ISSUE_NEW,
    PRICE_ISSUE_REMAINS as VC_ISSUE_REMAINS,
    STATUS_ADDED as VC_ADDED,
    STATUS_CHANGED as VC_CHANGED,
    STATUS_REMOVED as VC_REMOVED,
    STATUS_UNCHANGED as VC_UNCHANGED,
    compare_quote_versions,
    export_version_report,
)
from core.price_advisor import PriceAdvisor, PriceAdvisorConfig, SuggestionStatus
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


# Logic đoán tên nhà thầu nằm ở core/bidder_name.py để script xử lý dữ liệu
# dùng chung, khỏi phải chép lại rồi gắn cứng tên từng nhà thầu.
_guess_bidder_name = guess_bidder_name
_strip_shared_tokens = strip_shared_tokens


async def _save_upload(
    upload: UploadFile,
    target: Path,
    limit_bytes: int,
    allowed_suffixes: set[str] | None = None,
) -> None:
    allowed = {suffix.lower() for suffix in (allowed_suffixes or {".xlsx"})}
    # Kiểm tra theo ĐUÔI FILE GỐC người dùng tải lên, không theo tên target. Một
    # số ô (Phụ lục 01/02, HSMT) ép tên target thành .xlsx nên nếu chỉ xét target
    # thì .xlsb/.xls/file lạ sẽ lọt qua. Khi không có tên file gốc thì mới dựa vào
    # target để giữ tương thích.
    source_suffix = Path(upload.filename or "").suffix.lower()
    suffix = source_suffix or target.suffix.lower()
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
    )
    # Mặc định ưu tiên bảng tổng hợp nhẹ (nhanh hơn nhiều khi nhiều hồ sơ). Có thể
    # bật lại báo cáo phân tích nhiều sheet bằng "analytical_report": true.
    cfg.generate_analytical_report = bool(payload.get("analytical_report", False))
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



_GENERIC_PROCESSING_ERROR = (
    "Đã xảy ra lỗi khi xử lý file. Vui lòng kiểm tra lại file hoặc thử lại; "
    "nếu vẫn lỗi, hãy liên hệ người quản trị."
)


def restore_original_names(message: str, request: dict[str, Any] | None) -> str:
    """Đổi tên file nội bộ trong thông báo về đúng tên người dùng đã tải lên.

    Khi lưu, mỗi file được thêm tiền tố thứ tự ("000_", "001_") để hai file
    trùng tên không đè nhau. Tiền tố đó lọt vào thông báo lỗi thì người dùng
    tưởng hệ thống đã sửa file của mình.
    """
    if not message:
        return message
    if request:
        for key, value in request.items():
            if not key.endswith("_file") or not isinstance(value, str) or not value:
                continue
            original = request.get(key[: -len("_file")] + "_original")
            if isinstance(original, str) and original and original != value:
                message = message.replace(value, original)
        for entry in request.get("bidders", []) or []:
            stored, original = entry.get("file"), entry.get("original_name")
            if stored and original and stored != original:
                message = message.replace(stored, original)
    # Còn sót tiền tố (gọi trực tiếp, không qua request) thì cắt nốt.
    return re.sub(r"\b\d{3}_(?=[^\s'\"]*\.[A-Za-z0-9]{2,5})", "", message)


def format_job_error_message(
    exc: Exception,
    request: dict[str, Any] | None,
    folder: Path | None = None,
) -> str:
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
            
        # 1. Lỗi lập trình nội bộ: file có thể không sao, không chẩn đoán định dạng.
        if underlying_type in {"AttributeError", "TypeError", "NameError", "KeyError", "IndexError", "ZeroDivisionError", "UnboundLocalError"}:
            return _GENERIC_PROCESSING_ERROR

        # 2. Chẩn đoán chính xác theo CHỮ KÝ FILE (đáng tin hơn chuỗi lỗi): phân
        # biệt file mật khẩu, Excel cũ, ảnh, PDF, file hỏng... mỗi loại một thông báo.
        if folder is not None:
            reason = diagnose_excel_file(Path(folder) / target_filename)
            if reason:
                return f"File '{original_filename}' {reason}"

        # 3. Dự phòng bằng heuristic chuỗi khi không có file để soi chữ ký.
        if "xlsx" in underlying_message.lower() and ("valueerror" in underlying_type.lower() or "invalidfileexception" in underlying_type.lower()):
            return f"File '{original_filename}' không đúng định dạng Excel. Hệ thống nhận file .xlsx. Hãy Save As file .xls/.xlsb thành .xlsx trước khi chạy."

        if "badzipfile" in underlying_type.lower() or "zipfile.badzipfile" in underlying_type.lower() or "not a zip" in underlying_message.lower():
            return f"File '{original_filename}' không phải là file Excel."

        return f"File '{original_filename}' không đúng định dạng Excel."

    return _GENERIC_PROCESSING_ERROR


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
                _update(job_id, progress=20, message="Đang đọc PL01/PL02 và hồ sơ nhà thầu")
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
            elif mode == "version":
                # So sánh HAI PHIÊN BẢN chào giá của CÙNG nhà thầu (V1 -> V2).
                bidder = str(request.get("bidder_name") or "Nhà thầu")
                _update(job_id, progress=25, message="Đang ghép hạng mục giữa hai phiên bản chào giá")
                vc = compare_quote_versions(
                    folder / request["old_file"],
                    folder / request["new_file"],
                    bidder,
                    config=cfg,
                    old_label=str(request.get("old_label") or "Bản cũ (V1)"),
                    new_label=str(request.get("new_label") or "Bản mới (V2)"),
                )
                report = folder / "Bao_cao_so_sanh_phien_ban_chao_gia.xlsx"
                export_version_report(vc, report)
                preview = {
                    "kind": "version",
                    "summary": {
                        "bidder": vc.bidder,
                        "total_old": vc.total_old,
                        "total_new": vc.total_new,
                        "total_delta": vc.total_delta,
                        "total_delta_pct": (vc.total_delta / vc.total_old) if vc.total_old else None,
                        "changed": vc.count(VC_CHANGED),
                        "added": vc.count(VC_ADDED),
                        "removed": vc.count(VC_REMOVED),
                        "unchanged": vc.count(VC_UNCHANGED),
                        "price_issue_new": vc.count_price_issues(VC_ISSUE_NEW),
                        "price_issue_remains": vc.count_price_issues(VC_ISSUE_REMAINS),
                        "price_issue_fixed": vc.count_price_issues(VC_ISSUE_FIXED),
                    },
                    # Lỗi tự mâu thuẫn giá còn phải xử lý — hiện thẳng lên web chứ
                    # không bắt người dùng mở file báo cáo mới thấy.
                    "warnings": [
                        f"[{issue.status}] {issue.current.describe()}"
                        for issue in vc.price_issues
                        if issue.status in (VC_ISSUE_NEW, VC_ISSUE_REMAINS)
                    ][:40],
                    "anomalies": [],
                    "files": {},
                }
                _atomic_json(folder / "result.json", preview)
                elapsed = time.perf_counter() - started
                _update(job_id, state="done", progress=100,
                        message=f"Hoàn tất trong {elapsed:.1f} giây",
                        report=report.name, elapsed_seconds=round(elapsed, 3))
                return
            elif mode == "rfi":
                # Theo dõi vòng làm rõ: ghép yêu cầu của CĐT với phản hồi nhà thầu.
                bidder = str(request.get("bidder_name") or "Nhà thầu")
                _update(job_id, progress=25, message="Đang ghép yêu cầu làm rõ với phản hồi nhà thầu")
                tracked = track_rfi(
                    folder / request["request_file"],
                    folder / request["response_file"],
                    bidder,
                )
                if not tracked.items:
                    raise UserFacingError(
                        "Không tìm thấy yêu cầu làm rõ nào trong file của CĐT — cần file có các cột "
                        "'NỘI DUNG ĐÁNH GIÁ' và 'Ý kiến CĐT' (file Nội dung làm rõ HSCG)."
                    )
                report = folder / "Bao_cao_theo_doi_lam_ro_RFI.xlsx"
                export_rfi_report([tracked], report)
                pending = [
                    {"sheet": it.request.sheet, "stt": it.request.stt,
                     "request": it.request.cdt_request[:300], "status": it.status}
                    for it in tracked.items if it.status != RFI_ANSWERED
                ]
                preview = {
                    "kind": "rfi",
                    "summary": {
                        "bidder": bidder,
                        "total": len(tracked.items),
                        "answered": tracked.count(RFI_ANSWERED),
                        "unanswered": tracked.count(RFI_UNANSWERED),
                        "not_found": tracked.count(RFI_NOT_FOUND),
                    },
                    "pending": pending[:100],
                    "warnings": [],
                    "anomalies": [],
                    "files": {},
                }
                _atomic_json(folder / "result.json", preview)
                elapsed = time.perf_counter() - started
                _update(job_id, state="done", progress=100,
                        message=f"Hoàn tất trong {elapsed:.1f} giây",
                        report=report.name, elapsed_seconds=round(elapsed, 3))
                return
            elif mode == "dossier":
                # Đánh giá tính đầy đủ hồ sơ: mỗi file ZIP là hồ sơ một nhà thầu.
                # Có HSMT thì checklist dựng theo yêu cầu của chính gói thầu đó,
                # không có thì dùng bộ 12 đầu mục mặc định.
                checklist = load_checklist()
                custom = checklist is not DEFAULT_CHECKLIST
                checklist_source = {
                    "origin": (f"Checklist khai báo riêng ({len(checklist)} đầu mục)" if custom
                               else f"Checklist mặc định ({len(checklist)} đầu mục)"),
                    "meta": [("Nguồn", os.getenv("HSMT_DOSSIER_CHECKLIST", "") if custom
                              else "Bộ mặc định của hệ thống")],
                    "evidences": [],
                }
                hsmt = request.get("hsmt")
                if hsmt:
                    _update(job_id, progress=10, message="Đang đọc hồ sơ mời thầu")
                    try:
                        parsed = build_hsmt_checklist(folder / hsmt["file"])
                    except Exception as exc:
                        raise UserFacingError(
                            f"Không đọc được hồ sơ mời thầu '{hsmt['original_name']}': {exc}"
                        ) from exc
                    if not parsed.items:
                        raise UserFacingError(
                            f"Đã đọc '{hsmt['original_name']}' ({parsed.text_length:,} ký tự) "
                            "nhưng không nhận ra đầu mục tài liệu nào. File có thể là bản scan "
                            "chưa OCR, hoặc dùng cách diễn đạt khác thường. Hãy bỏ trống ô HSMT "
                            "để dùng checklist mặc định."
                        )
                    checklist = hsmt_to_checklist_items(parsed.items)
                    checklist_source = {
                        "origin": f"Hồ sơ mời thầu: {hsmt['original_name']}",
                        "meta": [
                            ("File HSMT", hsmt["original_name"]),
                            ("Số ký tự đọc được", f"{parsed.text_length:,}"),
                            ("File đã đọc", ", ".join(parsed.sources[:20]) or "—"),
                            ("File bỏ qua", ", ".join(parsed.skipped[:20]) or "—"),
                            ("Số đầu mục nhận ra", len(parsed.items)),
                        ],
                        "evidences": [(d.doc_type.label, d.hit_count, d.evidence)
                                      for d in parsed.items],
                    }
                results = []
                for index, entry in enumerate(request["bidders"]):
                    _update(job_id, progress=20 + int(60 * index / max(1, len(request["bidders"]))),
                            message=f"Đang quét hồ sơ {entry['name']}")
                    extract_dir = folder / f"dossier_{index:02d}"
                    extract_dir.mkdir(exist_ok=True)
                    try:
                        with zipfile.ZipFile(folder / entry["file"]) as archive:
                            archive.extractall(extract_dir)
                    except zipfile.BadZipFile as exc:
                        raise UserFacingError(
                            f"File '{entry.get('original_name', entry['file'])}' không phải ZIP hợp lệ. "
                            "Hãy nén thư mục hồ sơ của nhà thầu thành .zip rồi tải lên."
                        ) from exc
                    results.append(evaluate_dossier(entry["name"], extract_dir, checklist))
                report = folder / "Bao_cao_checklist_ho_so.xlsx"
                export_dossier_report(results, report, checklist_source)
                preview = {
                    "kind": "dossier",
                    "checklist_origin": checklist_source["origin"],
                    "checklist_labels": [i.label for i in checklist],
                    "summary": {
                        "bidder_count": len(results),
                        "total_files": sum(r.total_files for r in results),
                        "missing_total": sum(len(r.missing_required) for r in results),
                        "unmatched_total": sum(len(r.unmatched_files) for r in results),
                    },
                    "dossiers": [
                        {
                            "bidder": r.bidder,
                            "total_files": r.total_files,
                            "missing": [c.item.label for c in r.missing_required],
                            "unmatched": r.unmatched_files[:20],
                            "unmatched_count": len(r.unmatched_files),
                        }
                        for r in results
                    ],
                    "warnings": [],
                    "anomalies": [],
                    "files": {},
                }
                _atomic_json(folder / "result.json", preview)
                elapsed = time.perf_counter() - started
                _update(job_id, state="done", progress=100,
                        message=f"Hoàn tất trong {elapsed:.1f} giây",
                        report=report.name, elapsed_seconds=round(elapsed, 3))
                return
            else:
                raise ValueError(f"Chế độ không hỗ trợ: {mode}")

        _update(job_id, progress=92, message="Đang hoàn thiện báo cáo và file đánh dấu")

        # Khi bật báo cáo phân tích nặng, vẫn tạo thêm bảng tổng hợp nhẹ làm bản
        # đọc nhanh. Khi tắt (mặc định), chính báo cáo đã là bảng tổng hợp nên
        # không tạo lại.
        if mode in {"package", "bidders", "tender"} and cfg.generate_analytical_report:
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
        pa_config = PriceAdvisorConfig.from_env()
        if pa_config.enabled and pa_config.auto_trigger and mode in {"package", "tender", "bidders"}:
            _JOB_EXECUTOR.submit(_run_price_advisor, job_id)
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
        # Lớp bắt lỗi tổng: MỌI lỗi (kể cả lỗi chưa lường trước) đều được biến
        # thành thông báo thân thiện và job luôn kết thúc ở trạng thái "failed",
        # không bao giờ crash hay để job treo.
        try:
            if isinstance(exc, UserFacingError):
                friendly_message = restore_original_names(str(exc), request)
            else:
                friendly_message = format_job_error_message(exc, request, folder)
        except Exception:
            friendly_message = _GENERIC_PROCESSING_ERROR
        try:
            _update(
                job_id,
                state="failed",
                progress=100,
                message=friendly_message,
                error_type=type(exc).__name__,
            )
        except Exception:
            # Phương án cuối: ghi trạng thái thất bại tối thiểu để không treo job.
            try:
                _atomic_json(_job_dir(job_id) / "status.json", {
                    "job_id": job_id,
                    "state": "failed",
                    "progress": 100,
                    "message": _GENERIC_PROCESSING_ERROR,
                    "updated_at": time.time(),
                })
            except Exception:
                pass


def _run_price_advisor(job_id: str) -> None:
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


class PriceSuggestRequest(BaseModel):
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

def _internal_history(similar_items, unit: str) -> dict[str, Any]:
    """Khoảng giá lịch sử NỘI BỘ, lấy thẳng từ CSDL giá.

    Không phụ thuộc LLM: khi lời gọi LLM hỏng, đây vẫn là thông tin dùng được
    thay vì để trống cả bảng. Chỉ gộp các bản ghi CÙNG đơn vị tính — trộn
    đ/bộ với đ/m thì khoảng giá trở nên vô nghĩa.
    """
    wanted = (unit or "").strip().lower()
    prices = [
        float(item.record.unit_price)
        for item in similar_items
        if item.record.unit_price and (item.record.unit or "").strip().lower() == wanted
    ]
    if not prices:
        return {"history_min_price": None, "history_max_price": None, "history_count": 0}
    return {
        "history_min_price": min(prices),
        "history_max_price": max(prices),
        "history_count": len(prices),
    }


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
        # Frontend hardcode backend="ollama" với nghĩa "dùng LLM nội bộ".
        # Giữ nguyên provider cấu hình trong .env để chạy được cả Ollama lẫn
        # server nội bộ nói giao thức OpenAI (vLLM) — không ép cứng nữa.
        pass

    try:
        pa = PriceAdvisor(pa_config)
        pa._ensure_initialized()
        
        # 1. Fetch online market prices via DuckDuckGo (Web Search RAG)
        from core.price_advisor.market_price import MarketPriceFetcher
        market_res = MarketPriceFetcher.fetch_market_prices(req.item_name, req.unit)
        
        # Get internal similar items. Bộ nhúng vector hỏng (thiếu gói, hết hạn
        # khóa, mạng chập) thì KHÔNG được làm chết cả chức năng: CSDL giá vẫn
        # tra được theo văn bản, kết quả kém hơn nhưng vẫn dùng được.
        query_embedding: list[float] = []
        if pa._embedder:
            try:
                query_embedding = pa._embedder.embed_text(req.item_name)
            except Exception as exc:
                logger.warning("Bộ nhúng vector không dùng được, chuyển sang tra theo văn bản: %s", exc)
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
                "error_message": "",
                "similar_items": [item.to_dict() for item in similar_items],
                **_internal_history(similar_items, req.unit),
                "market_min_price": market_res["min_price"],
                "market_max_price": market_res["max_price"],
                "market_avg_price": market_res["avg_price"],
                "market_snippets": market_res["snippets"],
                "market_status": market_res.get("status", "ok"),
                "market_message": market_res.get("message", ""),
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
                # Lý do thất bại THẬT (LLM không gọi được, trả JSON hỏng...). Thiếu
                # trường này thì giao diện chỉ còn câu chung chung đổ lỗi cho dữ
                # liệu tham chiếu, người dùng không biết đường sửa.
                "error_message": suggestion.error_message or "",
                "similar_items": [item.to_dict() for item in suggestion.similar_items],
                **_internal_history(similar_items, req.unit),
                "market_min_price": market_res["min_price"],
                "market_max_price": market_res["max_price"],
                "market_avg_price": market_res["avg_price"],
                "market_snippets": market_res["snippets"],
                "market_status": market_res.get("status", "ok"),
                "market_message": market_res.get("message", ""),
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


@app.post("/api/compare-versions", status_code=202)
async def compare_versions_api(
    old_file: Annotated[UploadFile, File(...)],
    new_file: Annotated[UploadFile, File(...)],
    bidder_name: Annotated[str, Form()] = "",
):
    """So sánh hai phiên bản chào giá (cũ/mới) của cùng một nhà thầu."""
    _cleanup_expired()
    job_id, folder = _new_job("version")
    limit = DEFAULT_CONFIG.max_upload_mb * 1024 * 1024
    try:
        old_target = folder / ("000_" + _sanitize(old_file.filename or "", "ban_cu.xlsx"))
        new_target = folder / ("001_" + _sanitize(new_file.filename or "", "ban_moi.xlsx"))
        await _save_upload(old_file, old_target, limit)
        await _save_upload(new_file, new_target, limit)
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    request = {
        "old_file": old_target.name,
        "new_file": new_target.name,
        "old_original": old_file.filename or old_target.name,
        "new_original": new_file.filename or new_target.name,
        "old_label": f"Bản cũ ({old_file.filename})" if old_file.filename else "Bản cũ (V1)",
        "new_label": f"Bản mới ({new_file.filename})" if new_file.filename else "Bản mới (V2)",
        "bidder_name": bidder_name.strip() or _guess_bidder_name(old_file.filename or "") or "Nhà thầu",
    }
    _atomic_json(folder / "request.json", request)
    _JOB_EXECUTOR.submit(_run_job, job_id, "version", request)
    return {"job_id": job_id, "status_url": f"/api/jobs/{job_id}"}


@app.post("/api/track-rfi", status_code=202)
async def track_rfi_api(
    request_file: Annotated[UploadFile, File(...)],
    response_file: Annotated[UploadFile, File(...)],
    bidder_name: Annotated[str, Form()] = "",
):
    """Theo dõi làm rõ: file yêu cầu của CĐT + file phản hồi của nhà thầu."""
    _cleanup_expired()
    job_id, folder = _new_job("rfi")
    limit = DEFAULT_CONFIG.max_upload_mb * 1024 * 1024
    try:
        req_target = folder / ("000_" + _sanitize(request_file.filename or "", "yeu_cau.xlsx"))
        resp_target = folder / ("001_" + _sanitize(response_file.filename or "", "phan_hoi.xlsx"))
        await _save_upload(request_file, req_target, limit)
        await _save_upload(response_file, resp_target, limit)
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    request = {
        "request_file": req_target.name,
        "response_file": resp_target.name,
        "request_original": request_file.filename or req_target.name,
        "response_original": response_file.filename or resp_target.name,
        "bidder_name": bidder_name.strip() or _guess_bidder_name(request_file.filename or "") or "Nhà thầu",
    }
    _atomic_json(folder / "request.json", request)
    _JOB_EXECUTOR.submit(_run_job, job_id, "rfi", request)
    return {"job_id": job_id, "status_url": f"/api/jobs/{job_id}"}


@app.post("/api/check-dossier", status_code=202)
async def check_dossier_api(
    files: Annotated[list[UploadFile], File(...)],
    bidder_names: Annotated[list[str], Form(...)],
    hsmt_file: Annotated[UploadFile | None, File()] = None,
):
    """Đánh giá tính đầy đủ hồ sơ: mỗi file ZIP là toàn bộ thư mục hồ sơ một nhà thầu.

    `hsmt_file` (tuỳ chọn): hồ sơ mời thầu (zip/pdf/docx/xlsx). Có file này thì
    checklist được dựng theo đúng yêu cầu của gói thầu đó; không có thì dùng bộ
    12 đầu mục mặc định như trước.
    """
    _cleanup_expired()
    _validate_bidder_uploads(files, bidder_names, 1)
    job_id, folder = _new_job("dossier")
    limit = DEFAULT_CONFIG.max_upload_mb * 1024 * 1024
    entries = []
    hsmt_saved = None
    try:
        if hsmt_file is not None and (hsmt_file.filename or "").strip():
            hsmt_name = _sanitize(hsmt_file.filename or "", "hsmt.pdf")
            hsmt_target = folder / f"hsmt_{hsmt_name}"
            await _save_upload(hsmt_file, hsmt_target, limit,
                               allowed_suffixes=HSMT_SUPPORTED_SUFFIXES)
            hsmt_saved = {"file": hsmt_target.name,
                          "original_name": hsmt_file.filename or hsmt_name}
        for index, (upload, name) in enumerate(zip(files, bidder_names)):
            original = _sanitize(upload.filename or "", f"ho_so_{index}.zip")
            target = folder / f"{index:03d}_{original}"
            await _save_upload(upload, target, limit, allowed_suffixes={".zip"})
            user_name = name.strip()
            entries.append({
                "name": user_name,   # rỗng = để hệ thống tự đặt (bên dưới)
                "auto": _guess_bidder_name(upload.filename or original) or Path(original).stem,
                "file": target.name,
                "original_name": upload.filename or original,
            })
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    # Với các hồ sơ người dùng KHÔNG tự đặt tên: bỏ phần tên dự án chung giữa các
    # file để còn lại đúng tên nhà thầu (tổng quát cho mọi gói thầu).
    cleaned = _strip_shared_tokens([e["auto"] for e in entries])
    for entry, auto_clean in zip(entries, cleaned):
        if not entry["name"]:
            entry["name"] = auto_clean or entry["auto"]
        entry.pop("auto", None)
    request = {"bidders": entries, "hsmt": hsmt_saved}
    _atomic_json(folder / "request.json", request)
    _JOB_EXECUTOR.submit(_run_job, job_id, "dossier", request)
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
