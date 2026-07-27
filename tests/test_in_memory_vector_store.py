from app.domain.models import Chunk
from app.infrastructure.vector_store.in_memory import InMemoryVectorStore


def test_search_ranks_by_similarity_to_query_not_insertion_order() -> None:
    store = InMemoryVectorStore()
    store.initialize()

    chunks = [
        Chunk(content='unrelated content', source_id='doc-1', chunk_index=0),
        Chunk(content='closest match', source_id='doc-2', chunk_index=0),
        Chunk(content='somewhat related', source_id='doc-3', chunk_index=0),
    ]
    embeddings = [
        [1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0],
        [0.7, 0.0, 0.7],
    ]
    store.upsert(chunks, embeddings)

    results = store.search(query_embedding=[0.0, 0.0, 1.0], top_k=2)

    assert [chunk.source_id for chunk in results] == ['doc-2', 'doc-3']
    assert results[0].score > results[1].score


def test_search_returns_at_most_top_k_results() -> None:
    store = InMemoryVectorStore()
    store.initialize()
    store.upsert(
        [Chunk(content='a', source_id='doc-1', chunk_index=0), Chunk(content='b', source_id='doc-2', chunk_index=0)],
        [[1.0, 0.0], [0.0, 1.0]],
    )

    results = store.search(query_embedding=[1.0, 0.0], top_k=1)

    assert len(results) == 1
    assert results[0].source_id == 'doc-1'


def test_delete_by_source_removes_only_matching_entries() -> None:
    store = InMemoryVectorStore()
    store.initialize()
    store.upsert(
        [Chunk(content='a', source_id='doc-1', chunk_index=0), Chunk(content='b', source_id='doc-2', chunk_index=0)],
        [[1.0, 0.0], [0.0, 1.0]],
    )

    store.delete_by_source('doc-1')
    results = store.search(query_embedding=[1.0, 0.0], top_k=10)

    assert [chunk.source_id for chunk in results] == ['doc-2']
