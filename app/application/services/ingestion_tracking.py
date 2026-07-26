from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

# Bookkeeping for the ingestion process: idempotency (checksums) and stage
# progress (status) are both small, in-memory concerns of the same capability
# -- tracking what has happened to a document as it moves through ingestion.


class IncrementalProcessingService:
    """Track checksums and decide whether a document should be skipped or reprocessed."""

    def __init__(self) -> None:
        self._checksums: dict[str, str] = {}

    def compute_checksum(self, path: str | Path) -> str:
        file_path = Path(path)
        return hashlib.sha256(file_path.read_bytes()).hexdigest()

    def should_skip(self, path: str | Path, checksum: str) -> bool:
        file_path = Path(path)
        current_checksum = self.compute_checksum(file_path)
        previous_checksum = self._checksums.get(str(file_path))
        return previous_checksum is not None and previous_checksum == checksum and checksum == current_checksum

    def mark_processed(self, path: str | Path, checksum: str) -> None:
        self._checksums[str(Path(path))] = checksum


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
