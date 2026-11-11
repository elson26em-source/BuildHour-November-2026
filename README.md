# Groww Mutual Fund FAQ Assistant

A facts-only RAG demo that answers questions about five HDFC mutual fund pages
on Groww. It scrapes the pages, builds a section-aware Chroma index, retrieves
matching facts, and generates cited answers through a configurable LLM.

The assistant never gives investment advice, comparisons, rankings, or
performance predictions. See [docs/disclaimer.md](docs/disclaimer.md).

## Stack

- Python 3.11
- `requests` + BeautifulSoup for scraping
- `sentence-transformers/all-MiniLM-L6-v2` for embeddings
- ChromaDB for vector search
- Groq by default, with OpenAI, Anthropic, Gemini, and Mistral-compatible
  clients in `src/generation/llm_client.py`
- Streamlit UI

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Set the API key for the configured provider in `.env`:

```dotenv
GROQ_API_KEY=your_key_here
```

Ingestion and retrieval do not need an API key. Live answers do. Without a key,
the answerer falls back safely instead of guessing.

## Pipeline

```text
scrape -> load -> chunk -> embed -> index -> retrieve -> guardrails -> LLM
       -> validate -> persist answer
```

Run the full ingestion pipeline:

```powershell
python -m src.cli ingest
```

Run individual stages:

```powershell
python -m src.cli scrape
python -m src.cli load
python -m src.cli chunk
python -m src.cli embed
python -m src.cli index
```

`index` is idempotent. Use `python -m src.cli index --rebuild` to recreate the
collection.

## Ask Questions

```powershell
python -m src.cli ask "What is the expense ratio of HDFC Large Cap Fund?"
python -m src.cli chat
python -m src.cli retrieve "ELSS lock-in?"
```

`chat` opens an interactive prompt so you can type questions repeatedly without
re-running the command. Answers include a single source URL and a
`Last updated from sources` line.
Retrieval and answer artifacts are written under `artifacts/04_retrieval/` and
`artifacts/05_answers/`.

## Streamlit UI

```powershell
streamlit run src/app/streamlit_app.py
```

The UI provides a persistent facts-only disclaimer, three example questions, a
chat input, citation links, last-updated lines, and a diagnostics expander with
request IDs, retrieved chunks and scores, validation checks, and artifact paths.
If the Chroma collection is empty, it tells you to run `python -m src.cli ingest`
first.

## Guardrails

- PII is rejected before retrieval and is not persisted.
- Advice, comparison, and performance questions get a polite refusal with one
  educational link.
- Low-confidence retrieval and missing sections return "not available from
  sources" with a source link.
- Answers are validated for sentence count, a single allowed citation, no
  advice/performance language, and a last-updated line.
- Invalid LLM output is retried once with a stricter prompt, then replaced with
  a safe fallback.

## Evaluation

```powershell
python -m src.cli evaluate --mock
```

`--mock` uses a deterministic offline LLM so the retrieval, guardrails, and
validation path can be checked without an API key. Omit `--mock` for a live
provider. The report is written to
`artifacts/06_eval/evaluation_report.json`.

Golden factual cases are in `eval/golden_qa.yaml`; refusal and edge cases are
in `eval/refusal_cases.yaml`. Sample outputs are in `eval/sample_qa.md`.

## Tests

```powershell
pytest -q
```

## Artifacts

| Path | Contents |
|---|---|
| `artifacts/01_raw/` | Scraped JSON, HTML snapshots, manifest, load report |
| `artifacts/02_chunks/` | `chunks.jsonl` and chunking strategy |
| `artifacts/03_embeddings/` | `embeddings.npy`, manifest, Chroma index |
| `artifacts/04_retrieval/` | Retrieval logs with redacted queries |
| `artifacts/05_answers/` | Answer logs and validation diagnostics |
| `artifacts/06_eval/` | Evaluation report |

## Known Limitations

- The scraped corpus has no `statement_download` section, so capital-gains
  statement questions return an unavailable response with a source link.
- The configured Groq model name must be available to your account; change
  `llm.provider` and `llm.model` in `config.yaml` if needed.
- Answers are only as fresh as the last ingestion run.
- This is a demo, not a financial advisory product.
