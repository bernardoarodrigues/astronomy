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

from .integrity import verify_member
from .manifest import AtmosphereManifest
from .spectrum import Spectrum, load_spectrum, load_two_column_model


class AnalysisError(RuntimeError):
    """Raised when the frozen atmospheric analysis contract cannot be met."""


@dataclass(frozen=True)
class FitResult:
    beta: np.ndarray
    covariance: np.ndarray
    chi2: float
    dof: int


def design_matrix(
    wavelength: np.ndarray,
    *,
    pivot: float,
    feature_sigma: float,
    include_feature: bool,
) -> np.ndarray:
    x = np.asarray(wavelength, dtype=np.float64) - pivot
    columns = [np.ones_like(x), x]
    if include_feature:
        columns.append(np.exp(-0.5 * (x / feature_sigma) ** 2))
    return np.column_stack(columns)


def evaluate_model(
    wavelength: np.ndarray,
    beta: np.ndarray,
    *,
    pivot: float,
    feature_sigma: float,
) -> np.ndarray:
    """Evaluate M0 or M1 explicitly, avoiding platform-dependent BLAS paths."""

    x = np.asarray(wavelength, dtype=np.float64) - pivot
    beta = np.asarray(beta, dtype=np.float64)
    values = beta[0] + beta[1] * x
    if beta.size == 3:
        values = values + beta[2] * np.exp(-0.5 * (x / feature_sigma) ** 2)
    return values


def weighted_fit(
    design: np.ndarray,
    values: np.ndarray,
    *,
    uncertainties: np.ndarray | None = None,
    covariance: np.ndarray | None = None,
) -> FitResult:
    design = np.asarray(design, dtype=np.float64)
    values = np.asarray(values, dtype=np.float64)
    if design.ndim != 2 or values.ndim != 1 or design.shape[0] != values.size:
        raise AnalysisError("design and data dimensions do not agree")
    if covariance is not None and uncertainties is not None:
        raise AnalysisError("provide uncertainties or covariance, not both")
    try:
        if covariance is not None:
            covariance = np.asarray(covariance, dtype=np.float64)
            if covariance.shape != (values.size, values.size):
                raise AnalysisError("covariance shape does not match the data")
            if not np.all(np.isfinite(covariance)):
                raise AnalysisError("covariance contains nonfinite values")
            cholesky = np.linalg.cholesky(covariance)
            whitened_design = np.linalg.solve(cholesky, design)
            whitened_values = np.linalg.solve(cholesky, values)
        else:
            if uncertainties is None:
                raise AnalysisError("uncertainties are required for diagonal WLS")
            uncertainties = np.asarray(uncertainties, dtype=np.float64)
            if uncertainties.shape != values.shape or not np.all(uncertainties > 0):
                raise AnalysisError("uncertainties must be positive and match the data")
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
    return FitResult(
        beta=beta,
        covariance=parameter_covariance,
        chi2=float(residual @ residual),
        dof=int(values.size - design.shape[1]),
    )


def fit_models(
    wavelength: np.ndarray,
    values: np.ndarray,
    uncertainties: np.ndarray,
    *,
    pivot: float = 4.3,
    feature_sigma: float = 0.1,
    covariance: np.ndarray | None = None,
) -> tuple[FitResult, FitResult, dict[str, float]]:
    m0_design = design_matrix(
        wavelength,
        pivot=pivot,
        feature_sigma=feature_sigma,
        include_feature=False,
    )
    m1_design = design_matrix(
        wavelength,
        pivot=pivot,
        feature_sigma=feature_sigma,
        include_feature=True,
    )
    kwargs = {"covariance": covariance} if covariance is not None else {"uncertainties": uncertainties}
    m0 = weighted_fit(m0_design, values, **kwargs)
    m1 = weighted_fit(m1_design, values, **kwargs)
    amplitude = float(m1.beta[2])
    amplitude_se = float(np.sqrt(m1.covariance[2, 2]))
    metrics = {
        "amplitude": amplitude,
        "amplitude_se": amplitude_se,
        "z": amplitude / amplitude_se,
        "delta_chi2": m0.chi2 - m1.chi2,
    }
    return m0, m1, metrics


def select_frozen_window(spectrum: Spectrum, manifest: AtmosphereManifest) -> Spectrum:
    lower, upper = manifest.analysis.window_micrometres
    mask = (spectrum.wavelength >= lower) & (spectrum.wavelength <= upper)
    selected = spectrum.subset(mask)
    if selected.wavelength.size != manifest.analysis.expected_window_rows:
        raise AnalysisError(
            f"frozen window expected {manifest.analysis.expected_window_rows} rows, "
            f"found {selected.wavelength.size}"
        )
    return selected


def _in_band(value: float, band: list[float]) -> bool:
    return float(band[0]) <= value <= float(band[1])


def _fit_dict(fit: FitResult, *, feature: bool) -> dict[str, Any]:
    result: dict[str, Any] = {
        "beta0": float(fit.beta[0]),
        "beta1": float(fit.beta[1]),
        "chi2": fit.chi2,
        "dof": fit.dof,
    }
    if feature:
        result["amplitude"] = float(fit.beta[2])
        result["amplitude_se"] = float(np.sqrt(fit.covariance[2, 2]))
    return result


def null_calibration(
    wavelength: np.ndarray,
    uncertainties: np.ndarray,
    fitted_m0_values: np.ndarray,
    *,
    pivot: float,
    feature_sigma: float,
    draws: int,
    seed: int,
) -> dict[str, float]:
    design = design_matrix(
        wavelength,
        pivot=pivot,
        feature_sigma=feature_sigma,
        include_feature=True,
    )
    whitened_design = design / uncertainties[:, None]
    normal_inverse = np.linalg.inv(whitened_design.T @ whitened_design)
    estimator = normal_inverse @ whitened_design.T
    amplitude_se = float(np.sqrt(normal_inverse[2, 2]))
    generator = np.random.default_rng(seed)
    noise = generator.standard_normal((draws, wavelength.size))
    simulated = fitted_m0_values[None, :] + noise * uncertainties[None, :]
    whitened_simulated = simulated / uncertainties[None, :]
    # Explicit contraction avoids platform BLAS warnings observed for the
    # highly anisotropic nuisance/feature design while preserving float64 math.
    beta = np.einsum(
        "dn,pn->dp", whitened_simulated, estimator, optimize=False
    )
    z = beta[:, 2] / amplitude_se
    return {
        "mean_z": float(np.mean(z)),
        "std_z": float(np.std(z, ddof=1)),
        "two_sided_1p96_fraction": float(np.mean(np.abs(z) > 1.96)),
    }


def attribution_diagnostic(
    full_model: tuple[np.ndarray, np.ndarray],
    no_co2_model: tuple[np.ndarray, np.ndarray],
    manifest: AtmosphereManifest,
) -> dict[str, Any]:
    full_wavelength, full_depth = full_model
    no_co2_wavelength, no_co2_depth = no_co2_model
    lower, upper = manifest.analysis.window_micrometres
    mask = (no_co2_wavelength >= lower) & (no_co2_wavelength <= upper)
    wavelength = no_co2_wavelength[mask]
    if wavelength.size != manifest.analysis.expected_window_rows:
        raise AnalysisError("ScCHIMERA no-CO2 model does not match the frozen window")
    if wavelength[0] < full_wavelength[0] or wavelength[-1] > full_wavelength[-1]:
        raise AnalysisError("ScCHIMERA full model does not cover the diagnostic window")
    difference = np.interp(wavelength, full_wavelength, full_depth) - no_co2_depth[mask]
    peak = int(np.argmax(difference))
    return {
        "gating": False,
        "status": "published_model_pair_attribution_diagnostic",
        "window_rows": int(wavelength.size),
        "peak_full_minus_no_co2": float(difference[peak]),
        "peak_wavelength_micrometres": float(wavelength[peak]),
        "mean_full_minus_no_co2": float(np.mean(difference)),
        "interpretation": "Model-dependent comparison only; not used for benchmark acceptance.",
    }


def analyze_spectrum(
    spectrum: Spectrum,
    manifest: AtmosphereManifest,
    *,
    full_model: tuple[np.ndarray, np.ndarray],
    no_co2_model: tuple[np.ndarray, np.ndarray],
) -> dict[str, Any]:
    window = select_frozen_window(spectrum, manifest)
    pivot = manifest.analysis.pivot_micrometres
    feature_sigma = manifest.analysis.feature_sigma_micrometres
    m0, m1, primary = fit_models(
        window.wavelength,
        window.transit_depth,
        window.uncertainty,
        pivot=pivot,
        feature_sigma=feature_sigma,
    )
    acceptance = manifest.analysis.acceptance
    primary_checks = {
        "amplitude_in_band": _in_band(primary["amplitude"], acceptance["amplitude"]),
        "z_in_band": _in_band(primary["z"], acceptance["z"]),
        "delta_chi2_in_band": _in_band(
            primary["delta_chi2"], acceptance["delta_chi2"]
        ),
    }
    primary_checks["passed"] = all(primary_checks.values())
    fingerprint = manifest.analysis.expected_fingerprint
    fingerprint_differences = {
        key: primary[key] - float(fingerprint[key])
        for key in ("amplitude", "z", "delta_chi2")
    }

    leave_one_out = []
    loo_minimum_z = float(acceptance["leave_one_out_minimum_z"])
    for index in range(window.wavelength.size):
        keep = np.arange(window.wavelength.size) != index
        _, _, metrics = fit_models(
            window.wavelength[keep],
            window.transit_depth[keep],
            window.uncertainty[keep],
            pivot=pivot,
            feature_sigma=feature_sigma,
        )
        passed = metrics["amplitude"] > 0 and metrics["z"] >= loo_minimum_z
        leave_one_out.append(
            {
                "omitted_index": index,
                "omitted_wavelength_micrometres": float(window.wavelength[index]),
                "amplitude": metrics["amplitude"],
                "z": metrics["z"],
                "passed": passed,
            }
        )
    loo_passed = all(item["passed"] for item in leave_one_out)

    _, _, ppm = fit_models(
        window.wavelength,
        window.transit_depth * 1_000_000.0,
        window.uncertainty * 1_000_000.0,
        pivot=pivot,
        feature_sigma=feature_sigma,
    )
    invariance_tolerance = float(acceptance["ppm_invariance_tolerance"])
    z_difference = ppm["z"] - primary["z"]
    delta_difference = ppm["delta_chi2"] - primary["delta_chi2"]
    ppm_passed = (
        abs(z_difference) <= invariance_tolerance
        and abs(delta_difference) <= invariance_tolerance
    )

    median_bin_width = float(np.median(window.bin_width))
    stress_spec = manifest.analysis.covariance_stress
    stress_results = []
    separation = np.abs(
        window.wavelength[:, None] - window.wavelength[None, :]
    )
    for rho in sorted(float(item) for item in stress_spec["rho"]):
        for multiplier in sorted(
            float(item) for item in stress_spec["ell_median_bin_width_multipliers"]
        ):
            ell = multiplier * median_bin_width
            correlation = np.eye(window.wavelength.size) + rho * np.exp(
                -separation / ell
            )
            covariance = np.outer(window.uncertainty, window.uncertainty) * correlation
            _, _, metrics = fit_models(
                window.wavelength,
                window.transit_depth,
                window.uncertainty,
                pivot=pivot,
                feature_sigma=feature_sigma,
                covariance=covariance,
            )
            passed = (
                metrics["z"] >= float(stress_spec["minimum_z"])
                and metrics["delta_chi2"]
                >= float(stress_spec["minimum_delta_chi2"])
            )
            stress_results.append(
                {
                    "rho": rho,
                    "ell_median_bin_width_multiplier": multiplier,
                    "ell_micrometres": ell,
                    "amplitude": metrics["amplitude"],
                    "z": metrics["z"],
                    "delta_chi2": metrics["delta_chi2"],
                    "passed": passed,
                }
            )
    stress_passed = all(item["passed"] for item in stress_results)

    monte_spec = manifest.analysis.null_monte_carlo
    monte = null_calibration(
        window.wavelength,
        window.uncertainty,
        evaluate_model(
            window.wavelength,
            m0.beta,
            pivot=pivot,
            feature_sigma=feature_sigma,
        ),
        pivot=pivot,
        feature_sigma=feature_sigma,
        draws=int(monte_spec["draws"]),
        seed=int(monte_spec["seed"]),
    )
    monte_passed = (
        abs(monte["mean_z"]) < float(monte_spec["absolute_mean_z_max"])
        and _in_band(monte["std_z"], monte_spec["std_z"])
        and _in_band(
            monte["two_sided_1p96_fraction"],
            monte_spec["two_sided_1p96_fraction"],
        )
    )

    overall = (
        primary_checks["passed"]
        and loo_passed
        and ppm_passed
        and stress_passed
        and monte_passed
    )
    return {
        "window": {
            "lower_micrometres": manifest.analysis.window_micrometres[0],
            "upper_micrometres": manifest.analysis.window_micrometres[1],
            "inclusive": True,
            "rows": int(window.wavelength.size),
            "rebinning": False,
            "median_bin_width_micrometres": median_bin_width,
        },
        "models": {"m0": _fit_dict(m0, feature=False), "m1": _fit_dict(m1, feature=True)},
        "primary": {
            **primary,
            "expected_fingerprint": dict(sorted(fingerprint.items())),
            "fingerprint_differences": fingerprint_differences,
            "checks": primary_checks,
        },
        "leave_one_out": {
            "minimum_z_required": loo_minimum_z,
            "minimum_observed_z": min(item["z"] for item in leave_one_out),
            "all_amplitudes_positive": all(item["amplitude"] > 0 for item in leave_one_out),
            "passed": loo_passed,
            "fits": leave_one_out,
        },
        "ppm_scale_invariance": {
            "z": ppm["z"],
            "delta_chi2": ppm["delta_chi2"],
            "z_difference": z_difference,
            "delta_chi2_difference": delta_difference,
            "tolerance": invariance_tolerance,
            "passed": ppm_passed,
        },
        "covariance_stress": {
            "status": stress_spec["status"],
            "gating": True,
            "passed": stress_passed,
            "models": stress_results,
        },
        "null_monte_carlo": {
            "draws": int(monte_spec["draws"]),
            "seed": int(monte_spec["seed"]),
            **monte,
            "passed": monte_passed,
        },
        "attribution_diagnostic": attribution_diagnostic(
            full_model, no_co2_model, manifest
        ),
        "passed": overall,
    }


def _package_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "unknown"


def canonical_json_text(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def _render_plot(
    spectrum: Spectrum,
    analysis: dict[str, Any],
    full_model: tuple[np.ndarray, np.ndarray],
    no_co2_model: tuple[np.ndarray, np.ndarray],
    manifest: AtmosphereManifest,
    output_path: Path,
) -> None:
    import matplotlib

    matplotlib.use("Agg", force=True)
    from matplotlib import pyplot as plt

    window = select_frozen_window(spectrum, manifest)
    pivot = manifest.analysis.pivot_micrometres
    feature_sigma = manifest.analysis.feature_sigma_micrometres
    grid = np.linspace(
        manifest.analysis.window_micrometres[0],
        manifest.analysis.window_micrometres[1],
        500,
    )
    m0_beta = np.asarray(
        [analysis["models"]["m0"]["beta0"], analysis["models"]["m0"]["beta1"]]
    )
    m1_beta = np.asarray(
        [
            analysis["models"]["m1"]["beta0"],
            analysis["models"]["m1"]["beta1"],
            analysis["models"]["m1"]["amplitude"],
        ]
    )
    m0_grid = evaluate_model(
        grid, m0_beta, pivot=pivot, feature_sigma=feature_sigma
    )
    m1_grid = evaluate_model(
        grid, m1_beta, pivot=pivot, feature_sigma=feature_sigma
    )
    m0_data = evaluate_model(
        window.wavelength,
        m0_beta,
        pivot=pivot,
        feature_sigma=feature_sigma,
    )

    figure, (top, bottom) = plt.subplots(
        2, 1, figsize=(9, 7), sharex=True, gridspec_kw={"height_ratios": [2, 1]}
    )
    top.errorbar(
        window.wavelength,
        window.transit_depth * 1e6,
        yerr=window.uncertainty * 1e6,
        xerr=window.bin_width * 0.5,
        fmt="o",
        color="#1f4e79",
        markersize=4,
        capsize=2,
        label="Published FIREFLy spectrum",
    )
    top.plot(grid, m0_grid * 1e6, color="#777777", label="M0: linear baseline")
    top.plot(grid, m1_grid * 1e6, color="#c43c35", label="M1: baseline + feature")
    top.set_ylabel("Transit depth [ppm]")
    top.set_title("WASP-39 b atmospheric positive control")
    top.legend(loc="best")
    top.grid(alpha=0.2)

    bottom.errorbar(
        window.wavelength,
        (window.transit_depth - m0_data) * 1e6,
        yerr=window.uncertainty * 1e6,
        fmt="o",
        color="#1f4e79",
        markersize=4,
        capsize=2,
        label="Data − M0",
    )
    bottom.plot(
        grid,
        (m1_grid - m0_grid) * 1e6,
        color="#c43c35",
        label="M1 − M0 after refitting baseline",
    )
    full_wavelength, full_depth = full_model
    no_co2_wavelength, no_co2_depth = no_co2_model
    model_mask = (
        (no_co2_wavelength >= manifest.analysis.window_micrometres[0])
        & (no_co2_wavelength <= manifest.analysis.window_micrometres[1])
    )
    model_wavelength = no_co2_wavelength[model_mask]
    model_difference = (
        np.interp(model_wavelength, full_wavelength, full_depth)
        - no_co2_depth[model_mask]
    )
    bottom.plot(
        model_wavelength,
        model_difference * 1e6,
        linestyle="--",
        color="#6a3d9a",
        label="ScCHIMERA full − no CO₂ (non-gating)",
    )
    bottom.axhline(0, color="black", linewidth=0.7)
    bottom.set_xlabel("Wavelength [µm]")
    bottom.set_ylabel("Difference [ppm]")
    bottom.legend(loc="best", fontsize=8)
    bottom.grid(alpha=0.2)
    figure.tight_layout()
    figure.savefig(
        output_path,
        dpi=150,
        metadata={"Software": "atmosphere-benchmark 0.1.0"},
    )
    plt.close(figure)


def run_benchmark(
    extracted_dir: Path,
    output_dir: Path,
    manifest: AtmosphereManifest,
) -> dict[str, Any]:
    extracted_dir = Path(extracted_dir)
    primary_spec = manifest.member_for_role("primary_spectrum")
    full_spec = manifest.member_for_role("attribution_full_model")
    no_co2_spec = manifest.member_for_role("attribution_no_co2_model")
    verified = [
        verify_member(extracted_dir / member.path, member)
        for member in (primary_spec, full_spec, no_co2_spec)
    ]
    spectrum = load_spectrum(
        extracted_dir / primary_spec.path,
        expected_columns=manifest.spectrum.columns,
        expected_rows=manifest.spectrum.row_count,
    )
    full_model = load_two_column_model(extracted_dir / full_spec.path)
    no_co2_model = load_two_column_model(extracted_dir / no_co2_spec.path)
    analysis = analyze_spectrum(
        spectrum,
        manifest,
        full_model=full_model,
        no_co2_model=no_co2_model,
    )
    result: dict[str, Any] = {
        "schema_version": 1,
        "benchmark_id": manifest.benchmark_id,
        "source": {
            "archive_doi": manifest.archive.doi,
            "archive_sha256": manifest.archive.sha256,
            "license_spdx": manifest.archive.license_spdx,
            "members": sorted(verified, key=lambda item: str(item["role"])),
        },
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
    with tempfile.TemporaryDirectory(
        prefix=".atmosphere-benchmark-", dir=output_dir
    ) as raw:
        temporary = Path(raw)
        json_path = temporary / "atmosphere_benchmark.json"
        plot_path = temporary / "atmosphere_feature.png"
        json_path.write_text(canonical_json_text(result), encoding="utf-8")
        _render_plot(
            spectrum,
            analysis,
            full_model,
            no_co2_model,
            manifest,
            plot_path,
        )
        os.replace(json_path, output_dir / json_path.name)
        os.replace(plot_path, output_dir / plot_path.name)
    return result
