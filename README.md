# FixPart Catalog Sampler

A small, permission-respecting Python sampler for product pages that a site
owner has authorized you to crawl.

It reads sitemap locations advertised by `robots.txt`, checks crawler rules,
and extracts `Product` JSON-LD fields (`name`, `offers.price`, and currency).
It stores progress in SQLite and exports CSV.

## Important scope

This is **not** a stealth scraper and does not bypass bot protection, CAPTCHAs,
access controls, rate limits, or site restrictions. It stops on HTTP 403, 429,
and 5xx responses. Do not run it against FixPart or scale it to a large catalog
unless you have written authorization and an agreed crawl budget.

The current script is intentionally capped at 100 sitemap URLs per run and
requires a minimum 3-second delay. A public sitemap is not permission to bulk
copy a site's catalog.

## Setup

Python 3.10 or newer is recommended.

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

## Run a small authorized sample

Use a transparent crawler identity and a real contact email:

```bash
python catalog_scraper.py --base-url https://example.com --limit 25 --delay 5 --user-agent "CatalogResearch/0.1 (contact: you@example.com)" --db sample.sqlite3 --output products_sample.csv
```

Replace `https://example.com` with a domain you are authorized to crawl.

## Output

CSV columns:

- `title`
- `price`
- `currency`
- `url`

SQLite tracks attempted URLs and unique products so an interrupted sample can
resume without duplicating records.

## Current limitations

- Only sitemap URLs advertised by `robots.txt` are discovered.
- Only Product JSON-LD is parsed.
- Pages without structured Product data are skipped rather than guessed.
- The initial URL cap is 100 per run.
- This has not been verified against FixPart and makes no claim that all
  products are exposed in public sitemaps.

## Tests

```bash
pip install pytest
pytest -q
```
