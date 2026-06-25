from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Protocol

import cv2
import numpy as np

from .config import OCRConfig
from .grid import make_variants
from .models import OCRCandidate


class TextEngine(Protocol):
    name: str

    def recognize(self, image: np.ndarray, numeric: bool = False) -> OCRCandidate: ...


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def clean_numeric(text: str) -> str:
    text = str(text or "").strip()
    table = str.maketrans({
        "O": "0", "o": "0", "I": "1", "l": "1", "|": "1",
        "S": "5", "B": "8", "D": "0", "—": "-", "–": "-",
        "，": ",", "．": ".", "。": ".",
    })
    text = text.translate(table)
    return re.sub(r"[^0-9.,()\-+]", "", text)


def _result_dict(result: Any) -> dict[str, Any]:
    data = getattr(result, "json", None)
    if callable(data):
        try:
            data = data()
        except Exception:
            data = None
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            data = None
    if isinstance(data, dict):
        return data.get("res", data) if isinstance(data.get("res", data), dict) else data
    for attr in ("res", "_res"):
        value = getattr(result, attr, None)
        if isinstance(value, dict):
            return value.get("res", value) if isinstance(value.get("res", value), dict) else value
    return {}


def _walk_strings(value: Any, keys: set[str]) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in keys and isinstance(child, str):
                found.append(child)
            found.extend(_walk_strings(child, keys))
    elif isinstance(value, (list, tuple)):
        for child in value:
            found.extend(_walk_strings(child, keys))
    return found


class _HTMLTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._table_depth = 0

    def handle_starttag(self, tag: str, attrs):
        tag = tag.lower()
        if tag == "table":
            self._table_depth += 1
            if self._table_depth == 1:
                self._table = []
        elif self._table_depth == 1 and tag == "tr":
            self._row = []
        elif self._table_depth == 1 and tag in {"td", "th"}:
            self._cell = []
        elif self._cell is not None and tag == "br":
            self._cell.append(" ")

    def handle_data(self, data: str):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        if self._table_depth == 1 and tag in {"td", "th"} and self._cell is not None:
            if self._row is not None:
                self._row.append(clean_text("".join(self._cell)))
            self._cell = None
        elif self._table_depth == 1 and tag == "tr" and self._row is not None:
            if any(cell for cell in self._row):
                assert self._table is not None
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table_depth:
            if self._table_depth == 1 and self._table:
                self.tables.append(self._table)
                self._table = None
            self._table_depth -= 1


def parse_html_tables(html: str) -> list[list[list[str]]]:
    parser = _HTMLTableParser()
    try:
        parser.feed(html or "")
    except Exception:
        return []
    return parser.tables


def parse_markdown_tables(markdown: str) -> list[list[list[str]]]:
    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    for line in str(markdown or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [clean_text(x) for x in stripped.strip("|").split("|")]
            if cells and all(re.fullmatch(r":?-{2,}:?", c.replace(" ", "")) for c in cells):
                continue
            current.append(cells)
        elif current:
            if len(current) >= 2:
                tables.append(current)
            current = []
    if len(current) >= 2:
        tables.append(current)
    return tables


def extract_table_matrices(results: list[Any]) -> list[list[list[str]]]:
    matrices: list[list[list[str]]] = []
    for result in results:
        data = _result_dict(result)
        html_strings = _walk_strings(data, {"html", "pred_html", "table_html", "html_text"})
        for html in html_strings:
            matrices.extend(parse_html_tables(html))
        markdown_strings = _walk_strings(data, {"markdown", "md", "markdown_text"})
        for markdown in markdown_strings:
            matrices.extend(parse_markdown_tables(markdown))
    # Deduplicate identical matrices emitted in multiple result fields.
    unique: list[list[list[str]]] = []
    seen: set[str] = set()
    for matrix in matrices:
        width = max((len(row) for row in matrix), default=0)
        normalized = [row + [""] * (width - len(row)) for row in matrix]
        key = json.dumps(normalized, ensure_ascii=False)
        if key not in seen:
            seen.add(key)
            unique.append(normalized)
    return unique


class PaddleOCRv6Engine:
    name = "PP-OCRv6-medium-local"

    def __init__(self, config: OCRConfig):
        self.model = None
        if not config.paddle_ocr_yaml or not Path(config.paddle_ocr_yaml).exists():
            return
        try:
            from paddleocr import PaddleOCR

            self.model = PaddleOCR(paddlex_config=config.paddle_ocr_yaml, device=config.device)
        except Exception:
            self.model = None

    @property
    def available(self) -> bool:
        return self.model is not None

    def recognize(self, image: np.ndarray, numeric: bool = False) -> OCRCandidate:
        if not self.model:
            return OCRCandidate("", 0.0, self.name)
        try:
            output = list(self.model.predict(input=image))
            texts: list[str] = []
            scores: list[float] = []
            for result in output:
                root = _result_dict(result)
                texts.extend(map(str, root.get("rec_texts", []) or root.get("texts", [])))
                scores.extend(float(x) for x in (root.get("rec_scores", []) or root.get("scores", [])))
            text = " ".join(texts)
            text = clean_numeric(text) if numeric else clean_text(text)
            return OCRCandidate(text, float(np.mean(scores)) if scores else 0.0, self.name)
        except Exception:
            return OCRCandidate("", 0.0, self.name)


class TesseractEngine:
    name = "Tesseract-5-local"

    def __init__(self, config: OCRConfig):
        self.available = False
        try:
            import pytesseract

            if config.tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = config.tesseract_cmd
            _ = pytesseract.get_tesseract_version()
            self.pytesseract = pytesseract
            self.available = True
        except Exception:
            self.pytesseract = None

    def recognize(self, image: np.ndarray, numeric: bool = False) -> OCRCandidate:
        if not self.available:
            return OCRCandidate("", 0.0, self.name)
        config = "--oem 1 --psm 7 -c preserve_interword_spaces=1"
        if numeric:
            config += " -c tessedit_char_whitelist=0123456789.,()-+"
        try:
            data = self.pytesseract.image_to_data(
                image, lang="vie+eng", config=config,
                output_type=self.pytesseract.Output.DICT,
            )
        except Exception:
            try:
                data = self.pytesseract.image_to_data(
                    image, lang="eng", config=config,
                    output_type=self.pytesseract.Output.DICT,
                )
            except Exception:
                return OCRCandidate("", 0.0, self.name)
        texts: list[str] = []
        confidences: list[float] = []
        for text, confidence in zip(data.get("text", []), data.get("conf", [])):
            text = str(text).strip()
            try:
                score = float(confidence)
            except Exception:
                score = -1
            if text and score >= 0:
                texts.append(text)
                confidences.append(score / 100.0)
        result = " ".join(texts)
        result = clean_numeric(result) if numeric else clean_text(result)
        return OCRCandidate(result, float(np.mean(confidences)) if confidences else 0.0, self.name)


class PaddleBatchRecognitionEngine:
    """PP-OCRv6-medium recognition-only cho các ô đã được cắt sẵn."""

    name = "PP-OCRv6-medium-rec-local"

    def __init__(self, config: OCRConfig):
        self.model = None
        self.config = config
        model_dir = Path(config.paddle_rec_model_dir) if config.paddle_rec_model_dir else None
        if not model_dir or not model_dir.exists():
            return
        try:
            from paddleocr import TextRecognition

            self.model = TextRecognition(
                model_name=config.paddle_rec_model_name,
                model_dir=str(model_dir),
                device=config.device,
                enable_hpi=True,
            )
        except Exception:
            self.model = None

    @property
    def available(self) -> bool:
        return self.model is not None

    def recognize_batch(self, images: list[np.ndarray], batch_size: int) -> list[OCRCandidate]:
        if not self.model or not images:
            return [OCRCandidate("", 0.0, self.name) for _ in images]
        output: list[OCRCandidate] = []
        try:
            results = list(self.model.predict(input=images, batch_size=batch_size))
            for result in results:
                root = _result_dict(result)
                text = root.get("rec_text", "") or root.get("text", "")
                score = root.get("rec_score", 0.0) or root.get("score", 0.0)
                output.append(OCRCandidate(clean_text(str(text)), float(score), self.name))
        except Exception:
            return [OCRCandidate("", 0.0, self.name) for _ in images]
        if len(output) < len(images):
            output.extend(OCRCandidate("", 0.0, self.name) for _ in range(len(images) - len(output)))
        return output[:len(images)]


class OCRCellEnsemble:
    def __init__(self, config: OCRConfig):
        self.config = config
        paddle = PaddleOCRv6Engine(config)
        tesseract = TesseractEngine(config)
        self.engines: list[TextEngine] = []
        if paddle.available:
            self.engines.append(paddle)
        if tesseract.available:
            self.engines.append(tesseract)

    @property
    def available(self) -> bool:
        return bool(self.engines)

    def recognize(self, cell_image: np.ndarray, numeric: bool = False) -> tuple[OCRCandidate, list[OCRCandidate]]:
        candidates: list[OCRCandidate] = []
        variants = make_variants(cell_image, self.config.effective_upscale())
        # Fast/balanced modes use fewer variants; high mode uses all five.
        if self.config.accuracy_mode == "fast":
            variants = variants[:2]
        elif self.config.accuracy_mode == "balanced":
            variants = variants[:4]
        for variant_name, variant in variants:
            for engine in self.engines:
                result = engine.recognize(variant, numeric=numeric)
                result.variant = variant_name
                if result.text:
                    candidates.append(result)
        if not candidates:
            return OCRCandidate("", 0.0, "none"), []

        normalize = clean_numeric if numeric else lambda text: clean_text(text).casefold()
        groups: dict[str, list[OCRCandidate]] = {}
        for candidate in candidates:
            groups.setdefault(normalize(candidate.text), []).append(candidate)
        ranked: list[tuple[int, float, int, OCRCandidate]] = []
        for key, group in groups.items():
            base = max(group, key=lambda item: item.confidence)
            engines = len({item.engine for item in group})
            variants_count = len({item.variant for item in group})
            agreement = engines * 2 + variants_count
            score = min(0.999, base.confidence + min(0.16, 0.025 * (agreement - 1)))
            ranked.append((agreement, score, len(key), OCRCandidate(base.text, score, base.engine, base.variant)))
        ranked.sort(reverse=True, key=lambda item: (item[0], item[1], item[2]))
        return ranked[0][3], candidates


class FastCellRecognizer:
    """Hai tầng: PP-OCRv6-medium batch trước, ensemble chỉ chạy lại ô khó."""

    def __init__(self, config: OCRConfig):
        self.config = config
        self.batch = PaddleBatchRecognitionEngine(config)
        self.tesseract = TesseractEngine(config)
        self.slow = OCRCellEnsemble(config)

    @property
    def available(self) -> bool:
        return self.batch.available or self.slow.available

    @property
    def engines(self) -> list[str]:
        names: list[str] = []
        if self.batch.available:
            names.append(self.batch.name)
        if self.tesseract.available:
            names.append(self.tesseract.name)
        return names

    @property
    def has_primary_model(self) -> bool:
        return self.batch.available or any(
            getattr(engine, "name", "").startswith("PP-OCR")
            for engine in self.slow.engines
        )

    def recognize_many(
        self,
        cell_images: list[np.ndarray],
        numeric_flags: list[bool],
    ) -> list[tuple[OCRCandidate, list[OCRCandidate]]]:
        if not cell_images:
            return []
        primary: list[np.ndarray] = []
        for image in cell_images:
            variants = make_variants(image, self.config.effective_upscale())
            primary.append(variants[2][1] if len(variants) > 2 else variants[0][1] if variants else image)

        if self.batch.available:
            first_results = self.batch.recognize_batch(primary, batch_size=self.config.batch_size)
        elif self.tesseract.available:
            # Tesseract chạy thành tiến trình ngoài nên có thể song song an toàn bằng
            # ThreadPoolExecutor. Giới hạn workers từ cấu hình để tránh đầy RAM khi
            # nhiều người đồng thời gửi PDF lớn.
            work_items = list(zip(primary, numeric_flags))
            max_workers = max(1, min(int(self.config.workers), 8, len(work_items)))
            if max_workers > 1 and len(work_items) >= 8:
                def recognize_one(item: tuple[np.ndarray, bool]) -> OCRCandidate:
                    image, numeric = item
                    return self.tesseract.recognize(image, numeric=numeric)

                with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ocr-cell") as executor:
                    first_results = list(executor.map(recognize_one, work_items))
            else:
                first_results = [
                    self.tesseract.recognize(image, numeric=numeric)
                    for image, numeric in work_items
                ]
        else:
            first_results = [OCRCandidate("", 0.0, "none") for _ in primary]

        outputs: list[tuple[OCRCandidate, list[OCRCandidate]]] = []
        for original, numeric, first in zip(cell_images, numeric_flags, first_results):
            if numeric:
                first.text = clean_numeric(first.text)
            threshold = self.config.min_numeric_confidence if numeric else self.config.min_text_confidence
            # Ultra mode uses the strongest local ensemble for every numeric cell,
            # because a single wrong digit can materially change bid evaluation.
            ultra_force_retry = (
                self.config.accuracy_mode == "ultra"
                and (numeric and self.config.ultra_retry_all_numeric or first.confidence < 0.96)
            )
            if first.text and first.confidence >= threshold and not ultra_force_retry:
                outputs.append((first, [first]))
                continue
            # Với Tesseract-only, không lặp ensemble cho mọi ô; ultra/high chỉ retry
            # khi thực sự cần hoặc khi ô số bắt buộc kiểm tra chéo.
            retry = self.batch.available or ultra_force_retry or (self.config.accuracy_mode in {"high", "ultra"} and first.confidence < 0.45)
            if retry:
                best, candidates = self.slow.recognize(original, numeric=numeric)
                if first.text:
                    candidates.append(first)
                    if first.confidence > best.confidence:
                        best = first
                outputs.append((best, candidates))
            else:
                outputs.append((first, [first] if first.text else []))
        return outputs


class PaddleTableFallback:
    name = "PP-TableMagic-v2-local"

    def __init__(self, config: OCRConfig):
        self.pipeline = None
        if not config.use_tablemagic_fallback:
            return
        if not config.tablemagic_yaml or not Path(config.tablemagic_yaml).exists():
            return
        try:
            from paddleocr import TableRecognitionPipelineV2

            self.pipeline = TableRecognitionPipelineV2(
                paddlex_config=config.tablemagic_yaml,
                device=config.device,
            )
        except Exception:
            self.pipeline = None

    @property
    def available(self) -> bool:
        return self.pipeline is not None

    def predict_matrices(self, image: np.ndarray) -> list[list[list[str]]]:
        if not self.pipeline:
            return []
        try:
            return extract_table_matrices(list(self.pipeline.predict(input=image)))
        except Exception:
            return []


class PaddleStructureFallback:
    name = "PP-StructureV3-local"

    def __init__(self, config: OCRConfig):
        self.pipeline = None
        if not config.use_ppstructure_fallback:
            return
        if not config.ppstructure_yaml or not Path(config.ppstructure_yaml).exists():
            return
        try:
            from paddleocr import PPStructureV3

            self.pipeline = PPStructureV3(
                paddlex_config=config.ppstructure_yaml,
                device=config.device,
            )
        except Exception:
            self.pipeline = None

    @property
    def available(self) -> bool:
        return self.pipeline is not None

    def predict_matrices(self, image: np.ndarray) -> list[list[list[str]]]:
        if not self.pipeline:
            return []
        try:
            return extract_table_matrices(list(self.pipeline.predict(input=image)))
        except Exception:
            return []


class PaddleOCRVLFallback:
    """PaddleOCR-VL-1.6 full pipeline chạy local.

    Không khởi tạo khi thiếu model local hoặc local model server. Trong strict
    privacy, URL server ngoài loopback bị từ chối.
    """

    name = "PaddleOCR-VL-1.6-local"

    def __init__(self, config: OCRConfig):
        self.pipeline = None
        self.config = config
        if not config.use_paddle_vl_fallback:
            return
        yaml_path = Path(config.paddle_vl_yaml) if config.paddle_vl_yaml else None
        layout_dir = Path(config.paddle_vl_layout_model_dir) if config.paddle_vl_layout_model_dir else None
        local_dir = Path(config.paddle_vl_model_dir) if config.paddle_vl_model_dir else None
        server_ok = bool(config.paddle_vl_server_url) and (not config.strict_privacy or config.is_loopback_server())
        full_local_ok = bool(yaml_path and yaml_path.exists()) or bool(
            layout_dir and layout_dir.exists() and local_dir and local_dir.exists()
        )
        if not full_local_ok and not server_ok:
            return
        try:
            from paddleocr import PaddleOCRVL

            kwargs: dict[str, Any] = {
                "pipeline_version": config.paddle_vl_pipeline_version,
                "device": config.device,
                "use_doc_orientation_classify": False,
                "use_doc_unwarping": False,
                "use_layout_detection": True,
                "vl_rec_max_concurrency": config.paddle_vl_max_concurrency,
            }
            if yaml_path and yaml_path.exists():
                # YAML phải chứa toàn bộ model_dir local của layout, ranking và VLM.
                kwargs["paddlex_config"] = str(yaml_path)
            else:
                kwargs["layout_detection_model_dir"] = str(layout_dir)
                kwargs["vl_rec_model_dir"] = str(local_dir)
            if server_ok:
                kwargs["vl_rec_backend"] = config.paddle_vl_backend or "vllm-server"
                kwargs["vl_rec_server_url"] = config.paddle_vl_server_url
                kwargs["vl_rec_api_model_name"] = config.paddle_vl_api_model_name
            elif config.paddle_vl_backend:
                kwargs["engine"] = (
                    config.paddle_vl_backend
                    if config.paddle_vl_backend in {"paddle", "paddle_static", "paddle_dynamic", "transformers"}
                    else None
                )
            kwargs = {key: value for key, value in kwargs.items() if value not in {None, ""}}
            self.pipeline = PaddleOCRVL(**kwargs)
        except Exception:
            self.pipeline = None

    @property
    def available(self) -> bool:
        return self.pipeline is not None

    def predict_matrices(self, image: np.ndarray) -> list[list[list[str]]]:
        if not self.pipeline:
            return []
        try:
            results = list(self.pipeline.predict(
                input=image,
                min_pixels=self.config.vl_min_pixels,
                max_pixels=self.config.vl_max_pixels,
                max_new_tokens=self.config.vl_max_new_tokens,
                temperature=0.0,
                top_p=1.0,
                repetition_penalty=1.05,
                vlm_extra_args={
                    "table_min_pixels": self.config.vl_table_min_pixels,
                    "table_max_pixels": self.config.vl_table_max_pixels,
                    "ocr_min_pixels": self.config.vl_ocr_min_pixels,
                    "ocr_max_pixels": self.config.vl_ocr_max_pixels,
                },
            ))
            return extract_table_matrices(results)
        except Exception:
            return []
