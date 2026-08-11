"""Đánh giá TÍNH ĐẦY ĐỦ hồ sơ chào giá của nhà thầu theo checklist.

Quét cây thư mục hồ sơ mỗi nhà thầu, nhận diện từng đầu mục tài liệu bắt buộc
(đơn chào giá, bảng chào giá/BOQ, báo cáo tài chính 3 năm, hợp đồng tương tự,
nhân sự, tiến độ, biện pháp thi công...) qua tên file/thư mục — không phân biệt
hoa thường và DẤU tiếng Việt. Kết quả: bảng ĐẠT / THIẾU cho từng nhà thầu kèm
danh sách file bằng chứng, xuất Excel để chuyên viên rà lại.

Đây là đánh giá SƠ BỘ theo sự hiện diện của tài liệu — không thay thế việc
thẩm định nội dung từng tài liệu.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import xlsxwriter


def _fold(text: str) -> str:
    """Chữ thường, bỏ dấu tiếng Việt (đ -> d) để so khớp tên file bền vững."""
    text = text.replace("Đ", "D").replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower()


@dataclass(frozen=True)
class ChecklistItem:
    key: str
    label: str
    patterns: tuple[str, ...]          # regex (đã fold) khớp với đường dẫn tương đối
    min_count: int = 1                 # số file tối thiểu (BCTC cần 3 năm)
    required: bool = True
    extensions: tuple[str, ...] = ()   # rỗng = mọi định dạng


# Checklist dự phòng, dùng thuật ngữ đấu thầu chung. Chỉ áp dụng khi không có
# hồ sơ mời thầu để dựng checklist riêng cho gói thầu (xem core/hsmt_checklist.py).
# Gói thầu yêu cầu bộ tài liệu khác thì khai báo tệp JSON qua biến môi trường
# HSMT_DOSSIER_CHECKLIST thay vì sửa mã — xem load_checklist().
DEFAULT_CHECKLIST: tuple[ChecklistItem, ...] = (
    ChecklistItem("don_chao_gia", "Đơn chào giá / Đơn dự thầu",
                  (r"don\s*chao\s*gia", r"thu\s*chao\s*gia", r"don\s*du\s*thau")),
    ChecklistItem("bang_chao_gia", "Bảng chào giá chi tiết / BOQ",
                  (r"\bboq\b", r"chao\s*gia\s*chi\s*tiet", r"bang\s*chao\s*gia", r"klmt"),
                  extensions=(".xlsx", ".xlsb", ".xls", ".pdf")),
    ChecklistItem("danh_muc_vat_tu", "Danh mục vật tư/thiết bị đề xuất (PL02)",
                  (r"danh\s*muc\s*vat\s*tu", r"\bdmvt\b", r"vat\s*tu\s*(de\s*xuat|thiet\s*bi)", r"pl\s*0?2")),
    ChecklistItem("bao_cao_tai_chinh", "Báo cáo tài chính (3 năm)",
                  (r"bao\s*cao\s*tai\s*chinh", r"\bbctc\b"), min_count=3),
    ChecklistItem("nang_luc_phap_ly", "Hồ sơ năng lực / pháp lý doanh nghiệp",
                  (r"nang\s*luc", r"dang\s*ky\s*doanh\s*nghiep", r"phap\s*ly", r"chung\s*chi",
                   r"business\s*license", r"dkkd")),
    ChecklistItem("hop_dong_tuong_tu", "Hợp đồng tương tự",
                  (r"hop\s*dong\s*tuong\s*tu", r"\bhdtc\b", r"hd\s*tuong\s*tu")),
    ChecklistItem("nhan_su", "Nhân sự chủ chốt / sơ đồ tổ chức",
                  (r"nhan\s*su", r"so\s*do\s*to\s*chuc", r"\bcbkt\b")),
    ChecklistItem("tien_do", "Tiến độ thi công / cung cấp",
                  (r"tien\s*do",)),
    ChecklistItem("bien_phap_thi_cong", "Biện pháp thi công",
                  (r"bien\s*phap\s*thi\s*cong", r"\bbptc\b")),
    ChecklistItem("an_toan_lao_dong", "An toàn lao động / VSMT",
                  (r"an\s*toan\s*lao\s*dong", r"\batld\b", r"an\s*toan")),
    ChecklistItem("catalogue", "Catalogue vật tư thiết bị",
                  (r"catalog",), required=False),
    ChecklistItem("uy_quyen", "Giấy ủy quyền ký hồ sơ",
                  (r"uy\s*quyen",), required=False),
)

STATUS_OK = "ĐẠT"
STATUS_MISSING = "THIẾU"
STATUS_PARTIAL = "THIẾU MỘT PHẦN"
STATUS_OPTIONAL_MISSING = "KHÔNG CÓ (không bắt buộc)"

# Bỏ qua file rác/hệ thống khi quét.
_IGNORED_NAMES = {"thumbs.db", ".ds_store", "desktop.ini"}


def load_checklist() -> tuple[ChecklistItem, ...]:
    """Checklist dự phòng, ưu tiên tệp JSON khai báo ở HSMT_DOSSIER_CHECKLIST.

    Mỗi phần tử JSON: {"key", "label", "patterns": [...], "min_count", "required",
    "extensions": [...]}. Tệp hỏng hoặc thiếu trường bắt buộc thì dùng bộ mặc
    định — chấm thiếu tài liệu vì lỗi cấu hình còn tệ hơn dùng bộ chung.
    """
    path = os.getenv("HSMT_DOSSIER_CHECKLIST", "").strip()
    if not path:
        return DEFAULT_CHECKLIST
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        items = tuple(
            ChecklistItem(
                key=str(entry["key"]),
                label=str(entry["label"]),
                patterns=tuple(str(p) for p in entry["patterns"]),
                min_count=int(entry.get("min_count", 1)),
                required=bool(entry.get("required", True)),
                extensions=tuple(str(e).lower() for e in entry.get("extensions", ())),
            )
            for entry in raw
        )
        return items or DEFAULT_CHECKLIST
    except Exception:
        return DEFAULT_CHECKLIST


@dataclass
class CategoryResult:
    item: ChecklistItem
    files: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        n = len(self.files)
        if n >= self.item.min_count:
            return STATUS_OK
        if n == 0:
            return STATUS_MISSING if self.item.required else STATUS_OPTIONAL_MISSING
        return STATUS_PARTIAL


@dataclass
class DossierResult:
    bidder: str
    root: str
    categories: list[CategoryResult]
    total_files: int = 0
    # File không khớp bất kỳ đầu mục nào. Thường là tài liệu đặt tên sai quy
    # ước nên bị chấm THIẾU oan — cần người rà lại chứ không bỏ qua.
    unmatched_files: list[str] = field(default_factory=list)

    @property
    def missing_required(self) -> list[CategoryResult]:
        return [c for c in self.categories
                if c.item.required and c.status in (STATUS_MISSING, STATUS_PARTIAL)]


def evaluate_dossier(
    bidder: str,
    root: str | Path,
    checklist: tuple[ChecklistItem, ...] = DEFAULT_CHECKLIST,
) -> DossierResult:
    """Quét thư mục hồ sơ một nhà thầu và chấm ĐẠT/THIẾU theo checklist."""
    root = Path(root)
    compiled = [(item, [re.compile(p) for p in item.patterns]) for item in checklist]
    results = {item.key: CategoryResult(item=item) for item in checklist}
    total = 0
    unmatched: list[str] = []
    for f in root.rglob("*"):
        if not f.is_file() or f.name.lower() in _IGNORED_NAMES:
            continue
        total += 1
        rel = str(f.relative_to(root))
        folded = _fold(rel)
        matched_any = False
        for item, regexes in compiled:
            if item.extensions and f.suffix.lower() not in item.extensions:
                continue
            if any(rx.search(folded) for rx in regexes):
                results[item.key].files.append(rel)
                matched_any = True
        if not matched_any:
            unmatched.append(rel)
    return DossierResult(
        bidder=bidder,
        root=str(root),
        categories=[results[item.key] for item in checklist],
        total_files=total,
        unmatched_files=unmatched,
    )


def export_dossier_report(results: list[DossierResult], output_path: str | Path,
                          checklist_source: Optional[dict] = None) -> str:
    """Bảng ma trận checklist × nhà thầu + sheet bằng chứng từng nhà thầu.

    `checklist_source` (tuỳ chọn) mô tả checklist lấy từ đâu: mặc định hay đọc
    từ HSMT người dùng tải lên. Có thì thêm một sheet ghi rõ nguồn và bằng
    chứng trích từ HSMT, để người kiểm tra soi lại được vì sao có đầu mục đó.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb = xlsxwriter.Workbook(str(output_path), {"nan_inf_to_errors": True})

    f_title = wb.add_format({"bold": True, "font_size": 14, "font_color": "#FFFFFF",
                             "bg_color": "#17365D", "align": "center", "valign": "vcenter"})
    f_head = wb.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#1F4E78",
                            "align": "center", "valign": "vcenter", "text_wrap": True, "border": 1})
    f_cat = wb.add_format({"valign": "top", "text_wrap": True})
    f_ok = wb.add_format({"bold": True, "font_color": "#2E7D32", "bg_color": "#E2EFDA",
                          "align": "center", "border": 1})
    f_miss = wb.add_format({"bold": True, "font_color": "#9C0006", "bg_color": "#F4CCCC",
                            "align": "center", "border": 1})
    f_part = wb.add_format({"bold": True, "font_color": "#C65911", "bg_color": "#FCE4D6",
                            "align": "center", "border": 1})
    f_opt = wb.add_format({"font_color": "#808080", "align": "center", "border": 1})
    f_note = wb.add_format({"italic": True, "font_color": "#595959", "text_wrap": True})
    f_unmatched = wb.add_format({"font_color": "#7F6000", "bg_color": "#FFF2CC",
                                 "border": 1, "text_wrap": True})
    status_fmt = {STATUS_OK: f_ok, STATUS_MISSING: f_miss,
                  STATUS_PARTIAL: f_part, STATUS_OPTIONAL_MISSING: f_opt}

    ws = wb.add_worksheet("Checklist hồ sơ")
    ncols = 1 + len(results)
    ws.merge_range(0, 0, 0, max(1, ncols - 1), "ĐÁNH GIÁ TÍNH ĐẦY ĐỦ HỒ SƠ CHÀO GIÁ", f_title)
    ws.set_row(0, 26)
    ws.set_column(0, 0, 42)
    ws.write(2, 0, "Đầu mục tài liệu", f_head)
    for col, res in enumerate(results, 1):
        ws.set_column(col, col, 24)
        ws.write(2, col, f"{res.bidder}\n({res.total_files} file)", f_head)
    checklist = results[0].categories if results else []
    for r_idx, _ in enumerate(checklist):
        row = 3 + r_idx
        item = results[0].categories[r_idx].item
        label = item.label + ("" if item.required else " (không bắt buộc)")
        ws.write(row, 0, label, f_cat)
        for col, res in enumerate(results, 1):
            cat = res.categories[r_idx]
            text = cat.status
            if cat.status in (STATUS_OK, STATUS_PARTIAL):
                text += f" ({len(cat.files)}"
                text += f"/{item.min_count})" if item.min_count > 1 else " file)"
            ws.write(row, col, text, status_fmt[cat.status])
    # Dòng cảnh báo file lạ, ngay dưới bảng ma trận.
    warn_row = 3 + len(checklist)
    ws.write(warn_row, 0, "⚠ File không khớp đầu mục nào", f_cat)
    for col, res in enumerate(results, 1):
        n = len(res.unmatched_files)
        ws.write(warn_row, col, f"{n} file" if n else "—",
                 f_unmatched if n else f_opt)

    note_row = 5 + len(checklist)
    ws.merge_range(note_row, 0, note_row, max(1, ncols - 1),
                   "Đánh giá SƠ BỘ theo sự hiện diện của tài liệu trong hồ sơ (nhận diện qua tên "
                   "file/thư mục). Chuyên viên cần thẩm định nội dung từng tài liệu trước khi kết luận.",
                   f_note)
    ws.freeze_panes(3, 1)

    # Sheet bằng chứng cho từng nhà thầu
    for res in results:
        name = f"BC {res.bidder}"[:31]
        ev = wb.add_worksheet(name)
        ev.set_column(0, 0, 40)
        ev.set_column(1, 1, 14)
        ev.set_column(2, 2, 100)
        for col, head in enumerate(["Đầu mục", "Kết quả", "File bằng chứng (đường dẫn tương đối)"]):
            ev.write(0, col, head, f_head)
        r = 1
        for cat in res.categories:
            ev.write(r, 0, cat.item.label, f_cat)
            ev.write(r, 1, cat.status, status_fmt[cat.status])
            if cat.files:
                for path_ in cat.files[:50]:
                    ev.write(r, 2, path_, f_cat)
                    r += 1
            else:
                r += 1

        # File không khớp đầu mục nào — nghi đặt tên sai, cần rà tay.
        if res.unmatched_files:
            r += 1
            ev.write(r, 0, "⚠ FILE KHÔNG KHỚP ĐẦU MỤC NÀO", f_head)
            ev.write(r, 1, f"{len(res.unmatched_files)} file", f_head)
            ev.write(r, 2, "Có thể đặt tên sai quy ước — kiểm tra thủ công "
                           "trước khi kết luận là thiếu tài liệu", f_head)
            r += 1
            for path_ in res.unmatched_files[:200]:
                ev.write(r, 2, path_, f_unmatched)
                r += 1
        ev.freeze_panes(1, 0)

    # Sheet nguồn checklist
    if checklist_source:
        src = wb.add_worksheet("Nguồn checklist")
        src.set_column(0, 0, 42)
        src.set_column(1, 1, 10)
        src.set_column(2, 2, 105)
        src.merge_range(0, 0, 0, 2,
                        f"CHECKLIST LẤY TỪ: {checklist_source.get('origin', 'mặc định')}",
                        f_title)
        src.set_row(0, 26)
        row = 2
        for label, value in checklist_source.get("meta", []):
            src.write(row, 0, label, f_cat)
            src.merge_range(row, 1, row, 2, str(value), f_cat)
            row += 1
        evidences = checklist_source.get("evidences") or []
        if evidences:
            row += 1
            for col, head in enumerate(["Đầu mục yêu cầu", "Số lần nhắc",
                                        "Trích dẫn trong HSMT"]):
                src.write(row, col, head, f_head)
            row += 1
            for label, hits, evidence in evidences:
                src.write(row, 0, label, f_cat)
                src.write(row, 1, hits, f_cat)
                src.write(row, 2, evidence, f_cat)
                row += 1
        row += 1
        src.merge_range(row, 0, row, 2,
                        "Đầu mục được nhận diện bằng dò từ khoá trong HSMT, không phải đọc hiểu. "
                        "Hãy đối chiếu trích dẫn ở trên với HSMT gốc; nếu thiếu đầu mục nào thì "
                        "bổ sung thủ công.", f_note)

    wb.close()
    return str(output_path)
