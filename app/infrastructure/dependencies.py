from __future__ import annotations

import logging
from dataclasses import dataclass

from app.application.services.answer_service import AnswerService
from app.application.services.chunking_service import ChunkingService
from app.application.services.ingestion_service import IngestionService
from app.application.services.retrieval_service import RetrievalService
from app.config_util import Settings
from app.infrastructure.checksum_store.in_memory import InMemoryChecksumStore
from app.infrastructure.checksum_store.postgres import PostgresChecksumStore
from app.infrastructure.embedding.base import SentenceTransformerEmbeddingProvider
from app.infrastructure.vector_store.in_memory import InMemoryVectorStore
from app.infrastructure.vector_store.postgres import PostgresVectorStore
from app.llm.gemini_provider import GeminiProvider, LLMProvider

logger = logging.getLogger(__name__)


def _build_llm_provider(settings: Settings) -> LLMProvider | None:
    """Select an LLM provider based on settings.llm_provider.

    Only 'gemini' is implemented today; any other value disables generation
    (falls back to AnswerService's extractive summary) rather than silently
    ignoring the setting, so llm_provider actually controls behavior.
    """
    if not settings.llm_enabled:
        logger.info('llm_enabled is false; using extractive fallback only, no Gemini calls will be made.')
        return None
    if not settings.gemini_api_key:
        return None
    if settings.llm_provider == 'gemini':
        return GeminiProvider(settings.llm_model, settings.gemini_api_key)
    logger.warning('Unsupported llm_provider %r; no LLM provider implemented for it yet.', settings.llm_provider)
    return None


@dataclass
class ServiceContainer:
    """The concrete service graph for a single collection."""

    ingestion: IngestionService
    retrieval: RetrievalService
    answer: AnswerService


def build_services(collection_name: str | None = None) -> ServiceContainer:
    """Create the concrete service graph for the application."""
    settings = Settings.from_yaml(collection_name=collection_name)
    chunking_service = ChunkingService(chunk_size=settings.chunk_size, overlap=settings.chunk_overlap)
    embedding_provider = SentenceTransformerEmbeddingProvider(settings.embedding_model)
    try:
        vector_store = PostgresVectorStore(
            database_url=settings.database_url,
            collection=settings.collection_name,
            table_name=settings.vector_table_name,
            similarity_metric=settings.similarity_metric,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_pre_ping=settings.database_pool_pre_ping,
        )
        vector_store.initialize()
    except Exception:
        logger.warning(
            'Could not connect to Postgres at %s; falling back to a non-persistent in-memory vector store.',
            settings.database_url,
            exc_info=True,
        )
        # remove this fallback when moving to production; we want to fail fast if Postgres is unavailable
        vector_store = InMemoryVectorStore()
        vector_store.initialize()

    try:
        checksum_store = PostgresChecksumStore(
            database_url=settings.database_url,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_pre_ping=settings.database_pool_pre_ping,
        )
        checksum_store.initialize()
    except Exception:
        logger.warning(
            'Could not connect to Postgres at %s; falling back to a non-persistent in-memory checksum store.',
            settings.database_url,
            exc_info=True,
        )
        # remove this fallback when moving to production; we want to fail fast if Postgres is unavailable
        checksum_store = InMemoryChecksumStore()
        checksum_store.initialize()

    ingestion_service = IngestionService(
        chunking_service=chunking_service,
        embedding_provider=embedding_provider,
        vector_store=vector_store,
        min_document_length=settings.min_document_length,
        checksum_store=checksum_store,
    )
    retrieval_service = RetrievalService(
        embedding_provider=embedding_provider,
        vector_store=vector_store,
        top_k=settings.retrieval_top_k,
    )
    answer_service = AnswerService(
        retrieval_service=retrieval_service,
        llm_provider=_build_llm_provider(settings),
        settings=settings,
    )

    return ServiceContainer(ingestion=ingestion_service, retrieval=retrieval_service, answer=answer_service)
