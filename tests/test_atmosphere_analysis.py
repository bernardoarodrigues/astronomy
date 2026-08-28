from __future__ import annotations

import unittest

import numpy as np

from atmosphere_benchmark.analysis import (
    canonical_json_text,
    design_matrix,
    fit_models,
    null_calibration,
)


class AtmosphereAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.wavelength = np.linspace(4.1, 4.6, 20)
        self.uncertainty = np.full(20, 0.0001)
        self.m0 = 0.021 + 0.0003 * (self.wavelength - 4.3)
        self.feature = np.exp(-0.5 * ((self.wavelength - 4.3) / 0.1) ** 2)

    def test_recovers_signed_positive_amplitude(self) -> None:
        expected = 0.0015
        _, _, metrics = fit_models(
            self.wavelength,
            self.m0 + expected * self.feature,
            self.uncertainty,
        )
        self.assertAlmostEqual(metrics["amplitude"], expected, places=12)
        self.assertGreater(metrics["z"], 0)

    def test_null_and_negative_amplitudes_preserve_sign(self) -> None:
        _, _, null = fit_models(self.wavelength, self.m0, self.uncertainty)
        _, _, negative = fit_models(
            self.wavelength,
            self.m0 - 0.001 * self.feature,
            self.uncertainty,
        )
        self.assertAlmostEqual(null["amplitude"], 0.0, places=12)
        self.assertAlmostEqual(null["z"], 0.0, places=10)
        self.assertLess(negative["amplitude"], 0)
        self.assertLess(negative["z"], 0)

    def test_ppm_scaling_preserves_z_and_delta_chi2(self) -> None:
        values = self.m0 + 0.0015 * self.feature
        _, _, absolute = fit_models(self.wavelength, values, self.uncertainty)
        _, _, ppm = fit_models(
            self.wavelength,
            values * 1e6,
            self.uncertainty * 1e6,
        )
        self.assertAlmostEqual(absolute["z"], ppm["z"], places=10)
        self.assertAlmostEqual(
            absolute["delta_chi2"], ppm["delta_chi2"], places=10
        )

    def test_null_calibration_and_json_are_deterministic(self) -> None:
        fitted_m0 = design_matrix(
            self.wavelength,
            pivot=4.3,
            feature_sigma=0.1,
            include_feature=False,
        ) @ np.array([0.021, 0.0003])
        first = null_calibration(
            self.wavelength,
            self.uncertainty,
            fitted_m0,
            pivot=4.3,
            feature_sigma=0.1,
            draws=1000,
            seed=6959427,
        )
        second = null_calibration(
            self.wavelength,
            self.uncertainty,
            fitted_m0,
            pivot=4.3,
            feature_sigma=0.1,
            draws=1000,
            seed=6959427,
        )
        self.assertEqual(first, second)
        self.assertEqual(
            canonical_json_text({"z": 1, "a": 2}),
            '{\n  "a": 2,\n  "z": 1\n}\n',
        )


if __name__ == "__main__":
    unittest.main()
