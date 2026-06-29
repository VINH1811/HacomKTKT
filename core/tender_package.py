from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable, Optional

from .annotator import annotate_bidder_workbook
from .comparison import build_bidder_rows, make_result, misplacement_warnings
from .config import EnterpriseConfig
from .excel_io import read_workbook_matrices
from .excel_reader import detect_header, file_sha256, map_columns
from .matcher import match_items
from .models import (
    ComparedItem,
    ComparisonResult,
    DocumentRole,
    FieldDifference,
    ItemRecord,
    MatchKind,
    MatchResult,
    MaterialRequirement,
    Severity,
    UserFacingError,
    WorkbookData,
)
from .parallel import WorkbookLoadSpec, load_workbooks_parallel
from .peer_analysis import enrich_peer_comparison
from .peer_catalogue import build_peer_consensus
from .pl2_reader import PL2Matcher, _find_header, evaluate_pl2_compliance, load_pl2_requirements
from .reporter import export_comparison_report, export_consolidated_summary

_RANK = {Severity.OK: 0, Severity.INFO: 1, Severity.REVIEW: 2, Severity.WARNING: 3, Severity.CRITICAL: 4}
_SAFE = re.compile(r"[^0-9A-Za-zÀ-ỹ._ -]+")


@dataclass(slots=True)
class TenderPackageOutputs:
    result: ComparisonResult
    report_path: Path
    annotated_files: dict[str, Path]
    package_zip: Path


def _worst(a: Severity, b: Severity) -> Severity:
    return a if _RANK[a] >= _RANK[b] else b


def _add_pl2_difference(row: ComparedItem, field: str, message: str, severity: Severity) -> None:
    row.differences.append(FieldDifference(
        field=f"Phụ lục 02 - {field}",
        reference_value=row.pl2_requirement,
        candidate_value=(row.candidate.brand if field == "Thương hiệu" else row.candidate.origin) if row.candidate else "",
        severity=severity,
        message=message,
    ))
    row.flags.append(message)
    row.flags = list(dict.fromkeys(row.flags))
    row.severity = _worst(row.severity, severity)
    row.anomaly_score = min(100.0, row.anomaly_score + (14.0 if severity is Severity.WARNING else 7.0))


def _apply_pl2(
    rows: list[ComparedItem],
    requirements: list[MaterialRequirement],
    *,
    max_workers: int = 1,
) -> dict[str, int]:
    stats = {"matched": 0, "compliant": 0, "review": 0, "missing_info": 0, "unmapped": 0, "skipped_components": 0}
    if not requirements:
        return stats

    matcher = PL2Matcher(requirements)
    anchors: dict[str, ItemRecord] = {}
    for row in rows:
        if row.candidate is None:
            continue
        anchors.setdefault(row.canonical_id, row.reference or row.candidate)

    cache: dict[str, tuple[MaterialRequirement | None, float]] = {}

    def match_one(entry: tuple[str, ItemRecord]) -> tuple[str, tuple[MaterialRequirement | None, float]]:
        canonical_id, item = entry
        return canonical_id, matcher.match(item, minimum_score=0.66)

    workers = min(max(1, max_workers), max(1, len(anchors)))
    if workers == 1 or len(anchors) < 200:
        for entry in anchors.items():
            canonical_id, matched = match_one(entry)
            cache[canonical_id] = matched
    else:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="pl2-match") as executor:
            for canonical_id, matched in executor.map(match_one, anchors.items(), chunksize=64):
                cache[canonical_id] = matched

    for row in rows:
        if row.candidate is None:
            continue
        requirement, score = cache.get(row.canonical_id, (None, 0.0))
        if requirement is None:
            stats["unmapped"] += 1
            continue
        stats["matched"] += 1
        row.pl2_category = requirement.item_name
        row.pl2_requirement = requirement.requirement_text
        row.pl2_match_score = score

        if row.candidate.row_type.value == "component" and not (row.candidate.brand or row.candidate.origin):
            row.pl2_status = "KẾ THỪA DÒNG CHA / KHÔNG KIỂM TRA TRỰC TIẾP"
            stats["skipped_components"] += 1
            continue

        status, issues = evaluate_pl2_compliance(row.candidate, requirement)
        row.pl2_status = status
        if not issues:
            stats["compliant"] += 1
            continue
        if status == "THIẾU THÔNG TIN PL02":
            stats["missing_info"] += 1
        else:
            stats["review"] += 1
        for field, message in issues:
            severity = Severity.WARNING if message.startswith("Thiếu") else Severity.REVIEW
            _add_pl2_difference(row, field, message, severity)
    return stats


def _slug(name: str) -> str:
    value = _SAFE.sub("_", name).strip(" ._")
    return value[:120] or "Nha_thau"


def _requirements_audit(requirements: list[MaterialRequirement]) -> list[dict]:
    return [{
        "sheet": req.source_sheet,
        "row": req.source_row,
        "system": req.system,
        "item_name": req.item_name,
        "requirement": req.requirement_text,
        "brands": list(req.allowed_brands),
        "origins": list(req.allowed_origins),
        "note": req.note,
    } for req in requirements]


def _no_boq_message(label: str) -> str:
    return (
        f"Không đọc được hạng mục nào từ '{label}'. File có thể không chứa bảng khối lượng (BOQ) "
        "— hãy kiểm tra lại đúng file có sheet bảng khối lượng/hạng mục (ví dụ có các cột "
        "Diễn giải/Đơn vị/Khối lượng)."
    )


def _ensure_has_items(workbook: WorkbookData, label: str) -> None:
    if not any(item.is_comparable for item in workbook.items):
        raise UserFacingError(_no_boq_message(label))


def _looks_like_boq(matrices) -> bool:
    """Đúng cấu trúc Phụ lục 01 (KLMT): có cột tên hạng mục + khối lượng/đơn giá."""
    for sheet in matrices.sheets:
        if not sheet.rows:
            continue
        try:
            _start, _end, flat = detect_header(sheet.rows[:90])
        except ValueError:
            continue
        mapping, _technical = map_columns(flat, DocumentRole.HSMT)
        fields = set(mapping.values())
        has_quantity = bool({"reference_quantity", "bid_quantity"} & fields)
        has_price = bool({"unit_price_total", "reference_amount", "bid_amount"} & fields)
        if "item_name" in fields and (has_quantity or has_price):
            return True
    return False


def _looks_like_pl2(matrices) -> bool:
    """Đúng cấu trúc Phụ lục 02: có cột Vật tư + Thương hiệu/Xuất xứ."""
    return any(sheet.rows and _find_header(sheet.rows) is not None for sheet in matrices.sheets)


def detect_appendix_role(path: Path, config: EnterpriseConfig) -> str:
    """Nhận diện một file là 'pl1' (KLMT), 'pl2' (yêu cầu vật tư) hay 'unknown'.

    Dựa vào cấu trúc cột thực tế, không dựa vào ô upload người dùng chọn.
    """
    try:
        matrices = read_workbook_matrices(
            path,
            engine=config.excel_read_engine,
            max_rows=300,
            fallback_openpyxl=config.excel_fallback_openpyxl,
        )
    except Exception:
        return "unknown"
    is_boq = _looks_like_boq(matrices)
    is_pl2 = _looks_like_pl2(matrices)
    if is_pl2 and not is_boq:
        return "pl2"
    if is_boq and not is_pl2:
        return "pl1"
    # Cả hai tín hiệu (hiếm): KLMT có cột thương hiệu/xuất xứ -> ưu tiên KLMT vì
    # có số liệu khối lượng/đơn giá. Không có tín hiệu nào -> không xác định.
    if is_boq and is_pl2:
        return "pl1"
    return "unknown"


def _resolve_appendix_roles(
    pl1: Optional[Path],
    pl2: Optional[Path],
    config: EnterpriseConfig,
) -> tuple[Optional[Path], Optional[Path], list[str]]:
    """Tự sửa khi người dùng đặt nhầm PL01/PL02 vào sai ô upload."""
    warnings: list[str] = []
    role1 = detect_appendix_role(pl1, config) if pl1 else None
    role2 = detect_appendix_role(pl2, config) if pl2 else None

    if pl1 and pl2:
        if role1 == "pl2" and role2 == "pl1":
            warnings.append(
                "⚠️ CÓ THỂ BẠN ĐÃ TRÁO Phụ lục 01 và Phụ lục 02 (đặt nhầm ô tải lên): "
                "file ở ô Phụ lục 01 lại có cấu trúc Phụ lục 02 và ngược lại. "
                "Hệ thống đã TỰ ĐỔI LẠI cho đúng — vui lòng kiểm tra lại kết quả."
            )
            return pl2, pl1, warnings
        return pl1, pl2, warnings

    if pl1 and not pl2 and role1 == "pl2":
        warnings.append(
            "⚠️ File bạn tải ở ô Phụ lục 01 thực chất có cấu trúc Phụ lục 02 (yêu cầu vật tư/"
            "thương hiệu). Hệ thống đã TỰ XỬ LÝ đúng như Phụ lục 02 — kiểm tra lại vị trí tải lên."
        )
        return None, pl1, warnings

    if pl2 and not pl1 and role2 == "pl1":
        warnings.append(
            "⚠️ File bạn tải ở ô Phụ lục 02 thực chất có cấu trúc Phụ lục 01 (bảng khối lượng). "
            "Hệ thống đã TỰ XỬ LÝ đúng như Phụ lục 01 — kiểm tra lại vị trí tải lên."
        )
        return pl2, None, warnings

    return pl1, pl2, warnings


def compare_appendices_with_bidders(
    bidder_files: Iterable[tuple[str, str | Path]],
    output_dir: str | Path,
    *,
    pl1_path: str | Path | None = None,
    pl2_path: str | Path | None = None,
    config: Optional[EnterpriseConfig] = None,
) -> TenderPackageOutputs:
    """Compare one or both official appendices with one or more bidder files.

    Supported modes:
    - One bidder: compare only against the information available in PL01/PL02.
      No horizontal bidder-price comparison is created.
    - Two or more bidders: perform the same appendix checks for every bidder,
      then add horizontal price comparison between bidders.
    - PL01 + PL02: official quantity catalogue + material requirements.
    - PL01 only: official quantity catalogue; PL02 checks are skipped.
    - PL02 only: bidder catalogue + PL02 material checks. Without PL01 there is
      no official quantity/item catalogue for missing/extra-item checks.
    """
    config = config or EnterpriseConfig.from_env()
    pairs = [(name, Path(path)) for name, path in bidder_files]
    if not pairs:
        raise ValueError("Cần ít nhất 1 hồ sơ nhà thầu để đối chiếu phụ lục")
    if not pl1_path and not pl2_path:
        raise ValueError("Cần tải ít nhất một phụ lục: Phụ lục 01 hoặc Phụ lục 02")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    pl1 = Path(pl1_path) if pl1_path else None
    pl2 = Path(pl2_path) if pl2_path else None

    # Tự nhận diện và sửa nếu PL01/PL02 bị đặt nhầm ô upload (dựa vào cấu trúc cột
    # thực tế, không dựa vào ô người dùng chọn).
    pl1, pl2, role_warnings = _resolve_appendix_roles(pl1, pl2, config)

    specs = [
        WorkbookLoadSpec(f"bidder:{index}", path, DocumentRole.HSDT, name)
        for index, (name, path) in enumerate(pairs)
    ]
    if pl1:
        specs.append(WorkbookLoadSpec("pl1", pl1, DocumentRole.HSMT, "PHỤ LỤC 01 - KLMT"))

    # Read PL01 and all bidder workbooks concurrently. PL02 is read in parallel
    # with that group because it has a different schema.
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="package-read") as executor:
        workbook_future = executor.submit(load_workbooks_parallel, specs, config)
        
        def load_pl2():
            try:
                return load_pl2_requirements(pl2, config=config)
            except Exception as exc:
                raise RuntimeError(
                    f"Không đọc được file '{pl2.name}' (PHỤ LỤC 02): {type(exc).__name__}: {exc}"
                ) from exc

        pl2_future = executor.submit(load_pl2) if pl2 else None
        loaded = workbook_future.result()
        requirements, pl2_warnings = pl2_future.result() if pl2_future else ([], [])

    bidders = [loaded[f"bidder:{index}"] for index in range(len(pairs))]

    # A-05: file không có sheet bảng khối lượng nào -> báo lỗi rõ ràng thay vì
    # tạo báo cáo rỗng. PL02-only thì PL02 đã được kiểm tra riêng phía trên.
    for bidder in bidders:
        _ensure_has_items(bidder, bidder.bidder)
    if pl1:
        _ensure_has_items(loaded["pl1"], "Phụ lục 01")

    # Cảnh báo (không tự sửa) nếu nghi đặt nhầm vị trí: hồ sơ dự thầu vào ô Phụ
    # lục 01, hoặc một bảng mời thầu/khối lượng lọt vào danh sách nhà thầu.
    misplace_warnings = misplacement_warnings(loaded["pl1"] if pl1 else None, "Phụ lục 01", bidders)

    bidder_count = len(bidders)
    peer_price_enabled = bidder_count >= 2
    cluster_stats: dict = {}
    if pl1:
        reference = loaded["pl1"]
        rows: list[ComparedItem] = []

        def _match_one(workbook: WorkbookData) -> list[ComparedItem]:
            matches = match_items(reference.items, workbook.items, config)
            return build_bidder_rows(
                reference.items, workbook.items, workbook.bidder, matches, config, reference_is_boq=True,
            )

        # Mỗi nhà thầu được ghép độc lập với PL01 -> chạy song song để rút ngắn
        # thời gian khi có nhiều hồ sơ (rapidfuzz nhả GIL nên thread tăng tốc thật).
        if bidder_count > 1:
            workers = min(max(1, config.excel_read_workers), bidder_count)
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="match") as executor:
                for bidder_rows in executor.map(_match_one, bidders):
                    rows.extend(bidder_rows)
        else:
            for workbook in bidders:
                rows.extend(_match_one(workbook))
        catalogue_mode = "PL01_OFFICIAL"
    else:
        reference, rows, cluster_stats = build_peer_consensus(bidders, config)
        catalogue_mode = (
            "MULTIWAY_PEER_CONSENSUS"
            if peer_price_enabled
            else "SINGLE_BIDDER_CATALOGUE_FOR_PL02"
        )

    pl2_stats = _apply_pl2(rows, requirements, max_workers=config.excel_read_workers)
    if peer_price_enabled:
        # In the appendix workflow, cross-bidder comparison is intentionally
        # limited to price-related fields. Item names, units and quantities are
        # already checked independently against PL01/PL02 for each bidder.
        peer_stats = enrich_peer_comparison(rows, config, price_only=True)
    else:
        peer_stats = {
            "enabled": False,
            "scope": "disabled_single_bidder",
            "groups": len({row.canonical_id for row in rows}),
            "numeric_flags": 0,
            "text_flags": 0,
            "reason": "Chỉ có một hồ sơ nhà thầu; không có đối tượng để so sánh giá ngang hàng.",
        }

    if pl1 and pl2 and peer_price_enabled:
        mode = "PL01_PL02_VS_MULTI_HSDT_PRICE_PEER"
        report_name = "Bao_cao_tong_hop_PL01_PL02_va_cac_nha_thau.xlsx"
    elif pl1 and pl2:
        mode = "PL01_PL02_VS_SINGLE_HSDT"
        report_name = "Bao_cao_doi_chieu_PL01_PL02_voi_01_nha_thau.xlsx"
    elif pl1 and peer_price_enabled:
        mode = "PL01_ONLY_VS_MULTI_HSDT_PRICE_PEER"
        report_name = "Bao_cao_tong_hop_PL01_va_cac_nha_thau.xlsx"
    elif pl1:
        mode = "PL01_ONLY_VS_SINGLE_HSDT"
        report_name = "Bao_cao_doi_chieu_PL01_voi_01_nha_thau.xlsx"
    elif peer_price_enabled:
        mode = "PL02_ONLY_MULTIWAY_HSDT_PRICE_PEER"
        report_name = "Bao_cao_tong_hop_PL02_va_so_sanh_gia_cac_nha_thau.xlsx"
    else:
        mode = "PL02_ONLY_VS_SINGLE_HSDT"
        report_name = "Bao_cao_doi_chieu_PL02_voi_01_nha_thau.xlsx"

    comparison_principle = (
        "Official appendices are references; every bidder is checked independently against appendices; "
        "horizontal comparison is limited to price fields because two or more bidders were provided."
        if peer_price_enabled
        else
        "Official appendices are references; the single bidder is checked only against information available "
        "in PL01/PL02; horizontal bidder-price comparison is disabled."
    )

    audit = {
        "mode": mode,
        "catalogue_mode": catalogue_mode,
        "comparison_principle": comparison_principle,
        "bidder_count": bidder_count,
        "peer_price_comparison_enabled": peer_price_enabled,
        "peer_comparison_scope": "price_only" if peer_price_enabled else "disabled",
        "privacy": "STRICT_LOCAL" if config.strict_privacy else "LOCAL",
        "network_allowed": config.allow_network,
        "embedding_model": config.embedding_model_path or "disabled/not installed",
        "reranker_model": config.reranker_model_path or "disabled/not installed",
        "reference_sha256": file_sha256(pl1) if pl1 else "",
        "pl1_sha256": file_sha256(pl1) if pl1 else "NOT_PROVIDED",
        "pl2_sha256": file_sha256(pl2) if pl2 else "NOT_PROVIDED",
        "bidder_sha256": {bidder.bidder: file_sha256(bidder.path) for bidder in bidders},
        "sheet_mappings": {bidder.bidder: bidder.sheet_info for bidder in bidders},
        "pl1_sheet_mappings": reference.sheet_info if pl1 else [],
        "excel_read_engine": config.excel_read_engine,
        "excel_read_workers": config.excel_read_workers,
        "excel_write_workers": config.excel_write_workers,
        "read_performance": {
            bidder.bidder: {"engine": bidder.read_engine, "seconds": round(bidder.read_seconds, 4), "items": len(bidder.items)}
            for bidder in bidders
        },
        "formula_issue_counts": {bidder.bidder: len(bidder.formula_issues) for bidder in bidders},
        "external_link_counts": {bidder.bidder: bidder.external_link_count for bidder in bidders},
        "pl2_requirement_count": len(requirements),
        "pl2_stats": pl2_stats,
        "peer_stats": peer_stats,
        "peer_cluster_stats": cluster_stats,
        "pl2_requirements": _requirements_audit(requirements),
        "thresholds": {name: getattr(config.thresholds, name) for name in config.thresholds.__dataclass_fields__},
    }
    result = make_result(rows, reference, bidders, audit)
    result.warnings.extend(role_warnings)
    result.warnings.extend(misplace_warnings)
    result.warnings.extend(pl2_warnings)
    if not pl1:
        if peer_price_enabled:
            result.warnings.append(
                "Không có PL01: danh mục hạng mục được tạo bằng ghép đa chiều giữa tất cả nhà thầu; "
                "không thể kiểm tra chính thức hạng mục thiếu/thừa hoặc khối lượng mời thầu theo PL01."
            )
        else:
            result.warnings.append(
                "Không có PL01 và chỉ có 1 nhà thầu: hệ thống chỉ kiểm tra yêu cầu vật tư trong PL02; "
                "không thể xác định hạng mục thiếu/thừa hoặc chênh lệch khối lượng mời thầu."
            )
    if not pl2:
        result.warnings.append("Không có PL02: hệ thống bỏ qua kiểm tra thương hiệu/xuất xứ theo yêu cầu vật tư chính thức.")

    report_path = output_dir / report_name
    if config.generate_analytical_report:
        export_comparison_report(result, report_path)
    else:
        # Bảng tổng hợp side-by-side nhẹ thay cho báo cáo phân tích nặng (nhanh
        # hơn nhiều khi nhiều hồ sơ; vẫn đánh dấu giá lệch + vi phạm PL02).
        export_consolidated_summary(result, report_path)

    annotated: dict[str, Path] = {}
    annotation_jobs = []
    for bidder, (_, source_path) in zip(bidders, pairs):
        bidder_rows = [row for row in rows if row.bidder == bidder.bidder]
        destination = output_dir / f"{_slug(source_path.stem)}__DA_DANH_DAU.xlsx"
        annotation_jobs.append((bidder, source_path, destination, bidder_rows))

    workers = min(max(1, config.excel_write_workers), len(annotation_jobs))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="excel-write") as executor:
        future_map = {
            executor.submit(annotate_bidder_workbook, source, destination, bidder, bidder_rows): (bidder, destination)
            for bidder, source, destination, bidder_rows in annotation_jobs
        }
        for future in as_completed(future_map):
            bidder, destination = future_map[future]
            future.result()
            annotated[bidder.bidder] = destination

    manifest = {
        "mode": mode,
        "principle": audit["comparison_principle"],
        "bidder_count": bidder_count,
        "peer_price_comparison_enabled": peer_price_enabled,
        "peer_comparison_scope": audit["peer_comparison_scope"],
        "appendices": {"pl1": bool(pl1), "pl2": bool(pl2)},
        "report": report_path.name,
        "annotated_files": {name: path.name for name, path in annotated.items()},
        "pl2_stats": pl2_stats,
        "peer_stats": peer_stats,
        "peer_cluster_stats": cluster_stats,
        "warnings": result.warnings,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    package_zip = output_dir / "Ket_qua_so_sanh_va_file_da_danh_dau.zip"
    with zipfile.ZipFile(package_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.write(report_path, report_path.name)
        archive.write(manifest_path, manifest_path.name)
        for path in annotated.values():
            archive.write(path, path.name)

    return TenderPackageOutputs(result, report_path, annotated, package_zip)


def compare_pl1_pl2_with_bidders(
    pl1_path: str | Path | None,
    pl2_path: str | Path | None,
    bidder_files: Iterable[tuple[str, str | Path]],
    output_dir: str | Path,
    config: Optional[EnterpriseConfig] = None,
) -> TenderPackageOutputs:
    """Backward-compatible wrapper; now accepts either appendix as optional."""
    return compare_appendices_with_bidders(
        bidder_files, output_dir, pl1_path=pl1_path, pl2_path=pl2_path, config=config,
    )
