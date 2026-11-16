import unittest

from research.normalize import normalize_html


class NormalizeHTMLTests(unittest.TestCase):
    def test_extracts_title_text_and_absolute_links(self):
        html = """<!doctype html><html><head><title>Research page</title>
        <script>secret()</script></head><body><header>Navigation</header>
        <main><p>Observed fact</p><a href="/source">Source</a></main>
        <footer>Footer noise</footer></body></html>"""
        record = normalize_html(html, "https://example.org/page")
        self.assertEqual(record["title"], "Research page")
        self.assertIn("Observed fact", record["text"])
        self.assertNotIn("secret", record["text"])
        self.assertNotIn("Navigation", record["text"])
        self.assertNotIn("Footer noise", record["text"])
        self.assertEqual(record["links"], ["https://example.org/source"])
        self.assertEqual(len(record["content_sha256"]), 64)

    def test_rejects_non_http_urls_and_embedded_credentials(self):
        with self.assertRaises(ValueError):
            normalize_html("<p>x</p>", "file:///etc/passwd")
        with self.assertRaises(ValueError):
            normalize_html("<p>x</p>", "https://user:pass@example.org/")

    def test_rejects_oversized_html(self):
        with self.assertRaises(ValueError):
            normalize_html("x" * 2_000_001, "https://example.org/")

    def test_deduplicates_links_and_keeps_provenance(self):
        record = normalize_html(
            '<a href="/a">A</a><a href="/a">again</a>',
            "https://example.org/root",
            "2026-01-01T00:00:00Z",
        )
        self.assertEqual(record["links"], ["https://example.org/a"])
        self.assertEqual(record["retrieved_at"], "2026-01-01T00:00:00Z")
        self.assertEqual(record["source_url"], "https://example.org/root")


if __name__ == "__main__":
    unittest.main()
