from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from gj486_benchmark.manifest import PROJECT_HARD_MAX_DOWNLOAD_BYTES, ManifestError, load_manifest


class GJ486ManifestTests(unittest.TestCase):
    def modified_manifest(self, mutate) -> Path:
        source = Path(__file__).parents[1] / "src" / "gj486_benchmark" / "data_manifest.json"
        raw = json.loads(source.read_text(encoding="utf-8"))
        mutate(raw)
        handle = tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8", delete=False)
        self.addCleanup(Path(handle.name).unlink, missing_ok=True)
        with handle:
            json.dump(raw, handle)
        return Path(handle.name)

    def test_frozen_sources_programs_and_claim_state(self) -> None:
        manifest = load_manifest()
        self.assertEqual(manifest.archive.doi, "10.5281/zenodo.10408056")
        self.assertEqual(manifest.archive.size_bytes, 1_455_085)
        self.assertEqual(manifest.external_constraint.archive.doi, "10.5281/zenodo.13774462")
        self.assertEqual(manifest.external_constraint.archive.size_bytes, 288_070_101)
        self.assertEqual(manifest.archive.license_spdx, "CC-BY-4.0")
        self.assertEqual(manifest.external_constraint.archive.license_spdx, "CC-BY-4.0")
        self.assertEqual(
            manifest.program_provenance,
            {
                "GO-1981": "NIRSpec/G395H transmission",
                "GO-1743": "MIRI/LRS eclipse",
                "GO-5866": "NIRISS/SOSS transmission",
            },
        )
        self.assertEqual(
            manifest.expected_feature_state,
            "retrospective_template_regression_reproduced",
        )
        self.assertEqual(manifest.expected_science_state, "science_unresolved")
        self.assertEqual(len(manifest.members), 3)
        self.assertEqual(len(manifest.external_constraint.members), 4)

    def test_hard_limit_cannot_be_raised_for_either_source(self) -> None:
        for location in (("archive",), ("external_constraint", "archive")):
            def mutate(raw, location=location):
                target = raw
                for key in location:
                    target = target[key]
                target["hard_max_download_bytes"] = PROJECT_HARD_MAX_DOWNLOAD_BYTES + 1

            with self.subTest(location=location):
                with self.assertRaisesRegex(ManifestError, "project hard limit"):
                    load_manifest(self.modified_manifest(mutate))

    def test_program_provenance_is_hard_asserted(self) -> None:
        path = self.modified_manifest(lambda raw: raw["program_provenance"].update({"GO-1981": "MIRI"}))
        with self.assertRaisesRegex(ManifestError, "program provenance"):
            load_manifest(path)

    def test_interpretation_and_claim_fields_are_hard_asserted(self) -> None:
        changes = (
            (
                lambda raw: raw.update({"allowed_claim": "Water was detected on GJ 486 b."}),
                "allowed claim",
            ),
            (lambda raw: raw.update({"prohibited_claims": []}), "prohibited claims"),
            (
                lambda raw: raw["external_context"].update(
                    {"NIRISS_5866": "independent confirmation"}
                ),
                "external evidence context",
            ),
            (
                lambda raw: raw["external_constraint"].update(
                    {"classification": "all_atmospheres_excluded"}
                ),
                "MIRI classification",
            ),
            (
                lambda raw: raw["external_constraint"].update(
                    {"claim_limit": "All atmospheres are excluded."}
                ),
                "MIRI claim limit",
            ),
        )
        for mutate, message in changes:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ManifestError, message):
                    load_manifest(self.modified_manifest(mutate))

    def test_any_other_scientific_contract_change_is_rejected(self) -> None:
        changes = (
            lambda raw: raw["archive"].update({"doi": "10.5281/zenodo.99999999"}),
            lambda raw: raw["archive"].update({"sha256": "0" * 64}),
            lambda raw: raw["members"][0].update({"sha256": "0" * 64}),
            lambda raw: raw["analysis"].update({"z_tolerance": 1e12}),
            lambda raw: raw["external_constraint"]["analysis"].update(
                {"fingerprint_tolerance": 1e12}
            ),
        )
        for mutate in changes:
            with self.subTest():
                with self.assertRaisesRegex(ManifestError, "frozen canonical scientific contract"):
                    load_manifest(self.modified_manifest(mutate))

    def test_rejects_unsafe_primary_and_external_member_paths(self) -> None:
        for mutate in (
            lambda raw: raw["members"][0].update({"path": "../bad"}),
            lambda raw: raw["external_constraint"]["members"][0].update({"path": "/bad"}),
        ):
            with self.subTest():
                with self.assertRaisesRegex(ManifestError, "unsafe archive member path"):
                    load_manifest(self.modified_manifest(mutate))


if __name__ == "__main__":
    unittest.main()
