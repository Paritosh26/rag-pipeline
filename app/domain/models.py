from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Document:
    """Represents an ingested source document."""

    source_id: str
    title: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


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
