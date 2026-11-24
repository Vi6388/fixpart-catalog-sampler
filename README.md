# Permission-Respecting Product Catalog Sampler

A Python-based product catalog collection tool designed for websites where crawling permission has been explicitly granted.

The application discovers sitemap URLs, extracts product information from structured JSON-LD data, stores results in SQLite, and exports product records to CSV.

## Features

- Sitemap discovery and processing
- Product title and price extraction
- JSON-LD structured data parsing
- SQLite-based product storage
- Persistent sitemap and product queues
- Automatic recovery of pending jobs after restart
- Duplicate URL protection
- Batched CSV export
- Configurable request delays and processing limits
- Automated tests using simulated product data

## Safety and Scope

This project is designed for authorized collection only.

- Checks robots.txt before accessing URLs.
- Uses a transparent User-Agent with contact information.
- Respects website access restrictions.
- Does not bypass CAPTCHAs, authentication, or anti-bot controls.
- Stops on HTTP 403, 429, redirects, and relevant server errors.
- Does not attempt to evade rate limits.
- Requires explicit authorization before collecting data from a website.

This project has not been verified against FixPart and does not establish permission to collect or redistribute its catalog.

## Requirements

- Python 3.10 or newer
- pip
- Windows, macOS, or Linux

## Installation (Windows PowerShell)

Clone the repository:

```powershell
git clone YOUR_GITHUB_REPOSITORY_URL
cd fixpart-catalog-sampler
```

Create a virtual environment:

```powershell
python -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Install the test runner if it is not already included:

```powershell
python -m pip install pytest
```

## Run Automated Tests

Execute:

```powershell
python -m pytest -q
```

The tests cover:

- Product information extraction
- Structured JSON-LD parsing
- SQLite storage
- Duplicate handling
- CSV export
- Pending-job recovery after simulated interruption

## Run an Authorized Sample

Only use a website for which written crawling permission has been obtained.

Example:

```powershell
python catalog_scraper.py --base-url https://example.test --limit 10 --max-sitemaps 2 --delay 5 --user-agent "CatalogResearch/0.1 (contact: you@example.com)" --db sample.sqlite3 --output products_sample.csv
```

Replace the example domain and contact information with approved values.

The scraper applies its configured limits and website access restrictions.

## Data Storage and Recovery

SQLite stores:

- Extracted product records
- Sitemap processing status
- Product processing status
- Failed or skipped URL information

Pending jobs remain available after a restart.

Completed jobs are not selected again during normal queue processing.

## CSV Export

The CSV export contains:

- title
- price
- currency
- url

Records are exported in batches to avoid loading the entire database into memory.

## Project Structure

```text
fixpart-catalog-sampler/
│
├── catalog_scraper.py
├── requirements.txt
├── README.md
├── .gitignore
│
├── .github/
│   └── workflows/
│       └── tests.yml
│
└── tests/
    ├── test_extraction.py
    ├── test_storage.py
    └── test_queue.py
```

## Current Validation

The project has been tested using simulated data.

- Automated tests: 13 passed
- CSV export: 10,000 records
- CSV export: 100,000 records
- CSV export: 1,000,000 records
- Duplicate URL validation
- Simulated interrupted-job recovery
- Python syntax validation

These results demonstrate local test performance and do not represent a completed collection of real website products.

## Limitations

- No verified FixPart data integration.
- No confirmed access to a complete product feed.
- No authorization to collect FixPart's catalog has been established.
- Actual collection volume and performance depend on the authorized data source and its access conditions.
