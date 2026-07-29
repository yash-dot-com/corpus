"""HTML parsing and document extraction for Corpora workers."""

import re
from dataclasses import dataclass
from typing import Optional

from bs4 import BeautifulSoup


@dataclass(frozen=True)
class DocumentMetadata:
    """Metadata extracted from an HTML document."""

    description: Optional[str]
    keywords: list[str]


@dataclass(frozen=True)
class ParsedDocument:
    """Parsed document data used to build a worker result."""

    title: Optional[str]
    language: Optional[str]
    text: str
    html: str
    metadata: DocumentMetadata
    links: list[str]


def parse(html: str) -> ParsedDocument:
    """Parse HTML into clean document content, metadata, and raw links."""
    parser = "html.parser" if _looks_malformed_title(html) else "lxml"
    soup = BeautifulSoup(html, parser)

    title = _tag_text(soup.title)
    if title is None or _looks_malformed_title(html):
        title = _recover_title(html)

    language = soup.html.get("lang") if soup.html else None
    metadata = DocumentMetadata(
        description=_meta_content(soup, "description"),
        keywords=_keywords(soup),
    )
    links = _links(soup)

    for element in soup(["script", "style", "noscript"]):
        element.decompose()

    return ParsedDocument(
        title=title,
        language=language,
        text=soup.get_text(" ", strip=True),
        html=html,
        metadata=metadata,
        links=links,
    )


def _looks_malformed_title(html: str) -> bool:
    """Return whether a title tag appears to be never closed before the next markup."""
    title_open = re.search(r"<title\b[^>]*>", html, flags=re.IGNORECASE)
    if title_open is None:
        return False

    title_body = html[title_open.end() :]
    if re.search(r"</title\b[^>]*>", title_body, flags=re.IGNORECASE):
        return False

    return True


def _recover_title(html: str) -> Optional[str]:
    """Recover a title from malformed HTML when the parser consumes too much."""
    match = re.search(r"<title\s*>(.*?)</title\s*>", html, flags=re.IGNORECASE | re.DOTALL)
    if match is None:
        match = re.search(r"<title\s*>(.*?)<", html, flags=re.IGNORECASE | re.DOTALL)

    if match is None:
        return None

    title = re.sub(r"\s+", " ", match.group(1)).strip()
    return title or None


def _tag_text(tag: object) -> Optional[str]:
    """Return stripped text from an optional BeautifulSoup tag."""
    if tag is None:
        return None

    text = tag.get_text(" ", strip=True)
    return text or None


def _meta_content(soup: BeautifulSoup, name: str) -> Optional[str]:
    """Return a named meta tag's non-empty content value."""
    tag = soup.find("meta", attrs={"name": name})
    if tag is None:
        return None

    content = tag.get("content")
    if not isinstance(content, str):
        return None

    return content.strip() or None


def _keywords(soup: BeautifulSoup) -> list[str]:
    """Split the keywords meta value into non-empty keyword strings."""
    content = _meta_content(soup, "keywords")
    if content is None:
        return []

    return [keyword.strip() for keyword in content.split(",") if keyword.strip()]


def _links(soup: BeautifulSoup) -> list[str]:
    """Extract non-empty raw href values without manipulating URLs."""
    links: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href")
        if isinstance(href, str) and href:
            links.append(href)

    return links
