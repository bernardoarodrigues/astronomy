from __future__ import annotations

import unittest
from dataclasses import replace

import numpy as np

from gj486_benchmark.analysis import (
    assess_science_state,
    assess_sensitivity,
    canonical_json_text,
    classify_feature,
    detector_common_mode_covariance,
    fit_stellar_evidence,
    fit_water_pair,
    miri_fixed_model_ranking,
    publisher_hanning_smooth,
    within_detector_ar1_covariance,
)
from gj486_benchmark.data import EclipseSpectrum, NumericModel, StellarGroup
from gj486_benchmark.manifest import load_manifest


class GJ486AnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.template = np.linspace(-100.0, 100.0, 40)
        self.detector = np.arange(40) >= 20
        self.uncertainty = np.full(40, 10.0)

    def test_signed_amplitude_recovery_and_negative_behavior(self) -> None:
        for amplitude in (0.7, -0.4, 0.0):
            with self.subTest(amplitude=amplitude):
                values = 1300.0 + amplitude * self.template
                result = fit_water_pair(
                    values,
                    self.uncertainty,
                    self.template,
                    self.detector,
                    include_step=False,
                )
                self.assertAlmostEqual(result["amplitude"], amplitude, places=12)
                if amplitude < 0:
                    self.assertLess(result["z"], 0)

    def test_detector_step_and_unit_invariance(self) -> None:
        values = 1300.0 + 25.0 * self.detector + 0.6 * self.template
        primary = fit_water_pair(values, self.uncertainty, self.template, self.detector, include_step=True)
        for scale in (1.0, 1e-6, 1e-4):
            result = fit_water_pair(
                values * scale,
                self.uncertainty * scale,
                self.template * scale,
                self.detector,
                include_step=True,
            )
            self.assertAlmostEqual(result["amplitude"], primary["amplitude"], places=11)
            self.assertAlmostEqual(result["z"], primary["z"], places=9)
            self.assertAlmostEqual(result["delta_chi2"], primary["delta_chi2"], places=9)

    def test_assumed_covariance_structures(self) -> None:
        ar1 = within_detector_ar1_covariance(self.uncertainty, self.detector, 0.5)
        self.assertTrue(np.all(np.linalg.eigvalsh(ar1) > 0))
        self.assertEqual(ar1[0, 20], 0)
        self.assertAlmostEqual(ar1[0, 1], 50.0)
        common = detector_common_mode_covariance(self.uncertainty, self.detector, 20.0)
        self.assertEqual(common[0, 1], 400.0)
        self.assertEqual(common[0, 20], 0.0)
        self.assertEqual(common[0, 0], 500.0)

    def test_feature_classifier_uses_fingerprints_not_correlated_votes(self) -> None:
        result = {
            name: {"regression_fingerprint": {"passed": True}}
            for name in ("Eureka", "Firefly", "Tiberius")
        }
        self.assertEqual(
            classify_feature(result),
            "retrospective_template_regression_reproduced",
        )
        result["Firefly"]["regression_fingerprint"]["passed"] = False
        self.assertEqual(classify_feature(result), "regression_fingerprint_mismatch")

    def test_sensitivity_assessment_surfaces_each_diagnostic(self) -> None:
        def reduction(*, detector_negative: bool = False):
            return {
                "primary": {
                    "no_step": {"z": 3.5},
                    "step": {"z": 3.2},
                },
                "leave_one_bin_out": {"minimum_no_step_z": 2.2, "minimum_step_z": 3.1},
                "covariance_stress": {
                    "models": [{"fits": {"no_step": {"z": 3.1}, "step": {"z": 1.9}}}]
                },
                "affine_baseline_stress": {
                    "fits": {"no_step": {"z": 2.6}, "step": {"z": 3.1}}
                },
                "detector_side_deletions": {
                    "fits": {
                        "nrs1_only": {"amplitude": 1.0},
                        "nrs2_only": {"amplitude": -0.1 if detector_negative else 0.2},
                    }
                },
            }

        assessment = assess_sensitivity({"Eureka": reduction(detector_negative=True)})
        self.assertTrue(all(assessment["flags"].values()))
        self.assertFalse(assessment["gating"])

    def test_science_state_fails_closed_without_direct_origin_comparison(self) -> None:
        assessment = assess_science_state(
            "robust_spectral_feature",
            {"classification": "stellar_heterogeneity_clue"},
            {"classification": "specific_thick_water_model_disfavored"},
        )
        self.assertEqual(assessment["state"], "science_unresolved")
        self.assertEqual(assessment["origin_comparison_status"], "not_evaluated")
        self.assertFalse(assessment["resolution_attempted"])
        self.assertIn("planet-versus-star", assessment["reason"])

    def test_publisher_smoothing_and_canonical_json_are_deterministic(self) -> None:
        values = np.linspace(0, 1, 200)
        first = publisher_hanning_smooth(values)
        second = publisher_hanning_smooth(values)
        np.testing.assert_array_equal(first, second)
        self.assertEqual(first.shape, values.shape)
        self.assertEqual(canonical_json_text({"b": 1, "a": 2}), '{\n  "a": 2,\n  "b": 1\n}\n')

    def test_stellar_m3_ranking_with_identical_nuisance(self) -> None:
        wavelength = np.linspace(3.0, 5.0, 30)
        m3 = 100 + 10 * np.sin(wavelength)
        m1 = 100 + 10 * np.cos(wavelength)
        m2 = 100 + 5 * np.sin(2 * wavelength)
        groups = {
            "V1": StellarGroup("V1", wavelength, 1.02 * m3, np.ones(30)),
            "V2": StellarGroup("V2", wavelength, 0.98 * m3, np.ones(30)),
            "M1": StellarGroup("M1", wavelength, m1, None),
            "M2": StellarGroup("M2", wavelength, m2, None),
            "M3": StellarGroup("M3", wavelength, m3, None),
        }
        result = fit_stellar_evidence(groups)
        self.assertTrue(result["passed"])
        self.assertTrue(all(item["m3_ranks_above_m1"] for item in result["visits"].values()))
        self.assertFalse(result["direct_transit_contamination_fit"])

    def test_miri_fixed_models_have_no_fitted_offset_or_normalization(self) -> None:
        wavelength = np.linspace(5.0, 12.0, 22)
        spectrum = EclipseSpectrum(wavelength, np.full(22, 100.0), np.full(22, 10.0))
        model_wavelength = np.linspace(4.0, 13.0, 500)
        models = {
            "blackbody_824k": NumericModel(model_wavelength, np.full(500, 100e-6)),
            "ultramafic": NumericModel(model_wavelength, np.full(500, 110e-6)),
            "pure_h2o_1bar": NumericModel(model_wavelength, np.full(500, 200e-6)),
        }
        manifest = load_manifest()
        analysis = {
            **manifest.external_constraint.analysis,
            "expected_chi2_per_point": {
                "blackbody_824k": 0.0,
                "ultramafic": 1.0,
                "pure_h2o_1bar": 100.0,
            },
            "fingerprint_tolerance": 1e-10,
        }
        external = replace(manifest.external_constraint, analysis=analysis)
        result = miri_fixed_model_ranking(spectrum, models, replace(manifest, external_constraint=external))
        self.assertTrue(result["passed"])
        self.assertFalse(result["normalization_or_offset_fitted"])
        self.assertEqual(result["ranking_best_to_worst"][0], "blackbody_824k")
        self.assertEqual(result["classification"], "specific_thick_water_model_disfavored")


if __name__ == "__main__":
    unittest.main()
