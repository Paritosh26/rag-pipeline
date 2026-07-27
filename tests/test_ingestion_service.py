from pathlib import Path

from app.application.services.ingestion_service import IngestionService
from app.domain.models import Chunk


class StubExtractionService:
    supported_extensions = ('.pdf', '.txt')

    def extract_text_from_path(self, path) -> str:
        return f'content of {Path(path).name}'

    def extract_metadata(self, path, text=None) -> dict:
        return {
            'title': 'Stub Title',
            'authors': ['Stub Author'],
            'keywords': [],
            'publication_year': 2020,
            'source_file': str(path),
        }


class StubChunkingService:
    def chunk_text(self, text: str, source_id: str, document_metadata=None):
        return [Chunk(content=text, source_id=source_id, chunk_index=0, metadata=document_metadata or {})]


class StubEmbeddingProvider:
    def embed(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]


class StubVectorStore:
    def __init__(self) -> None:
        self.upserted_chunks: list[Chunk] = []
        self.upserted_embeddings: list[list[float]] = []
        self.deleted_sources: list[str] = []

    def initialize(self) -> None:
        return None

    def delete_by_source(self, source_id: str) -> None:
        self.deleted_sources.append(source_id)
        self.upserted_chunks = [chunk for chunk in self.upserted_chunks if chunk.source_id != source_id]

    def upsert(self, chunks, embeddings) -> None:
        self.upserted_chunks.extend(chunks)
        self.upserted_embeddings.extend(embeddings)


_UNSET = object()


def _build_service(extraction_service=_UNSET, **overrides) -> tuple[IngestionService, StubVectorStore]:
    vector_store = overrides.pop('vector_store', None) or StubVectorStore()
    service = IngestionService(
        chunking_service=overrides.pop('chunking_service', None) or StubChunkingService(),
        embedding_provider=overrides.pop('embedding_provider', None) or StubEmbeddingProvider(),
        vector_store=vector_store,
        extraction_service=StubExtractionService() if extraction_service is _UNSET else extraction_service,
        **overrides,
    )
    return service, vector_store


def test_index_document_extracts_chunks_embeds_and_stores(tmp_path: Path) -> None:
    file_path = tmp_path / 'paper.txt'
    file_path.write_text('unused - StubExtractionService supplies the content', encoding='utf-8')

    service, vector_store = _build_service()
    document = service.index_document(str(file_path))

    assert document.source_id == 'paper'
    assert document.title == 'Stub Title'
    assert len(vector_store.upserted_chunks) == 1
    assert vector_store.upserted_embeddings == [[0.1, 0.2, 0.3]]
    assert vector_store.upserted_chunks[0].metadata['title'] == 'Stub Title'
    assert vector_store.upserted_chunks[0].metadata['authors'] == ['Stub Author']
    assert vector_store.upserted_chunks[0].metadata['publication_year'] == 2020


def test_index_folder_indexes_all_supported_files(tmp_path: Path) -> None:
    folder = tmp_path / 'disease-data'
    folder.mkdir()
    (folder / 'paper1.txt').write_text('first document', encoding='utf-8')
    (folder / 'paper2.pdf').write_text('second document', encoding='utf-8')
    (folder / 'notes.md').write_text('ignored', encoding='utf-8')

    service, _ = _build_service()

    documents = service.index_folder(str(folder))

    assert len(documents) == 2
    assert {document.source_id for document in documents} == {'paper1', 'paper2'}


def test_process_document_runs_end_to_end_with_metadata_and_status(tmp_path: Path) -> None:
    file_path = tmp_path / 'paper.txt'
    file_path.write_text('Title: Diabetes Study. Authors: Alice Brown. This is a sufficiently long document for processing.', encoding='utf-8')

    service, vector_store = _build_service(min_document_length=10, extraction_service=None)

    result = service.process_document(str(file_path), collection_name='diabetes')

    assert result.source_id == 'paper'
    assert result.metadata['collection'] == 'diabetes'
    assert result.metadata['title'] == 'Diabetes Study'
    assert result.metadata['authors'] == ['Alice Brown']
    assert result.metadata['bronze_status'] == 'completed'
    assert result.metadata['silver_status'] == 'completed'
    assert result.metadata['gold_status'] == 'completed'
    assert len(vector_store.upserted_chunks) == 1
    assert vector_store.upserted_chunks[0].source_id == 'paper'


def test_index_document_replaces_existing_chunks_for_same_source(tmp_path: Path) -> None:
    file_path = tmp_path / 'paper.txt'
    file_path.write_text('unused - StubExtractionService supplies the content', encoding='utf-8')

    service, vector_store = _build_service()

    service.index_document(str(file_path))
    service.index_document(str(file_path))

    assert vector_store.deleted_sources == ['paper', 'paper']
    assert len(vector_store.upserted_chunks) == 1


def test_process_document_skips_unchanged_files_on_reprocessing(tmp_path: Path) -> None:
    file_path = tmp_path / 'paper.txt'
    file_path.write_text('This is a sufficiently long document for processing twice.', encoding='utf-8')

    service, vector_store = _build_service(min_document_length=10, extraction_service=None)

    first = service.process_document(str(file_path), collection_name='diabetes')
    second = service.process_document(str(file_path), collection_name='diabetes')

    assert first.metadata.get('skipped') is None
    assert second.metadata['skipped'] is True
    assert len(vector_store.upserted_chunks) == 1
