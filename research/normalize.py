"""Normalize saved HTML into provenance-preserving research records.

This module intentionally performs no network requests or crawling. Feed it HTML
obtained through an approved source adapter (or a user-supplied saved page).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

MAX_HTML_CHARS = 2_000_000
MAX_LINKS = 100
_BLOCKED_TAGS = {"script", "style", "noscript", "svg", "canvas", "iframe", "template"}
_IGNORED_TEXT_TAGS = {"nav", "footer", "header", "form", "button"}


def _validate_source_url(source_url: str) -> str:
    parts = urlsplit(source_url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("source_url must be an absolute HTTP(S) URL")
    if parts.username or parts.password:
        raise ValueError("source_url must not contain embedded credentials")
    return source_url


class _ResearchHTMLParser(HTMLParser):
    def __init__(self, source_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.source_url = source_url
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[str] = []
        self._title_depth = 0
        self._skip_depth = 0
        self._ignored_depth = 0
        self._ignored_stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = dict(attrs)
        if tag in _BLOCKED_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._title_depth += 1
        if tag in _IGNORED_TEXT_TAGS:
            self._ignored_depth += 1
            self._ignored_stack.append(tag)
        if tag == "a" and len(self.links) < MAX_LINKS:
            href = attrs_map.get("href")
            if href:
                candidate = urljoin(self.source_url, href)
                parts = urlsplit(candidate)
                if parts.scheme in {"http", "https"} and parts.hostname:
                    self.links.append(candidate)

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOCKED_TAGS and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag == "title" and self._title_depth:
            self._title_depth -= 1
        if tag in self._ignored_stack:
            self._ignored_stack.remove(tag)
            self._ignored_depth = max(0, self._ignored_depth - 1)

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if not value or self._skip_depth:
            return
        if self._title_depth:
            self.title_parts.append(value)
        elif not self._ignored_depth:
            self.text_parts.append(value)


def normalize_html(html: str, source_url: str, retrieved_at: str | None = None) -> dict[str, Any]:
    """Return a stable, source-attributed record from HTML text."""
    source_url = _validate_source_url(source_url)
    if not isinstance(html, str):
        raise TypeError("html must be a string")
    if len(html) > MAX_HTML_CHARS:
        raise ValueError(f"HTML exceeds the {MAX_HTML_CHARS}-character limit")

    parser = _ResearchHTMLParser(source_url)
    parser.feed(html)
    parser.close()

    title = " ".join(" ".join(parser.title_parts).split())
    text = " ".join(" ".join(parser.text_parts).split())
    links = list(dict.fromkeys(parser.links))
    digest = hashlib.sha256((title + "\n" + text).encode("utf-8")).hexdigest()
    timestamp = retrieved_at or datetime.now(timezone.utc).isoformat()

    return {
        "source_url": source_url,
        "retrieved_at": timestamp,
        "title": title,
        "content_type": "text/html",
        "text": text,
        "links": links,
        "extractor": "research.normalize_html/1",
        "content_sha256": digest,
    }


def normalize_file(path: str, source_url: str, retrieved_at: str | None = None) -> dict[str, Any]:
    """Normalize a locally saved HTML file; never accesses the network."""
    html = Path(path).read_text(encoding="utf-8")
    return normalize_html(html, source_url, retrieved_at)


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("html_file", help="Path to a locally saved HTML file")
    cli.add_argument("--source-url", required=True, help="Original HTTP(S) page URL")
    cli.add_argument("--output", help="Optional JSON output path")
    args = cli.parse_args()
    record = normalize_file(args.html_file, args.source_url)
    rendered = json.dumps(record, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
