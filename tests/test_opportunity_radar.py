import unittest
from advanced import opportunity_score

class OpportunityScoreTests(unittest.TestCase):
    def test_empty_evidence_scores_zero(self):
        self.assertEqual(opportunity_score({}), 0)

    def test_revenue_threshold_awards_top_demand_points(self):
        self.assertEqual(opportunity_score({"revenue_usd_monthly": 50000}), 25)

    def test_revenue_below_threshold_is_not_top_tier(self):
        self.assertEqual(opportunity_score({"revenue_usd_monthly": 10000}), 15)

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
