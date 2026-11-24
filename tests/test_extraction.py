from catalog_scraper import extract_product


def test_extracts_product_jsonld():
    html = '''
    <html><head>
      <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "Drain Pump",
        "offers": {
          "@type": "Offer",
          "price": "29.95",
          "priceCurrency": "CHF"
        }
      }
      </script>
    </head></html>
    '''
    assert extract_product(html, "https://example.test/drain-pump") == {
        "title": "Drain Pump",
        "price": "29.95",
        "currency": "CHF",
        "url": "https://example.test/drain-pump",
    }


def test_extracts_product_from_graph():
    html = '''
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@graph": [
        {"@type": "BreadcrumbList", "name": "Parts"},
        {
          "@type": "Product",
          "name": "Door Seal",
          "offers": [{"price": "18.00", "priceCurrency": "EUR"}]
        }
      ]
    }
    </script>
    '''
    product = extract_product(html, "https://example.test/door-seal")
    assert product is not None
    assert product["title"] == "Door Seal"
    assert product["price"] == "18.00"
    assert product["currency"] == "EUR"


def test_returns_none_when_no_product_jsonld():
    html = '<html><body><h1>Not a product page</h1></body></html>'
    assert extract_product(html, "https://example.test/") is None
