from __future__ import annotations

import logging
import secrets
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security import APIKeyHeader
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

if not settings.api_key:
    logger.warning(
        'API_KEY is not set: all endpoints are UNAUTHENTICATED. Set the API_KEY '
        'environment variable to require an X-API-Key header on every request.'
    )

_api_key_header = APIKeyHeader(name='X-API-Key', auto_error=False)


def require_api_key(provided_key: str | None = Depends(_api_key_header)) -> None:
    """Enforce the shared-secret API key when one is configured.

    When ``settings.api_key`` is unset the API stays open (dev/demo default,
    with a loud startup warning); when it is set, every protected endpoint
    requires a matching ``X-API-Key`` header.
    """
    expected = settings.api_key
    if not expected:
        return
    if not provided_key or not secrets.compare_digest(provided_key, expected):
        raise HTTPException(status_code=401, detail='Invalid or missing API key')


def _resolve_ingestion_path(raw_path: str) -> str:
    """Confine an untrusted request path to the configured ingestion root.

    Prevents path-traversal / arbitrary-file-read: the caller-supplied path is
    resolved (following ``..`` and symlinks) and rejected unless it lands inside
    ``settings.ingestion_root``.
    """
    root = Path(settings.ingestion_root).resolve()
    resolved = Path(raw_path).resolve()
    if resolved != root and root not in resolved.parents:
        logger.warning('Rejected ingestion path outside root: %r', raw_path)
        raise HTTPException(status_code=400, detail='path is outside the allowed ingestion directory')
    return str(resolved)


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


class IndexRequest(BaseModel):
    path: str
    collection: str | None = None


class QueryRequest(BaseModel):
    question: str
    collection: str | None = None


class FolderIngestionRequest(BaseModel):
    folder_path: str
    collection: str | None = None


class PipelineIngestionRequest(BaseModel):
    path: str
    collection: str | None = None


@app.get('/health')
def health_check() -> dict[str, str]:
    return {'status': 'ok'}


def _internal_error(exc: Exception) -> HTTPException:
    """Log the real error server-side and return a generic client-facing 500.

    Raw exception text can leak filesystem paths, DB DSNs, and stack internals,
    so it never reaches the client.
    """
    logger.exception('Unhandled error while serving request')
    return HTTPException(status_code=500, detail='Internal server error')


@app.post('/index')
def index_document(request: IndexRequest, _: None = Depends(require_api_key)) -> dict[str, str]:
    path = _resolve_ingestion_path(request.path)
    try:
        collection_name = request.collection or settings.collection_name
        services = resolve_services(collection_name, app_state)
        document = services.ingestion.index_document(path)
    except Exception as exc:  # pragma: no cover - defensive boundary
        raise _internal_error(exc) from exc
    return {'status': 'indexed', 'source_id': document.source_id}


@app.post('/query')
def query_document(request: QueryRequest, _: None = Depends(require_api_key)) -> dict[str, object]:
    try:
        collection_name = request.collection or settings.collection_name
        services = resolve_services(collection_name, app_state)
        response = services.answer.answer(request.question)
    except Exception as exc:  # pragma: no cover - defensive boundary
        raise _internal_error(exc) from exc
    return response


@app.post('/ingest-folder')
def ingest_folder(request: FolderIngestionRequest, _: None = Depends(require_api_key)) -> dict[str, object]:
    folder_path = _resolve_ingestion_path(request.folder_path)
    try:
        collection_name = request.collection or settings.collection_name
        services = resolve_services(collection_name, app_state)
        documents = services.ingestion.index_folder(folder_path)
    except Exception as exc:  # pragma: no cover - defensive boundary
        raise _internal_error(exc) from exc
    return {'status': 'ingested', 'count': len(documents), 'sources': [doc.source_id for doc in documents]}


@app.post('/ingest-pipeline')
def ingest_with_pipeline(request: PipelineIngestionRequest, _: None = Depends(require_api_key)) -> dict[str, object]:
    path = _resolve_ingestion_path(request.path)
    try:
        collection_name = request.collection or settings.collection_name
        services = resolve_services(collection_name, app_state)
        document = services.ingestion.process_document(path, collection_name=collection_name)
    except Exception as exc:  # pragma: no cover - defensive boundary
        raise _internal_error(exc) from exc
    return {'status': 'processed', 'source_id': document.source_id, 'metadata': document.metadata}
