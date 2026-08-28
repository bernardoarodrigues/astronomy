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

    def test_gj486_is_frozen_as_unresolved_with_narrow_claim(self):
        hypothesis = next(
            item
            for item in self.ledger["hypotheses"]
            if item["hypothesis_id"] == "H-GJ486-ORIGIN"
        )
        self.assertEqual(hypothesis["status"], "unresolved")
        self.assertEqual(
            hypothesis["allowed_claim"],
            "The harness reproduces the pinned GO 1981 NIRSpec water-template regressions and exposes their reduction, detector-side, influential-bin, covariance, and nuisance sensitivity; no direct planet-versus-star origin comparison is available in the deposited products.",
        )
        self.assertNotIn("detection", hypothesis["allowed_claim"].lower())

    def test_b3a_remains_incomplete_and_does_not_authorize_k2_18(self):
        hypothesis = next(
            item
            for item in self.ledger["hypotheses"]
            if item["hypothesis_id"] == "H-SYNTH-ATM-B3A"
        )
        self.assertEqual(hypothesis["status"], "contradicted")
        self.assertIn("remains incomplete", hypothesis["allowed_claim"].lower())
        self.assertIn("do not tune", hypothesis["stop_rule"].lower())
        self.assertIn("authorize k2-18 b", hypothesis["stop_rule"].lower())
        b3b = next(
            item
            for item in self.ledger["hypotheses"]
            if item["hypothesis_id"] == "H-SYNTH-ATM-B3B"
        )
        self.assertEqual(b3b["status"], "untested")
        self.assertIn("remain unestablished", b3b["allowed_claim"].lower())

    def test_k218_morphology_is_separate_non_attribution_hypothesis(self):
        hypothesis = next(
            item
            for item in self.ledger["hypotheses"]
            if item["hypothesis_id"] == "H-K218-G395H-MORPH"
        )
        self.assertEqual(hypothesis["layer"], "observation")
        self.assertEqual(hypothesis["status"], "contradicted")
        self.assertIn("SCIENCE_UNRESOLVED", hypothesis["allowed_claim"])
        self.assertIn("molecular attribution is not evaluated", hypothesis["allowed_claim"])
        self.assertIn("cannot update H-K218-CO2", hypothesis["stop_rule"])
        self.assertIn("B3/B3b", hypothesis["stop_rule"])


if __name__ == "__main__":
    unittest.main()
