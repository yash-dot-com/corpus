"""Stateless HTTP fetching for AWS lambda workers."""

from dataclasses import dataclass
from typing import Optional

import httpx


class FetchRequestError(Exception):
    """Raised when an HTTP request cannot be completed."""


@dataclass(frozen=True)
class FetchResponse:
    """HTTP response data needed by later worker stages."""

    requested_url: str
    final_url: str
    status_code: int
    redirect_chain: list[str]
    content_type: Optional[str]
    content: bytes


class HttpFetcher:
    """Fetch one URL at a time without owning any crawl state."""

    def __init__(
        self,
        user_agent: str,
        timeout_seconds: float,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        """Configure request headers, timeout, and an optional test transport."""
        self._user_agent = user_agent
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def fetch(self, url: str) -> FetchResponse:
        """Fetch a URL, following redirects and returning its final response."""
        try:
            with httpx.Client(
                follow_redirects=True,
                headers={"User-Agent": self._user_agent},
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = client.get(url)
        except httpx.RequestError as error:
            raise FetchRequestError(f"Unable to fetch URL: {url}") from error

        redirect_chain = [str(history.url) for history in response.history]
        redirect_chain.append(str(response.url))

        return FetchResponse(
            requested_url=url,
            final_url=str(response.url),
            status_code=response.status_code,
            redirect_chain=redirect_chain,
            content_type=_content_type(response),
            content=response.content,
        )


def _content_type(response: httpx.Response) -> Optional[str]:
    """Return the response media type without optional header parameters."""
    content_type = response.headers.get("content-type")
    if content_type is None:
        return None

    return content_type.split(";", maxsplit=1)[0].strip().lower()
