from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from app.config_util import Settings
from app.infrastructure.dependencies import ServiceContainer, build_services

settings = Settings.from_yaml()

_LOG_DIR = Path(__file__).resolve().parents[2] / 'logs'
_LOG_DIR.mkdir(exist_ok=True)
_LOG_FORMAT = '%(asctime)s %(levelname)s %(name)s: %(message)s'

logging.basicConfig(
    level=logging.INFO,
    format=_LOG_FORMAT,
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(_LOG_DIR / 'app.log', maxBytes=5_000_000, backupCount=3),
    ],
)
logging.getLogger('app').setLevel(logging.DEBUG if settings.debug else logging.INFO)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name, version=settings.app_version)


@app.middleware('http')
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info('%s %s -> %d (%.1fms)', request.method, request.url.path, response.status_code, duration_ms)
    return response


def resolve_services(collection_name: str | None, app_state: dict[str, Any]) -> ServiceContainer:
    services_by_collection = app_state.setdefault('services_by_collection', {})
    if collection_name is None:
        collection_name = settings.collection_name

    if collection_name not in services_by_collection:
        logger.info('Building service graph for collection %r', collection_name)
        services_by_collection[collection_name] = build_services(collection_name=collection_name)

    return services_by_collection[collection_name]


app_state: dict[str, Any] = {
    'services_by_collection': {},
}


class CollectionScopedRequest(BaseModel):
    """Base for every request body that may target a specific collection."""

    collection: str | None = None


class PathRequest(CollectionScopedRequest):
    path: str


class QueryRequest(CollectionScopedRequest):
    question: str


class FolderIngestionRequest(CollectionScopedRequest):
    folder_path: str


@contextmanager
def services_for(request: CollectionScopedRequest) -> Iterator[tuple[ServiceContainer, str]]:
    """Resolve the service graph for a request and map any failure to a 500 response."""
    collection_name = request.collection or settings.collection_name
    try:
        yield resolve_services(collection_name, app_state), collection_name
    except Exception as exc:  # pragma: no cover - defensive boundary
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get('/health')
def health_check() -> dict[str, str]:
    return {'status': 'ok'}


@app.post('/index')
def index_document(request: PathRequest) -> dict[str, str]:
    with services_for(request) as (services, _):
        document = services.ingestion.index_document(request.path)
    return {'status': 'indexed', 'source_id': document.source_id}


@app.post('/query')
def query_document(request: QueryRequest) -> dict[str, object]:
    with services_for(request) as (services, _):
        return services.answer.answer(request.question)


@app.post('/ingest-folder')
def ingest_folder(request: FolderIngestionRequest) -> dict[str, object]:
    with services_for(request) as (services, _):
        documents = services.ingestion.index_folder(request.folder_path)
    return {'status': 'ingested', 'count': len(documents), 'sources': [doc.source_id for doc in documents]}


@app.post('/ingest-pipeline')
def ingest_with_pipeline(request: PathRequest) -> dict[str, object]:
    with services_for(request) as (services, collection_name):
        document = services.ingestion.process_document(request.path, collection_name=collection_name)
    return {'status': 'processed', 'source_id': document.source_id, 'metadata': document.metadata}
