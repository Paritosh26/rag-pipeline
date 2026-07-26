from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """Abstraction for embedding providers so the system can evolve beyond one model."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return embeddings for a batch of texts."""


class SentenceTransformerEmbeddingProvider(EmbeddingProvider):
    """Sentence-transformers implementation used by the default pipeline."""

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, convert_to_tensor=False).tolist()
