"""Validator for LLM-generated price suggestions.

Checks for hallucinations, unit mismatches, unreasonable price ranges
and other common failure modes.  Each suggestion receives a validated
status: ``validated``, ``needs_review`` or ``rejected``.
"""
from __future__ import annotations

import logging
import math
from typing import Optional

from .config import PriceAdvisorConfig
from .models import PriceSuggestion, SimilarItem, SuggestionStatus

logger = logging.getLogger(__name__)


class SuggestionValidator:
    """Post-LLM validation of price suggestions."""

    def __init__(self, config: PriceAdvisorConfig) -> None:
        self._config = config
        self._max_deviation = config.max_price_deviation
        self._min_confidence = config.confidence_threshold

    def validate(
        self,
        suggestion: PriceSuggestion,
        similar_items: list[SimilarItem],
    ) -> PriceSuggestion:
        """Validate and possibly adjust the suggestion status.

        Checks performed:
        1. JSON parse succeeded (status != FAILED)
        2. Suggested price is a positive finite number
        3. Price range is consistent (min <= suggested <= max)
        4. Price is within reasonable bounds vs. RAG data
        5. Confidence meets the minimum threshold
        """
        if suggestion.status is SuggestionStatus.FAILED:
            suggestion.price_comment = suggestion.price_comment or "Không thể nhận xét vì gợi ý giá đã thất bại."
            return suggestion

        llm_price_comment = suggestion.price_comment

        issues: list[str] = []

        # 1. Basic numeric validity
        if suggestion.suggested_price is None:
            issues.append("LLM không trả về giá gợi ý (null)")
        elif not math.isfinite(suggestion.suggested_price) or suggestion.suggested_price <= 0:
            issues.append(f"Giá gợi ý không hợp lệ: {suggestion.suggested_price}")

        # 2. Range consistency
        if suggestion.min_price is not None and suggestion.max_price is not None:
            if suggestion.min_price > suggestion.max_price:
                issues.append(
                    f"Khoảng giá ngược: min={suggestion.min_price:,.0f} > max={suggestion.max_price:,.0f}"
                )
            if suggestion.suggested_price is not None:
                if suggestion.suggested_price < (suggestion.min_price * 0.95):
                    issues.append("Giá gợi ý thấp hơn giá tối thiểu")
                if suggestion.suggested_price > (suggestion.max_price * 1.05):
                    issues.append("Giá gợi ý cao hơn giá tối đa")

        # 3. Cross-check with RAG data (hallucination detection)
        rag_prices = [
            item.record.unit_price
            for item in similar_items
            if item.record.unit_price is not None
            and math.isfinite(item.record.unit_price)
            and item.record.unit_price > 0
        ]

        if rag_prices and suggestion.suggested_price is not None and suggestion.suggested_price > 0:
            median_price = sorted(rag_prices)[len(rag_prices) // 2]
            ratio = suggestion.suggested_price / median_price if median_price > 0 else float("inf")

            if ratio > self._max_deviation or ratio < (1.0 / self._max_deviation):
                issues.append(
                    f"Giá gợi ý ({suggestion.suggested_price:,.0f}) lệch quá "
                    f"{self._max_deviation}x so với trung vị RAG ({median_price:,.0f})"
                )
        elif not rag_prices:
            # No RAG prices available — lower confidence
            if suggestion.confidence > 0.5:
                suggestion.confidence = min(suggestion.confidence, 0.5)
                issues.append("Không có dữ liệu giá tham khảo — đã hạ confidence")

        # 4. Confidence threshold
        if suggestion.confidence < self._min_confidence:
            issues.append(
                f"Độ tin cậy ({suggestion.confidence:.2f}) thấp hơn ngưỡng ({self._min_confidence:.2f})"
            )

        # ------------------------------------------------------------------
        # Decide final status
        # ------------------------------------------------------------------
        if not issues:
            suggestion.status = SuggestionStatus.VALIDATED
        elif any("không hợp lệ" in issue or "ngược" in issue or "lệch quá" in issue for issue in issues):
            suggestion.status = SuggestionStatus.NEEDS_REVIEW
            suggestion.reasoning += f" ⚠ Cần kiểm tra: {'; '.join(issues)}"
        else:
            suggestion.status = SuggestionStatus.NEEDS_REVIEW
            suggestion.reasoning += f" ℹ Lưu ý: {'; '.join(issues)}"

        if issues:
            logger.info(
                "Validation issues for item %s: %s",
                suggestion.item_id, "; ".join(issues),
            )

        suggestion.price_comment = self._build_price_comment(suggestion, rag_prices, issues, llm_price_comment)

        return suggestion

    def _build_price_comment(
        self,
        suggestion: PriceSuggestion,
        rag_prices: list[float],
        issues: list[str],
        llm_price_comment: str = "",
    ) -> str:
        if suggestion.suggested_price is None:
            return "Chưa có giá dự đoán nên chưa thể nhận xét mức giá."

        if llm_price_comment.strip() and not issues:
            return llm_price_comment.strip()

        status_text = {
            SuggestionStatus.VALIDATED: "Giá dự đoán có thể dùng làm mức tham khảo.",
            SuggestionStatus.NEEDS_REVIEW: "Giá dự đoán nên được xem lại trước khi chốt.",
            SuggestionStatus.ACCEPTED: "Giá dự đoán đã được chấp nhận.",
            SuggestionStatus.REJECTED: "Giá dự đoán đã bị từ chối.",
            SuggestionStatus.PENDING: "Giá dự đoán đang ở trạng thái chờ đánh giá.",
            SuggestionStatus.FAILED: "Không thể nhận xét vì gợi ý giá thất bại.",
        }.get(suggestion.status, "Giá dự đoán cần được đánh giá thêm.")

        confidence = suggestion.confidence
        if confidence >= 0.8:
            confidence_text = "Độ tin cậy cao."
        elif confidence >= 0.6:
            confidence_text = "Độ tin cậy ở mức trung bình."
        else:
            confidence_text = "Độ tin cậy thấp, cần kiểm tra lại."

        if not rag_prices:
            reference_text = "Chưa có dữ liệu tham khảo đủ mạnh để đối chiếu trực tiếp."
        else:
            median_price = sorted(rag_prices)[len(rag_prices) // 2]
            if median_price > 0:
                ratio = suggestion.suggested_price / median_price
                deviation_pct = abs(ratio - 1.0) * 100
                if deviation_pct <= 5:
                    reference_text = "Mức giá bám khá sát mặt bằng dữ liệu lịch sử."
                elif deviation_pct <= 15:
                    if ratio > 1:
                        reference_text = "Mức giá cao hơn nhẹ so với dữ liệu lịch sử nhưng vẫn trong vùng tham khảo."
                    else:
                        reference_text = "Mức giá thấp hơn nhẹ so với dữ liệu lịch sử nhưng vẫn trong vùng tham khảo."
                else:
                    if ratio > 1:
                        reference_text = "Mức giá cao hơn đáng kể so với dữ liệu lịch sử, nên kiểm tra lại."
                    else:
                        reference_text = "Mức giá thấp hơn đáng kể so với dữ liệu lịch sử, nên kiểm tra lại."
            else:
                reference_text = "Không thể đối chiếu với dữ liệu lịch sử do trung vị không hợp lệ."

        if issues:
            issue_text = f"Phát hiện {len(issues)} điểm cần lưu ý."
        else:
            issue_text = "Không phát hiện sai lệch lớn sau kiểm tra."

        if llm_price_comment.strip():
            return f"{llm_price_comment.strip()} {status_text} {confidence_text} {reference_text} {issue_text}".strip()

        return f"{status_text} {confidence_text} {reference_text} {issue_text}".strip()
