from pathlib import Path

from fastapi.testclient import TestClient

import app.presentation.api as api_module
from app.presentation.api import app

client = TestClient(app)


def test_fetch_pubmed_400_when_no_query_configured(monkeypatch) -> None:
    monkeypatch.setenv('PUBMED_ENTREZ_EMAIL', 'test@example.com')
    # Settings.from_yaml() does os.environ.setdefault(...) for every collection
    # field it loads, so an earlier test loading sickle_cell's pubmed_query can
    # leak it into the process env and make wilson inherit it. Guard against that.
    monkeypatch.delenv('PUBMED_QUERY', raising=False)

    response = client.post('/fetch-pubmed', json={'collection': 'wilson'})

    assert response.status_code == 400
    assert 'query' in response.json()['detail'].lower()


def test_fetch_pubmed_400_when_email_missing(monkeypatch) -> None:
    monkeypatch.delenv('PUBMED_ENTREZ_EMAIL', raising=False)

    response = client.post('/fetch-pubmed', json={'collection': 'sickle_cell', 'query': 'sickle cell disease'})

    assert response.status_code == 400
    assert 'email' in response.json()['detail'].lower()


def test_fetch_pubmed_returns_200_with_expected_shape(monkeypatch) -> None:
    monkeypatch.setenv('PUBMED_ENTREZ_EMAIL', 'test@example.com')

    class FakeFetcher:
        def __init__(self, email, api_key=None):
            self.email = email
            self.api_key = api_key

        def fetch_and_save(self, query, collection, max_results=20):
            return [Path(f'data/raw/{collection}/pubmed-123.txt')]

    monkeypatch.setattr(api_module, 'EntrezPubMedFetcher', FakeFetcher)

    response = client.post('/fetch-pubmed', json={'collection': 'sickle_cell', 'query': 'sickle cell disease'})

    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'fetched'
    assert body['collection'] == 'sickle_cell'
    assert body['count'] == 1
    assert body['files'] == ['data/raw/sickle_cell/pubmed-123.txt']
