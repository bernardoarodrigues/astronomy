from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from synthetic_atmosphere_benchmark.canonical import sha256_file
from synthetic_atmosphere_benchmark.source import SourceError, _bin_average, _verify_member, load_eureka_scaffold


class SyntheticSourceTests(unittest.TestCase):
    def _grid_file(self, directory: str, *, nonmonotonic: bool = False) -> Path:
        rows = []
        wavelengths = [2.867] + [2.887 + 0.02 * index for index in range(109)]
        if nonmonotonic:
            wavelengths[20] = wavelengths[19]
        for wavelength in wavelengths:
            # The poison token proves the observed-depth column is not parsed.
            rows.append(f"Eureka {wavelength:.6f} 0.010 POISON 20")
        path = Path(directory) / "grid.txt"
        path.write_text("\n".join(rows) + "\n", encoding="utf-8")
        return path

    def test_grid_loader_never_parses_observed_depths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            wavelength, width, uncertainty = load_eureka_scaffold(self._grid_file(directory))
        self.assertEqual(wavelength.size, 109)
        np.testing.assert_allclose(width, 0.01)
        np.testing.assert_allclose(uncertainty, 20.0)

    def test_grid_validation_rejects_nonmonotonic_and_nonpositive_uncertainty(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(SourceError, "strictly increasing"):
                load_eureka_scaffold(self._grid_file(directory, nonmonotonic=True))
            path = self._grid_file(directory)
            text = path.read_text(encoding="utf-8").replace("POISON 20", "POISON 0", 1)
            path.write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(SourceError, "positive"):
                load_eureka_scaffold(path)

    def test_integrity_verifier_rejects_size_and_checksum_failures(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "member.txt"
            path.write_bytes(b"pinned content")
            digest = sha256_file(path)
            record = _verify_member(path, size_bytes=14, sha256=digest)
            self.assertEqual(record["status"], "verified")
            with self.assertRaisesRegex(SourceError, "size mismatch"):
                _verify_member(path, size_bytes=13, sha256=digest)
            with self.assertRaisesRegex(SourceError, "SHA-256 mismatch"):
                _verify_member(path, size_bytes=14, sha256="0" * 64)

    def test_piecewise_linear_bin_average(self) -> None:
        model_x = np.asarray([0.0, 1.0, 2.0])
        model_y = np.asarray([0.0, 2.0, 4.0])
        actual = _bin_average(model_x, model_y, np.asarray([0.5, 1.5]), np.asarray([1.0, 1.0]))
        np.testing.assert_allclose(actual, [1.0, 3.0], atol=1e-15)


if __name__ == "__main__":
    unittest.main()
