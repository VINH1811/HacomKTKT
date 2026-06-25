from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass(slots=True)
class OCRConfig:
    """Cấu hình OCR chạy hoàn toàn trong hạ tầng nội bộ.

    ``accuracy_mode=high`` ưu tiên độ chính xác: grid-first, PP-OCRv6-medium theo ô,
    PP-TableMagic/PP-StructureV3 và PaddleOCR-VL-1.6 chỉ làm fallback.
    """

    strict_privacy: bool = True
    device: str = "cpu"
    accuracy_mode: str = "balanced"  # fast | balanced | high | ultra
    document_profile: str = "dense_boq"  # dense_boq | generic_table | document
    render_dpi: int = 400
    upscale_factor: float = 3.5
    max_pages: int = 500
    max_file_gb: float = 2.0
    min_cell_width: int = 7
    min_cell_height: int = 5
    min_text_confidence: float = 0.82
    min_numeric_confidence: float = 0.90
    min_structure_confidence: float = 0.45
    math_tolerance_pct: float = 0.005
    component_tolerance_pct: float = 0.01
    orientation_with_tesseract: bool = True
    # Probe ngữ nghĩa ở vùng đầu trang để phân biệt 0/180 độ. Tesseract OSD và
    # hình học lưới không đủ tin cậy với bảng ngang dày đặc.
    orientation_semantic_probe: bool = True
    orientation_probe_top_ratio: float = 0.30
    orientation_probe_target_width: int = 3000
    orientation_probe_min_gap: float = 6.0
    orientation_probe_timeout: float = 20.0
    use_grid_first: bool = True
    use_tablemagic_fallback: bool = True
    use_ppstructure_fallback: bool = True
    use_paddle_vl_fallback: bool = True
    use_paddle_vl_for_uncertain_tables: bool = True
    use_arithmetic_reconciliation: bool = True
    save_review_images: bool = True
    allow_tesseract_only: bool = True
    workers: int = 1
    batch_size: int = 32
    gpu_vram_gb: float = 0.0
    precision: str = "fp32"
    ultra_retry_all_numeric: bool = True
    ultra_vl_reconcile_tables: bool = True

    # PP-OCRv6-medium recognition-only fast path (PP-OCRv5 Latin có thể dùng làm fallback nếu cần).
    paddle_ocr_yaml: str = ""
    paddle_rec_model_dir: str = ""
    paddle_rec_model_name: str = "PP-OCRv6_medium_rec"

    # Structured table/document fallbacks.
    tablemagic_yaml: str = ""
    ppstructure_yaml: str = ""

    # PaddleOCR-VL-1.6 full pipeline. A local model directory or a loopback-only
    # local model server is required in strict privacy mode.
    paddle_vl_pipeline_version: str = "v1.6"
    paddle_vl_yaml: str = ""
    paddle_vl_layout_model_dir: str = ""
    paddle_vl_model_dir: str = ""
    paddle_vl_backend: str = ""  # empty/paddle/transformers/vllm-server/sglang-server/fastdeploy-server
    paddle_vl_server_url: str = ""
    paddle_vl_api_model_name: str = "PaddlePaddle/PaddleOCR-VL-1.6"
    paddle_vl_max_concurrency: int = 1
    vl_min_pixels: int = 1_048_576
    vl_max_pixels: int = 16_777_216
    vl_table_min_pixels: int = 1_572_864
    vl_table_max_pixels: int = 20_971_520
    vl_ocr_min_pixels: int = 786_432
    vl_ocr_max_pixels: int = 12_582_912
    vl_max_new_tokens: int = 8192

    tesseract_cmd: str = ""
    debug_dir: str = ""

    @classmethod
    def from_env(cls) -> "OCRConfig":
        truthy = lambda name, default="1": os.getenv(name, default).strip().lower() not in {"0", "false", "no", "off"}
        return cls(
            strict_privacy=truthy("HSMT_STRICT_PRIVACY"),
            device=os.getenv("HSMT_OCR_DEVICE", "cpu"),
            accuracy_mode=os.getenv("HSMT_OCR_ACCURACY_MODE", "balanced").strip().lower(),
            document_profile=os.getenv("HSMT_OCR_PROFILE", "dense_boq").strip().lower(),
            render_dpi=int(os.getenv("HSMT_OCR_DPI", "400")),
            upscale_factor=float(os.getenv("HSMT_OCR_UPSCALE", "3.5")),
            max_pages=int(os.getenv("HSMT_MAX_PDF_PAGES", "500")),
            max_file_gb=float(os.getenv("HSMT_OCR_MAX_FILE_GB", "2")),
            min_text_confidence=float(os.getenv("HSMT_OCR_MIN_TEXT_CONF", "0.82")),
            min_numeric_confidence=float(os.getenv("HSMT_OCR_MIN_NUMERIC_CONF", "0.90")),
            min_structure_confidence=float(os.getenv("HSMT_OCR_MIN_STRUCTURE_CONF", "0.45")),
            math_tolerance_pct=float(os.getenv("HSMT_OCR_MATH_TOLERANCE", "0.005")),
            component_tolerance_pct=float(os.getenv("HSMT_OCR_COMPONENT_TOLERANCE", "0.01")),
            orientation_with_tesseract=truthy("HSMT_OCR_USE_OSD", "1"),
            orientation_semantic_probe=truthy("HSMT_OCR_ORIENTATION_PROBE", "1"),
            orientation_probe_top_ratio=float(os.getenv("HSMT_OCR_ORIENTATION_TOP_RATIO", "0.30")),
            orientation_probe_target_width=int(os.getenv("HSMT_OCR_ORIENTATION_TARGET_WIDTH", "3000")),
            orientation_probe_min_gap=float(os.getenv("HSMT_OCR_ORIENTATION_MIN_GAP", "6.0")),
            orientation_probe_timeout=float(os.getenv("HSMT_OCR_ORIENTATION_TIMEOUT", "20")),
            use_tablemagic_fallback=truthy("HSMT_USE_TABLEMAGIC", "1"),
            use_ppstructure_fallback=truthy("HSMT_USE_PPSTRUCTURE", "1"),
            use_paddle_vl_fallback=truthy("HSMT_USE_PADDLE_VL", "1"),
            use_paddle_vl_for_uncertain_tables=truthy("HSMT_USE_VL_UNCERTAIN_TABLES", "1"),
            use_arithmetic_reconciliation=truthy("HSMT_OCR_ARITHMETIC_RECONCILIATION", "1"),
            save_review_images=truthy("HSMT_OCR_SAVE_REVIEW_IMAGES", "1"),
            allow_tesseract_only=truthy("HSMT_OCR_ALLOW_TESSERACT_ONLY", "1"),
            workers=int(os.getenv("HSMT_OCR_WORKERS", "1")),
            batch_size=int(os.getenv("HSMT_OCR_BATCH_SIZE", "32")),
            gpu_vram_gb=float(os.getenv("HSMT_OCR_GPU_VRAM_GB", "0")),
            precision=os.getenv("HSMT_OCR_PRECISION", "fp32"),
            ultra_retry_all_numeric=truthy("HSMT_OCR_ULTRA_RETRY_ALL_NUMERIC", "1"),
            ultra_vl_reconcile_tables=truthy("HSMT_OCR_ULTRA_VL_RECONCILE", "1"),
            paddle_ocr_yaml=os.getenv("HSMT_PADDLE_OCR_YAML", ""),
            paddle_rec_model_dir=os.getenv("HSMT_PADDLE_REC_MODEL_DIR", ""),
            paddle_rec_model_name=os.getenv("HSMT_PADDLE_REC_MODEL_NAME", "PP-OCRv6_medium_rec"),
            tablemagic_yaml=os.getenv("HSMT_TABLEMAGIC_YAML", ""),
            ppstructure_yaml=os.getenv("HSMT_PPSTRUCTURE_YAML", ""),
            paddle_vl_pipeline_version=os.getenv("HSMT_PADDLE_VL_VERSION", "v1.6"),
            paddle_vl_yaml=os.getenv("HSMT_PADDLE_VL_YAML", ""),
            paddle_vl_layout_model_dir=os.getenv("HSMT_PADDLE_VL_LAYOUT_MODEL_DIR", ""),
            paddle_vl_model_dir=os.getenv("HSMT_PADDLE_VL_MODEL_DIR", ""),
            paddle_vl_backend=os.getenv("HSMT_PADDLE_VL_BACKEND", ""),
            paddle_vl_server_url=os.getenv("HSMT_PADDLE_VL_SERVER_URL", ""),
            paddle_vl_api_model_name=os.getenv("HSMT_PADDLE_VL_API_MODEL_NAME", "PaddlePaddle/PaddleOCR-VL-1.6"),
            paddle_vl_max_concurrency=int(os.getenv("HSMT_PADDLE_VL_MAX_CONCURRENCY", "1")),
            vl_min_pixels=int(os.getenv("HSMT_VL_MIN_PIXELS", "1048576")),
            vl_max_pixels=int(os.getenv("HSMT_VL_MAX_PIXELS", "16777216")),
            vl_table_min_pixels=int(os.getenv("HSMT_VL_TABLE_MIN_PIXELS", "1572864")),
            vl_table_max_pixels=int(os.getenv("HSMT_VL_TABLE_MAX_PIXELS", "20971520")),
            vl_ocr_min_pixels=int(os.getenv("HSMT_VL_OCR_MIN_PIXELS", "786432")),
            vl_ocr_max_pixels=int(os.getenv("HSMT_VL_OCR_MAX_PIXELS", "12582912")),
            vl_max_new_tokens=int(os.getenv("HSMT_VL_MAX_NEW_TOKENS", "8192")),
            tesseract_cmd=os.getenv("TESSERACT_CMD", ""),
            debug_dir=os.getenv("HSMT_OCR_DEBUG_DIR", ""),
        )

    def is_loopback_server(self) -> bool:
        if not self.paddle_vl_server_url:
            return False
        host = (urlparse(self.paddle_vl_server_url).hostname or "").lower()
        return host in {"127.0.0.1", "localhost", "::1"}

    def validate_local_models(self) -> list[str]:
        warnings: list[str] = []
        for label, path in [
            ("PP-OCRv6 pipeline", self.paddle_ocr_yaml),
            ("PP-OCRv6 recognition", self.paddle_rec_model_dir),
            ("PP-TableMagic", self.tablemagic_yaml),
            ("PP-StructureV3", self.ppstructure_yaml),
            ("PaddleOCR-VL-1.6 pipeline YAML", self.paddle_vl_yaml),
            ("PaddleOCR-VL-1.6 layout", self.paddle_vl_layout_model_dir),
            ("PaddleOCR-VL-1.6 recognition", self.paddle_vl_model_dir),
        ]:
            if path and not Path(path).exists():
                warnings.append(f"{label}: không tìm thấy tài nguyên local '{path}'")
        if self.strict_privacy and self.paddle_vl_server_url and not self.is_loopback_server():
            warnings.append("PaddleOCR-VL server bị vô hiệu: strict privacy chỉ cho phép localhost/127.0.0.1.")
        if self.paddle_vl_pipeline_version != "v1.6":
            warnings.append(f"Đang dùng PaddleOCR-VL {self.paddle_vl_pipeline_version}; cấu hình khuyến nghị là v1.6.")
        return warnings

    def effective_upscale(self) -> float:
        if self.accuracy_mode == "fast":
            return min(self.upscale_factor, 2.5)
        if self.accuracy_mode == "balanced":
            return min(self.upscale_factor, 3.5)
        if self.accuracy_mode == "high":
            return max(self.upscale_factor, 4.0)
        return max(self.upscale_factor, 5.0)
