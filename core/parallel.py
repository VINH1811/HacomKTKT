from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from .config import EnterpriseConfig
from .excel_reader import load_workbook_items
from .models import DocumentRole, WorkbookData


@dataclass(frozen=True, slots=True)
class WorkbookLoadSpec:
    key: str
    path: Path
    role: DocumentRole
    bidder: str
    selected_sheets: Optional[list[str]] = None


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

    def load(spec: WorkbookLoadSpec) -> WorkbookData:
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

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="excel-read") as executor:
        future_map = {executor.submit(load, spec): spec for spec in specs}
        for future in as_completed(future_map):
            spec = future_map[future]
            try:
                results[spec.key] = future.result()
            except Exception as exc:
                raise RuntimeError(
                    f"Không đọc được file '{spec.path.name}' ({spec.bidder}): {type(exc).__name__}: {exc}"
                ) from exc
    return results
