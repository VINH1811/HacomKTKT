"""Đoán tên nhà thầu từ tên file hoặc tiêu đề cột — dùng chung cho web và script.

Nguyên tắc: KHÔNG gắn cứng tên nhà thầu hay tên dự án nào. Chỉ loại các thuật
ngữ đấu thầu chung ("hồ sơ", "chào giá", "BOQ"...), phần còn lại chính là tên
nhà thầu. Khi có nhiều file cùng lúc, token nào xuất hiện ở MỌI tên là tên dự
án/gói thầu dùng chung nên cũng bị loại.

Từ vựng viết KHÔNG DẤU vì việc dò được thực hiện trên bản đã bỏ dấu — khỏi phải
liệt kê song song hai cách viết, vốn là nguồn gốc của những chỗ chỉ đúng với
đúng một cách gõ. Bổ sung qua HSMT_BIDDER_NOISE và HSMT_COLUMN_NOISE (các cụm
cách nhau bằng dấu phẩy).
"""

from __future__ import annotations

import os
import re
import unicodedata

# Thuật ngữ đấu thầu CHUNG, không phải tên riêng của khách hàng nào.
# "du thau" phải đứng trước \bthau\b, nếu không sẽ chỉ xoá chữ "thầu" và bỏ lại
# chữ "dự" dính vào tên nhà thầu.
_DEFAULT_NOISE = (
    r"ho\s*so|chao\s*gia|bang\s*chao\s*gia|chi\s*tiet\s*gia|tong\s*hop|noi\s*dung|"
    r"phan\s*hoi|lam\s*ro|\bhscg\b|\bhsyc\b|\bhsdt\b|\bhsmt\b|\bboq\b|\bmep\b|\bme\b|"
    r"rev\s*\d+|\btskt\b|final|\bv\d\b|du\s*thau|goi\s*thau|\bthau\b|"
    r"danh\s*gia|\bpl\s*0?\d\b|\brfi\b|so\s*sanh"
)

# Tiêu đề cột thường gặp trong bảng khối lượng. Chỉ dùng khi dò tên nhà thầu từ
# TIÊU ĐỀ CỘT: "Đơn giá Công ty ABC" -> "Công ty ABC", còn "Đơn giá" trơ trọi thì
# không phải tên ai cả.
#
# Các từ ngắn PHẢI có ranh giới từ \b, nếu không sẽ ăn vào tên thật: thiếu \b
# thì "chao" cắt "Chaozhou" thành "zhou", "vat" cắt "Vatico" thành "ico".
_DEFAULT_COLUMN_NOISE = (
    r"don\s*gia|thanh\s*tien|khoi\s*luong|don\s*vi|\bdvt\b|\bstt\b|ghi\s*chu|"
    r"thuong\s*hieu|xuat\s*xu|ma\s*hieu|quy\s*cach|vat\s*tu|vat\s*lieu|"
    r"tong\s*cong|tong\s*hop|truoc\s*thue|sau\s*thue|\bvat\b|\bvnd\b|"
    r"dien\s*giai|noi\s*dung|hang\s*muc|so\s*luong|nha\s*thau|\bchao\b|"
    # Cột thành phần giá — cũng là từ vựng chung, không phải tên ai. Cụm DÀI phải
    # đứng trước cụm ngắn, nếu không "\bvl\b" khớp trước và "VL chính" chỉ mất "VL".
    r"vl\s*chinh|vl\s*phu|may\s*thi\s*cong|nhan\s*cong|loi\s*nhuan|quan\s*ly|"
    r"moi\s*thau|chi\s*phi|\bcpql\b|\bdgth\b|\bkl\b|\bvl\b|\bnc\b|\bcp\b|"
    r"\bln\b|\bdg\b|\btt\b|thue"
)


def _build_pattern(default: str, env_name: str) -> re.Pattern[str]:
    extra = [re.escape(t.strip()) for t in os.getenv(env_name, "").split(",") if t.strip()]
    return re.compile(default + ("|" + "|".join(extra) if extra else ""), re.IGNORECASE)


BIDDER_NOISE = _build_pattern(_DEFAULT_NOISE, "HSMT_BIDDER_NOISE")
COLUMN_NOISE = _build_pattern(_DEFAULT_COLUMN_NOISE, "HSMT_COLUMN_NOISE")


def _fold_keep_length(text: str) -> str:
    """Bỏ dấu tiếng Việt nhưng GIỮ NGUYÊN độ dài chuỗi.

    Nhờ vậy có thể dò từ vựng trên bản không dấu rồi cắt đúng vị trí đó ở bản
    gốc, không cần liệt kê cả hai cách viết.
    """
    out: list[str] = []
    for ch in unicodedata.normalize("NFD", text):
        if unicodedata.combining(ch):
            continue
        out.append("d" if ch == "đ" else "D" if ch == "Đ" else ch)
    folded = "".join(out)
    return folded if len(folded) == len(text) else text


def _strip_noise(text: str, pattern: re.Pattern[str]) -> str:
    """Xoá các cụm khớp pattern: dò trên bản không dấu, cắt trên bản gốc."""
    folded = _fold_keep_length(text)
    if len(folded) != len(text):
        return pattern.sub(" ", text)
    chars = list(text)
    for match in pattern.finditer(folded):
        for index in range(match.start(), match.end()):
            chars[index] = " "
    return "".join(chars)


def guess_bidder_name(filename: str) -> str:
    """Tách tên nhà thầu từ tên file (bỏ ngày, chỉ số, từ kỹ thuật).

    Logic giống hệt hàm guessBidderName ở web/app.js để giao diện và máy chủ
    luôn đoán ra cùng một tên.
    """
    s = re.sub(r"\.[a-z0-9]+$", "", filename or "", flags=re.IGNORECASE).replace("_", " ")
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"\b\d{1,4}[.\-/]\d{1,2}(?:[.\-/]\d{1,4})?\b", " ", s)
    s = re.sub(r"\b\d{5,8}\b", " ", s)
    s = re.sub(r"^\s*\d+\s*[.\-)]\s*", "", s)
    s = _strip_noise(s, BIDDER_NOISE)
    s = re.sub(r"\s+", " ", s).strip(" -_.+")
    s = re.sub(r"^\d+\s+", "", s)
    s = re.sub(r"\s+\d+$", "", s).strip()
    if s and s == s.upper() and " " not in s:
        s = s[:1] + s[1:].lower()
    return s


def strip_shared_tokens(names: list[str], min_ratio: float = 1.0) -> list[str]:
    """Bỏ các token dùng chung (tên dự án/gói thầu), giữ lại phần khác biệt.

    ``min_ratio`` là tỷ lệ tên phải chứa token thì mới coi là dùng chung. Mặc
    định 1.0 nghĩa là phải có ở MỌI tên — an toàn cho giao diện web, nơi người
    dùng chỉ chọn đúng các file chào giá.

    Khi quét cả một thư mục thì thường lẫn file khác (bảng tổng hợp, file kết
    quả...) làm token dự án không còn xuất hiện ở mọi tên; lúc đó truyền
    ``min_ratio`` thấp hơn để vẫn nhận ra phần dùng chung.
    """
    toks = [str(n or "").split() for n in names]
    if len(toks) < 2:
        return names
    low = [[t.lower() for t in ts] for ts in toks]
    threshold = max(2, int(len(low) * min_ratio + 0.999))  # làm tròn lên
    counts: dict[str, int] = {}
    for tokens in low:
        for token in set(tokens):
            counts[token] = counts.get(token, 0) + 1
    shared = {token for token, count in counts.items() if count >= threshold}
    if not shared:
        return names
    result = []
    for ts in toks:
        kept = [t for t in ts if t.lower() not in shared]
        result.append(" ".join(kept) if kept else " ".join(ts))
    return result


def guess_bidder_from_column(title: str) -> str:
    """Tên nhà thầu nằm trong tiêu đề cột, sau khi bỏ từ vựng cột thông thường."""
    cleaned = _strip_noise(str(title or ""), COLUMN_NOISE)
    cleaned = re.sub(r"[()\[\]/\\|,;:.\-]+", " ", cleaned)
    return guess_bidder_name(re.sub(r"\s+", " ", cleaned).strip())


def guess_bidder_from_context(column_title: str = "", filename: str = "") -> str:
    """Ưu tiên tên trong tiêu đề cột, không có thì suy từ tên file."""
    return guess_bidder_from_column(column_title) or guess_bidder_name(filename)
