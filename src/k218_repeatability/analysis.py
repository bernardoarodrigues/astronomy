from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from . import __version__
from .data import VisitSpectrum, load_spectrum
from .extraction import verify_extracted
from .manifest import K218Manifest


class AnalysisError(RuntimeError):
    """Raised when the frozen morphology analysis cannot be evaluated honestly."""


@dataclass(frozen=True)
class GlobalGrid:
    edges_micrometres: np.ndarray
    centres_micrometres: np.ndarray
    feature_overlap_fraction: np.ndarray
    edge_sha256: str


@dataclass(frozen=True)
class RebinnedSpectrum:
    grid: GlobalGrid
    depth_ppm: np.ndarray
    covariance_ppm2: np.ndarray
    weight_matrix: np.ndarray
    interval_overlap_micrometres: np.ndarray
    coverage_fraction: np.ndarray


@dataclass(frozen=True)
class ContrastFit:
    beta: np.ndarray
    parameter_covariance: np.ndarray
    chi2: float
    dof: int
    design_rank: int
    normal_condition_number: float


def _edge_hash(edges: np.ndarray) -> str:
    encoded = "\n".join(format(float(value), ".17g") for value in edges).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def build_global_grid(manifest: K218Manifest) -> GlobalGrid:
    spec = manifest.rebinning
    indices = np.arange(spec.first_edge_index, spec.last_edge_index + 1, dtype=np.float64)
    edges = spec.grid_anchor_micrometres * np.exp(indices / spec.resolving_power)
    if edges.size != spec.edge_count or edges.size - 1 != spec.output_bin_count:
        raise AnalysisError("global edge count differs from the frozen manifest")
    digest = _edge_hash(edges)
    if digest != spec.edge_sha256:
        raise AnalysisError(f"global edge hash mismatch: expected {spec.edge_sha256}, got {digest}")
    domain_low, domain_high = manifest.analysis.domain_micrometres
    if not np.all(edges[:-1] >= domain_low) or not np.all(edges[1:] <= domain_high):
        raise AnalysisError("a global output cell is not wholly inside the analysis domain")
    centres = np.sqrt(edges[:-1] * edges[1:])
    feature_low, feature_high = manifest.analysis.feature_micrometres
    overlaps = np.maximum(
        0.0,
        np.minimum(edges[1:], feature_high) - np.maximum(edges[:-1], feature_low),
    )
    feature_fraction = overlaps / np.diff(edges)
    if not np.any((feature_fraction > 0) & (feature_fraction < 1)):
        raise AnalysisError("frozen feature vector must retain boundary-overlap fractions")
    return GlobalGrid(edges, centres, feature_fraction, digest)


def native_covariance(spectrum: VisitSpectrum, rho: float | None = None) -> np.ndarray:
    sigma = np.asarray(spectrum.uncertainty_ppm, dtype=np.float64)
    if rho is None:
        return np.diag(np.square(sigma))
    if not 0.0 <= rho < 1.0:
        raise AnalysisError("AR(1) rho must be in [0,1)")
    distance = np.abs(np.subtract.outer(np.arange(sigma.size), np.arange(sigma.size)))
    return np.outer(sigma, sigma) * np.power(rho, distance)


def overlap_weight_matrix(
    spectrum: VisitSpectrum,
    grid: GlobalGrid,
    manifest: K218Manifest,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    output_low = grid.edges_micrometres[:-1, None]
    output_high = grid.edges_micrometres[1:, None]
    native_low = spectrum.lower_micrometres[None, :]
    native_high = spectrum.upper_micrometres[None, :]
    overlap = np.maximum(0.0, np.minimum(output_high, native_high) - np.maximum(output_low, native_low))
    output_width = np.diff(grid.edges_micrometres)
    coverage = np.sum(overlap, axis=1) / output_width
    tolerance = manifest.rebinning.coverage_relative_tolerance
    minimum = manifest.rebinning.minimum_coverage_fraction
    if not np.all(coverage >= minimum) or not np.all(np.abs(coverage - 1.0) <= tolerance):
        raise AnalysisError(
            "global output cell lacks full native coverage within the frozen relative tolerance"
        )

    inverse_variance_overlap = overlap / np.square(spectrum.uncertainty_ppm[None, :])
    row_denominator = np.sum(inverse_variance_overlap, axis=1)
    if not np.all(np.isfinite(row_denominator)) or not np.all(row_denominator > 0):
        raise AnalysisError("overlap-aware inverse-variance weight normalization failed")
    weights = inverse_variance_overlap / row_denominator[:, None]
    if np.any(weights[overlap == 0.0] != 0.0):
        raise AnalysisError("a native row received weight without actual interval overlap")
    if not np.allclose(np.sum(weights, axis=1), 1.0, rtol=0.0, atol=1e-14):
        raise AnalysisError("overlap-aware inverse-variance rows do not sum to one")
    # A native interval may straddle a global edge. Such a row can contribute
    # to adjacent cells, but only where the explicitly computed overlap is > 0.
    for native_index in np.flatnonzero(np.count_nonzero(weights, axis=0) > 1):
        if np.any(weights[:, native_index] > 0.0) and np.any(
            (weights[:, native_index] > 0.0) & (overlap[:, native_index] <= 0.0)
        ):
            raise AnalysisError("native-row cross-cell contribution lacks actual overlap")
    return weights, overlap, coverage


def rebin_spectrum(
    spectrum: VisitSpectrum,
    grid: GlobalGrid,
    manifest: K218Manifest,
    *,
    covariance_native: np.ndarray | None = None,
) -> RebinnedSpectrum:
    weights, overlap, coverage = overlap_weight_matrix(spectrum, grid, manifest)
    covariance = native_covariance(spectrum) if covariance_native is None else np.asarray(
        covariance_native, dtype=np.float64
    )
    expected_shape = (spectrum.wavelength_micrometres.size,) * 2
    if covariance.shape != expected_shape or not np.all(np.isfinite(covariance)):
        raise AnalysisError("native covariance shape or values are invalid")
    try:
        np.linalg.cholesky(covariance)
    except np.linalg.LinAlgError as exc:
        raise AnalysisError(f"native covariance is not positive definite: {exc}") from exc
    # Explicit contractions avoid platform BLAS warnings seen for sparse,
    # highly anisotropic overlap matrices while retaining float64 arithmetic.
    depth = np.einsum("ji,i->j", weights, spectrum.depth_ppm, optimize=False)
    output_covariance = np.einsum(
        "ji,ik,lk->jl", weights, covariance, weights, optimize=False
    )
    if not np.all(np.isfinite(depth)) or not np.all(np.isfinite(output_covariance)):
        raise AnalysisError("rebinning produced nonfinite values")
    return RebinnedSpectrum(grid, depth, output_covariance, weights, overlap, coverage)


def fit_contrast(
    wavelength_micrometres: np.ndarray,
    depth_ppm: np.ndarray,
    covariance_ppm2: np.ndarray,
    feature_overlap_fraction: np.ndarray,
    *,
    pivot_micrometres: float = 4.3,
) -> ContrastFit:
    wavelength = np.asarray(wavelength_micrometres, dtype=np.float64)
    depth = np.asarray(depth_ppm, dtype=np.float64)
    covariance = np.asarray(covariance_ppm2, dtype=np.float64)
    feature = np.asarray(feature_overlap_fraction, dtype=np.float64)
    if wavelength.ndim != 1 or depth.shape != wavelength.shape or feature.shape != wavelength.shape:
        raise AnalysisError("contrast vectors have incompatible dimensions")
    if wavelength.size <= 3 or covariance.shape != (wavelength.size, wavelength.size):
        raise AnalysisError("contrast fit has too few bins or an invalid covariance shape")
    if not all(np.all(np.isfinite(value)) for value in (wavelength, depth, covariance, feature)):
        raise AnalysisError("contrast fit contains nonfinite values")
    design = np.column_stack(
        (
            np.ones_like(wavelength),
            wavelength - pivot_micrometres,
            feature,
        )
    )
    try:
        cholesky = np.linalg.cholesky(covariance)
        whitened_design = np.linalg.solve(cholesky, design)
        whitened_depth = np.linalg.solve(cholesky, depth)
        rank = int(np.linalg.matrix_rank(whitened_design))
        if rank != 3:
            raise AnalysisError(f"contrast design rank is {rank}, expected 3")
        normal = whitened_design.T @ whitened_design
        condition = float(np.linalg.cond(normal))
        if not np.isfinite(condition):
            raise AnalysisError("contrast normal matrix has nonfinite condition number")
        parameter_covariance = np.linalg.inv(normal)
        beta = np.linalg.solve(normal, whitened_design.T @ whitened_depth)
        residual = whitened_depth - whitened_design @ beta
    except np.linalg.LinAlgError as exc:
        raise AnalysisError(f"full GLS fit failed: {exc}") from exc
    if not all(np.all(np.isfinite(value)) for value in (beta, parameter_covariance, residual)):
        raise AnalysisError("full GLS fit produced nonfinite values")
    if parameter_covariance[2, 2] <= 0:
        raise AnalysisError("amplitude variance is nonpositive")
    return ContrastFit(
        beta=beta,
        parameter_covariance=parameter_covariance,
        chi2=float(residual @ residual),
        dof=int(wavelength.size - 3),
        design_rank=rank,
        normal_condition_number=condition,
    )


def _fit_dict(fit: ContrastFit, *, z_label: str) -> dict[str, Any]:
    amplitude_se = float(math.sqrt(fit.parameter_covariance[2, 2]))
    slope_se = float(math.sqrt(fit.parameter_covariance[1, 1]))
    slope_amplitude_correlation = float(
        fit.parameter_covariance[1, 2] / (slope_se * amplitude_se)
    )
    return {
        "valid": True,
        "intercept_ppm": float(fit.beta[0]),
        "slope_ppm_per_micrometre": float(fit.beta[1]),
        "amplitude_ppm": float(fit.beta[2]),
        "amplitude_se_ppm": amplitude_se,
        "z": float(fit.beta[2] / amplitude_se),
        "z_label": z_label,
        "chi2": fit.chi2,
        "dof": fit.dof,
        "bin_count": fit.dof + 3,
        "design_rank": fit.design_rank,
        "normal_condition_number": fit.normal_condition_number,
        "slope_amplitude_correlation": slope_amplitude_correlation,
    }


def _invalid_fit(exc: Exception) -> dict[str, Any]:
    return {"valid": False, "error": str(exc)}


def analyze_cell(
    spectrum: VisitSpectrum,
    grid: GlobalGrid,
    manifest: K218Manifest,
    *,
    source_role: str,
) -> dict[str, Any]:
    primary = rebin_spectrum(spectrum, grid, manifest)
    fit = fit_contrast(
        grid.centres_micrometres,
        primary.depth_ppm,
        primary.covariance_ppm2,
        grid.feature_overlap_fraction,
        pivot_micrometres=manifest.analysis.pivot_micrometres,
    )
    nominal = _fit_dict(fit, z_label=manifest.analysis.z_label)

    ar1_results: list[dict[str, Any]] = []
    for rho in manifest.analysis.ar1_rho_sensitivities:
        try:
            rebinned = rebin_spectrum(
                spectrum,
                grid,
                manifest,
                covariance_native=native_covariance(spectrum, rho),
            )
            stress_fit = fit_contrast(
                grid.centres_micrometres,
                rebinned.depth_ppm,
                rebinned.covariance_ppm2,
                grid.feature_overlap_fraction,
                pivot_micrometres=manifest.analysis.pivot_micrometres,
            )
            ar1_results.append(
                {
                    "rho": rho,
                    "covariance_status": "assumed_within_detector_AR1_sensitivity",
                    **_fit_dict(stress_fit, z_label=manifest.analysis.z_label),
                }
            )
        except AnalysisError as exc:
            ar1_results.append(
                {
                    "rho": rho,
                    "covariance_status": "assumed_within_detector_AR1_sensitivity",
                    **_invalid_fit(exc),
                }
            )

    leave_one_out: list[dict[str, Any]] = []
    for omitted in range(grid.centres_micrometres.size):
        keep = np.arange(grid.centres_micrometres.size) != omitted
        try:
            loo_fit = fit_contrast(
                grid.centres_micrometres[keep],
                primary.depth_ppm[keep],
                primary.covariance_ppm2[np.ix_(keep, keep)],
                grid.feature_overlap_fraction[keep],
                pivot_micrometres=manifest.analysis.pivot_micrometres,
            )
            entry = _fit_dict(loo_fit, z_label=manifest.analysis.z_label)
        except AnalysisError as exc:
            entry = _invalid_fit(exc)
        leave_one_out.append(
            {
                "omitted_bin_index": omitted,
                "omitted_lower_micrometres": float(grid.edges_micrometres[omitted]),
                "omitted_upper_micrometres": float(grid.edges_micrometres[omitted + 1]),
                **entry,
            }
        )

    nominal_pass = bool(nominal["amplitude_ppm"] > 0 and nominal["z"] >= 2.0)
    ar1_pass = bool(
        len(ar1_results) == len(manifest.analysis.ar1_rho_sensitivities)
        and all(item.get("valid") is True and item["amplitude_ppm"] > 0 for item in ar1_results)
    )
    loo_pass = bool(
        len(leave_one_out) == grid.centres_micrometres.size
        and all(item.get("valid") is True and item["amplitude_ppm"] > 0 for item in leave_one_out)
    )
    weights = primary.weight_matrix
    overlap = primary.interval_overlap_micrometres
    native_contribution_counts = np.count_nonzero(weights, axis=0)
    cell_pass = nominal_pass and ar1_pass and loo_pass
    return {
        "reduction": spectrum.reduction,
        "visit": spectrum.visit,
        "detector": spectrum.detector,
        "evidence_unit": manifest.program["complete_g395h_visit_inventory"][spectrum.visit][
            "independence_group"
        ],
        "independent_reduction": False,
        "source_role": source_role,
        "native": {
            "row_count": int(spectrum.wavelength_micrometres.size),
            "wavelength_min_micrometres": float(spectrum.wavelength_micrometres[0]),
            "wavelength_max_micrometres": float(spectrum.wavelength_micrometres[-1]),
            "depth_unit": "ppm",
            "uncertainty_symmetrization": "max(error_low,error_high); both positive",
            "source_metadata": spectrum.source_metadata,
        },
        "rebinning": {
            "method": "overlap-aware inverse-variance mean",
            "grid_edge_sha256": grid.edge_sha256,
            "output_bin_count": int(grid.centres_micrometres.size),
            "coverage_relative_tolerance": manifest.rebinning.coverage_relative_tolerance,
            "minimum_coverage_fraction_required": manifest.rebinning.minimum_coverage_fraction,
            "minimum_coverage_fraction_observed": float(np.min(primary.coverage_fraction)),
            "maximum_coverage_fraction_observed": float(np.max(primary.coverage_fraction)),
            "minimum_weight_row_sum": float(np.min(np.sum(weights, axis=1))),
            "maximum_weight_row_sum": float(np.max(np.sum(weights, axis=1))),
            "zero_weight_without_overlap": bool(np.all(weights[overlap == 0.0] == 0.0)),
            "maximum_output_bins_per_native_row": int(np.max(native_contribution_counts)),
            "native_rows_contributing_to_multiple_bins": int(
                np.count_nonzero(native_contribution_counts > 1)
            ),
            "covariance_propagation": "C_out=W*C_native*W^T",
            "centres_micrometres": [float(value) for value in grid.centres_micrometres],
            "depth_ppm": [float(value) for value in primary.depth_ppm],
            "uncertainty_ppm": [
                float(value) for value in np.sqrt(np.diag(primary.covariance_ppm2))
            ],
            "feature_overlap_fraction": [
                float(value) for value in grid.feature_overlap_fraction
            ],
        },
        "nominal": nominal,
        "ar1_sensitivity": ar1_results,
        "leave_one_output_bin_out": {
            "required_fit_count": int(grid.centres_micrometres.size),
            "valid_fit_count": sum(item.get("valid") is True for item in leave_one_out),
            "all_valid_amplitudes_positive": loo_pass,
            "fits": leave_one_out,
        },
        "criterion_checks": {
            "nominal_A_positive_and_z_at_least_2": nominal_pass,
            "all_required_AR1_A_positive": ar1_pass,
            "all_required_LOO_valid_and_A_positive": loo_pass,
            "cell_passed": cell_pass,
        },
    }


def classify_outcome(cells: list[dict[str, Any]]) -> dict[str, Any]:
    required = {
        ("Eureka", "visit_2"),
        ("Eureka", "visit_3"),
        ("exoTEDRF", "visit_2"),
        ("exoTEDRF", "visit_3"),
    }
    observed = [(str(cell.get("reduction")), str(cell.get("visit"))) for cell in cells]
    observed_set = set(observed)
    duplicate_cells = sorted(key for key in observed_set if observed.count(key) != 1)
    missing_cells = sorted(required - observed_set)
    unexpected_cells = sorted(observed_set - required)
    failed_cells = sorted(
        (str(cell.get("reduction")), str(cell.get("visit")))
        for cell in cells
        if cell.get("criterion_checks", {}).get("cell_passed") is not True
    )
    complete = (
        len(cells) == 4
        and not duplicate_cells
        and not missing_cells
        and not unexpected_cells
        and not failed_cells
    )
    state = "repeatable_positive_morphology" if complete else "SCIENCE_UNRESOLVED"
    reason = "all_frozen_repeatability_criteria_met" if complete else "criterion_not_met"
    return {
        "state": state,
        "reason": reason,
        "required_cell_count": 4,
        "observed_cell_count": len(cells),
        "missing_cells": [list(value) for value in missing_cells],
        "duplicate_cells": [list(value) for value in duplicate_cells],
        "unexpected_cells": [list(value) for value in unexpected_cells],
        "failed_cells": [list(value) for value in failed_cells],
        "all_required_cells_complete_and_passed": complete,
    }


def within_reduction_diagnostics(cells: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for reduction in ("Eureka", "exoTEDRF"):
        selected = sorted(
            [cell for cell in cells if cell.get("reduction") == reduction],
            key=lambda item: str(item.get("visit")),
        )
        if len(selected) != 2 or any(cell.get("nominal", {}).get("valid") is not True for cell in selected):
            result[reduction] = {
                "valid": False,
                "scope": "within_reduction_across_two_distinct_visits_only",
                "error": "two valid visit fits are required",
            }
            continue
        amplitudes = np.asarray([cell["nominal"]["amplitude_ppm"] for cell in selected])
        errors = np.asarray([cell["nominal"]["amplitude_se_ppm"] for cell in selected])
        weights = 1.0 / np.square(errors)
        mean = float(np.sum(weights * amplitudes) / np.sum(weights))
        se = float(math.sqrt(1.0 / np.sum(weights)))
        q = float(np.sum(weights * np.square(amplitudes - mean)))
        i2 = float(max(0.0, (q - 1.0) / q) * 100.0) if q > 0 else 0.0
        result[reduction] = {
            "valid": True,
            "scope": "within_reduction_across_two_distinct_visits_only",
            "visits": [cell["visit"] for cell in selected],
            "common_effect_amplitude_ppm": mean,
            "common_effect_se_ppm": se,
            "common_effect_z": mean / se,
            "z_label": "retrospective_standardized_contrast",
            "cochran_q": q,
            "cochran_q_df": 1,
            "i_squared_percent": i2,
        }
    return result


def paired_reduction_differences(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for visit in ("visit_2", "visit_3"):
        by_reduction = {
            str(cell.get("reduction")): cell
            for cell in cells
            if cell.get("visit") == visit
        }
        if set(by_reduction) != {"Eureka", "exoTEDRF"}:
            result.append(
                {
                    "visit": visit,
                    "valid": False,
                    "independent_reduction": False,
                    "significance": "not_evaluated_cross_reduction_covariance_unavailable",
                    "error": "both paired reduction views are required",
                }
            )
            continue
        eureka = by_reduction["Eureka"]["nominal"]
        exotedrf = by_reduction["exoTEDRF"]["nominal"]
        if eureka.get("valid") is not True or exotedrf.get("valid") is not True:
            result.append(
                {
                    "visit": visit,
                    "valid": False,
                    "independent_reduction": False,
                    "significance": "not_evaluated_cross_reduction_covariance_unavailable",
                    "error": "paired nominal fit is invalid",
                }
            )
            continue
        result.append(
            {
                "visit": visit,
                "valid": True,
                "delta_amplitude_ppm_eureka_minus_exotedrf": float(
                    eureka["amplitude_ppm"] - exotedrf["amplitude_ppm"]
                ),
                "independent_reduction": False,
                "significance": "not_evaluated_cross_reduction_covariance_unavailable",
                "used_for_voting": False,
            }
        )
    return result


def analyze_spectra(
    spectra: list[tuple[str, VisitSpectrum]], manifest: K218Manifest
) -> dict[str, Any]:
    grid = build_global_grid(manifest)
    cells = [
        analyze_cell(spectrum, grid, manifest, source_role=role)
        for role, spectrum in sorted(
            spectra, key=lambda item: (item[1].reduction, item[1].visit)
        )
    ]
    outcome = classify_outcome(cells)
    return {
        "analysis_label": "retrospective_published_spectrum_feature_repeatability",
        "model": manifest.analysis_contract["model"],
        "z_interpretation": "retrospective standardized contrast; not discovery significance",
        "global_grid": {
            "definition": "e_k=1 micrometre*exp(k/100)",
            "first_edge_index": manifest.rebinning.first_edge_index,
            "last_edge_index": manifest.rebinning.last_edge_index,
            "edge_sha256": grid.edge_sha256,
            "edge_hash_encoding": manifest.rebinning.edge_hash_encoding,
            "edge_count": int(grid.edges_micrometres.size),
            "output_bin_count": int(grid.centres_micrometres.size),
            "edges_micrometres": [float(value) for value in grid.edges_micrometres],
            "identical_edge_vector_required_and_used_for_all_cells": True,
            "no_clipped_partial_output_cells": True,
        },
        "cells": cells,
        "within_reduction_common_effect_and_heterogeneity": within_reduction_diagnostics(cells),
        "paired_reduction_differences": paired_reduction_differences(cells),
        "evidence_combination": {
            "evidence_units": 2,
            "paired_correlated_views_per_evidence_unit": 2,
            "independent_reduction": False,
            "cross_reduction_z_combination": "prohibited_not_computed",
            "cross_reduction_voting": "prohibited_not_performed",
            "within_reduction_common_effect_scope": "two distinct GO-2372 visits only",
        },
        "outcome": outcome,
    }


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    try:
        return (
            json.dumps(
                value,
                sort_keys=True,
                indent=2,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AnalysisError(f"result cannot be serialized canonically: {exc}") from exc


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _write_plot(path: Path, analysis: dict[str, Any]) -> None:
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    path.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 2, figsize=(10.0, 6.8), dpi=120, sharex=True)
    for axis, cell in zip(axes.ravel(), analysis["cells"]):
        rebinned = cell["rebinning"]
        wavelength = np.asarray(rebinned["centres_micrometres"])
        depth = np.asarray(rebinned["depth_ppm"])
        uncertainty = np.asarray(rebinned["uncertainty_ppm"])
        feature = np.asarray(rebinned["feature_overlap_fraction"])
        nominal = cell["nominal"]
        model = (
            nominal["intercept_ppm"]
            + nominal["slope_ppm_per_micrometre"] * (wavelength - 4.3)
            + nominal["amplitude_ppm"] * feature
        )
        axis.errorbar(
            wavelength,
            depth,
            yerr=uncertainty,
            fmt="o",
            color="#1f5a7a",
            ecolor="#8a9daa",
            markersize=3.2,
            linewidth=0.8,
            capsize=1.5,
            label="R=100 published bins",
        )
        axis.plot(wavelength, model, color="#a33b20", linewidth=1.4, label="frozen morphology fit")
        axis.axvspan(4.05, 4.55, color="#d9a441", alpha=0.12)
        axis.set_title(
            f"{cell['visit']} / {cell['reduction']}  A={nominal['amplitude_ppm']:.1f} ppm, z={nominal['z']:.2f}",
            fontsize=9,
        )
        axis.grid(alpha=0.18, linewidth=0.5)
    for axis in axes[:, 0]:
        axis.set_ylabel("Published transit depth (ppm)")
    for axis in axes[-1, :]:
        axis.set_xlabel("Wavelength (micrometres)")
    axes[0, 0].legend(loc="best", fontsize=7, frameon=False)
    fig.suptitle(
        "K2-18 b GO-2372 published-spectrum 4.3 µm morphology\n"
        "Retrospective; paired reductions are not independent; no molecule attribution",
        fontsize=11,
    )
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.93))
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
        fig.savefig(
            temporary,
            format="png",
            dpi=120,
            metadata={"Software": "k218_repeatability 0.1.0"},
        )
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        plt.close(fig)
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def run_benchmark(
    extracted_dir: Path,
    output_dir: Path,
    manifest: K218Manifest,
) -> dict[str, Any]:
    verified = verify_extracted(extracted_dir, manifest)
    spectra: list[tuple[str, VisitSpectrum]] = []
    for member in manifest.members:
        spectrum = load_spectrum(Path(extracted_dir) / member.path, member, manifest)
        spectra.append((member.role, spectrum))
    analysis = analyze_spectra(spectra, manifest)
    result = {
        "schema_version": 1,
        "benchmark_id": manifest.benchmark_id,
        "execution_status": "PASS",
        **manifest.output_contract,
        "retrospective": True,
        "independent_reduction": False,
        "manifest_canonical_sha256": manifest.canonical_sha256,
        "source": {
            "record": manifest.archive.record,
            "doi": manifest.archive.doi,
            "url": manifest.archive.url,
            "filename": manifest.archive.filename,
            "size_bytes": manifest.archive.size_bytes,
            "sha256": manifest.archive.sha256,
            "license_spdx": manifest.archive.license_spdx,
            "members": verified,
        },
        "visit_selection": {
            "complete_g395h_visit_inventory": manifest.program[
                "complete_g395h_visit_inventory"
            ],
            "selection_rule": manifest.program["selection_rule"],
            "selection_basis": "metadata_only",
            "spectral_result_selection": False,
            "eligible_visits": manifest.program["eligible_visits"],
        },
        "analysis": analysis,
        "allowed_claim": manifest.allowed_claim,
        "prohibited_claims": list(manifest.prohibited_claims),
        "citations": manifest.citations,
        "software": {
            "k218_repeatability": __version__,
            "numpy": np.__version__,
            "python": platform.python_version(),
        },
    }
    output_dir = Path(output_dir)
    _atomic_write(output_dir / "k218_repeatability.json", _canonical_bytes(result))
    _write_plot(output_dir / "k218_repeatability.png", analysis)
    return result
