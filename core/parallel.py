from __future__ import annotations

import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Optional

from .config import EnterpriseConfig
from .excel_reader import file_sha256, load_workbook_items
from .models import DocumentRole, WorkbookData


@dataclass(frozen=True, slots=True)
class WorkbookLoadSpec:
    key: str
    path: Path
    role: DocumentRole
    bidder: str
    selected_sheets: Optional[list[str]] = None


# ---------------------------------------------------------------------------
# Cache parse theo SHA-256 nội dung file.
#
# An toàn tuyệt đối về độ chính xác:
# - Khóa cache gồm SHA-256 của file + toàn bộ tham số parse: file đổi 1 byte
#   hay đổi cách đọc là khóa khác, không bao giờ trả nhầm dữ liệu cũ.
# - Cache LUÔN trả bản sao độc lập (items mới, list/dict mới): pipeline của
#   lần chạy sau không thể bị ảnh hưởng bởi trạng thái lần trước.
# - Pipeline hiện không mutate ItemRecord sau khi load (đã kiểm chứng), nhưng
#   bản sao vẫn được tạo để bảo vệ cả các thay đổi trong tương lai.
# ---------------------------------------------------------------------------
_PARSE_CACHE: "OrderedDict[tuple, WorkbookData]" = OrderedDict()
_PARSE_CACHE_LOCK = threading.Lock()


def clear_parse_cache() -> None:
    with _PARSE_CACHE_LOCK:
        _PARSE_CACHE.clear()


def _parse_cache_key(sha: str, spec: WorkbookLoadSpec, config: EnterpriseConfig) -> tuple:
    sheets = tuple(spec.selected_sheets) if spec.selected_sheets is not None else None
    return (
        sha,
        spec.role.value,
        sheets,
        config.max_excel_rows,
        config.excel_read_engine,
        config.excel_fallback_openpyxl,
        config.excel_scan_formulas,
        config.excel_scan_external_links,
    )


def _default_bidder(spec: WorkbookLoadSpec) -> str:
    # Trùng logic đặt tên trong load_workbook_items.
    return spec.bidder or ("HSMT" if spec.role is DocumentRole.HSMT else spec.path.stem)


def _clone_workbook(cached: WorkbookData, spec: WorkbookLoadSpec, *, from_cache: bool) -> WorkbookData:
    """Bản sao độc lập từ cache, cập nhật path/bidder theo lần chạy hiện tại."""
    bidder_name = _default_bidder(spec)
    workbook_name = spec.path.name
    items = [
        replace(
            item,
            bidder=bidder_name,
            workbook=workbook_name,
            technical_specs=dict(item.technical_specs),
            raw=dict(item.raw),
            data_quality_flags=list(item.data_quality_flags),
        )
        for item in cached.items
    ]
    return WorkbookData(
        path=spec.path,
        role=cached.role,
        bidder=bidder_name,
        items=items,
        warnings=list(cached.warnings),
        sheet_info=[dict(info) for info in cached.sheet_info],
        totals=dict(cached.totals),
        read_engine=f"{cached.read_engine}+cache" if from_cache else cached.read_engine,
        read_seconds=0.0 if from_cache else cached.read_seconds,
        formula_issues=[dict(issue) for issue in cached.formula_issues],
        external_link_count=cached.external_link_count,
        content_sha=cached.content_sha,
    )


def _load_with_cache(spec: WorkbookLoadSpec, config: EnterpriseConfig) -> WorkbookData:
    capacity = max(0, int(getattr(config, "parse_cache_size", 0) or 0))
    if capacity <= 0:
        return _load_fresh(spec, config)

    sha = file_sha256(spec.path)
    key = _parse_cache_key(sha, spec, config)
    with _PARSE_CACHE_LOCK:
        cached = _PARSE_CACHE.get(key)
        if cached is not None:
            _PARSE_CACHE.move_to_end(key)
    if cached is not None:
        return _clone_workbook(cached, spec, from_cache=True)

    loaded = _load_fresh(spec, config)
    with _PARSE_CACHE_LOCK:
        _PARSE_CACHE[key] = loaded
        _PARSE_CACHE.move_to_end(key)
        while len(_PARSE_CACHE) > capacity:
            _PARSE_CACHE.popitem(last=False)
    # Trả bản sao cả ở lần nạp đầu: object trong cache không bao giờ được dùng
    # trực tiếp trong pipeline nên không thể bị thay đổi.
    return _clone_workbook(loaded, spec, from_cache=False)


def _load_fresh(spec: WorkbookLoadSpec, config: EnterpriseConfig) -> WorkbookData:
    return load_workbook_items(
        spec.path,
        spec.role,
        bidder=spec.bidder,
        selected_sheets=spec.selected_sheets,
        max_rows=config.max_excel_rows,
        read_engine=config.excel_read_engine,
        fallback_openpyxl=config.excel_fallback_openpyxl,
        scan_formulas=config.excel_scan_formulas,
        scan_external_links=config.excel_scan_external_links,
    )


def load_workbooks_parallel(
    specs: Iterable[WorkbookLoadSpec],
    config: EnterpriseConfig,
) -> dict[str, WorkbookData]:
    """Load independent workbooks concurrently.

    Each task opens its own Calamine/openpyxl workbook. Workbook objects are
    never shared across threads.
    """
    specs = list(specs)
    if not specs:
        return {}
    workers = min(max(1, config.excel_read_workers), len(specs))
    results: dict[str, WorkbookData] = {}

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="excel-read") as executor:
        future_map = {executor.submit(_load_with_cache, spec, config): spec for spec in specs}
        for future in as_completed(future_map):
            spec = future_map[future]
            try:
                results[spec.key] = future.result()
            except Exception as exc:
                raise RuntimeError(
                    f"Không đọc được file '{spec.path.name}' ({spec.bidder}): {type(exc).__name__}: {exc}"
                ) from exc
    return results
