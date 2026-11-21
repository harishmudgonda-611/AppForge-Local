import unittest

import server


class AppForgeIntroTests(unittest.TestCase):
    def test_intro_assets_injected_into_generated_app(self):
        files = {
            "index.html": "<!doctype html><html><head></head><body><main>App</main></body></html>",
            "app.js": "console.log('app');",
            "styles.css": "body{}",
            "manifest.webmanifest": '{"name":"Demo"}',
            "sw.js": "const CACHE='demo-v1'; self.addEventListener('install',e=>e.waitUntil(caches.open(CACHE)));",
            "README.md": "# Demo",
        }
        result = server.inject_appforge_intro(files)
        self.assertIn("appforge-intro.css", result["index.html"])
        self.assertIn("appforge-intro.js", result["index.html"])
        self.assertIn("intro.mp4", result["appforge-intro.js"])
        self.assertIn("Skip intro", result["appforge-intro.js"])
        self.assertIn("appforge-intro.css", result["sw.js"])
        self.assertIn("appforge-intro.js", result["sw.js"])
        self.assertIn("intro.mp4", result["README.md"])
        validated, error = server.validate_generated_files(result)
        self.assertIsNone(error)
        self.assertIsNotNone(validated)


if __name__ == "__main__":
    unittest.main()
