import tempfile
import unittest
from pathlib import Path
import opportunity_radar


class OpportunityRadarTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_db = opportunity_radar.DB
        opportunity_radar.DB = Path(self.temp.name) / "test.db"

    def tearDown(self):
        opportunity_radar.DB = self.original_db
        self.temp.cleanup()

    def sample(self, **overrides):
        data = {
            "title": "Offline invoice app",
            "problem": "Freelancers need simple invoices offline.",
            "audience": "Indian freelancers",
            "source_name": "Reddit",
            "source_url": "https://reddit.com/",
            "evidence": "Manual notes from user discussion",
            "revenue_note": "No revenue evidence yet",
            "launch_age": "Unknown",
            "demand": 20,
            "revenue": 2,
            "gap": 18,
            "build_ease": 12,
            "monetization": 8,
            "fit": 9,
            "status": "validate",
        }
        data.update(overrides)
        return data

    def test_create_and_rank_saved_idea(self):
        created = opportunity_radar.save_opportunity(self.sample())
        self.assertTrue(created["ok"])
        self.assertEqual(created["opportunity"]["score"], 69)
        listed = opportunity_radar.list_opportunities()
        self.assertEqual(len(listed["opportunities"]), 1)
        self.assertEqual(listed["opportunities"][0]["title"], "Offline invoice app")
        self.assertEqual(listed["score_max"], 100)
        self.assertTrue(listed["sources"])

    def test_update_existing_idea(self):
        created = opportunity_radar.save_opportunity(self.sample())
        oid = created["opportunity"]["id"]
        updated = opportunity_radar.save_opportunity(self.sample(id=oid, title="Updated title", demand=25))
        self.assertEqual(updated["opportunity"]["title"], "Updated title")
        self.assertEqual(updated["opportunity"]["demand"], 25)
        self.assertEqual(updated["opportunity"]["score"], 74)
        self.assertEqual(len(opportunity_radar.list_opportunities()["opportunities"]), 1)

    def test_score_bounds_are_enforced(self):
        with self.assertRaises(ValueError):
            opportunity_radar.save_opportunity(self.sample(demand=26))
        with self.assertRaises(ValueError):
            opportunity_radar.save_opportunity(self.sample(revenue=-1))

    def test_title_required_and_delete(self):
        with self.assertRaises(ValueError):
            opportunity_radar.save_opportunity(self.sample(title=""))
        created = opportunity_radar.save_opportunity(self.sample())
        self.assertTrue(opportunity_radar.delete_opportunity(created["opportunity"]["id"])["ok"])
        self.assertEqual(opportunity_radar.list_opportunities()["opportunities"], [])

    def test_delete_unknown_id_fails(self):
        with self.assertRaises(ValueError):
            opportunity_radar.delete_opportunity(9999)


if __name__ == "__main__":
    unittest.main()
