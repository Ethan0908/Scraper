from event_scraper.cleaning import clean_name, extract_email, normalise_url


def test_normalise_url_removes_tracking_params():
    assert normalise_url("https://example.com/a?utm_source=x&ok=1#frag") == "https://example.com/a?ok=1"


def test_clean_name_rejects_ui_labels():
    assert clean_name("Follow") is None
    assert clean_name("Jane Smith") == "Jane Smith"


def test_extract_email():
    assert extract_email("Contact us at hello@example.com for details") == "hello@example.com"
