from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from rapidfuzz import fuzz

from .config import EnterpriseConfig
from .excel_io import read_workbook_matrices
from .models import ItemRecord, MaterialRequirement
from .text_normalizer import normalize_name, normalize_text, strip_accents

_SPLIT = re.compile(r"\s*/\s*|\s*;\s*|\s*,\s*")
_DASH = re.compile(r"\s+-\s+")

_STOPWORDS = {
    "he", "thong", "vat", "tu", "thiet", "bi", "cung", "cap", "lap", "dat",
    "va", "cua", "cho", "phan", "loai", "don", "vi", "san", "xuat", "phu", "kien",
}

# Hints are intentionally domain-oriented, but they are only a bonus. The lexical
# score still controls matching so the reader remains usable for other projects.
_CATEGORY_HINTS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("tu dien ha the",), ("tu dien", "msb", "mdb", "db", "ha the")),
    (("thiet bi dong cat tu dien ha the",), ("mccb", "acb", "mcb", "rcbo", "elcb", "dong cat")),
    (("thiet bi dong cat tu dien can ho",), ("mcb", "rcbo", "elcb", "tu can ho", "aptomat")),
    (("day cap ha the", "he thong day cap ha the"), ("cap", "cable", "xlpe", "pvc", "fr", "cu/")),
    (("busway",), ("busway", "busduct", "thanh dan dien")),
    (("den chieu sang",), ("den", "lighting", "led")),
    (("cong tac o cam",), ("cong tac", "o cam", "switch", "socket")),
    (("ong luon day dien pvc", "ong luon day pvc"), ("ong", "pvc", "luon day", "conduit")),
    (("thang mang cap",), ("thang cap", "mang cap", "trunking", "ladder", "cable tray")),
    (("kim thu set",), ("kim thu set", "lightning rod", "tia tien dao")),
    (("coc tiep dia",), ("coc tiep dia", "tiep dia", "ground rod")),
    (("bom cap nuoc",), ("bom", "pump", "cap nuoc")),
    (("ong thoat nuoc upvc",), ("upvc", "thoat nuoc")),
    (("ong cap nuoc ppr",), ("ppr", "cap nuoc")),
    (("ong thep",), ("ong thep", "steel pipe")),
    (("van va phu kien",), ("van", "valve", "phu kien")),
    (("binh nong lanh",), ("binh nong lanh", "water heater")),
    (("dong ho nuoc",), ("dong ho nuoc", "water meter")),
    (("be nuoc mai",), ("be nuoc", "bon nuoc", "tank")),
    (("dieu hoa vrv",), ("vrv", "vrf", "dieu hoa")),
    (("dieu hoa cuc bo",), ("dieu hoa cuc bo", "split", "cassette")),
    (("ong dong dieu hoa",), ("ong dong", "copper pipe", "refrigerant")),
    (("ong nuoc ngung dieu hoa",), ("nuoc ngung", "condensate")),
    (("quat thong gio",), ("quat", "fan", "thong gio")),
    (("ong gio",), ("ong gio", "duct")),
    (("mieng gio van gio",), ("mieng gio", "van gio", "grille", "damper", "diffuser")),
    (("bao on ong dong",), ("bao on", "insulation", "ong dong", "nuoc ngung")),
    (("bao on ong gio",), ("bao on", "insulation", "ong gio")),
    (("ngan chay", "chen bit ngan chay"), ("ngan chay", "firestop", "chen bit")),
)

_ASIA = {
    "asia", "chau a", "vn", "viet nam", "vietnam", "china", "trung quoc", "taiwan", "dai loan",
    "thailand", "thai lan", "japan", "nhat ban", "korea", "han quoc", "malaysia", "singapore",
    "india", "an do", "indonesia", "philippines", "turkey", "tho nhi ky",
}
_EU = {
    "eu", "europe", "chau au", "spain", "tay ban nha", "germany", "duc", "france", "phap",
    "italy", "y", "netherlands", "ha lan", "belgium", "bi", "austria", "ao", "poland", "ba lan",
}
_USA = {"usa", "us", "united states", "my", "hoa ky"}


def _n(value: object) -> str:
    return strip_accents(normalize_text(str(value or "")))


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", _n(value)) if len(token) > 1 and token not in _STOPWORDS}


def _split_requirement(text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    clean = str(text or "").strip()
    if not clean:
        return (), ()
    parts = _DASH.split(clean, maxsplit=1)
    brands_text = parts[0]
    origins_text = parts[1] if len(parts) > 1 else ""
    brands = tuple(x.strip() for x in _SPLIT.split(brands_text) if x.strip())
    origins = tuple(x.strip() for x in _SPLIT.split(origins_text) if x.strip())
    return brands, origins


def _sheet_project_text(rows: list[list[object]], limit_rows: int = 6, limit_cols: int = 10) -> str:
    values: list[str] = []
    for row in rows[:limit_rows]:
        values.extend(str(v) for v in row[:limit_cols] if v not in (None, ""))
    return _n(" ".join(values))


def _cell(rows: list[list[object]], row_idx: int, col_idx: int) -> object:
    r = row_idx - 1
    c = col_idx - 1
    if r < 0 or r >= len(rows) or c < 0 or c >= len(rows[r]):
        return None
    return rows[r][c]


def _find_header(rows: list[list[object]]) -> Optional[tuple[int, int, int, int, Optional[int]]]:
    for row_idx in range(1, min(len(rows), 40) + 1):
        row = rows[row_idx - 1]
        values = [_n(row[col] if col < len(row) else None) for col in range(min(max(len(row), 1), 40))]
        item_col = next((i + 1 for i, v in enumerate(values) if "vat tu" in v and "thuong hieu" not in v), None)
        req_cols = [i + 1 for i, v in enumerate(values) if "thuong hieu" in v or ("xuat xu" in v and "vat tu" not in v)]
        if item_col and req_cols:
            req_col = next((c for c in req_cols if c > item_col), req_cols[0])
            stt_col = next((i + 1 for i, v in enumerate(values) if re.search(r"\bstt\b", v)), max(1, item_col - 1))
            note_col = next((i + 1 for i, v in enumerate(values) if "ghi chu" in v), None)
            return row_idx, stt_col, item_col, req_col, note_col
    return None


def load_pl2_requirements(
    path: str | Path,
    *,
    project_keywords: Iterable[str] = ("hacom", "mall"),
    config: EnterpriseConfig | None = None,
) -> tuple[list[MaterialRequirement], list[str]]:
    """Load official PL02 requirements with Calamine-first reading."""
    path = Path(path)
    if path.suffix.lower() != ".xlsx":
        raise ValueError("Phụ lục 02 phải là file .xlsx")
    try:
        with open(path, "rb") as f:
            header = f.read(8)
            if header == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
                f.seek(0)
                content = f.read(512 * 1024)
                if b"E\x00n\x00c\x00r\x00y\x00p\x00t\x00e\x00d\x00P\x00a\x00c\x00k\x00a\x00g\x00e" in content:
                    raise ValueError("File bị khóa hoặc bảo vệ bằng mật khẩu. Vui lòng gỡ bỏ mật khẩu trước khi tải lên.")
                else:
                    raise ValueError("Hệ thống nhận file .xlsx. Hãy Save As file .xls/.xlsb thành .xlsx trước khi chạy.")
    except Exception as e:
        if "mật khẩu" in str(e) or "Hệ thống nhận file" in str(e):
            raise
    config = config or EnterpriseConfig.from_env()
    keywords = tuple(_n(x) for x in project_keywords if str(x).strip())
    matrices = read_workbook_matrices(
        path,
        engine=config.excel_read_engine,
        max_rows=config.max_excel_rows,
        fallback_openpyxl=config.excel_fallback_openpyxl,
    )
    if not matrices.sheets or all(len(sheet.rows) == 0 for sheet in matrices.sheets):
        raise ValueError(f"File Phụ lục 02 '{path.name}' không có dữ liệu dòng hàng để đối chiếu. Vui lòng kiểm tra lại.")
    requirements: list[MaterialRequirement] = []
    warnings: list[str] = list(matrices.warnings)
    for sheet in matrices.sheets:
        rows = sheet.rows
        project_text = _sheet_project_text(rows)
        if keywords and project_text and not any(k in project_text for k in keywords):
            if "du an" in project_text and "hacom" not in project_text and "mall" not in project_text:
                warnings.append(f"Bỏ qua sheet '{sheet.name}' vì thuộc dự án khác")
                continue
        header = _find_header(rows)
        if not header:
            warnings.append(f"Sheet '{sheet.name}': không nhận diện được cột Vật tư/Thương hiệu-Xuất xứ")
            continue
        header_row, stt_col, item_col, req_col, note_col = header
        current_system = ""
        for row_idx in range(header_row + 1, len(rows) + 1):
            stt = str(_cell(rows, row_idx, stt_col) or "").strip()
            item_name = str(_cell(rows, row_idx, item_col) or "").strip()
            requirement_text = str(_cell(rows, row_idx, req_col) or "").strip()
            note = str(_cell(rows, row_idx, note_col) or "").strip() if note_col else ""
            if not item_name:
                continue
            norm_item = _n(item_name)
            if norm_item.startswith("he thong") and not requirement_text:
                current_system = item_name
                continue
            if not requirement_text or requirement_text.startswith("#"):
                continue
            brands, origins = _split_requirement(requirement_text)
            requirements.append(MaterialRequirement(
                source_sheet=sheet.name,
                source_row=row_idx,
                system=current_system,
                item_name=item_name,
                requirement_text=requirement_text,
                allowed_brands=brands,
                allowed_origins=origins,
                note=note,
                normalized_name=normalize_name(item_name),
            ))
    if not requirements:
        warnings.append("Không đọc được yêu cầu vật tư nào từ Phụ lục 02")
    warnings.append(f"PL02 được đọc bằng {matrices.engine} trong {matrices.elapsed_seconds:.3f} giây")
    return requirements, warnings

@dataclass(frozen=True, slots=True)
class _PreparedRequirement:
    requirement: MaterialRequirement
    normalized_name: str
    tokens: frozenset[str]
    system_tokens: frozenset[str]
    item_hints: tuple[str, ...]


class PL2Matcher:
    """Pre-indexed PL02 matcher reused for thousands of BOQ rows.

    Requirement normalization and tokenization are done once. This avoids
    repeating the same Python work for every bidder row. The matcher object is
    immutable after construction and can safely be called from worker threads.
    """

    def __init__(self, requirements: list[MaterialRequirement]) -> None:
        prepared: list[_PreparedRequirement] = []
        for requirement in requirements:
            normalized_name = _n(requirement.item_name)
            hints: list[str] = []
            for req_keys, item_hints in _CATEGORY_HINTS:
                if any(key in normalized_name for key in req_keys):
                    hints.extend(item_hints)
            prepared.append(_PreparedRequirement(
                requirement=requirement,
                normalized_name=normalized_name,
                tokens=frozenset(_tokens(normalized_name)),
                system_tokens=frozenset(_tokens(requirement.system)) if requirement.system else frozenset(),
                item_hints=tuple(dict.fromkeys(hints)),
            ))
        self._prepared = tuple(prepared)

    @staticmethod
    def _item_features(item: ItemRecord) -> tuple[str, frozenset[str]]:
        item_text = " | ".join(filter(None, [
            item.item_name, item.material, item.item_code, item.normalized_path,
        ]))
        normalized = _n(item_text)
        return normalized, frozenset(_tokens(normalized))

    def match(
        self,
        item: ItemRecord,
        minimum_score: float = 0.54,
    ) -> tuple[Optional[MaterialRequirement], float]:
        item_text, left = self._item_features(item)
        if not item_text:
            return None, 0.0

        best: Optional[MaterialRequirement] = None
        best_score = 0.0
        for entry in self._prepared:
            requirement_text = entry.normalized_name
            if not requirement_text:
                continue
            lexical = (
                0.35 * fuzz.WRatio(item_text, requirement_text)
                + 0.35 * fuzz.token_set_ratio(item_text, requirement_text)
                + 0.30 * fuzz.partial_ratio(item_text, requirement_text)
            ) / 100.0
            right = entry.tokens
            jaccard = len(left & right) / max(1, len(left | right))
            hint_bonus = 0.28 if entry.item_hints and any(hint in item_text for hint in entry.item_hints) else 0.0
            system_bonus = 0.05 if entry.system_tokens and left & entry.system_tokens else 0.0
            score = min(1.0, 0.72 * lexical + 0.28 * jaccard + hint_bonus + system_bonus)
            if score > best_score:
                best, best_score = entry.requirement, score

        if best_score < minimum_score:
            return None, best_score
        return best, best_score


def requirement_match_score(item: ItemRecord, requirement: MaterialRequirement) -> float:
    matcher = PL2Matcher([requirement])
    _matched, score = matcher.match(item, minimum_score=0.0)
    return score


def match_pl2_requirement(
    item: ItemRecord,
    requirements: list[MaterialRequirement],
    minimum_score: float = 0.54,
) -> tuple[Optional[MaterialRequirement], float]:
    return PL2Matcher(requirements).match(item, minimum_score=minimum_score)


def _equivalent_token(candidate: str, allowed: str) -> bool:
    c, a = _n(candidate), _n(allowed)
    if not c or not a:
        return False
    if a in c or c in a:
        return True
    return fuzz.ratio(c, a) >= 82 or fuzz.partial_ratio(c, a) >= 90


def _origin_allowed(candidate: str, allowed_values: tuple[str, ...]) -> bool:
    c = _n(candidate)
    if not c:
        return False
    for allowed in allowed_values:
        a = _n(allowed)
        if _equivalent_token(c, a):
            return True
        if a in {"asia", "chau a"} and any(token in c for token in _ASIA):
            return True
        if a in {"eu", "europe", "chau au"} and any(token in c for token in _EU):
            return True
        if a in {"usa", "us", "my", "hoa ky"} and any(token in c for token in _USA):
            return True
    return False


def evaluate_pl2_compliance(
    item: ItemRecord,
    requirement: MaterialRequirement,
) -> tuple[str, list[tuple[str, str]]]:
    """Return status and (field, message) issues.

    Outside-list brands are marked for technical review, not automatically
    rejected, because the HSYC allows equivalent-or-better alternatives.
    """
    issues: list[tuple[str, str]] = []
    req_norm = _n(requirement.requirement_text)
    if "cdt cap" in req_norm or "chu dau tu cap" in req_norm:
        return "CHỦ ĐẦU TƯ CẤP THIẾT BỊ", issues

    candidate_brand = str(item.brand or "").strip()
    candidate_origin = str(item.origin or "").strip()
    combined = " | ".join(filter(None, [candidate_brand, item.material, item.note] + [str(v) for v in item.technical_specs.values()]))

    if requirement.allowed_brands:
        brand_detected = any(_equivalent_token(combined, allowed) for allowed in requirement.allowed_brands)
        if not candidate_brand and not brand_detected:
            issues.append(("Thương hiệu", "Thiếu thương hiệu/nhà sản xuất theo yêu cầu Phụ lục 02"))
        elif candidate_brand and not brand_detected:
            issues.append((
                "Thương hiệu",
                f"Thương hiệu '{candidate_brand}' ngoài danh sách PL02 ({'/'.join(requirement.allowed_brands)}); cần chứng minh tương đương hoặc tốt hơn",
            ))

    if requirement.allowed_origins:
        origin_detected = _origin_allowed(candidate_origin or combined, requirement.allowed_origins)
        if not candidate_origin and not origin_detected:
            issues.append(("Xuất xứ", "Thiếu xuất xứ theo yêu cầu Phụ lục 02"))
        elif candidate_origin and not origin_detected:
            issues.append((
                "Xuất xứ",
                f"Xuất xứ '{candidate_origin}' khác phạm vi PL02 ({'/'.join(requirement.allowed_origins)}); cần chuyên viên xác nhận",
            ))

    if not issues:
        return "PHÙ HỢP DANH SÁCH PL02", issues
    if any("Thiếu" in message for _, message in issues):
        return "THIẾU THÔNG TIN PL02", issues
    return "CẦN THẨM ĐỊNH TƯƠNG ĐƯƠNG", issues
