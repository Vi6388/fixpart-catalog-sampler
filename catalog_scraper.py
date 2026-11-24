#!/usr/bin/env python3
"""
Permission-respecting product catalog sampler.

- Reads sitemap locations advertised in robots.txt.
- Checks robots.txt before requesting sitemap/product URLs.
- Extracts Product JSON-LD title and price.
- Uses SQLite for deduplication/resume and exports CSV.
- Stops on 403/429 and server errors; does not evade blocks.

Use only where you have permission to crawl. Do not use to bypass access
controls, CAPTCHAs, rate limits, or other anti-bot protections.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import logging
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

LOG = logging.getLogger("catalog_sampler")
STOP_STATUSES = {403, 429}


def get_session(user_agent: str) -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    return session


def fetch(session: requests.Session, url: str, timeout: int = 25) -> requests.Response:
    response = session.get(url, timeout=timeout)
    if response.status_code in STOP_STATUSES:
        raise RuntimeError(
            f"Server returned HTTP {response.status_code} for {url}. "
            "Stopping; do not try to work around the restriction."
        )
    if response.status_code >= 500:
        raise RuntimeError(
            f"Server returned HTTP {response.status_code} for {url}. "
            "Stopping to avoid adding load during a server problem."
        )
    response.raise_for_status()
    return response


def load_robots(session: requests.Session, base_url: str) -> tuple[RobotFileParser, list[str]]:
    robots_url = urljoin(base_url.rstrip("/") + "/", "robots.txt")
    response = fetch(session, robots_url)
    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(response.text.splitlines())

    sitemaps = []
    for line in response.text.splitlines():
        if line.strip().lower().startswith("sitemap:"):
            sitemap_url = line.split(":", 1)[1].strip()
            if sitemap_url:
                sitemaps.append(sitemap_url)

    if not sitemaps:
        raise RuntimeError(
            "robots.txt did not advertise a sitemap. Stopping rather than "
            "guessing sitemap locations."
        )
    return parser, sitemaps


def parse_sitemap_bytes(content: bytes, source_url: str) -> tuple[str, list[str]]:
    if source_url.lower().endswith(".gz") or content[:2] == b"\x1f\x8b":
        content = gzip.decompress(content)

    root = ET.fromstring(content)
    root_name = root.tag.rsplit("}", 1)[-1].lower()
    locs = [
        (element.text or "").strip()
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1].lower() == "loc" and (element.text or "").strip()
    ]
    return root_name, locs


def sitemap_product_urls(
    session: requests.Session,
    robots: RobotFileParser,
    sitemap_urls: list[str],
    user_agent: str,
    max_urls: int,
    delay: float,
) -> Iterator[str]:
    """Yield candidate URLs from advertised sitemap files, within a strict cap."""
    pending = list(sitemap_urls)
    seen_sitemaps: set[str] = set()
    yielded = 0

    while pending and yielded < max_urls:
        sitemap_url = pending.pop(0)
        if sitemap_url in seen_sitemaps:
            continue
        seen_sitemaps.add(sitemap_url)

        if not robots.can_fetch(user_agent, sitemap_url):
            LOG.info("Skipping sitemap disallowed by robots.txt: %s", sitemap_url)
            continue

        time.sleep(delay)
        response = fetch(session, sitemap_url)
        kind, locs = parse_sitemap_bytes(response.content, sitemap_url)

        if kind == "sitemapindex":
            pending.extend(locs)
            continue

        if kind != "urlset":
            LOG.warning("Unrecognized sitemap root %r at %s", kind, sitemap_url)
            continue

        for page_url in locs:
            if yielded >= max_urls:
                break
            if urlparse(page_url).netloc != urlparse(sitemap_url).netloc:
                LOG.info("Skipping cross-host URL: %s", page_url)
                continue
            if not robots.can_fetch(user_agent, page_url):
                continue
            yielded += 1
            yield page_url


def iter_jsonld_objects(value):
    if isinstance(value, list):
        for item in value:
            yield from iter_jsonld_objects(item)
    elif isinstance(value, dict):
        if "@graph" in value:
            yield from iter_jsonld_objects(value["@graph"])
        else:
            yield value


def has_type(obj: dict, wanted: str) -> bool:
    types = obj.get("@type", [])
    if isinstance(types, str):
        types = [types]
    return any(str(item).split("/")[-1].lower() == wanted.lower() for item in types)



def extract_product(html: str, page_url: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")

    for script in soup.find_all(
        "script", attrs={"type": "application/ld+json"}
    ):
        raw = script.string or script.get_text()

        if not raw or not raw.strip():
            continue

        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue

        for obj in iter_jsonld_objects(data):
            if not isinstance(obj, dict):
                continue

            if not has_type(obj, "Product"):
                continue

            title = obj.get("name")

            if not isinstance(title, str) or not title.strip():
                continue

            offers = obj.get("offers", [])
            if isinstance(offers, dict):
                offers = [offers]

            if not isinstance(offers, list):
                offers = []

            price = ""
            currency = ""

            for offer in offers:
                if not isinstance(offer, dict):
                    continue

                currency = (
                    offer.get("priceCurrency")
                    or currency
                )

                value = offer.get("price")

                if value is None:
                    value = offer.get("lowPrice")

                if value is None:
                    value = offer.get("highPrice")

                if value is None:
                    specifications = offer.get(
                        "priceSpecification", []
                    )

                    if isinstance(specifications, dict):
                        specifications = [specifications]

                    if isinstance(specifications, list):
                        for specification in specifications:
                            if isinstance(specification, dict):
                                value = specification.get("price")
                                if value is not None:
                                    currency = (
                                        specification.get("priceCurrency")
                                        or currency
                                    )
                                    break

                if value is not None:
                    price = str(value).strip()
                    break

            return {
                "title": title.strip(),
                "price": price,
                "currency": str(currency).strip(),
                "url": page_url,
            }

    return None


def init_db(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS products (
            url TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            price TEXT,
            currency TEXT,
            collected_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS attempts (
            url TEXT PRIMARY KEY,
            attempted_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    connection.commit()
    return connection


def export_csv(connection: sqlite3.Connection, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = connection.execute(
        "SELECT title, price, currency, url FROM products ORDER BY title"
    ).fetchall()
    with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["title", "price", "currency", "url"])
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect a small, permitted product-page sample.")
    parser.add_argument("--base-url", default="https://fixpart.ch")
    parser.add_argument("--limit", type=int, default=25,
                        help="Maximum sitemap URLs to inspect (default: 25).")
    parser.add_argument("--delay", type=float, default=5.0,
                        help="Seconds between requests (default: 5).")
    parser.add_argument("--user-agent", required=True,
                        help='Transparent crawler identity, e.g. "JuanCatalogResearch/0.1 (contact: you@example.com)".')
    parser.add_argument("--db", default="catalog_sample.sqlite3")
    parser.add_argument("--output", default="products_sample.csv")
    args = parser.parse_args()

    if args.limit < 1 or args.limit > 100:
        parser.error("--limit must be between 1 and 100 for the initial sample.")
    if args.delay < 3:
        parser.error("--delay must be at least 3 seconds.")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    session = get_session(args.user_agent)
    db = init_db(Path(args.db))

    try:
        robots, sitemaps = load_robots(session, args.base_url)
        LOG.info("Found %d sitemap location(s) in robots.txt.", len(sitemaps))

        inspected = 0
        extracted = 0

        for page_url in sitemap_product_urls(
            session, robots, sitemaps, args.user_agent, args.limit, args.delay
        ):
            already_done = db.execute(
                "SELECT 1 FROM attempts WHERE url = ?", (page_url,)
            ).fetchone()
            if already_done:
                continue

            time.sleep(args.delay)
            response = fetch(session, page_url)
            product = extract_product(response.text, page_url)

            db.execute("INSERT OR IGNORE INTO attempts(url) VALUES (?)", (page_url,))
            if product:
                db.execute(
                    """INSERT OR IGNORE INTO products(url, title, price, currency)
                       VALUES (?, ?, ?, ?)""",
                    (product["url"], product["title"], product["price"], product["currency"]),
                )
                extracted += 1

            inspected += 1
            if inspected % 10 == 0:
                db.commit()
                LOG.info("Inspected %d pages; extracted %d products.", inspected, extracted)

        db.commit()
        export_csv(db, Path(args.output))
        total = db.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        LOG.info("Finished sample. Total unique products in database: %d", total)
        LOG.info("CSV exported to: %s", args.output)
        return 0

    except Exception as exc:
        db.commit()
        LOG.error("%s", exc)
        LOG.error("Progress has been saved. Resolve permissions/site issues before retrying.")
        return 1
    finally:
        db.close()
        session.close()


if __name__ == "__main__":
    sys.exit(main())
