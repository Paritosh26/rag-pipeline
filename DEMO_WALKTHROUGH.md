# Demo Walkthrough — Ingestion to Retrieval, Step by Step

This is a rehearsal script, not reference documentation. Every command and response below was captured from a real run against this codebase on a clean, freshly-seeded database — nothing here is hypothetical. Use it to build muscle memory for the live demo, and to have precise, code-level answers ready when someone asks "why."

Companion docs: [ARCHITECTURE_SUMMARY.md](ARCHITECTURE_SUMMARY.md) (what to show), [ADD.md](ADD.md) (why, in depth).

---

## Setup (do this before the room fills up)

```bash
cd /Users/paritoshdutta/biomedical-rag
.venv/bin/python3 -m uvicorn app.presentation.api:app --host 127.0.0.1 --port 8000
```

Confirm it's alive:

```bash
curl -s http://127.0.0.1:8000/health
# {"status":"ok"}
```

If you're re-running this demo more than once, restart the server between rehearsals (`pkill -f uvicorn` then start again). Two things below explain exactly why that matters — it's not just habit.

---

## Part A — Ingestion, one document, step by step

**Say:** "I'll ingest one real PubMed record through the tracked pipeline, which is the path that gives us observability — checksum-based idempotency and bronze/silver/gold status."

```bash
curl -s -X POST http://127.0.0.1:8000/ingest-pipeline \
  -H "Content-Type: application/json" \
  -d '{"path": "data/raw/sickle_cell/pubmed-20301551.txt", "collection": "sickle_cell"}'
```

Real response:

```json
{
  "status": "processed",
  "source_id": "pubmed-20301551",
  "metadata": {
    "title": null,
    "authors": [],
    "keywords": [],
    "publication_year": null,
    "source_file": "data/raw/sickle_cell/pubmed-20301551.txt",
    "collection": "sickle_cell",
    "cleaned_length": 7449,
    "bronze_status": "completed",
    "silver_status": "completed",
    "gold_status": "completed"
  }
}
```

Walk the three stages against this one real response:

### Bronze — `ExtractionService.extract_text_from_path()`
- Reads `pubmed-20301551.txt`, a raw MEDLINE record starting with `PMID-`.
- Detects the MEDLINE format, keeps only the `TI` and `AB` fields, discards ~15 lines of bibliographic header (ISSN, volume/issue, dates).
- **Why this matters, concretely:** before this cleaning step existed, that header noise was chunked and embedded like real content, and it occasionally out-ranked the actual answer in retrieval. (Part C below shows this exact failure mode reproduced live and fixed.)
- Result: `cleaned_length: 7449` — clean title+abstract text, ready to chunk.

### Silver — `ExtractionService.extract_metadata()`
- Runs a regex looking for `Title: ... Authors: ...` phrasing.
- **`title: null`, `authors: []` — this is expected, not a bug in this demo.** MEDLINE's actual field format is `TI  -` / `FAU -`, which this regex doesn't parse. If asked "why is the title empty," say exactly this — it's a documented, known gap, not something breaking live.
- **The sharper point, if pressed:** none of Silver's output — title, authors, keywords, year — is persisted anywhere. It's computed, put into this one JSON response, and then discarded. There's no silver table, no silver column. "Silver: completed" means the step *ran*, not that its data exists after this response returns. Only Gold's output survives.

### Gold — `IngestionService._embed_and_store()`
- Chunks the cleaned text (`ChunkingService`, 600 chars / 120 overlap for this collection), embeds each chunk (`sentence-transformers/all-MiniLM-L6-v2`, local, 384-dim), and inserts into `document_chunks`.
- This document alone produced **16 chunks** from 7,449 characters.

---

## Part B — Idempotency: re-run the exact same document

**Say:** "Ingestion is checksum-gated — re-running an unchanged document is a no-op, which matters for scheduled/repeated ingestion runs."

```bash
curl -s -X POST http://127.0.0.1:8000/ingest-pipeline \
  -H "Content-Type: application/json" \
  -d '{"path": "data/raw/sickle_cell/pubmed-20301551.txt", "collection": "sickle_cell"}'
```

Real response the second time:

```json
{
  "status": "processed",
  "source_id": "pubmed-20301551",
  "metadata": {
    "skipped": true,
    "checksum": "5bfb4793f833bc567ec828b85d4b793bc86beab01d7409731610404fb9913692"
  }
}
```

SHA-256 of the file matched the last-seen checksum, so it's skipped — no duplicate chunks, no wasted embedding calls.

**One thing to know before someone else finds it live:** this checksum cache lives in the API process's memory, not the database. If the vector store is ever cleared or restored independently of the app (a migration, a manual cleanup, disaster recovery) *without* restarting the process, `/ingest-pipeline` will still think it's already processed those documents and skip them — even though their data no longer exists in Postgres. I hit this directly while preparing this demo: I cleared the table to fix a duplication issue, forgot the process was still warm, and one document silently ended up with **zero** chunks because the tracker "remembered" it as done. The fix was simply restarting the process. If asked about production hardening for this pipeline, this is a legitimate answer: the checksum cache needs to move to something that agrees with actual storage state (e.g., a `content_hash` column on `document_chunks` itself), not stay in-process.

**Separately, and worth knowing rather than being surprised by it live:** this checksum gating only exists on the *tracked* path (`/ingest-pipeline`). The *quick* path (`/index`, `/ingest-folder`) has no deduplication at all — `VectorStore.upsert()` is a pure `INSERT`, so calling `/ingest-folder` twice on the same folder will duplicate every chunk, forever. I hit this too while preparing this demo (the corpus briefly had 104 rows instead of the correct 44 because of exactly this). If your live demo re-uses `/ingest-folder`, ingest fresh data or restart between rehearsals — don't call it twice on the same folder.

---

## Part C — Retrieval + Answer Generation

**Say:** "Now the other direction — a question comes in, and I'll trace exactly how it gets an answer."

First, ingest the rest of the corpus (quick path is fine here, it's the first and only time in this run):

```bash
curl -s -X POST http://127.0.0.1:8000/ingest-folder \
  -H "Content-Type: application/json" \
  -d '{"folder_path": "data/raw/sickle_cell", "collection": "sickle_cell"}'
```

Then ask the question that has real history in this project — it's the exact query that once exposed the MEDLINE-header-noise bug (Part A):

```bash
curl -s -X POST http://127.0.0.1:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "How is sickle cell disease diagnosed?", "collection": "sickle_cell"}'
```

Real response:

```json
{
  "answer": "Based on the provided context, sickle cell disease is diagnosed through newborn screening programs.",
  "citations": [
    {"source_id": "pubmed-28423290", "score": 0.8235, "excerpt": "Sickle Cell Disease."},
    {"source_id": "pubmed-33428443", "score": 0.7364, "excerpt": "Sickle Cell Disease. Sickle cell disease is an umbrella term..."},
    {"source_id": "pubmed-21131035", "score": 0.7302, "excerpt": "...this disease; however, we do know that the disorder follows..."},
    {"source_id": "pubmed-35788790", "score": 0.7149, "excerpt": "Sickle Cell Disease: A Review. IMPORTANCE: Sickle cell disease (SCD)..."},
    {"source_id": "pubmed-27637966", "score": 0.7146, "excerpt": "Sickle cell disease. Sickle cell disease (SCD) is an inherited hemoglobinopathy..."}
  ],
  "lineage": {"question": "How is sickle cell disease diagnosed?", "collection": "sickle_cell", "retrieved_chunk_count": 5}
}
```

Walk this step by step:

1. **`RetrievalService.retrieve()`** embeds the question with the same model used at ingestion — query and corpus live in the same vector space.
2. **`VectorStore.search()`** runs `ORDER BY embedding <=> :query_embedding LIMIT 5` against Postgres/pgvector, scoped to `collection = 'sickle_cell'` — cosine similarity, converted to a `1 - distance` score.
3. **A genuinely interesting, honest wrinkle worth narrating live:** the #1-ranked chunk (score 0.82) is just the 21-character title `"Sickle Cell Disease."` — that document's MEDLINE record has no abstract field at all in what NLM returned, so its only chunk is the title. Short, generic text like this embeds deceptively close to almost any query mentioning the disease by name, so it wins the top rank despite carrying no real information. **This is a real, live example of a known dense-retrieval failure mode** (short/sparse documents scoring artificially high), not a corpus mistake — the extraction code did exactly the right thing with what the source provided.
4. **`AnswerService.answer()`** builds a prompt from *all five* retrieved chunks and sends it to Gemini. This is the point worth making explicitly: **retrieval brings back candidates, generation does the actual synthesis.** The LLM isn't fooled by the top-ranked-but-uninformative chunk — it reads all five, finds the one substantive fact buried in `pubmed-35788790` ("SCD is diagnosed through newborn screening programs..."), and answers correctly. Retrieval ranking quality and final answer quality are related but not the same thing, and this response is live proof of that distinction.
5. Every claim in the answer is traceable: five citations, each with `source_id` (PMID), similarity score, and excerpt.

**If asked "how would you improve step 3":** cross-encoder reranking (score the retrieved candidates with a second, more precise model before generation) or a minimum-content-length filter on chunks would both directly address a short, low-information chunk winning a top-k slot on lexical/semantic coincidence alone. Both are already listed as future enhancements.

---

## Cheat Sheet — Likely Questions

| Question | Answer |
|---|---|
| "Why is the title/author metadata empty?" | Regex-based extractor doesn't parse MEDLINE's `TI -`/`FAU -` tag format — known gap, doesn't affect retrieval or answer quality. |
| "Where does Silver's data live?" | Nowhere, past the single API response. It's computed and discarded — only Gold's output (chunks + embeddings) persists. |
| "Why did the top citation score highest but contain the least information?" | That source has no abstract in its MEDLINE record — its only chunk is a 21-character title, and short generic text scores deceptively high in dense retrieval. Generation still synthesizes the correct answer from the full retrieved set. |
| "What happens if I ingest the same file twice?" | Through `/ingest-pipeline`: nothing, it's checksum-skipped. Through `/index` or `/ingest-folder`: it duplicates — those paths have no dedup logic today. |
| "What if the vector store gets cleared/restored independently of the app?" | The tracked path's checksum cache is in-process memory, not tied to actual DB state — it can incorrectly skip re-ingesting documents whose data no longer exists, until the process restarts. |
| "Why pgvector and not a dedicated vector DB?" | One system for metadata + vectors at this scale; interface-based `VectorStore` makes swapping to Pinecone/Qdrant/Vertex AI Vector Search later a non-breaking change. |
| "How would you scale this?" | See ADD.md Section 13 — the concrete first step is an HNSW/IVFFlat index (today's search is a full sequential scan), then Cloud Run + Vertex AI, then Vertex AI Vector Search once corpus size actually justifies a second data system. |
| "What's the biggest gap before production?" | No authentication, and `/index` accepts an arbitrary server-local file path with no restriction — both intentional demonstration-scope decisions, both required before any untrusted network exposure. |
