#!/usr/bin/env python3
"""Permission-respecting product catalog sampler.

This tool is intended only for domains and URLs you are authorized to crawl.
It does not bypass robots.txt, authentication, CAPTCHAs, anti-bot controls,
rate limits, or access restrictions. It stops on 403, 429, redirects, and 5xx.

Sitemap discovery and product-page work are stored in SQLite queues so a later
run can continue from pending work instead of restarting at the first URLs.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import logging
import math
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

LOG = logging.getLogger("catalog_sampler")
STOP_STATUSES = {403, 429}
USER_AGENT_DEFAULT = "CatalogResearch/0.1"


def get_session(user_agent: str) -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    return session


def fetch(session: requests.Session, url: str, timeout: int = 25) -> requests.Response:
    """Fetch one URL without following redirects or retrying blocked requests."""
    response = session.get(url, timeout=timeout, allow_redirects=False)
    if 300 <= response.status_code < 400:
        raise RuntimeError(
            f"Server redirected {url} (HTTP {response.status_code}). "
            "Stopping rather than following an unverified destination."
        )
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


def load_robots(
    session: requests.Session, base_url: str
) -> tuple[RobotFileParser, list[str]]:
    robots_url = base_url.rstrip("/") + "/robots.txt"
    response = fetch(session, robots_url)
    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(response.text.splitlines())

    sitemaps: list[str] = []
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
    locations = [
        (element.text or "").strip()
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1].lower() == "loc"
        and (element.text or "").strip()
    ]
    return root_name, locations


def same_host(url: str, base_url: str) -> bool:
    return (urlparse(url).hostname or "").lower() == (
        urlparse(base_url).hostname or ""
    ).lower()


def iter_jsonld_objects(value: object) -> Iterator[dict]:
    """Yield JSON-LD objects, including objects nested in @graph and arrays."""
    if isinstance(value, list):
        for item in value:
            yield from iter_jsonld_objects(item)
    elif isinstance(value, dict):
        yield value
        for key, child in value.items():
            if key in {"@graph", "mainEntity", "itemListElement"}:
                yield from iter_jsonld_objects(child)


def has_type(obj: dict, wanted: str) -> bool:
    types = obj.get("@type", [])
    if isinstance(types, str):
        types = [types]
    if not isinstance(types, list):
        return False
    return any(str(item).rstrip("/").split("/")[-1].split("#")[-1].lower() == wanted.lower()
               for item in types)


def _as_list(value: object) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def _valid_price(value: object) -> str:
    if isinstance(value, bool) or value is None:
        return ""
    if isinstance(value, (str, int, float)):
        text = str(value).strip()
        if not text:
            return ""
        try:
            number = float(text)
        except ValueError:
            return ""
        return text if math.isfinite(number) and number >= 0 else ""
    return ""


def _offer_price(offer: dict) -> tuple[str, str]:
    currency = str(offer.get("priceCurrency") or "").strip()
    candidates = [offer.get("price"), offer.get("lowPrice"), offer.get("highPrice")]
    for candidate in candidates:
        price = _valid_price(candidate)
        if price:
            return price, currency

    for spec in _as_list(offer.get("priceSpecification")):
        if not isinstance(spec, dict):
            continue
        price = _valid_price(spec.get("price"))
        if price:
            spec_currency = str(spec.get("priceCurrency") or currency).strip()
            return price, spec_currency
    return "", currency


def extract_product(html: str, page_url: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        if not raw or not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue

        for obj in iter_jsonld_objects(data):
            if not has_type(obj, "Product"):
                continue
            title = obj.get("name")
            if not isinstance(title, str) or not title.strip():
                continue

            price = ""
            currency = ""
            for offer in _as_list(obj.get("offers")):
                if not isinstance(offer, dict):
                    continue
                candidate_price, candidate_currency = _offer_price(offer)
                if candidate_price:
                    price, currency = candidate_price, candidate_currency
                    break
                if not currency:
                    currency = candidate_currency

            return {
                "title": title.strip(),
                "price": price,
                "currency": currency,
                "url": page_url,
            }
    return None


def init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS products (
            url TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            price TEXT NOT NULL DEFAULT '',
            currency TEXT NOT NULL DEFAULT '',
            collected_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS sitemap_queue (
            url TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending', 'done', 'skipped'))
        );
        CREATE TABLE IF NOT EXISTS product_queue (
            url TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending', 'done', 'skipped')),
            last_error TEXT
        );
    """)
    connection.commit()
    return connection


def seed_sitemaps(db: sqlite3.Connection, sitemap_urls: list[str]) -> None:
    db.executemany(
        "INSERT OR IGNORE INTO sitemap_queue(url, status) VALUES (?, 'pending')",
        ((url,) for url in sitemap_urls),
    )
    db.commit()


def discover_sitemap_entries(
    session: requests.Session,
    robots: RobotFileParser,
    db: sqlite3.Connection,
    base_url: str,
    user_agent: str,
    max_sitemaps: int,
    delay: float,
) -> int:
    """Process a bounded number of queued sitemap files and persist discoveries."""
    processed = 0
    while processed < max_sitemaps:
        row = db.execute(
            "SELECT url FROM sitemap_queue WHERE status='pending' ORDER BY rowid LIMIT 1"
        ).fetchone()
        if row is None:
            break
        sitemap_url = row[0]
        if not same_host(sitemap_url, base_url) or not robots.can_fetch(user_agent, sitemap_url):
            db.execute("UPDATE sitemap_queue SET status='skipped' WHERE url=?", (sitemap_url,))
            db.commit()
            LOG.info("Skipping sitemap not allowed or outside the approved host: %s", sitemap_url)
            processed += 1
            continue

        time.sleep(delay)
        response = fetch(session, sitemap_url)
        kind, locations = parse_sitemap_bytes(response.content, sitemap_url)
        if kind == "sitemapindex":
            db.executemany(
                "INSERT OR IGNORE INTO sitemap_queue(url, status) VALUES (?, 'pending')",
                ((url,) for url in locations if same_host(url, base_url)),
            )
        elif kind == "urlset":
            db.executemany(
                "INSERT OR IGNORE INTO product_queue(url, status) VALUES (?, 'pending')",
                ((url,) for url in locations if same_host(url, base_url)),
            )
        else:
            LOG.warning("Unrecognized sitemap root %r at %s", kind, sitemap_url)
        db.execute("UPDATE sitemap_queue SET status='done' WHERE url=?", (sitemap_url,))
        db.commit()
        processed += 1
        LOG.info("Processed sitemap %d/%d: %s", processed, max_sitemaps, sitemap_url)
    return processed


def process_product_queue(
    session: requests.Session,
    robots: RobotFileParser,
    db: sqlite3.Connection,
    user_agent: str,
    limit: int,
    delay: float,
) -> tuple[int, int]:
    inspected = extracted = 0
    while inspected < limit:
        row = db.execute(
            "SELECT url FROM product_queue WHERE status='pending' ORDER BY rowid LIMIT 1"
        ).fetchone()
        if row is None:
            break
        page_url = row[0]
        if not robots.can_fetch(user_agent, page_url):
            db.execute(
                "UPDATE product_queue SET status='skipped', last_error=? WHERE url=?",
                ("Disallowed by robots.txt", page_url),
            )
            db.commit()
            continue

        time.sleep(delay)
        try:
            response = fetch(session, page_url)
        except requests.HTTPError as exc:
            status = getattr(exc.response, "status_code", None)
            if status is not None and 400 <= status < 500 and status not in STOP_STATUSES:
                db.execute(
                    "UPDATE product_queue SET status='skipped', last_error=? WHERE url=?",
                    (f"HTTP {status}", page_url),
                )
                db.commit()
                inspected += 1
                continue
            raise

        product = extract_product(response.text, page_url)
        if product:
            db.execute(
                """INSERT OR IGNORE INTO products(url, title, price, currency)
                   VALUES (?, ?, ?, ?)""",
                (product["url"], product["title"], product["price"], product["currency"]),
            )
            extracted += 1
        db.execute("UPDATE product_queue SET status='done', last_error=NULL WHERE url=?", (page_url,))
        db.commit()
        inspected += 1
        if inspected % 10 == 0:
            LOG.info("Inspected %d pages in this run; extracted %d products.", inspected, extracted)
    return inspected, extracted


def export_csv(db: sqlite3.Connection, output_path: Path, batch_size: int = 1000) -> int:
    """Stream database rows to CSV in bounded batches; atomically replace output."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(output_path.name + ".tmp")
    cursor = db.execute(
        "SELECT title, price, currency, url FROM products ORDER BY url"
    )
    count = 0
    try:
        with temp_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(["title", "price", "currency", "url"])
            while True:
                rows = cursor.fetchmany(batch_size)
                if not rows:
                    break
                writer.writerows(rows)
                count += len(rows)
        temp_path.replace(output_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return count


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect a small, permitted product-page sample."
    )
    parser.add_argument("--base-url", required=True,
                        help="Base URL of a site you are authorized to crawl.")
    parser.add_argument("--limit", type=int, default=25,
                        help="Maximum product pages to inspect in this run (default: 25).")
    parser.add_argument("--max-sitemaps", type=int, default=10,
                        help="Maximum sitemap files to process in this run (default: 10).")
    parser.add_argument("--delay", type=float, default=5.0,
                        help="Seconds between requests (minimum: 3).")
    parser.add_argument("--user-agent", required=True,
                        help="Transparent crawler identity with a contact address.")
    parser.add_argument("--db", default="catalog_sample.sqlite3")
    parser.add_argument("--output", default="products_sample.csv")
    args = parser.parse_args()

    if not 1 <= args.limit <= 100:
        parser.error("--limit must be between 1 and 100 for the initial sample.")
    if not 1 <= args.max_sitemaps <= 25:
        parser.error("--max-sitemaps must be between 1 and 25 per run.")
    if args.delay < 3:
        parser.error("--delay must be at least 3 seconds.")
    if not args.user_agent.strip():
        parser.error("--user-agent cannot be empty.")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    session = get_session(args.user_agent)
    db = init_db(Path(args.db))
    try:
        robots, sitemap_urls = load_robots(session, args.base_url)
        seed_sitemaps(db, sitemap_urls)
        sitemap_count = discover_sitemap_entries(
            session, robots, db, args.base_url, args.user_agent,
            args.max_sitemaps, args.delay,
        )
        inspected, extracted = process_product_queue(
            session, robots, db, args.user_agent, args.limit, args.delay,
        )
        total = db.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        pending_sitemaps = db.execute(
            "SELECT COUNT(*) FROM sitemap_queue WHERE status='pending'"
        ).fetchone()[0]
        pending_products = db.execute(
            "SELECT COUNT(*) FROM product_queue WHERE status='pending'"
        ).fetchone()[0]
        exported = export_csv(db, Path(args.output))
        LOG.info("Sitemaps processed this run: %d", sitemap_count)
        LOG.info("Product pages inspected this run: %d", inspected)
        LOG.info("Products extracted this run: %d", extracted)
        LOG.info("Unique products stored: %d", total)
        LOG.info("Pending sitemap files: %d", pending_sitemaps)
        LOG.info("Pending product pages: %d", pending_products)
        LOG.info("CSV rows exported: %d (%s)", exported, args.output)
        return 0
    except Exception as exc:
        db.commit()
        LOG.error("%s", exc)
        LOG.error("Saved work remains in SQLite. Resolve permission/site issues before retrying.")
        return 1
    finally:
        db.close()
        session.close()


if __name__ == "__main__":
    sys.exit(main())
