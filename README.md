# Biomedical RAG Platform

A retrieval-augmented question-answering pipeline over biomedical research articles. The included dataset covers **Sickle Cell Disease** (10 real PubMed/MEDLINE records in [data/raw/sickle_cell](data/raw/sickle_cell)). The architecture is configuration-driven so additional disease collections can be added without code changes — see [ARCHITECTURE.md](ARCHITECTURE.md) for design rationale and trade-offs.

## Architecture

The application follows a layered design:

- **Presentation** — FastAPI routes ([app/presentation/api.py](app/presentation/api.py))
- **Application** — five services, one per capability:
  - [ingestion_service.py](app/application/services/ingestion_service.py) — extract, chunk, embed, store (quick path + a checksum/metadata/status-tracked path)
  - [extraction_service.py](app/application/services/extraction_service.py) — PDF/TXT parsing, cleaning, metadata
  - [chunking_service.py](app/application/services/chunking_service.py) — overlapping text chunking
  - [retrieval_service.py](app/application/services/retrieval_service.py) — embed a query and search the vector store
  - [answer_service.py](app/application/services/answer_service.py) — LLM synthesis + citations, with extractive fallback
- **Domain** — value objects for documents and chunks ([models.py](app/domain/models.py))
- **Infrastructure** — swappable embedding providers, vector stores (Postgres/pgvector, in-memory), and the LLM provider ([dependencies.py](app/infrastructure/dependencies.py) wires it all together)

See [ARCHITECTURE.md](ARCHITECTURE.md) for the reasoning behind these boundaries.

## Setup

1. Create a virtual environment and install dependencies:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in:
   - `DATABASE_URL` — a PostgreSQL instance with the `pgvector` extension. If unset or unreachable, the app automatically falls back to an in-memory vector store (fine for local demos, not for multi-process/production use).
   - `GEMINI_API_KEY` — a [Google AI Studio](https://aistudio.google.com/) API key. If unset, `/query` still works end-to-end but returns an extractive (non-LLM) answer built directly from the retrieved passages instead of a Gemini-generated one.

3. Run the API:

   ```bash
   uvicorn app.presentation.api:app --reload
   ```

## Ingesting the sample dataset

```bash
curl -X POST http://localhost:8000/ingest-folder \
  -H 'Content-Type: application/json' \
  -d '{"folder_path":"data/raw/sickle_cell","collection":"sickle_cell"}'
```

## Asking a question

```bash
curl -X POST http://localhost:8000/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"What are the main clinical complications of sickle cell disease?","collection":"sickle_cell"}'
```

Returns a JSON payload with `answer`, `citations` (source article, similarity score, excerpt), and `lineage` (question, collection, retrieved chunk count).

## UI

A lightweight Streamlit client is included in [ui/app.py](ui/app.py) for manually testing questions
and ingestion without curl. It lives in its **own virtual environment** (`.venv-ui`) so Streamlit's
dependency tree (pandas, pyarrow, altair, its own pinned `starlette`) never conflicts with the
backend's — mixing them broke FastAPI's `starlette` pin during development, hence the separation.

```bash
python3 -m venv .venv-ui
.venv-ui/bin/pip install -r ui/requirements.txt

# with the API already running (uvicorn app.presentation.api:app --reload):
.venv-ui/bin/streamlit run ui/app.py
```

Opens at `http://localhost:8501` — pick a collection, ingest a folder, and ask questions with a form
instead of raw HTTP calls.

## Configuration

Everything non-secret lives in [configs/application.yaml](configs/application.yaml): a `default:`
section with base values, and an `environments:` section keyed by `local`/`prod` (selected via the
`APP_ENV` env var, defaults to `local`) for environment-specific overrides like `debug`. Secrets
(`DATABASE_URL`, `GEMINI_API_KEY`) are deliberately never in this file — only in `.env` — so a
committed config value can never silently override real deployment credentials.

## Multi-collection support

All disease collections are defined in one file, [configs/collections.yaml](configs/collections.yaml),
keyed by collection name. To add a new disease: add a block to that file, drop documents in
`data/raw/<disease>/`, and ingest via `/ingest-folder` with that collection name — no schema change,
no new table, no new file. All collections share one Postgres table (`document_chunks`), scoped by
an indexed `collection` column, so adding a disease never touches the database schema.

## Security

- **Authentication** — set `API_KEY` in `.env` to require an `X-API-Key: <key>`
  header on every endpoint except `/health`. When it is unset the API is
  **unauthenticated** (fine for local demos, not for anything exposed on a
  network); a warning is logged at startup in that case.

  ```bash
  curl -X POST http://localhost:8000/query \
    -H 'Content-Type: application/json' -H "X-API-Key: $API_KEY" \
    -d '{"question":"...","collection":"sickle_cell"}'
  ```

- **Ingestion paths** — the `path`/`folder_path` accepted by `/index`,
  `/ingest-folder`, and `/ingest-pipeline` are confined to `ingestion_root`
  (default `data/`, see [configs/application.yaml](configs/application.yaml)) so
  the API cannot be coerced into reading arbitrary files off the host.

## Testing

```bash
pytest
```
