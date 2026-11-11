# Architecture: Groww Mutual Fund FAQ Assistant

Source of truth: [PRD.md](PRD.md). This document describes how the system is structured and how data moves through each RAG stage.

## 1. Architectural Goals

- Facts-only answers grounded in five fixed Groww pages.
- One citation link and a last-updated date in every answer.
- Every RAG stage persists an inspectable artifact for demo purposes.
- Chunking, embedding model, vector DB, retrieval settings, and LLM provider are config-driven.
- Advice, performance, comparison, and PII inputs are safely refused.

## 2. System Context

```
                +-------------------------------------------+
                |                Reviewer / User            |
                |        (browser, Streamlit UI)            |
                +----------------------+--------------------+
                                       |
                                       v
                +-------------------------------------------+
                |         Streamlit Application             |
                |  welcome + examples + disclaimer + chat   |
                +---------+-----------------------+---------+
                          |                       |
                          v                       v
                +-------------------+   +----------------------+
                |  Guardrail Layer  |   |   Query Pipeline     |
                |  PII, advice,     |   |   embed -> retrieve  |
                |  performance      |   |   -> prompt -> LLM   |
                +---------+---------+   +----------+-----------+
                          |                        |
                          v                        v
                +-------------------------------------------+
                |             Configuration                 |
                |   config.yaml + .env (secrets)            |
                +-------------------------------------------+

        Offline ingestion (run once / on refresh):

        Five Groww URLs -> Loader -> Chunker -> Embedder -> ChromaDB
             artifacts/01_raw  02_chunks  03_embeddings
```

Runtime components:

| Component | Responsibility |
|---|---|
| UI | Collect query, show answer, citation, last-updated line, disclaimer |
| Guardrail layer | Detect PII, advice, performance, comparison intent before/after LLM |
| Query pipeline | Embed query, retrieve context, build prompt, call LLM, validate output |
| Config | Single source for models, vector DB, retrieval, chunking, LLM provider |
| Ingestion pipeline | Scrape, chunk, embed, index the five pages |
| Artifact store | Persist stage outputs for inspection |

## 3. Component Diagram

```
src/
├── config/
│   ├── loader.py           # load config.yaml, validate, merge .env
│   └── schema.py           # dataclasses / pydantic models for config
├── ingestion/
│   ├── loader.py           # fetch five URLs, render JS, extract sections
│   ├── chunker.py          # section-aware chunking
│   ├── embedder.py         # all-MiniLM-L6-v2 embeddings
│   └── indexer.py          # upsert into ChromaDB
├── retrieval/
│   ├── embedder.py         # query embedding (same model as ingestion)
│   └── retriever.py        # Chroma query, filters, top-k, threshold
├── generation/
│   ├── prompts.py          # system + refusal prompts
│   ├── llm_client.py       # provider factory (Groq/Gemini/OpenAI/Anthropic/Mistral)
│   ├── validator.py        # sentence count, citation, advice/PII checks
│   └── answerer.py         # orchestration of retrieve + generate + validate
├── guardrails/
│   ├── intent.py           # classify factual vs advice/performance/comparison
│   └── pii.py              # detect/redact PAN, Aadhaar, account, OTP, email, phone
├── app/
│   └── streamlit_app.py    # UI, examples, disclaimer, diagnostics expander
├── cli.py                  # ingest / ask / evaluate commands
└── tests/
```

Module boundaries:

- `ingestion` never imports `generation`; it only writes artifacts and Chroma.
- `retrieval` and `ingestion` share the embedding model name and Chroma settings strictly through config.
- `generation` receives retrieved chunks, never fetches pages directly.
- `app` depends on `answerer`, `guardrails`, and `config`; it does not embed/query directly.

## 4. Data Flow

### 4.1 Offline Ingestion

```
1. config.loader loads config.yaml + .env
2. loader.fetch(url) for each of the five URLs (no link following)
3. loader extracts title, headings, text blocks, tables, scraped_at
4. write artifacts/01_raw/<slug>.json + manifest.json
5. chunker splits by section heading (strategy documented)
6. write artifacts/02_chunks/chunks.jsonl + strategy.md
7. embedder encodes chunk text with configured model
8. write artifacts/03_embeddings/embeddings.npy + index_manifest.json
9. indexer upserts vectors + metadata into Chroma collection
```

### 4.2 Online Query

```
1. UI receives query
2. guardrails.pii detects PII -> safe message, no storage
3. guardrails.intent classifies query
   - advice/performance/comparison -> template refusal + educational link
   - factual -> continue
4. retriever embeds query with the same configured model
5. Chroma returns top-k chunks above threshold (optional scheme/section filter)
6. write artifacts/04_retrieval/<request_id>.json
7. answerer builds prompt with context + single-citation rule
8. llm_client calls configured provider/model
9. validator enforces <=3 sentences, one valid citation, last-updated line,
   no advice/performance; retry once, else safe fallback
10. write artifacts/05_answers/<request_id>.json
11. UI renders answer, citation, last-updated line, disclaimer
```

### 4.3 Sequence Diagram

```
User        UI        Guardrails     Retriever     Chroma      LLM        Validator
 |           |             |             |            |          |            |
 |--query--->|             |             |            |          |            |
 |           |--check PII->|             |            |          |            |
 |           |--intent---->|             |            |          |            |
 |           |<--factual---|             |            |          |            |
 |           |--embed+retrieve-------------------->|          |            |
 |           |             |             |<--top-k----|          |            |
 |           |             |             |--context--------------------->|    |
 |           |             |             |            |    prompt+LLM-->|    |
 |           |             |             |            |          |--answer-->|
 |           |             |             |            |          |            |--validate
 |           |<--------------------------answer + citation + last updated--|
 |<--render--|
```

## 5. Data Model

### 5.1 Raw Document (`artifacts/01_raw/<slug>.json`)

```json
{
  "doc_id": "hdfc-flexi-cap-direct-growth",
  "url": "https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth",
  "title": "HDFC Flexi Cap Direct Plan Growth",
  "scheme": "HDFC Flexi Cap Fund",
  "scraped_at": "2026-11-09",
  "sections": [
    { "heading": "Expense Ratio", "text": "...", "tables": [] }
  ],
  "raw_html_path": "artifacts/01_raw/html/hdfc-flexi-cap-direct-growth.html"
}
```

### 5.2 Chunk (`artifacts/02_chunks/chunks.jsonl`)

```json
{
  "chunk_id": "hdfc-flexi-cap-direct-growth::expense_ratio::0",
  "doc_id": "hdfc-flexi-cap-direct-growth",
  "scheme": "HDFC Flexi Cap Fund",
  "section": "expense_ratio",
  "heading": "Expense Ratio",
  "text": "The expense ratio of HDFC Flexi Cap Direct Plan Growth is ...",
  "source_url": "https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth",
  "scraped_at": "2026-11-09",
  "token_count": 84
}
```

### 5.3 Chroma Collection

- Collection name: from `config.vector_db.collection` (default `groww_mf_faq`).
- Distance: cosine.
- IDs: stable `chunk_id`.
- Documents: chunk text.
- Metadata: `scheme`, `section`, `heading`, `source_url`, `scraped_at`, `doc_id`.
- Embeddings: 384-dim normalized vectors from `all-MiniLM-L6-v2`.

### 5.4 Retrieval Log (`artifacts/04_retrieval/<request_id>.json`)

```json
{
  "request_id": "uuid",
  "query": "...",
  "query_embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
  "top_k": 5,
  "hits": [
    { "chunk_id": "...", "score": 0.82, "section": "exit_load", "source_url": "..." }
  ]
}
```

### 5.5 Answer Log (`artifacts/05_answers/<request_id>.json`)

```json
{
  "request_id": "uuid",
  "prompt": "...",
  "context_chunk_ids": ["..."],
  "llm": { "provider": "groq", "model": "qwen/qwen3.8-27b", "temperature": 0.0 },
  "raw_output": "...",
  "final_output": "...",
  "citation_url": "https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth",
  "last_updated": "2026-11-09",
  "validation": { "passed": true, "checks": ["sentence_count", "citation", "no_advice"] },
  "latency_ms": 0
}
```

## 6. Configuration and Secrets

- `config.yaml` holds non-secret settings: source URLs, chunking, embedding model, vector DB path/collection, retrieval thresholds, LLM provider/model/temperature.
- `.env` holds provider API keys only: `GROQ_API_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `MISTRAL_API_KEY`.
- `config/loader.py` validates config at startup and fails fast on missing required values or matching embedding/DB settings.
- Ingestion and retrieval both call the same loader so the embedding model and collection can never diverge accidentally.

## 7. LLM Provider Abstraction

```
LLMClient (interface)
├── generate(system_prompt, context, user_query, max_tokens, temperature) -> str
├── GroqClient     (default; qwen/qwen3.8-27b, configurable)
├── GeminiClient
├── OpenAIClient
├── AnthropicClient
└── MistralClient
```

Rules:

- Provider and model selected by config; API key resolved from `.env`.
- Temperature default 0.0.
- All clients return plain text; normalization and validation happen downstream.
- Provider-specific errors map to one internal error type; UI shows a safe fallback with a source link.

## 8. Retrieval Design

- Same embedding model at ingestion and query time, enforced via config.
- Top-k default 5, threshold default 0.35, both configurable.
- Metadata filters allowed for `scheme` and `section` when the query clearly names a scheme or fact type.
- No cross-encoder reranking in v1 (keep demo small); the interface leaves room for a reranker stage.
- If no hit clears the threshold, return a low-confidence response with the most relevant source page link (no guessed facts).

## 9. Guardrails

| Guardrail | Where | Action |
|---|---|---|
| PII detection | Pre-LLM | Redact/reject; do not log raw input |
| Intent classification | Pre-LLM | Factual -> pipeline; advice/performance/comparison -> refusal template |
| Grounding | Prompt + post-check | Answer only from retrieved context; citation must be from retrieved metadata/allowlist |
| Sentence limit | Post-LLM | Enforce <=3 sentences (truncate or retry) |
| Advice/performance language | Post-LLM | Replace with refusal template |
| Last-updated line | Post-LLM | Append from chunk `scraped_at` |
| Output citation count | Post-LLM | Exactly one link |

Refusal template characteristics: polite, no partial answer, one relevant educational link (scheme page, AMFI/SEBI investor education, or official factsheet).

## 10. Storage and Artifacts

```
artifacts/
├── 01_raw/                # per-page JSON + HTML snapshots + manifest
├── 02_chunks/             # chunks.jsonl + strategy.md
├── 03_embeddings/         # embeddings.npy + index_manifest.json + chroma/
├── 04_retrieval/          # per-request retrieval logs
└── 05_answers/            # per-request prompt/context/output logs
```

- Directory root configurable (`artifacts/` default).
- Chroma persisted on disk and reused across runs; ingestion supports rebuild (`--rebuild`).
- No PII is written to artifacts; raw queries are logged only after redaction.

## 11. UI Architecture

- Streamlit single-page app.
- Layout:
  1. Welcome line and disclaimer banner: "Facts-only. No investment advice."
  2. Three example question buttons.
  3. Chat input and answer cards (answer, citation link, last-updated line).
  4. Diagnostics expander showing retrieved chunk IDs, scores, and artifact paths for the request (demo feature).
- Refusals render in the same card format but with an educational link.
- No login, no session persistence beyond the browser tab.

## 12. Error Handling

| Failure | Behavior |
|---|---|
| Scrape fails / page changed | Keep previous artifacts; report failing URL; do not silently index partial data |
| Chroma empty or missing | Inform user to run ingestion; CLI error with instruction |
| Embedding model mismatch | Config validation fails fast at startup |
| LLM timeout/rate limit | One retry, then safe fallback with retrieved source link |
| Empty retrieval | Low-confidence message + most relevant source page link |
| Validator failure | Regenerate once with stricter prompt; else safe template |
| PII detected | Safe message; input not stored |

## 13. Testing Strategy

- Unit: chunker boundaries, metadata schema, PII detector, validator checks.
- Integration: ingest a saved HTML snapshot -> chunks -> embeddings -> Chroma -> retrieve known fact.
- End-to-end: golden Q&A set (5-10 queries) verifying answer, citation, last-updated line, sentence count.
- Refusal tests: advice, performance, comparison, PII, out-of-scope.
- Citation tests: every answer link exists in retrieved metadata / source allowlist.

## 14. Deployment and Runbook

- Local-first: Python 3.11, virtualenv, `pip install -r requirements.txt`.
- One-time or refresh ingestion: `python -m src.cli ingest [--rebuild]`.
- Run UI: `streamlit run src/app/streamlit_app.py`.
- Optional hosted demo (Streamlit Community Cloud or equivalent); secrets injected as environment variables, never committed.
- Demo video fallback if hosting is unavailable.

## 15. Key Architectural Decisions

| Decision | Rationale |
|---|---|
| Section-aware chunking | MF pages are naturally structured by fact type; improves retrieval precision for single-fact questions |
| Single embedding model from config | Guarantees vector space consistency between ingestion and query |
| ChromaDB persistent local store | Small corpus, simple demo, inspectable artifacts |
| Provider-agnostic LLM client | PRD requires Groq default plus Gemini/OpenAI/Anthropic/Mistral options |
| Deterministic generation (temperature 0) | Facts-only requirement favors consistency over creativity |
| Artifact-per-stage logging | Explicit demo requirement to show each RAG stage |
| Policy guardrails before and after LLM | Prevents advice/performance output even if retrieval or model drifts |
