from __future__ import annotations

import hashlib
import json
import re
from importlib import resources
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

from k218_repeatability.manifest import (
    AnalysisSpec,
    ArchiveSpec,
    K218Manifest,
    MemberSpec,
    RebinSpec,
)


class ManifestError(ValueError):
    """Raised when the isolated C1 historical-context contract changes."""


_FROZEN_CONTRACT_SHA256 = "7e586d625c79a027b95802c7b408d1bd3962a42702fc5f9442dc48c8ffac6680"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_EXPECTED_MEMBERS = {
    (
        "exoTEDRF",
        "visit_1",
        "NRS2",
        46925,
        "bd5ffeacfd2962f44175872e90b1f335e87e5212f1c194ccc4cf3be2469e663a",
    ),
    (
        "Eureka",
        "visit_1",
        "NRS2",
        33017,
        "e2f2ee2489f81203e8292194c6e5fc949740fe407a98c34348a48b87bab7392b",
    ),
}


def _https(value: str, field: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ManifestError(f"{field} must be an absolute HTTPS URL")
    return value


def _safe_member_path(value: str) -> str:
    path = PurePosixPath(value)
    if not value or "\\" in value or path.is_absolute() or ".." in path.parts:
        raise ManifestError(f"unsafe archive member path: {value!r}")
    return value


def _parse(raw: dict[str, Any]) -> K218Manifest:
    try:
        archive_raw = raw["archive"]
        archive = ArchiveSpec(
            record=str(archive_raw["record"]),
            doi=_https(str(archive_raw["doi"]), "archive.doi"),
            url=_https(str(archive_raw["url"]), "archive.url"),
            filename=str(archive_raw["filename"]),
            size_bytes=int(archive_raw["size_bytes"]),
            sha256=str(archive_raw["sha256"]).lower(),
            license_spdx=str(archive_raw["license_spdx"]),
            default_max_download_bytes=int(archive_raw["default_max_download_bytes"]),
            hard_max_download_bytes=int(archive_raw["hard_max_download_bytes"]),
            max_archive_members=int(archive_raw["max_archive_members"]),
            max_total_uncompressed_bytes=int(archive_raw["max_total_uncompressed_bytes"]),
        )
        members = tuple(
            MemberSpec(
                role=str(item["role"]),
                reduction=str(item["reduction"]),
                visit=str(item["visit"]),
                detector=str(item["detector"]),
                path=_safe_member_path(str(item["path"])),
                size_bytes=int(item["size_bytes"]),
                sha256=str(item["sha256"]).lower(),
                rows=int(item["rows"]),
                wavelength_min_micrometres=float(item["wavelength_min_micrometres"]),
                wavelength_max_micrometres=float(item["wavelength_max_micrometres"]),
            )
            for item in raw["members"]
        )
        rebin_raw = raw["rebinning"]
        rebinning = RebinSpec(
            resolving_power=float(rebin_raw["resolving_power"]),
            grid_anchor_micrometres=float(rebin_raw["grid_anchor_micrometres"]),
            first_edge_index=int(rebin_raw["first_edge_index"]),
            last_edge_index=int(rebin_raw["last_edge_index"]),
            edge_count=int(rebin_raw["edge_count"]),
            output_bin_count=int(rebin_raw["output_bin_count"]),
            edge_sha256=str(rebin_raw["edge_sha256"]).lower(),
            edge_hash_encoding=str(rebin_raw["edge_hash_encoding"]),
            coverage_relative_tolerance=float(rebin_raw["coverage_relative_tolerance"]),
            minimum_coverage_fraction=float(rebin_raw["minimum_coverage_fraction"]),
        )
        analysis_raw = raw["analysis"]
        analysis = AnalysisSpec(
            detector=str(analysis_raw["detector"]),
            domain_micrometres=tuple(float(v) for v in analysis_raw["domain_micrometres"]),
            feature_micrometres=tuple(float(v) for v in analysis_raw["feature_micrometres"]),
            pivot_micrometres=float(analysis_raw["pivot_micrometres"]),
            ar1_rho_sensitivities=tuple(float(v) for v in analysis_raw["ar1_rho_sensitivities"]),
            z_label=str(analysis_raw["z_label"]),
        )
        canonical = json.dumps(
            raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        manifest = K218Manifest(
            schema_version=int(raw["schema_version"]),
            benchmark_id=str(raw["benchmark_id"]),
            description=str(raw["description"]),
            archive=archive,
            program=dict(raw["program"]),
            members=members,
            schemas=dict(raw["schemas"]),
            rebinning=rebinning,
            analysis=analysis,
            analysis_contract=dict(analysis_raw),
            output_contract=dict(raw["output_contract"]),
            allowed_claim=str(raw["allowed_claim"]),
            prohibited_claims=tuple(str(value) for value in raw["prohibited_claims"]),
            citations={
                str(key): _https(str(value), f"citations.{key}")
                for key, value in raw["citations"].items()
            },
            canonical_sha256=hashlib.sha256(canonical).hexdigest(),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ManifestError(f"invalid manifest field: {exc}") from exc
    _validate(manifest, raw)
    return manifest


def _validate(manifest: K218Manifest, raw: dict[str, Any]) -> None:
    if manifest.schema_version != 1 or manifest.canonical_sha256 != _FROZEN_CONTRACT_SHA256:
        raise ManifestError("manifest differs from the frozen C1 context contract")
    archive = manifest.archive
    if (
        Path(archive.filename).name != archive.filename
        or archive.size_bytes != 275602
        or archive.sha256 != "4ee5cb6ad42015bd8fb10f64e54329d250137ab1fa129c89a14830946adc8f18"
        or archive.license_spdx != "NOASSERTION"
        or archive.hard_max_download_bytes != 20_000_000_000
        or archive.default_max_download_bytes < archive.size_bytes
        or not _SHA256_RE.fullmatch(archive.sha256)
    ):
        raise ManifestError("archive provenance or transfer guard changed")
    observed = {
        (member.reduction, member.visit, member.detector, member.size_bytes, member.sha256)
        for member in manifest.members
    }
    if observed != _EXPECTED_MEMBERS or len(manifest.members) != 2:
        raise ManifestError("exactly the two frozen C1 NRS2 correlated views are required")
    if len({item.role for item in manifest.members}) != 2 or len({item.path for item in manifest.members}) != 2:
        raise ManifestError("C1 member roles and paths must be unique")
    if any(
        item.rows != 335
        or item.wavelength_min_micrometres != 3.832
        or item.wavelength_max_micrometres != 5.168
        for item in manifest.members
    ):
        raise ManifestError("C1 row counts or wavelength centres changed")

    program = manifest.program
    inventory = program.get("complete_g395h_visit_inventory", {})
    if set(inventory) != {"visit_1"}:
        raise ManifestError("the isolated C1 inventory must contain visit_1 only")
    c1 = inventory["visit_1"]
    if (
        c1.get("paper_label") != "C1"
        or c1.get("program_id") != "GO-2722"
        or c1.get("observation_date_utc") != "2023-01-20"
        or c1.get("independence_group") != "GO-2722-C1-photons"
        or program.get("eligible_visits") != ["visit_1"]
        or program.get("evidence_units") != 1
        or program.get("paired_correlated_views_per_evidence_unit") != 2
        or program.get("reductions_are_independent") is not False
        or program.get("cross_reduction_combination") != "prohibited"
        or program.get("comparison_to_go2372") != "descriptive_only_not_inferential"
    ):
        raise ManifestError("C1 evidence-unit or comparison contract changed")

    rebin = manifest.rebinning
    if (
        rebin.resolving_power,
        rebin.grid_anchor_micrometres,
        rebin.first_edge_index,
        rebin.last_edge_index,
        rebin.edge_count,
        rebin.output_bin_count,
        rebin.edge_sha256,
        rebin.coverage_relative_tolerance,
        rebin.minimum_coverage_fraction,
    ) != (
        100.0,
        1.0,
        135,
        155,
        21,
        20,
        "7f7e418fc0bfde1478d7ade8a4fef0f774bc7bb0f3046a918be7bc763d3b2d28",
        1e-12,
        0.999999999999,
    ):
        raise ManifestError("C1 must reuse the exact committed global grid and rebin guards")
    analysis = manifest.analysis
    if (
        analysis.detector,
        analysis.domain_micrometres,
        analysis.feature_micrometres,
        analysis.pivot_micrometres,
        analysis.ar1_rho_sensitivities,
        analysis.z_label,
    ) != (
        "NRS2",
        (3.85, 4.75),
        (4.05, 4.55),
        4.3,
        (0.25, 0.5),
        "retrospective_standardized_contrast",
    ):
        raise ManifestError("C1 must reuse the exact committed contrast model")

    output = manifest.output_contract
    exact_output = {
        "retrospective": True,
        "externally_preregistered": False,
        "science_state": "not_applicable_historical_context",
        "independent_reduction": False,
        "independent_reduction_evidence": False,
        "comparison_to_go2372": "descriptive_only_not_inferential",
        "planetary_origin": "not_evaluated",
        "atmosphere": "not_evaluated",
        "molecule": "not_evaluated",
        "molecule_attribution": "not_evaluated",
        "biosignature": "not_evaluated",
        "biosignature_state": "not_evaluated",
        "evidence_of_life": False,
        "b3_completion": False,
        "b3b_completion": False,
        "real_data_readiness": False,
    }
    if output != exact_output:
        raise ManifestError("fail-closed C1 output contract changed")
    transparency = raw.get("transparency", {})
    if (
        transparency.get("blind_or_pre_unblinded") is not False
        or transparency.get("post_publication") is not True
        or transparency.get("held_out") is not False
        or "No input, numerical method" not in transparency.get(
            "post_run_editorial_clarification", ""
        )
        or len(transparency.get("limitations", [])) != 5
    ):
        raise ManifestError("C1 transparency disclosures changed")


def load_manifest(path: Path | None = None) -> K218Manifest:
    try:
        if path is None:
            payload = resources.files("k218_c1_context").joinpath("data_manifest.json").read_text(
                encoding="utf-8"
            )
        else:
            payload = Path(path).read_text(encoding="utf-8")
        raw = json.loads(payload)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"could not read C1 manifest: {exc}") from exc
    if not isinstance(raw, dict):
        raise ManifestError("C1 manifest root must be an object")
    return _parse(raw)
