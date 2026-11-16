# AppForge research adapters

This branch adds a deliberately optional research-adapter boundary for AppForge Local. Existing App Store snapshots, SQLite history, local model endpoint and static project checks remain authoritative and unchanged.

## Intended adapter map
- **Scrapy**: optional, owner-configured crawl jobs for permitted public catalog/documentation sites; not a default dependency.
- **Crawl4AI**: optional HTML-to-Markdown adapter for pages the operator is permitted to access.
- **MarkItDown**: optional conversion of operator-supplied PDFs, Office documents and HTML exports into research text.
- **AutoScraper / Scrapling**: optional extraction experiments against saved fixtures; never use to evade authentication, CAPTCHAs, rate limits or access controls.
- **Browser Use / Skyvern**: explicitly out of process and disabled by default; no unattended login or purchase flows.

## Integration contract
Adapters must return normalized records containing source URL, retrieval timestamp, content type, title, extracted text, extraction method and a content hash. Preserve the original URL and distinguish observed facts from model-generated summaries. Store crawl policy and source allowlists locally. Respect robots.txt, site terms, rate limits and copyright. Do not infer app downloads/revenue from rankings or reviews.

## Runtime policy
No new runtime dependencies are installed by this documentation change. Keep the standard-library baseline. Each adapter is opt-in and must have fixture-based tests before it can be wired into the server. Local-only mode remains the default; no paid API, public endpoint or remote model is required.

## Validation still required
Wire an adapter into the existing research UI/API only after a follow-up implementation adds unit tests for parsing, deduplication, source provenance, blocked hosts and failure handling. Existing AppForge test commands remain the regression gate.