import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = ROOT / "docs" / "hypothesis_ledger.json"


class HypothesisLedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))

    def test_ledger_has_unique_ids_and_required_fields(self):
        required = {
            "hypothesis_id",
            "target_id",
            "track",
            "layer",
            "selection_status",
            "exact_claim",
            "status",
            "null_hypothesis",
            "competing_hypotheses",
            "test",
            "success_gate",
            "stop_rule",
            "allowed_claim",
        }
        hypotheses = self.ledger["hypotheses"]
        ids = [hypothesis["hypothesis_id"] for hypothesis in hypotheses]

        self.assertEqual(len(ids), len(set(ids)))
        for hypothesis in hypotheses:
            self.assertFalse(required - hypothesis.keys(), hypothesis["hypothesis_id"])

    def test_controlled_vocabularies_are_used(self):
        statuses = set(self.ledger["status_vocabulary"])
        selections = set(self.ledger["selection_vocabulary"])

        for hypothesis in self.ledger["hypotheses"]:
            self.assertIn(hypothesis["status"], statuses)
            self.assertIn(hypothesis["selection_status"], selections)

    def test_k2_18_life_claim_is_not_present(self):
        k2_claims = [
            hypothesis["allowed_claim"].lower()
            for hypothesis in self.ledger["hypotheses"]
            if hypothesis["target_id"] == "K2-18-b"
        ]

        self.assertTrue(k2_claims)
        self.assertTrue(all("evidence of life" not in claim for claim in k2_claims))


if __name__ == "__main__":
    unittest.main()
