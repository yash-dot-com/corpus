# Corpora

Corpora is a cloud-native, production-inspired distributed web corpus
generation platform. It generates high-quality web corpora—HTML, cleaned text,
metadata, and JSONL documents—for downstream applications such as LLM training,
RAG pipelines, search indexing, analytics, and dataset generation.

## Implementation checklist

This checklist is the strict implementation order for Version 1. We implement
and review one item at a time. Every implementation item must include focused
unit tests before moving to the next item.

- [x] Establish the development baseline: inspect existing code, preserve public
      behavior, define Python 3.13 tooling, test layout, and a test command that
      works in the workspace.
- [x] Define and test the CLI contract: thin Typer entry point, configuration
      path argument behavior, exit codes, and no business logic.
- [x] Implement typed configuration models and custom configuration errors; add
      exhaustive validation tests for every supported field and invalid input.
- [x] Replace the YAML loader with a deterministic `Path`-based loader that
      parses YAML into configuration models; test missing, unreadable, empty,
      malformed, and invalid configuration files.
- [x] Finalize URL exception types and implement `validate()`, `normalize()`,
      `canonicalize()`, and `resolve()` to the declared contract; test normal,
      malformed, edge-case, and idempotency behavior.
- [ ] Define and test the coordinator's crawl-job contract before implementation:
      run on EC2; own in-memory crawl state and per-host robots.txt cache;
      validate/normalize/canonicalize URLs; allow configured domains and their
      subdomains; enforce depth and robots rules; deduplicate by canonical URL;
      and enqueue only verified JSON jobs (`url`, `depth`, `parent_url`) to
      Amazon SQS in batches.
- [ ] Define fetch result and error models and implement a stateless HTTP
      fetcher with explicit timeouts, user agent, and predictable failures;
      unit-test request construction and response handling with mocked transport.
- [ ] Implement stateless HTML parsing and link extraction, with document and
      text metadata models; test representative HTML, malformed markup, link
      forms, and extraction boundaries.
- [ ] Define a minimal storage interface and local test implementation for raw
      HTML, parsed documents, and metadata; test serialization, paths, and error
      behavior.
- [ ] Add AWS-facing adapters for the approved Version 1 architecture (SQS, S3,
      and RDS) behind the existing interfaces, without changing core logic;
      test adapters with mocked AWS clients.
- [ ] Implement stateless worker handlers and message contracts: fetch, parse,
      return discoveries to the coordinator or output queue, and persist results;
      test each handler end-to-end with fakes.
- [ ] Wire the CLI composition root for the approved local and AWS execution
      paths; add a small, deterministic end-to-end test using fakes only.
- [ ] Add structured logging, metrics hooks, and failure visibility without
      coupling domain logic to infrastructure; test emitted events and error
      paths.
- [ ] Run the final quality gate: full unit suite, coverage report at the agreed
      100% threshold, Ruff, mypy, and a clean documented local workflow;
      remediate only failures found.
- [ ] Update README, configuration examples, and architecture documentation to
      match the implemented, tested system.

## Review workflow

1. Implement exactly one checklist item.
2. Run that item's focused tests and relevant quality checks.
3. Review the change before starting the next item.

## Version 1 AWS operating targets

These settings are the initial Free Tier-friendly targets. They are deployment
configuration, not coordinator business logic, and will be implemented with the
AWS integration milestone.

| Setting | Initial value |
| --- | --- |
| SQS-to-Lambda batch size | 10 jobs |
| Lambda maximum concurrency | 10, adjustable to 20 after review |
| Lambda timeout | 60 seconds |
| Lambda memory | 512 MB; adjust after benchmarking |

## Coordinator robots.txt policy

The EC2 coordinator, not the stateless Lambda workers, owns robots.txt policy
management. Before it schedules a URL, it checks the in-memory cache for that
URL's host. On a cache miss, it downloads and parses `/robots.txt` with Protego,
caches the policy, and applies it to all later URLs from the same host.

```js
Coordinator

↓

check robots

↓

allowed?

↓

enqueue

↓

Worker

↓

crawl
```