import unittest
import agents

class AgentRegistryTests(unittest.TestCase):
    def test_agent_registry_has_unique_ids_and_required_roles(self):
        catalog=agents.list_agents()["agents"]
        ids=[a["id"] for a in catalog]
        self.assertEqual(len(ids),len(set(ids)))
        for required in ("market-scout","competitor-analyst","user-pain-researcher","opportunity-analyst","product-architect","uiux-designer","developer","qa-agent","repair-agent","release-reviewer"):
            self.assertIn(required,ids)

    def test_unknown_agent_returns_none(self):
        self.assertIsNone(agents.get_agent("not-a-role"))

    def test_role_system_prompts_for_evidence_integrity(self):
        for role in agents.AGENT_ROLES:
            self.assertTrue(role["system"])
            self.assertIn("evidence",role["system"].lower())

if __name__=="__main__":
    unittest.main()
