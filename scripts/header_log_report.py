"""Xem nhật ký tiêu đề cột chưa nhận diện được, để mở rộng sổ tay từ khóa.

Mỗi lần hệ thống gặp một cột có tiêu đề mà không khóa nào nhận, nó ghi lại tiêu
đề đó cùng đặc trưng dữ liệu bên dưới. Chạy lệnh này định kỳ để xem cách viết
nào hay gặp, rồi khai vào HSMT_COLUMN_SYNONYMS.

    python scripts/header_log_report.py                 # xem tiêu đề hay gặp nhất
    python scripts/header_log_report.py --chi-tiet      # kèm đặc trưng dữ liệu
    python scripts/header_log_report.py -n 50           # xem nhiều hơn
"""

import argparse
import collections
import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

parser = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("log", nargs="?",
                    default=os.getenv("HSMT_HEADER_LOG_PATH", "runtime/header_log.jsonl"))
parser.add_argument("-n", "--so-luong", type=int, default=25)
parser.add_argument("--chi-tiet", action="store_true", help="kèm đặc trưng dữ liệu")
args = parser.parse_args()

path = Path(args.log)
if not path.exists():
    print(f"Chưa có nhật ký tại {path} — hệ thống chưa gặp tiêu đề lạ nào.")
    raise SystemExit(0)

count: collections.Counter[str] = collections.Counter()
detail: dict[str, dict] = {}
sheets: dict[str, set[str]] = {}
records = 0
for line in path.read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        continue
    records += 1
    for column in record.get("cot_chua_nhan_ra", []):
        header = column.get("tieu_de", "")
        if not header:
            continue
        count[header] += 1
        detail.setdefault(header, column)
        sheets.setdefault(header, set()).add(record.get("sheet", ""))

print(f"Nhật ký: {path}   ({records:,} lượt đọc file, {len(count)} tiêu đề lạ)")
print()
print(f"{'LẦN GẶP':>8}  TIÊU ĐỀ")
for header, times in count.most_common(args.so_luong):
    print(f"{times:>8}  {header}")
    if args.chi_tiet:
        info = detail[header]
        if info.get("kieu") == "chu":
            print(f"          chữ · mẫu: {', '.join(info.get('gia_tri_mau', [])[:5])}")
        elif info.get("kieu") == "so":
            thap_phan = "có thập phân" if info.get("co_phan_thap_phan") else "số nguyên"
            print(f"          số · {info.get('so_chu_so_it_nhat')}-{info.get('so_chu_so_nhieu_nhat')} "
                  f"chữ số · {thap_phan}")
        print(f"          sheet: {', '.join(sorted(sheets[header])[:4])}")

if count:
    print()
    print("Khai vào .env để hệ thống nhận ra lần sau, ví dụ:")
    print('  HSMT_COLUMN_SYNONYMS="<vai_tro>=' + count.most_common(1)[0][0] + '"')
    print("Vai trò dùng được: stt, item_code, item_name, unit, bid_quantity,")
    print("reference_quantity, unit_price_total, bid_amount, material, brand, origin, note")
