from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import EnterpriseConfig
from ocr.config import OCRConfig


def hash_tree(root: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    count = 0
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        count += 1
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    return count, digest.hexdigest()


def main() -> None:
    cfg = EnterpriseConfig.from_env()
    ocr = OCRConfig.from_env()
    paths = {
        "Qwen3/BGE embedding": cfg.embedding_model_path,
        "Qwen3/BGE reranker": cfg.reranker_model_path,
        "PP-OCRv6-medium recognition": ocr.paddle_rec_model_dir,
        "OCR YAML": ocr.paddle_ocr_yaml,
        "TableMagic YAML": ocr.tablemagic_yaml,
        "PP-Structure YAML": ocr.ppstructure_yaml,
        "PaddleOCR-VL-1.6 pipeline YAML": ocr.paddle_vl_yaml,
        "PaddleOCR-VL-1.6 layout": ocr.paddle_vl_layout_model_dir,
        "PaddleOCR-VL-1.6 recognition": ocr.paddle_vl_model_dir,
    }
    failed = False
    for label, raw in paths.items():
        if not raw:
            print(f"[SKIP] {label}: chưa cấu hình")
            continue
        path = Path(raw)
        if not path.exists():
            print(f"[FAIL] {label}: {path}")
            failed = True
            continue
        if path.is_dir():
            count, digest = hash_tree(path)
            print(f"[OK] {label}: {count} files, tree-sha256={digest}")
        else:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            print(f"[OK] {label}: sha256={digest}")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
