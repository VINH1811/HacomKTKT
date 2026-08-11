"""PriceAdvisor — LLM-powered RAG price suggestion module.

This package adds AI-based price suggestions to the existing tender
comparison workflow.  It is disabled by default and has zero impact on
the core system until ``PRICE_ADVISOR_ENABLED=1`` is set in ``.env``.

Quick start
-----------
1. Set ``PRICE_ADVISOR_ENABLED=1`` and ``PRICE_ADVISOR_API_KEY=sk-...``
   in your ``.env`` file.
2. Import historical price data::

       python scripts/import_price_data.py --input prices.xlsx

3. Run a comparison as usual.  Price suggestions will appear in the
   result panel if the advisor is enabled and the price database has
   data.

Architecture
------------
::

    ComparisonEngine (Phase 1)
        │ detects items lacking prices
        ▼
    PriceAdvisor (this module)
        ├── Embedder      → vector embedding (OpenAI / Google / local)
        ├── PriceDatabase  → SQLite + cosine similarity search
        ├── EgressGuard    → anonymize before sending to LLM
        ├── LLMClient      → multi-provider (OpenAI / Anthropic / Google)
        └── Validator      → hallucination detection & sanity checks
"""
from .advisor import PriceAdvisor
from .config import PriceAdvisorConfig
from .database import PriceDatabase
from .egress_guard import EgressGuard
from .models import AdvisorResult, PriceSuggestion, SuggestionStatus

__all__ = [
    "PriceAdvisor",
    "PriceAdvisorConfig",
    "PriceDatabase",
    "EgressGuard",
    "AdvisorResult",
    "PriceSuggestion",
    "SuggestionStatus",
]
