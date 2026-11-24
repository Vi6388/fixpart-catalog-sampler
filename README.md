# Permission-Respecting Catalog Sampler

A Python sampler for product pages on a domain you are explicitly authorized to crawl.

## Safety and scope

- Reads sitemap locations advertised in `robots.txt`.
- Checks `robots.txt` before fetching sitemap and product URLs.
- Uses a transparent User-Agent with a contact address.
- Does not bypass logins, CAPTCHAs, anti-bot controls, rate limits, or access restrictions.
- Stops on HTTP 403, 429, redirects, and server errors.
- Starts with a maximum of 100 product pages and 25 sitemap files per run.
- This project has not been verified against FixPart and is not evidence of permission to collect FixPart's catalog.

## Setup (Windows PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt pytest
```

## Tests

```powershell
python -m pytest -q
```

## Run a small authorized sample

Use only a domain for which you have written permission. Replace the example domain and contact address with approved values.

```powershell
python catalog_scraper.py --base-url https://example.test --limit 10 --max-sitemaps 2 --delay 5 --user-agent "CatalogResearch/0.1 (contact: you@example.com)" --db sample.sqlite3 --output products_sample.csv
```

The database stores sitemap and product queues. Re-running the same command resumes pending work instead of repeatedly starting at the first product URLs. The CSV export streams rows in batches.

## Files

- `catalog_scraper.py`: crawler, JSON-LD extraction, SQLite queues, CSV export
- `tests/test_extraction.py`: structured-data parsing tests
- `tests/test_storage.py`: queue deduplication and CSV export tests
