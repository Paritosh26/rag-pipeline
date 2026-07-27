from __future__ import annotations

from abc import ABC, abstractmethod


class ChecksumStore(ABC):
    """Abstraction for persisting per-document, per-collection ingestion checksums."""

    @abstractmethod
    def initialize(self) -> None:
        """Prepare the storage backend."""

    @abstractmethod
    def get_checksum(self, path: str, collection: str) -> str | None:
        """Return the last recorded checksum for path/collection, or None if never processed."""

    @abstractmethod
    def set_checksum(self, path: str, collection: str, checksum: str) -> None:
        """Record the checksum for path/collection."""
