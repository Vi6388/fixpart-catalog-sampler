import csv
import sqlite3

from catalog_scraper import export_csv, init_db, seed_sitemaps


def test_database_queues_resume_without_duplicate_urls(tmp_path):
    db = init_db(tmp_path / "sample.sqlite3")
    try:
        seed_sitemaps(db, ["https://example.test/sitemap.xml"])
        seed_sitemaps(db, ["https://example.test/sitemap.xml"])
        assert db.execute("SELECT COUNT(*) FROM sitemap_queue").fetchone()[0] == 1
        db.execute("INSERT OR IGNORE INTO product_queue(url) VALUES (?)", ("https://example.test/p/1",))
        db.execute("INSERT OR IGNORE INTO product_queue(url) VALUES (?)", ("https://example.test/p/1",))
        db.commit()
        assert db.execute("SELECT COUNT(*) FROM product_queue").fetchone()[0] == 1
    finally:
        db.close()


def test_csv_export_writes_header_and_product_rows(tmp_path):
    db = init_db(tmp_path / "sample.sqlite3")
    try:
        db.execute(
            "INSERT INTO products(url,title,price,currency) VALUES (?,?,?,?)",
            ("https://example.test/p/1", "Drain Pump", "29.95", "CHF"),
        )
        db.commit()
        output = tmp_path / "out" / "products.csv"
        count = export_csv(db, output, batch_size=1)
        assert count == 1
        with output.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))
        assert rows[0] == ["title", "price", "currency", "url"]
        assert rows[1] == ["Drain Pump", "29.95", "CHF", "https://example.test/p/1"]
    finally:
        db.close()
