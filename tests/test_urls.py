"""Tests for URL utilities."""

import pytest

from src.urls import (
    InvalidURLException,
    UnsupportedSchemeError,
    canonicalize,
    normalize,
    resolve,
    validate,
)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://sub.example.com/path?query=value#section",
        "HTTPS://EXAMPLE.COM",
        "https://[2001:db8::1]/",
    ],
)
def test_validate_accepts_crawlable_http_urls(url: str) -> None:
    """HTTP and HTTPS URLs with hostnames are crawlable."""
    assert validate(url) is None


@pytest.mark.parametrize("url", ["ftp://example.com", "mailto:hi@example.com"])
def test_validate_rejects_unsupported_schemes(url: str) -> None:
    """Only HTTP and HTTPS are supported by the crawler."""
    with pytest.raises(UnsupportedSchemeError):
        validate(url)


@pytest.mark.parametrize(
    "url",
    [
        "",
        "example.com",
        "https://",
        "http:///path",
        "https://exa mple.com",
        "https://example.com:bad-port",
        "https://[2001:db8::1",
        "https://-example.com",
    ],
)
def test_validate_rejects_malformed_urls(url: str) -> None:
    """Malformed URLs cannot enter the crawl pipeline."""
    with pytest.raises(InvalidURLException):
        validate(url)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("HTTPS://Example.COM", "https://example.com/"),
        ("https://example.com:443", "https://example.com/"),
        ("http://example.com:80", "http://example.com/"),
        ("https://example.com:8443", "https://example.com:8443/"),
        (
            "https://example.com//blog/./python/../post?b=2&a=1#top",
            "https://example.com/blog/post?b=2&a=1#top",
        ),
        (
            "https://user:secret@[2001:DB8::1]:443/path",
            "https://user:secret@[2001:db8::1]/path",
        ),
    ],
)
def test_normalize_standardizes_superficial_url_differences(
    url: str,
    expected: str,
) -> None:
    """Normalization preserves query and fragment while standardizing URLs."""
    assert normalize(url) == expected


def test_normalize_is_idempotent() -> None:
    """Repeated normalization produces the same URL."""
    normalized = normalize("HTTPS://Example.COM//blog/../about")

    assert normalize(normalized) == normalized


def test_normalize_rejects_invalid_url() -> None:
    """Normalization only operates on crawlable URLs."""
    with pytest.raises(InvalidURLException):
        normalize("https://example.com:invalid")


def test_canonicalize_sorts_query_values_and_removes_fragment() -> None:
    """Canonicalization creates stable query ordering for deduplication."""
    url = "https://example.com/page?b=2&a=1&a=#section"

    assert canonicalize(url) == "https://example.com/page?a=&a=1&b=2"


def test_canonicalize_is_idempotent() -> None:
    """Repeated canonicalization produces the same URL."""
    canonical_url = canonicalize("https://example.com/?z=3&a=1#top")

    assert canonicalize(canonical_url) == canonical_url


@pytest.mark.parametrize(
    ("base_url", "href", "expected"),
    [
        ("https://example.com/blog/post", "/about", "https://example.com/about"),
        (
            "https://example.com/blog/post",
            "../contact",
            "https://example.com/contact",
        ),
        (
            "https://example.com/blog/post",
            "?page=2",
            "https://example.com/blog/post?page=2",
        ),
        (
            "https://example.com/blog/post",
            "https://other.example/path",
            "https://other.example/path",
        ),
    ],
)
def test_resolve_converts_links_to_absolute_urls(
    base_url: str,
    href: str,
    expected: str,
) -> None:
    """Relative and absolute links are resolved using standard URL rules."""
    assert resolve(base_url, href) == expected
