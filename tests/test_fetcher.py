"""Contract tests for the stateless HTTP fetcher.

These tests intentionally precede the fetcher implementation.
"""

import httpx
import pytest

from src.fetcher import FetchRequestError, HttpFetcher


def test_fetcher_returns_successful_response_details() -> None:
    """A successful response exposes worker-relevant fetch details."""
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["user-agent"] == "corpora/0.1"
        assert request.extensions["timeout"] == {
            "connect": 15.0,
            "read": 15.0,
            "write": 15.0,
            "pool": 15.0,
        }
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=b"<html><title>Corpora</title></html>",
            request=request,
        )

    fetcher = HttpFetcher(
        user_agent="corpora/0.1",
        timeout_seconds=15.0,
        transport=httpx.MockTransport(handler),
    )

    result = fetcher.fetch("https://example.com/page")

    assert result.requested_url == "https://example.com/page"
    assert result.final_url == "https://example.com/page"
    assert result.status_code == 200
    assert result.redirect_chain == ["https://example.com/page"]
    assert result.content_type == "text/html"
    assert result.content == b"<html><title>Corpora</title></html>"


def test_fetcher_follows_redirects_and_records_the_complete_chain() -> None:
    """Redirect responses lead to the final page and preserve redirect history."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(
                301,
                headers={"location": "/final"},
                request=request,
            )

        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=b"final page",
            request=request,
        )

    fetcher = HttpFetcher(
        user_agent="corpora/0.1",
        timeout_seconds=10.0,
        transport=httpx.MockTransport(handler),
    )

    result = fetcher.fetch("https://example.com/start")

    assert result.requested_url == "https://example.com/start"
    assert result.final_url == "https://example.com/final"
    assert result.status_code == 200
    assert result.redirect_chain == [
        "https://example.com/start",
        "https://example.com/final",
    ]


def test_fetcher_returns_non_success_http_responses() -> None:
    """HTTP status codes are recorded rather than converted into fetch errors."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=b"not found", request=request)

    fetcher = HttpFetcher(
        user_agent="corpora/0.1",
        timeout_seconds=10.0,
        transport=httpx.MockTransport(handler),
    )

    result = fetcher.fetch("https://example.com/missing")

    assert result.status_code == 404
    assert result.content_type is None
    assert result.content == b"not found"


def test_fetcher_wraps_httpx_request_failures() -> None:
    """Transport failures become a stable domain-specific fetch error."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed", request=request)

    fetcher = HttpFetcher(
        user_agent="corpora/0.1",
        timeout_seconds=10.0,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(FetchRequestError) as error:
        fetcher.fetch("https://example.com/unavailable")

    assert "https://example.com/unavailable" in str(error.value)
