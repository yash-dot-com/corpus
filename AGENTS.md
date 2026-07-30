# Corpora

Corpora is a cloud-native, production-inspired distributed web corpus generation platform.

Its purpose is **not** to build a search engine. Instead, it generates high-quality web corpora (HTML, cleaned text, metadata, JSONL documents) suitable for downstream applications such as LLM training, RAG pipelines, search indexing, analytics, and dataset generation.

The project is designed primarily as a systems engineering learning project with a strong emphasis on software architecture, clean code, distributed systems, observability, reliability, and cloud-native design.

---

## Design Philosophy

This project follows several strict engineering principles.

- Keep modules small and focused.
- Every component has a single responsibility.
- Favor composition over large classes.
- Avoid unnecessary abstractions until required.
- Standard library whenever possible.
- Strong typing.
- High unit test coverage.
- Every public function should be deterministic whenever possible.

The goal is maintainable production-quality code rather than maximum feature count.

---

# Current Development Stage

This repository is currently implementing Version 1.

Do not implement advanced distributed features unless explicitly requested.

Current focus is building the project incrementally from the foundation upwards.

Current implementation order:

1. CLI
2. Configuration Loader
3. URL Utilities
4. Coordinator
5. HTTP Fetcher
6. HTML Parser
7. Storage Layer
8. AWS Integration
9. Distributed Workers
10. Observability

Current progress:

- Completed: CLI, configuration loader, URL utilities, coordinator, HTTP
  fetcher, and HTML parser.
- Active: storage layer.

---

# Tech Stack

Language:

- Python 3.13

Package Manager:

- uv

CLI:

- Typer

Configuration:

- PyYAML
- Pydantic v2

Networking:

- httpx

HTML Parsing:

- BeautifulSoup4
- lxml

Robots.txt:

- Protego

Database:

- SQLAlchemy
- Alembic

AWS:

- boto3

Testing:

- pytest

Linting:

- Ruff

Type Checking:

- we have static type checking using ty from astral configured no need to do anything for type checking.

---

# Current Folder Structure

The project intentionally uses a flat module structure during initial development.

Do not prematurely reorganize into packages.

Example:

src/corpora/

main.py
config.py
config_models.py
urls.py
coordinator.py
fetcher.py
parser.py
storage.py
database.py
aws.py
exceptions.py

Packages may be introduced later after implementation stabilizes.

---

# CLI

Typer is used.

The CLI should remain extremely thin.

Responsibilities:

- Parse command line arguments
- Load configuration
- Instantiate coordinator
- Start execution

The CLI should never contain business logic.

---

# Configuration

Configuration is provided using YAML.

Example:

seed_urls:
  - https://example.com

allowed_domains:
  - example.com

max_depth: 2

user_agent: corpora/0.1

output_directory: ./output

The loader should:

- Read YAML
- Validate configuration
- Return a Pydantic configuration object

The rest of the application should never read YAML directly.

---

# URL Module

The URL module owns all URL manipulation.

Public API:

validate(url: str)

normalize(url: str)

canonicalize(url: str)

resolve(base_url: str, href: str)

Responsibilities:

validate()

- verify supported scheme
- verify hostname
- reject malformed URLs

normalize()

- lowercase scheme
- lowercase hostname
- remove default ports
- normalize path

canonicalize()

- remove fragments
- sort query parameters

resolve()

- convert relative URLs into absolute URLs using urllib.parse.urljoin()

No other module should manipulate URLs directly.

---

# Coordinator

The coordinator owns crawl state.

Responsibilities:

- scheduling
- deduplication
- crawl depth
- enqueue URLs
- visited set
- crawl frontier
- consume discovered URLs from the Discovery Queue
- enqueue verified crawl jobs to the Crawl Queue

Workers never own crawl state.

The coordinator's work is intentionally lightweight: normalize URLs, check the
robots cache, query or update the visited set, enforce depth, and enqueue crawl
jobs. It does not download or parse web pages.

Crawl Queue job contract:

```json
{
  "job_id": "uuid",
  "crawl_id": "uuid",
  "url": "https://example.com/page",
  "depth": 2,
  "discovered_from": "https://example.com/index",
  "discovered_at": "2026-07-29T12:00:00Z"
}
```

When a worker reports a redirect, the coordinator treats the reported final URL
like any newly discovered URL. It applies allowed-domain checks, canonical URL
deduplication, and crawl-depth rules before deciding whether to schedule it.

---

# Workers

Workers are stateless.

Responsibilities:

- fetch page
- parse a successfully fetched final page with BeautifulSoup4
- extract links
- publish discovered URLs and redirect targets to the Discovery Queue
- publish parsed document data to the Storage Queue

Workers never modify crawl state.

Workers must follow redirects with `httpx` and record the requested URL, final
URL, redirect chain, status code, and content type. They parse only a
successfully fetched final page. Redirect scheduling decisions remain with the
coordinator. Workers publish links and redirect targets to the Discovery Queue;
they publish extracted document data to the Storage Queue.

Worker result contract:

```json
{
  "job_id": "...",
  "crawl_id": "...",
  "requested_url": "...",
  "final_url": "...",
  "status_code": 200,
  "redirect_chain": ["..."],
  "content_type": "text/html",
  "depth": 2,
  "document": {"...": "..."},
  "links": ["..."],
  "fetched_at": "...",
  "processing_time_ms": 213
}
```

The crawler core produces one WorkerResult. A publisher derives the two queue
messages from it: the Storage Queue receives persistence data only, while the
Discovery Queue receives `job_id`, `crawl_id`, `requested_url`, `final_url`,
`parent_depth`, and `links`. The coordinator schedules the final URL at the
parent depth and resolves links relative to that final URL at the next depth.

---

# Storage

Metadata:

Amazon RDS

Raw HTML / Documents:

Amazon S3

Storage should eventually be isolated behind a Storage interface.

The Storage Worker consumes the Storage Queue. It writes JSONL documents to S3
and stores metadata, including the resulting S3 key, in RDS.

---

# Architecture

Version 1 architecture:

```text
                 Crawl Queue
                      │
                      ▼
               Lambda Worker
          fetch + parse + process
               │             │
               ▼             ▼
        Storage Queue   Discovery Queue
               │             │
               ▼             ▼
        Storage Worker   Coordinator
         │                 │
         ├── S3            ├── Robots Cache
         ├── RDS           ├── Visited Set
         └── Done          ├── Depth Checks
                            └── Crawl Queue
```

Do not introduce Celery, Kafka, Redis, RabbitMQ, or other queue systems.

AWS-native architecture is intentional.

---

# Coding Guidelines

Prefer:

Small pure functions.

Avoid:

Large classes with many responsibilities.

Use descriptive names.

Prefer explicit code over clever code.

Avoid unnecessary inheritance.

Use pathlib instead of os.path.

Use urllib.parse for URL manipulation.

Use dataclasses or Pydantic models where appropriate.

Raise custom exceptions instead of generic Exception.

Every public function should have:

- docstring
- type hints
- unit tests

---

# Testing Philosophy

Every module should be independently testable.

Unit tests should be preferred over integration tests during early development.

Target:

High coverage for:

- configuration
- URL utilities
- parsing
- coordinator logic

---

# Important Constraints

Do not introduce additional frameworks unless requested.

Do not over-engineer.

Do not redesign the architecture.

Implement exactly what is requested.

When unsure, prefer the simplest implementation that satisfies the requirements.

Maintain clean, readable, production-quality Python code.
