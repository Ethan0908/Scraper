from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

TRACKING_PREFIXES = ("utm_",)
TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid", "igshid"}
NOISE_LINK_PATTERNS = (
    "schema.org",
    "w3.org",
    "images.lumacdn.com",
    "static.",
    "javascript:",
    "mailto:?",
)
NOISE_LABELS = {
    "follow",
    "profile",
    "linkedin",
    "instagram",
    "twitter",
    "x",
    "github",
    "website",
    "subscribe",
    "share",
    "contact",
    "calendar",
}
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", value).strip()
    return text or None


def clean_name(value: str | None) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    lowered = text.lower()
    if lowered in NOISE_LABELS:
        return None
    if len(text) > 120:
        return None
    return text


def normalise_url(url: str | None, base_url: str | None = None) -> str | None:
    if not url:
        return None
    absolute = urljoin(base_url, url) if base_url else url
    parsed = urlparse(absolute)
    if not parsed.scheme or not parsed.netloc:
        return None
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key not in TRACKING_KEYS and not any(key.startswith(prefix) for prefix in TRACKING_PREFIXES)
    ]
    parsed = parsed._replace(query=urlencode(query), fragment="")
    return urlunparse(parsed)


def is_noise_url(url: str | None) -> bool:
    if not url:
        return True
    lowered = url.lower()
    return any(pattern in lowered for pattern in NOISE_LINK_PATTERNS)


def extract_email(text: str | None) -> str | None:
    if not text:
        return None
    match = EMAIL_RE.search(text)
    return match.group(0) if match else None


def split_categories(text: str | None) -> list[str]:
    if not text:
        return []
    pieces = re.split(r"[,•|/]", text)
    return sorted({piece.strip() for piece in pieces if 1 < len(piece.strip()) <= 40})
