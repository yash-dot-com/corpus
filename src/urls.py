"""
URL utilities for Corpora.
Every URL that enters the crawler should eventually pass through this module.
"""

from posixpath import normpath
from urllib.parse import (
    parse_qsl,
    urlencode,
    urljoin,
    urlparse,
    urlunparse,
)

SUPPORTED_SCHEMES = {"http", "https"}


class InvalidURLException(Exception):
    """Raised when a URL is malformed."""


class UnsupportedSchemeError(Exception):
    """Raised when a URL scheme is not supported."""


def validate(url: str) -> None:
    """
    Validate that a URL is crawlable.

    Raises:
        InvalidURLException
        UnsupportedSchemeError
    """

    parsed = urlparse(url)

    if not parsed.scheme:
        raise InvalidURLException("URL is missing a scheme.")

    if parsed.scheme.lower() not in SUPPORTED_SCHEMES:
        raise UnsupportedSchemeError(
            f"Unsupported scheme: {parsed.scheme}"
        )

    if not parsed.hostname:
        raise InvalidURLException("URL is missing a hostname.")


def normalize(url: str) -> str:
    """
    Normalize superficial URL differences.
    Does NOT remove fragments or sort query parameters.
    """

    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    hostname = parsed.hostname.lower() if parsed.hostname else ""
    port = parsed.port

    if (
        (scheme == "http" and port == 80)
        or (scheme == "https" and port == 443)
    ):
        port = None

    netloc = hostname

    if port is not None:
        netloc = f"{hostname}:{port}"

    path = normpath(parsed.path)

    if path == ".":
        path = "/"

    if not path.startswith("/"):
        path = "/" + path

    normalized = parsed._replace(
        scheme=scheme,
        netloc=netloc,
        path=path,
    )

    return urlunparse(normalized)


def canonicalize(url: str) -> str:
    """
    Produce a canonical URL suitable for deduplication.
    """

    parsed = urlparse(url)
    query = urlencode(sorted(parse_qsl(parsed.query)))

    canonical = parsed._replace(
        query=query,
        fragment="",
    )

    return urlunparse(canonical)


def resolve(base_url: str, href: str) -> str:
    """
    Resolve a relative link against a base URL.
    """

    return urljoin(base_url, href)

if __name__ == "__main__":

    print("========== validate ==========")

    test_urls = [
        "https://example.com",
        "http://example.com",
        "https://sub.example.com",
        "ftp://example.com",
        "mailto:test@example.com",
        "javascript:alert(1)",
        "https://",
        "example.com",
    ]

    for url in test_urls:
        try:
            validate(url)
            print(f"✓ {url}")
        except Exception as e:
            print(f"✗ {url} -> {type(e).__name__}: {e}")

    print("\n========== normalize ==========")

    normalize_tests = [
        "HTTPS://Example.COM",
        "https://example.com:443",
        "http://example.com:80",
        "https://example.com:8443",
        "https://example.com//blog///post",
        "https://example.com/blog/./python",
        "https://example.com/blog/../about",
        "https://example.com",
    ]

    for url in normalize_tests:
        print(f"{url}")
        print(f" -> {normalize(url)}")
        print()

    print("========== canonicalize ==========")

    canonical_tests = [
        "https://example.com?b=1&a=2",
        "https://example.com/page#section",
        "https://example.com/page?z=3&a=1#top",
        "https://example.com?a=2&a=1",
    ]

    for url in canonical_tests:
        print(f"{url}")
        print(f" -> {canonicalize(url)}")
        print()

    print("========== resolve ==========")

    base = "https://example.com/blog/post"

    hrefs = [
        "/about",
        "../contact",
        "./faq",
        "team.html",
        "?page=2",
        "#comments",
        "https://google.com",
    ]

    for href in hrefs:
        print(f"{href}")
        print(f" -> {resolve(base, href)}")
