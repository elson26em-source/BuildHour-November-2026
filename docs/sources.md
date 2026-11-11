# Sources

The assistant is restricted to these five Groww pages from `config.yaml`.
Internal links are not followed, and no other URL is scraped.

| Doc ID | Page | Type |
|---|---|---|
| `hdfc-mutual-funds` | https://groww.in/mutual-funds/amc/hdfc-mutual-funds | AMC overview |
| `hdfc-large-cap-fund-direct-growth` | https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth | Scheme |
| `hdfc-equity-fund-direct-growth` | https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth | Scheme (HDFC Flexi Cap) |
| `hdfc-elss-tax-saver-fund-direct-plan-growth` | https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth | Scheme |
| `hdfc-mid-cap-fund-direct-growth` | https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth | Scheme |

## Corpus Coverage

The current scrape date is `2026-11-09`. The four scheme pages provide
chunks for:

- `expense_ratio`
- `exit_load`
- `minimum_sip`
- `lock_in`
- `riskometer`
- `benchmark`
- `other`

The corpus does **not** contain a `statement_download` section. Questions about
capital-gains statements therefore return the safe
"section is not available from the scraped sources" response with a source
link instead of guessed steps.

## Freshness

Each retrieved chunk carries `source_url` and `scraped_at`. Answers include a
`Last updated from sources: <date>` line. Re-run ingestion to refresh the
corpus:

```powershell
python -m src.cli ingest
```
