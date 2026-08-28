from __future__ import annotations

import json
import os
import platform
import tempfile
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any

import numpy as np

from .data import (
    EclipseSpectrum,
    NumericModel,
    StellarGroup,
    TransmissionSpectrum,
    load_stellar_groups,
    load_miri_atmosphere_model,
    load_miri_blackbody_model,
    load_miri_spectrum,
    load_transmission_spectra,
    load_water_model,
)
from .integrity import verify_member
from .manifest import GJ486Manifest


class AnalysisError(RuntimeError):
    """Raised when the frozen GJ 486 b analysis cannot be completed."""


@dataclass(frozen=True)
class LinearFit:
    beta: np.ndarray
    covariance: np.ndarray
    chi2: float
    dof: int


def weighted_linear_fit(
    design: np.ndarray,
    values: np.ndarray,
    *,
    uncertainties: np.ndarray | None = None,
    covariance: np.ndarray | None = None,
) -> LinearFit:
    design = np.asarray(design, dtype=np.float64)
    values = np.asarray(values, dtype=np.float64)
    if design.ndim != 2 or values.ndim != 1 or design.shape[0] != values.size:
        raise AnalysisError("design and data dimensions do not agree")
    if (uncertainties is None) == (covariance is None):
        raise AnalysisError("provide exactly one of uncertainties or covariance")
    try:
        if covariance is not None:
            covariance = np.asarray(covariance, dtype=np.float64)
            if covariance.shape != (values.size, values.size) or not np.all(np.isfinite(covariance)):
                raise AnalysisError("covariance must be finite and match the data")
            cholesky = np.linalg.cholesky(covariance)
            whitened_design = np.linalg.solve(cholesky, design)
            whitened_values = np.linalg.solve(cholesky, values)
        else:
            uncertainties = np.asarray(uncertainties, dtype=np.float64)
            if uncertainties.shape != values.shape or not np.all(np.isfinite(uncertainties)) or not np.all(uncertainties > 0):
                raise AnalysisError("uncertainties must be finite, positive, and match the data")
            whitened_design = design / uncertainties[:, None]
            whitened_values = values / uncertainties
        normal = whitened_design.T @ whitened_design
        parameter_covariance = np.linalg.inv(normal)
        beta = np.linalg.solve(normal, whitened_design.T @ whitened_values)
        residual = whitened_values - whitened_design @ beta
    except np.linalg.LinAlgError as exc:
        raise AnalysisError(f"weighted fit is singular or non-positive-definite: {exc}") from exc
    if not all(np.all(np.isfinite(item)) for item in (beta, parameter_covariance, residual)):
        raise AnalysisError("weighted fit produced nonfinite results")
    return LinearFit(beta, parameter_covariance, float(residual @ residual), int(values.size - design.shape[1]))


def interpolate_centered_template(
    wavelength: np.ndarray,
    uncertainty: np.ndarray,
    water_model: NumericModel,
) -> tuple[np.ndarray, float]:
    wavelength = np.asarray(wavelength, dtype=np.float64)
    uncertainty = np.asarray(uncertainty, dtype=np.float64)
    if wavelength[0] < water_model.wavelength[0] or wavelength[-1] > water_model.wavelength[-1]:
        raise AnalysisError("water model does not cover every observed wavelength")
    raw_ppm = np.interp(wavelength, water_model.wavelength, water_model.values) * 1_000_000.0
    centre = float(np.average(raw_ppm, weights=uncertainty**-2))
    return raw_ppm - centre, centre


def _design(
    template: np.ndarray,
    detector: np.ndarray,
    *,
    include_step: bool,
    include_water: bool,
    wavelength_trend: np.ndarray | None = None,
) -> np.ndarray:
    columns = [np.ones(template.size)]
    if include_step:
        columns.append(detector.astype(np.float64))
    if wavelength_trend is not None:
        columns.append(np.asarray(wavelength_trend, dtype=np.float64))
    if include_water:
        columns.append(template)
    return np.column_stack(columns)


def fit_water_pair(
    values: np.ndarray,
    uncertainties: np.ndarray,
    template: np.ndarray,
    detector: np.ndarray,
    *,
    include_step: bool,
    covariance: np.ndarray | None = None,
    wavelength_trend: np.ndarray | None = None,
) -> dict[str, Any]:
    null_design = _design(
        template,
        detector,
        include_step=include_step,
        include_water=False,
        wavelength_trend=wavelength_trend,
    )
    water_design = _design(
        template,
        detector,
        include_step=include_step,
        include_water=True,
        wavelength_trend=wavelength_trend,
    )
    kwargs = {"covariance": covariance} if covariance is not None else {"uncertainties": uncertainties}
    null = weighted_linear_fit(null_design, values, **kwargs)
    water = weighted_linear_fit(water_design, values, **kwargs)
    amplitude = float(water.beta[-1])
    amplitude_se = float(np.sqrt(water.covariance[-1, -1]))
    return {
        "amplitude": amplitude,
        "amplitude_se": amplitude_se,
        "z": amplitude / amplitude_se,
        "chi2_null": null.chi2,
        "chi2_water": water.chi2,
        "delta_chi2": null.chi2 - water.chi2,
        "dof_null": null.dof,
        "dof_water": water.dof,
        "null_parameters": [float(value) for value in null.beta],
        "water_parameters": [float(value) for value in water.beta],
    }


def within_detector_ar1_covariance(
    uncertainties: np.ndarray,
    detector: np.ndarray,
    rho: float,
) -> np.ndarray:
    uncertainties = np.asarray(uncertainties, dtype=np.float64)
    detector = np.asarray(detector, dtype=bool)
    if not 0 <= rho < 1:
        raise AnalysisError("AR(1) rho must be in [0, 1)")
    correlation = np.zeros((uncertainties.size, uncertainties.size), dtype=np.float64)
    for side in (False, True):
        indices = np.flatnonzero(detector == side)
        local_separation = np.abs(np.arange(indices.size)[:, None] - np.arange(indices.size)[None, :])
        correlation[np.ix_(indices, indices)] = rho**local_separation
    return np.outer(uncertainties, uncertainties) * correlation


def detector_common_mode_covariance(
    uncertainties: np.ndarray,
    detector: np.ndarray,
    common_mode_ppm: float,
) -> np.ndarray:
    uncertainties = np.asarray(uncertainties, dtype=np.float64)
    detector = np.asarray(detector, dtype=bool)
    if common_mode_ppm < 0:
        raise AnalysisError("detector common mode must be nonnegative")
    covariance = np.diag(uncertainties**2)
    for side in (False, True):
        indices = np.flatnonzero(detector == side)
        covariance[np.ix_(indices, indices)] += common_mode_ppm**2
    return covariance


def _fit_both(
    values: np.ndarray,
    uncertainties: np.ndarray,
    template: np.ndarray,
    detector: np.ndarray,
    covariance: np.ndarray | None = None,
) -> dict[str, Any]:
    return {
        "no_step": fit_water_pair(values, uncertainties, template, detector, include_step=False, covariance=covariance),
        "step": fit_water_pair(values, uncertainties, template, detector, include_step=True, covariance=covariance),
    }


def _analyze_reduction(
    spectrum: TransmissionSpectrum,
    water_model: NumericModel,
    manifest: GJ486Manifest,
) -> tuple[dict[str, Any], TransmissionSpectrum, np.ndarray]:
    spec = manifest.analysis
    filtered = spectrum.subset(spectrum.wavelength >= spec.minimum_wavelength_micrometres)
    expected_rows = spec.expected_filtered_rows[spectrum.reduction]
    if filtered.wavelength.size != expected_rows:
        raise AnalysisError(f"{spectrum.reduction} expected {expected_rows} filtered rows, found {filtered.wavelength.size}")
    detector = filtered.wavelength >= spec.detector_split_micrometres
    if not np.any(~detector) or not np.any(detector):
        raise AnalysisError(f"{spectrum.reduction} does not retain both detector sides")
    template, template_centre = interpolate_centered_template(filtered.wavelength, filtered.uncertainty_ppm, water_model)
    primary = _fit_both(filtered.depth_ppm, filtered.uncertainty_ppm, template, detector)
    wavelength_trend = filtered.wavelength - float(
        np.average(filtered.wavelength, weights=filtered.uncertainty_ppm**-2)
    )
    affine_baseline = {
        "no_step": fit_water_pair(
            filtered.depth_ppm,
            filtered.uncertainty_ppm,
            template,
            detector,
            include_step=False,
            wavelength_trend=wavelength_trend,
        ),
        "step": fit_water_pair(
            filtered.depth_ppm,
            filtered.uncertainty_ppm,
            template,
            detector,
            include_step=True,
            wavelength_trend=wavelength_trend,
        ),
    }

    target = spec.expected_z[spectrum.reduction]
    fingerprint_checks = {
        key: {
            "expected_z": target[key],
            "observed_z": primary[key]["z"],
            "absolute_difference": abs(primary[key]["z"] - target[key]),
            "tolerance": spec.z_tolerance,
            "passed": abs(primary[key]["z"] - target[key]) <= spec.z_tolerance,
        }
        for key in ("no_step", "step")
    }
    fingerprint_passed = all(item["passed"] for item in fingerprint_checks.values())

    leave_one_out = []
    for omitted in range(filtered.wavelength.size):
        keep = np.arange(filtered.wavelength.size) != omitted
        fits = _fit_both(
            filtered.depth_ppm[keep],
            filtered.uncertainty_ppm[keep],
            template[keep],
            detector[keep],
        )
        leave_one_out.append(
            {
                "omitted_index": omitted,
                "omitted_wavelength_micrometres": float(filtered.wavelength[omitted]),
                "no_step_amplitude": fits["no_step"]["amplitude"],
                "no_step_z": fits["no_step"]["z"],
                "step_amplitude": fits["step"]["amplitude"],
                "step_z": fits["step"]["z"],
            }
        )

    detector_deletions: dict[str, Any] = {}
    for name, keep in (("nrs1_only", ~detector), ("nrs2_only", detector)):
        detector_deletions[name] = fit_water_pair(
            filtered.depth_ppm[keep],
            filtered.uncertainty_ppm[keep],
            template[keep],
            detector[keep],
            include_step=False,
        )
        detector_deletions[name]["rows"] = int(np.count_nonzero(keep))

    unit_results: dict[str, Any] = {}
    max_z_difference = 0.0
    max_delta_difference = 0.0
    for name, scale in (("fraction", 1e-6), ("ppm", 1.0), ("percent", 1e-4)):
        fits = _fit_both(
            filtered.depth_ppm * scale,
            filtered.uncertainty_ppm * scale,
            template * scale,
            detector,
        )
        unit_results[name] = fits
        for model_name in ("no_step", "step"):
            max_z_difference = max(max_z_difference, abs(fits[model_name]["z"] - primary[model_name]["z"]))
            max_delta_difference = max(max_delta_difference, abs(fits[model_name]["delta_chi2"] - primary[model_name]["delta_chi2"]))
    invariance_passed = max(max_z_difference, max_delta_difference) <= spec.unit_invariance_tolerance

    stresses = []
    stress_spec = spec.covariance_stress
    for rho in sorted(float(item) for item in stress_spec["within_detector_ar1_rho"]):
        covariance = within_detector_ar1_covariance(filtered.uncertainty_ppm, detector, rho)
        stresses.append({"kind": "within_detector_ar1", "rho": rho, "fits": _fit_both(filtered.depth_ppm, filtered.uncertainty_ppm, template, detector, covariance)})
    for common_mode in sorted(float(item) for item in stress_spec["detector_common_mode_ppm"]):
        covariance = detector_common_mode_covariance(filtered.uncertainty_ppm, detector, common_mode)
        stresses.append({"kind": "detector_common_mode", "common_mode_ppm": common_mode, "fits": _fit_both(filtered.depth_ppm, filtered.uncertainty_ppm, template, detector, covariance)})

    result = {
        "rows": int(filtered.wavelength.size),
        "wavelength_range_micrometres": [float(filtered.wavelength[0]), float(filtered.wavelength[-1])],
        "detector_rows": {"nrs1": int(np.count_nonzero(~detector)), "nrs2": int(np.count_nonzero(detector))},
        "largest_adjacent_gap_micrometres": float(np.max(np.diff(filtered.wavelength))),
        "template_weighted_centre_ppm": template_centre,
        "primary": primary,
        "regression_fingerprint": {"checks": fingerprint_checks, "passed": fingerprint_passed},
        "leave_one_bin_out": {
            "gating": False,
            "classification": "non_promotional_sensitivity_diagnostic",
            "minimum_no_step_z": min(item["no_step_z"] for item in leave_one_out),
            "minimum_step_z": min(item["step_z"] for item in leave_one_out),
            "all_no_step_amplitudes_positive": all(item["no_step_amplitude"] > 0 for item in leave_one_out),
            "all_step_amplitudes_positive": all(item["step_amplitude"] > 0 for item in leave_one_out),
            "fits": leave_one_out,
        },
        "detector_side_deletions": {
            "gating": False,
            "classification": "non_promotional_sensitivity_diagnostic",
            "fits": detector_deletions,
        },
        "affine_baseline_stress": {
            "gating": False,
            "classification": "non_promotional_nuisance_flexibility_diagnostic",
            "fits": affine_baseline,
        },
        "unit_invariance": {
            "scales": unit_results,
            "maximum_absolute_z_difference": max_z_difference,
            "maximum_absolute_delta_chi2_difference": max_delta_difference,
            "tolerance": spec.unit_invariance_tolerance,
            "passed": invariance_passed,
        },
        "covariance_stress": {
            "gating": False,
            "classification": stress_spec["status"],
            "models": stresses,
        },
    }
    return result, filtered, template


def classify_feature(reductions: dict[str, dict[str, Any]]) -> str:
    if all(item["regression_fingerprint"]["passed"] for item in reductions.values()):
        return "retrospective_template_regression_reproduced"
    return "regression_fingerprint_mismatch"


def assess_sensitivity(reductions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Summarize diagnostics without treating correlated views as votes."""

    robust_view_threshold = 3.0
    per_reduction: dict[str, Any] = {}
    for name, result in reductions.items():
        influential_bin = any(
            result["primary"][model]["z"] >= robust_view_threshold
            and result["leave_one_bin_out"][f"minimum_{model}_z"] < robust_view_threshold
            for model in ("no_step", "step")
        )
        assumed_covariance_sensitive = any(
            result["primary"][model]["z"] >= robust_view_threshold
            and stress["fits"][model]["z"] < robust_view_threshold
            for model in ("no_step", "step")
            for stress in result["covariance_stress"]["models"]
        )
        nuisance_sensitive = any(
            result["primary"][model]["z"] >= robust_view_threshold
            and result["affine_baseline_stress"]["fits"][model]["z"] < robust_view_threshold
            for model in ("no_step", "step")
        )
        detector_amplitudes = [
            item["amplitude"]
            for item in result["detector_side_deletions"]["fits"].values()
        ]
        detector_sensitive = min(detector_amplitudes) <= 0 < max(detector_amplitudes)
        per_reduction[name] = {
            "influential_bin": influential_bin,
            "assumed_covariance_sensitive": assumed_covariance_sensitive,
            "nuisance_sensitive": nuisance_sensitive,
            "detector_sensitive": detector_sensitive,
        }
    flags = {
        key: any(item[key] for item in per_reduction.values())
        for key in (
            "influential_bin",
            "assumed_covariance_sensitive",
            "nuisance_sensitive",
            "detector_sensitive",
        )
    }
    active = [key for key, value in flags.items() if value]
    return {
        "state": "sensitive:" + ",".join(active) if active else "no_frozen_sensitivity_flag",
        "robust_view_threshold_z": robust_view_threshold,
        "flags": flags,
        "per_reduction": per_reduction,
        "gating": False,
        "interpretation": (
            "Diagnostics qualify the retrospective regression and cannot promote "
            "it to an authentic or planetary feature."
        ),
    }


def assess_science_state(
    feature_state: str,
    stellar_evidence: dict[str, Any],
    miri_constraint: dict[str, Any],
) -> dict[str, Any]:
    """Apply B2's fail-closed interpretation boundary.

    The deposited products do not contain a direct planet-versus-star model
    comparison for the transmission spectrum. Stellar heterogeneity and the
    MIRI eclipse ranking are separate constraints, so none of their possible
    outcomes can resolve the origin of the NIRSpec feature in this benchmark.
    """

    return {
        "state": "science_unresolved",
        "origin_comparison_status": "not_evaluated",
        "resolution_attempted": False,
        "reason": (
            "No deposited direct planet-versus-star transmission-model comparison; "
            "stellar and MIRI results remain separate constraints."
        ),
        "inputs": {
            "nirspec_feature_state": feature_state,
            "stellar_classification": stellar_evidence["classification"],
            "miri_classification": miri_constraint["classification"],
        },
    }


def fit_stellar_evidence(groups: dict[str, StellarGroup]) -> dict[str, Any]:
    models = ("M1", "M2", "M3")
    common_lower = max(groups[name].wavelength[0] for name in models)
    common_upper = min(groups[name].wavelength[-1] for name in models)
    visits: dict[str, Any] = {}
    for visit_name in ("V1", "V2"):
        visit = groups[visit_name]
        assert visit.uncertainty_mjy is not None
        keep = (visit.wavelength >= common_lower) & (visit.wavelength <= common_upper)
        wavelength = visit.wavelength[keep]
        values = visit.flux_mjy[keep]
        uncertainty = visit.uncertainty_mjy[keep]
        weights = uncertainty**-2
        fits: dict[str, Any] = {}
        for model_name in models:
            model = groups[model_name]
            template = np.interp(wavelength, model.wavelength, model.flux_mjy)
            denominator = float(np.sum(weights * template**2))
            normalization = float(np.sum(weights * template * values) / denominator)
            normalization_se = float(denominator**-0.5)
            chi2 = float(np.sum(weights * (values - normalization * template) ** 2))
            fits[model_name] = {
                "multiplicative_normalization": normalization,
                "normalization_se": normalization_se,
                "chi2": chi2,
                "dof": int(wavelength.size - 1),
            }
        ranking = sorted(models, key=lambda name: fits[name]["chi2"])
        visits[visit_name] = {
            "rows_in_common_model_overlap": int(wavelength.size),
            "wavelength_range_micrometres": [float(wavelength[0]), float(wavelength[-1])],
            "fits": fits,
            "ranking_best_to_worst": ranking,
            "m3_ranks_above_m1": fits["M3"]["chi2"] < fits["M1"]["chi2"],
        }
    passed = all(item["m3_ranks_above_m1"] for item in visits.values())
    return {
        "classification": "stellar_heterogeneity_clue",
        "gating_interpretation": "M3 must rank above M1 in both visits",
        "passed": passed,
        "visits": visits,
        "direct_transit_contamination_fit": False,
        "poseidon_transit_contamination_posterior": "not_deposited; not_reconstructed_or_fabricated",
        "claim_limit": "PHOENIX mixture ranking is a stellar heterogeneity clue, not a direct transit-contamination fit.",
    }


def publisher_hanning_smooth(values: np.ndarray, *, window_length: int = 100) -> np.ndarray:
    """Reproduce the archived Figure 5 smoothing function for a Hanning window."""

    values = np.asarray(values, dtype=np.float64)
    if values.ndim != 1:
        raise AnalysisError("publisher smoothing accepts one-dimensional values")
    if window_length < 4 or values.size < window_length:
        raise AnalysisError("publisher smoothing window is invalid for the model")
    reflected = np.r_[
        2 * np.median(values[: window_length // 5]) - values[window_length:1:-1],
        values,
        2 * np.median(values[-window_length // 5 :]) - values[-1:-window_length:-1],
    ]
    window = np.hanning(window_length)
    smoothed = np.convolve(window / window.sum(), reflected, mode="same")
    result = smoothed[window_length - 1 : -window_length + 1]
    if result.shape != values.shape or not np.all(np.isfinite(result)):
        raise AnalysisError("publisher smoothing produced an invalid result")
    return result


def miri_fixed_model_ranking(
    spectrum: EclipseSpectrum,
    models: dict[str, NumericModel],
    manifest: GJ486Manifest,
) -> dict[str, Any]:
    constraint = manifest.external_constraint
    expected = constraint.analysis["expected_chi2_per_point"]
    tolerance = float(constraint.analysis["fingerprint_tolerance"])
    results: dict[str, Any] = {}
    for name in ("ultramafic", "blackbody_824k", "pure_h2o_1bar"):
        model = models[name]
        if spectrum.wavelength[0] < model.wavelength[0] or spectrum.wavelength[-1] > model.wavelength[-1]:
            raise AnalysisError(f"MIRI model {name} does not cover all SPARTA centres")
        smoothed_ratio = publisher_hanning_smooth(model.values, window_length=100)
        predicted_ppm = np.interp(spectrum.wavelength, model.wavelength, smoothed_ratio) * 1_000_000.0
        residual = (spectrum.eclipse_depth_ppm - predicted_ppm) / spectrum.uncertainty_ppm
        chi2 = float(residual @ residual)
        chi2_per_point = chi2 / spectrum.wavelength.size
        difference = abs(chi2_per_point - float(expected[name]))
        results[name] = {
            "chi2": chi2,
            "points": int(spectrum.wavelength.size),
            "chi2_per_point": chi2_per_point,
            "expected_chi2_per_point": float(expected[name]),
            "absolute_difference": difference,
            "fingerprint_tolerance": tolerance,
            "fingerprint_passed": difference <= tolerance,
            "predicted_eclipse_depth_ppm": [float(value) for value in predicted_ppm],
        }
    ranking = sorted(results, key=lambda name: results[name]["chi2_per_point"])
    all_fingerprints = all(item["fingerprint_passed"] for item in results.values())
    thick_water_worse = (
        results["pure_h2o_1bar"]["chi2_per_point"] > results["ultramafic"]["chi2_per_point"]
        and results["pure_h2o_1bar"]["chi2_per_point"] > results["blackbody_824k"]["chi2_per_point"]
    )
    return {
        "source_role": constraint.role,
        "evidence_type": "external_constraint_not_transmission_bins",
        "spectrum_reduction": constraint.analysis["spectrum_reduction"],
        "points": int(spectrum.wavelength.size),
        "smoothing": constraint.analysis["smoothing"],
        "normalization_or_offset_fitted": False,
        "models": results,
        "ranking_best_to_worst": ranking,
        "classification": constraint.classification if thick_water_worse else "external_constraint_unresolved",
        "fingerprints_passed": all_fingerprints,
        "passed": all_fingerprints and thick_water_worse,
        "claim_limit": constraint.claim_limit,
        "eclipse_spectrum": {
            "wavelength_micrometres": [float(value) for value in spectrum.wavelength],
            "depth_ppm": [float(value) for value in spectrum.eclipse_depth_ppm],
            "uncertainty_ppm": [float(value) for value in spectrum.uncertainty_ppm],
        },
    }


def analyze(
    spectra: dict[str, TransmissionSpectrum],
    water_model: NumericModel,
    stellar_groups: dict[str, StellarGroup],
    miri_spectrum: EclipseSpectrum,
    miri_models: dict[str, NumericModel],
    manifest: GJ486Manifest,
) -> tuple[dict[str, Any], dict[str, tuple[TransmissionSpectrum, np.ndarray]]]:
    reduction_results: dict[str, Any] = {}
    plot_data: dict[str, tuple[TransmissionSpectrum, np.ndarray]] = {}
    for reduction in manifest.spectrum.reductions:
        result, filtered, template = _analyze_reduction(spectra[reduction], water_model, manifest)
        reduction_results[reduction] = result
        plot_data[reduction] = (filtered, template)
    feature_state = classify_feature(reduction_results)
    sensitivity = assess_sensitivity(reduction_results)
    stellar = fit_stellar_evidence(stellar_groups)
    miri_constraint = miri_fixed_model_ranking(miri_spectrum, miri_models, manifest)
    science_assessment = assess_science_state(feature_state, stellar, miri_constraint)
    fingerprint_passed = all(item["regression_fingerprint"]["passed"] for item in reduction_results.values())
    invariance_passed = all(item["unit_invariance"]["passed"] for item in reduction_results.values())
    passed = (
        fingerprint_passed
        and invariance_passed
        and feature_state == manifest.expected_feature_state
        and science_assessment["state"] == manifest.expected_science_state
        and stellar["passed"]
        and miri_constraint["passed"]
    )
    return {
        "pipeline_status": "PASS" if passed else "FAIL",
        "passed": passed,
        "science_state": science_assessment["state"],
        "science_assessment": science_assessment,
        "feature_state": feature_state,
        "robust_spectral_feature": False,
        "sensitivity_state": sensitivity["state"],
        "sensitivity_assessment": sensitivity,
        "planetary_atmosphere_detection": False,
        "independence_statement": "Eureka, Firefly, and Tiberius are correlated robustness views of the same GO 1981 transits; their evidence is not combined.",
        "reductions": reduction_results,
        "stellar_evidence": stellar,
        "miri_external_constraint": miri_constraint,
        "external_context": dict(sorted(manifest.external_context.items())),
    }, plot_data


def canonical_json_text(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def _package_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "unknown"


def _render_plot(
    analysis: dict[str, Any],
    plot_data: dict[str, tuple[TransmissionSpectrum, np.ndarray]],
    manifest: GJ486Manifest,
    output_path: Path,
) -> None:
    import matplotlib

    matplotlib.use("Agg", force=True)
    from matplotlib import pyplot as plt

    figure = plt.figure(figsize=(12, 7.5))
    grid = figure.add_gridspec(2, 3)
    spectrum_axes = [figure.add_subplot(grid[0, index]) for index in range(3)]
    colors = {"Eureka": "#1f77b4", "Firefly": "#d95f02", "Tiberius": "#2ca02c"}
    for axis, reduction in zip(spectrum_axes, manifest.spectrum.reductions, strict=True):
        spectrum, template = plot_data[reduction]
        detector = spectrum.wavelength >= manifest.analysis.detector_split_micrometres
        fit = analysis["reductions"][reduction]["primary"]["no_step"]
        fitted = fit["water_parameters"][0] + fit["amplitude"] * template
        axis.errorbar(
            spectrum.wavelength,
            spectrum.depth_ppm,
            yerr=spectrum.uncertainty_ppm,
            xerr=spectrum.bin_width * 0.5,
            fmt=".",
            markersize=3,
            linewidth=0.6,
            color=colors[reduction],
            alpha=0.75,
            label=f"{reduction} spectrum",
        )
        for side in (False, True):
            axis.plot(spectrum.wavelength[detector == side], fitted[detector == side], color="#222222", linewidth=1.2)
        axis.axvspan(
            spectrum.wavelength[~detector][-1],
            spectrum.wavelength[detector][0],
            color="#cccccc",
            alpha=0.35,
            label="detector gap" if reduction == "Eureka" else None,
        )
        axis.set_title(reduction)
        axis.set_xlabel("Wavelength [µm]")
        axis.set_ylabel("Transit depth [ppm]")
        axis.grid(alpha=0.2)
        axis.legend(fontsize=7, loc="best")

    axis = figure.add_subplot(grid[1, :2])
    positions = np.arange(3)
    no_step = [analysis["reductions"][name]["primary"]["no_step"]["z"] for name in manifest.spectrum.reductions]
    step = [analysis["reductions"][name]["primary"]["step"]["z"] for name in manifest.spectrum.reductions]
    axis.bar(positions - 0.18, no_step, width=0.36, color="#4c78a8", label="No detector step")
    axis.bar(positions + 0.18, step, width=0.36, color="#f58518", label="Detector step")
    axis.axhline(3, color="#555555", linestyle="--", linewidth=0.8, label="robust-view threshold")
    axis.set_xticks(positions, manifest.spectrum.reductions)
    axis.set_ylabel("Signed template z")
    axis.set_title("Correlated robustness views (not combined)")
    axis.legend(fontsize=7, loc="best")
    axis.grid(axis="y", alpha=0.2)
    miri_axis = figure.add_subplot(grid[1, 2])
    miri = analysis["miri_external_constraint"]
    wavelengths = np.asarray(miri["eclipse_spectrum"]["wavelength_micrometres"])
    depths = np.asarray(miri["eclipse_spectrum"]["depth_ppm"])
    errors = np.asarray(miri["eclipse_spectrum"]["uncertainty_ppm"])
    miri_axis.errorbar(wavelengths, depths, yerr=errors, fmt=".", color="#222222", label="SPARTA joint")
    miri_colors = {"ultramafic": "#2ca02c", "blackbody_824k": "#555555", "pure_h2o_1bar": "#1f77b4"}
    for name in ("ultramafic", "blackbody_824k", "pure_h2o_1bar"):
        model = miri["models"][name]
        label = f"{name} (χ²/N={model['chi2_per_point']:.2f})"
        miri_axis.plot(wavelengths, model["predicted_eclipse_depth_ppm"], color=miri_colors[name], label=label)
    miri_axis.set_xlabel("Wavelength [µm]")
    miri_axis.set_ylabel("Eclipse depth [ppm]")
    miri_axis.set_title("GO 1743 external constraint")
    miri_axis.legend(fontsize=6, loc="best")
    miri_axis.grid(alpha=0.2)
    figure.suptitle("GJ 486 b: retrospective water-template regression; science unresolved")
    figure.tight_layout()
    figure.savefig(output_path, dpi=150, metadata={"Software": "gj486-benchmark 0.1.0"})
    plt.close(figure)


def run_benchmark(
    extracted_dir: Path,
    miri_extracted_dir: Path,
    output_dir: Path,
    manifest: GJ486Manifest,
) -> dict[str, Any]:
    extracted_dir = Path(extracted_dir)
    verified = [verify_member(extracted_dir / member.path, member) for member in manifest.members]
    miri_extracted_dir = Path(miri_extracted_dir)
    miri_verified = [
        verify_member(miri_extracted_dir / member.path, member)
        for member in manifest.external_constraint.members
    ]
    transmission_spec = manifest.member_for_role("transmission_spectrum")
    water_spec = manifest.member_for_role("water_model")
    stellar_spec = manifest.member_for_role("stellar_spectra_models")
    spectra = load_transmission_spectra(
        extracted_dir / transmission_spec.path,
        reductions=manifest.spectrum.reductions,
        expected_rows=manifest.spectrum.row_counts,
    )
    water_model = load_water_model(extracted_dir / water_spec.path, expected_rows=manifest.water_model.row_count)
    stellar_groups = load_stellar_groups(extracted_dir / stellar_spec.path, expected_rows=manifest.stellar.row_counts)
    constraint = manifest.external_constraint
    miri_spectrum_spec = constraint.member_for_role("miri_spectrum")
    ultramafic_spec = constraint.member_for_role("ultramafic_model")
    water_1bar_spec = constraint.member_for_role("pure_h2o_1bar_model")
    blackbody_spec = constraint.member_for_role("blackbody_824k_model")
    miri_spectrum = load_miri_spectrum(
        miri_extracted_dir / miri_spectrum_spec.path,
        expected_rows=int(constraint.analysis["spectrum_rows"]),
    )
    miri_models = {
        "ultramafic": load_miri_atmosphere_model(miri_extracted_dir / ultramafic_spec.path),
        "pure_h2o_1bar": load_miri_atmosphere_model(miri_extracted_dir / water_1bar_spec.path),
        "blackbody_824k": load_miri_blackbody_model(miri_extracted_dir / blackbody_spec.path),
    }
    analysis, plot_data = analyze(spectra, water_model, stellar_groups, miri_spectrum, miri_models, manifest)
    result: dict[str, Any] = {
        "schema_version": 1,
        "benchmark_id": manifest.benchmark_id,
        "source": {
            "archive_doi": manifest.archive.doi,
            "archive_sha256": manifest.archive.sha256,
            "license_spdx": manifest.archive.license_spdx,
            "members": sorted(verified, key=lambda item: str(item["role"])),
            "external_constraint": {
                "archive_doi": constraint.archive.doi,
                "archive_sha256": constraint.archive.sha256,
                "license_spdx": constraint.archive.license_spdx,
                "members": sorted(miri_verified, key=lambda item: str(item["role"])),
            },
        },
        "program_provenance": dict(sorted(manifest.program_provenance.items())),
        "software": {
            "python": platform.python_version(),
            "numpy": _package_version("numpy"),
            "matplotlib": _package_version("matplotlib"),
        },
        "analysis": analysis,
        "allowed_claim": manifest.allowed_claim,
        "prohibited_claims": list(manifest.prohibited_claims),
        "citations": dict(sorted(manifest.citations.items())),
    }
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".gj486-benchmark-", dir=output_dir) as raw:
        temporary = Path(raw)
        json_path = temporary / "gj486_benchmark.json"
        plot_path = temporary / "gj486_benchmark.png"
        json_path.write_text(canonical_json_text(result), encoding="utf-8")
        _render_plot(analysis, plot_data, manifest, plot_path)
        os.replace(json_path, output_dir / json_path.name)
        os.replace(plot_path, output_dir / plot_path.name)
    return result
