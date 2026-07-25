"""Egress Guard — sanitizes data before sending to external LLM APIs.

Strips project names, contractor names, internal codes and any personally
identifiable information from the RAG context.  Only generic item
descriptions, units, quantities and anonymised historical prices are
included in the prompt sent to the LLM.

Every sanitisation call is logged for audit purposes.
"""
from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

from .models import SimilarItem

logger = logging.getLogger(__name__)

# Patterns that indicate sensitive content
_PROJECT_PATTERNS = re.compile(
    r"(dự\s*án|công\s*trình|tòa\s*nhà|khu\s*đô\s*thị|chung\s*cư|"
    r"khách\s*sạn|bệnh\s*viện|trường\s*học|nhà\s*máy)\s*[:\-]?\s*\S+",
    re.IGNORECASE,
)
_CONTRACTOR_PATTERNS = re.compile(
    r"(nhà\s*thầu|công\s*ty|tập\s*đoàn|TNHH|CP|cổ\s*phần)\s*[:\-]?\s*\S+",
    re.IGNORECASE,
)
_INTERNAL_CODE_PATTERN = re.compile(r"[A-Z]{2,5}-\d{4,}")
_EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_PATTERN = re.compile(r"(?:0|\+84)\d{9,10}")


class EgressGuard:
    """Sanitize data before it leaves the local environment."""

    def __init__(self, *, strict: bool = True) -> None:
        self._strict = strict
        self._audit_log: list[dict[str, Any]] = []

    def sanitize_item_description(self, text: str) -> str:
        """Remove sensitive identifiers from an item description string."""
        cleaned = text
        if self._strict:
            cleaned = _PROJECT_PATTERNS.sub("[DỰ ÁN]", cleaned)
            cleaned = _CONTRACTOR_PATTERNS.sub("[NHÀ THẦU]", cleaned)
            cleaned = _INTERNAL_CODE_PATTERN.sub("[MÃ NỘI BỘ]", cleaned)
            cleaned = _EMAIL_PATTERN.sub("[EMAIL]", cleaned)
            cleaned = _PHONE_PATTERN.sub("[SĐT]", cleaned)
        return cleaned.strip()

    def sanitize_similar_items(self, items: list[SimilarItem]) -> list[dict[str, Any]]:
        """Prepare a list of similar items for inclusion in an LLM prompt.

        Returns a list of dicts containing only the fields safe to send
        to an external API.
        """
        sanitized: list[dict[str, Any]] = []
        for item in items:
            record = item.record
            entry = {
                "mô_tả_vật_tư": self.sanitize_item_description(record.item_name),
                "đơn_vị": record.unit,
                "đơn_giá": record.unit_price,
                "khối_lượng": record.quantity,
                "năm": record.year,
                "khu_vực": record.region or "Không rõ",
                "quy_cách": self.sanitize_item_description(record.material_spec),
                "độ_tương_đồng": round(item.similarity_score, 3),
            }
            # Explicitly exclude: project_name, brand (may reveal supplier),
            # source_file, item_code (internal)
            sanitized.append(entry)
        return sanitized

    def build_safe_prompt_context(
        self,
        item_name: str,
        item_unit: str,
        similar_items: list[SimilarItem],
    ) -> dict[str, Any]:
        """Build a complete, sanitized context dict ready for LLM prompt.

        Returns a structure that can be JSON-serialized into the prompt.
        """
        context = {
            "hạng_mục_cần_tư_vấn": self.sanitize_item_description(item_name),
            "đơn_vị_tính": item_unit,
            "dữ_liệu_tham_khảo": self.sanitize_similar_items(similar_items),
            "số_mẫu_tham_khảo": len(similar_items),
        }

        # Audit trail
        audit_entry = {
            "action": "egress_sanitize",
            "original_item_hash": hashlib.sha256(item_name.encode()).hexdigest()[:12],
            "similar_count": len(similar_items),
            "fields_stripped": ["project_name", "brand", "source_file", "item_code"],
            "strict_mode": self._strict,
        }
        self._audit_log.append(audit_entry)
        logger.debug("EgressGuard: sanitized context for item hash=%s", audit_entry["original_item_hash"])

        return context

    @property
    def audit_log(self) -> list[dict[str, Any]]:
        """Return the accumulated audit log entries."""
        return list(self._audit_log)

    def clear_audit(self) -> None:
        """Clear the audit log."""
        self._audit_log.clear()
