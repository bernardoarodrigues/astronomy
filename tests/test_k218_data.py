from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np

from k218_repeatability.data import DataError, load_spectrum
from k218_repeatability.manifest import MemberSpec, load_manifest


EXO_PREAMBLE = """# %ECSV 1.0
# ---
# datatype:
# - {name: instrname, datatype: string}
# - {name: reference, datatype: string}
# - {name: bandpass, datatype: string}
# - {name: iwave, datatype: int64}
# - {name: wave, unit: um, datatype: float64}
# - {name: waveMin, unit: um, datatype: float64}
# - {name: waveMax, unit: um, datatype: float64}
# - {name: xMin, datatype: int64}
# - {name: xMax, datatype: int64}
# - {name: yval, unit: ppm, datatype: float64}
# - {name: yerrLow, unit: ppm, datatype: float64}
# - {name: yerrUpp, unit: ppm, datatype: float64}
# - {name: wlcLow, datatype: float64}
# - {name: wlcUpp, datatype: float64}
# - {name: ignore, datatype: int64}
# - {name: referenceLink, datatype: string}
# delimiter: ','
# meta: !!omap
# - {visit: '1'}
# - {date: '2024-05-28 20:42'}
# schema: astropy-2.0
instrname,reference,bandpass,iwave,wave,waveMin,waveMax,xMin,xMax,yval,yerrLow,yerrUpp,wlcLow,wlcUpp,ignore,referenceLink
"""

EUREKA_PREAMBLE = """# %ECSV 1.0
# ---
# datatype:
# - {name: wavelength, datatype: float64}
# - {name: bin_width, datatype: float64}
# - {name: rp^2_value, datatype: float64}
# - {name: rp^2_errorneg, datatype: float64}
# - {name: rp^2_errorpos, datatype: float64}
# schema: astropy-2.0
wavelength bin_width rp^2_value rp^2_errorneg rp^2_errorpos
"""


def spec(reduction: str) -> MemberSpec:
    return MemberSpec(
        role=f"{reduction}_test",
        reduction=reduction,
        visit="visit_2",
        detector="NRS2",
        path="unused",
        size_bytes=1,
        sha256="0" * 64,
        rows=2,
        wavelength_min_micrometres=3.832,
        wavelength_max_micrometres=3.836,
    )


class K218DataTests(unittest.TestCase):
    def path(self, text: str) -> Path:
        handle = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False)
        self.addCleanup(Path(handle.name).unlink, missing_ok=True)
        with handle:
            handle.write(text)
        return Path(handle.name)

    def exo(self, rows: str | None = None) -> str:
        if rows is None:
            rows = (
                "NIRSPEC_G395H_NRS2,ExoTEP,uniform,0,3.832,3.83,3.834,0,0,3000,10,12,0,0,0,none\n"
                "NIRSPEC_G395H_NRS2,ExoTEP,uniform,1,3.836,3.834,3.838,0,0,3100,14,13,0,0,0,none\n"
            )
        return EXO_PREAMBLE + rows

    def eureka(self, rows: str | None = None) -> str:
        if rows is None:
            rows = (
                "3.832 0.002 0.0030 0.000010 0.000012\n"
                "3.836 0.002 0.0031 0.000014 0.000013\n"
            )
        return EUREKA_PREAMBLE + rows

    def test_exotedrf_schema_units_and_conservative_sigma(self) -> None:
        spectrum = load_spectrum(self.path(self.exo()), spec("exoTEDRF"), load_manifest())
        self.assertEqual(spectrum.depth_ppm.tolist(), [3000.0, 3100.0])
        self.assertEqual(spectrum.uncertainty_ppm.tolist(), [12.0, 14.0])
        self.assertEqual(spectrum.source_metadata["embedded_visit_label_scope"], "reduction_local_not_science_visit")
        malformed = self.exo().replace("unit: ppm", "unit: fraction", 1)
        with self.assertRaisesRegex(DataError, "schema or unit metadata"):
            load_spectrum(self.path(malformed), spec("exoTEDRF"), load_manifest())

    def test_eureka_fraction_to_ppm_and_conservative_sigma(self) -> None:
        spectrum = load_spectrum(self.path(self.eureka()), spec("Eureka"), load_manifest())
        np.testing.assert_allclose(spectrum.depth_ppm, [3000.0, 3100.0])
        np.testing.assert_allclose(spectrum.uncertainty_ppm, [12.0, 14.0])
        self.assertEqual(spectrum.source_metadata["depth_input_unit"], "fractional_transit_depth")

    def test_nonfinite_nonpositive_nonmonotonic_and_discontinuous_fail(self) -> None:
        nonfinite = self.eureka(
            "3.832 0.002 nan 0.00001 0.00001\n3.836 0.002 0.003 0.00001 0.00001\n"
        )
        with self.assertRaisesRegex(DataError, "nonfinite"):
            load_spectrum(self.path(nonfinite), spec("Eureka"), load_manifest())
        nonpositive = self.eureka(
            "3.832 0.002 0.003 0 0.00001\n3.836 0.002 0.003 0.00001 0.00001\n"
        )
        with self.assertRaisesRegex(DataError, "errors must be positive"):
            load_spectrum(self.path(nonpositive), spec("Eureka"), load_manifest())
        nonmonotonic_spec = replace(
            spec("Eureka"),
            wavelength_min_micrometres=3.836,
            wavelength_max_micrometres=3.832,
        )
        nonmonotonic = self.eureka(
            "3.836 0.002 0.003 0.00001 0.00001\n3.832 0.002 0.003 0.00001 0.00001\n"
        )
        with self.assertRaisesRegex(DataError, "strictly increasing"):
            load_spectrum(self.path(nonmonotonic), nonmonotonic_spec, load_manifest())
        discontinuous_spec = replace(spec("Eureka"), wavelength_max_micrometres=3.840)
        discontinuous = self.eureka(
            "3.832 0.002 0.003 0.00001 0.00001\n3.840 0.002 0.003 0.00001 0.00001\n"
        )
        with self.assertRaisesRegex(DataError, "contiguous"):
            load_spectrum(self.path(discontinuous), discontinuous_spec, load_manifest())

    def test_wrong_row_count_and_observation_date_fail(self) -> None:
        one_row = self.exo(
            "NIRSPEC_G395H_NRS2,ExoTEP,uniform,0,3.832,3.83,3.834,0,0,3000,10,12,0,0,0,none\n"
        )
        with self.assertRaisesRegex(DataError, "expected 2 rows"):
            load_spectrum(self.path(one_row), spec("exoTEDRF"), load_manifest())
        wrong_date = self.exo().replace("2024-05-28", "2024-05-29")
        with self.assertRaisesRegex(DataError, "date does not match"):
            load_spectrum(self.path(wrong_date), spec("exoTEDRF"), load_manifest())


if __name__ == "__main__":
    unittest.main()
