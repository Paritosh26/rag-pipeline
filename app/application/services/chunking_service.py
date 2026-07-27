from __future__ import annotations

from typing import Any, List

from app.domain.models import Chunk


class ChunkingService:
    """Split text into manageable chunks for embedding and retrieval."""

    def __init__(self, chunk_size: int = 500, overlap: int = 100) -> None:
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_text(self, text: str, source_id: str, document_metadata: dict[str, Any] | None = None) -> List[Chunk]:
        """Create overlapping chunks from a document body."""
        if not text.strip():
            return []

        document_metadata = document_metadata or {}
        normalized = ' '.join(text.split())
        step = max(self.chunk_size - self.overlap, 1)
        chunks: List[Chunk] = []
        start = 0
        index = 0

        while start < len(normalized):
            end = start + self.chunk_size
            piece = normalized[start:end]
            if not piece:
                break
            chunks.append(
                Chunk(
                    content=piece,
                    source_id=source_id,
                    chunk_index=index,
                    metadata={
                        'title': document_metadata.get('title'),
                        'authors': document_metadata.get('authors'),
                        'publication_year': document_metadata.get('publication_year'),
                        'char_start': start,
                        'char_end': end,
                    },
                )
            )
            if end >= len(normalized):
                break
            start += step
            index += 1

        return chunks
