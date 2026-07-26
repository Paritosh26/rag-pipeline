from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.models import Chunk, RetrievedChunk


class VectorStore(ABC):
    """Abstraction for vector persistence and retrieval."""

    @abstractmethod
    def initialize(self) -> None:
        """Prepare the storage backend."""

    @abstractmethod
    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        """Persist chunks and their vectors."""

    @abstractmethod
    def search(self, query_embedding: list[float], top_k: int) -> list[RetrievedChunk]:
        """Search for the closest chunks."""
