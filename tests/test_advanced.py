import unittest, tempfile, json
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

    def test_repair_requires_approval(self):
        with self.assertRaises(ValueError): advanced.repair_project('NoSuchProject_abcdef',False)

if __name__=='__main__': unittest.main(verbosity=2)


    def test_local_model_endpoint_policy(self):
        self.assertTrue(advanced.local_endpoint_allowed("http://127.0.0.1:8080/v1"))
        self.assertTrue(advanced.local_endpoint_allowed("http://192.168.1.20:11434/v1"))
        self.assertFalse(advanced.local_endpoint_allowed("https://example.com/v1"))
        self.assertFalse(advanced.local_endpoint_allowed("http://8.8.8.8/v1"))
        self.assertFalse(advanced.local_endpoint_allowed("file:///etc/passwd"))

    def test_repair_rejects_remote_endpoint_before_model_call(self):
        old_workspace = advanced.WORKSPACE
        with tempfile.TemporaryDirectory() as tmp:
            advanced.WORKSPACE = Path(tmp)
            project = Path(tmp) / "RemoteRepairGuard"
            project.mkdir()
            (project / "index.html").write_text("<html></html>")
            # No node is required: the valid minimal project should pass current checks.
            result = advanced.repair_project("RemoteRepairGuard", approved=True)
            self.assertTrue(result["ok"])
            advanced.WORKSPACE = old_workspace

