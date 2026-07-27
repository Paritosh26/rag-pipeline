from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from app.infrastructure.checksum_store.base import ChecksumStore
from app.infrastructure.checksum_store.in_memory import InMemoryChecksumStore

# Bookkeeping for the ingestion process: idempotency (checksums) and stage
# progress (status) are both small concerns of the same capability -- tracking
# what has happened to a document as it moves through ingestion. Checksums are
# persisted via a ChecksumStore (Postgres by default, see dependencies.py) so
# skip decisions survive process restarts; status is still in-memory only.


class IncrementalProcessingService:
    """Track checksums and decide whether a document should be skipped or reprocessed."""

    def __init__(self, checksum_store: ChecksumStore | None = None) -> None:
        self.checksum_store = checksum_store or InMemoryChecksumStore()

    def compute_checksum(self, path: str | Path) -> str:
        file_path = Path(path)
        return hashlib.sha256(file_path.read_bytes()).hexdigest()

    def should_skip(self, path: str | Path, collection: str, checksum: str) -> bool:
        file_path = Path(path)
        current_checksum = self.compute_checksum(file_path)
        previous_checksum = self.checksum_store.get_checksum(str(file_path), collection)
        return previous_checksum is not None and previous_checksum == checksum and checksum == current_checksum

    def mark_processed(self, path: str | Path, collection: str, checksum: str) -> None:
        self.checksum_store.set_checksum(str(Path(path)), collection, checksum)


class IngestionStatusService:
    """Track ingestion progress across Bronze, Silver, and Gold stages."""

    _STAGES = ('bronze', 'silver', 'gold')

    def __init__(self) -> None:
        self._statuses: dict[str, dict[str, Any]] = {}

    def mark_started(self, source_id: str, stage: str) -> None:
        self._statuses.setdefault(source_id, {})[stage] = 'in_progress'

    def mark_completed(self, source_id: str, stage: str) -> None:
        self._statuses.setdefault(source_id, {})[stage] = 'completed'

    def mark_failed(self, source_id: str, stage: str, error: str) -> None:
        state = self._statuses.setdefault(source_id, {})
        state[stage] = 'failed'
        state[f'{stage}_error'] = error

    def get_status(self, source_id: str) -> dict[str, Any]:
        return self._statuses.get(source_id, {})

    def get_summary(self, source_id: str) -> dict[str, Any]:
        state = self.get_status(source_id)
        completed_stages = sum(1 for stage in self._STAGES if state.get(stage) == 'completed')
        failed_stages = [stage for stage in self._STAGES if state.get(stage) == 'failed']

        if failed_stages:
            overall = 'failed'
        elif completed_stages == len(self._STAGES):
            overall = 'completed'
        elif completed_stages > 0:
            overall = 'in_progress'
        else:
            overall = 'not_started'

        return {
            'overall': overall,
            'completed_stages': completed_stages,
            'total_stages': len(self._STAGES),
            'failed_stages': failed_stages,
        }
