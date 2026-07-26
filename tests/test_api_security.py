import pytest
from fastapi.testclient import TestClient

from app.presentation import api


@pytest.fixture()
def client() -> TestClient:
    return TestClient(api.app)


def test_ingestion_path_outside_root_is_rejected(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # If path validation is bypassed this would build the service graph, so make
    # that fail loudly to prove the 400 is raised before we ever get there.
    monkeypatch.setattr(api, 'resolve_services', lambda *a, **k: pytest.fail('service graph should not be built'))

    response = client.post('/index', json={'path': '/etc/passwd'})

    assert response.status_code == 400
    assert 'allowed ingestion directory' in response.json()['detail']


def test_ingestion_path_traversal_is_rejected(client: TestClient) -> None:
    response = client.post('/ingest-folder', json={'folder_path': 'data/../../etc'})
    assert response.status_code == 400


def test_missing_api_key_is_rejected_when_configured(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api.settings, 'api_key', 'super-secret')

    response = client.post('/query', json={'question': 'hi'})

    assert response.status_code == 401


def test_wrong_api_key_is_rejected_when_configured(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api.settings, 'api_key', 'super-secret')

    response = client.post('/query', json={'question': 'hi'}, headers={'X-API-Key': 'nope'})

    assert response.status_code == 401


def test_health_never_requires_api_key(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api.settings, 'api_key', 'super-secret')

    response = client.get('/health')

    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


def test_internal_error_does_not_leak_exception_text(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args, **_kwargs):
        raise RuntimeError('sensitive DSN postgresql://user:pw@host/db leaked here')

    monkeypatch.setattr(api, 'resolve_services', boom)

    response = client.post('/query', json={'question': 'hi'})

    assert response.status_code == 500
    assert response.json() == {'detail': 'Internal server error'}
