
from catalog_scraper import extract_product


# TEST 1: Extract a normal product title and price
def test_extracts_product_jsonld():
    html = '''
    <script type="application/ld+json">
    {
        "@type": "Product",
        "name": "Drain Pump",
        "offers": {
            "price": "29.95",
            "priceCurrency": "CHF"
        }
    }
    </script>
    '''

    result = extract_product(
        html,
        "https://example.test/drain-pump"
    )

    assert result["title"] == "Drain Pump"
    assert result["price"] == "29.95"
    assert result["currency"] == "CHF"


# TEST 2: Extract a product inside JSON-LD graph
def test_extracts_product_from_graph():
    html = '''
    <script type="application/ld+json">
    {
        "@graph": [
            {
                "@type": "BreadcrumbList",
                "name": "Parts"
            },
            {
                "@type": "Product",
                "name": "Door Seal",
                "offers": [
                    {
                        "price": "18.00",
                        "priceCurrency": "EUR"
                    }
                ]
            }
        ]
    }
    </script>
    '''

    result = extract_product(
        html,
        "https://example.test/door-seal"
    )

    assert result is not None
    assert result["title"] == "Door Seal"
    assert result["price"] == "18.00"
    assert result["currency"] == "EUR"


# TEST 3: Handle a page without product information
def test_returns_none_without_product_jsonld():
    html = '''
    <html>
        <body>
            <h1>Not a product page</h1>
        </body>
    </html>
    '''

    result = extract_product(
        html,
        "https://example.test/"
    )

    assert result is None


# TEST 4: Extract a product without a price
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


# TEST 5: Extract the lowest price from an offer
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

    assert result is not None
    assert result["title"] == "Refrigerator Filter"
    assert result["price"] == "19.95"
    assert result["currency"] == "CHF"


# TEST 6: Extract price from priceSpecification
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

    assert result is not None
    assert result["title"] == "Motor Assembly"
    assert result["price"] == "45.50"
    assert result["currency"] == "EUR"


# TEST 7: Ignore malformed JSON-LD
def test_handles_malformed_jsonld():
    html = '''
    <script type="application/ld+json">
    {
        "type": "Product",
        "name": "Broken Product",
        "offers":
    }
    </script>
    '''

    result = extract_product(
        html,
        "https://example.test/broken"
    )

    assert result is None


# TEST 8: Handle a product without a title
def test_product_without_title_returns_none():
    html = '''
    <script type="application/ld+json">
    {
        "@type": "Product",
        "offers": {
            "price": "35.00",
            "priceCurrency": "CHF"
        }
    }
    </script>
    '''

    result = extract_product(
        html,
        "https://example.test/untitled"
    )

    assert result is None
