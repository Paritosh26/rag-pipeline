from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class Document:
    """Represents an ingested source document."""

    source_id: str
    title: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        content: str,
        metadata: dict[str, Any] | None = None,
        title: str | None = None,
    ) -> 'Document':
        """Build a document identified by a file's stem, the ingestion-wide convention."""
        file_path = Path(path)
        return cls(
            source_id=file_path.stem,
            title=title or file_path.stem,
            content=content,
            metadata=metadata if metadata is not None else {},
        )


@dataclass(slots=True)
class Chunk:
    """Represents a chunk of a document ready for indexing."""

    content: str
    source_id: str
    chunk_index: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RetrievedChunk:
    """Represents a retrieved chunk with its similarity score."""

    content: str
    source_id: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_chunk(cls, chunk: Chunk, score: float) -> 'RetrievedChunk':
        return cls(content=chunk.content, source_id=chunk.source_id, score=score, metadata=chunk.metadata)
