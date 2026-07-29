"""Tests for HTML document parsing and link extraction."""

from src.parser import parse


def test_parse_extracts_document_fields_metadata_and_raw_links() -> None:
    """The parser extracts the document data needed by a worker result."""
    html = """
<!doctype html>
<html lang="en">
  <head>
    <title>Corpora page</title>
    <meta name="description" content="Corpus generation">
    <meta name="keywords" content="crawling, datasets,  corpora ">
  </head>
  <body>
    <main>Hello <strong>world</strong>.</main>
    <a href="/about">About</a>
    <a href="https://other.example/page">External</a>
    <a href="#section">Section</a>
    <a>No destination</a>
    <a href="">Empty destination</a>
  </body>
</html>
"""

    document = parse(html)

    assert document.title == "Corpora page"
    assert document.language == "en"
    assert document.text == "Corpora page Hello world . About External Section No destination Empty destination"
    assert document.html == html
    assert document.metadata.description == "Corpus generation"
    assert document.metadata.keywords == ["crawling", "datasets", "corpora"]
    assert document.links == ["/about", "https://other.example/page", "#section"]


def test_parse_excludes_non_content_elements_from_clean_text() -> None:
    """Script, style, and noscript content do not enter the document text."""
    document = parse(
        """
<html>
  <head><style>.hidden { display: none; }</style></head>
  <body>
    <script>window.analytics = true;</script>
    <noscript>Enable JavaScript</noscript>
    <p>Visible content</p>
  </body>
</html>
"""
    )

    assert document.text == "Visible content"


def test_parse_handles_missing_optional_metadata() -> None:
    """Pages without optional metadata return explicit empty values."""
    document = parse("<html><body><p>Content</p></body></html>")

    assert document.title is None
    assert document.language is None
    assert document.metadata.description is None
    assert document.metadata.keywords == []
    assert document.links == []


def test_parse_handles_malformed_html() -> None:
    """Malformed HTML still produces usable text and link data."""
    document = parse("<html lang='en'><title>Broken<title><body>Text<a href='/next'>Next")

    assert document.title == "Broken"
    assert document.language == "en"
    assert "Text" in document.text
    assert document.links == ["/next"]
