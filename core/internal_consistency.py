"""Kiểm tra tính nhất quán NỘI BỘ trong một hồ sơ chào giá.

Các phép so sánh khác của hệ thống đều cần ít nhất hai tài liệu: hồ sơ nhà thầu
với phụ lục, hoặc nhà thầu này với nhà thầu kia. Module này chỉ nhìn vào MỘT hồ
sơ và trả lời câu hỏi: trong chính hồ sơ đó, cùng một hạng mục có được chào cùng
một đơn giá ở mọi nơi không?

Chào lệch giá cho cùng hạng mục là dấu hiệu điển hình của việc sao chép giữa các
sheet rồi sửa sót, hoặc chào giá không nhất quán. Trường hợp một nhà thầu duy
nhất thì đây là phép kiểm tra giá duy nhất còn dùng được, vì không có ai để so
ngang.

Mức độ được phân biệt theo phạm vi:
- Cùng một sheet: gần như chắc chắn là sai sót -> CẢNH BÁO.
- Khác sheet: có thể hợp lý (khác vị trí lắp đặt, khác điều kiện thi công)
  -> CẦN KIỂM TRA, không kết luận thay người dùng.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from statistics import median

from .models import ItemRecord, Severity
from .text_normalizer import strip_accents

def _env_float(name: str, default: float, low: float, high: float) -> float:
    try:
        return max(low, min(high, float(os.getenv(name, str(default)))))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(os.getenv(name, str(default)))))
    except (TypeError, ValueError):
        return default


def _env_terms(name: str) -> set[str]:
    """Từ vựng bổ sung do người dùng khai báo, phân tách bằng dấu phẩy."""
    raw = os.getenv(name, "")
    return {term.strip().lower() for term in raw.split(",") if term.strip()}


# Bỏ qua chênh lệch nhỏ hơn ngưỡng này — thường chỉ là làm tròn khi lập bảng.
DEFAULT_TOLERANCE_PCT = _env_float("HSMT_PRICE_CONSISTENCY_TOLERANCE", 0.005, 0.0, 1.0)
# Nhóm quá lớn thường là hạng mục gộp chung tên ("Đầu vào:", "Đầu ra:") chứ không
# phải cùng một thứ hàng; liệt kê ra chỉ gây nhiễu.
MAX_GROUP_SIZE = _env_int("HSMT_PRICE_CONSISTENCY_MAX_GROUP", 40, 2, 10_000)


@dataclass
class PriceOccurrence:
    """Một lần hạng mục xuất hiện kèm đơn giá."""
    sheet: str
    row_number: int
    item_name: str
    unit_price: float


@dataclass
class PriceInconsistency:
    """Một hạng mục được chào nhiều mức giá khác nhau trong cùng một hồ sơ."""
    key_label: str                     # mã hiệu, hoặc tên hạng mục nếu không có mã
    matched_by: str                    # "mã hiệu" | "tên hạng mục"
    occurrences: list[PriceOccurrence] = field(default_factory=list)

    @property
    def prices(self) -> list[float]:
        return [o.unit_price for o in self.occurrences]

    @property
    def min_price(self) -> float:
        return min(self.prices)

    @property
    def max_price(self) -> float:
        return max(self.prices)

    @property
    def median_price(self) -> float:
        return float(median(self.prices))

    @property
    def spread_pct(self) -> float:
        """Chênh lệch cao nhất so với thấp nhất, tính trên mức thấp nhất."""
        low = self.min_price
        if low <= 0:
            return 1.0 if self.max_price > 0 else 0.0
        return (self.max_price - low) / low

    @property
    def sheets(self) -> list[str]:
        return sorted({o.sheet for o in self.occurrences})

    @property
    def same_sheet(self) -> bool:
        return len(self.sheets) == 1

    @property
    def severity(self) -> Severity:
        return Severity.WARNING if self.same_sheet else Severity.REVIEW

    def describe(self, max_rows: int = 6) -> str:
        """Câu mô tả đủ để chuyên viên mở file kiểm lại đúng dòng."""
        shown = sorted(self.occurrences, key=lambda o: (o.sheet, o.row_number))[:max_rows]
        detail = "; ".join(
            f"{o.sheet}!dòng {o.row_number}: {o.unit_price:,.0f}" for o in shown
        )
        if len(self.occurrences) > max_rows:
            detail += f"; ... (+{len(self.occurrences) - max_rows} dòng nữa)"
        scope = "cùng sheet" if self.same_sheet else f"{len(self.sheets)} sheet khác nhau"
        return (
            f"Cùng hạng mục nhưng chào nhiều đơn giá khác nhau "
            f"({self.matched_by}: {self.key_label}) — chênh {self.spread_pct:.1%} "
            f"[{self.min_price:,.0f} … {self.max_price:,.0f}], {scope}. Chi tiết: {detail}"
        )


# Đơn vị "trọn gói": mỗi dòng là một phạm vi công việc riêng nên đơn giá khác
# nhau là bình thường, không so được với nhau. normalize_unit giữ nguyên dấu
# tiếng Việt nên phải bỏ dấu trước khi đối chiếu danh sách này.
# Ngành khác có đơn vị trọn gói riêng thì khai báo thêm qua biến môi trường
# HSMT_LUMP_SUM_UNITS (danh sách cách nhau bằng dấu phẩy, không dấu).
_LUMP_SUM_UNITS = {
    "lo", "goi", "he thong", "ht", "tron goi", "tron bo", "hm", "khoan", "tt",
} | _env_terms("HSMT_LUMP_SUM_UNITS")

# Mã hiệu thật là mã kỹ thuật (GST852RP, DI-M9102+DB-M01, AF.32317). Chuỗi có
# dấu tiếng Việt hoặc khoảng trắng thường là ghi chú bị đọc nhầm vào cột mã
# ("CĐT cấp", "Chủ đầu tư cấp"), không dùng để gom nhóm được.
_CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-_./+*]{1,}$")


def _is_usable_code(code: str) -> bool:
    if not _CODE_PATTERN.match(code.strip()):
        return False
    # Mã toàn số 0 hoặc một chữ số là ô trống bị điền cho có.
    return code.strip("0.-") != ""


def _is_generic_name(name: str) -> bool:
    """Tên mang tính tiêu đề/nhóm chứ không phải một món hàng cụ thể."""
    text = name.strip()
    if len(text) < 12:
        return True
    # "HỆ THỐNG ĐIỆN", "PHẦN NGẦM" — viết hoa toàn bộ là quy ước đặt tiêu đề mục.
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and all(c.isupper() for c in letters)


def _group_key(item: ItemRecord) -> tuple[str, str, str] | None:
    """Khóa gom nhóm: ưu tiên mã hiệu, không có mã thì dùng tên + đơn vị.

    Kèm đơn vị để không gộp nhầm hai cách tính khác nhau của cùng một tên gọi
    (ví dụ tính theo mét và tính theo bộ).
    """
    unit = item.normalized_unit or ""
    if strip_accents(unit).strip() in _LUMP_SUM_UNITS:
        return None
    name = item.normalized_name or ""
    if item.normalized_code and _is_usable_code(item.item_code or item.normalized_code):
        # Phải khớp CẢ mã lẫn tên. Trong hồ sơ cơ điện, một mã định mức thường
        # dùng chung cho nhiều quy cách vật tư (mã tôn Z08-1.15 dùng cho mọi cỡ
        # ống gió), nên chỉ khớp mã thôi thì đơn giá khác nhau là chuyện bình thường.
        return ("mã hiệu", f"{item.normalized_code}|{name}", unit)
    if name and not _is_generic_name(item.item_name or ""):
        # Tên rút gọn kiểu "KT: 1500x500" chỉ có nghĩa trong ngữ cảnh mục cha,
        # nên kèm đường dẫn nhóm để không gộp hai thứ khác nhau.
        return ("tên hạng mục", f"{name}|{item.normalized_path}", unit)
    return None


def find_price_inconsistencies(
    items: list[ItemRecord],
    *,
    tolerance_pct: float = DEFAULT_TOLERANCE_PCT,
) -> list[PriceInconsistency]:
    """Tìm các hạng mục bị chào nhiều mức đơn giá khác nhau trong cùng hồ sơ."""
    groups: dict[tuple[str, str, str], list[ItemRecord]] = defaultdict(list)
    for item in items:
        if not item.is_comparable:
            continue
        price = item.unit_price_total
        if price is None or price <= 0:
            continue
        key = _group_key(item)
        if key is not None:
            groups[key].append(item)

    found: list[PriceInconsistency] = []
    for (matched_by, key_value, _unit), members in groups.items():
        if not 1 < len(members) <= MAX_GROUP_SIZE:
            continue
        prices = [m.unit_price_total for m in members]
        low, high = min(prices), max(prices)
        if low <= 0:
            continue
        if (high - low) / low <= tolerance_pct:
            continue

        first = members[0]
        label = f"{first.item_code} – {first.item_name}" if matched_by == "mã hiệu" else first.item_name
        found.append(PriceInconsistency(
            key_label=str(label)[:80],
            matched_by=matched_by,
            occurrences=[
                PriceOccurrence(
                    sheet=m.sheet,
                    row_number=m.row_number,
                    item_name=m.item_name,
                    unit_price=float(m.unit_price_total),
                )
                for m in members
            ],
        ))

    # Chênh lệch lớn nhất lên đầu để người rà soát xử lý theo mức nghiêm trọng.
    found.sort(key=lambda g: -g.spread_pct)
    return found


def annotate_price_inconsistencies(
    items: list[ItemRecord],
    *,
    tolerance_pct: float = DEFAULT_TOLERANCE_PCT,
    max_warnings: int = 60,
) -> list[str]:
    """Gắn cờ chất lượng dữ liệu lên từng dòng liên quan và trả về danh sách cảnh báo."""
    issues = find_price_inconsistencies(items, tolerance_pct=tolerance_pct)
    if not issues:
        return []

    by_position: dict[tuple[str, int], ItemRecord] = {
        (item.sheet, item.row_number): item for item in items
    }
    warnings: list[str] = []
    for issue in issues:
        message = issue.describe()
        for occurrence in issue.occurrences:
            item = by_position.get((occurrence.sheet, occurrence.row_number))
            if item is not None and message not in item.data_quality_flags:
                item.data_quality_flags.append(message)
        if len(warnings) < max_warnings:
            warnings.append(message)

    remaining = len(issues) - len(warnings)
    if remaining > 0:
        warnings.append(
            f"Còn {remaining} hạng mục khác cũng bị chào nhiều đơn giá; "
            f"xem đầy đủ ở sheet Chất lượng dữ liệu trong báo cáo."
        )
    return warnings
