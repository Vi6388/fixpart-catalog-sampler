
from types import SimpleNamespace

from catalog_scraper import init_db, process_product_queue


class FakeRobots:
    def can_fetch(self, user_agent, url):
        return True


def test_pending_products_resume_after_restart(tmp_path, monkeypatch):
    db_path = tmp_path / "resume_test.sqlite3"

    first_url = "https://example.test/product-1"
    second_url = "https://example.test/product-2"

    # Create two pending products.
    db = init_db(db_path)

    db.executemany(
        "INSERT INTO product_queue(url, status) VALUES (?, ?)",
        [
            (first_url, "pending"),
            (second_url, "pending"),
        ],
    )
    db.commit()

    # Mock HTTP requests so no real website is contacted.
    fetched_urls = []

    def fake_fetch(session, url):
        fetched_urls.append(url)

        html = f"""
        <script type="application/ld+json">
        {{
            "@type": "Product",
            "name": "Test Product",
            "offers": {{
                "price": "29.95",
                "priceCurrency": "CHF"
            }}
        }}
        </script>
        """

        return SimpleNamespace(text=html)

    monkeypatch.setattr(
        "catalog_scraper.fetch",
        fake_fetch
    )

    # Process only one product, simulating an interrupted run.
    inspected, extracted = process_product_queue(
        None,
        FakeRobots(),
        db,
        "TestBot",
        1,
        0,
    )

    assert inspected == 1
    assert extracted == 1

    db.close()

    # Restart the database.
    db = init_db(db_path)

    # The first product should be done.
    first_status = db.execute(
        "SELECT status FROM product_queue WHERE url = ?",
        (first_url,),
    ).fetchone()[0]

    assert first_status == "done"

    # The second product should still be pending.
    second_status = db.execute(
        "SELECT status FROM product_queue WHERE url = ?",
        (second_url,),
    ).fetchone()[0]

    assert second_status == "pending"

    # Resume processing.
    inspected, extracted = process_product_queue(
        None,
        FakeRobots(),
        db,
        "TestBot",
        1,
        0,
    )

    assert inspected == 1
    assert extracted == 1

    assert fetched_urls == [first_url, second_url]

    db.close()
