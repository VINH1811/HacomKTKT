from __future__ import annotations

from collections import defaultdict

from core.text_normalizer import normalize_text, strip_accents

from .models import OCRTable


FIELD_LABELS = {
    "stt": "STT",
    "item_code": "Mã hiệu",
    "item_name": "Mô tả công việc mời thầu",
    "unit": "ĐVT",
    "invited_quantity": "Khối lượng theo KLMT",
    "bid_quantity": "Khối lượng nhà thầu chào",
    "material": "Mô tả quy cách",
    "product_code": "Mã hiệu/Model",
    "brand": "Thương hiệu",
    "origin": "Xuất xứ",
    "main_material": "VL chính",
    "aux_material": "VL phụ",
    "labor_machine": "NC & máy TC",
    "management_cost": "CP quản lý",
    "profit": "Lợi nhuận",
    "unit_price": "Đơn giá tổng hợp",
    "amount_invited": "Thành tiền theo KLMT",
    "amount_bid": "Thành tiền nhà thầu chào",
    "note": "Ghi chú",
}

NUMERIC_FIELDS = {
    "invited_quantity", "bid_quantity", "main_material", "aux_material",
    "labor_machine", "management_cost", "profit", "unit_price",
    "amount_invited", "amount_bid",
}

HEADER_PATTERNS: dict[str, tuple[str, ...]] = {
    "stt": ("stt", "so thu tu"),
    "item_code": ("ma cong tac", "ma hieu cong viec"),
    "item_name": ("mo ta cong viec moi thau", "noi dung cong viec", "dien giai", "ten hang muc"),
    "unit": ("dvt", "don vi tinh"),
    "invited_quantity": ("khoi luong theo hscg", "khoi luong theo klmt", "khoi luong moi thau"),
    "bid_quantity": ("khoi luong nha thau chao", "khoi luong nha thau"),
    "material": ("mo ta quy cach", "vat tu quy cach", "thong tin vat lieu"),
    "product_code": ("ma hieu model", "ma hieu quy cach", "model"),
    "brand": ("thuong hieu", "nhan hieu", "hang san xuat"),
    "origin": ("xuat xu", "nuoc san xuat"),
    "main_material": ("vl chinh", "vat lieu chinh"),
    "aux_material": ("vl phu", "vat lieu phu"),
    "labor_machine": ("nc may tc", "nhan cong may", "nc va may"),
    "management_cost": ("cp quan ly", "chi phi quan ly"),
    "profit": ("loi nhuan",),
    "unit_price": ("don gia tong hop", "don gia du thau", "don gia"),
    "amount_invited": ("thanh tien theo klmt", "thanh tien theo hscg"),
    "amount_bid": ("thanh tien nha thau chao",),
    "note": ("ghi chu",),
}

# Biểu 03.2 thực tế thường có 15, 18 hoặc 19 cột. Các map này chỉ được
# dùng khi OCR tiêu đề không đủ tin cậy.
POSITIONAL_SCHEMAS: dict[int, list[str]] = {
    15: [
        "stt", "item_name", "unit", "invited_quantity", "bid_quantity",
        "material", "origin", "main_material", "aux_material", "labor_machine",
        "management_cost", "profit", "unit_price", "amount_bid", "note",
    ],
    18: [
        "stt", "item_name", "unit", "invited_quantity", "bid_quantity",
        "material", "product_code", "brand", "origin", "main_material",
        "aux_material", "labor_machine", "management_cost", "profit",
        "unit_price", "amount_invited", "amount_bid", "note",
    ],
    19: [
        "stt", "item_code", "item_name", "unit", "invited_quantity",
        "bid_quantity", "material", "product_code", "brand", "origin",
        "main_material", "aux_material", "labor_machine", "management_cost",
        "profit", "unit_price", "amount_invited", "amount_bid", "note",
    ],
}


def infer_header_rows(table: OCRTable) -> int:
    heights = [table.y_lines[i + 1] - table.y_lines[i] for i in range(len(table.y_lines) - 1)]
    if len(heights) <= 2:
        return 1
    median = sorted(heights)[len(heights) // 2]

    # Bảng BOQ 15-19 cột thường có 3-4 tầng tiêu đề. Một số scan làm hai
    # dòng đầu bị tách rất mỏng, sau đó mới đến hai dòng tiêu đề cao. Không
    # được dừng ngay ở dòng mỏng thứ hai như thuật toán cũ.
    if table.n_cols >= 15:
        tall = [
            index for index, height in enumerate(heights[:6])
            if height >= median * 1.35
        ]
        early_tall = [index for index in tall if index <= 3]
        if early_tall:
            return max(2, min(max(early_tall) + 1, 5))

    header = 1
    for index, height in enumerate(heights[:6]):
        if index == 0 or height >= median * 1.10:
            header = index + 1
        else:
            break
    return max(1, min(header, 5))


def _header_by_col(table: OCRTable) -> dict[int, str]:
    by_col: dict[int, list[str]] = defaultdict(list)
    for cell in table.cells:
        if cell.row < table.header_rows and cell.text:
            by_col[cell.col].append(cell.text)
    result: dict[int, str] = {}
    inherited = ""
    for col in range(table.n_cols):
        raw = " ".join(by_col.get(col, []))
        if raw.strip():
            inherited = raw
        # Kế thừa nhãn nhóm của ô gộp theo chiều ngang, nhưng vẫn giữ nhãn con.
        combined = f"{inherited} {raw}" if raw else inherited
        result[col] = strip_accents(normalize_text(combined))
    return result


def _pattern_score(header: str, pattern: str) -> int:
    if not header or not pattern:
        return 0
    if pattern == header:
        return 100
    if pattern in header:
        return 70 + min(len(pattern), 25)
    words = set(header.split())
    target = set(pattern.split())
    if not target:
        return 0
    overlap = len(words & target) / len(target)
    return int(overlap * 55) if overlap >= 0.65 else 0


def infer_header_fields(table: OCRTable) -> dict[int, str]:
    """Chỉ ánh xạ các cột có bằng chứng từ nội dung tiêu đề OCR.

    Không dùng schema vị trí ở bước này. Hàm được dùng để chấm chiều trang;
    nếu dùng positional schema, cả chữ đúng và chữ lộn ngược đều có thể nhận
    đủ 19 trường và làm sai quyết định xoay.
    """
    headers = _header_by_col(table)
    candidates: list[tuple[int, int, str]] = []
    for col, header in headers.items():
        for field, patterns in HEADER_PATTERNS.items():
            score = max((_pattern_score(header, pattern) for pattern in patterns), default=0)
            if score:
                candidates.append((score, col, field))

    candidates.sort(key=lambda item: (-item[0], item[1]))
    mapping: dict[int, str] = {}
    used: set[str] = set()
    for score, col, field in candidates:
        if col not in mapping and field not in used:
            mapping[col] = field
            used.add(field)
    return mapping


def infer_columns(table: OCRTable) -> dict[int, str]:
    mapping = infer_header_fields(table)
    used: set[str] = set(mapping.values())
    positional = POSITIONAL_SCHEMAS.get(table.n_cols)
    if positional:
        for col, field in enumerate(positional):
            if col not in mapping and field not in used:
                mapping[col] = field
                used.add(field)

    # Khôi phục thận trọng cho bảng lạ: cột mô tả là cột rộng nhất ở nửa trái;
    # các cột tiền nằm phía phải.
    widths = [table.x_lines[i + 1] - table.x_lines[i] for i in range(max(table.n_cols, 0))]
    if table.n_cols and "item_name" not in used:
        left = range(0, max(1, min(table.n_cols, table.n_cols // 2 + 2)))
        col = max(left, key=lambda index: widths[index])
        if col not in mapping:
            mapping[col] = "item_name"
            used.add("item_name")
    if table.n_cols and "unit" not in used:
        free_left = [i for i in range(min(table.n_cols, 7)) if i not in mapping]
        if free_left:
            col = min(free_left, key=lambda index: widths[index])
            mapping[col] = "unit"
            used.add("unit")

    right_fields = [
        "amount_bid", "amount_invited", "unit_price", "profit",
        "management_cost", "labor_machine", "aux_material", "main_material",
    ]
    free_right = [i for i in range(table.n_cols - 1, max(-1, table.n_cols - 10), -1) if i not in mapping]
    for field, col in zip((f for f in right_fields if f not in used), free_right):
        mapping[col] = field
        used.add(field)

    table.column_fields = mapping
    return mapping


def is_numeric_field(field: str) -> bool:
    return field in NUMERIC_FIELDS


def label_for(field: str) -> str:
    return FIELD_LABELS.get(field, field)
