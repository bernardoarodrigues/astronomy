from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from gj486_benchmark.data import (
    DataError,
    load_miri_atmosphere_model,
    load_miri_spectrum,
    load_stellar_groups,
    load_transmission_spectra,
    load_water_model,
)


TRANSMISSION_HEADER = """Reduction  Reduction identifier
Wave       Wavelength
Width      Wavelength bin width
Depth      Transit depth; parts per million
e_Depth      Uncertainty in Depth
"""

STELLAR_HEADER = """Type   Data type
Wave   Wavelength
Flux   Flux density
e_Flux   ? Uncertainty
"""


class GJ486DataTests(unittest.TestCase):
    def path(self, text: str) -> Path:
        handle = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False)
        self.addCleanup(Path(handle.name).unlink, missing_ok=True)
        with handle:
            handle.write(text)
        return Path(handle.name)

    def transmission(self, replacement: str = "") -> str:
        rows = """Eureka 2.90 0.01 1300 20
Firefly 2.91 0.02 1310 25
Tiberius 2.92 0.02 1320 24
"""
        return TRANSMISSION_HEADER + (replacement or rows)

    def test_transmission_schema_and_validation(self) -> None:
        spectra = load_transmission_spectra(
            self.path(self.transmission()),
            expected_rows={"Eureka": 1, "Firefly": 1, "Tiberius": 1},
        )
        self.assertEqual(spectra["Eureka"].depth_ppm[0], 1300)
        with self.assertRaisesRegex(DataError, "malformed transmission-spectrum schema"):
            load_transmission_spectra(self.path("bad\n"))
        with self.assertRaisesRegex(DataError, "nonfinite"):
            load_transmission_spectra(self.path(self.transmission("Eureka 2.9 0.1 nan 2\nFirefly 2.9 0.1 1 2\nTiberius 2.9 0.1 1 2\n")))
        with self.assertRaisesRegex(DataError, "uncertainties must be positive"):
            load_transmission_spectra(self.path(self.transmission("Eureka 2.9 0.1 1 0\nFirefly 2.9 0.1 1 2\nTiberius 2.9 0.1 1 2\n")))
        nonmonotonic = "Eureka 3.0 0.1 1 2\nEureka 2.9 0.1 1 2\nFirefly 2.9 0.1 1 2\nTiberius 2.9 0.1 1 2\n"
        with self.assertRaisesRegex(DataError, "strictly increasing"):
            load_transmission_spectra(self.path(self.transmission(nonmonotonic)))

    def test_water_model_validation(self) -> None:
        model = load_water_model(self.path("header\n1.0 0.001\n2.0 0.002\n"), expected_rows=2)
        self.assertEqual(model.values.size, 2)
        with self.assertRaisesRegex(DataError, "strictly increasing"):
            load_water_model(self.path("2.0 0.1\n1.0 0.2\n"))
        with self.assertRaisesRegex(DataError, "positive"):
            load_water_model(self.path("1.0 0.0\n2.0 0.2\n"))

    def stellar(self, *, bad_uncertainty: bool = False) -> str:
        uncertainty = "0" if bad_uncertainty else "1"
        return STELLAR_HEADER + f"""V1 1.0 10 {uncertainty}
V1 2.0 11 1
V2 1.0 10 1
V2 2.0 11 1
M1 1.0 9
M1 2.0 10
M2 1.0 9
M2 2.0 11
M3 1.0 10
M3 2.0 11
"""

    def test_stellar_schema_and_uncertainty(self) -> None:
        groups = load_stellar_groups(self.path(self.stellar()))
        self.assertEqual(groups["M3"].flux_mjy.size, 2)
        self.assertIsNone(groups["M3"].uncertainty_mjy)
        with self.assertRaisesRegex(DataError, "malformed stellar-spectrum schema"):
            load_stellar_groups(self.path("bad\n"))
        with self.assertRaisesRegex(DataError, "uncertainties must be positive"):
            load_stellar_groups(self.path(self.stellar(bad_uncertainty=True)))

    def test_miri_tables(self) -> None:
        spectrum = load_miri_spectrum(self.path("5.0 100 10\n6.0 120 11\n"), expected_rows=2)
        self.assertEqual(spectrum.eclipse_depth_ppm.tolist(), [100.0, 120.0])
        with self.assertRaisesRegex(DataError, "uncertainties must be positive"):
            load_miri_spectrum(self.path("5.0 100 0\n"), expected_rows=1)
        atmosphere = load_miri_atmosphere_model(
            self.path("# header\n0 5.0 4.9 0.1 1 2 0.0001\n1 6.0 5.9 0.1 1 2 0.0002\n")
        )
        self.assertEqual(atmosphere.values.tolist(), [0.0001, 0.0002])
        with self.assertRaisesRegex(DataError, "expected 7 columns"):
            load_miri_atmosphere_model(self.path("0 5.0 1\n"))


if __name__ == "__main__":
    unittest.main()
