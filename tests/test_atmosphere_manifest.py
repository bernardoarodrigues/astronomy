from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from atmosphere_benchmark.manifest import (
    PROJECT_HARD_MAX_DOWNLOAD_BYTES,
    ManifestError,
    load_manifest,
)


class AtmosphereManifestTests(unittest.TestCase):
    def write_modified_manifest(self, change):
        source = (
            Path(__file__).parents[1]
            / "src"
            / "atmosphere_benchmark"
            / "data_manifest.json"
        )
        raw = json.loads(source.read_text(encoding="utf-8"))
        change(raw)
        temporary = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", encoding="utf-8", delete=False
        )
        self.addCleanup(Path(temporary.name).unlink, missing_ok=True)
        with temporary:
            json.dump(raw, temporary)
        return Path(temporary.name)

    def test_frozen_archive_and_primary_member(self) -> None:
        manifest = load_manifest()
        self.assertEqual(manifest.archive.doi, "10.5281/zenodo.6959427")
        self.assertEqual(manifest.archive.size_bytes, 375_091)
        self.assertEqual(
            manifest.archive.publisher_md5,
            "578368eb0c86014462f109d1e8699693",
        )
        self.assertEqual(
            manifest.archive.sha256,
            "5f69e0279885104b49593aea7523903118895a0dadaaff47a5f6a1beda82f7fb",
        )
        self.assertEqual(manifest.archive.license_spdx, "CC-BY-4.0")
        primary = manifest.member_for_role("primary_spectrum")
        self.assertEqual(primary.size_bytes, 7_833)
        self.assertEqual(
            primary.sha256,
            "83e5e45d5867f1abe6a8776469d4284daf2630f66b7f67736453d912a6bfdd27",
        )
        self.assertEqual(manifest.spectrum.row_count, 95)
        self.assertEqual(manifest.analysis.expected_window_rows, 20)
        self.assertEqual(
            manifest.analysis.expected_fingerprint,
            {"amplitude": 0.0015007, "z": 15.51, "delta_chi2": 240.5},
        )

    def test_alternate_manifest_cannot_raise_project_download_ceiling(self) -> None:
        path = self.write_modified_manifest(
            lambda raw: raw["archive"].update(
                {
                    "hard_max_download_bytes": (
                        PROJECT_HARD_MAX_DOWNLOAD_BYTES + 1
                    )
                }
            )
        )
        with self.assertRaisesRegex(ManifestError, "project hard limit"):
            load_manifest(path)

    def test_rejects_unsafe_member_path(self) -> None:
        path = self.write_modified_manifest(
            lambda raw: raw["members"][0].update({"path": "../spectrum.txt"})
        )
        with self.assertRaisesRegex(ManifestError, "unsafe archive member path"):
            load_manifest(path)


if __name__ == "__main__":
    unittest.main()
