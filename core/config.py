from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .models import CompareThresholds


def _bool_env(name: str, default: bool) -> bool:
    return os.getenv(name, "1" if default else "0").strip().lower() not in {"0", "false", "no", "off"}


def _int_env(name: str, default: int, minimum: int = 1, maximum: int = 64) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


@dataclass(slots=True)
class EnterpriseConfig:
    thresholds: CompareThresholds = field(default_factory=CompareThresholds)

    # Security / runtime
    strict_privacy: bool = True
    allow_network: bool = False
    runtime_root: Path = Path("runtime/jobs")
    max_upload_mb: int = 2048
    max_excel_rows: int = 1_000_000
    max_concurrent_jobs: int = 3
    job_retention_hours: int = 24

    # Fast Excel I/O
    excel_read_engine: str = "calamine"          # calamine | openpyxl | auto
    excel_read_workers: int = 4                  # files read in parallel per job
    excel_write_workers: int = 1                 # annotated files written in parallel
    excel_scan_formulas: bool = True             # direct OOXML scan for #REF!, etc.
    excel_scan_external_links: bool = True
    excel_fallback_openpyxl: bool = True

    # Matching
    model_root: Path = Path("models")
    embedding_model_path: str = ""
    reranker_model_path: str = ""
    enable_semantic_matching: bool = False
    enable_reranker: bool = False
    semantic_batch_size: int = 32
    reranker_batch_size: int = 16
    fuzzy_top_k: int = 8
    semantic_top_k: int = 5
    max_fuzzy_candidates: int = 250_000

    # Reporting
    report_constant_memory: bool = True
    # Báo cáo phân tích nhiều sheet (nặng) — mặc định bật để giữ tương thích. Tắt
    # đi (HSMT_ANALYTICAL_REPORT=0) để dùng bảng tổng hợp nhẹ làm báo cáo chính,
    # nhanh hơn nhiều khi có nhiều hồ sơ.
    generate_analytical_report: bool = True
    random_state: int = 42

    @classmethod
    def from_env(cls) -> "EnterpriseConfig":
        engine = os.getenv("HSMT_EXCEL_READ_ENGINE", "calamine").strip().lower()
        if engine not in {"calamine", "openpyxl", "auto"}:
            engine = "calamine"
        return cls(
            strict_privacy=_bool_env("HSMT_STRICT_PRIVACY", True),
            allow_network=_bool_env("HSMT_ALLOW_NETWORK", False),
            runtime_root=Path(os.getenv("HSMT_RUNTIME_ROOT", "runtime/jobs")),
            max_upload_mb=_int_env("HSMT_MAX_UPLOAD_MB", 2048, 1, 100_000),
            max_excel_rows=_int_env("HSMT_MAX_EXCEL_ROWS", 1_000_000, 1_000, 10_000_000),
            max_concurrent_jobs=_int_env("HSMT_MAX_CONCURRENT_JOBS", 3, 1, 16),
            job_retention_hours=_int_env("HSMT_JOB_RETENTION_HOURS", 24, 1, 24 * 365),
            excel_read_engine=engine,
            excel_read_workers=_int_env("HSMT_EXCEL_READ_WORKERS", 4, 1, 16),
            excel_write_workers=_int_env("HSMT_EXCEL_WRITE_WORKERS", 1, 1, 8),
            excel_scan_formulas=_bool_env("HSMT_EXCEL_SCAN_FORMULAS", True),
            excel_scan_external_links=_bool_env("HSMT_EXCEL_SCAN_EXTERNAL_LINKS", True),
            excel_fallback_openpyxl=_bool_env("HSMT_EXCEL_FALLBACK_OPENPYXL", True),
            model_root=Path(os.getenv("HSMT_MODEL_ROOT", "models")),
            embedding_model_path=os.getenv("HSMT_EMBEDDING_MODEL", ""),
            reranker_model_path=os.getenv("HSMT_RERANKER_MODEL", ""),
            enable_semantic_matching=_bool_env("HSMT_ENABLE_EMBEDDINGS", False),
            enable_reranker=_bool_env("HSMT_ENABLE_RERANKER", False),
            semantic_batch_size=_int_env("HSMT_EMBED_BATCH", 32, 1, 512),
            reranker_batch_size=_int_env("HSMT_RERANK_BATCH", 16, 1, 256),
            fuzzy_top_k=_int_env("HSMT_FUZZY_TOP_K", 8, 1, 100),
            semantic_top_k=_int_env("HSMT_SEMANTIC_TOP_K", 5, 1, 100),
            generate_analytical_report=_bool_env("HSMT_ANALYTICAL_REPORT", True),
        )
