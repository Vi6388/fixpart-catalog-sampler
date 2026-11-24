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


def test_product_without_price_returns_empty_price():
    html = '''
    <script type="application/ld+json">
    {
        "@type": "Product",
        "name": "Washing Machine Filter"
    }
    </script>
    '''

    result = extract_product(
        html,
        "https://example.test/filter"
    )

    assert result is not None
    assert result["title"] == "Washing Machine Filter"
    assert result["price"] == ""


def test_extracts_low_price_from_offer():
    html = '''
    <script type="application/ld+json">
    {
        "@type": "Product",
        "name": "Refrigerator Filter",
        "offers": [
            {
                "@type": "AggregateOffer",
                "lowPrice": "19.95",
                "priceCurrency": "CHF"
            }
        ]
    }
    </script>
    '''

    result = extract_product(
        html,
        "https://example.test/filter"
    )

    assert result["title"] == "Refrigerator Filter"
    assert result["price"] == "19.95"
    assert result["currency"] == "CHF"


def test_extracts_price_specification():
    html = '''
    <script type="application/ld+json">
    {
        "@type": "Product",
        "name": "Motor Assembly",
        "offers": {
            "priceSpecification": {
                "price": "45.50",
                "priceCurrency": "EUR"
            }
        }
    }
    </script>
    '''

    result = extract_product(
        html,
        "https://example.test/motor"
    )

    assert result["title"] == "Motor Assembly"
    assert result["price"] == "45.50"
    assert result["currency"] == "EUR"
