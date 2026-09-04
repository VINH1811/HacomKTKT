"""Suy ra vai trò cột từ CHÍNH DỮ LIỆU, không phụ thuộc cách đặt tên tiêu đề.

Đọc cột theo từ khóa tiêu đề luôn có giới hạn: mỗi đơn vị viết một kiểu và
không có chuẩn nào cho file Excel, nên sẽ luôn gặp cách viết chưa từng thấy
("ĐGTH", "Tên vật tư", "Giá trị"...). Khi đó cả sheet bị đọc thiếu.

Bảng khối lượng lại có một quan hệ luôn đúng bất kể tiêu đề viết thế nào:

    khối lượng × đơn giá = thành tiền

Đo trên hồ sơ thật, một sheet có tới 676 dòng cùng thỏa quan hệ này — tín hiệu
đủ mạnh để tin. Module dùng nó theo hướng an toàn: KHÔNG thay thế cách đọc tiêu
đề, chỉ (1) điền vào những cột tiêu đề không nhận ra, và (2) báo khi cách đọc
theo tiêu đề mâu thuẫn với chính số liệu trong file.

Đơn vị tính thì không có quan hệ toán học, nhưng lại thuộc một TẬP ĐÓNG rất nhỏ
(m, m2, cái, bộ, kg...) nên nhận theo giá trị cũng đủ chắc.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from .env_config import env_float, env_int, env_terms
from .number_parser import parse_number
from .text_normalizer import strip_accents

# Sai số cho phép của phép nhân; file thật hay làm tròn tới đồng.
TOLERANCE = env_float("HSMT_INFER_TOLERANCE", 0.005, 0.0, 0.2)
# Số dòng tối thiểu cùng thỏa quan hệ mới đủ tin. Dưới ngưỡng này rất dễ trùng
# hợp ngẫu nhiên giữa vài dòng.
MIN_ROWS = env_int("HSMT_INFER_MIN_ROWS", 12, 3, 100_000)
# Tỷ lệ dòng phải thỏa thì mới coi là quan hệ thật (trên các dòng có đủ ba số).
MIN_RATIO = env_float("HSMT_INFER_MIN_RATIO", 0.70, 0.1, 1.0)

# Đơn vị tính thông dụng — tập đóng, dùng để nhận cột đơn vị khi tiêu đề trượt.
_UNITS = {
    "m", "m2", "m3", "md", "ml", "kg", "tan", "cai", "bo", "chiec", "con",
    "hop", "thung", "cuon", "binh", "qua", "vien", "tam", "cay", "goi", "lo",
    "he", "he thong", "ht", "bang", "doi", "khoi", "lit", "ong", "tui", "vi",
    "cong", "ca", "luot", "diem", "vi tri", "tram", "bo dan", "sheet",
} | env_terms("HSMT_UNIT_VOCABULARY")


def _numeric_by_column(
    rows: Iterable[list[Any]], column_count: int, *, max_rows: int = 1500
) -> dict[int, dict[int, float]]:
    """Giá trị số theo từng cột: {cột: {chỉ số dòng: giá trị}}. Bỏ qua số 0."""
    result: dict[int, dict[int, float]] = {}
    for index, row in enumerate(rows):
        if index >= max_rows:
            break
        for col in range(column_count):
            if col >= len(row):
                continue
            value = parse_number(row[col])
            if value is None or value == 0:
                continue
            result.setdefault(col, {})[index] = float(value)
    return result


def _relation_hits(
    a: dict[int, float], b: dict[int, float], c: dict[int, float]
) -> tuple[int, int]:
    """(số dòng thỏa a*b=c, số dòng có đủ ba giá trị)."""
    shared = a.keys() & b.keys() & c.keys()
    if not shared:
        return 0, 0
    hits = sum(
        1 for i in shared
        if abs(a[i] * b[i] - c[i]) <= TOLERANCE * max(abs(c[i]), 1.0)
    )
    return hits, len(shared)


def find_quantity_price_amount(
    rows: Iterable[list[Any]],
    column_count: int,
    *,
    known_quantity: Optional[int] = None,
    known_price: Optional[int] = None,
    known_amount: Optional[int] = None,
    exclude: Optional[set[int]] = None,
) -> Optional[tuple[tuple[int, int, int], int, int]]:
    """Tìm bộ ba cột (khối lượng, đơn giá, thành tiền) thỏa phép nhân.

    Cột nào đã biết từ tiêu đề thì truyền vào để neo phép tìm, vừa nhanh vừa
    tránh chọn nhầm sang cặp "KL mời thầu × đơn giá" khi file có cả hai.

    Trả về ((cột KL, cột ĐG, cột TT), số dòng thỏa, số dòng xét) hoặc None.
    """
    data = list(rows)
    numeric = _numeric_by_column(data, column_count)
    if len(numeric) < 3:
        return None
    banned = set(exclude or ())

    def options(known: Optional[int]) -> list[int]:
        if known is not None:
            return [known] if known in numeric else []
        return [c for c in numeric if c not in banned]

    best: Optional[tuple[tuple[int, int, int], int, int]] = None
    for q in options(known_quantity):
        for p in options(known_price):
            if p == q:
                continue
            for amount in options(known_amount):
                if amount in (q, p):
                    continue
                hits, total = _relation_hits(numeric[q], numeric[p], numeric[amount])
                if hits < MIN_ROWS or not total or hits / total < MIN_RATIO:
                    continue
                # Nhiều dòng thỏa hơn thì chắc hơn; hòa thì lấy cột bên phải,
                # vì cột của nhà thầu thường nằm sau cột mời thầu.
                key = (hits, q + p + amount)
                if best is None or key > (best[1], sum(best[0])):
                    best = ((q, p, amount), hits, total)
    return best


def looks_like_unit_column(values: Iterable[Any], *, min_ratio: float = 0.6) -> bool:
    """Cột có phần lớn giá trị nằm trong tập đơn vị tính thông dụng."""
    seen = [strip_accents(str(v)).strip().lower() for v in values if str(v or "").strip()]
    if len(seen) < 5:
        return False
    return sum(1 for v in seen if v in _UNITS) / len(seen) >= min_ratio


def find_unit_column(
    rows: Iterable[list[Any]], column_count: int, *, exclude: Optional[set[int]] = None
) -> Optional[int]:
    """Cột đơn vị tính, nhận theo giá trị thay vì theo tiêu đề."""
    data = [row for row in rows][:400]
    banned = set(exclude or ())
    for col in range(column_count):
        if col in banned:
            continue
        if looks_like_unit_column(row[col] for row in data if col < len(row)):
            return col
    return None
