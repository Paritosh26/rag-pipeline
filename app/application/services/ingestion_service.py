from __future__ import annotations

import logging
from pathlib import Path

from app.application.services.chunking_service import ChunkingService
from app.application.services.extraction_service import ExtractionService
from app.application.services.ingestion_tracking import IncrementalProcessingService, IngestionStatusService
from app.domain.models import Document
from app.infrastructure.embedding.base import EmbeddingProvider
from app.infrastructure.vector_store.base import VectorStore

logger = logging.getLogger(__name__)


class IngestionService:
    """Turn source files into searchable, embedded chunks.

    Two entry points cover the same underlying capability at different levels
    of rigor:
      - `index_document` / `index_folder`: quick extract -> chunk -> embed -> store.
      - `process_document`: adds checksum-based skip, metadata extraction, and
        bronze/silver/gold stage tracking for observability during larger ingests.
    Both share the same extraction, chunking, embedding, and storage building blocks.
    """

    def __init__(
        self,
        chunking_service: ChunkingService,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
        extraction_service: ExtractionService | None = None,
        min_document_length: int = 20,
    ) -> None:
        self.chunking_service = chunking_service
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store
        self.extraction_service = extraction_service or ExtractionService()
        self.min_document_length = min_document_length
        self.incremental_processing = IncrementalProcessingService()
        self.status = IngestionStatusService()

    def index_document(self, path: str | Path) -> Document:
        """Extract, chunk, embed, and store a single document."""
        self.vector_store.initialize()
        file_path = Path(path)
        text = self.extraction_service.extract_text_from_path(file_path)
        document = Document.from_path(file_path, content=text, metadata={'path': str(file_path)})
        self._embed_and_store(document)
        return document

    def index_folder(self, folder_path: str | Path) -> list[Document]:
        """Index every supported file in a folder."""
        folder = Path(folder_path)
        if not folder.exists():
            raise FileNotFoundError(folder_path)

        documents = [
            self.index_document(str(path))
            for path in sorted(folder.iterdir())
            if path.is_file() and path.suffix.lower() in self.extraction_service.supported_extensions
        ]
        logger.info('Ingested %d document(s) from folder %s', len(documents), folder_path)
        return documents

    def process_document(self, path: str | Path, collection_name: str) -> Document:
        """Ingest a document with checksum-based skip and staged status tracking."""
        file_path = Path(path)
        checksum = self.incremental_processing.compute_checksum(file_path)
        if self.incremental_processing.should_skip(file_path, checksum):
            logger.info('Skipping unchanged document %s (checksum match)', file_path.stem)
            self.status.mark_all_completed(file_path.stem)
            return Document.from_path(file_path, content='', metadata={'skipped': True, 'checksum': checksum})

        with self.status.track(file_path.stem, 'bronze'):
            text = self.extraction_service.extract_text_from_path(file_path)
            if len(text) < self.min_document_length:
                raise ValueError(f'Document too short for ingestion: {file_path}')

        with self.status.track(file_path.stem, 'silver'):
            metadata = self.extraction_service.extract_metadata(file_path, text)
            metadata['collection'] = collection_name
            metadata['cleaned_length'] = len(text)

        document = Document.from_path(file_path, content=text, metadata=metadata, title=metadata.get('title'))
        self.incremental_processing.mark_processed(file_path, checksum)

        with self.status.track(file_path.stem, 'gold'):
            self._embed_and_store(document)

        document.metadata.update(self.status.stage_statuses(document.source_id))
        logger.info('Processed document %s through bronze/silver/gold (collection=%s)', document.source_id, collection_name)
        return document

    def _embed_and_store(self, document: Document) -> None:
        chunks = self.chunking_service.chunk_text(document.content, source_id=document.source_id)
        if not chunks:
            logger.warning('Document %s produced 0 chunks; nothing embedded or stored', document.source_id)
            return
        embeddings = self.embedding_provider.embed([chunk.content for chunk in chunks])
        self.vector_store.upsert(chunks, embeddings)
        logger.info('Embedded and stored %d chunk(s) for document %s', len(chunks), document.source_id)
