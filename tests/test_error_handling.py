from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.application.services.answer_service import AnswerService
from app.application.services.ingestion_service import IngestionService
from app.application.services.retrieval_service import RetrievalService
from app.presentation import api


class StubEmbeddingProvider:
    def embed(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]


class StubVectorStore:
    def initialize(self) -> None:
        return None

    def upsert(self, chunks, embeddings) -> None:
        return None

    def search(self, query_embedding, top_k):
        return [
            type('Chunk', (), {'content': 'context snippet', 'source_id': 'doc-1', 'score': 0.95, 'metadata': {}})()
        ]


class ExplodingLLMProvider:
    def generate(self, prompt: str) -> str:
        raise RuntimeError('upstream unavailable')


def _answer_service(llm_provider):
    retrieval_service = RetrievalService(
        embedding_provider=StubEmbeddingProvider(),
        vector_store=StubVectorStore(),
        top_k=3,
    )
    return AnswerService(retrieval_service=retrieval_service, llm_provider=llm_provider)


def _client(monkeypatch, ingestion=None, answer=None):
    container = SimpleNamespace(ingestion=ingestion, answer=answer, retrieval=None)
    monkeypatch.setattr(api, 'resolve_services', lambda collection_name, app_state: container)
    return TestClient(api.app)


def test_missing_folder_returns_404(monkeypatch) -> None:
    def index_folder(folder_path):
        raise FileNotFoundError(folder_path)

    client = _client(monkeypatch, ingestion=SimpleNamespace(index_folder=index_folder))

    response = client.post('/ingest-folder', json={'folder_path': 'data/raw/nope'})

    assert response.status_code == 404
    assert 'data/raw/nope' in response.json()['detail']


def test_unsupported_file_type_returns_400(monkeypatch) -> None:
    def index_document(path):
        raise ValueError('Unsupported file type: .docx')

    client = _client(monkeypatch, ingestion=SimpleNamespace(index_document=index_document))

    response = client.post('/index', json={'path': 'paper.docx'})

    assert response.status_code == 400
    assert response.json()['detail'] == 'Unsupported file type: .docx'


def test_unexpected_failure_returns_500_without_leaking_message(monkeypatch) -> None:
    def answer(question):
        raise RuntimeError('psycopg: password authentication failed for user "postgres"')

    client = _client(monkeypatch, answer=SimpleNamespace(answer=answer))

    response = client.post('/query', json={'question': 'anything?'})

    assert response.status_code == 500
    assert 'password' not in response.json()['detail']


def test_empty_question_returns_400(monkeypatch) -> None:
    client = _client(monkeypatch, answer=SimpleNamespace(answer=lambda question: {}))

    response = client.post('/query', json={'question': '   '})

    assert response.status_code == 400


def test_answer_payload_reports_llm_failure_instead_of_hiding_it() -> None:
    payload = _answer_service(ExplodingLLMProvider()).answer('What is this?')

    assert payload['answer_source'] == 'extractive'
    assert 'upstream unavailable' in payload['lineage']['llm_error']


def test_successful_answer_reports_llm_source() -> None:
    payload = _answer_service(SimpleNamespace(generate=lambda prompt: 'real answer')).answer('What is this?')

    assert payload['answer_source'] == 'llm'
    assert payload['lineage']['llm_error'] is None


def test_failed_stage_is_recorded_and_error_propagates(tmp_path) -> None:
    document = tmp_path / 'doc.txt'
    document.write_text('short', encoding='utf-8')
    service = IngestionService(
        chunking_service=SimpleNamespace(chunk_text=lambda text, source_id: []),
        embedding_provider=StubEmbeddingProvider(),
        vector_store=StubVectorStore(),
        min_document_length=20,
    )

    with pytest.raises(ValueError):
        service.process_document(document, collection_name='test')

    assert service.status.get_status('doc')['bronze'] == 'failed'
    assert service.status.get_summary('doc')['overall'] == 'failed'


def test_folder_ingestion_propagates_file_level_failure(tmp_path) -> None:
    (tmp_path / 'a.txt').write_text('some usable content for chunking', encoding='utf-8')

    def explode(text, source_id):
        raise RuntimeError('embedding backend down')

    service = IngestionService(
        chunking_service=SimpleNamespace(chunk_text=explode),
        embedding_provider=StubEmbeddingProvider(),
        vector_store=StubVectorStore(),
    )

    with pytest.raises(RuntimeError, match='embedding backend down'):
        service.index_folder(tmp_path)
