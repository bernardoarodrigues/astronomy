from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from atmosphere_benchmark.spectrum import SpectrumError, load_spectrum


HEADER = "wv_center transit_depth wv_wdth tran_unc\n"


class AtmosphereSpectrumTests(unittest.TestCase):
    def load_text(self, text: str):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "spectrum.txt"
            path.write_text(text, encoding="utf-8")
            return load_spectrum(path)

    def test_valid_schema(self) -> None:
        spectrum = self.load_text(
            HEADER + "4.1 0.02 0.02 0.0001\n4.2 0.021 0.02 0.0001\n"
        )
        self.assertEqual(spectrum.wavelength.size, 2)

    def test_malformed_schema(self) -> None:
        with self.assertRaisesRegex(SpectrumError, "malformed spectrum schema"):
            self.load_text("wavelength depth width error\n4.1 0.02 0.02 0.0001\n")

    def test_nonfinite_value(self) -> None:
        with self.assertRaisesRegex(SpectrumError, "nonfinite"):
            self.load_text(HEADER + "4.1 nan 0.02 0.0001\n")

    def test_nonpositive_uncertainty(self) -> None:
        with self.assertRaisesRegex(SpectrumError, "uncertainties must be positive"):
            self.load_text(HEADER + "4.1 0.02 0.02 0.0\n")

    def test_nonmonotonic_wavelength(self) -> None:
        with self.assertRaisesRegex(SpectrumError, "strictly increasing"):
            self.load_text(
                HEADER + "4.2 0.02 0.02 0.0001\n4.1 0.021 0.02 0.0001\n"
            )


if __name__ == "__main__":
    unittest.main()
