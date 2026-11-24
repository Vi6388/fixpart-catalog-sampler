from catalog_scraper import extract_product


def test_extracts_product_jsonld():
    html = '''<script type="application/ld+json">
    {"@type":"Product","name":"Drain Pump","offers":{"price":"29.95","priceCurrency":"CHF"}}
    </script>'''
    result = extract_product(html, "https://example.test/drain-pump")
    assert result == {"title": "Drain Pump", "price": "29.95", "currency": "CHF", "url": "https://example.test/drain-pump"}


def test_extracts_product_from_graph():
    html = '''<script type="application/ld+json">
    {"@graph":[{"@type":"BreadcrumbList","name":"Parts"},{"@type":"Product","name":"Door Seal","offers":[{"price":"18.00","priceCurrency":"EUR"}]}]}
    </script>'''
    result = extract_product(html, "https://example.test/door-seal")
    assert result is not None
    assert result["title"] == "Door Seal"
    assert result["price"] == "18.00"
    assert result["currency"] == "EUR"


def test_returns_none_without_product_jsonld():
    assert extract_product("<h1>Not a product</h1>", "https://example.test/") is None


def test_product_without_price_returns_empty_price():
    html = '''<script type="application/ld+json">{"@type":"Product","name":"Filter"}</script>'''
    result = extract_product(html, "https://example.test/filter")
    assert result is not None and result["price"] == ""


def test_extracts_low_price_from_offer():
    html = '''<script type="application/ld+json">{"@type":"Product","name":"Refrigerator Filter","offers":{"@type":"AggregateOffer","lowPrice":"19.95","priceCurrency":"CHF"}}</script>'''
    result = extract_product(html, "https://example.test/filter")
    assert result is not None
    assert result["price"] == "19.95"
    assert result["currency"] == "CHF"


def test_extracts_price_specification():
    html = '''<script type="application/ld+json">{"@type":"Product","name":"Motor","offers":{"priceSpecification":{"price":"45.50","priceCurrency":"EUR"}}}</script>'''
    result = extract_product(html, "https://example.test/motor")
    assert result is not None
    assert result["price"] == "45.50"
    assert result["currency"] == "EUR"


def test_handles_malformed_jsonld():
    html = '''<script type="application/ld+json">{"@type":"Product","offers":</script>'''
    assert extract_product(html, "https://example.test/broken") is None


def test_product_without_title_returns_none():
    html = '''<script type="application/ld+json">{"@type":"Product","offers":{"price":"35.00","priceCurrency":"CHF"}}</script>'''
    assert extract_product(html, "https://example.test/untitled") is None


def test_rejects_negative_or_non_numeric_price():
    html = '''<script type="application/ld+json">{"@type":"Product","name":"Part","offers":{"price":"-5","priceCurrency":"CHF"}}</script>'''
    result = extract_product(html, "https://example.test/part")
    assert result is not None
    assert result["price"] == ""


def test_reads_product_nested_in_main_entity():
    html = '''<script type="application/ld+json">{"@type":"WebPage","mainEntity":{"@type":"Product","name":"Pump","offers":{"price":12.5,"priceCurrency":"CHF"}}}</script>'''
    result = extract_product(html, "https://example.test/pump")
    assert result is not None
    assert result["title"] == "Pump"
    assert result["price"] == "12.5"
