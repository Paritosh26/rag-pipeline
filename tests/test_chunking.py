from app.application.services.chunking_service import ChunkingService


def test_chunk_text_respects_size_and_overlap() -> None:
    service = ChunkingService(chunk_size=20, overlap=5)
    text = "This is a long sample paragraph intended to be chunked into smaller pieces."

    chunks = service.chunk_text(text, source_id="doc-1")

    assert len(chunks) > 1
    assert all(chunk.content for chunk in chunks)
    assert all(len(chunk.content) <= 20 for chunk in chunks)
    assert chunks[0].content != chunks[1].content


def test_chunk_text_carries_document_metadata_into_each_chunk() -> None:
    service = ChunkingService(chunk_size=20, overlap=5)
    text = "This is a long sample paragraph intended to be chunked into smaller pieces."
    document_metadata = {'title': 'Sickle Cell Disease', 'authors': ['Piel FB'], 'publication_year': 2017}

    chunks = service.chunk_text(text, source_id="doc-1", document_metadata=document_metadata)

    assert all(chunk.metadata['title'] == 'Sickle Cell Disease' for chunk in chunks)
    assert all(chunk.metadata['authors'] == ['Piel FB'] for chunk in chunks)
    assert all(chunk.metadata['publication_year'] == 2017 for chunk in chunks)


def test_chunk_text_defaults_metadata_fields_to_none_without_document_metadata() -> None:
    service = ChunkingService(chunk_size=20, overlap=5)

    chunks = service.chunk_text("short text here", source_id="doc-1")

    assert chunks[0].metadata['title'] is None
    assert chunks[0].metadata['authors'] is None
    assert chunks[0].metadata['publication_year'] is None
