from app.application.services.chunking_service import ChunkingService


def test_chunk_text_respects_size_and_overlap() -> None:
    service = ChunkingService(chunk_size=20, overlap=5)
    text = "This is a long sample paragraph intended to be chunked into smaller pieces."

    chunks = service.chunk_text(text, source_id="doc-1")

    assert len(chunks) > 1
    assert all(chunk.content for chunk in chunks)
    assert all(len(chunk.content) <= 20 for chunk in chunks)
    assert chunks[0].content != chunks[1].content
