from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np

from .manifest import SyntheticManifest
from .truth import TruthBundle


class ScoringError(ValueError):
    """Raised when predictions and separately held truth cannot be joined safely."""


_INVARIANCE_KEYS = {
    "deterministic_generation",
    "fraction_unit_invariance",
    "order_invariance",
    "percent_nanometre_unit_invariance",
}
_UNSAFE_SPECIFIC_CLASSIFICATION_FAMILIES = {
    "null",
    "correlated_null",
    "stellar_only",
    "detector_only",
    "omitted_template",
    "ambiguous_cancellation",
}


def _rate(numerator: int, denominator: int) -> dict[str, float | int]:
    return {
        "denominator": denominator,
        "numerator": numerator,
        "rate": float(numerator / denominator) if denominator else 0.0,
    }


def _is_supported(classification: str) -> bool:
    return classification in {"planetary_supported", "stellar_supported", "joint_supported"}


def _unsafe_specific_classification(family: str, classification: str, *, error: bool) -> bool:
    if error:
        return True
    if family in {"null", "correlated_null", "detector_only"}:
        return _is_supported(classification)
    if family == "stellar_only":
        return classification in {"planetary_supported", "joint_supported"}
    if family in {"omitted_template", "ambiguous_cancellation"}:
        return _is_supported(classification)
    return False


def _summarize_mode(
    manifest: SyntheticManifest,
    truth: TruthBundle,
    predictions: dict[str, Any],
    mode: str,
) -> dict[str, Any]:
    by_id = {item["case_id"]: item for item in predictions["cases"]}
    truths = {item.case_id: item for item in truth.cases}
    if len(by_id) != len(predictions["cases"]):
        raise ScoringError("prediction case IDs must be unique")
    missing = sorted(set(truths) - set(by_id))
    extra = sorted(set(by_id) - set(truths))

    family_rows: dict[str, list[tuple[Any, dict[str, Any] | None]]] = defaultdict(list)
    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    failed = 0
    coverage_counts = {"50": 0, "80": 0, "95": 0}
    coverage_denominator = 0
    pulls: list[float] = []
    coefficient_errors: dict[str, list[float]] = {"planet": [], "stellar": []}
    false_numerator = 0
    false_denominator = 0

    for case_id, item in truths.items():
        prediction = by_id.get(case_id)
        usable = prediction is not None and prediction["status"] == "complete" and mode in prediction["modes"]
        mode_result = prediction["modes"][mode] if usable else None
        if not usable:
            failed += 1
        classification = mode_result["classification"] if mode_result is not None else "evaluation_error"
        confusion[item.expected_origin][classification] += 1
        family_rows[item.family].append((item, mode_result))
        if item.family in _UNSAFE_SPECIFIC_CLASSIFICATION_FAMILIES:
            false_denominator += 1
            false_numerator += int(
                _unsafe_specific_classification(item.family, classification, error=not usable)
            )
        if item.coverage_eligible:
            for parameter, true_value in (
                ("planet", item.planet_coefficient),
                ("stellar", item.stellar_coefficient),
            ):
                coverage_denominator += 1
                if mode_result is None:
                    continue
                estimate = mode_result["full_model"]["parameters"][parameter]
                se = float(estimate["se"])
                error_value = float(estimate["estimate"]) - true_value
                coefficient_errors[parameter].append(error_value)
                pulls.append(error_value / se)
                for level in coverage_counts:
                    low, high = estimate["intervals"][level]
                    coverage_counts[level] += int(low <= true_value <= high)

    family_metrics: dict[str, Any] = {}
    for family in manifest.families:
        rows = family_rows[family]
        denominator = len(rows)
        counts: dict[str, int] = defaultdict(int)
        errors = 0
        wrong = 0
        for item, result in rows:
            classification = result["classification"] if result is not None else "evaluation_error"
            counts[classification] += 1
            errors += int(result is None)
            wrong += int(
                _unsafe_specific_classification(family, classification, error=result is None)
            )
        family_metrics[family] = {
            "classifications": dict(sorted(counts.items())),
            "errors": errors,
            "expected_origin": rows[0][0].expected_origin if rows else None,
            "unsafe_specific_classification": _rate(wrong, denominator),
            "scheduled": denominator,
        }

    def class_rate(family: str, accepted: set[str]) -> dict[str, float | int]:
        rows = family_rows[family]
        return _rate(
            sum(result is not None and result["classification"] in accepted for _, result in rows),
            len(rows),
        )

    coverage = {
        level: _rate(numerator, coverage_denominator)
        for level, numerator in coverage_counts.items()
    }
    pull_array = np.asarray(pulls, dtype=np.float64)
    bias = {}
    for parameter, values in coefficient_errors.items():
        array = np.asarray(values, dtype=np.float64)
        bias[parameter] = {
            "available": int(array.size),
            "mean_error": float(np.mean(array)) if array.size else None,
            "rmse": float(np.sqrt(np.mean(np.square(array)))) if array.size else None,
        }
    maximum_family, maximum_family_rate = max(
        (
            (family, family_metrics[family]["unsafe_specific_classification"])
            for family in manifest.families
            if family in _UNSAFE_SPECIFIC_CLASSIFICATION_FAMILIES
        ),
        key=lambda item: float(item[1]["rate"]),
    )
    return {
        "diagnostic_classification": {
            "ambiguous_cancellation": class_rate(
                "ambiguous_cancellation", {"conflicting_single_template_support"}
            ),
            "omitted_template": class_rate("omitted_template", {"model_inadequate"}),
        },
        "confusion": {key: dict(sorted(value.items())) for key, value in sorted(confusion.items())},
        "coefficient_bias": bias,
        "coverage": coverage,
        "coverage_scheduled_parameter_estimates": coverage_denominator,
        "evaluation_errors": failed,
        "extra_prediction_ids": extra,
        "family_metrics": family_metrics,
        "maximum_family_unsafe_specific_classification": {
            "family": maximum_family,
            **maximum_family_rate,
        },
        "pooled_unsafe_specific_classification": _rate(false_numerator, false_denominator),
        "missing_prediction_ids": missing,
        "power": {
            "joint": class_rate("planet_stellar", {"joint_supported"}),
            "stellar": class_rate("stellar_only", {"stellar_supported"}),
            "strong_planet": class_rate("strong_planet", {"planetary_supported"}),
        },
        "pulls": {
            "available": int(pull_array.size),
            "mean": float(np.mean(pull_array)) if pull_array.size else None,
            "std": float(np.std(pull_array, ddof=1)) if pull_array.size > 1 else None,
        },
        "weak_planet_promotion": class_rate(
            "weak_planet", {"planetary_supported", "joint_supported"}
        ),
        "weak_planet_abstention": class_rate(
            "weak_planet", {"none", "conflicting_single_template_support"}
        ),
    }


def score_predictions(
    manifest: SyntheticManifest,
    truth: TruthBundle,
    predictions: dict[str, Any],
    *,
    invariance_checks: dict[str, bool],
) -> dict[str, Any]:
    if set(invariance_checks) != _INVARIANCE_KEYS or any(
        type(value) is not bool for value in invariance_checks.values()
    ):
        raise ScoringError("invariance checks must contain the exact frozen boolean key set")
    if (
        truth.schema_version != 1
        or truth.benchmark_id != manifest.benchmark_id
        or truth.contract_sha256 != manifest.contract_sha256
        or predictions.get("benchmark_id") != manifest.benchmark_id
        or predictions.get("contract_sha256") != manifest.contract_sha256
        or predictions.get("evaluator_schema_version") != 1
        or float(predictions.get("promotion_z", float("nan"))) != manifest.promotion_z
    ):
        raise ScoringError("prediction/truth artifacts do not match the frozen manifest")
    if truth.benchmark_id != predictions["benchmark_id"] or truth.contract_sha256 != predictions["contract_sha256"]:
        raise ScoringError("prediction/truth benchmark contract mismatch")
    correct = _summarize_mode(manifest, truth, predictions, "correct_covariance")
    naive = _summarize_mode(manifest, truth, predictions, "naive_diagonal")
    gates = manifest.raw["preflight_gates"]

    checks = {
        "all_cases_evaluated": correct["evaluation_errors"] == 0
        and not correct["extra_prediction_ids"],
        "planet_bias": abs(float(correct["coefficient_bias"]["planet"]["mean_error"]))
        <= gates["coefficient_bias_abs_max"],
        "stellar_bias": abs(float(correct["coefficient_bias"]["stellar"]["mean_error"]))
        <= gates["coefficient_bias_abs_max"],
        "coverage_50": gates["coverage"]["50"][0]
        <= correct["coverage"]["50"]["rate"]
        <= gates["coverage"]["50"][1],
        "coverage_80": gates["coverage"]["80"][0]
        <= correct["coverage"]["80"]["rate"]
        <= gates["coverage"]["80"][1],
        "coverage_95": gates["coverage"]["95"][0]
        <= correct["coverage"]["95"]["rate"]
        <= gates["coverage"]["95"][1],
        "maximum_family_unsafe_specific_classification": correct[
            "maximum_family_unsafe_specific_classification"
        ]["rate"]
        <= gates["maximum_family_unsafe_specific_classification_max"],
        "pooled_unsafe_specific_classification": correct[
            "pooled_unsafe_specific_classification"
        ]["rate"]
        <= gates["pooled_unsafe_specific_classification_max"],
        "joint_power": correct["power"]["joint"]["rate"] >= gates["joint_power_min"],
        "ambiguous_cancellation_classification": correct["diagnostic_classification"]
        ["ambiguous_cancellation"]["rate"]
        >= gates["ambiguous_cancellation_classification_min"],
        "omitted_model_inadequacy_detection": correct["diagnostic_classification"]
        ["omitted_template"]["rate"]
        >= gates["omitted_model_inadequacy_detection_min"],
        "pull_mean": abs(float(correct["pulls"]["mean"])) <= gates["pull_mean_abs_max"],
        "pull_std": gates["pull_std"][0]
        <= float(correct["pulls"]["std"])
        <= gates["pull_std"][1],
        "stellar_power": correct["power"]["stellar"]["rate"] >= gates["stellar_power_min"],
        "strong_planet_power": correct["power"]["strong_planet"]["rate"]
        >= gates["strong_planet_power_min"],
        "weak_planet_abstention": correct["weak_planet_abstention"]["rate"]
        >= gates["weak_planet_abstention_min"],
        "weak_planet_promotion": correct["weak_planet_promotion"]["rate"]
        <= gates["weak_planet_promotion_max"],
    }
    checks.update(invariance_checks)
    status = "PASS" if all(checks.values()) else "INCOMPLETE"
    return {
        "engineering_preflight_status": status,
        "gate_checks": dict(sorted(checks.items())),
        "metrics": {
            "correct_covariance": correct,
            "naive_diagonal_diagnostic": naive,
        },
        "scope_note": (
            "A B3a pass is a public synthetic engineering smoke result only; it is not B3 "
            "completion and does not establish real-data readiness."
        ),
    }
