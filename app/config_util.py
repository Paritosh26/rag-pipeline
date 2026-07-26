from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    """Application settings.

    Real default values live in configs/application.yaml (under `default:`,
    with per-environment overrides under `environments:`) and
    configs/collections.yaml (per-disease overrides) -- this class only
    declares field types/shapes. The Python-level defaults below are a
    last-resort fallback if the config file is ever missing, never the
    intended source of truth; `Settings.from_yaml()` is the only supported
    way to construct this class and always supplies the real values explicitly.

    Secrets (DATABASE_URL, GEMINI_API_KEY, API_KEY) are the one exception: they come
    only from environment variables / .env, never from YAML, so a committed
    config file can never silently override real deployment credentials.
    """

    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    app_name: str = 'biomedical-rag'
    app_version: str = '0.1.0'
    debug: bool = False

    # Untrusted request-supplied ingestion paths (/index, /ingest-folder,
    # /ingest-pipeline) are constrained to live under this directory so the API
    # cannot be coerced into reading arbitrary files off the host filesystem.
    ingestion_root: str = 'data'
    # Optional shared-secret API key. When set (via the API_KEY env var / .env),
    # every endpoint except /health requires a matching `X-API-Key` header.
    # Never comes from committed YAML -- it is a secret, like the two below.
    api_key: str | None = None

    database_url: str = 'postgresql+psycopg://postgres:postgres@localhost:5432/rag'
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_pool_pre_ping: bool = True
    vector_table_name: str = 'document_chunks'

    embedding_model: str = 'sentence-transformers/all-MiniLM-L6-v2'
    embedding_dimension: int = 384
    llm_enabled: bool = True
    llm_provider: str = 'gemini'
    llm_model: str = 'gemini-flash-lite-latest'
    gemini_api_key: str | None = None
    chunk_size: int = 500
    chunk_overlap: int = 100
    retrieval_top_k: int = 5
    similarity_metric: str = 'cosine'
    # Below this top-retrieved-chunk score, skip the LLM call entirely and go
    # straight to the extractive fallback -- saves an API call on queries that
    # are very unlikely to be answerable anyway. 0.0 = always call (disabled).
    retrieval_score_threshold: float = 0.0
    min_document_length: int = 20
    collection_name: str = 'biomedical-papers'

    prompt_template: str = (
        'You answer using only the provided context.\n'
        'Context:\n{context}\n\nQuestion: {question}\nAnswer:'
    )

    @classmethod
    def from_yaml(
        cls,
        path: str | None = None,
        collection_name: str | None = None,
        config_dir: str | None = None,
    ) -> 'Settings':
        """Load settings from the consolidated application config and collection YAML files."""
        project_root = Path(__file__).resolve().parents[1]
        config_root = Path(config_dir or project_root / 'configs')
        base_path = Path(path or config_root / 'application.yaml')

        merged: dict[str, Any] = {}
        if base_path.exists():
            with base_path.open('r', encoding='utf-8') as handle:
                document: dict[str, Any] = yaml.safe_load(handle) or {}
            merged = dict(document.get('default') or {})
            environment_key = os.getenv('APP_ENV', 'local')
            merged.update(document.get('environments', {}).get(environment_key) or {})

        collection_key = collection_name or merged.get('collection_name') or 'default'
        collections_path = config_root / 'collections.yaml'
        if collections_path.exists():
            with collections_path.open('r', encoding='utf-8') as handle:
                all_collections: dict[str, Any] = yaml.safe_load(handle) or {}
            merged.update(all_collections.get(collection_key) or {})
        merged['collection_name'] = collection_key

        for key, value in merged.items():
            os.environ.setdefault(key.upper(), str(value))

        return cls(**merged)

    def collection_summary(self) -> dict[str, Any]:
        """Return the collection-specific runtime settings as a plain dictionary."""
        return {
            'collection_name': self.collection_name,
            'chunk_size': self.chunk_size,
            'chunk_overlap': self.chunk_overlap,
            'retrieval_top_k': self.retrieval_top_k,
            'vector_table_name': self.vector_table_name,
        }


settings = Settings.from_yaml()
