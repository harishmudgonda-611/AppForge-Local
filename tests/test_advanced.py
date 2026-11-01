import unittest, tempfile, json
from unittest.mock import patch
from pathlib import Path
import advanced

class AppForgeAdvancedTests(unittest.TestCase):
    def test_repo_catalog_has_optional_adapter(self):
        d=advanced.repo_catalog(); self.assertTrue(any(x['name']=='Aider' for x in d['repositories']))
    def test_launch_config_checklist(self):
        d=advanced.launch_config('unit-test-project'); self.assertGreaterEqual(len(d['checklist']),5)
    def test_capacitor_rejects_missing_project(self):
        with self.assertRaises(ValueError): advanced.create_capacitor('../outside')
    def test_test_runner_rejects_missing_project(self):
        with self.assertRaises(ValueError): advanced.test_project('NoSuchProject_abcdef')

    def test_replica_catalog_exposes_eleven_stages(self):
        d = advanced.replica_workflows()
        self.assertEqual(len(d['stages']), 11)
        self.assertEqual(d['upstream'], 'https://github.com/Jakeschincariol/replica-skill')
        self.assertIn('not bundled', d['integration'])

    def test_replica_requires_approval(self):
        d = advanced.replica_run({'project':'ReplicaApprovalTest','stage':'replica-recon','approved':False}, lambda *a: {'ok':True,'text':'should not run'})
        self.assertEqual(d['status'], 400)

    def test_replica_recon_saves_local_artifact(self):
        import tempfile
        old = advanced.WORKSPACE
        with tempfile.TemporaryDirectory() as t:
            advanced.WORKSPACE = Path(t)
            fake = lambda system, user, raw: {'ok':True,'text':'# Recon\nEvidence is pending.'}
            d = advanced.replica_run({'project':'ReplicaUnitTest','stage':'replica-recon','approved':True,'target_app':'Demo','context':'User supplied source URL: https://example.invalid'}, fake)
            self.assertEqual(d['status'], 200)
            self.assertTrue((Path(t)/'ReplicaUnitTest'/'replica'/'01-recon.md').is_file())
            self.assertTrue((Path(t)/'ReplicaUnitTest'/'replica'/'workflow-state.json').is_file())
            advanced.WORKSPACE = old

    def test_replica_rejects_symlinked_artifact_directory(self):
        old = advanced.WORKSPACE
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "ReplicaSymlink"
            project.mkdir()
            outside = root / "outside"
            outside.mkdir()
            (project / "replica").symlink_to(outside, target_is_directory=True)
            advanced.WORKSPACE = root
            called = []
            try:
                fake = lambda *args: called.append(True) or {"ok": True, "text": "# Should not run"}
                result = advanced.replica_run({"project": "ReplicaSymlink", "stage": "replica-architect", "approved": True}, fake)
                self.assertEqual(result["status"], 409)
                self.assertEqual(called, [])
                self.assertEqual(list(outside.iterdir()), [])
            finally:
                advanced.WORKSPACE = old

    def test_replica_build_rejects_symlinked_app_file(self):
        old = advanced.WORKSPACE
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "ReplicaFileSymlink"
            project.mkdir()
            outside = root / "outside.html"
            outside.write_text("keep me")
            (project / "index.html").symlink_to(outside)
            advanced.WORKSPACE = root
            try:
                files = {"index.html": "<html></html>", "app.js": "console.log('x')", "styles.css": "body{}"}
                fake = lambda *args: {"ok": True, "data": {"files": files}, "text": "{}"}
                result = advanced.replica_run({"project": "ReplicaFileSymlink", "stage": "replica-build", "approved": True}, fake)
                self.assertEqual(result["status"], 409)
                self.assertEqual(outside.read_text(), "keep me")
            finally:
                advanced.WORKSPACE = old

    def test_replica_build_rejects_unsafe_file_paths(self):
        import tempfile
        old = advanced.WORKSPACE
        with tempfile.TemporaryDirectory() as t:
            advanced.WORKSPACE = Path(t)
            project = Path(t)/'ReplicaBuildTest'; project.mkdir()
            fake = lambda system, user, raw: {'ok':True,'data':{'files':{'../evil.txt':'bad'}},'text':'{}'}
            d = advanced.replica_run({'project':'ReplicaBuildTest','stage':'replica-build','approved':True}, fake)
            self.assertEqual(d['status'], 400)
            self.assertFalse((Path(t)/'evil.txt').exists())
            advanced.WORKSPACE = old


    def test_replica_build_validates_and_saves_safe_files(self):
        old = advanced.WORKSPACE
        with tempfile.TemporaryDirectory() as t:
            advanced.WORKSPACE = Path(t)
            (Path(t)/'ReplicaBuildValid').mkdir()
            files = {'index.html':'<!doctype html><html><body>App</body></html>', 'app.js':'console.log("ok");', 'styles.css':'body { margin: 0; }', 'manifest.webmanifest':'{"name":"Demo"}', 'sw.js':'self.addEventListener("install",()=>{});', 'README.md':'# Demo'}
            fake = lambda system, user, raw: {'ok':True,'data':{'files':files,'summary':'Generated'},'text':'{}'}
            d = advanced.replica_run({'project':'ReplicaBuildValid','stage':'replica-build','approved':True}, fake)
            self.assertEqual(d['status'], 200)
            self.assertTrue((Path(t)/'ReplicaBuildValid'/'index.html').is_file())
            self.assertTrue((Path(t)/'ReplicaBuildValid'/'replica'/'workflow-state.json').is_file())
            advanced.WORKSPACE = old

    def test_replica_build_rejects_invalid_javascript(self):
        old = advanced.WORKSPACE
        with tempfile.TemporaryDirectory() as t:
            advanced.WORKSPACE = Path(t)
            (Path(t)/'ReplicaBadJS').mkdir()
            files = {'index.html':'<html></html>', 'app.js':'function {', 'styles.css':'body{}'}
            fake = lambda system, user, raw: {'ok':True,'data':{'files':files},'text':'{}'}
            d = advanced.replica_run({'project':'ReplicaBadJS','stage':'replica-build','approved':True}, fake)
            if advanced.shutil.which('node'):
                self.assertEqual(d['status'], 422)
                self.assertFalse((Path(t)/'ReplicaBadJS'/'app.js').exists())
            advanced.WORKSPACE = old



    def test_capacitor_rejects_symlinked_package_file(self):
        old_workspace = advanced.WORKSPACE
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); project = root / "CapSymlink"; project.mkdir()
            (project / "index.html").write_text("<html></html>")
            outside = root / "outside-package.json"; outside.write_text("keep")
            (project / "package.json").symlink_to(outside)
            advanced.WORKSPACE = root
            try:
                with self.assertRaisesRegex(ValueError, "symlinked scaffold path"):
                    advanced.create_capacitor("CapSymlink")
                self.assertEqual(outside.read_text(), "keep")
            finally:
                advanced.WORKSPACE = old_workspace

    def test_test_runner_rejects_symlinked_report_directory(self):
        old_workspace = advanced.WORKSPACE
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); project = root / "ReportSymlink"; project.mkdir()
            outside = root / "outside-reports"; outside.mkdir()
            (project / "index.html").write_text("<html></html>")
            (project / "test-reports").symlink_to(outside, target_is_directory=True)
            advanced.WORKSPACE = root
            try:
                with self.assertRaisesRegex(ValueError, "test report"):
                    advanced.test_project("ReportSymlink")
                self.assertEqual(list(outside.iterdir()), [])
            finally:
                advanced.WORKSPACE = old_workspace


    def test_git_checkpoint_blocks_sensitive_filename(self):
        old_workspace, old_state = advanced.WORKSPACE, advanced.STATE
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); project = root / "SecretProject"; project.mkdir()
            state = root / "state"; state.mkdir()
            advanced.WORKSPACE, advanced.STATE = root, state
            try:
                (project / "index.html").write_text("<html></html>")
                (project / ".env").write_text("PRIVATE_TOKEN=do-not-commit")
                result = advanced.git_action("SecretProject", "checkpoint")
                self.assertFalse(result["ok"])
                self.assertIn(".env", result["blocked_paths"][0])
                self.assertFalse((project / ".git").exists(), "Secret scan should run before Git init")
            finally:
                advanced.WORKSPACE, advanced.STATE = old_workspace, old_state

    def test_git_checkpoint_blocks_credential_like_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "notes.txt").write_text("credential = 'AKIA1234567890ABCDEF'")
            findings = advanced.checkpoint_secret_findings(project)
            self.assertTrue(findings)
            self.assertIn("possible credential content", findings[0])


    def test_git_checkpoint_scans_android_source_for_signing_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            android = project / "android" / "app"
            android.mkdir(parents=True)
            (android / "release.jks").write_bytes(b"keystore")
            (android / "google-services.json").write_text('{"api_key":"example"}')
            findings = advanced.checkpoint_secret_findings(project)
            self.assertTrue(any("release.jks" in item for item in findings))
            self.assertTrue(any("google-services.json" in item for item in findings))

    def test_git_checkpoint_detects_common_provider_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            token_a = "xoxb-" + ("A" * 24)
            token_b = "sk_live_" + ("B" * 24)
            token_c = "AIza" + ("C" * 36)
            (project / "config.txt").write_text(
                "slack=" + token_a + "\\nstripe=" + token_b + "\\ngoogle=" + token_c
            )
            findings = advanced.checkpoint_secret_findings(project)
            self.assertTrue(findings)
            self.assertIn("possible credential content", findings[0])

    def test_git_checkpoint_allows_normal_source_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "app.js").write_text("console.log('hello world')")
            (project / "README.md").write_text("# Project")
            self.assertEqual(advanced.checkpoint_secret_findings(project), [])


    def test_git_action_disables_project_hooks(self):
        old_workspace, old_state = advanced.WORKSPACE, advanced.STATE
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); project = root / "HookProject"; project.mkdir()
            state = root / "state"; state.mkdir()
            advanced.WORKSPACE, advanced.STATE = root, state
            marker = root / "hook-ran"
            try:
                (project / "README.md").write_text("initial")
                first = advanced.git_action("HookProject", "checkpoint")
                self.assertTrue(first["ok"], first)
                hooks = project / ".git" / "hooks"; hooks.mkdir(exist_ok=True)
                hook = hooks / "pre-commit"
                hook.write_text("#!/bin/sh\\nprintf ran > " + str(marker) + "\\n")
                hook.chmod(0o755)
                (project / "README.md").write_text("changed")
                second = advanced.git_action("HookProject", "checkpoint")
                self.assertTrue(second["ok"], second)
                self.assertFalse(marker.exists(), "Project-controlled pre-commit hook must not execute")
            finally:
                advanced.WORKSPACE, advanced.STATE = old_workspace, old_state

    def test_git_action_rejects_symlinked_git_metadata(self):
        old_workspace = advanced.WORKSPACE
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); project = root / "GitLinkProject"; project.mkdir()
            outside = root / "outside-git"; outside.mkdir()
            (project / ".git").symlink_to(outside, target_is_directory=True)
            advanced.WORKSPACE = root
            try:
                with self.assertRaisesRegex(ValueError, "cannot be a symlink"):
                    advanced.git_action("GitLinkProject", "status")
            finally:
                advanced.WORKSPACE = old_workspace

    def test_test_runner_does_not_execute_npm_scripts_by_default(self):
        old_workspace = advanced.WORKSPACE
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); project = root / "StaticOnly"; project.mkdir()
            marker = root / "npm-ran"
            (project / "index.html").write_text("<html></html>")
            (project / "package.json").write_text(json.dumps({"scripts":{"test":"python -c \\\"open('" + str(marker) + "','w').write('ran')\\\""}}))
            advanced.WORKSPACE = root
            try:
                with patch.object(advanced.shutil, "which", side_effect=lambda name: "/usr/bin/npm" if name == "npm" else None):
                    result = advanced.test_project("StaticOnly")
                self.assertTrue(result["ok"], result)
                self.assertFalse(marker.exists())
                self.assertNotIn("npm-test", [x["stage"] for x in result["logs"]])
            finally:
                advanced.WORKSPACE = old_workspace

    def test_repair_requires_approval(self):
        with self.assertRaises(ValueError): advanced.repair_project('NoSuchProject_abcdef',False)


    def test_local_model_endpoint_policy(self):
        self.assertTrue(advanced.local_endpoint_allowed("http://127.0.0.1:8080/v1"))
        self.assertTrue(advanced.local_endpoint_allowed("http://192.168.1.20:11434/v1"))
        self.assertFalse(advanced.local_endpoint_allowed("https://example.com/v1"))
        self.assertFalse(advanced.local_endpoint_allowed("http://8.8.8.8/v1"))
        self.assertFalse(advanced.local_endpoint_allowed("file:///etc/passwd"))


    def test_repair_refuses_remote_endpoint_before_checkpoint(self):
        old_root, old_workspace = advanced.ROOT, advanced.WORKSPACE
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir()
            project = workspace / "BrokenProject"
            project.mkdir()
            (root / "config.local.json").write_text(json.dumps({
                "llm_base_url": "https://example.com/v1",
                "llm_model": "test",
                "timeout_seconds": 1
            }))
            advanced.ROOT, advanced.WORKSPACE = root, workspace
            try:
                with patch.object(advanced, "git_action") as checkpoint:
                    result = advanced.repair_project("BrokenProject", approved=True)
                self.assertFalse(result["ok"])
                self.assertIn("Local-first policy", result["error"])
                checkpoint.assert_not_called()
            finally:
                advanced.ROOT, advanced.WORKSPACE = old_root, old_workspace

    def test_aider_refuses_remote_endpoint_before_checkpoint(self):
        old_root, old_workspace = advanced.ROOT, advanced.WORKSPACE
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / "DemoProject").mkdir()
            (root / "config.local.json").write_text(json.dumps({
                "llm_base_url": "https://example.com/v1",
                "llm_model": "test"
            }))
            advanced.ROOT, advanced.WORKSPACE = root, workspace
            try:
                with patch.object(advanced.shutil, "which", return_value="/usr/bin/aider"):
                    with patch.object(advanced, "git_action") as checkpoint:
                        result = advanced.run_aider("DemoProject", "Please improve this app safely.", approved=True)
                self.assertFalse(result["ok"])
                self.assertIn("Local-first policy", result["error"])
                checkpoint.assert_not_called()
            finally:
                advanced.ROOT, advanced.WORKSPACE = old_root, old_workspace



    def test_aider_rejects_symlinked_report_directory(self):
        old_root, old_workspace = advanced.ROOT, advanced.WORKSPACE
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir()
            project = workspace / "AiderReportLink"
            project.mkdir()
            outside = root / "outside"
            outside.mkdir()
            (project / "test-reports").symlink_to(outside, target_is_directory=True)
            (root / "config.local.json").write_text(json.dumps({
                "llm_base_url": "http://127.0.0.1:8080/v1",
                "llm_model": "test-model",
                "llm_api_key": "local"
            }))
            advanced.ROOT, advanced.WORKSPACE = root, workspace
            try:
                with patch.object(advanced.shutil, "which", return_value="/usr/bin/aider"):
                    with patch.object(advanced, "git_action", return_value={"ok": True}):
                        with patch.object(advanced.subprocess, "run") as runner:
                            result = advanced.run_aider("AiderReportLink", "Make a safe focused improvement.", approved=True)
                self.assertFalse(result["ok"])
                self.assertIn("test-reports", result["error"])
                runner.assert_not_called()
                self.assertEqual(list(outside.iterdir()), [])
            finally:
                advanced.ROOT, advanced.WORKSPACE = old_root, old_workspace

    def test_capacitor_scaffold_has_explicit_android_build_scripts(self):
        old_workspace = advanced.WORKSPACE
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "AndroidScaffoldTest"
            project.mkdir()
            (project / "index.html").write_text("<!doctype html><html></html>")
            advanced.WORKSPACE = root
            try:
                result = advanced.create_capacitor("AndroidScaffoldTest", "Scaffold Test")
                package = json.loads((project / "package.json").read_text())
                config = json.loads((project / "capacitor.config.json").read_text())
                self.assertTrue(result["ok"])
                self.assertIn("android:add", package["scripts"])
                self.assertIn("android:debug", package["scripts"])
                self.assertEqual(config["webDir"], "dist")
                self.assertEqual(result["apk_expected_path"], "android/app/build/outputs/apk/debug/app-debug.apk")
                self.assertFalse((project / "android").exists())
            finally:
                advanced.WORKSPACE = old_workspace


if __name__ == '__main__':
    unittest.main(verbosity=2)
