from __future__ import annotations

from typing import Any

from sqlalchemy import Column, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from pgvector.sqlalchemy import Vector

from app.domain.models import Chunk, RetrievedChunk
from app.infrastructure.vector_store.base import VectorStore
from app.config_util import settings as _settings

Base = declarative_base()

# pgvector distance operator and how to turn its raw distance into a score,
# keyed by the configurable `similarity_metric` setting.
_METRIC_OPERATORS = {
    'cosine': ('<=>', '1 - ({distance})'),
    'l2': ('<->', '-({distance})'),
}


class DocumentChunk(Base):
    __tablename__ = 'document_chunks'

    id = Column(Integer, primary_key=True)
    collection = Column(String, nullable=False, index=True)
    source_id = Column(String, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    # Dimension is config-driven (embedding_dimension) since it must match
    # whatever embedding_model actually produces.
    embedding = Column(Vector(_settings.embedding_dimension))
    chunk_metadata = Column(Text, nullable=True)


class PostgresVectorStore(VectorStore):
    """PostgreSQL + pgvector-backed vector store implementation.

    A single shared table holds chunks for every disease collection,
    distinguished by the `collection` column rather than one table per
    collection -- adding a new disease is a config + ingestion change, never
    a schema change, and there's one vector index to maintain regardless of
    how many collections exist.
    """

    def __init__(
        self,
        database_url: str,
        collection: str,
        table_name: str = 'document_chunks',
        similarity_metric: str = 'cosine',
        pool_size: int = 5,
        max_overflow: int = 10,
        pool_pre_ping: bool = True,
    ) -> None:
        if similarity_metric not in _METRIC_OPERATORS:
            raise ValueError(f'Unsupported similarity_metric: {similarity_metric!r} (expected one of {sorted(_METRIC_OPERATORS)})')

        self.engine = create_engine(
            database_url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=pool_pre_ping,
        )
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.table_name = table_name
        self.collection = collection
        self.similarity_metric = similarity_metric

    def initialize(self) -> None:
        Base.metadata.create_all(self.engine)

    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        from sqlalchemy import text

        with self.session_factory() as session:
            for chunk, embedding in zip(chunks, embeddings, strict=True):
                session.execute(
                    text(
                        f"INSERT INTO {self.table_name} (collection, source_id, chunk_index, content, embedding, chunk_metadata) "
                        "VALUES (:collection, :source_id, :chunk_index, :content, :embedding, :chunk_metadata)"
                    ),
                    {
                        'collection': self.collection,
                        'source_id': chunk.source_id,
                        'chunk_index': chunk.chunk_index,
                        'content': chunk.content,
                        'embedding': embedding,
                        'chunk_metadata': str(chunk.metadata),
                    },
                )
            session.commit()

    def search(self, query_embedding: list[float], top_k: int) -> list[RetrievedChunk]:
        import ast

        from sqlalchemy import text

        operator, score_expr = _METRIC_OPERATORS[self.similarity_metric]
        distance = f'embedding {operator} CAST(:query_embedding AS vector)'
        score = score_expr.format(distance=distance)

        with self.session_factory() as session:
            rows = session.execute(
                text(
                    f"SELECT source_id, content, chunk_metadata, {score} AS score "
                    f"FROM {self.table_name} WHERE collection = :collection "
                    f"ORDER BY {distance} LIMIT :limit"
                ),
                {'query_embedding': query_embedding, 'limit': top_k, 'collection': self.collection},
            ).fetchall()

        results = []
        for row in rows:
            try:
                metadata = ast.literal_eval(row.chunk_metadata) if row.chunk_metadata else {}
            except (ValueError, SyntaxError):
                metadata = {}
            results.append(
                RetrievedChunk(content=row.content, source_id=row.source_id, score=float(row.score), metadata=metadata)
            )
        return results
