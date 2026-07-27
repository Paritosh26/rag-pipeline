from __future__ import annotations

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint, create_engine, func, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.infrastructure.checksum_store.base import ChecksumStore

Base = declarative_base()


class DocumentChecksum(Base):
    __tablename__ = 'document_checksums'
    __table_args__ = (UniqueConstraint('path', 'collection', name='uq_document_checksums_path_collection'),)

    id = Column(Integer, primary_key=True)
    path = Column(String, nullable=False, index=True)
    collection = Column(String, nullable=False, index=True)
    checksum = Column(String, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class PostgresChecksumStore(ChecksumStore):
    """Postgres-backed checksum store so incremental-processing state survives restarts."""

    def __init__(
        self,
        database_url: str,
        table_name: str = 'document_checksums',
        pool_size: int = 5,
        max_overflow: int = 10,
        pool_pre_ping: bool = True,
    ) -> None:
        self.engine = create_engine(
            database_url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=pool_pre_ping,
        )
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.table_name = table_name

    def initialize(self) -> None:
        Base.metadata.create_all(self.engine)

    def get_checksum(self, path: str, collection: str) -> str | None:
        with self.session_factory() as session:
            row = session.execute(
                text(f'SELECT checksum FROM {self.table_name} WHERE path = :path AND collection = :collection'),
                {'path': path, 'collection': collection},
            ).fetchone()
        return row.checksum if row else None

    def set_checksum(self, path: str, collection: str, checksum: str) -> None:
        with self.session_factory() as session:
            session.execute(
                text(
                    f'INSERT INTO {self.table_name} (path, collection, checksum, updated_at) '
                    'VALUES (:path, :collection, :checksum, now()) '
                    'ON CONFLICT (path, collection) '
                    'DO UPDATE SET checksum = :checksum, updated_at = now()'
                ),
                {'path': path, 'collection': collection, 'checksum': checksum},
            )
            session.commit()
