"""Multi-provider LLM client for PriceAdvisor.

Supports OpenAI (and OpenAI-compatible endpoints like vLLM/Ollama),
Anthropic (Claude) and Google (Gemini).  All providers are accessed
through their official SDKs with a unified interface.

The system prompt enforces structured JSON output so the response
can be reliably parsed by the Validator.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from typing import Any, Optional

from .config import PriceAdvisorConfig
from .models import PriceSuggestion, SuggestionStatus

logger = logging.getLogger(__name__)

# Máy chủ LLM chạy tại chỗ. Nhận theo địa chỉ loopback / tên máy nội bộ, KHÔNG
# theo số cổng — cổng là thứ người dùng hay đổi.
_LOCAL_HOSTS = ("127.0.0.1", "localhost", "0.0.0.0", "[::1]", "host.docker.internal")
# Họ mô hình có chế độ "thinking" cần tắt khi chạy tại chỗ. Bổ sung qua
# PRICE_ADVISOR_THINKING_MODELS (cách nhau bằng dấu phẩy).
_THINKING_MODELS = ("qwen3", "r1", "deepseek-r1", "qwq", "marco-o1")


def _is_local_llm(base_url: Optional[str], model: str) -> bool:
    """True khi đang gọi một máy chủ LLM nội bộ chạy mô hình có chế độ suy luận."""
    url = (base_url or "").lower()
    if "ollama" in url or any(host in url for host in _LOCAL_HOSTS):
        return True
    import os

    extra = tuple(m.strip().lower()
                  for m in os.getenv("PRICE_ADVISOR_THINKING_MODELS", "").split(",") if m.strip())
    name = (model or "").lower()
    return any(tag in name for tag in _THINKING_MODELS + extra)

SYSTEM_PROMPT = """Bạn là chuyên gia phân tích giá vật tư xây dựng MEP (Cơ Điện). \
Nhiệm vụ của bạn là phân tích dữ liệu giá lịch sử nội bộ và đưa ra gợi ý giá tham khảo cho hạng mục được yêu cầu.

YÊU CẦU BẮT BUỘC:
1. Chỉ dựa trên dữ liệu tham khảo được cung cấp. KHÔNG bịa đặt giá.
2. Nếu dữ liệu tham khảo không đủ hoặc không liên quan, trả confidence = 0 và nói rõ lý do.
3. Phải xem xét đơn vị tính khi so sánh giá. Đảm bảo đơn giá trả về cùng đơn vị tính với hạng mục cần tư vấn.
4. Giải thích ngắn gọn lý do trong trường "reasoning" bằng tiếng Việt.
5. Nhận xét xu hướng giá thị trường trong trường "market_trend" dựa trên năm ghi nhận của các mẫu lịch sử.
6. Luôn trả về đúng format JSON dưới đây, không thêm text ngoài JSON.

FORMAT JSON TRẢ VỀ:
{
  "min_price": <số_float_hoặc_null>,
  "max_price": <số_float_hoặc_null>,
  "suggested_price": <số_float_hoặc_null>,
  "confidence": <float_từ_0.0_đến_1.0>,
  "reasoning": "<lý_do_bằng_tiếng_Việt>",
    "market_trend": "<nhận_xét_xu_hướng_thị_trường_bằng_tiếng_Việt>",
    "price_comment": "<nhận_xét_ngắn_về_giá_dự_đoán_bằng_tiếng_Việt>"
}

HƯỚNG DẪN TÍNH CONFIDENCE:
- 0.9-1.0: Có ≥3 mẫu rất tương đồng, cùng đơn vị, cùng quy cách.
- 0.7-0.9: Có 2-3 mẫu tương đồng tốt nhưng khác năm hoặc khu vực.
- 0.5-0.7: Chỉ có 1-2 mẫu gần đúng hoặc đơn vị/quy cách khác biệt nhẹ.
- 0.0-0.5: Không có mẫu phù hợp, gợi ý mang tính tham khảo thấp.

HƯỚNG DẪN MARKET_TREND:
- Phân tích dựa trên trường "năm" trong các mẫu lịch sử. Nếu có nhiều năm, so sánh mức giá qua các năm.
- Ví dụ tốt: "Giá vật tư này có xu hướng tăng khoảng 5-8%/năm qua các năm 2023-2025."
- Nếu các mẫu cùng năm: "Các mẫu tham khảo cùng thời kỳ, không đủ dữ liệu để phân tích xu hướng nhiều năm."
- Nếu không có trường năm: "Không có thông tin năm trong dữ liệu tham khảo để nhận xét xu hướng." """


def _build_user_prompt(context: dict[str, Any]) -> str:
    """Build the user prompt from the sanitized context."""
    item_name = context.get("hạng_mục_cần_tư_vấn", "Không rõ")
    unit = context.get("đơn_vị_tính", "")
    references = context.get("dữ_liệu_tham_khảo", [])
    count = context.get("số_mẫu_tham_khảo", 0)

    ref_text = json.dumps(references, ensure_ascii=False, indent=2) if references else "Không có dữ liệu tham khảo."

    market_ref = context.get("giá_thị_trường_web")
    market_text = ""
    if market_ref and market_ref.get("avg_price") is not None:
        market_text = (
            f"DỮ LIỆU GIÁ THỊ TRƯỜNG TRỰC TUYẾN (WEB SEARCH RAG):\n"
            f"- Cận dưới: {market_ref.get('min_price'):,} VNĐ\n"
            f"- Cận trên: {market_ref.get('max_price'):,} VNĐ\n"
            f"- Trung bình: {market_ref.get('avg_price'):,} VNĐ\n"
            f"- Trích dẫn tìm thấy:\n" + "\n".join([f"  * {snip}" for snip in market_ref.get('snippets', [])]) + "\n\n"
        )

    return (
        f"HẠNG MỤC CẦN TƯ VẤN GIÁ:\n"
        f"- Tên: {item_name}\n"
        f"- Đơn vị tính: {unit}\n\n"
        f"DỮ LIỆU GIÁ LỊCH SỬ THAM KHẢO ({count} mẫu):\n{ref_text}\n\n"
        f"{market_text}"
        f"Hãy phân tích và trả về JSON gợi ý giá."
    )


def _parse_llm_response(raw: str) -> dict[str, Any]:
    """Extract JSON from an LLM response, handling markdown code fences and extra text."""
    # Clean think block if present
    text = raw.strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strip markdown code fences if present
    if "```" in text:
        for fence in ["```json", "```JSON", "```"]:
            if fence in text:
                parts = text.split(fence)
                if len(parts) > 1:
                    inner = parts[1].split("```")[0].strip()
                    try:
                        return json.loads(inner)
                    except json.JSONDecodeError:
                        text = inner
                        break

    # Regex search for the first JSON object { ... }
    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # If all fails, try direct json.loads again to raise the original exception
    return json.loads(text)


class LLMClient:
    """Unified LLM client with multi-provider support."""

    def __init__(self, config: PriceAdvisorConfig) -> None:
        self._config = config
        self._provider = config.llm_provider
        self._model = config.llm_model
        self._api_key = config.api_key
        self._base_url = config.base_url
        self._temperature = config.llm_temperature
        self._max_tokens = config.llm_max_tokens
        self._timeout = config.llm_timeout_seconds
        self._think = config.llm_think

    def query_price(
        self,
        context: dict[str, Any],
        item_id: str = "",
        item_name: str = "",
        unit: str = "",
    ) -> PriceSuggestion:
        """Send a price query to the LLM and return a PriceSuggestion.

        Parameters
        ----------
        context : dict
            Sanitized context from EgressGuard.
        item_id : str
            Canonical ID of the item being priced.
        item_name : str
            Display name of the item.
        unit : str
            Unit of measurement.
        """
        user_prompt = _build_user_prompt(context)
        suggestion = PriceSuggestion(
            item_id=item_id,
            item_name=item_name,
            unit=unit,
            llm_provider=self._provider,
            llm_model=self._model,
        )

        try:
            if self._provider == "openai":
                raw, tokens = self._call_openai(user_prompt)
            elif self._provider == "anthropic":
                raw, tokens = self._call_anthropic(user_prompt)
            elif self._provider == "google":
                raw, tokens = self._call_google(user_prompt)
            elif self._provider == "ollama":
                raw, tokens = self._call_ollama(user_prompt)
            else:
                raise ValueError(f"Unsupported LLM provider: {self._provider}")

            suggestion.tokens_used = tokens
            parsed = _parse_llm_response(raw)

            suggestion.min_price = parsed.get("min_price")
            suggestion.max_price = parsed.get("max_price")
            suggestion.suggested_price = parsed.get("suggested_price")
            suggestion.confidence = float(parsed.get("confidence", 0.0))
            suggestion.reasoning = str(parsed.get("reasoning", ""))
            suggestion.market_trend = str(parsed.get("market_trend", ""))
            suggestion.price_comment = str(parsed.get("price_comment", ""))
            suggestion.status = SuggestionStatus.PENDING

        except json.JSONDecodeError as exc:
            logger.warning("LLM returned invalid JSON: %s", exc)
            suggestion.status = SuggestionStatus.FAILED
            suggestion.error_message = f"LLM trả về JSON không hợp lệ: {exc}"
        except Exception as exc:
            logger.error("LLM call failed: %s", exc)
            suggestion.status = SuggestionStatus.FAILED
            suggestion.error_message = f"Lỗi gọi LLM: {type(exc).__name__}: {exc}"

        return suggestion

    # ------------------------------------------------------------------
    # Provider implementations
    # ------------------------------------------------------------------

    def _call_openai(self, user_prompt: str) -> tuple[str, int]:
        """Call OpenAI (or compatible) API."""
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("Cài gói 'openai': pip install openai")

        client = OpenAI(
            api_key=self._api_key,
            base_url=self._base_url or None,
            timeout=self._timeout,
        )
        
        extra_body = {}
        # Mô hình suy luận chạy tại chỗ cần tắt chế độ "thinking", nếu không sẽ
        # hết token hoặc quá hạn chờ.
        #
        # Nhận diện máy chủ nội bộ theo ĐỊA CHỈ LOOPBACK chứ không theo số cổng:
        # trước đây dò chuỗi "11434" nên ai đổi cổng (ví dụ 11435) là heuristic
        # này im lặng thất bại.
        if _is_local_llm(self._base_url, self._model):
            extra_body["think"] = False

        response = client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            response_format={"type": "json_object"},
            extra_body=extra_body if extra_body else None,
        )
        content = response.choices[0].message.content or ""
        tokens = (response.usage.total_tokens if response.usage else 0)
        return content, tokens

    def _call_ollama(self, user_prompt: str) -> tuple[str, int]:
        """Call Ollama's native chat API with root-level thinking control."""
        base_url = (self._base_url or "http://localhost:11434").rstrip("/")
        api_url = f"{base_url}/api/chat"
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {
                "temperature": self._temperature,
                "num_predict": max(self._max_tokens, 4096),
            },
        }
        if self._think:
            payload["think"] = True

        request = urllib.request.Request(
            api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Khong ket noi duoc Ollama tai {api_url}: {exc}") from exc

        message = data.get("message") or {}
        content = str(message.get("content") or "")
        tokens = int(data.get("prompt_eval_count") or 0) + int(data.get("eval_count") or 0)
        return content, tokens

    def _call_anthropic(self, user_prompt: str) -> tuple[str, int]:
        """Call Anthropic Claude API."""
        try:
            from anthropic import Anthropic
        except ImportError:
            raise ImportError("Cài gói 'anthropic': pip install anthropic")

        client = Anthropic(api_key=self._api_key)
        response = client.messages.create(
            model=self._model,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        content = response.content[0].text if response.content else ""
        tokens = (response.usage.input_tokens + response.usage.output_tokens) if response.usage else 0
        return content, tokens

    def _call_google(self, user_prompt: str) -> tuple[str, int]:
        """Call Google Gemini API."""
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise ImportError("Cài gói 'google-genai': pip install google-genai")

        client = genai.Client(api_key=self._api_key)
        response = client.models.generate_content(
            model=self._model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=self._temperature,
                max_output_tokens=self._max_tokens,
                response_mime_type="application/json",
            ),
        )
        content = response.text or ""
        tokens = 0
        if response.usage_metadata:
            tokens = (response.usage_metadata.prompt_token_count or 0) + (
                response.usage_metadata.candidates_token_count or 0
            )
        return content, tokens
