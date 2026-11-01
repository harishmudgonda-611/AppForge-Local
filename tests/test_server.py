"""HTTP smoke tests for the local AppForge server."""
import json
from io import BytesIO
from email.message import Message
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import server
import shutil


class AppForgeHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.httpd.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=3)

    def get_json(self, path):
        with urllib.request.urlopen(self.base_url + path, timeout=3) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def post_json(self, path, payload, extra_headers=None):
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", **(extra_headers or {})},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def test_local_model_json_response_is_size_limited(self):
        from io import BytesIO
        self.assertEqual(server.read_limited_json(BytesIO(b'{"ok":true}'), 32), {"ok": True})
        with self.assertRaisesRegex(ValueError, "response exceeds"):
            server.read_limited_json(BytesIO(b'{"payload":"' + b'x' * 40 + b'"}'), 32)

    def test_request_body_rejects_negative_content_length(self):
        handler = object.__new__(server.Handler)
        handler.headers = Message()
        handler.headers["Content-Length"] = "-1"
        handler.rfile = BytesIO(b"")
        with self.assertRaisesRegex(ValueError, "Invalid Content-Length"):
            handler.body()

    def test_request_body_requires_json_object(self):
        handler = object.__new__(server.Handler)
        handler.headers = Message()
        handler.headers["Content-Length"] = "2"
        handler.rfile = BytesIO(b"[]")
        with self.assertRaisesRegex(ValueError, "JSON object"):
            handler.body()

    def test_request_body_rejects_oversized_content_length(self):
        handler = object.__new__(server.Handler)
        handler.headers = Message()
        handler.headers["Content-Length"] = "2000001"
        handler.rfile = BytesIO(b"")
        with self.assertRaisesRegex(ValueError, "too large"):
            handler.body()

    def test_aider_and_repair_require_boolean_approval(self):
        for path, payload in (
            ("/api/aider/run", {"project": "Demo", "prompt": "Make a focused change", "approved": "false"}),
            ("/api/test-repair", {"project": "Demo", "approved": 1}),
        ):
            status, data = self.post_json(path, payload)
            self.assertEqual(status, 403)
            self.assertTrue(data["requires_approval"])

    def test_apk_build_requires_explicit_approval_before_running_tools(self):
        import tempfile
        from pathlib import Path
        original = server.WORKSPACE
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "Demo").mkdir()
            server.WORKSPACE = workspace
            try:
                status, data = self.post_json(
                    "/api/build",
                    {"project": "Demo", "command": "apk"},
                )
                self.assertEqual(status, 403)
                self.assertTrue(data["requires_approval"])
                self.assertIn("explicit approval", data["error"])
            finally:
                server.WORKSPACE = original

    def test_apk_build_does_not_accept_truthy_non_boolean_approval(self):
        import tempfile
        from pathlib import Path
        original = server.WORKSPACE
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "Demo").mkdir()
            server.WORKSPACE = workspace
            try:
                status, data = self.post_json(
                    "/api/build",
                    {"project": "Demo", "command": "apk", "approved": "yes"},
                )
                self.assertEqual(status, 403)
                self.assertTrue(data["requires_approval"])
            finally:
                server.WORKSPACE = original

    def test_apk_build_rejects_symlinked_npm_paths_before_execution(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        original = server.WORKSPACE
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "Demo"
            project.mkdir()
            (project / "package.json").write_text('{"scripts":{"build":"echo unsafe"}}')
            outside = root / "outside-lock.json"
            outside.write_text("{}")
            (project / "package-lock.json").symlink_to(outside)
            server.WORKSPACE = root
            try:
                with patch.object(server.subprocess, "run") as runner:
                    status, data = self.post_json("/api/build", {"project": "Demo", "command": "apk", "approved": True})
                self.assertEqual(status, 400)
                self.assertIn("package-lock.json", data["error"])
                runner.assert_not_called()
            finally:
                server.WORKSPACE = original

    def test_apk_build_rejects_symlinked_node_modules_before_execution(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        original = server.WORKSPACE
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "Demo"
            project.mkdir()
            (project / "package.json").write_text('{"scripts":{"build":"echo unsafe"}}')
            outside = root / "outside-modules"
            outside.mkdir()
            (project / "node_modules").symlink_to(outside, target_is_directory=True)
            server.WORKSPACE = root
            try:
                with patch.object(server.subprocess, "run") as runner:
                    status, data = self.post_json("/api/build", {"project": "Demo", "command": "apk", "approved": True})
                self.assertEqual(status, 400)
                self.assertIn("node_modules", data["error"])
                runner.assert_not_called()
            finally:
                server.WORKSPACE = original

    def test_approved_apk_build_installs_dependencies_and_adds_android_platform(self):
        import tempfile
        import subprocess
        from pathlib import Path
        from unittest.mock import patch
        original = server.WORKSPACE
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            project = workspace / "Demo"
            project.mkdir()
            (project / "package.json").write_text('{"scripts":{"build":"node build.js"}}')
            server.WORKSPACE = workspace
            commands = []
            def fake_run(command, cwd=None, **kwargs):
                commands.append(command)
                if command[:4] == ["npx", "--no-install", "cap", "add"]:
                    android = project / "android"
                    android.mkdir()
                    wrapper = android / "gradlew"
                    wrapper.write_text("#!/bin/sh\\nexit 0\\n")
                    wrapper.chmod(0o755)
                if command[:1] == ["./gradlew"]:
                    apk = project / "android/app/build/outputs/apk/debug/app-debug.apk"
                    apk.parent.mkdir(parents=True)
                    apk.write_bytes(b"verified-apk")
                return subprocess.CompletedProcess(command, 0, "ok", "")
            try:
                with patch.object(server.subprocess, "run", side_effect=fake_run):
                    status, data = self.post_json("/api/build", {"project": "Demo", "command": "apk", "approved": True})
                self.assertEqual(status, 200, data)
                self.assertTrue(data["artifact_verified"])
                self.assertEqual(commands[0][:2], ["npm", "install"])
                self.assertEqual(commands[1], ["npm", "test", "--if-present"])
                self.assertEqual(commands[2][:3], ["npm", "run", "build"])
                self.assertIn(["npx", "--no-install", "cap", "add", "android"], commands)
                self.assertIn(["npx", "--no-install", "cap", "sync", "android"], commands)
                self.assertTrue((project / "android/app/build/outputs/apk/debug/app-debug.apk").is_file())
            finally:
                server.WORKSPACE = original

    def test_post_rejects_cross_origin_browser_request(self):
        status, data = self.post_json(
            "/api/feedback",
            {"feedback": "should not be stored"},
            {"Origin": "http://attacker.example"},
        )
        self.assertEqual(status, 403)
        self.assertIn("same-origin", data["error"])

    def test_post_rejects_non_loopback_host_header(self):
        status, data = self.post_json(
            "/api/feedback",
            {"feedback": "should not be stored"},
            {"Host": "attacker.example"},
        )
        self.assertEqual(status, 403)

    def test_post_accepts_matching_local_origin(self):
        origin = self.base_url
        status, data = self.post_json(
            "/api/feedback",
            {"feedback": "local origin test"},
            {"Origin": origin},
        )
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])

    def test_browser_script_selectors_match_real_html_elements(self):
        import re
        html = (server.STATIC / "index.html").read_text(encoding="utf-8")
        script = (server.STATIC / "app.js").read_text(encoding="utf-8")
        element_ids = set(re.findall(r'id="([^"]+)"', html))
        selectors = set(re.findall(r"\$\('#([^']+)'\)", script))
        self.assertTrue(selectors)
        self.assertEqual(selectors - element_ids, set())

    def test_service_worker_precache_assets_exist(self):
        import re
        worker = (server.STATIC / "sw.js").read_text(encoding="utf-8")
        match = re.search(r"const FILES=\[(.*?)\]", worker)
        self.assertIsNotNone(match, "Service worker cache list must be discoverable")
        paths = re.findall(r"'([^']+)'", match.group(1))
        self.assertTrue(paths)
        for path in paths:
            if path == "/":
                continue
            self.assertTrue((server.STATIC / path.lstrip("/")).is_file(), path)

    def test_home_page_is_served(self):
        with urllib.request.urlopen(self.base_url + "/", timeout=3) as response:
            body = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn("AppForge", body)

    def test_get_rejects_non_loopback_host_header(self):
        request = urllib.request.Request(self.base_url + "/api/health", headers={"Host": "attacker.example"})
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, timeout=3)
        self.assertEqual(error.exception.code, 403)

    def test_get_accepts_loopback_host_header(self):
        request = urllib.request.Request(self.base_url + "/api/health", headers={"Host": "127.0.0.1"})
        with urllib.request.urlopen(request, timeout=3) as response:
            self.assertEqual(response.status, 200)

    def test_research_api_returns_400_for_invalid_storefront_region(self):
        try:
            urllib.request.urlopen(self.base_url + "/api/research/search?term=calculator&region=../../", timeout=3)
        except urllib.error.HTTPError as error:
            self.assertEqual(error.code, 400)
            data = json.loads(error.read().decode("utf-8"))
            self.assertIn("two-letter", data["error"])
        else:
            self.fail("Invalid storefront region should return HTTP 400")

    def test_health_endpoint(self):
        status, data = self.get_json("/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertIn("llm_base_url", data)

    def test_replica_workflow_catalog_has_eleven_stages(self):
        status, data = self.get_json("/api/replica/workflows")
        self.assertEqual(status, 200)
        self.assertEqual(len(data["stages"]), 11)

    def test_safe_path_rejects_symlink_escape(self):
        import tempfile
        from pathlib import Path
        original = server.WORKSPACE
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            project = workspace / "Demo"
            outside = root / "private.txt"
            project.mkdir(parents=True)
            outside.write_text("private")
            (project / "leak.txt").symlink_to(outside)
            server.WORKSPACE = workspace
            try:
                self.assertIsNone(server.Handler.safe_path(None, "Demo", "leak.txt"))
                self.assertEqual(server.Handler.safe_path(None, "Demo", "index.html"), project / "index.html")
            finally:
                server.WORKSPACE = original

    def test_generated_files_require_nonempty_html_entrypoint(self):
        for files in ({}, {"app.js": "console.log('missing html')"}, {"index.html": ""}):
            normalized, error = server.validate_generated_files(files)
            self.assertIsNone(normalized)
            self.assertTrue(error)

    def test_generated_files_reject_unsafe_and_windows_paths(self):
        for path in ("../outside.txt", "assets\\\\secret.txt", "C:/outside.txt", "assets/<bad>.txt"):
            normalized, error = server.validate_generated_files({"index.html": "<html></html>", "app.js": "ok", "styles.css": "body{}", "manifest.webmanifest": '{"name":"Demo"}', "sw.js": "ok", path: "x"})
            self.assertIsNone(normalized, path)
            self.assertTrue(error, path)

    def test_generated_files_enforce_count_and_size_limits(self):
        too_many = {"index.html": "ok", "app.js": "ok", "styles.css": "body{}", "manifest.webmanifest": '{"name":"Demo"}', "sw.js": "ok"}
        too_many.update({f"asset-{i}.txt": "x" for i in range(80)})
        self.assertIsNotNone(server.validate_generated_files(too_many)[1])
        too_large = {"index.html": "<html></html>", "app.js": "ok", "styles.css": "body{}", "manifest.webmanifest": '{"name":"Demo"}', "sw.js": "ok", "large.txt": "x" * 512_001}
        self.assertIsNotNone(server.validate_generated_files(too_large)[1])

    def test_generated_files_reject_invalid_manifest_json(self):
        files = {"index.html": "<html></html>", "app.js": "console.log('ok')", "styles.css": "body{}", "manifest.webmanifest": "{bad", "sw.js": "self.addEventListener('install',()=>{});"}
        normalized, error = server.validate_generated_files(files)
        self.assertIsNone(normalized)
        self.assertIn("manifest.webmanifest", error)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for generated JS syntax validation")
    def test_generated_files_reject_invalid_javascript(self):
        files = {"index.html": "<html></html>", "app.js": "function {", "styles.css": "body{}", "manifest.webmanifest": '{"name":"Demo"}', "sw.js": "self.addEventListener('install',()=>{});"}
        normalized, error = server.validate_generated_files(files)
        self.assertIsNone(normalized)
        self.assertIn("JavaScript syntax validation", error)

    def test_generated_files_reject_invalid_service_worker_javascript(self):
        files = {
            "index.html": "<html></html>",
            "app.js": "console.log('ok')",
            "styles.css": "body{}",
            "manifest.webmanifest": '{"name":"Demo"}',
            "sw.js": "function {"
        }
        normalized, error = server.validate_generated_files(files)
        if server.shutil.which("node"):
            self.assertIsNone(normalized)
            self.assertIn("sw.js", error)

    def test_generated_files_accept_safe_nested_assets(self):
        files = {"index.html": "<!doctype html><html></html>", "app.js": "console.log('ok')", "styles.css": "body{}", "manifest.webmanifest": '{"name":"Demo"}', "sw.js": "self.addEventListener('install',()=>{});", "assets/icon.svg": "<svg></svg>"}
        normalized, error = server.validate_generated_files(files)
        self.assertIsNone(error)
        self.assertEqual(normalized, files)

    def test_safe_path_rejects_project_root_symlink_even_inside_workspace(self):
        import tempfile
        from pathlib import Path
        original = server.WORKSPACE
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            target = workspace / "RealProject"
            target.mkdir(parents=True)
            (target / "index.html").write_text("private")
            (workspace / "AliasProject").symlink_to(target, target_is_directory=True)
            server.WORKSPACE = workspace
            try:
                self.assertIsNone(server.Handler.safe_path(None, "AliasProject"))
                self.assertEqual(server.Handler.safe_path(None, "RealProject"), target)
            finally:
                server.WORKSPACE = original

    def test_api_rejects_non_text_prompt_and_slug_values(self):
        status, data = self.post_json("/api/analyze", {"prompt": 123})
        self.assertEqual(status, 400)
        self.assertIn("text", data["error"])
        status, data = self.post_json("/api/generate", {"slug": 123, "brief": "A sufficiently long app brief for validation."})
        self.assertEqual(status, 400)
        self.assertIn("text", data["error"])
        status, data = self.post_json("/api/generate", {"slug": "SafeSlug", "brief": None})
        self.assertEqual(status, 400)

    def test_safe_path_rejects_non_string_inputs(self):
        self.assertIsNone(server.Handler.safe_path(None, 123))
        self.assertIsNone(server.Handler.safe_path(None, "Demo", 123))

    def test_apk_download_serves_only_verified_project_artifact(self):
        import tempfile
        from pathlib import Path
        original = server.WORKSPACE
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            apk = workspace / "Demo/android/app/build/outputs/apk/debug/app-debug.apk"
            apk.parent.mkdir(parents=True)
            apk.write_bytes(b"test-apk-bytes")
            server.WORKSPACE = workspace
            try:
                with urllib.request.urlopen(self.base_url + "/api/apk?project=Demo", timeout=3) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.headers.get("Content-Type"), "application/vnd.android.package-archive")
                    self.assertEqual(response.read(), b"test-apk-bytes")
                apk.unlink()
                status, data = self.get_json("/api/health")
                self.assertEqual(status, 200)
                with self.assertRaises(urllib.error.HTTPError) as missing:
                    urllib.request.urlopen(self.base_url + "/api/apk?project=Demo", timeout=3)
                self.assertEqual(missing.exception.code, 404)
            finally:
                server.WORKSPACE = original

    def test_apk_download_rejects_symlinked_artifact(self):
        import tempfile
        from pathlib import Path
        original = server.WORKSPACE
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "Demo"
            artifact_dir = project / "android/app/build/outputs/apk/debug"
            artifact_dir.mkdir(parents=True)
            outside = root / "outside.apk"
            outside.write_bytes(b"private")
            (artifact_dir / "app-debug.apk").symlink_to(outside)
            server.WORKSPACE = root
            try:
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(self.base_url + "/api/apk?project=Demo", timeout=3)
                self.assertEqual(error.exception.code, 404)
                self.assertEqual(outside.read_bytes(), b"private")
            finally:
                server.WORKSPACE = original

    def test_generate_endpoint_rejects_symlinked_project_slug(self):
        import tempfile
        from pathlib import Path
        original = server.WORKSPACE
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            target = workspace / "outside"
            target.mkdir()
            (target / "keep.txt").write_text("untouched")
            (workspace / "Alias").symlink_to(target, target_is_directory=True)
            server.WORKSPACE = workspace
            try:
                status, data = self.post_json("/api/generate", {
                    "slug": "Alias",
                    "brief": "Build a useful offline-first application for testing."
                })
                self.assertEqual(status, 409)
                self.assertEqual((target / "keep.txt").read_text(), "untouched")
            finally:
                server.WORKSPACE = original

    def test_generate_endpoint_uses_unique_name_without_overwriting_existing_project(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        original = server.WORKSPACE
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            existing = workspace / "AlreadyThere"
            existing.mkdir()
            (existing / "keep.txt").write_text("preserve")
            server.WORKSPACE = workspace
            generated = {"files": {"index.html": "<html>new</html>", "app.js": "console.log('new')", "styles.css": "body{}", "manifest.webmanifest": '{"name":"New Demo"}', "sw.js": "self.addEventListener('install',()=>{});"}}
            def fake_llm(self, system, user, raw=False):
                return {"ok": True, "data": generated, "text": "{}"}
            try:
                with patch.object(server.Handler, "call_llm", fake_llm):
                    status, data = self.post_json("/api/generate", {
                        "slug": "AlreadyThere",
                        "brief": "Build a useful offline-first application for testing."
                    })
                self.assertEqual(status, 200, data)
                self.assertNotEqual(data["project"], "AlreadyThere")
                self.assertEqual((existing / "keep.txt").read_text(), "preserve")
                self.assertTrue((workspace / data["project"] / "index.html").is_file())
            finally:
                server.WORKSPACE = original

    def test_generate_endpoint_writes_only_validated_pwa_files(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        original = server.WORKSPACE
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            server.WORKSPACE = workspace
            generated = {
                "app_name": "Validated Demo",
                "description": "Test app",
                "files": {
                    "index.html": "<!doctype html><html><body>Demo</body></html>",
                    "app.js": "console.log('demo');",
                    "styles.css": "body { margin: 0; }",
                    "manifest.webmanifest": '{"name":"Validated Demo"}',
                    "sw.js": "self.addEventListener('install',()=>{});",
                    "assets/icon.svg": "<svg></svg>"
                }
            }
            def fake_llm(self, system, user, raw=False):
                assert raw is True
                return {"ok": True, "data": generated, "text": "{}"}
            try:
                with patch.object(server.Handler, "call_llm", fake_llm):
                    status, data = self.post_json("/api/generate", {
                        "slug": "ValidatedDemo",
                        "brief": "Build a useful offline-first demo application for testing."
                    })
                self.assertEqual(status, 200, data)
                self.assertTrue((workspace / "ValidatedDemo/index.html").is_file())
                self.assertTrue((workspace / "ValidatedDemo/assets/icon.svg").is_file())
                manifest = json.loads((workspace / "ValidatedDemo/appforge-project.json").read_text())
                self.assertEqual(manifest["files"], data["files"])
            finally:
                server.WORKSPACE = original

    def test_generate_endpoint_rejects_incomplete_model_output_without_project(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        original = server.WORKSPACE
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            server.WORKSPACE = workspace
            def fake_llm(self, system, user, raw=False):
                return {"ok": True, "data": {"files": {"app.js": "console.log('missing html')"}}, "text": "{}"}
            try:
                with patch.object(server.Handler, "call_llm", fake_llm):
                    status, data = self.post_json("/api/generate", {
                        "slug": "InvalidDemo",
                        "brief": "Build a useful offline-first demo application for testing."
                    })
                self.assertEqual(status, 422)
                self.assertIn("index.html", data["error"])
                self.assertFalse((workspace / "InvalidDemo").exists())
            finally:
                server.WORKSPACE = original

    def test_settings_reject_remote_model_endpoint(self):
        status, data = self.post_json(
            "/api/config",
            {"llm_base_url": "https://example.com/v1"},
        )
        self.assertEqual(status, 400)
        self.assertIn("localhost or private-LAN", data["error"])

    def test_local_endpoint_rejects_embedded_credentials_and_query(self):
        self.assertFalse(server.local_endpoint_allowed("http://user:pass@127.0.0.1:8080/v1"))
        self.assertFalse(server.local_endpoint_allowed("http://127.0.0.1:8080/v1?token=secret"))
        self.assertFalse(server.local_endpoint_allowed("http://127.0.0.1:8080/v1#fragment"))

    def test_config_rejects_invalid_timeout_types_and_bounds(self):
        current=dict(server.DEFAULT_CONFIG)
        for value in (True, "120", 4, 601, 1.5):
            cfg,error=server.validate_config_update(current, {"timeout_seconds": value})
            self.assertIsNone(cfg)
            self.assertIn("between 5 and 600", error)

    def test_config_rejects_empty_or_oversized_model_name(self):
        current=dict(server.DEFAULT_CONFIG)
        for value in (" ", "m" * 201, 123):
            cfg,error=server.validate_config_update(current, {"llm_model": value})
            self.assertIsNone(cfg)
            self.assertIn("Model name", error)

    def test_config_rejects_non_text_or_oversized_api_key(self):
        current=dict(server.DEFAULT_CONFIG)
        for value in (None, 123, "k" * 1001):
            cfg,error=server.validate_config_update(current, {"llm_api_key": value})
            self.assertIsNone(cfg)
            self.assertIn("API key", error)

    def test_config_accepts_valid_local_settings_and_normalizes_url(self):
        current=dict(server.DEFAULT_CONFIG)
        cfg,error=server.validate_config_update(current, {
            "llm_base_url": "http://127.0.0.1:8080/v1/",
            "llm_model": " qwen-local ",
            "timeout_seconds": 300,
        })
        self.assertIsNone(error)
        self.assertEqual(cfg["llm_base_url"], "http://127.0.0.1:8080/v1")
        self.assertEqual(cfg["llm_model"], "qwen-local")
        self.assertEqual(cfg["timeout_seconds"], 300)

    def test_model_calls_reject_remote_endpoint_even_if_config_is_edited(self):
        original = server.CONFIG.read_text(encoding="utf-8")
        try:
            config = json.loads(original)
            config["llm_base_url"] = "https://example.com/v1"
            server.CONFIG.write_text(json.dumps(config), encoding="utf-8")
            status, data = self.post_json(
                "/api/analyze",
                {"prompt": "A test prompt long enough to pass input validation."},
            )
            self.assertEqual(status, 400)
            self.assertIn("local-first", data["error"])
        finally:
            server.CONFIG.write_text(original, encoding="utf-8")


if __name__ == "__main__":
    unittest.main(verbosity=2)
