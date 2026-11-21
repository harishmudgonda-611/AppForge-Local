import unittest
import agents
import advanced
import tempfile
from pathlib import Path


class AgentRegistryTests(unittest.TestCase):
    def test_workflow_run_persists_and_updates(self):
        original_db=advanced.DB
        with tempfile.TemporaryDirectory() as temp:
            advanced.DB=Path(temp)/"test.sqlite3"
            try:
                steps=[{"id":"market-scout","status":"pending"}]
                run=advanced.workflow_create("Test","Research brief",steps)
                self.assertEqual(run["status"],"running")
                self.assertEqual(run["input_text"],"Research brief")
                steps[0]["status"]="completed"
                updated=advanced.workflow_update(run["id"],steps,"awaiting_approval")
                self.assertEqual(updated["steps"][0]["status"],"completed")
                self.assertEqual(advanced.workflow_list()["workflows"][0]["id"],run["id"])
            finally:
                advanced.DB=original_db

    def test_agent_registry_has_unique_ids_and_required_roles(self):
        catalog=agents.list_agents()["agents"]
        ids=[a["id"] for a in catalog]
        self.assertEqual(len(ids),len(set(ids)))
        for required in ("market-scout","competitor-analyst","user-pain-researcher","opportunity-analyst","product-architect","uiux-designer","developer","qa-agent","repair-agent","release-reviewer"):
            self.assertIn(required,ids)

    def test_workflow_plan_has_approval_gate_before_architecture(self):
        plan=agents.workflow_plan()
        ids=[s["id"] for s in plan["steps"]]
        self.assertEqual(ids[:4],["market-scout","competitor-analyst","user-pain-researcher","opportunity-analyst"])
        self.assertLess(ids.index("approval"),ids.index("product-architect"))
        self.assertEqual(plan["approval_required_before"],"product-architect")

    def test_workflow_approval_requires_literal_true(self):
        for value in (False,0,"true",None):
            self.assertFalse(agents.workflow_approval_valid(value))
        self.assertTrue(agents.workflow_approval_valid(True))

    def test_next_step_stops_at_approval_gate(self):
        completed=["market-scout","competitor-analyst","user-pain-researcher","opportunity-analyst"]
        self.assertEqual(agents.workflow_next_step(completed,False)["id"],"approval")
        self.assertTrue(agents.workflow_next_step(completed,False)["blocked"])
        self.assertEqual(agents.workflow_next_step(completed+["approval"],True)["id"],"product-architect")

    def test_unknown_agent_returns_none(self):
        self.assertIsNone(agents.get_agent("not-a-role"))

    def test_role_system_prompts_for_evidence_integrity(self):
        for role in agents.AGENT_ROLES:
            self.assertTrue(role["system"])
            self.assertIn("evidence",role["system"].lower())

if __name__=="__main__":
    unittest.main()
