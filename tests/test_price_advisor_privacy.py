"""Bật chế độ bảo mật nội bộ thì tên hạng mục không được rời khỏi máy.

PriceAdvisor tra giá thị trường qua công cụ tìm kiếm và có thể gọi LLM đám mây
— cả hai đều gửi tên hạng mục trong hồ sơ thầu ra ngoài. Phần này trước đây
chạy NGOÀI hàng rào chặn mạng của hệ thống.

Hàng rào vẫn cho phép loopback nên LLM chạy tại chỗ (Ollama/vLLM) không bị ảnh
hưởng; chỉ dịch vụ bên ngoài bị chặn.
"""

from __future__ import annotations

import socket

import pytest

from security import deny_external_network


def _connect(host: str, port: int) -> Exception | None:
    sock = socket.socket()
    sock.settimeout(2)
    try:
        sock.connect((host, port))
        return None
    except Exception as exc:  # noqa: BLE001 - cần biết đúng loại lỗi
        return exc
    finally:
        sock.close()


def test_external_host_is_blocked_by_the_fence():
    with deny_external_network(True):
        error = _connect("duckduckgo.com", 443)
    assert isinstance(error, PermissionError), f"Phải bị chặn, nhận được: {error!r}"


def test_loopback_stays_available_for_local_llm():
    # Cổng Ollama mặc định. Không có gì lắng nghe thì báo "từ chối kết nối" —
    # điều cần khẳng định là KHÔNG bị chặn bởi hàng rào.
    with deny_external_network(True):
        error = _connect("127.0.0.1", 11434)
    assert not isinstance(error, PermissionError), "Hàng rào không được chặn localhost"


def test_fence_is_lifted_after_the_block():
    with deny_external_network(True):
        pass
    assert socket.socket.connect is not None
    # Bật rồi tắt xong thì kết nối nội bộ vẫn tạo được bình thường.
    assert not isinstance(_connect("127.0.0.1", 11434), PermissionError)


def test_disabled_fence_does_not_patch_anything():
    original = socket.socket.connect
    with deny_external_network(False):
        assert socket.socket.connect is original


def test_offline_mode_follows_config(monkeypatch: pytest.MonkeyPatch):
    import app

    monkeypatch.setattr(app.DEFAULT_CONFIG, "strict_privacy", True, raising=False)
    monkeypatch.setattr(app.DEFAULT_CONFIG, "allow_network", False, raising=False)
    assert app._offline_mode() is True

    # Cho phép mạng tường minh thì không chặn nữa.
    monkeypatch.setattr(app.DEFAULT_CONFIG, "allow_network", True, raising=False)
    assert app._offline_mode() is False

    monkeypatch.setattr(app.DEFAULT_CONFIG, "strict_privacy", False, raising=False)
    monkeypatch.setattr(app.DEFAULT_CONFIG, "allow_network", False, raising=False)
    assert app._offline_mode() is False


def test_market_block_explains_why_it_is_empty():
    import app

    assert app._MARKET_DISABLED["status"] == "disabled"
    assert app._MARKET_DISABLED["min_price"] is None
    assert "bảo mật" in app._MARKET_DISABLED["message"]
