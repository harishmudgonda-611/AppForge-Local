import unittest
from advanced import opportunity_score, opportunity_is_recent

class OpportunityScoreTests(unittest.TestCase):
    def test_empty_evidence_scores_zero(self):
        self.assertEqual(opportunity_score({}), 10)  # default build difficulty and operating cost points

    def test_recent_launch_filter_accepts_recent_date(self):
        from datetime import date
        today=date.today()
        recent=today.replace(year=today.year-1) if today.month==12 else today.replace(year=today.year-1,month=today.month+1)
        self.assertTrue(opportunity_is_recent({'launch_date':recent.isoformat()}))

    def test_recent_launch_filter_rejects_old_or_invalid_date(self):
        self.assertFalse(opportunity_is_recent({'launch_date':'2000-01-01'}))
        self.assertFalse(opportunity_is_recent({'launch_date':'not-a-date'}))

    def test_revenue_threshold_awards_top_demand_points(self):
        self.assertEqual(opportunity_score({"revenue_usd_monthly": 50000}), 35)

    def test_revenue_below_threshold_is_not_top_tier(self):
        self.assertEqual(opportunity_score({"revenue_usd_monthly": 10000}), 25)

    def test_differentiation_and_pain_points_add_points(self):
        base = opportunity_score({})
        improved = opportunity_score({"pain_points": "slow onboarding", "differentiator": "offline mode"})
        self.assertEqual(improved - base, 30)

    def test_difficulty_and_operating_cost_are_bounded(self):
        low = opportunity_score({"build_difficulty": 1, "operating_cost": 1})
        high = opportunity_score({"build_difficulty": 5, "operating_cost": 5})
        self.assertGreater(low, high)

if __name__ == "__main__":
    unittest.main()
