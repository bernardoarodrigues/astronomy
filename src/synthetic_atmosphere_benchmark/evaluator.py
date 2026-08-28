from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .challenge import ChallengeBundle


_INTERVAL_Z = {
    "50": 0.6744897501960817,
    "80": 1.2815515655446004,
    "95": 1.959963984540054,
}


class EvaluationError(ValueError):
    """Raised when a truth-free challenge cannot be evaluated."""


@dataclass(frozen=True)
class Fit:
    beta: np.ndarray
    covariance: np.ndarray
    chi2: float
    dof: int


def _depth_to_ppm(unit: str) -> float:
    return {"ppm": 1.0, "fraction": 1_000_000.0, "percent": 10_000.0}[unit]


def _wavelength_to_um(unit: str) -> float:
    return {"micrometre": 1.0, "nanometre": 0.001}[unit]


def _covariance(uncertainty: np.ndarray, detector: np.ndarray, kind: str, rho: float) -> np.ndarray:
    if kind == "diagonal":
        return np.diag(np.square(uncertainty))
    if kind != "within_detector_ar1":
        raise EvaluationError(f"unsupported covariance {kind!r}")
    index = np.arange(uncertainty.size)
    distance = np.abs(index[:, None] - index[None, :])
    same = detector[:, None] == detector[None, :]
    correlation = np.where(same, np.power(rho, distance), 0.0)
    return uncertainty[:, None] * uncertainty[None, :] * correlation


def _fit(design: np.ndarray, values: np.ndarray, covariance: np.ndarray) -> Fit:
    cholesky = np.linalg.cholesky(covariance)
    whitened_design = np.linalg.solve(cholesky, design)
    whitened_values = np.linalg.solve(cholesky, values)
    normal = whitened_design.T @ whitened_design
    parameter_covariance = np.linalg.inv(normal)
    beta = parameter_covariance @ (whitened_design.T @ whitened_values)
    residual = whitened_values - whitened_design @ beta
    return Fit(beta, parameter_covariance, float(residual @ residual), int(values.size - design.shape[1]))


def _intervals(value: float, se: float) -> dict[str, list[float]]:
    return {
        level: [float(value - multiplier * se), float(value + multiplier * se)]
        for level, multiplier in _INTERVAL_Z.items()
    }


def _fit_payload(fit: Fit, *, parameter_names: tuple[str, ...]) -> dict[str, Any]:
    standard_errors = np.sqrt(np.diag(fit.covariance))
    parameters = {}
    for index, name in enumerate(parameter_names):
        parameters[name] = {
            "estimate": float(fit.beta[index]),
            "intervals": _intervals(float(fit.beta[index]), float(standard_errors[index])),
            "se": float(standard_errors[index]),
            "z": float(fit.beta[index] / standard_errors[index]),
        }
    return {"chi2": fit.chi2, "dof": fit.dof, "parameters": parameters}


def _classification(full: Fit, planet_only: Fit, stellar_only: Fit, promotion_z: float) -> str:
    lack_of_fit = full.chi2 > full.dof + 4.0 * np.sqrt(2.0 * full.dof)
    if lack_of_fit:
        return "model_inadequate"
    full_se = np.sqrt(np.diag(full.covariance))
    planet_z = float(full.beta[3] / full_se[3])
    stellar_z = float(full.beta[4] / full_se[4])
    planet_single_z = float(planet_only.beta[3] / np.sqrt(planet_only.covariance[3, 3]))
    stellar_single_z = float(stellar_only.beta[3] / np.sqrt(stellar_only.covariance[3, 3]))
    planet_promoted = planet_z >= promotion_z
    stellar_promoted = stellar_z >= promotion_z
    if planet_promoted and stellar_promoted:
        return "joint_supported"
    if planet_promoted:
        return "planetary_supported"
    if stellar_promoted:
        return "stellar_supported"
    if abs(planet_single_z) >= promotion_z and abs(stellar_single_z) >= promotion_z:
        return "conflicting_single_template_support"
    return "none"


def evaluate_challenge(
    challenge: ChallengeBundle,
    *,
    promotion_z: float = 3.0,
) -> dict[str, Any]:
    """Evaluate a challenge using only public inputs; no truth object is accepted."""

    challenge.validate()
    depth_factor = _depth_to_ppm(challenge.depth_unit)
    wavelength_factor = _wavelength_to_um(challenge.wavelength_unit)
    wavelength = np.asarray(challenge.wavelength, dtype=np.float64) * wavelength_factor
    width = np.asarray(challenge.bin_width, dtype=np.float64) * wavelength_factor
    del width  # Width is schema-validated and frozen, but the linear evaluator does not rebin.
    uncertainty = np.asarray(challenge.uncertainty, dtype=np.float64) * depth_factor
    planet = np.asarray(challenge.planet_template, dtype=np.float64) * depth_factor
    stellar = np.asarray(challenge.stellar_template, dtype=np.float64) * depth_factor
    split = challenge.detector_split * wavelength_factor
    detector = wavelength >= split
    trend = wavelength - float(np.average(wavelength, weights=1.0 / np.square(uncertainty)))
    trend /= float(np.ptp(wavelength))
    nuisance = np.column_stack((np.ones(wavelength.size), trend, detector.astype(np.float64)))
    full_design = np.column_stack((nuisance, planet, stellar))
    planet_design = np.column_stack((nuisance, planet))
    stellar_design = np.column_stack((nuisance, stellar))

    predictions = []
    for case in challenge.cases:
        values = np.asarray(case.synthetic_depth, dtype=np.float64) * depth_factor
        modes: dict[str, Any] = {}
        error = None
        try:
            for mode in ("correct_covariance", "naive_diagonal"):
                kind = case.covariance_kind if mode == "correct_covariance" else "diagonal"
                rho = case.covariance_rho if mode == "correct_covariance" else 0.0
                covariance = _covariance(uncertainty, detector, kind, rho)
                full = _fit(full_design, values, covariance)
                planet_only = _fit(planet_design, values, covariance)
                stellar_only = _fit(stellar_design, values, covariance)
                modes[mode] = {
                    "classification": _classification(full, planet_only, stellar_only, promotion_z),
                    "full_model": _fit_payload(
                        full,
                        parameter_names=("intercept", "wavelength_trend", "nrs2_step", "planet", "stellar"),
                    ),
                    "planet_only_z": float(
                        planet_only.beta[3] / np.sqrt(planet_only.covariance[3, 3])
                    ),
                    "stellar_only_z": float(
                        stellar_only.beta[3] / np.sqrt(stellar_only.covariance[3, 3])
                    ),
                }
        except (ValueError, np.linalg.LinAlgError, FloatingPointError) as exc:
            error = f"{type(exc).__name__}: {exc}"
        predictions.append(
            {
                "case_id": case.case_id,
                "error": error,
                "modes": modes,
                "status": "complete" if error is None else "error",
            }
        )
    predictions.sort(key=lambda item: item["case_id"])
    return {
        "benchmark_id": challenge.benchmark_id,
        "cases": predictions,
        "contract_sha256": challenge.contract_sha256,
        "evaluator_schema_version": 1,
        "promotion_z": promotion_z,
    }


def equivalent_predictions(left: dict[str, Any], right: dict[str, Any], *, atol: float = 1e-9) -> bool:
    left_cases = {item["case_id"]: item for item in left["cases"]}
    right_cases = {item["case_id"]: item for item in right["cases"]}
    if left_cases.keys() != right_cases.keys():
        return False
    for case_id in left_cases:
        a, b = left_cases[case_id], right_cases[case_id]
        if a["status"] != b["status"] or a["error"] != b["error"]:
            return False
        for mode in ("correct_covariance", "naive_diagonal"):
            if a["modes"][mode]["classification"] != b["modes"][mode]["classification"]:
                return False
            for parameter in ("intercept", "wavelength_trend", "nrs2_step", "planet", "stellar"):
                pa = a["modes"][mode]["full_model"]["parameters"][parameter]
                pb = b["modes"][mode]["full_model"]["parameters"][parameter]
                for key in ("estimate", "se", "z"):
                    if not np.isclose(pa[key], pb[key], rtol=1e-10, atol=atol):
                        return False
    return True
