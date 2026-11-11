# Disclaimer

**Facts-only. No investment advice.**

This demo answers factual questions using only the five scraped Groww pages
listed in [sources.md](sources.md). It does not provide investment advice,
recommendations, rankings, comparisons, or return/performance predictions.

## Data and Privacy

- Queries containing PAN, Aadhaar, account numbers, OTPs, emails, or phone
  numbers are rejected before retrieval.
- PII-containing inputs are not written to retrieval or answer artifacts.
- Retrieval and answer artifacts store redacted queries only.

## Answer Limits

- Answers are limited to three sentences.
- Answers must contain exactly one citation from the configured source list.
- Answers must include a last-updated line derived from retrieved metadata.
- If retrieval is empty, low-confidence, or missing the requested section, the
  assistant says the information is not available instead of guessing.
- The LLM may paraphrase retrieved text. The citation points to the original
  Groww page; always verify important details there.

## Source Freshness

The current corpus was scraped on `2026-11-09`. Mutual fund facts can change.
Re-run `python -m src.cli ingest` to refresh the index.

## Official Information

For decisions about investments, taxes, or personal account actions, use the
official AMC or registrar channels and consult a qualified professional.
