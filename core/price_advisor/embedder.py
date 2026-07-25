"""Multi-provider text embedder for PriceAdvisor vector search.

Supports OpenAI, Google Gemini and local sentence-transformers models.
The local backend requires ``sentence-transformers`` to be installed
separately (see requirements-price-advisor.txt).
"""
from __future__ import annotations

import logging
from typing import Optional

from .config import PriceAdvisorConfig

logger = logging.getLogger(__name__)


class Embedder:
    """Generate text embeddings via the configured provider."""

    def __init__(self, config: PriceAdvisorConfig) -> None:
        self._config = config
        self._provider = config.embedding_provider
        self._model = config.embedding_model
        self._api_key = config.embedding_api_key or config.api_key
        self._dimensions = config.embedding_dimensions
        self._local_model = None  # lazy-loaded for local backend

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def embed_text(self, text: str) -> list[float]:
        """Embed a single text string and return its vector."""
        results = self.embed_batch([text])
        return results[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts and return their vectors."""
        if not texts:
            return []

        # Normalize whitespace
        cleaned = [" ".join(t.split()) for t in texts]

        if self._provider == "openai":
            return self._embed_openai(cleaned)
        elif self._provider == "google":
            return self._embed_google(cleaned)
        elif self._provider == "local":
            return self._embed_local(cleaned)
        elif self._provider == "none":
            return [[0.0] * self._dimensions for _ in cleaned]
        else:
            raise ValueError(f"Unsupported embedding provider: {self._provider}")

    # ------------------------------------------------------------------
    # Provider implementations
    # ------------------------------------------------------------------

    def _embed_openai(self, texts: list[str]) -> list[list[float]]:
        """Embed via OpenAI API (also works with any OpenAI-compatible endpoint)."""
        try:
            # pyrefly: ignore [missing-import]
            from openai import OpenAI
        except ImportError:
            raise ImportError("Cài gói 'openai' để dùng OpenAI embeddings: pip install openai")

        client = OpenAI(
            api_key=self._api_key,
            base_url=self._config.base_url or None,
        )
        response = client.embeddings.create(
            model=self._model,
            input=texts,
            dimensions=self._dimensions,
        )
        # Sort by index to guarantee order
        sorted_data = sorted(response.data, key=lambda x: x.index)
        return [item.embedding for item in sorted_data]

    def _embed_google(self, texts: list[str]) -> list[list[float]]:
        """Embed via Google Generative AI (Gemini) API."""
        try:
            from google import genai
        except ImportError:
            raise ImportError("Cài gói 'google-genai' để dùng Google embeddings: pip install google-genai")

        client = genai.Client(api_key=self._api_key)
        results: list[list[float]] = []
        # Google API processes one text at a time for embed_content
        for text in texts:
            response = client.models.embed_content(
                model=self._model,
                contents=text,
            )
            results.append(list(response.embeddings[0].values))
        return results

    def _embed_local(self, texts: list[str]) -> list[list[float]]:
        """Embed via a local sentence-transformers model (e.g. bge-m3)."""
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "Cài gói 'sentence-transformers' để dùng local embeddings: "
                "pip install sentence-transformers"
            )

        if self._local_model is None:
            logger.info("Loading local embedding model: %s", self._model)
            self._local_model = SentenceTransformer(self._model)
            logger.info("Local embedding model loaded successfully")

        embeddings = self._local_model.encode(texts, normalize_embeddings=True)
        return [emb.tolist() for emb in embeddings]
