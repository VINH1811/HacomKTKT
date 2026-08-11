"""Đọc tham số từ biến môi trường — dùng chung cho toàn hệ thống.

Mỗi ngưỡng nghiệp vụ và mỗi danh sách từ vựng đều nên chỉnh được mà không phải
sửa mã. Trước đây mỗi module tự viết lại các hàm này nên dễ lệch nhau về cách
xử lý giá trị sai; gom về một chỗ để hành vi thống nhất: giá trị không hợp lệ
luôn quay về mặc định thay vì làm hỏng cả lần chạy.
"""

from __future__ import annotations

import os


def env_float(name: str, default: float, low: float, high: float) -> float:
    """Số thực trong khoảng [low, high]; ngoài khoảng thì kẹp về biên."""
    try:
        return max(low, min(high, float(os.getenv(name, str(default)))))
    except (TypeError, ValueError):
        return default


def env_int(name: str, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(os.getenv(name, str(default)))))
    except (TypeError, ValueError):
        return default


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "có", "co"}


def env_terms(name: str) -> set[str]:
    """Danh sách từ vựng cách nhau bằng dấu phẩy, đã thường hoá."""
    return {term.strip().lower() for term in os.getenv(name, "").split(",") if term.strip()}


def env_groups(name: str) -> tuple[tuple[str, ...], ...]:
    """Nhiều nhóm từ vựng: các nhóm cách nhau bằng ';', từ trong nhóm bằng ','.

    Ví dụ: HSMT_EXCLUSIVE_GROUPS="be tong,nhua duong;m250,m300,m350"
    """
    groups: list[tuple[str, ...]] = []
    for chunk in os.getenv(name, "").split(";"):
        terms = tuple(t.strip().lower() for t in chunk.split(",") if t.strip())
        if len(terms) > 1:
            groups.append(terms)
    return tuple(groups)
