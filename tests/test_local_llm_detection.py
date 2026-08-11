"""Nhận diện máy chủ LLM nội bộ theo địa chỉ, không theo số cổng.

Mô hình suy luận chạy tại chỗ cần tắt chế độ "thinking", nếu không sẽ hết token
hoặc quá hạn chờ. Trước đây việc nhận diện dò chuỗi "11434" trong địa chỉ, nên
ai đổi cổng — ví dụ chạy Ollama ở 11435 — là heuristic im lặng thất bại: không
báo lỗi gì, chỉ thỉnh thoảng treo hoặc trả rỗng.
"""

from __future__ import annotations

import pytest

from core.price_advisor.llm_client import _is_local_llm


@pytest.mark.parametrize(
    "base_url",
    [
        "http://127.0.0.1:11434",          # cổng mặc định của Ollama
        "http://127.0.0.1:11435",          # cổng tự đổi — trước đây bị bỏ sót
        "http://localhost:11435/v1",
        "http://localhost:8000/v1",        # vLLM nội bộ
        "http://0.0.0.0:9000",
        "http://host.docker.internal:11434",
        "http://ollama-server:7000",       # tên máy nêu rõ Ollama
    ],
)
def test_local_servers_are_recognised(base_url: str):
    assert _is_local_llm(base_url, "llama3.1") is True


@pytest.mark.parametrize(
    "base_url",
    [
        "https://api.openai.com/v1",
        "https://generativelanguage.googleapis.com",
        "https://api.anthropic.com",
        "",
        None,
    ],
)
def test_cloud_providers_are_not_local(base_url):
    assert _is_local_llm(base_url, "gpt-4.1-mini") is False


@pytest.mark.parametrize("model", ["qwen3-32b", "deepseek-r1:14b", "QwQ-32B", "marco-o1"])
def test_thinking_models_detected_by_name(model: str):
    # Mô hình có chế độ suy luận thì vẫn phải tắt "thinking" dù đặt ở đâu.
    assert _is_local_llm("https://api.openai.com/v1", model) is True


def test_thinking_model_list_is_extendable(monkeypatch: pytest.MonkeyPatch):
    assert _is_local_llm("https://api.openai.com/v1", "mo-hinh-moi-x") is False
    monkeypatch.setenv("PRICE_ADVISOR_THINKING_MODELS", "mo-hinh-moi-x, khac")
    assert _is_local_llm("https://api.openai.com/v1", "mo-hinh-moi-x:7b") is True


def test_port_number_alone_does_not_decide():
    # Cổng 11434 trên máy chủ ngoài KHÔNG có nghĩa là chạy nội bộ.
    assert _is_local_llm("https://llm.nha-cung-cap.com:11434/v1", "gpt-4o") is False
