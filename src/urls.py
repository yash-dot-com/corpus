"""URL utilities for Corpora."""

from ipaddress import ip_address
from posixpath import normpath
from re import fullmatch, sub
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse


SUPPORTED_SCHEMES = {"http", "https"}


class InvalidURLException(Exception):
    """Raised when a URL is malformed."""


class UnsupportedSchemeError(Exception):
    """Raised when a URL scheme is not supported."""


def validate(url: str) -> None:
    """Validate that a URL has a supported scheme and valid hostname.

    Raises:
        InvalidURLException: If the URL is malformed or has no hostname.
        UnsupportedSchemeError: If the URL scheme is not HTTP or HTTPS.
    """
    if not url or any(character.isspace() for character in url):
        raise InvalidURLException("URL must not be empty or contain whitespace.")

    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError as error:
        raise InvalidURLException(f"Malformed URL: {url}") from error

    if not parsed.scheme:
        raise InvalidURLException("URL is missing a scheme.")

    if parsed.scheme.lower() not in SUPPORTED_SCHEMES:
        raise UnsupportedSchemeError(f"Unsupported scheme: {parsed.scheme}")

    if not parsed.hostname:
        raise InvalidURLException("URL is missing a hostname.")

    _validate_hostname(parsed.hostname)

    if port is not None and not 0 < port <= 65535:
        raise InvalidURLException(f"URL has an invalid port: {port}")


def normalize(url: str) -> str:
    """Normalize a URL without removing fragments or sorting its query string."""
    validate(url)
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    hostname = parsed.hostname.lower() if parsed.hostname else ""
    netloc = _normalized_netloc(parsed.netloc, hostname, parsed.port, scheme)
    path = _normalize_path(parsed.path)

    return urlunparse(parsed._replace(scheme=scheme, netloc=netloc, path=path))


def canonicalize(url: str) -> str:
    """Produce a canonical URL suitable for deduplication."""
    validate(url)
    parsed = urlparse(url)
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))

    return urlunparse(parsed._replace(query=query, fragment=""))


def resolve(base_url: str, href: str) -> str:
    """Resolve a relative link against a base URL."""
    return urljoin(base_url, href)


def _validate_hostname(hostname: str) -> None:
    """Raise when a hostname is neither a valid IP address nor domain name."""
    try:
        ip_address(hostname)
        return
    except ValueError:
        pass

    try:
        ascii_hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError as error:
        raise InvalidURLException(f"Malformed hostname: {hostname}") from error

    if len(ascii_hostname) > 253:
        raise InvalidURLException(f"Malformed hostname: {hostname}")

    labels = ascii_hostname.rstrip(".").split(".")
    if not labels or any(
        not fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
        for label in labels
    ):
        raise InvalidURLException(f"Malformed hostname: {hostname}")


def _normalized_netloc(
    netloc: str,
    hostname: str,
    port: Optional[int],
    scheme: str,
) -> str:
    """Rebuild a netloc with normalized host casing and default ports removed."""
    userinfo, separator, _ = netloc.rpartition("@")
    authority = f"{userinfo}{separator}" if separator else ""

    try:
        ip_address(hostname)
        host = f"[{hostname}]" if ":" in hostname else hostname
    except ValueError:
        host = hostname

    if (scheme, port) in {("http", 80), ("https", 443)}:
        port = None

    if port is None:
        return f"{authority}{host}"

    return f"{authority}{host}:{port}"


def _normalize_path(path: str) -> str:
    """Collapse repeated separators and dot segments in an absolute URL path."""
    normalized_path = normpath(sub(r"/{2,}", "/", path))

    if normalized_path == ".":
        return "/"

    return normalized_path if normalized_path.startswith("/") else f"/{normalized_path}"
