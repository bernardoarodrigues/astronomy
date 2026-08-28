from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from synthetic_atmosphere_benchmark.canonical import canonical_sha256
from synthetic_atmosphere_benchmark.manifest import ManifestError, load_manifest


class SyntheticManifestTests(unittest.TestCase):
    def test_frozen_scope_sources_counts_and_claims(self) -> None:
        manifest = load_manifest()
        self.assertEqual(manifest.benchmark_id, "synthetic_atmosphere_engineering_preflight_v1")
        self.assertEqual(manifest.cases_per_family * len(manifest.families), 648)
        self.assertEqual(manifest.raw["states"]["science_state"], "not_applicable_synthetic")
        self.assertEqual(manifest.raw["states"]["real_data_readiness"], "not_established")
        self.assertFalse(manifest.raw["scope"]["full_b3_gate"])
        self.assertFalse(manifest.raw["scope"]["authorizes_k2_18"])
        self.assertFalse(manifest.raw["grid"]["uses_observed_transit_depths"])
        self.assertEqual(manifest.raw["future_sealed_b3b"]["negative_cases_per_family"], 2000)
        self.assertEqual(manifest.raw["future_sealed_b3b"]["power_cases_per_cell"], 1000)
        self.assertEqual(manifest.raw["future_sealed_b3b"]["coverage_cases_per_key_cell"], 2000)
        self.assertIn("ambiguous_cancellation", manifest.families)
        self.assertNotIn("nonidentifiable", manifest.families)
        self.assertEqual(
            {item.role for item in manifest.members},
            {"eureka_grid_uncertainties", "picaso_water_template", "phoenix_m1_m3_models"},
        )

    def test_contract_and_claim_tampering_fail_closed(self) -> None:
        bundled = Path("src/synthetic_atmosphere_benchmark/data_manifest.json")
        raw = json.loads(bundled.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            raw["preflight_gates"]["pooled_unsafe_specific_classification_max"] = 1.0
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(ManifestError, "contract SHA-256"):
                load_manifest(path)

            raw = json.loads(bundled.read_text(encoding="utf-8"))
            raw["allowed_claim"] = "Atmosphere detected."
            contract = dict(raw)
            contract.pop("contract_sha256")
            raw["contract_sha256"] = canonical_sha256(contract)
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(ManifestError, "allowed claim"):
                load_manifest(path)

            raw = json.loads(bundled.read_text(encoding="utf-8"))
            raw["description"] = "recomputed-hash mutation"
            contract = dict(raw)
            contract.pop("contract_sha256")
            raw["contract_sha256"] = canonical_sha256(contract)
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(ManifestError, "frozen manifest contract"):
                load_manifest(path)


if __name__ == "__main__":
    unittest.main()
