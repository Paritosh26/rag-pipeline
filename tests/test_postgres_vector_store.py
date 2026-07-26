from app.infrastructure.vector_store.postgres import DocumentChunk, PostgresVectorStore


def test_document_chunk_model_can_be_imported() -> None:
    assert DocumentChunk.__table__.name == 'document_chunks'
    assert 'chunk_metadata' in DocumentChunk.__table__.c.keys()
    assert 'collection' in DocumentChunk.__table__.c.keys()


def test_vector_store_scopes_queries_to_its_own_collection() -> None:
    store = PostgresVectorStore(database_url='postgresql+psycopg://localhost/nonexistent', collection='sickle_cell')

    assert store.collection == 'sickle_cell'
    assert store.table_name == 'document_chunks'
