import io
from pathlib import Path
from unittest.mock import Mock

from Bio import Entrez

from app.infrastructure.pubmed.entrez_fetcher import EntrezPubMedFetcher


def test_fetch_and_save_writes_one_file_per_pmid(tmp_path: Path, monkeypatch) -> None:
    raw_text = 'PMID- 111\nTI  - First.\n\nPMID- 222\nTI  - Second.\n'

    esearch_mock = Mock(return_value=io.StringIO())
    efetch_mock = Mock(return_value=io.StringIO(raw_text))
    monkeypatch.setattr(Entrez, 'esearch', esearch_mock)
    monkeypatch.setattr(Entrez, 'efetch', efetch_mock)
    monkeypatch.setattr(Entrez, 'read', lambda handle: {'IdList': ['111', '222']})

    fetcher = EntrezPubMedFetcher(email='test@example.com', raw_data_root=tmp_path)
    written = fetcher.fetch_and_save('sickle cell disease', 'sickle_cell', max_results=5)

    assert {p.name for p in written} == {'pubmed-111.txt', 'pubmed-222.txt'}
    first = (tmp_path / 'sickle_cell' / 'pubmed-111.txt').read_text(encoding='utf-8')
    second = (tmp_path / 'sickle_cell' / 'pubmed-222.txt').read_text(encoding='utf-8')
    assert first == 'PMID- 111\nTI  - First.\n\n'
    assert second == 'PMID- 222\nTI  - Second.\n'
    esearch_mock.assert_called_once_with(db='pubmed', term='sickle cell disease', retmax=5)


def test_fetch_and_save_returns_empty_list_on_zero_results(tmp_path: Path, monkeypatch) -> None:
    esearch_mock = Mock(return_value=io.StringIO())
    efetch_mock = Mock(return_value=io.StringIO(''))
    monkeypatch.setattr(Entrez, 'esearch', esearch_mock)
    monkeypatch.setattr(Entrez, 'efetch', efetch_mock)
    monkeypatch.setattr(Entrez, 'read', lambda handle: {'IdList': []})

    fetcher = EntrezPubMedFetcher(email='test@example.com', raw_data_root=tmp_path)
    written = fetcher.fetch_and_save('an obscure query with no hits', 'sickle_cell')

    assert written == []
    efetch_mock.assert_not_called()


def test_fetch_and_save_creates_collection_directory_if_missing(tmp_path: Path, monkeypatch) -> None:
    raw_text = 'PMID- 333\nTI  - Third.\n'
    monkeypatch.setattr(Entrez, 'esearch', Mock(return_value=io.StringIO()))
    monkeypatch.setattr(Entrez, 'efetch', Mock(return_value=io.StringIO(raw_text)))
    monkeypatch.setattr(Entrez, 'read', lambda handle: {'IdList': ['333']})

    fetcher = EntrezPubMedFetcher(email='test@example.com', raw_data_root=tmp_path)
    target_dir = tmp_path / 'new_collection'
    assert not target_dir.exists()

    written = fetcher.fetch_and_save('query', 'new_collection')

    assert target_dir.exists()
    assert written == [target_dir / 'pubmed-333.txt']


def test_fetch_and_save_sets_entrez_email_and_api_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(Entrez, 'email', None, raising=False)
    monkeypatch.setattr(Entrez, 'api_key', None, raising=False)
    monkeypatch.setattr(Entrez, 'esearch', Mock(return_value=io.StringIO()))
    monkeypatch.setattr(Entrez, 'efetch', Mock(return_value=io.StringIO('')))
    monkeypatch.setattr(Entrez, 'read', lambda handle: {'IdList': []})

    fetcher = EntrezPubMedFetcher(email='test@example.com', api_key='secret-key', raw_data_root=tmp_path)
    fetcher.fetch_and_save('query', 'sickle_cell')

    assert Entrez.email == 'test@example.com'
    assert Entrez.api_key == 'secret-key'


def test_fetch_and_save_batches_single_efetch_call_for_multiple_ids(tmp_path: Path, monkeypatch) -> None:
    raw_text = 'PMID- 1\nTI  - A.\n\nPMID- 2\nTI  - B.\n\nPMID- 3\nTI  - C.\n'
    efetch_mock = Mock(return_value=io.StringIO(raw_text))
    monkeypatch.setattr(Entrez, 'esearch', Mock(return_value=io.StringIO()))
    monkeypatch.setattr(Entrez, 'efetch', efetch_mock)
    monkeypatch.setattr(Entrez, 'read', lambda handle: {'IdList': ['1', '2', '3']})

    fetcher = EntrezPubMedFetcher(email='test@example.com', raw_data_root=tmp_path)
    fetcher.fetch_and_save('query', 'sickle_cell')

    assert efetch_mock.call_count == 1
    efetch_mock.assert_called_once_with(db='pubmed', id='1,2,3', rettype='medline', retmode='text')
