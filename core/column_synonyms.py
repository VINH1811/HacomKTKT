"""Sổ tay tên cột: nhận cả viết tắt, viết sai và cách gọi chưa từng gặp.

Bộ luật từ khóa chính (``map_columns``) khớp chuỗi con nên chỉ đúng với những
cách viết đã liệt kê sẵn. Module này là lớp đỡ CUỐI CÙNG, chạy sau khi bộ luật
chính đã bó tay, và nhận thêm ba kiểu:

1. Viết tắt bằng chữ cái đầu: "ĐVT" = Đơn vị tính, "KLMT" = Khối lượng mời thầu,
   "ĐGTH" = Đơn giá tổng hợp. Đây là cách viết cực phổ biến trong hồ sơ thầu.
2. Gần giống: sai chính tả, thừa/thiếu chữ, khác thứ tự từ ("Giá đơn vị tổng").
3. Từ vựng do người dùng khai báo, không cần sửa mã:

       HSMT_COLUMN_SYNONYMS="unit_price_total=ĐG tổng,Giá TH;bid_quantity=SL chào"

Ngưỡng để chấp nhận đặt cao vì đây là lớp đoán: nhầm một cột còn tệ hơn bỏ sót,
vì bỏ sót thì hệ thống đã có cảnh báo và lớp suy luận theo số liệu đỡ tiếp.
"""

from __future__ import annotations

import os

from rapidfuzz import fuzz

from .env_config import env_float
from .text_normalizer import normalize_name, strip_accents

# Điểm tối thiểu để chấp nhận một cột theo độ gần giống.
MIN_FUZZY_SCORE = env_float("HSMT_COLUMN_FUZZY_SCORE", 88.0, 50.0, 100.0)

# Tên gọi CHUẨN của từng vai trò. Dùng để sinh viết tắt và so độ gần giống.
_CANONICAL: dict[str, tuple[str, ...]] = {
    "stt": ("Số thứ tự", "Số TT"),
    "item_code": ("Mã hiệu", "Mã công tác", "Ký hiệu", "Mã hàng", "Mã vật tư",
                  "Code", "Item code"),
    "item_name": ("Tên hạng mục", "Nội dung công việc", "Diễn giải",
                  "Mô tả công việc", "Danh mục công việc", "Tên vật tư"),
    "unit": ("Đơn vị tính", "Đơn vị"),
    "bid_quantity": ("Khối lượng nhà thầu chào", "Khối lượng chào",
                     "Khối lượng dự thầu", "Số lượng chào"),
    "reference_quantity": ("Khối lượng mời thầu", "Khối lượng theo hồ sơ mời thầu"),
    "unit_price_total": ("Đơn giá tổng hợp", "Đơn giá", "Đơn giá dự thầu",
                         "Đơn giá chào"),
    "bid_amount": ("Thành tiền", "Thành tiền nhà thầu chào", "Tổng tiền",
                   "Giá trị"),
    "reference_amount": ("Thành tiền theo khối lượng mời thầu",),
    "material": ("Mô tả quy cách", "Quy cách", "Vật tư thiết bị",
                 "Specification", "Material"),
    "brand": ("Thương hiệu", "Nhãn hiệu", "Nhãn hàng", "Hãng sản xuất",
              "Brand", "Maker", "Manufacturer"),
    "origin": ("Xuất xứ", "Nước sản xuất", "Origin", "Country of origin"),
    "note": ("Ghi chú", "Remark", "Note"),
    "price_main": ("Vật liệu chính",),
    "price_aux": ("Vật liệu phụ",),
    "price_labor": ("Nhân công và máy thi công",),
    "price_management": ("Chi phí quản lý",),
    "price_profit": ("Lợi nhuận",),
}


def _acronym(text: str) -> str:
    """Chữ cái đầu mỗi từ, đã bỏ dấu: 'Đơn giá tổng hợp' -> 'dgth'."""
    return "".join(word[0] for word in strip_accents(normalize_name(text)).split() if word)


def _compact(text: str) -> str:
    """Bỏ dấu và mọi ký tự không phải chữ/số: 'Đ.V.T' -> 'dvt'."""
    return "".join(ch for ch in strip_accents(normalize_name(text)) if ch.isalnum())


def _load_user_synonyms() -> dict[str, tuple[str, ...]]:
    """HSMT_COLUMN_SYNONYMS="vai_tro=ten1,ten2;vai_tro_khac=ten3"."""
    out: dict[str, tuple[str, ...]] = {}
    for chunk in os.getenv("HSMT_COLUMN_SYNONYMS", "").split(";"):
        if "=" not in chunk:
            continue
        field, names = chunk.split("=", 1)
        field = field.strip()
        values = tuple(n.strip() for n in names.split(",") if n.strip())
        if field and values:
            out[field] = out.get(field, ()) + values
    return out


def labels_for(field: str) -> tuple[str, ...]:
    return _CANONICAL.get(field, ()) + _load_user_synonyms().get(field, ())


def score_header(header: str, field: str) -> float:
    """Điểm 0..100 cho khả năng tiêu đề này mang vai trò ``field``."""
    header = str(header or "").strip()
    if not header:
        return 0.0
    compact = _compact(header)
    if not compact:
        return 0.0
    best = 0.0
    for label in labels_for(field):
        canonical = _compact(label)
        if not canonical:
            continue
        # Viết tắt bằng chữ cái đầu: ĐVT / KLMT / ĐGTH.
        if compact == _acronym(label) or _acronym(header) == canonical:
            return 100.0
        if compact == canonical:
            return 100.0
        best = max(best, float(fuzz.token_sort_ratio(compact, canonical)))
    return best


def guess_field(header: str, allowed: tuple[str, ...]) -> tuple[str, float] | None:
    """Vai trò khả dĩ nhất cho tiêu đề này trong số ``allowed``, kèm điểm."""
    ranked = sorted(((score_header(header, f), f) for f in allowed), reverse=True)
    if not ranked or ranked[0][0] < MIN_FUZZY_SCORE:
        return None
    # Điểm sát nhau giữa hai vai trò thì không đủ chắc để chọn.
    if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < 5.0:
        return None
    return ranked[0][1], ranked[0][0]
