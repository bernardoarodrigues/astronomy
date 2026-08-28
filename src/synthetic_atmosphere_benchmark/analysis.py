from __future__ import annotations

import hashlib
import platform
from dataclasses import replace
from importlib import metadata
from pathlib import Path
from typing import Any

import numpy as np

from .canonical import atomic_write_text, canonical_json_text
from .challenge import ChallengeBundle, ChallengeCase
from .evaluator import equivalent_predictions, evaluate_challenge
from .generator import generate_public_suite
from .manifest import SyntheticManifest
from .scorer import score_predictions
from .source import build_scaffold, scaffold_fingerprints, verify_sources


class AnalysisError(RuntimeError):
    """Raised when the frozen preflight contract cannot be executed."""


def _package_version() -> str:
    try:
        return metadata.version("voyager-radio-benchmark")
    except metadata.PackageNotFoundError:
        from . import __version__

        return __version__


def _assert_fingerprints(manifest: SyntheticManifest, actual: dict[str, object]) -> None:
    expected = manifest.raw["derived_fingerprints"]
    for key in (
        "wavelength_sha256",
        "width_sha256",
        "uncertainty_sha256",
        "planet_template_sha256",
        "stellar_template_sha256",
    ):
        if actual[key] != expected[key]:
            raise AnalysisError(f"derived fingerprint mismatch for {key}: {actual[key]}")
    if not np.isclose(
        actual["template_weighted_correlation"],
        expected["template_weighted_correlation"],
        rtol=0.0,
        atol=1e-12,
    ):
        raise AnalysisError("derived template correlation changed")


def _scaled_challenge(
    challenge: ChallengeBundle,
    *,
    depth_unit: str,
    wavelength_unit: str,
) -> ChallengeBundle:
    depth_scale = {"ppm": 1.0, "fraction": 1e-6, "percent": 1e-4}[depth_unit]
    wavelength_scale = {"micrometre": 1.0, "nanometre": 1000.0}[wavelength_unit]
    return replace(
        challenge,
        depth_unit=depth_unit,
        wavelength_unit=wavelength_unit,
        wavelength=tuple(value * wavelength_scale for value in challenge.wavelength),
        bin_width=tuple(value * wavelength_scale for value in challenge.bin_width),
        uncertainty=tuple(value * depth_scale for value in challenge.uncertainty),
        detector_split=challenge.detector_split * wavelength_scale,
        planet_template=tuple(value * depth_scale for value in challenge.planet_template),
        stellar_template=tuple(value * depth_scale for value in challenge.stellar_template),
        cases=tuple(
            replace(case, synthetic_depth=tuple(value * depth_scale for value in case.synthetic_depth))
            for case in challenge.cases
        ),
    )


def run_preflight(manifest: SyntheticManifest, extracted_root: Path) -> dict[str, Any]:
    source_records = verify_sources(manifest, extracted_root)
    scaffold = build_scaffold(manifest, extracted_root)
    fingerprints = scaffold_fingerprints(scaffold)
    _assert_fingerprints(manifest, fingerprints)
    challenge, truth = generate_public_suite(manifest, scaffold)
    repeat_challenge, repeat_truth = generate_public_suite(manifest, scaffold)
    predictions = evaluate_challenge(challenge, promotion_z=manifest.promotion_z)

    reversed_challenge = replace(challenge, cases=tuple(reversed(challenge.cases)))
    order_predictions = evaluate_challenge(reversed_challenge, promotion_z=manifest.promotion_z)
    fraction_predictions = evaluate_challenge(
        _scaled_challenge(challenge, depth_unit="fraction", wavelength_unit="micrometre"),
        promotion_z=manifest.promotion_z,
    )
    percent_nm_predictions = evaluate_challenge(
        _scaled_challenge(challenge, depth_unit="percent", wavelength_unit="nanometre"),
        promotion_z=manifest.promotion_z,
    )
    invariance = {
        "deterministic_generation": canonical_json_text(challenge.to_dict())
        == canonical_json_text(repeat_challenge.to_dict())
        and canonical_json_text(truth.to_dict()) == canonical_json_text(repeat_truth.to_dict()),
        "fraction_unit_invariance": equivalent_predictions(predictions, fraction_predictions),
        "order_invariance": equivalent_predictions(predictions, order_predictions),
        "percent_nanometre_unit_invariance": equivalent_predictions(predictions, percent_nm_predictions),
    }
    score = score_predictions(manifest, truth, predictions, invariance_checks=invariance)
    return {
        "allowed_claim_if_pass": manifest.allowed_claim,
        "benchmark_id": manifest.benchmark_id,
        "challenge": challenge,
        "contract_sha256": manifest.contract_sha256,
        "engineering_preflight_status": score["engineering_preflight_status"],
        "current_allowed_report": (
            manifest.allowed_claim
            if score["engineering_preflight_status"] == "PASS"
            else manifest.incomplete_claim
        ),
        "environment": {
            "matplotlib": metadata.version("matplotlib"),
            "numpy": np.__version__,
            "package": _package_version(),
            "python": platform.python_version(),
        },
        "execution_status": "complete",
        "fingerprints": fingerprints,
        "predictions": predictions,
        "prohibited_claims": list(manifest.prohibited_claims),
        "real_data_readiness": "not_established",
        "science_state": "not_applicable_synthetic",
        "sealed_b3b_status": "pending_not_executed",
        "success_claim_available": score["engineering_preflight_status"] == "PASS",
        "score": score,
        "source_records": source_records,
        "truth": truth,
        "authorizes_k2_18": False,
    }


def _plot(path: Path, report: dict[str, Any]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    metrics = report["score"]["metrics"]["correct_covariance"]
    labels = [
        "pooled unsafe\nspecific class",
        "planet\npower",
        "stellar\npower",
        "joint\npower",
        "omitted model\ninadequacy",
        "cancellation\nclassified",
    ]
    values = [
        metrics["pooled_unsafe_specific_classification"]["rate"],
        metrics["power"]["strong_planet"]["rate"],
        metrics["power"]["stellar"]["rate"],
        metrics["power"]["joint"]["rate"],
        metrics["diagnostic_classification"]["omitted_template"]["rate"],
        metrics["diagnostic_classification"]["ambiguous_cancellation"]["rate"],
    ]
    figure, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    colors = ["#b94a48"] + ["#376a9e"] * 3 + ["#6f5a8a"] * 2
    axes[0].bar(np.arange(len(values)), values, color=colors)
    axes[0].set_xticks(np.arange(len(values)), labels)
    axes[0].set_ylim(0, 1.05)
    axes[0].set_ylabel("Observed public-preflight rate")
    axes[0].set_title("Correct-covariance decisions")
    coverage = metrics["coverage"]
    coverage_labels = ["50%", "80%", "95%"]
    observed = [coverage[level]["rate"] for level in ("50", "80", "95")]
    axes[1].bar(np.arange(3), observed, color="#3f7f66", label="observed")
    axes[1].scatter(np.arange(3), [0.5, 0.8, 0.95], color="black", marker="_", s=300, label="nominal")
    axes[1].set_xticks(np.arange(3), coverage_labels)
    axes[1].set_ylim(0, 1.05)
    axes[1].set_ylabel("Empirical coverage")
    axes[1].set_title("Aggregate smoke coverage")
    axes[1].legend(loc="lower right", frameon=False)
    figure.suptitle(
        f"B3a synthetic engineering preflight: {report['score']['engineering_preflight_status']}\n"
        "not B3 completion; no real-atmosphere inference",
        fontsize=11,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.stem}.part{path.suffix}")
    figure.savefig(
        temporary,
        dpi=150,
        metadata={"Software": "synthetic-atmosphere-benchmark"},
    )
    plt.close(figure)
    temporary.replace(path)


def write_artifacts(output_dir: Path, result: dict[str, Any]) -> dict[str, dict[str, object]]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    payloads = {
        "challenge": result["challenge"].to_dict(),
        "predictions": result["predictions"],
        "truth": result["truth"].to_dict(),
    }
    report = {key: value for key, value in result.items() if key not in {"challenge", "predictions", "truth"}}
    paths = {
        "challenge": output / "challenge.json",
        "predictions": output / "predictions.json",
        "report": output / "synthetic_atmosphere_preflight.json",
        "truth": output / "truth.json",
    }
    for key, payload in payloads.items():
        atomic_write_text(paths[key], canonical_json_text(payload))
    atomic_write_text(paths["report"], canonical_json_text(report))
    plot_path = output / "synthetic_atmosphere_preflight.png"
    _plot(plot_path, report)
    paths["plot"] = plot_path
    records: dict[str, dict[str, object]] = {}
    for key, path in sorted(paths.items()):
        content = path.read_bytes()
        records[key] = {
            "path": str(path),
            "sha256": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
        }
    return records
