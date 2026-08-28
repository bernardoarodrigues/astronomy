from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from voyager_benchmark.manifest import (
    HARD_MAX_DOWNLOAD_BYTES,
    ManifestError,
    load_manifest,
)


class ManifestTests(unittest.TestCase):
    def test_bundled_manifest_has_guarded_small_sample(self) -> None:
        manifest = load_manifest()
        self.assertEqual(manifest.size_bytes, 50_549_227)
        self.assertLess(manifest.size_bytes, 100_000_000)
        self.assertLess(manifest.size_bytes, HARD_MAX_DOWNLOAD_BYTES)
        self.assertEqual(len(manifest.benchmark.known_signal_targets), 3)
        self.assertEqual(manifest.data_license_spdx, "NOASSERTION")
        self.assertEqual(
            manifest.git_blob_oid, "42a41e5c2564afc8e73dc7b23cece3e3123f15d6"
        )
        self.assertIn("dbfb5e35", manifest.url)

    def test_rejects_path_traversal_filename(self) -> None:
        package_manifest = (
            Path(__file__).parents[1]
            / "src"
            / "voyager_benchmark"
            / "data_manifest.json"
        )
        raw = json.loads(package_manifest.read_text(encoding="utf-8"))
        raw["filename"] = "../observation.h5"
        with tempfile.TemporaryDirectory() as raw_dir:
            path = Path(raw_dir) / "manifest.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(ManifestError, "plain basename"):
                load_manifest(path)

    def test_rejects_manifest_over_hard_cap(self) -> None:
        package_manifest = (
            Path(__file__).parents[1]
            / "src"
            / "voyager_benchmark"
            / "data_manifest.json"
        )
        raw = json.loads(package_manifest.read_text(encoding="utf-8"))
        raw["size_bytes"] = HARD_MAX_DOWNLOAD_BYTES + 1
        with tempfile.TemporaryDirectory() as raw_dir:
            path = Path(raw_dir) / "manifest.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(ManifestError, "size_bytes"):
                load_manifest(path)


if __name__ == "__main__":
    unittest.main()
