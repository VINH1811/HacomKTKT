"""Dựng checklist hồ sơ TỪ CHÍNH HỒ SƠ MỜI THẦU (HSMT) do người dùng tải lên.

Chức năng checklist mặc định (`core.dossier_check.DEFAULT_CHECKLIST`) dùng bộ
12 đầu mục cố định. Module này bổ sung lựa chọn: đọc HSMT (zip/pdf/docx/xlsx),
dò xem gói thầu đó YÊU CẦU những tài liệu gì, rồi sinh checklist đúng theo yêu
cầu ấy để đối chiếu với hồ sơ nhà thầu.

Cách dò: đối chiếu văn bản HSMT với một bộ từ vựng các loại tài liệu thường gặp
trong đấu thầu. Chỉ những loại THỰC SỰ được nhắc tới trong HSMT mới vào
checklist — không suy diễn thêm. Mỗi đầu mục nhận diện được đều kèm câu trích
dẫn trong HSMT làm bằng chứng để người dùng kiểm lại.

Hạn chế: đây là dò theo từ khoá, không phải đọc hiểu. HSMT viết bằng cách diễn
đạt lạ có thể bị bỏ sót; vì vậy luôn trả kèm bằng chứng và cho phép quay về
checklist mặc định.
"""

from __future__ import annotations

import logging
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Định dạng đọc được. .doc (binary Word cũ) KHÔNG đọc được, sẽ báo rõ cho người dùng.
SUPPORTED_SUFFIXES = {".zip", ".pdf", ".docx", ".xlsx", ".xlsb", ".xls", ".txt", ".md"}

_MAX_TEXT_CHARS = 3_000_000       # chặn HSMT quá lớn làm nghẽn tiến trình
_MAX_ZIP_MEMBERS = 400


def fold(text: str) -> str:
    """Chữ thường, bỏ dấu tiếng Việt (đ -> d) — dùng chung với dossier_check."""
    text = text.replace("Đ", "D").replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower()


# --------------------------------------------------------------------------
# Đọc văn bản từ nhiều định dạng
# --------------------------------------------------------------------------

def _text_from_pdf(path: Path) -> str:
    import fitz  # PyMuPDF
    parts: list[str] = []
    with fitz.open(path) as doc:
        for page in doc:
            parts.append(page.get_text())
            if sum(map(len, parts)) > _MAX_TEXT_CHARS:
                break
    return "\n".join(parts)


def _text_from_docx(path: Path) -> str:
    """Đọc .docx bằng zipfile + regex, không cần thư viện ngoài.

    File .docx thực chất là ZIP chứa XML. Lấy word/document.xml (thân bài) cùng
    header/footer, thay thẻ xuống dòng/hết đoạn bằng '\\n' rồi bỏ mọi thẻ XML.
    """
    parts: list[str] = []
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist()
                 if re.fullmatch(r'word/(document|header\d*|footer\d*)\.xml', n)]
        names.sort(key=lambda n: (n != "word/document.xml", n))
        for name in names:
            xml = z.read(name).decode("utf-8", "ignore")
            xml = re.sub(r'</w:p>|<w:br\b[^>]*/?>', '\n', xml)
            xml = re.sub(r'</w:tc>', '\t', xml)
            parts.append(re.sub(r'<[^>]+>', '', xml))
    from html import unescape
    return unescape("\n".join(parts))


def _text_from_excel(path: Path) -> str:
    import python_calamine
    rows_text: list[str] = []
    wb = python_calamine.CalamineWorkbook.from_path(str(path))
    for sheet_name in wb.sheet_names:
        rows_text.append(f"--- {sheet_name} ---")
        for row in wb.get_sheet_by_name(sheet_name).to_python():
            cells = [str(c).strip() for c in row if c not in (None, "")]
            if cells:
                rows_text.append(" | ".join(cells))
        if sum(map(len, rows_text)) > _MAX_TEXT_CHARS:
            break
    return "\n".join(rows_text)


def _text_from_plain(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


_READERS = {
    ".pdf": _text_from_pdf,
    ".docx": _text_from_docx,
    ".xlsx": _text_from_excel,
    ".xlsb": _text_from_excel,
    ".xls": _text_from_excel,
    ".txt": _text_from_plain,
    ".md": _text_from_plain,
}


@dataclass
class ExtractedText:
    text: str
    sources: list[str]              # tên file đã đọc được
    skipped: list[str]              # file bỏ qua kèm lý do


def extract_text(path: str | Path) -> ExtractedText:
    """Đọc HSMT ra văn bản thuần. ZIP thì đọc mọi file con hỗ trợ được."""
    path = Path(path)
    parts: list[str] = []
    sources: list[str] = []
    skipped: list[str] = []

    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as z:
            members = [m for m in z.namelist() if not m.endswith("/")][:_MAX_ZIP_MEMBERS]
            tmp_dir = path.parent / f"_hsmt_extract_{path.stem}"
            tmp_dir.mkdir(exist_ok=True)
            for member in members:
                suffix = Path(member).suffix.lower()
                if suffix not in _READERS:
                    skipped.append(f"{member} (định dạng {suffix or 'không rõ'} không đọc được)")
                    continue
                try:
                    target = tmp_dir / Path(member).name
                    with z.open(member) as src, target.open("wb") as dst:
                        dst.write(src.read())
                    parts.append(_READERS[suffix](target))
                    sources.append(member)
                except Exception as exc:
                    skipped.append(f"{member} ({type(exc).__name__})")
                if sum(map(len, parts)) > _MAX_TEXT_CHARS:
                    break
    else:
        suffix = path.suffix.lower()
        reader = _READERS.get(suffix)
        if reader is None:
            hint = ("File .doc đời cũ không đọc được — hãy mở bằng Word và lưu lại "
                    "thành .docx hoặc .pdf.") if suffix == ".doc" else \
                   f"Định dạng {suffix or 'không rõ'} không hỗ trợ."
            raise ValueError(hint)
        parts.append(reader(path))
        sources.append(path.name)

    return ExtractedText("\n".join(parts)[:_MAX_TEXT_CHARS], sources, skipped)


# --------------------------------------------------------------------------
# Từ vựng các loại tài liệu thường được HSMT yêu cầu
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class DocType:
    key: str
    label: str
    hsmt_patterns: tuple[str, ...]    # dò trong văn bản HSMT (đã fold)
    file_patterns: tuple[str, ...]    # khớp tên file/thư mục của nhà thầu
    min_count: int = 1
    extensions: tuple[str, ...] = ()


VOCABULARY: tuple[DocType, ...] = (
    DocType("don_du_thau", "Đơn dự thầu / Đơn chào giá",
            (r"don\s*du\s*thau", r"don\s*chao\s*gia", r"thu\s*chao\s*gia"),
            (r"don\s*du\s*thau", r"don\s*chao\s*gia", r"thu\s*chao\s*gia")),
    DocType("bao_lanh_du_thau", "Bảo lãnh dự thầu / Bảo đảm dự thầu",
            (r"bao\s*lanh\s*du\s*thau", r"bao\s*dam\s*du\s*thau"),
            (r"bao\s*lanh\s*du\s*thau", r"bao\s*dam\s*du\s*thau", r"\bbldt\b")),
    DocType("bang_chao_gia", "Bảng chào giá chi tiết / BOQ",
            (r"bang\s*chao\s*gia", r"bang\s*gia\s*chi\s*tiet", r"\bboq\b",
             r"bang\s*tien\s*luong", r"bieu\s*gia"),
            (r"\bboq\b", r"chao\s*gia\s*chi\s*tiet", r"bang\s*chao\s*gia", r"klmt",
             r"bang\s*gia"),
            extensions=(".xlsx", ".xlsb", ".xls", ".pdf")),
    DocType("danh_muc_vat_tu", "Danh mục vật tư / thiết bị đề xuất",
            (r"danh\s*muc\s*vat\s*tu", r"danh\s*muc\s*thiet\s*bi",
             r"bang\s*ke\s*vat\s*tu", r"vat\s*tu\s*de\s*xuat"),
            (r"danh\s*muc\s*vat\s*tu", r"\bdmvt\b", r"vat\s*tu\s*(de\s*xuat|thiet\s*bi)",
             r"pl\s*0?2")),
    DocType("bao_cao_tai_chinh", "Báo cáo tài chính",
            (r"bao\s*cao\s*tai\s*chinh", r"\bbctc\b", r"bao\s*cao\s*kiem\s*toan"),
            (r"bao\s*cao\s*tai\s*chinh", r"\bbctc\b", r"kiem\s*toan"),
            min_count=3),
    DocType("nang_luc_phap_ly", "Hồ sơ năng lực / pháp lý doanh nghiệp",
            (r"ho\s*so\s*nang\s*luc", r"tu\s*cach\s*hop\s*le",
             r"dang\s*ky\s*doanh\s*nghiep", r"giay\s*chung\s*nhan\s*dang\s*ky"),
            (r"nang\s*luc", r"dang\s*ky\s*doanh\s*nghiep", r"phap\s*ly", r"chung\s*chi",
             r"business\s*license", r"dkkd")),
    DocType("hop_dong_tuong_tu", "Hợp đồng tương tự",
            (r"hop\s*dong\s*tuong\s*tu", r"kinh\s*nghiem\s*thuc\s*hien"),
            (r"hop\s*dong\s*tuong\s*tu", r"\bhdtt\b", r"\bhdtc\b", r"hd\s*tuong\s*tu")),
    DocType("nhan_su", "Nhân sự chủ chốt / sơ đồ tổ chức",
            (r"nhan\s*su\s*chu\s*chot", r"nhan\s*su\s*chu\s*yeu", r"so\s*do\s*to\s*chuc",
             r"ke\s*khai\s*nhan\s*su"),
            (r"nhan\s*su", r"so\s*do\s*to\s*chuc", r"\bcbkt\b")),
    DocType("may_moc_thiet_bi", "Kê khai máy móc, thiết bị thi công",
            (r"may\s*moc\s*thiet\s*bi", r"ke\s*khai\s*thiet\s*bi", r"thiet\s*bi\s*thi\s*cong"),
            (r"may\s*moc", r"thiet\s*bi\s*thi\s*cong", r"\bmmtb\b")),
    DocType("tien_do", "Tiến độ thi công / cung cấp",
            (r"tien\s*do\s*thi\s*cong", r"tien\s*do\s*cung\s*cap", r"bang\s*tien\s*do"),
            (r"tien\s*do",)),
    DocType("bien_phap_thi_cong", "Biện pháp thi công",
            (r"bien\s*phap\s*thi\s*cong", r"bien\s*phap\s*to\s*chuc\s*thi\s*cong"),
            (r"bien\s*phap\s*thi\s*cong", r"\bbptc\b")),
    DocType("an_toan_lao_dong", "An toàn lao động / vệ sinh môi trường",
            (r"an\s*toan\s*lao\s*dong", r"\batld\b", r"ve\s*sinh\s*moi\s*truong"),
            (r"an\s*toan\s*lao\s*dong", r"\batld\b", r"ve\s*sinh\s*moi\s*truong")),
    DocType("bao_hanh", "Cam kết bảo hành / bảo trì",
            (r"cam\s*ket\s*bao\s*hanh", r"che\s*do\s*bao\s*hanh", r"bao\s*hanh\s*bao\s*tri"),
            (r"bao\s*hanh", r"bao\s*tri")),
    DocType("catalogue", "Catalogue / tài liệu kỹ thuật vật tư",
            (r"catalog", r"tai\s*lieu\s*ky\s*thuat", r"thong\s*so\s*ky\s*thuat"),
            (r"catalog", r"tai\s*lieu\s*ky\s*thuat", r"\btskt\b")),
    DocType("chung_chi_xuat_xu", "Chứng chỉ chất lượng / xuất xứ (CO, CQ)",
            (r"\bco\s*[,/]\s*cq\b", r"chung\s*chi\s*chat\s*luong", r"chung\s*nhan\s*xuat\s*xu",
             r"giay\s*chung\s*nhan\s*chat\s*luong"),
            (r"\bco\b.*\bcq\b", r"chung\s*chi\s*chat\s*luong", r"xuat\s*xu", r"\bcocq\b")),
    DocType("uy_quyen", "Giấy ủy quyền",
            (r"giay\s*uy\s*quyen", r"uy\s*quyen\s*ky"),
            (r"uy\s*quyen",)),
    DocType("lien_danh", "Thỏa thuận liên danh",
            (r"thoa\s*thuan\s*lien\s*danh", r"hop\s*dong\s*lien\s*danh"),
            (r"lien\s*danh",)),
    DocType("thue_bhxh", "Nghĩa vụ thuế / bảo hiểm xã hội",
            (r"nghia\s*vu\s*thue", r"bao\s*hiem\s*xa\s*hoi", r"\bbhxh\b",
             r"hoan\s*thanh\s*nghia\s*vu\s*thue"),
            (r"\bthue\b", r"\bbhxh\b", r"bao\s*hiem\s*xa\s*hoi")),
)


@dataclass
class DetectedItem:
    doc_type: DocType
    evidence: str          # câu trong HSMT chứng minh yêu cầu này
    hit_count: int


@dataclass
class HsmtChecklist:
    items: list[DetectedItem]
    sources: list[str]
    skipped: list[str]
    text_length: int

    @property
    def labels(self) -> list[str]:
        return [d.doc_type.label for d in self.items]


def _clean_evidence(line: str, limit: int = 180) -> str:
    line = re.sub(r'\s+', ' ', line).strip(" .;-\t|")
    return line[:limit] + ("..." if len(line) > limit else "")


def detect_requirements(text: str) -> list[DetectedItem]:
    """Dò xem HSMT yêu cầu những loại tài liệu nào."""
    raw_lines = [ln for ln in re.split(r'[\n\r]+', text) if ln.strip()]
    folded_lines = [fold(ln) for ln in raw_lines]

    found: list[DetectedItem] = []
    for doc in VOCABULARY:
        regexes = [re.compile(p) for p in doc.hsmt_patterns]
        hits = 0
        evidence = ""
        for raw, folded in zip(raw_lines, folded_lines):
            if any(rx.search(folded) for rx in regexes):
                hits += 1
                if not evidence:
                    evidence = _clean_evidence(raw)
        if hits:
            found.append(DetectedItem(doc_type=doc, evidence=evidence, hit_count=hits))
    return found


def build_from_file(path: str | Path) -> HsmtChecklist:
    """Đọc HSMT rồi dựng danh sách đầu mục tài liệu mà gói thầu yêu cầu."""
    extracted = extract_text(path)
    items = detect_requirements(extracted.text)
    logger.info("HSMT '%s': đọc %d ký tự, nhận ra %d đầu mục tài liệu",
                Path(path).name, len(extracted.text), len(items))
    return HsmtChecklist(items=items, sources=extracted.sources,
                         skipped=extracted.skipped, text_length=len(extracted.text))


def to_checklist_items(detected: list[DetectedItem]):
    """Chuyển đầu mục dò được sang ChecklistItem để dossier_check dùng."""
    from core.dossier_check import ChecklistItem
    return tuple(
        ChecklistItem(
            key=d.doc_type.key,
            label=d.doc_type.label,
            patterns=d.doc_type.file_patterns,
            min_count=d.doc_type.min_count,
            required=True,          # đã nằm trong HSMT thì là bắt buộc
            extensions=d.doc_type.extensions,
        )
        for d in detected
    )
