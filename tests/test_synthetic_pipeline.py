from __future__ import annotations

import inspect
import unittest
from dataclasses import replace

import numpy as np

import synthetic_atmosphere_benchmark.evaluator as evaluator_module
from synthetic_atmosphere_benchmark.canonical import canonical_json_text
from synthetic_atmosphere_benchmark.challenge import ChallengeBundle, ChallengeCase, ChallengeError
from synthetic_atmosphere_benchmark.evaluator import equivalent_predictions, evaluate_challenge
from synthetic_atmosphere_benchmark.generator import generate_public_suite, within_detector_ar1_covariance
from synthetic_atmosphere_benchmark.manifest import load_manifest
from synthetic_atmosphere_benchmark.scorer import ScoringError, score_predictions
from synthetic_atmosphere_benchmark.source import Scaffold


def _project(template: np.ndarray, nuisance: np.ndarray, uncertainty: np.ndarray) -> np.ndarray:
    weights = 1.0 / np.square(uncertainty)
    beta = np.linalg.solve(nuisance.T @ (weights[:, None] * nuisance), nuisance.T @ (weights * template))
    residual = template - nuisance @ beta
    return residual / np.sqrt(residual @ (weights * residual))


def _scaffold() -> Scaffold:
    wavelength = np.concatenate((np.linspace(2.9, 3.7, 8), np.linspace(3.9, 5.1, 8)))
    width = np.full(wavelength.size, 0.04)
    uncertainty = np.linspace(18.0, 24.0, wavelength.size)
    detector = wavelength >= 3.8
    trend = wavelength - np.average(wavelength, weights=1.0 / uncertainty**2)
    trend /= np.ptp(wavelength)
    nuisance = np.column_stack((np.ones(wavelength.size), trend, detector.astype(float)))
    planet = _project(np.sin(wavelength * 4.1), nuisance, uncertainty)
    stellar = _project(np.cos(wavelength * 2.7 + 0.3), nuisance, uncertainty)
    return Scaffold(wavelength, width, uncertainty, detector, planet, stellar, nuisance)


def _challenge(planet_coefficient: float, stellar_coefficient: float) -> ChallengeBundle:
    scaffold = _scaffold()
    beta = np.asarray([1300.0, 30.0, 20.0])
    depth = (
        scaffold.nuisance_design @ beta
        + planet_coefficient * scaffold.planet_template_ppm
        + stellar_coefficient * scaffold.stellar_template_ppm
    )
    return ChallengeBundle(
        schema_version=1,
        benchmark_id="unit",
        contract_sha256="0" * 64,
        depth_unit="ppm",
        wavelength_unit="micrometre",
        wavelength=tuple(scaffold.wavelength_um),
        bin_width=tuple(scaffold.bin_width_um),
        uncertainty=tuple(scaffold.uncertainty_ppm),
        detector_split=3.8,
        planet_template=tuple(scaffold.planet_template_ppm),
        stellar_template=tuple(scaffold.stellar_template_ppm),
        cases=(ChallengeCase("opaque", tuple(depth), "diagonal", 0.0),),
    )


class SyntheticPipelineTests(unittest.TestCase):
    def test_evaluator_recovers_signed_amplitudes_without_truth(self) -> None:
        challenge = _challenge(6.0, -4.0)
        result = evaluate_challenge(challenge)
        parameters = result["cases"][0]["modes"]["correct_covariance"]["full_model"]["parameters"]
        self.assertAlmostEqual(parameters["planet"]["estimate"], 6.0, places=9)
        self.assertAlmostEqual(parameters["stellar"]["estimate"], -4.0, places=9)
        self.assertEqual(result["cases"][0]["modes"]["correct_covariance"]["classification"], "planetary_supported")
        source = inspect.getsource(evaluator_module)
        self.assertNotIn("from .truth", source)
        self.assertNotIn("from .generator", source)
        self.assertEqual(list(inspect.signature(evaluate_challenge).parameters), ["challenge", "promotion_z"])

    def test_negative_and_null_coefficients_do_not_promote(self) -> None:
        for coefficients in ((0.0, 0.0), (-8.0, 0.0), (0.0, -8.0)):
            result = evaluate_challenge(_challenge(*coefficients))
            classification = result["cases"][0]["modes"]["correct_covariance"]["classification"]
            self.assertNotIn(classification, {"planetary_supported", "stellar_supported", "joint_supported"})

    def test_units_and_input_order_are_invariant(self) -> None:
        base = _challenge(6.0, 0.0)
        second = replace(base.cases[0], case_id="opaque-2")
        base = replace(base, cases=(base.cases[0], second))
        expected = evaluate_challenge(base)
        scaled = replace(
            base,
            depth_unit="fraction",
            wavelength_unit="nanometre",
            wavelength=tuple(value * 1000 for value in base.wavelength),
            bin_width=tuple(value * 1000 for value in base.bin_width),
            detector_split=base.detector_split * 1000,
            uncertainty=tuple(value * 1e-6 for value in base.uncertainty),
            planet_template=tuple(value * 1e-6 for value in base.planet_template),
            stellar_template=tuple(value * 1e-6 for value in base.stellar_template),
            cases=tuple(
                replace(case, synthetic_depth=tuple(value * 1e-6 for value in case.synthetic_depth))
                for case in reversed(base.cases)
            ),
        )
        self.assertTrue(equivalent_predictions(expected, evaluate_challenge(scaled)))

    def test_per_case_streams_and_outputs_ignore_family_loop_order(self) -> None:
        manifest = load_manifest()
        scaffold = _scaffold()
        challenge_a, truth_a = generate_public_suite(manifest, scaffold)
        challenge_b, truth_b = generate_public_suite(manifest, scaffold, family_order=tuple(reversed(manifest.families)))
        self.assertEqual(canonical_json_text(challenge_a.to_dict()), canonical_json_text(challenge_b.to_dict()))
        self.assertEqual(canonical_json_text(truth_a.to_dict()), canonical_json_text(truth_b.to_dict()))
        public = challenge_a.to_dict()
        public_text = canonical_json_text(public)
        self.assertNotIn('"family"', public_text)
        self.assertNotIn('"spawn_key"', public_text)
        for case in challenge_a.cases[:20]:
            self.assertFalse(any(family in case.case_id for family in manifest.families))

    def test_covariance_is_block_ar1_and_positive_definite(self) -> None:
        uncertainty = np.asarray([2.0, 3.0, 4.0, 5.0])
        detector = np.asarray([False, False, True, True])
        covariance = within_detector_ar1_covariance(uncertainty, detector, 0.5)
        self.assertEqual(covariance[0, 2], 0.0)
        self.assertAlmostEqual(covariance[0, 1], 3.0)
        np.linalg.cholesky(covariance)

    def test_scoring_counts_evaluation_failures_in_frozen_denominators(self) -> None:
        manifest = load_manifest()
        challenge, truth = generate_public_suite(manifest, _scaffold())
        predictions = evaluate_challenge(challenge)
        predictions["cases"][0]["status"] = "error"
        predictions["cases"][0]["error"] = "deliberate test failure"
        predictions["cases"][0]["modes"] = {}
        score = score_predictions(
            manifest,
            truth,
            predictions,
            invariance_checks={
                "deterministic_generation": True,
                "fraction_unit_invariance": True,
                "order_invariance": True,
                "percent_nanometre_unit_invariance": True,
            },
        )
        metrics = score["metrics"]["correct_covariance"]
        self.assertEqual(metrics["evaluation_errors"], 1)
        self.assertEqual(sum(item["scheduled"] for item in metrics["family_metrics"].values()), 648)
        self.assertEqual(score["engineering_preflight_status"], "INCOMPLETE")

    def test_scorer_rejects_invariance_collision_and_contract_forgery(self) -> None:
        manifest = load_manifest()
        challenge, truth = generate_public_suite(manifest, _scaffold())
        predictions = evaluate_challenge(challenge, promotion_z=manifest.promotion_z)
        invariance = {
            "deterministic_generation": True,
            "fraction_unit_invariance": True,
            "order_invariance": True,
            "percent_nanometre_unit_invariance": True,
        }
        with self.assertRaisesRegex(ScoringError, "exact frozen boolean key set"):
            score_predictions(
                manifest,
                truth,
                predictions,
                invariance_checks={**invariance, "pooled_unsafe_specific_classification": True},
            )
        forged = dict(predictions)
        forged["contract_sha256"] = "0" * 64
        with self.assertRaisesRegex(ScoringError, "frozen manifest"):
            score_predictions(manifest, truth, forged, invariance_checks=invariance)
        wrong_threshold = dict(predictions)
        wrong_threshold["promotion_z"] = 4.0
        with self.assertRaisesRegex(ScoringError, "frozen manifest"):
            score_predictions(manifest, truth, wrong_threshold, invariance_checks=invariance)

    def test_challenge_schema_rejects_nonfinite_and_nonpositive_values(self) -> None:
        base = _challenge(0.0, 0.0)
        with self.assertRaisesRegex(ChallengeError, "positive"):
            replace(base, uncertainty=tuple(0.0 for _ in base.uncertainty)).validate()
        bad_case = replace(base.cases[0], synthetic_depth=(float("nan"),) + base.cases[0].synthetic_depth[1:])
        with self.assertRaisesRegex(ChallengeError, "nonfinite"):
            replace(base, cases=(bad_case,)).validate()


if __name__ == "__main__":
    unittest.main()
