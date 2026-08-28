from __future__ import annotations

import json
import os
import platform
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from k218_repeatability.analysis import AnalysisError, analyze_cell, build_global_grid
from k218_repeatability.data import VisitSpectrum, load_spectrum
from k218_repeatability.extraction import verify_extracted
from k218_repeatability.manifest import K218Manifest

from . import __version__


def classify_context(cells: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply the frozen two-view descriptor without treating views as independent."""

    required = {("Eureka", "visit_1"), ("exoTEDRF", "visit_1")}
    observed = [(str(cell.get("reduction")), str(cell.get("visit"))) for cell in cells]
    observed_set = set(observed)
    duplicate = sorted(key for key in observed_set if observed.count(key) != 1)
    missing = sorted(required - observed_set)
    unexpected = sorted(observed_set - required)
    failed = sorted(
        (str(cell.get("reduction")), str(cell.get("visit")))
        for cell in cells
        if cell.get("criterion_checks", {}).get("cell_passed") is not True
    )
    passed = (
        len(cells) == 2
        and not duplicate
        and not missing
        and not unexpected
        and not failed
    )
    return {
        "science_state": "not_applicable_historical_context",
        "context_descriptor": (
            "positive_local_contrast_in_both_correlated_views"
            if passed
            else "criterion_not_met"
        ),
        "required_correlated_view_count": 2,
        "observed_correlated_view_count": len(cells),
        "missing_views": [list(value) for value in missing],
        "duplicate_views": [list(value) for value in duplicate],
        "unexpected_views": [list(value) for value in unexpected],
        "failed_views": [list(value) for value in failed],
        "all_required_correlated_views_complete_and_passed": passed,
    }


def analyze_spectra(
    spectra: list[tuple[str, VisitSpectrum]], manifest: K218Manifest
) -> dict[str, Any]:
    grid = build_global_grid(manifest)
    cells = [
        analyze_cell(spectrum, grid, manifest, source_role=role)
        for role, spectrum in sorted(spectra, key=lambda item: item[1].reduction)
    ]
    context = classify_context(cells)
    by_reduction = {str(cell["reduction"]): cell for cell in cells}
    paired: dict[str, Any]
    if set(by_reduction) == {"Eureka", "exoTEDRF"} and all(
        cell.get("nominal", {}).get("valid") is True for cell in by_reduction.values()
    ):
        paired = {
            "valid": True,
            "delta_amplitude_ppm_eureka_minus_exotedrf": float(
                by_reduction["Eureka"]["nominal"]["amplitude_ppm"]
                - by_reduction["exoTEDRF"]["nominal"]["amplitude_ppm"]
            ),
            "significance": "not_evaluated_cross_reduction_covariance_unavailable",
            "comparison_only": True,
        }
    else:
        paired = {
            "valid": False,
            "significance": "not_evaluated_cross_reduction_covariance_unavailable",
            "comparison_only": True,
            "error": "both valid correlated views are required",
        }
    return {
        "analysis_label": "retrospective_historical_c1_local_contrast_context",
        "model": manifest.analysis_contract["model"],
        "z_interpretation": "retrospective standardized contrast; not discovery significance",
        "global_grid": {
            "definition": "e_k=1 micrometre*exp(k/100)",
            "first_edge_index": manifest.rebinning.first_edge_index,
            "last_edge_index": manifest.rebinning.last_edge_index,
            "edge_sha256": grid.edge_sha256,
            "edge_count": int(grid.edges_micrometres.size),
            "output_bin_count": int(grid.centres_micrometres.size),
            "edges_micrometres": [float(value) for value in grid.edges_micrometres],
            "identical_to_committed_go2372_grid": True,
        },
        "cells": cells,
        "paired_correlated_view_difference": paired,
        "evidence_structure": {
            "evidence_units": 1,
            "paired_correlated_views": 2,
            "independent_reduction_evidence": False,
            "cross_reduction_z_combination": "prohibited_not_computed",
            "cross_reduction_voting": "prohibited_not_performed",
            "pooling_with_go2372": "prohibited_not_performed",
            "comparison_to_go2372": "descriptive_only_not_inferential",
        },
        "context": context,
    }


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    try:
        return (
            json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AnalysisError(f"C1 result cannot be serialized canonically: {exc}") from exc


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, delete=False
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
    fig, axes = plt.subplots(1, 2, figsize=(10.0, 4.0), dpi=120, sharex=True, sharey=True)
    for axis, cell in zip(axes, analysis["cells"]):
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
        axis.plot(wavelength, model, color="#a33b20", linewidth=1.4, label="unchanged local fit")
        axis.axvspan(4.05, 4.55, color="#d9a441", alpha=0.12)
        axis.set_title(
            f"C1 / {cell['reduction']}  A={nominal['amplitude_ppm']:.1f} ppm, z={nominal['z']:.2f}",
            fontsize=9,
        )
        axis.set_xlabel("Wavelength (micrometres)")
        axis.grid(alpha=0.18, linewidth=0.5)
    axes[0].set_ylabel("Published transit depth (ppm)")
    axes[0].legend(loc="best", fontsize=7, frameon=False)
    fig.suptitle(
        "K2-18 b historical GO-2722 C1 local-contrast context\n"
        "Retrospective; correlated views; no molecule or GO-2372 inference",
        fontsize=11,
    )
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.89))
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
        fig.savefig(
            temporary,
            format="png",
            dpi=120,
            metadata={"Software": "k218_c1_context 0.1.0"},
        )
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        plt.close(fig)
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def run_diagnostic(
    extracted_dir: Path, output_dir: Path, manifest: K218Manifest
) -> dict[str, Any]:
    verified = verify_extracted(extracted_dir, manifest)
    spectra = [
        (
            member.role,
            load_spectrum(Path(extracted_dir) / member.path, member, manifest),
        )
        for member in manifest.members
    ]
    analysis = analyze_spectra(spectra, manifest)
    context = analysis["context"]
    result = {
        "schema_version": 1,
        "benchmark_id": manifest.benchmark_id,
        "execution_status": "PASS",
        **manifest.output_contract,
        "context_descriptor": context["context_descriptor"],
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
        "visit": {
            "paper_label": "C1",
            "program_id": "GO-2722",
            "observation_date_utc": "2023-01-20",
            "evidence_unit": "GO-2722-C1-photons",
            "views": ["Eureka", "exoTEDRF"],
        },
        "analysis": analysis,
        "transparency": {
            "blind_or_pre_unblinded": False,
            "method_status": "unchanged_committed_go2372_numerical_method",
            "reason": (
                "The numerical method was already committed for C2/C3 and is reused unchanged, "
                "but the first few C1 table rows had been displayed while checking headers before "
                "this C1 implementation."
            ),
            "post_publication": True,
            "held_out": False,
            "post_run_editorial_clarification": (
                "After the first execution, two limitation labels were made more precise and "
                "the Schmidt et al. provenance citation was added. No input, numerical method, "
                "threshold, descriptor rule, or result value changed."
            ),
            "limitations": [
                "substantially shorter out-of-transit time baseline in C1",
                (
                    "published spot-treatment disagreement: Hu et al. masked a C1 "
                    "spot-crossing event in Eureka, while Schmidt et al. report no spot "
                    "crossing in the NIRSpec light curves and treat the event as "
                    "NIRISS-specific; these spectra cannot adjudicate the disagreement"
                ),
                "the two reduction views share photons",
                "post-publication and not held out",
                "published covariance is unavailable; diagonal and assumed native AR(1) covariances are diagnostics, not measured covariance",
            ],
        },
        "allowed_claim": manifest.allowed_claim,
        "prohibited_claims": list(manifest.prohibited_claims),
        "citations": manifest.citations,
        "software": {
            "k218_c1_context": __version__,
            "reused_numerical_module": "k218_repeatability.analysis",
            "numpy": np.__version__,
            "python": platform.python_version(),
        },
    }
    output_dir = Path(output_dir)
    _atomic_write(output_dir / "k218_c1_context.json", _canonical_bytes(result))
    _write_plot(output_dir / "k218_c1_context.png", analysis)
    return result
