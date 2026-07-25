"""Configuration for the PriceAdvisor module.

All settings are read from environment variables with sensible defaults.
The module is disabled by default (PRICE_ADVISOR_ENABLED=0) so it has
zero impact on the existing HacomKTKT system until explicitly turned on.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool_env(name: str, default: bool) -> bool:
    return os.getenv(name, "1" if default else "0").strip().lower() not in {"0", "false", "no", "off"}


def _int_env(name: str, default: int, minimum: int = 1, maximum: int = 10000) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _float_env(name: str, default: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


@dataclass
class PriceAdvisorConfig:
    """Configuration for the PriceAdvisor RAG + LLM module."""

    # Master switch — disabled by default
    enabled: bool = False

    # LLM provider and model
    llm_provider: str = "openai"            # openai | anthropic | google | ollama
    llm_model: str = "gpt-4.1-mini"         # model name
    api_key: str = ""                        # API key for the chosen provider
    base_url: str = ""                       # Custom endpoint (for self-host / vLLM / Ollama)
    llm_temperature: float = 0.1            # Low temperature for factual output
    llm_max_tokens: int = 1024              # Max tokens in LLM response
    llm_timeout_seconds: int = 60           # Request timeout
    llm_think: bool = False                 # Ollama reasoning toggle

    # Embedding provider and model
    embedding_provider: str = "openai"       # openai | google | local | none
    embedding_model: str = "text-embedding-3-small"
    embedding_api_key: str = ""              # Separate key for embedding (falls back to api_key)
    embedding_dimensions: int = 512          # Vector dimensions (lower = faster search)

    # Database Configuration
    # Default to sqlite to make the module runnable out-of-the-box in local/offline setups.
    db_provider: str = "sqlite"              # postgres | sqlite
    db_path: Path = Path("data/price_db.sqlite")
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "hacom_ktkt"
    db_user: str = "postgres"
    db_password: str = "postgres"

    # RAG parameters
    max_similar_results: int = 5             # Top-K similar items to retrieve
    confidence_threshold: float = 0.6        # Minimum confidence to display suggestion
    max_price_deviation: float = 5.0         # Max allowed deviation from RAG median (multiplier)

    # Behavior
    auto_trigger: bool = False               # Auto-run after comparison completes
    max_items_per_batch: int = 50            # Max items to process in one batch

    @classmethod
    def from_env(cls) -> PriceAdvisorConfig:
        """Build configuration from environment variables."""
        llm_provider = os.getenv("PRICE_ADVISOR_LLM_PROVIDER", "openai").strip().lower()
        if llm_provider not in {"openai", "anthropic", "google", "ollama"}:
            llm_provider = "openai"

        embedding_provider = os.getenv("PRICE_ADVISOR_EMBEDDING_PROVIDER", "openai").strip().lower()
        if embedding_provider not in {"openai", "google", "local", "none"}:
            embedding_provider = "openai"

        api_key = os.getenv("PRICE_ADVISOR_API_KEY", "")

        # Default to sqlite for local/offline usage.
        db_provider = os.getenv("PRICE_ADVISOR_DB_PROVIDER", "sqlite").strip().lower()
        if db_provider not in {"postgres", "sqlite"}:
            db_provider = "sqlite"

        return cls(
            enabled=_bool_env("PRICE_ADVISOR_ENABLED", False),
            llm_provider=llm_provider,
            llm_model=os.getenv("PRICE_ADVISOR_LLM_MODEL", "gpt-4.1-mini").strip(),
            api_key=api_key,
            base_url=os.getenv("PRICE_ADVISOR_BASE_URL", "").strip(),
            llm_temperature=_float_env("PRICE_ADVISOR_LLM_TEMPERATURE", 0.1, 0.0, 2.0),
            llm_max_tokens=_int_env("PRICE_ADVISOR_LLM_MAX_TOKENS", 1024, 128, 8192),
            llm_timeout_seconds=_int_env("PRICE_ADVISOR_LLM_TIMEOUT", 60, 5, 1200),
            llm_think=_bool_env("PRICE_ADVISOR_LLM_THINK", False),
            embedding_provider=embedding_provider,
            embedding_model=os.getenv("PRICE_ADVISOR_EMBEDDING_MODEL", "text-embedding-3-small").strip(),
            embedding_api_key=os.getenv("PRICE_ADVISOR_EMBEDDING_API_KEY", "") or api_key,
            embedding_dimensions=_int_env("PRICE_ADVISOR_EMBEDDING_DIMS", 512, 64, 4096),
            db_provider=db_provider,
            db_path=Path(os.getenv("PRICE_ADVISOR_DB_PATH", "data/price_db.sqlite")),
            db_host=os.getenv("PRICE_ADVISOR_DB_HOST", "localhost").strip(),
            db_port=_int_env("PRICE_ADVISOR_DB_PORT", 5432, 1, 65535),
            db_name=os.getenv("PRICE_ADVISOR_DB_NAME", "hacom_ktkt").strip(),
            db_user=os.getenv("PRICE_ADVISOR_DB_USER", "postgres").strip(),
            db_password=os.getenv("PRICE_ADVISOR_DB_PASSWORD", "postgres").strip(),
            max_similar_results=_int_env("PRICE_ADVISOR_MAX_RESULTS", 5, 1, 20),
            confidence_threshold=_float_env("PRICE_ADVISOR_CONFIDENCE_THRESHOLD", 0.6, 0.0, 1.0),
            max_price_deviation=_float_env("PRICE_ADVISOR_MAX_DEVIATION", 5.0, 1.0, 100.0),
            auto_trigger=_bool_env("PRICE_ADVISOR_AUTO_TRIGGER", False),
            max_items_per_batch=_int_env("PRICE_ADVISOR_MAX_BATCH", 50, 1, 500),
        )

    @property
    def is_ready(self) -> bool:
        """Check if the module has minimum config to operate."""
        if not self.enabled:
            return False
        if self.llm_provider == "ollama":
            return bool(self.llm_model)
        return bool(self.api_key)
