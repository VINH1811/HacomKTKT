"""Nhật ký tiêu đề cột chưa nhận diện được — để mở rộng sổ tay từ khóa.

File Excel không có chuẩn nào, mỗi đơn vị đặt tên cột một kiểu, nên sẽ luôn gặp
cách viết chưa từng thấy. Mỗi lần như vậy hệ thống ghi lại tiêu đề đó cùng vài
đặc trưng của dữ liệu bên dưới, để định kỳ xem lại và bổ sung vào sổ tay
(HSMT_COLUMN_SYNONYMS) mà không phải chờ người dùng báo lỗi.

Ghi gì:
- Tiêu đề cột đọc được và tên sheet.
- Cột CHỮ: vài giá trị mẫu ngắn ("cái", "m2", "GST") — chính là thứ giúp nhận ra
  đó là cột đơn vị tính hay thương hiệu.
- Cột SỐ: chỉ ghi ĐẶC TRƯNG (số chữ số, tỷ lệ dòng có giá trị, có phần thập phân
  không). Với việc phân loại cột thì "6-7 chữ số, 92% dòng có giá trị" nói được
  nhiều hơn là bản thân con số, mà lại không lưu đơn giá của nhà thầu vào nhật ký.

Chạy hoàn toàn ở phía máy chủ, không hiện gì trên giao diện. Mọi lỗi khi ghi
đều bị nuốt: nhật ký hỏng không bao giờ được phép làm hỏng một lần chấm thầu.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from .env_config import env_bool, env_int
from .number_parser import parse_number

ENABLED = env_bool("HSMT_HEADER_LOG", True)
LOG_PATH = os.getenv("HSMT_HEADER_LOG_PATH", "runtime/header_log.jsonl")
# Số giá trị mẫu giữ lại cho mỗi cột chữ.
SAMPLE_COUNT = env_int("HSMT_HEADER_LOG_SAMPLES", 5, 0, 50)
# Giá trị dài hơn ngưỡng này là mô tả hạng mục, không giúp nhận dạng cột mà chỉ
# làm nhật ký phình ra — cắt bớt.
MAX_SAMPLE_LEN = env_int("HSMT_HEADER_LOG_SAMPLE_LEN", 40, 5, 200)
MAX_FILE_MB = env_int("HSMT_HEADER_LOG_MAX_MB", 20, 1, 1000)

_LOCK = threading.Lock()


def _digits(value: float) -> int:
    return len(str(abs(int(value)))) if abs(value) >= 1 else 0


def _profile_column(values: list[Any]) -> dict[str, Any]:
    """Đặc trưng đủ để phân loại vai trò cột, không giữ số liệu nhạy cảm."""
    texts = [str(v).strip() for v in values if str(v or "").strip()]
    if not texts:
        return {"kieu": "trong", "so_dong_co_gia_tri": 0}

    numbers = [parse_number(v) for v in texts]
    numbers = [float(n) for n in numbers if n is not None]
    is_numeric = len(numbers) >= max(1, int(len(texts) * 0.8))

    profile: dict[str, Any] = {
        "so_dong_co_gia_tri": len(texts),
        "so_gia_tri_khac_nhau": len({t.lower() for t in texts}),
        "do_dai_trung_binh": round(sum(len(t) for t in texts) / len(texts), 1),
    }
    if is_numeric and numbers:
        magnitudes = sorted(_digits(n) for n in numbers)
        profile.update({
            "kieu": "so",
            "so_chu_so_it_nhat": magnitudes[0],
            "so_chu_so_nhieu_nhat": magnitudes[-1],
            "co_phan_thap_phan": any(abs(n - int(n)) > 1e-9 for n in numbers),
        })
    else:
        # Cột chữ: giữ vài giá trị NGẮN làm mẫu. "cái", "m2", "GST" chính là
        # thứ cho biết đây là cột đơn vị tính hay thương hiệu.
        seen: list[str] = []
        for text in texts:
            if len(text) <= MAX_SAMPLE_LEN and text not in seen:
                seen.append(text)
            if len(seen) >= SAMPLE_COUNT:
                break
        profile.update({"kieu": "chu", "gia_tri_mau": seen})
    return profile


def _column_values(rows: Iterable[list[Any]], column: int, limit: int = 300) -> list[Any]:
    out: list[Any] = []
    for index, row in enumerate(rows):
        if index >= limit:
            break
        if column < len(row):
            out.append(row[column])
    return out


def record_unknown_headers(
    *,
    workbook: str,
    sheet: str,
    flat_headers: list[str],
    mapped_columns: Iterable[int],
    rows: Iterable[list[Any]],
    log_path: Optional[str] = None,
) -> None:
    """Ghi lại các cột có tiêu đề nhưng không khóa nào nhận.

    Không bao giờ ném lỗi ra ngoài: nhật ký chỉ là công cụ phụ.
    """
    if not ENABLED:
        return
    try:
        mapped = set(mapped_columns)
        data = list(rows)
        entries = []
        for column, raw in enumerate(flat_headers):
            header = str(raw or "").replace("\n", " ").strip()
            if column in mapped or not header:
                continue
            entries.append({
                "cot": column + 1,
                "tieu_de": header[:120],
                **_profile_column(_column_values(data, column)),
            })
        if not entries:
            return

        path = Path(log_path or LOG_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "thoi_diem": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "workbook": Path(workbook).name[:150],
            "sheet": sheet[:80],
            "cot_chua_nhan_ra": entries,
        }
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with _LOCK:
            if path.exists() and path.stat().st_size > MAX_FILE_MB * 1024 * 1024:
                # Đầy thì xoay vòng, giữ lại đúng một bản trước đó.
                path.replace(path.with_suffix(path.suffix + ".1"))
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(line)
    except Exception:
        # Nhật ký hỏng không được phép làm hỏng một lần chấm thầu.
        pass
