from pathlib import Path

import fitz
import pytest

from app.application.services.answer_service import AnswerService
from app.application.services.chunking_service import ChunkingService
from app.application.services.extraction_service import ExtractionService
from app.application.services.retrieval_service import RetrievalService
from app.domain.models import RetrievedChunk
from app.infrastructure.vector_store.in_memory import InMemoryVectorStore, _cosine_similarity


class StubEmbeddingProvider:
    def embed(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]


class EmptyVectorStore:
    def initialize(self) -> None:
        return None

    def upsert(self, chunks, embeddings) -> None:
        return None

    def search(self, query_embedding, top_k):
        return []


class OneChunkVectorStore(EmptyVectorStore):
    def search(self, query_embedding, top_k):
        return [RetrievedChunk(content='context snippet', source_id='doc-1', score=0.95)]


class FailingLLMProvider:
    def generate(self, prompt: str) -> str:
        raise RuntimeError('provider unavailable')


def _retrieval_service(store) -> RetrievalService:
    return RetrievalService(embedding_provider=StubEmbeddingProvider(), vector_store=store, top_k=3)


def test_answer_falls_back_to_extractive_answer_when_llm_raises() -> None:
    service = AnswerService(
        retrieval_service=_retrieval_service(OneChunkVectorStore()),
        llm_provider=FailingLLMProvider(),
    )

    payload = service.answer('What is this?')

    assert payload['answer'].startswith('Based on the retrieved context')
    assert payload['lineage']['retrieved_chunk_count'] == 1


def test_retrieve_returns_empty_list_when_nothing_matches() -> None:
    assert _retrieval_service(EmptyVectorStore()).retrieve('anything') == []


def test_extract_text_rejects_unsupported_file_types(tmp_path: Path) -> None:
    unsupported = tmp_path / 'notes.docx'
    unsupported.write_text('x', encoding='utf-8')

    with pytest.raises(ValueError, match='Unsupported file type'):
        ExtractionService().extract_text_from_path(unsupported)


def test_extract_text_reads_pdf_pages(tmp_path: Path) -> None:
    pdf_path = tmp_path / 'paper.pdf'
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), 'Sickle cell crisis management')
    document.save(pdf_path)
    document.close()

    content = ExtractionService().extract_text_from_path(pdf_path)

    assert 'Sickle cell crisis management' in content


def test_clean_text_returns_empty_string_for_empty_input() -> None:
    assert ExtractionService().clean_text('') == ''


def test_chunking_returns_no_chunks_for_blank_text() -> None:
    assert ChunkingService().chunk_text('   ', source_id='doc-1') == []


def test_cosine_similarity_is_zero_for_a_zero_vector() -> None:
    assert _cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_in_memory_store_search_returns_empty_before_any_upsert() -> None:
    store = InMemoryVectorStore()
    store.initialize()

    assert store.search([0.1, 0.2], top_k=3) == []
