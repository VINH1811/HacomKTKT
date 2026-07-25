"""PriceAdvisor — orchestrator that ties together the RAG pipeline.

This is the main entry point for price suggestion.  It:
1. Filters items that lack pricing data
2. Embeds item descriptions and searches the price database
3. Sanitizes context via EgressGuard
4. Queries the LLM for structured price suggestions
5. Validates results before returning

The module is designed to be called as a BackgroundTask so it does not
block the main comparison pipeline.
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Optional

from .config import PriceAdvisorConfig
from .database import PriceDatabase
from .egress_guard import EgressGuard
from .embedder import Embedder
from .llm_client import LLMClient
from .models import AdvisorResult, PriceSuggestion, SuggestionStatus
from .validator import SuggestionValidator

logger = logging.getLogger(__name__)


class PriceAdvisor:
    """Orchestrates the full RAG → LLM → Validate pipeline."""

    def __init__(self, config: Optional[PriceAdvisorConfig] = None) -> None:
        self._config = config or PriceAdvisorConfig.from_env()
        self._db: Optional[PriceDatabase] = None
        self._embedder: Optional[Embedder] = None
        self._llm: Optional[LLMClient] = None
        self._guard: Optional[EgressGuard] = None
        self._validator: Optional[SuggestionValidator] = None

    def _ensure_initialized(self) -> None:
        """Lazy-initialize components on first use."""
        if self._db is None:
            cfg = self._config
            self._db = PriceDatabase(cfg.db_path, config=cfg)
            self._embedder = Embedder(cfg)
            self._llm = LLMClient(cfg)
            self._guard = EgressGuard(strict=True)
            self._validator = SuggestionValidator(cfg)

    @property
    def is_ready(self) -> bool:
        """Check if the advisor has a valid configuration."""
        return self._config.is_ready

    def get_stats(self) -> dict:
        """Return price database statistics."""
        self._ensure_initialized()
        assert self._db is not None
        stats = self._db.get_stats()
        stats["advisor_enabled"] = self._config.enabled
        stats["llm_provider"] = self._config.llm_provider
        stats["llm_model"] = self._config.llm_model
        return stats

    def suggest_prices(
        self,
        items: list[dict],
        job_id: str = "",
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> AdvisorResult:
        """Run price suggestions for a list of items lacking prices.

        Parameters
        ----------
        items : list[dict]
            Each dict should have at minimum:
            - ``item_id``: canonical identifier
            - ``item_name``: descriptive name
            - ``unit``: unit of measurement
            Optional fields: ``item_code``, ``material_spec``
        job_id : str
            Associated job identifier for tracking.
        progress_callback : callable, optional
            Called with (percent, message) during processing.
        """
        if not self._config.is_ready:
            return AdvisorResult(
                job_id=job_id,
                warnings=["PriceAdvisor chưa được cấu hình đầy đủ (thiếu API key hoặc chưa bật)."],
            )

        self._ensure_initialized()
        assert self._db is not None
        assert self._embedder is not None
        assert self._llm is not None
        assert self._guard is not None
        assert self._validator is not None

        started = time.perf_counter()
        max_batch = self._config.max_items_per_batch
        work_items = items[:max_batch]
        total = len(work_items)

        result = AdvisorResult(job_id=job_id, total_items_analyzed=total)
        if not work_items:
            result.warnings.append("Không có hạng mục nào cần gợi ý giá.")
            return result

        if progress_callback:
            progress_callback(5, f"Đang phân tích {total} hạng mục cần gợi ý giá...")

        # ------------------------------------------------------------------
        # Process each item through the RAG pipeline
        # ------------------------------------------------------------------
        for index, item in enumerate(work_items):
            item_id = str(item.get("item_id", f"item_{index}"))
            item_name = str(item.get("item_name", ""))
            item_unit = str(item.get("unit", ""))

            if not item_name.strip():
                result.warnings.append(f"Bỏ qua hạng mục {item_id}: tên trống")
                continue

            try:
                # Step 1: Embed item description
                description = item_name
                if item.get("material_spec"):
                    description += f" | {item['material_spec']}"
                if item.get("item_code"):
                    description += f" | Mã: {item['item_code']}"

                try:
                    query_embedding = self._embedder.embed_text(description)
                except Exception as embed_exc:
                    logger.warning("Embedding generation failed, falling back to keyword search: %s", embed_exc)
                    query_embedding = []

                # Step 2: Search similar items in price database
                similar_items = self._db.search_similar(
                    query_embedding,
                    top_k=self._config.max_similar_results,
                    query_text=description,
                )

                # Step 3: Sanitize context via EgressGuard
                context = self._guard.build_safe_prompt_context(
                    item_name=item_name,
                    item_unit=item_unit,
                    similar_items=similar_items,
                )

                # Step 4: Query LLM
                suggestion = self._llm.query_price(
                    context=context,
                    item_id=item_id,
                    item_name=item_name,
                    unit=item_unit,
                )
                suggestion.similar_items = similar_items

                # Ghi log huấn luyện LLM local (chỉ khi gọi LLM không lỗi)
                if suggestion.status != SuggestionStatus.FAILED:
                    output_response = {
                        "min_price": suggestion.min_price,
                        "max_price": suggestion.max_price,
                        "suggested_price": suggestion.suggested_price,
                        "confidence": suggestion.confidence,
                        "reasoning": suggestion.reasoning,
                    }
                    self._db.log_llm_query(
                        job_id=job_id,
                        item_id=item_id,
                        item_name=item_name,
                        unit=item_unit,
                        input_context=context,
                        output_response=output_response,
                        suggested_price=suggestion.suggested_price,
                        confidence=suggestion.confidence,
                        reasoning=suggestion.reasoning,
                        llm_provider=self._config.llm_provider,
                        llm_model=self._config.llm_model,
                    )

                # Step 5: Validate
                suggestion = self._validator.validate(suggestion, similar_items)

                result.suggestions.append(suggestion)
                result.total_tokens_used += suggestion.tokens_used

                if suggestion.status in {SuggestionStatus.VALIDATED, SuggestionStatus.NEEDS_REVIEW}:
                    result.items_with_suggestions += 1
                else:
                    result.items_failed += 1

            except Exception as exc:
                logger.error("Failed to process item %s: %s", item_id, exc)
                failed = PriceSuggestion(
                    item_id=item_id,
                    item_name=item_name,
                    unit=item_unit,
                    status=SuggestionStatus.FAILED,
                    error_message=f"Lỗi xử lý: {type(exc).__name__}: {exc}",
                    llm_provider=self._config.llm_provider,
                    llm_model=self._config.llm_model,
                )
                result.suggestions.append(failed)
                result.items_failed += 1

            if progress_callback:
                pct = 5 + int(90 * (index + 1) / total)
                progress_callback(pct, f"Đã xử lý {index + 1}/{total} hạng mục...")

        result.elapsed_seconds = time.perf_counter() - started

        if len(items) > max_batch:
            result.warnings.append(
                f"Chỉ xử lý {max_batch}/{len(items)} hạng mục (giới hạn batch). "
                f"Tăng PRICE_ADVISOR_MAX_BATCH để xử lý thêm."
            )

        if progress_callback:
            progress_callback(98, f"Hoàn tất gợi ý giá cho {result.items_with_suggestions} hạng mục.")

        logger.info(
            "PriceAdvisor completed: %d items, %d suggestions, %d failed, %d tokens, %.1fs",
            result.total_items_analyzed,
            result.items_with_suggestions,
            result.items_failed,
            result.total_tokens_used,
            result.elapsed_seconds,
        )
        return result

    def record_feedback(self, job_id: str, item_id: str, action: str,
                        suggested_price: Optional[float] = None, note: str = "") -> None:
        """Record user feedback (accept/reject) for a suggestion."""
        self._ensure_initialized()
        assert self._db is not None
        self._db.log_feedback(job_id, item_id, action, suggested_price, note)
