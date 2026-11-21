import unittest

import server


class AveroIntroTests(unittest.TestCase):
    def sample_files(self):
        return {
            "index.html": "<!doctype html><html><head><title>Demo App</title></head><body><main>App</main></body></html>",
            "app.js": "console.log('app');",
            "styles.css": "body{}",
            "manifest.webmanifest": '{"name":"Demo App","icons":[{"src":"icon.png"}]}',
            "sw.js": "const CACHE='demo-v1'; self.addEventListener('install',e=>e.waitUntil(caches.open(CACHE)));",
            "README.md": "# Demo",
        }

    def test_intro_assets_injected_and_validated(self):
        result = server.inject_appforge_intro(self.sample_files())
        self.assertIn("avero-intro.css", result["index.html"])
        self.assertIn("avero-intro.js", result["index.html"])
        self.assertIn("intro.mp4", result["avero-intro.js"])
        self.assertIn("Skip intro", result["avero-intro.js"])
        self.assertIn("manifest.webmanifest", result["avero-intro.js"])
        self.assertIn("avero-intro.css", result["sw.js"])
        self.assertIn("avero-intro.js", result["sw.js"])
        self.assertIn("intro.mp4", result["README.md"])
        self.assertNotIn("AppForge", result["avero-intro.js"])
        self.assertNotIn("AVERO", result["avero-intro.js"])
        validated, error = server.validate_generated_files(result)
        self.assertIsNone(error)
        self.assertIsNotNone(validated)

    def test_injection_is_idempotent(self):
        files = self.sample_files()
        first = server.inject_appforge_intro(files)
        second = server.inject_appforge_intro(first)
        self.assertEqual(first["index.html"], second["index.html"])
        self.assertEqual(first["avero-intro.js"], second["avero-intro.js"])
        self.assertEqual(first["avero-intro.css"], second["avero-intro.css"])

    def test_intro_inserts_before_closing_tags(self):
        result = server.inject_appforge_intro(self.sample_files())
        self.assertLess(result["index.html"].index("avero-intro.css"), result["index.html"].index("</head>"))
        self.assertLess(result["index.html"].index("avero-intro.js"), result["index.html"].index("</body>"))


if __name__ == "__main__":
    unittest.main()
