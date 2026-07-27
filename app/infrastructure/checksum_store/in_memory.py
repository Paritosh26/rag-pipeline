from __future__ import annotations

from app.infrastructure.checksum_store.base import ChecksumStore


class InMemoryChecksumStore(ChecksumStore):
    """In-memory checksum store used when no database backend is available.

    State does not survive a process restart -- this is a fallback, not a
    substitute for PostgresChecksumStore.
    """

    def __init__(self) -> None:
        self._checksums: dict[tuple[str, str], str] = {}

    def initialize(self) -> None:
        return None

    def get_checksum(self, path: str, collection: str) -> str | None:
        return self._checksums.get((path, collection))

    def set_checksum(self, path: str, collection: str, checksum: str) -> None:
        self._checksums[(path, collection)] = checksum
