import base64

import pytest

from event_scraper.exporters import parse_google_credentials


VALID_CREDS = {
    "type": "service_account",
    "client_email": "bot@example.iam.gserviceaccount.com",
    "private_key": "-----BEGIN PRIVATE KEY-----\\nabc\\n-----END PRIVATE KEY-----\\n",
}


def test_parse_google_credentials_wraps_inner_json_lines():
    parsed = parse_google_credentials('"type":"service_account","client_email":"bot@example.iam.gserviceaccount.com","private_key":"key"')
    assert parsed["type"] == "service_account"


def test_parse_google_credentials_accepts_base64_json():
    import json

    encoded = base64.b64encode(json.dumps(VALID_CREDS).encode("utf-8")).decode("utf-8")
    parsed = parse_google_credentials(credentials_b64=encoded)
    assert parsed["client_email"] == VALID_CREDS["client_email"]


def test_parse_google_credentials_reports_bad_secret():
    with pytest.raises(ValueError, match="Could not parse Google"):
        parse_google_credentials('"type":"service_account"\n"client_email":"bot@example.com"')
