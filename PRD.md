# PRD: Groww Mutual Fund FAQ Assistant (RAG Demo)

## 1. Overview

Build a small, facts-only FAQ assistant for HDFC mutual fund schemes listed on Groww. The assistant answers factual questions about expense ratio, exit load, minimum SIP, ELSS lock-in, riskometer, benchmark, and how to download statements. Answers are grounded strictly in five specified public Groww pages and always include one citation link.

The project is also a **demo of a RAG pipeline**, so every stage (load, chunk, embed, index, retrieve, generate) must persist inspectable artifacts.

## 2. Problem Statement

Retail users comparing mutual fund schemes and support/content teams repeatedly ask the same factual questions about scheme features. Existing chatbot answers are often ungrounded, mix opinion with facts, or omit sources. We need a small assistant that:

- Answers only verifiable facts from official public pages.
- Never gives investment advice or performance claims.
- Always cites one source link.
- Refuses unsafe or opinionated queries politely.
- Exposes each RAG stage as stored data for demonstration.

## 3. Goals

- Provide accurate, source-backed answers to a defined set of mutual fund FAQ intents.
- Refuse advice, comparison, prediction, and performance questions with a polite, facts-only response.
- Make the full RAG pipeline transparent: raw pages, chunks, embeddings, vector index, retrieval results, and final answers are saved.
- Make chunking strategy, embedding model, vector DB, retrieval settings, and LLM provider/model configurable.

## 4. Non-Goals

- No investment advice, recommendations, portfolio analysis, or buy/sell guidance.
- No return calculations, performance comparisons, or rankings.
- No scraping of links found inside the five target pages.
- No handling or storage of PII (PAN, Aadhaar, account numbers, OTPs, emails, phone numbers).
- No user accounts, authentication, or personalized data.
- No production-scale ingestion beyond the five pages.
- No support for languages other than English in v1.

## 5. Target Users

| Persona | Need |
|---|---|
| Retail investor comparing schemes | Quick factual answers with a trustworthy source link |
| Support / content team | Consistent answers to repetitive mutual fund questions |
| Demo reviewer / evaluator | Visibility into every RAG stage and refusal behavior |

## 6. Scope

### 6.1 In Scope

- Five fixed Groww pages for HDFC Mutual Fund and four schemes.
- A Q&A UI with welcome line, three example questions, and the disclaimer "Facts-only. No investment advice."
- Retrieval-augmented generation with mandatory citation.
- Safe refusal for opinionated, advisory, performance, and out-of-scope queries.
- Persisted artifacts for every pipeline stage.
- Source list, README, sample Q&A file, and demo video or hosted prototype.

### 6.2 Out of Scope

- All other AMCs, schemes, and Groww pages.
- Fundamental analysis, valuation, or performance data.
- Links inside target pages (do not crawl or scrape).
- Third-party blogs, forums, or screenshots.

## 7. Data Sources

Only these five public pages are scraped and used as the factual corpus:

| # | Page | URL |
|---|---|---|
| 1 | AMC overview — HDFC Mutual Fund | https://groww.in/mutual-funds/amc/hdfc-mutual-funds |
| 2 | Large Cap — HDFC Large Cap Fund Direct Growth | https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth |
| 3 | Flexi Cap — HDFC Flexi Cap Direct Plan Growth | https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth |
| 4 | ELSS (tax saver) — HDFC ELSS Tax Saver Fund Direct Plan Growth | https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth |
| 5 | Mid Cap — HDFC Mid Cap Fund Direct Growth | https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth |

Rules:

- Do not follow or scrape internal links from these pages.
- Do not use third-party sources for factual answers.
- Capture the scrape timestamp for every page and carry it through to answers as "Last updated from sources: <date>".
- The source-list deliverable (15–25 URLs) will contain the five scraped URLs plus official AMC/SEBI/AMFI pages used only for refusal/education links. Non-scraped links must never be used as factual grounding.

## 8. User Stories

1. As a retail user, I can ask "What is the expense ratio of HDFC Flexi Cap Fund?" and get a short factual answer with a Groww link.
2. As a retail user, I can ask "What is the lock-in for HDFC ELSS?" and get the ELSS lock-in period with a citation.
3. As a retail user, I can ask "What is the minimum SIP?" and get the amount with a citation.
4. As a retail user, I can ask "What is the exit load?" and get the applicable exit load with a citation.
5. As a retail user, I can ask "What is the riskometer / benchmark?" and get the stated value with a citation.
6. As a retail user, I can ask "How do I download a capital-gains statement?" and get instructions with a citation.
7. As a retail user, when I ask "Should I buy this fund?", I get a polite refusal and an educational link, with no advice.
8. As a reviewer, I can inspect raw pages, chunks, embeddings, Chroma collection, retrieval hits, and final answers for each stage.

## 9. Functional Requirements

### 9.1 FAQ Assistant Behavior

- Answer only factual intents: expense ratio, exit load, minimum SIP, ELSS lock-in, riskometer, benchmark, statement download, and closely related factual fields present in the five pages.
- Ground every factual answer in retrieved chunks from the five pages.
- Include exactly one clear source link in every answer, taken from the retrieved chunk metadata.
- Keep the factual answer to three sentences or fewer.
- Append "Last updated from sources: <YYYY-MM-DD>" to every answer.
- Do not compute, compare, or imply returns or performance.

### 9.2 Refusal Behavior

- Refuse advisory, opinionated, predictive, ranking, or comparison-for-decision questions (e.g., "Should I buy/sell?", "Which fund is better?", "Will this give 15%?").
- Refusal response must be polite, factual, and include one relevant educational link (e.g., the scheme page, AMFI/SEBI investor education page, or official factsheet).
- Do not partially answer advisory questions.
- If retrieval confidence is too low, state that the fact is not available from the provided sources and link the most relevant source page; do not guess.

### 9.3 UI Requirements

- Welcome line explaining the assistant.
- Three example questions visible on load, for example:
  1. "What is the expense ratio of HDFC Large Cap Fund?"
  2. "What is the lock-in period for HDFC ELSS Tax Saver Fund?"
  3. "How can I download my capital-gains statement?"
- Persistent disclaimer: "Facts-only. No investment advice."
- Display answer, single citation link, and last-updated line.
- Do not request or accept PII; if user input contains PII, do not store it and return a safe message.

### 9.4 PII and Safety

- Reject or strip inputs containing PAN, Aadhaar, account numbers, OTPs, emails, or phone numbers.
- Do not log raw user inputs containing PII.
- No secrets committed to the repository; API keys live in `.env`.

## 10. RAG Pipeline (Phased)

Every phase writes an artifact under `artifacts/` (or configured path) so the demo can show each stage explicitly.

### Phase 0 — Configuration and Setup

- Single config file (e.g., `config.yaml`) plus `.env` for secrets.
- Provider-agnostic LLM interface: Groq (default), Gemini, OpenAI, Anthropic, Mistral.
- Default embedding model: `sentence-transformers/all-MiniLM-L6-v2`.
- Default vector DB: ChromaDB (persistent local).
- Config values are read by both ingestion and retrieval so models and stores always match.

### Phase 1 — Data Loading

- Fetch the five URLs only; no internal link following.
- Render JavaScript if required (e.g., Playwright) because Groww pages are dynamic.
- Extract page title, scheme name, section headings, section text, tables, and scrape timestamp.
- Store one raw document per URL as JSON with metadata.

Artifacts:

```
artifacts/01_raw/<slug>.json
artifacts/01_raw/manifest.json
```

### Phase 2 — Data Chunking

The AI coding agent inspects the scraped structure and chooses the chunking strategy. Default approach: **section-aware chunking**.

- Split on semantic headings (e.g., Expense Ratio, Exit Load, Minimum SIP, Lock-in, Riskometer, Benchmark, Statement Download).
- Keep table rows together; convert fee/exit-load tables into key-value facts where possible.
- Target 300–500 tokens per chunk, 50-token overlap for long sections.
- Preserve heading as chunk title and attach URL, scheme, section, and scrape date metadata.
- Record the chosen strategy and rationale in `artifacts/02_chunks/strategy.md`.

Artifacts:

```
artifacts/02_chunks/chunks.jsonl
artifacts/02_chunks/strategy.md
```

### Phase 3 — Data Embedding and Indexing

- Embed chunks with the configured embedding model (`all-MiniLM-L6-v2`, 384 dimensions, normalized).
- Store embeddings and chunk records for inspection.
- Upsert into the configured ChromaDB persistent collection with metadata and stable IDs.
- Record embedding model, dimensions, chunk count, and index timestamp.

Artifacts:

```
artifacts/03_embeddings/embeddings.npy
artifacts/03_embeddings/index_manifest.json
artifacts/03_embeddings/chroma/   (persistent Chroma store)
```

### Phase 4 — Data Retrieval

- Embed the user query with the same configured embedding model.
- Query the same configured ChromaDB collection.
- Retrieve top-k chunks (default k=5, configurable) with optional scheme/section filters and a similarity threshold.
- Persist query, retrieved chunk IDs, scores, and metadata for each request.

Artifacts:

```
artifacts/04_retrieval/<request_id>.json
```

### Phase 5 — Answer Generation (LLM)

- Build a prompt with system rules, retrieved context, and single-citation instruction.
- Default provider/model: Groq with `qwen/qwen3.8-27b` as stated by the requester; verify the exact model ID available in the Groq account and keep it configurable.
- Enforce:
  - Facts only, no advice, no performance claims.
  - At most three sentences.
  - Exactly one source URL from retrieved metadata.
  - "Last updated from sources: <date>".
- Apply an output validator that checks sentence count, citation presence/validity, and absence of advice/performance language; if validation fails, retry once or return a safe fallback with a source link.
- Persist prompt, retrieved context, raw LLM output, validated output, model info, and latency.

Artifacts:

```
artifacts/05_answers/<request_id>.json
```

### Phase 6 — UI and Demo

- Minimal UI (recommended: Streamlit) with the required welcome line, three example questions, disclaimer, answer, citation, and last-updated line.
- Show a "Pipeline" or diagnostics expander exposing stage artifacts for demo purposes.
- Optional CLI entry point for batch evaluation.

### Phase 7 — Evaluation and Documentation

- Sample Q&A file with 5–10 queries: answers, citations, and last-updated lines.
- Refusal test set covering advice, performance, comparison, and PII inputs.
- Check citation validity against chunk metadata and URL allowlist.
- README with setup steps, scope, architecture, config reference, and known limits.
- Source list (CSV/MD) with the five scraped URLs plus official educational/factsheet URLs.
- Demo video (≤3 min) or hosted prototype link.

## 11. Configuration

Example `config.yaml`:

```yaml
app:
  name: "Groww MF Facts Assistant"
  disclaimer: "Facts-only. No investment advice."
  max_answer_sentences: 3

data:
  source_urls:
    - "https://groww.in/mutual-funds/amc/hdfc-mutual-funds"
    - "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth"
    - "https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth"
    - "https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth"
    - "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth"
  follow_internal_links: false

chunking:
  strategy: "section_aware"   # agent may revise after inspecting data
  max_tokens: 450
  overlap_tokens: 50

embedding:
  model: "sentence-transformers/all-MiniLM-L6-v2"
  normalize: true

vector_db:
  provider: "chromadb"
  persist_path: "artifacts/03_embeddings/chroma"
  collection: "groww_mf_faq"

retrieval:
  top_k: 5
  similarity_threshold: 0.35

llm:
  provider: "groq"            # groq | gemini | openai | anthropic | mistral
  model: "qwen/qwen3.8-27b"   # verify exact model ID; configurable
  temperature: 0.0
  max_tokens: 300
```

Secrets in `.env` (never committed):

```
GROQ_API_KEY=...
GEMINI_API_KEY=...
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
MISTRAL_API_KEY=...
```

Rules:

- Ingestion and retrieval must read embedding model and vector DB settings from the same config.
- Changing provider, model, chunking, or vector DB requires config changes only, not code changes.

## 12. Architecture

```
Five Groww URLs
      │
      ▼
[1] Loader (Playwright/requests) ──► raw JSON + manifest
      │
      ▼
[2] Section-aware chunker ────────► chunks.jsonl + strategy.md
      │
      ▼
[3] all-MiniLM-L6-v2 embeddings ──► embeddings.npy + ChromaDB
      │
      ▼
[4] Retriever (same model/DB) ────► retrieval logs
      │
      ▼
[5] LLM (Groq / qwen) + guardrails ► answer logs
      │
      ▼
[6] Streamlit UI (citation + disclaimer + last updated)
```

## 13. Metadata Schema (per chunk)

```json
{
  "chunk_id": "string",
  "doc_id": "string",
  "scheme": "HDFC Flexi Cap Fund | HDFC ELSS Tax Saver Fund | HDFC Large Cap Fund | HDFC Mid Cap Fund | HDFC Mutual Fund",
  "section": "expense_ratio | exit_load | minimum_sip | lock_in | riskometer | benchmark | statement_download | other",
  "heading": "string",
  "text": "string",
  "source_url": "string",
  "scraped_at": "YYYY-MM-DD",
  "token_count": 0
}
```

## 14. Prompting and Guardrails

System prompt requirements:

- Role: facts-only mutual fund FAQ assistant using provided context.
- Allowed topics: the seven factual intents plus directly stated facts on the five pages.
- Use only provided context; do not use outside knowledge.
- Answer in three sentences or fewer.
- Include exactly one source URL from the context metadata.
- End with "Last updated from sources: <date>".
- Refuse advice, recommendations, predictions, comparisons, and performance questions politely, with an educational link and no partial answer.
- Never ask for or repeat PII.

Post-generation validation:

| Check | Failure action |
|---|---|
| Citation present and belongs to retrieved metadata / allowlist | Retry once; else safe fallback with source link |
| Sentence count ≤ 3 | Truncate or retry |
| No advice/performance language | Replace with refusal template |
| "Last updated" line present | Append from chunk metadata |
| No PII echoed | Redact and safe response |

## 15. Non-Functional Requirements

- **Accuracy:** Every factual claim traceable to a retrieved chunk from the five pages.
- **Transparency:** All pipeline artifacts persisted and inspectable.
- **Reproducibility:** Config-driven pipeline; deterministic settings where possible.
- **Safety:** PII rejection, no secrets in repo, no advice or performance output.
- **Performance:** Demo-level latency; target under ~5 seconds per answer excluding cold model load.
- **Maintainability:** Modular stages with clear interfaces; provider adapters for LLMs.
- **Portability:** Runs locally on Windows/Linux with Python 3.11.

## 16. Deliverables

1. Working prototype (hosted link) or ≤3-minute demo video.
2. Source list (CSV/MD) of URLs used, including the five scraped pages and official educational/factsheet links.
3. `README.md` with setup steps, scope (AMC + schemes), architecture, config reference, and known limits.
4. Sample Q&A file with 5–10 queries, answers, and links.
5. Disclaimer snippet used in the UI.
6. Pipeline artifacts for each stage (`artifacts/01_raw` through `artifacts/05_answers`).

## 17. Acceptance Criteria

- [ ] Only the five specified URLs are scraped; no internal links followed.
- [ ] Raw pages, chunks, chunking rationale, embeddings, Chroma index, retrieval logs, and answer logs are persisted.
- [ ] Embedding model and vector DB are read from config and identical for ingestion and retrieval.
- [ ] LLM provider and model are configurable via config and secrets via `.env`.
- [ ] Factual questions across all seven intents return ≤3 sentences, exactly one valid source link, and a last-updated line.
- [ ] Advisory, performance, comparison, and PII requests are refused politely with a relevant link and no advice.
- [ ] UI shows welcome line, three examples, and "Facts-only. No investment advice."
- [ ] Sample Q&A file and source list are present.
- [ ] No secrets or PII are committed or logged.
- [ ] README allows a new user to set up and run the demo.

## 18. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Groww pages are JS-rendered or layout changes | Use Playwright rendering, selector fallbacks, store raw HTML snapshot for debugging |
| Scraped values differ across pages/dates | Store scrape timestamp per chunk; include last-updated line; prefer scheme page for scheme facts |
| LLM hallucinates or adds advice | Strict grounding prompt, output validator, retry, safe fallback |
| LLM model ID mismatch | Verify model availability in Groq console; keep model configurable |
| Source-list requirement (15–25 URLs) conflicts with 5-page scraping limit | List only the five scraped URLs as factual sources; add official AMC/SEBI/AMFI URLs used solely for refusal/education |
| PII leakage in logs | Input PII detection/redaction before logging or model calls |
| Retrieval misses a fact | Section metadata filters, tuned chunking, low-confidence fallback with source link |

## 19. Assumptions and Open Questions

- Groww pages named in the brief are treated as the official public pages for this exercise.
- Model identifier `qwen/qwen3.8-27b` is taken verbatim from the brief; the exact Groq model ID must be confirmed during implementation.
- Default UI is Streamlit unless hosting constraints require another framework.
- English-only v1.
- Open: whether retrieval logs and user questions may be stored for demo (with PII redaction) or must be ephemeral.
- Open: preferred hosting target for the prototype link.

## 20. Milestones

| Milestone | Output |
|---|---|
| M0 | Config, `.env`, project scaffold, provider interface |
| M1 | Scraper and raw artifact for the five pages |
| M2 | Chunking strategy, `chunks.jsonl`, rationale |
| M3 | Embeddings and persistent Chroma index |
| M4 | Retriever with logged results |
| M5 | LLM generation with guardrails and refusal templates |
| M6 | Streamlit UI with disclaimer and examples |
| M7 | Sample Q&A, source list, README, demo video/hosted link |
