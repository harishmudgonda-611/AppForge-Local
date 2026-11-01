"""Regression checks for the opt-in hosted Android APK workflow.

These checks validate workflow policy and command wiring. They do not replace
running the workflow or installing the resulting APK on a device.
"""
from pathlib import Path
import json
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "android-apk.yml"
README = ROOT / "README.md"
ANDROID_FIXTURE = ROOT / "apps" / "android-smoke-test"


class AndroidWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        cls.readme = README.read_text(encoding="utf-8")

    def test_build_requires_committed_lockfile_and_clean_install(self):
        self.assertIn("test -s package-lock.json", self.workflow)
        self.assertIn("npm ci", self.workflow)
        self.assertNotIn("npm install", self.workflow)

    def test_build_checks_capacitor_dependencies_and_web_output(self):
        for dependency in ("@capacitor/core", "@capacitor/cli", "@capacitor/android"):
            self.assertIn(dependency, self.workflow)
        self.assertIn("test -s dist/index.html", self.workflow)
        self.assertIn("c.webDir !== 'dist'", self.workflow)

    def test_capacitor_8_android_toolchain_uses_jdk_21(self):
        self.assertIn('java-version: "21"', self.workflow)
        self.assertIn('sdkmanager --licenses', self.workflow)
        self.assertIn('platforms;android-36', self.workflow)

    def test_apk_is_checked_and_identity_matches_config(self):
        self.assertIn("unzip -t", self.workflow)
        self.assertIn("aapt", self.workflow)
        self.assertIn("EXPECTED_ID", self.workflow)
        self.assertIn("ACTUAL_ID", self.workflow)
        self.assertIn("APK-SHA256.txt", self.workflow)

    def test_apk_is_installed_and_launched_in_android_emulator(self):
        self.assertIn("reactivecircus/android-emulator-runner@v2", self.workflow)
        self.assertIn("adb install -r", self.workflow)
        self.assertIn("adb shell am start", self.workflow)
        self.assertIn("dumpsys activity activities", self.workflow)

    def test_artifact_contains_apk_and_checksum(self):
        self.assertIn("app-debug.apk", self.workflow)
        self.assertIn("APK-SHA256.txt", self.workflow)
        self.assertIn("if-no-files-found: error", self.workflow)

    def test_committed_smoke_fixture_has_matching_lockfile(self):
        package = json.loads((ANDROID_FIXTURE / "package.json").read_text(encoding="utf-8"))
        lock = json.loads((ANDROID_FIXTURE / "package-lock.json").read_text(encoding="utf-8"))
        config = json.loads((ANDROID_FIXTURE / "capacitor.config.json").read_text(encoding="utf-8"))
        self.assertEqual(lock["lockfileVersion"], 3)
        self.assertEqual(lock["packages"][""]["dependencies"], package["dependencies"])
        self.assertEqual(config["webDir"], "dist")
        self.assertTrue(config["appId"])
        self.assertTrue((ANDROID_FIXTURE / "index.html").is_file())
        self.assertTrue((ANDROID_FIXTURE / "build.mjs").is_file())

    def test_android_quick_start_uses_localhost_and_no_cloud_runtime(self):
        guide = (ROOT / "ANDROID-QUICKSTART.md").read_text(encoding="utf-8")
        setup = (ROOT / "android-setup.sh").read_text(encoding="utf-8")
        launcher = (ROOT / "android-start.sh").read_text(encoding="utf-8")
        self.assertIn("127.0.0.1:8787", guide)
        self.assertIn("pkg install -y python curl", setup)
        self.assertIn('BASE_URL="http://127.0.0.1:${PORT}"', launcher)
        self.assertIn("api/health", launcher)
        self.assertNotIn("0.0.0.0", launcher)

    def test_documentation_discloses_hosted_build_and_lockfile(self):
        self.assertIn("package-lock.json", self.readme)
        self.assertIn("GitHub-hosted runner", self.readme)
        self.assertIn("does not sign a production release", self.readme)


if __name__ == "__main__":
    unittest.main()
