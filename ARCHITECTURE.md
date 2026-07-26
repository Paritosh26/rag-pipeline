# Architecture Summary

## Dataset

Sickle Cell Disease. 10 records pulled directly from PubMed via NCBI's E-utilities
(`esearch`/`efetch`, MEDLINE format) into [data/raw/sickle_cell](data/raw/sickle_cell) —
GeneReviews and journal reviews spanning pathophysiology, clinical management, and a 2024
NEJM report on gene therapy (exa-cel). Fetching real MEDLINE records rather than hand-written
text keeps citations verifiable against the actual PMIDs.

## Pipeline

```
PDF/TXT --> extraction+cleaning --> chunking (overlapping, char-based) --> embedding
        --> vector store (pgvector, cosine) --> top-k retrieval --> LLM synthesis --> cited answer
```

- **Chunking**: fixed-size character windows with overlap (default 600/120 for this collection).
  Simple and predictable for a ~10-document corpus; not section-aware. A production system over
  full-text biomedical papers would chunk by section/paragraph boundaries to avoid splitting
  figures, tables, and citations mid-sentence.
- **Embeddings**: `sentence-transformers/all-MiniLM-L6-v2` — fast, runs locally with no API
  dependency or cost, 384-dim. Trade-off: a domain-tuned biomedical embedding model (e.g.
  PubMedBERT-based) would likely improve retrieval precision on specialized terminology; swapping
  it is a one-line config change since embedding is behind the `EmbeddingProvider` interface.
- **Vector store**: PostgreSQL + pgvector by default, with an in-memory fallback (real cosine
  similarity, not just insertion order) for local dev without a database. Both implement the same
  `VectorStore` interface, so swapping in Pinecone/Qdrant/Vertex AI Vector Search later doesn't
  touch retrieval or answer logic. One shared table (`document_chunks`) holds every disease
  collection, distinguished by an indexed `collection` column filtered on every query — not one
  table per disease. Collection settings live in one file, `configs/collections.yaml`, keyed by
  collection name (not one YAML file per disease). Adding a new disease is purely a config +
  ingestion action — a block in that file, documents in `data/raw/<disease>/` — never a schema
  change or a new file, and there's exactly one place a vector index would need to be maintained
  regardless of how many diseases exist, *if* one existed. It doesn't yet: search does a full
  sequential scan (`ORDER BY embedding <=> ...`) with no HNSW/IVFFlat index, which is fine at this
  corpus size and a real limitation before this could handle a much larger one — see Known
  limitations. Verified live: ingesting a second collection into the same table and querying
  each confirms zero cross-collection leakage — a query scoped to one disease never sees another's
  chunks.
- **Generation**: Gemini (`google-genai`), behind an `LLMProvider` interface. If no API key is
  configured, or the API call fails at runtime, the service degrades gracefully to an extractive
  answer built directly from retrieved passages rather than failing the request — grounding is
  never lost, only fluency.
- **Citations**: every answer returns the retrieved chunks' `source_id` (PMID), similarity score,
  and excerpt alongside the generated text, so a claim can always be traced back to a specific
  article.

## One ingestion capability, two entry points

`/index` and `/ingest-folder` (quick path: extract → chunk → embed → upsert) and `/ingest-pipeline`
(adds checksum-based skip-if-unchanged, metadata extraction, and bronze/silver/gold stage-status
tracking) both correctly populate the vector store. They used to be nine separate service classes
built as two disconnected object graphs — one of which never actually persisted embeddings. That
was consolidated into a single `IngestionService` ([ingestion_service.py](app/application/services/ingestion_service.py))
with two methods that share the same extraction/chunking/embedding/storage building blocks, plus a
small `ingestion_tracking.py` for the checksum and stage-status bookkeeping the tracked path needs.
One class to read, one place to change chunking or storage behavior, no risk of the two paths
drifting apart again. The bronze/silver/gold *status labels* are kept (useful for observability
during larger ingests); the three intermediate Bronze/Silver/Gold *objects* that were built and
discarded on every call were not — they added ceremony without adding information beyond what the
status labels already capture.

## Maintainability

The app package is 17 files (down from 27) after consolidating along business capability rather
than one class per micro-step: extraction+metadata into one `extraction_service.py`, the two
ingestion object graphs into one `ingestion_service.py`, checksum+status tracking into one
`ingestion_tracking.py`, and the single-implementation `LLMProvider` interface into the same file
as its one implementation (matching how the embedding provider was already structured). A
no-op `Repository` abstraction that never persisted anything, a dead `/app/api` re-export shim, a
duplicate FastAPI entry point, and three empty placeholder directories (`docs/`, `scripts/`,
`sql/`) were removed outright. Abstractions that earn their keep — `VectorStore` and
`EmbeddingProvider`, each with more than one real, in-use implementation — were left alone. The
5-service application layer (ingestion, extraction, chunking, retrieval, answer) maps directly onto
the 5 pipeline stages in the diagram above, which is the property that keeps this explainable in a
short walkthrough: one service per stage, one file per service, no hidden indirection.

## Known limitations

- **Header noise (fixed)**: raw MEDLINE records lead with ~15 lines of bibliographic bookkeeping
  (PMID, ISSN, volume/issue, dates, ...) before the real `TI`/`AB` content. Early on, chunking
  treated the whole record as plain text, so chunk 0 of every article was pure header noise that
  embedded close enough to disease-name queries to win top-k slots over substantive content —
  concretely, asking "How is sickle cell disease diagnosed?" once returned "no information
  provided" even though a full diagnosis section existed in the corpus, because 4 of 5 retrieved
  chunks were header blocks instead of the chunk that actually discussed diagnosis.
  `extraction_service.py` now detects MEDLINE-formatted input (`text.startswith('PMID-')`) and
  keeps only the `TI` and `AB` fields as chunkable content; re-ingesting after the fix resolved the
  false negative. Non-MEDLINE input (PDFs, plain text) is untouched.
- **Metadata extraction doesn't understand MEDLINE tags**: the regex-based title/author/keyword
  extractor in `extraction_service.py` looks for human-written `Title: ... Authors: ...` phrasing,
  not MEDLINE's `TI  -` / `FAU -` field format, so `title`/`authors` still come back empty for the
  ingested PubMed records via `/ingest-pipeline`'s metadata step, even though that data is now
  cleanly available post-extraction. Same class of fix as above (parse MEDLINE fields directly for
  title/authors/year); not addressed since it affects only pipeline metadata, not retrieval or
  answer correctness.

## Production scaling considerations

- **Ingestion**: replace manual folder ingestion with a scheduled/streamed pull from the PubMed
  API (E-utilities) per disease collection, with the existing checksum-based incremental
  processing deciding what's new.
- **Vector store**: no HNSW/IVFFlat index exists today — every search is a full sequential scan
  over the `embedding` column. Fine at the current corpus size; adding one of those index types is
  the first thing to do before this corpus grows much further, and pgvector stays viable into the
  low millions of chunks once it's there. Beyond that, a managed vector DB reduces operational
  burden.
- **Evaluation**: no offline evaluation harness exists yet. Before production rollout this needs a
  held-out set of question/answer/citation triples to track retrieval recall and answer groundedness
  over time, plus regression testing on embedding/model upgrades.
- **Cost/latency**: embedding is local (free, ~ms); generation cost/latency is dominated by the
  Gemini call — worth caching repeated questions and setting a retrieval score threshold below
  which the system declines to answer rather than guessing.
- **Compliance**: biomedical literature carries redistribution/licensing constraints; a production
  ingester should track per-source license terms, and any answer surface should avoid presenting
  synthesized text as medical advice.
