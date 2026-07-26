from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import pytest

from app.domain.models import Chunk
from app.infrastructure.vector_store.postgres import Base, PostgresVectorStore

_URL = 'postgresql+psycopg://localhost/nonexistent'


@dataclass
class FakeRow:
    source_id: str
    content: str
    chunk_metadata: str | None
    score: float


class FakeResult:
    def __init__(self, rows: list[FakeRow]) -> None:
        self._rows = rows

    def fetchall(self) -> list[FakeRow]:
        return self._rows


class FakeSession:
    def __init__(self, rows: list[FakeRow] | None = None) -> None:
        self.rows = rows or []
        self.executed: list[tuple[str, dict[str, Any]]] = []
        self.commits = 0

    def execute(self, statement: Any, params: dict[str, Any]) -> FakeResult:
        self.executed.append((str(statement), params))
        return FakeResult(self.rows)

    def commit(self) -> None:
        self.commits += 1


def _attach(store: PostgresVectorStore, session: FakeSession) -> None:
    @contextmanager
    def session_factory():
        yield session

    store.session_factory = session_factory  # type: ignore[assignment]


def _store(**kwargs: Any) -> PostgresVectorStore:
    return PostgresVectorStore(database_url=_URL, collection='sickle_cell', **kwargs)


def test_unsupported_similarity_metric_is_rejected() -> None:
    with pytest.raises(ValueError, match='Unsupported similarity_metric'):
        _store(similarity_metric='dot')


def test_initialize_creates_tables(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store()
    engines: list[Any] = []
    monkeypatch.setattr(Base.metadata, 'create_all', lambda engine: engines.append(engine))

    store.initialize()

    assert engines == [store.engine]


def test_upsert_inserts_every_chunk_scoped_to_the_collection() -> None:
    store = _store()
    session = FakeSession()
    _attach(store, session)
    chunks = [
        Chunk(content='a', source_id='doc-1', chunk_index=0, metadata={'title': 'T'}),
        Chunk(content='b', source_id='doc-1', chunk_index=1),
    ]

    store.upsert(chunks, [[0.1, 0.2], [0.3, 0.4]])

    assert session.commits == 1
    assert len(session.executed) == 2
    statement, params = session.executed[0]
    assert 'INSERT INTO document_chunks' in statement
    assert params == {
        'collection': 'sickle_cell',
        'source_id': 'doc-1',
        'chunk_index': 0,
        'content': 'a',
        'embedding': [0.1, 0.2],
        'chunk_metadata': "{'title': 'T'}",
    }


def test_upsert_rejects_mismatched_embedding_count() -> None:
    store = _store()
    _attach(store, FakeSession())

    with pytest.raises(ValueError):
        store.upsert([Chunk(content='a', source_id='doc-1', chunk_index=0)], [])


def test_search_returns_retrieved_chunks_with_parsed_metadata() -> None:
    store = _store()
    session = FakeSession(
        rows=[
            FakeRow(source_id='doc-1', content='a', chunk_metadata="{'title': 'T'}", score=0.9),
            FakeRow(source_id='doc-2', content='b', chunk_metadata=None, score=0.5),
            FakeRow(source_id='doc-3', content='c', chunk_metadata='not-a-literal', score=0.1),
        ]
    )
    _attach(store, session)

    results = store.search([0.1, 0.2], top_k=3)

    assert [r.source_id for r in results] == ['doc-1', 'doc-2', 'doc-3']
    assert [r.metadata for r in results] == [{'title': 'T'}, {}, {}]
    assert results[0].score == pytest.approx(0.9)

    statement, params = session.executed[0]
    assert 'WHERE collection = :collection' in statement
    assert params == {'query_embedding': [0.1, 0.2], 'limit': 3, 'collection': 'sickle_cell'}


@pytest.mark.parametrize(
    ('metric', 'operator', 'score_prefix'),
    [('cosine', '<=>', '1 - ('), ('l2', '<->', '-(')],
)
def test_search_uses_the_operator_for_the_configured_metric(
    metric: str, operator: str, score_prefix: str
) -> None:
    store = _store(similarity_metric=metric)
    session = FakeSession()
    _attach(store, session)

    store.search([0.1], top_k=1)

    statement, _ = session.executed[0]
    assert f'embedding {operator} CAST(:query_embedding AS vector)' in statement
    assert score_prefix in statement
