from __future__ import annotations

import json
import unittest
from dataclasses import replace

import numpy as np

from k218_repeatability.analysis import (
    AnalysisError,
    analyze_spectra,
    build_global_grid,
    classify_outcome,
    fit_contrast,
    native_covariance,
    overlap_weight_matrix,
    paired_reduction_differences,
    rebin_spectrum,
)
from k218_repeatability.data import VisitSpectrum
from k218_repeatability.manifest import load_manifest


def synthetic_spectrum(
    reduction: str = "Eureka",
    visit: str = "visit_2",
    *,
    amplitude_ppm: float = 100.0,
    sigma_ppm: float = 20.0,
    lower_bound: float = 3.83,
    upper_bound: float = 4.73,
) -> VisitSpectrum:
    step = 0.01
    edges = np.arange(lower_bound, upper_bound + step / 2, step)
    lower = edges[:-1]
    upper = edges[1:]
    wave = (lower + upper) / 2
    depth = 3000.0 + amplitude_ppm * ((wave >= 4.05) & (wave < 4.55))
    sigma = np.full_like(wave, sigma_ppm)
    return VisitSpectrum(
        reduction=reduction,
        visit=visit,
        detector="NRS2",
        wavelength_micrometres=wave,
        lower_micrometres=lower,
        upper_micrometres=upper,
        depth_ppm=depth,
        uncertainty_ppm=sigma,
        source_error_low_ppm=sigma,
        source_error_high_ppm=sigma,
        source_metadata={"synthetic": "true"},
    )


def passed_cell(reduction: str, visit: str, *, z: float = 3.0) -> dict:
    return {
        "reduction": reduction,
        "visit": visit,
        "nominal": {"valid": True, "amplitude_ppm": 10.0, "amplitude_se_ppm": 10.0 / z},
        "criterion_checks": {"cell_passed": True},
    }


class K218AnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = load_manifest()
        self.grid = build_global_grid(self.manifest)

    def test_global_grid_hash_edges_and_feature_overlap(self) -> None:
        self.assertEqual(len(self.grid.edges_micrometres), 21)
        self.assertEqual(
            self.grid.edge_sha256,
            "7f7e418fc0bfde1478d7ade8a4fef0f774bc7bb0f3046a918be7bc763d3b2d28",
        )
        self.assertTrue(np.all(self.grid.edges_micrometres[:-1] >= 3.85))
        self.assertTrue(np.all(self.grid.edges_micrometres[1:] <= 4.75))
        partial = self.grid.feature_overlap_fraction[
            (self.grid.feature_overlap_fraction > 0) & (self.grid.feature_overlap_fraction < 1)
        ]
        self.assertEqual(partial.size, 2)

    def test_overlap_inverse_variance_weights_and_covariance_propagation(self) -> None:
        spectrum = synthetic_spectrum()
        spectrum = replace(
            spectrum,
            uncertainty_ppm=np.linspace(10.0, 30.0, spectrum.uncertainty_ppm.size),
            source_error_low_ppm=np.linspace(10.0, 30.0, spectrum.uncertainty_ppm.size),
            source_error_high_ppm=np.linspace(10.0, 30.0, spectrum.uncertainty_ppm.size),
        )
        weights, overlap, coverage = overlap_weight_matrix(spectrum, self.grid, self.manifest)
        self.assertTrue(np.allclose(weights.sum(axis=1), 1.0, rtol=0, atol=1e-14))
        self.assertTrue(np.all(weights[overlap == 0] == 0))
        self.assertTrue(np.allclose(coverage, 1.0, rtol=0, atol=1e-12))
        first = 0
        used = overlap[first] > 0
        raw = overlap[first, used] / spectrum.uncertainty_ppm[used] ** 2
        np.testing.assert_allclose(weights[first, used], raw / raw.sum(), rtol=1e-14, atol=0)
        native = native_covariance(spectrum)
        rebinned = rebin_spectrum(spectrum, self.grid, self.manifest, covariance_native=native)
        expected = np.einsum("ji,ik,lk->jl", weights, native, weights, optimize=False)
        np.testing.assert_allclose(rebinned.covariance_ppm2, expected)

    def test_partial_native_coverage_is_rejected_without_clipping(self) -> None:
        spectrum = synthetic_spectrum(lower_bound=4.0)
        with self.assertRaisesRegex(AnalysisError, "lacks full native coverage"):
            rebin_spectrum(spectrum, self.grid, self.manifest)

    def test_signed_full_gls_recovers_positive_and_negative_amplitudes(self) -> None:
        for amplitude in (125.0, -80.0):
            spectrum = synthetic_spectrum(amplitude_ppm=amplitude, sigma_ppm=10.0)
            rebinned = rebin_spectrum(spectrum, self.grid, self.manifest)
            fit = fit_contrast(
                self.grid.centres_micrometres,
                rebinned.depth_ppm,
                rebinned.covariance_ppm2,
                self.grid.feature_overlap_fraction,
            )
            self.assertAlmostEqual(fit.beta[2], amplitude, places=8)
            self.assertEqual(fit.design_rank, 3)
            self.assertTrue(np.isfinite(fit.normal_condition_number))

    def test_outcome_is_positive_only_when_every_cell_passes(self) -> None:
        cells = [
            passed_cell("Eureka", "visit_2"),
            passed_cell("Eureka", "visit_3"),
            passed_cell("exoTEDRF", "visit_2"),
            passed_cell("exoTEDRF", "visit_3"),
        ]
        self.assertEqual(classify_outcome(cells)["state"], "repeatable_positive_morphology")
        cells[0]["criterion_checks"]["cell_passed"] = False
        unresolved = classify_outcome(cells)
        self.assertEqual(unresolved["state"], "SCIENCE_UNRESOLVED")
        self.assertEqual(unresolved["reason"], "criterion_not_met")
        self.assertNotIn("not_repeatable", json.dumps(unresolved).lower())
        self.assertEqual(classify_outcome(cells[:-1])["state"], "SCIENCE_UNRESOLVED")

    def test_paired_reduction_delta_has_no_significance(self) -> None:
        cells = [
            passed_cell("Eureka", "visit_2"),
            passed_cell("Eureka", "visit_3"),
            passed_cell("exoTEDRF", "visit_2"),
            passed_cell("exoTEDRF", "visit_3"),
        ]
        paired = paired_reduction_differences(cells)
        self.assertEqual(len(paired), 2)
        self.assertTrue(all(item["independent_reduction"] is False for item in paired))
        self.assertTrue(all(item["significance"].startswith("not_evaluated") for item in paired))
        self.assertFalse(any("z" in item for item in paired))

    def test_analysis_is_order_deterministic_and_non_promotional(self) -> None:
        spectra = [
            ("eureka_visit_2_nrs2", synthetic_spectrum("Eureka", "visit_2", amplitude_ppm=100)),
            ("eureka_visit_3_nrs2", synthetic_spectrum("Eureka", "visit_3", amplitude_ppm=110)),
            ("exotedrf_visit_2_nrs2", synthetic_spectrum("exoTEDRF", "visit_2", amplitude_ppm=95)),
            ("exotedrf_visit_3_nrs2", synthetic_spectrum("exoTEDRF", "visit_3", amplitude_ppm=105)),
        ]
        first = analyze_spectra(spectra, self.manifest)
        second = analyze_spectra(list(reversed(spectra)), self.manifest)
        self.assertEqual(
            json.dumps(first, sort_keys=True, separators=(",", ":")),
            json.dumps(second, sort_keys=True, separators=(",", ":")),
        )
        evidence = first["evidence_combination"]
        self.assertFalse(evidence["independent_reduction"])
        self.assertEqual(evidence["cross_reduction_z_combination"], "prohibited_not_computed")
        self.assertNotIn("3.3", json.dumps(first))


if __name__ == "__main__":
    unittest.main()
