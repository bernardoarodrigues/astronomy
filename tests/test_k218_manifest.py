from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from k218_repeatability.manifest import (
    PROJECT_HARD_MAX_DOWNLOAD_BYTES,
    ManifestError,
    load_manifest,
)


class K218ManifestTests(unittest.TestCase):
    def test_frozen_contract_and_evidence_structure(self) -> None:
        manifest = load_manifest()
        self.assertEqual(
            manifest.canonical_sha256,
            "1434dde1a6c2169e95b1442671555bb27c0d77873daa53f0da6d6e296dec546f",
        )
        self.assertEqual(manifest.archive.size_bytes, 275602)
        self.assertEqual(
            manifest.archive.sha256,
            "4ee5cb6ad42015bd8fb10f64e54329d250137ab1fa129c89a14830946adc8f18",
        )
        self.assertEqual(manifest.archive.license_spdx, "NOASSERTION")
        self.assertEqual(manifest.archive.hard_max_download_bytes, PROJECT_HARD_MAX_DOWNLOAD_BYTES)
        self.assertEqual(len(manifest.members), 4)
        self.assertEqual(
            {(item.reduction, item.visit, item.detector) for item in manifest.members},
            {
                ("Eureka", "visit_2", "NRS2"),
                ("Eureka", "visit_3", "NRS2"),
                ("exoTEDRF", "visit_2", "NRS2"),
                ("exoTEDRF", "visit_3", "NRS2"),
            },
        )
        program = manifest.program
        self.assertEqual(program["evidence_units"], 2)
        self.assertEqual(program["paired_correlated_views_per_evidence_unit"], 2)
        self.assertFalse(program["reductions_are_independent"])
        self.assertEqual(program["selection_basis"], "metadata_only")
        self.assertFalse(program["spectral_result_selection"])
        self.assertFalse(program["complete_g395h_visit_inventory"]["visit_1"]["eligible"])
        self.assertEqual(program["complete_g395h_visit_inventory"]["visit_1"]["paper_label"], "C1")

    def test_grid_and_fail_closed_outcomes_are_frozen(self) -> None:
        manifest = load_manifest()
        self.assertEqual(manifest.rebinning.resolving_power, 100.0)
        self.assertEqual(manifest.rebinning.first_edge_index, 135)
        self.assertEqual(manifest.rebinning.last_edge_index, 155)
        self.assertEqual(
            manifest.rebinning.edge_sha256,
            "7f7e418fc0bfde1478d7ade8a4fef0f774bc7bb0f3046a918be7bc763d3b2d28",
        )
        self.assertEqual(manifest.rebinning.coverage_relative_tolerance, 1e-12)
        self.assertEqual(
            set(manifest.analysis_contract["outcome_rules"]),
            {"repeatable_positive_morphology", "SCIENCE_UNRESOLVED"},
        )
        self.assertEqual(
            manifest.analysis_contract["combination_rules"]["cross_reduction_z_combination"],
            "prohibited",
        )
        self.assertEqual(manifest.output_contract["molecule"], "not_evaluated")
        self.assertEqual(manifest.output_contract["biosignature"], "not_evaluated")
        self.assertFalse(manifest.output_contract["evidence_of_life"])
        self.assertNotIn("3.3", json.dumps(manifest.analysis_contract))

    def test_any_manifest_change_fails_the_canonical_freeze(self) -> None:
        source = Path(__file__).resolve().parents[1] / "src/k218_repeatability/data_manifest.json"
        raw = json.loads(source.read_text(encoding="utf-8"))
        raw["analysis"]["pivot_micrometres"] = 4.31
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(ManifestError, "frozen pre-result contract"):
                load_manifest(path)


if __name__ == "__main__":
    unittest.main()
