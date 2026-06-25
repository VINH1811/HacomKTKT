from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env", override=False)

from security import configure_offline_environment, deny_external_network

configure_offline_environment()

from core.config import EnterpriseConfig
from core.pipeline import compare_bidder_files, compare_tender_files
from core.tender_package import compare_pl1_pl2_with_bidders
from ocr.config import OCRConfig
from ocr.pipeline import create_ocr_package, run_ocr, run_ocr_batch


def _pairs(values: list[str]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for item in values:
        if "=" not in item:
            raise argparse.ArgumentTypeError("HSDT phải có dạng TenNhaThau=duong_dan.xlsx")
        name, path = item.split("=", 1)
        result.append((name.strip(), path.strip()))
    return result


def _ocr_config(args: argparse.Namespace) -> OCRConfig:
    config = OCRConfig.from_env()
    config.accuracy_mode = args.accuracy
    config.document_profile = args.profile
    config.save_review_images = not args.no_review_images
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description="HSMT Enterprise AI v8.3 — so sánh Excel và OCR nội bộ")
    sub = parser.add_subparsers(dest="command", required=True)

    compare = sub.add_parser("compare", help="So sánh HSMT với một hoặc nhiều HSDT")
    compare.add_argument("--hsmt", required=True)
    compare.add_argument("--hsdt", action="append", required=True, help="Tên=path.xlsx; có thể lặp lại")
    compare.add_argument("--output", required=True)

    bidders = sub.add_parser("compare-bidders", help="So sánh ngang nhiều HSDT")
    bidders.add_argument("--hsdt", action="append", required=True, help="Tên=path.xlsx; lặp lại ít nhất 2 lần")
    bidders.add_argument("--output", required=True)

    package = sub.add_parser("compare-package", help="Đối chiếu PL01/PL02 với một hoặc nhiều nhà thầu và đánh dấu file")
    package.add_argument("--pl1", help="Đường dẫn Phụ lục 01")
    package.add_argument("--pl2", help="Đường dẫn Phụ lục 02")
    package.add_argument(
        "--hsdt",
        action="append",
        required=True,
        help="Tên=path.xlsx; một file để đối chiếu phụ lục, từ hai file để thêm so sánh giá",
    )
    package.add_argument("--output-dir", required=True)

    ocr = sub.add_parser("ocr", help="Quét một PDF/ảnh scan sang Excel")
    ocr.add_argument("--input", required=True)
    ocr.add_argument("--output", required=True)
    ocr.add_argument("--accuracy", choices=["fast", "balanced", "high", "ultra"], default="balanced")
    ocr.add_argument("--profile", choices=["dense_boq", "generic_table", "document"], default="dense_boq")
    ocr.add_argument("--no-review-images", action="store_true")

    ocr_batch = sub.add_parser("ocr-batch", help="Quét nhiều PDF/ảnh và đóng gói ZIP")
    ocr_batch.add_argument("--input", action="append", required=True)
    ocr_batch.add_argument("--output-dir", required=True)
    ocr_batch.add_argument("--accuracy", choices=["fast", "balanced", "high", "ultra"], default="balanced")
    ocr_batch.add_argument("--profile", choices=["dense_boq", "generic_table", "document"], default="dense_boq")
    ocr_batch.add_argument("--no-review-images", action="store_true")

    args = parser.parse_args()
    config = EnterpriseConfig.from_env()
    created: str | Path

    with deny_external_network(config.strict_privacy and not config.allow_network):
        if args.command == "compare":
            compare_tender_files(args.hsmt, _pairs(args.hsdt), args.output, config)
            created = args.output
        elif args.command == "compare-bidders":
            pairs = _pairs(args.hsdt)
            if len(pairs) < 2:
                parser.error("compare-bidders cần ít nhất 2 --hsdt")
            compare_bidder_files(pairs, args.output, config)
            created = args.output
        elif args.command == "compare-package":
            if not args.pl1 and not args.pl2:
                parser.error("compare-package cần ít nhất --pl1 hoặc --pl2")
            pairs = _pairs(args.hsdt)
            if not pairs:
                parser.error("compare-package cần ít nhất 1 --hsdt")
            outputs = compare_pl1_pl2_with_bidders(args.pl1, args.pl2, pairs, args.output_dir, config)
            created = outputs.package_zip
        elif args.command == "ocr":
            run_ocr(args.input, args.output, _ocr_config(args))
            created = args.output
        else:
            output_dir = Path(args.output_dir)
            documents = run_ocr_batch(args.input, output_dir, _ocr_config(args))
            created = create_ocr_package(documents, output_dir)

    print(f"Đã tạo: {created}")


if __name__ == "__main__":
    main()
