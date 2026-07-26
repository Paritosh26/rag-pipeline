from __future__ import annotations

import math

from app.domain.models import Chunk, RetrievedChunk
from app.infrastructure.vector_store.base import VectorStore


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class InMemoryVectorStore(VectorStore):
    """In-memory vector store used when no database backend is available.

    Performs real cosine-similarity search over stored embeddings so query
    results stay correct even without Postgres/pgvector.
    """

    def __init__(self) -> None:
        self._entries: list[tuple[RetrievedChunk, list[float]]] = []

    def initialize(self) -> None:
        return None

    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            self._entries.append(
                (
                    RetrievedChunk(
                        content=chunk.content,
                        source_id=chunk.source_id,
                        score=0.0,
                        metadata=chunk.metadata,
                    ),
                    embedding,
                )
            )

    def search(self, query_embedding: list[float], top_k: int) -> list[RetrievedChunk]:
        scored = [
            (chunk, _cosine_similarity(query_embedding, embedding))
            for chunk, embedding in self._entries
        ]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return [
            RetrievedChunk(content=chunk.content, source_id=chunk.source_id, score=score, metadata=chunk.metadata)
            for chunk, score in scored[:top_k]
        ]
