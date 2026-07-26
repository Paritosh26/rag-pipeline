from __future__ import annotations

import logging

from app.infrastructure.embedding.base import EmbeddingProvider
from app.infrastructure.vector_store.base import VectorStore
from app.domain.models import RetrievedChunk

logger = logging.getLogger(__name__)


class RetrievalService:
    """Retrieve semantically similar chunks for a user query."""

    def __init__(self, embedding_provider: EmbeddingProvider, vector_store: VectorStore, top_k: int) -> None:
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store
        self.top_k = top_k

    def retrieve(self, query: str) -> list[RetrievedChunk]:
        """Convert a query into an embedding and retrieve the closest chunks."""
        self.vector_store.initialize()
        embeddings = self.embedding_provider.embed([query])
        chunks = self.vector_store.search(embeddings[0], self.top_k)

        if chunks:
            top_score = max(chunk.score for chunk in chunks)
            logger.info('Retrieved %d chunk(s) for query %r (top score %.3f)', len(chunks), query, top_score)
        else:
            logger.warning('Retrieved 0 chunks for query %r', query)

        return chunks
