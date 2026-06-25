from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from .anomaly import enrich_consensus_anomalies
from .comparison import build_bidder_rows, make_result
from .config import EnterpriseConfig
from .excel_reader import file_sha256
from .matcher import match_items
from .models import ComparisonResult, DocumentRole, WorkbookData
from .parallel import WorkbookLoadSpec, load_workbooks_parallel
from .peer_analysis import enrich_peer_comparison
from .peer_catalogue import build_peer_consensus
from .reporter import export_comparison_report


def compare_tender_files(
    hsmt_path: str | Path,
    bidder_files: Iterable[tuple[str, str | Path]],
    output_path: str | Path | None = None,
    config: Optional[EnterpriseConfig] = None,
    hsmt_sheets: Optional[list[str]] = None,
    bidder_sheets: Optional[dict[str, list[str]]] = None,
) -> ComparisonResult:
    config = config or EnterpriseConfig.from_env()
    pairs = [(name, Path(path)) for name, path in bidder_files]
    if not pairs:
        raise ValueError("Cần ít nhất 1 HSDT để đối chiếu với HSMT")

    specs = [WorkbookLoadSpec("reference", Path(hsmt_path), DocumentRole.HSMT, "HSMT", hsmt_sheets)]
    specs.extend(
        WorkbookLoadSpec(
            f"bidder:{index}",
            path,
            DocumentRole.HSDT,
            name,
            (bidder_sheets or {}).get(name),
        )
        for index, (name, path) in enumerate(pairs)
    )
    loaded = load_workbooks_parallel(specs, config)
    reference = loaded["reference"]
    bidders = [loaded[f"bidder:{index}"] for index in range(len(pairs))]

    rows = []
    for workbook in bidders:
        matches = match_items(reference.items, workbook.items, config)
        rows.extend(build_bidder_rows(reference.items, workbook.items, workbook.bidder, matches, config))

    enrich_peer_comparison(rows, config)
    enrich_consensus_anomalies(rows, config)
    result = make_result(rows, reference, bidders, _audit(reference, bidders, config, "HSMT_vs_HSDT"))
    if output_path:
        export_comparison_report(result, output_path)
    return result


def compare_bidder_files(
    bidder_files: Iterable[tuple[str, str | Path]],
    output_path: str | Path | None = None,
    config: Optional[EnterpriseConfig] = None,
) -> ComparisonResult:
    """Compare two or more bidder files without selecting a baseline bidder."""
    config = config or EnterpriseConfig.from_env()
    pairs = [(name, Path(path)) for name, path in bidder_files]
    if len(pairs) < 2:
        raise ValueError("Cần ít nhất 2 HSDT để so sánh giữa các nhà thầu")

    specs = [
        WorkbookLoadSpec(f"bidder:{index}", path, DocumentRole.HSDT, name)
        for index, (name, path) in enumerate(pairs)
    ]
    loaded = load_workbooks_parallel(specs, config)
    bidders = [loaded[f"bidder:{index}"] for index in range(len(pairs))]
    reference, rows, cluster_stats = build_peer_consensus(bidders, config)
    peer_stats = enrich_peer_comparison(rows, config)
    enrich_consensus_anomalies(rows, config)

    audit = _audit(reference, bidders, config, "HSDT_MULTIWAY_PEER")
    audit.update({
        "catalogue_mode": "MULTIWAY_PEER_CONSENSUS",
        "comparison_principle": "all bidders are horizontal peers; no bidder baseline",
        "peer_cluster_stats": cluster_stats,
        "peer_stats": peer_stats,
    })
    result = make_result(rows, reference, bidders, audit)
    if output_path:
        export_comparison_report(result, output_path)
    return result


def _audit(reference: WorkbookData, bidders: list[WorkbookData], config: EnterpriseConfig, mode: str) -> dict:
    return {
        "mode": mode,
        "privacy": "STRICT_LOCAL" if config.strict_privacy else "LOCAL",
        "network_allowed": config.allow_network,
        "excel_read_engine": config.excel_read_engine,
        "excel_read_workers": config.excel_read_workers,
        "excel_write_workers": config.excel_write_workers,
        "embedding_model": config.embedding_model_path or "disabled/not installed",
        "reranker_model": config.reranker_model_path or "disabled/not installed",
        "reference_sha256": file_sha256(reference.path) if reference.path.exists() else "",
        "bidder_sha256": {bidder.bidder: file_sha256(bidder.path) for bidder in bidders},
        "sheet_mappings": {bidder.bidder: bidder.sheet_info for bidder in bidders},
        "read_performance": {
            bidder.bidder: {
                "engine": bidder.read_engine,
                "seconds": round(bidder.read_seconds, 4),
                "items": len(bidder.items),
            }
            for bidder in bidders
        },
        "formula_issue_counts": {bidder.bidder: len(bidder.formula_issues) for bidder in bidders},
        "external_link_counts": {bidder.bidder: bidder.external_link_count for bidder in bidders},
        "thresholds": {name: getattr(config.thresholds, name) for name in config.thresholds.__dataclass_fields__},
    }


def run_comparison(hsmt_path, hsdt_path, output_path=None, ten_nha_thau="Nhà thầu", **kwargs):
    config = kwargs.pop("config", None) or EnterpriseConfig.from_env()
    if "fuzzy_threshold" in kwargs:
        config.thresholds.name_reject_score = float(kwargs["fuzzy_threshold"])
    return compare_tender_files(hsmt_path, [(ten_nha_thau, hsdt_path)], output_path=output_path, config=config)


def run_multi(hsmt_path, bidder_files, output_path=None, config=None):
    return compare_tender_files(hsmt_path, bidder_files, output_path=output_path, config=config)
