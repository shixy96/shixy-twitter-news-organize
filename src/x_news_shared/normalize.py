#!/usr/bin/env python3
"""URL normalization utilities extracted from x_news_common.py."""

from urllib.parse import urlparse


X_DOMAINS = {"x.com", "twitter.com"}


def normalize_domain(value: str) -> str:
    domain = value.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain.rstrip(".").split(":")[0]


def normalize_x_url(value: str) -> str | None:
    if not value:
        return None
    parsed = urlparse(value.strip())
    if not parsed.scheme or not parsed.netloc:
        return None
    domain = normalize_domain(parsed.netloc)
    if domain not in X_DOMAINS:
        return None
    path = parsed.path.rstrip("/")
    if not path:
        return None
    return f"https://x.com{path}"


def normalize_external_url(value: str) -> str | None:
    if not value:
        return None
    parsed = urlparse(value.strip())
    if not parsed.scheme or not parsed.netloc:
        return None
    domain = normalize_domain(parsed.netloc)
    path = parsed.path.rstrip("/")
    normalized = f"https://{domain}{path}"
    if parsed.query:
        normalized = f"{normalized}?{parsed.query}"
    if parsed.fragment:
        normalized = f"{normalized}#{parsed.fragment}"
    return normalized


def normalize_link(value: str) -> str | None:
    x_url = normalize_x_url(value)
    if x_url:
        return x_url
    return normalize_external_url(value)
