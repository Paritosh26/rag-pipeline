from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.domain.models import Document
from app.presentation import api


@dataclass
class FakeIngestionService:
    calls: list[tuple[str, Any]] = field(default_factory=list)
    error: Exception | None = None

    def _document(self, source_id: str) -> Document:
        return Document(source_id=source_id, title='T', content='text', metadata={'title': 'T'})

    def index_document(self, path: str) -> Document:
        self.calls.append(('index_document', path))
        if self.error:
            raise self.error
        return self._document('doc-1')

    def index_folder(self, folder_path: str) -> list[Document]:
        self.calls.append(('index_folder', folder_path))
        if self.error:
            raise self.error
        return [self._document('doc-1'), self._document('doc-2')]

    def process_document(self, path: str, collection_name: str) -> Document:
        self.calls.append(('process_document', (path, collection_name)))
        if self.error:
            raise self.error
        return self._document('doc-1')


@dataclass
class FakeAnswerService:
    error: Exception | None = None
    questions: list[str] = field(default_factory=list)

    def answer(self, question: str) -> dict[str, object]:
        self.questions.append(question)
        if self.error:
            raise self.error
        return {'answer': 'A', 'citations': [], 'lineage': {'question': question}}


@dataclass
class FakeServices:
    ingestion: FakeIngestionService
    answer: FakeAnswerService


@pytest.fixture
def services() -> FakeServices:
    return FakeServices(ingestion=FakeIngestionService(), answer=FakeAnswerService())


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, services: FakeServices) -> TestClient:
    resolved: list[str | None] = []

    def fake_resolve_services(collection_name: str | None, app_state: dict[str, Any]) -> FakeServices:
        resolved.append(collection_name)
        return services

    monkeypatch.setattr(api, 'resolve_services', fake_resolve_services)
    test_client = TestClient(api.app)
    test_client.resolved_collections = resolved  # type: ignore[attr-defined]
    return test_client


def test_health_check_returns_ok(client: TestClient) -> None:
    response = client.get('/health')

    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


def test_index_document_returns_source_id(client: TestClient, services: FakeServices) -> None:
    response = client.post('/index', json={'path': 'data/raw/a.txt', 'collection': 'sickle_cell'})

    assert response.status_code == 200
    assert response.json() == {'status': 'indexed', 'source_id': 'doc-1'}
    assert services.ingestion.calls == [('index_document', 'data/raw/a.txt')]
    assert client.resolved_collections == ['sickle_cell']


def test_endpoints_fall_back_to_configured_collection(client: TestClient) -> None:
    client.post('/index', json={'path': 'data/raw/a.txt'})

    assert client.resolved_collections == [api.settings.collection_name]


def test_query_returns_answer_payload(client: TestClient, services: FakeServices) -> None:
    response = client.post('/query', json={'question': 'Why?', 'collection': 'sickle_cell'})

    assert response.status_code == 200
    assert response.json()['answer'] == 'A'
    assert services.answer.questions == ['Why?']


def test_ingest_folder_reports_count_and_sources(client: TestClient, services: FakeServices) -> None:
    response = client.post('/ingest-folder', json={'folder_path': 'data/raw/sickle_cell'})

    assert response.status_code == 200
    assert response.json() == {'status': 'ingested', 'count': 2, 'sources': ['doc-1', 'doc-2']}
    assert services.ingestion.calls == [('index_folder', 'data/raw/sickle_cell')]


def test_ingest_pipeline_passes_collection_and_returns_metadata(client: TestClient, services: FakeServices) -> None:
    response = client.post('/ingest-pipeline', json={'path': 'a.txt', 'collection': 'sickle_cell'})

    assert response.status_code == 200
    assert response.json() == {'status': 'processed', 'source_id': 'doc-1', 'metadata': {'title': 'T'}}
    assert services.ingestion.calls == [('process_document', ('a.txt', 'sickle_cell'))]


@pytest.mark.parametrize(
    ('path', 'payload'),
    [
        ('/index', {'path': 'a.txt'}),
        ('/query', {'question': 'Why?'}),
        ('/ingest-folder', {'folder_path': 'data/raw'}),
        ('/ingest-pipeline', {'path': 'a.txt'}),
    ],
)
def test_service_failures_become_http_500(
    client: TestClient, services: FakeServices, path: str, payload: dict[str, str]
) -> None:
    services.ingestion.error = RuntimeError('boom')
    services.answer.error = RuntimeError('boom')

    response = client.post(path, json=payload)

    assert response.status_code == 500
    assert response.json() == {'detail': 'boom'}


def test_requests_are_rejected_when_required_fields_are_missing(client: TestClient) -> None:
    assert client.post('/query', json={}).status_code == 422


def test_resolve_services_defaults_to_configured_collection(monkeypatch: pytest.MonkeyPatch) -> None:
    built: list[str] = []

    def fake_build_services(collection_name: str) -> str:
        built.append(collection_name)
        return f'services:{collection_name}'

    monkeypatch.setattr(api, 'build_services', fake_build_services)
    app_state: dict[str, Any] = {}

    result = api.resolve_services(None, app_state)

    assert result == f'services:{api.settings.collection_name}'
    assert built == [api.settings.collection_name]
    assert app_state['services_by_collection'] == {api.settings.collection_name: result}
