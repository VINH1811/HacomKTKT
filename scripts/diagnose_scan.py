from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ocr.config import OCRConfig
from ocr.grid import detect_grids
from ocr.pdf_io import load_pages
from ocr.orientation import probe_upright_pair


def main() -> None:
    parser = argparse.ArgumentParser(description="Kiểm tra chiều, DPI và lưới bảng mà không cần model OCR")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", help="Tệp JSON kết quả")
    args = parser.parse_args()

    config = OCRConfig.from_env()
    pages = load_pages(args.input, config)
    result = {
        "input": Path(args.input).name,
        "pages": [],
    }
    for page in pages:
        probes = probe_upright_pair(page.image, config)
        recommended_extra_rotation = max(probes, key=lambda angle: probes[angle].score)
        grids = detect_grids(
            page.image if recommended_extra_rotation == 0 else __import__("cv2").rotate(page.image, __import__("cv2").ROTATE_180),
            config,
        )
        result["pages"].append({
            "page": page.page,
            "image_width": int(page.image.shape[1]),
            "image_height": int(page.image.shape[0]),
            "initial_rotation": page.rotation,
            "recommended_extra_rotation": recommended_extra_rotation,
            "recommended_final_rotation": (page.rotation + recommended_extra_rotation) % 360,
            "orientation_scores": {str(angle): round(probe.score, 3) for angle, probe in probes.items()},
            "orientation_keywords": {str(angle): list(probe.keyword_hits) for angle, probe in probes.items()},
            "source": page.source,
            "estimated_dpi": round(page.estimated_dpi, 2),
            "tables": [
                {
                    "bbox": grid.bbox,
                    "columns": len(grid.x_lines) - 1,
                    "rows": len(grid.y_lines) - 1,
                    "structure_confidence": round(grid.confidence, 4),
                }
                for grid in grids
            ],
        })
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    print(payload)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")


if __name__ == "__main__":
    main()
