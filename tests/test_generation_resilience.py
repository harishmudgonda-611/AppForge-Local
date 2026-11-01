"""Regression tests for resilient local-model PWA generation."""
import unittest
import server
import advanced


class GenerationResilienceTests(unittest.TestCase):
    def test_extracts_json_surrounded_by_model_commentary(self):
        value = server.extract_model_json('Here is the result: {"app_name":"Demo","files":{}} Done.')
        self.assertEqual(value["app_name"], "Demo")

    def test_rejects_unbalanced_or_non_object_json(self):
        self.assertIsNone(server.extract_model_json('{"files":'))
        self.assertIsNone(server.extract_model_json('["index.html","app.js"]'))

    def test_normalizes_dictionary_file_map(self):
        result = server.normalize_model_files({"files":{"index.html":"<html>ok</html>","app.js":{"content":"console.log(1)"}}})
        self.assertEqual(result["app.js"], "console.log(1)")

    def test_normalizes_list_of_file_records(self):
        result = server.normalize_model_files({"files":[{"path":"index.html","content":"<html>ok</html>"}]})
        self.assertEqual(result["index.html"], "<html>ok</html>")

    def test_filename_only_response_is_detected_as_unusable_file_map(self):
        result = server.normalize_model_files({"files":["index.html","app.js","styles.css"]})
        self.assertEqual(result, {})

    def test_split_generation_builds_required_pwa_files(self):
        calls = []
        def fake_model(system, user, raw=False):
            calls.append(user)
            return {"ok":True,"text":"/* " + ("x" * 120) + " */"}
        files, error = server.generate_split_source_files(fake_model,"Demo","Build a demo app")
        self.assertIsNone(error)
        self.assertEqual(set(files), {"index.html","app.js","styles.css","manifest.webmanifest","sw.js","README.md"})
        self.assertEqual(len(calls), 3)
        normalized, validation_error = server.validate_generated_files(files)
        self.assertIsNone(validation_error)
        self.assertEqual(set(normalized), set(files))


    def test_replica_normalizes_list_of_file_records(self):
        result = advanced.normalize_replica_files({"files":[{"path":"app.js","content":"console.log('ok')"}]})
        self.assertEqual(result["app.js"], "console.log('ok')")

    def test_replica_falls_back_when_model_returns_only_filenames(self):
        calls = []
        def fake_model(system, user, raw=False):
            calls.append(user)
            return {"ok":True,"text":"/* " + ("x" * 120) + " */"}
        files, error = advanced.generate_replica_split_files(fake_model, "Demo", {"scope":"test"})
        self.assertIsNone(error)
        self.assertIn("index.html", files)
        self.assertIn("manifest.webmanifest", files)
        self.assertEqual(len(calls), 3)


if __name__ == "__main__":
    unittest.main()
