from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse


PROJECT_HARD_MAX_DOWNLOAD_BYTES = 20_000_000_000
PROJECT_HARD_MAX_ARCHIVE_MEMBERS = 10_000
PROJECT_HARD_MAX_UNCOMPRESSED_BYTES = 20_000_000_000
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FROZEN_CONTRACT_SHA256 = "1434dde1a6c2169e95b1442671555bb27c0d77873daa53f0da6d6e296dec546f"
_EXPECTED_CELLS = {
    ("Eureka", "visit_2", "NRS2"),
    ("Eureka", "visit_3", "NRS2"),
    ("exoTEDRF", "visit_2", "NRS2"),
    ("exoTEDRF", "visit_3", "NRS2"),
}


class ManifestError(ValueError):
    """Raised when the K2-18 repeatability contract is malformed or unsafe."""


@dataclass(frozen=True)
class ArchiveSpec:
    record: str
    doi: str
    url: str
    filename: str
    size_bytes: int
    sha256: str
    license_spdx: str
    default_max_download_bytes: int
    hard_max_download_bytes: int
    max_archive_members: int
    max_total_uncompressed_bytes: int


@dataclass(frozen=True)
class MemberSpec:
    role: str
    reduction: str
    visit: str
    detector: str
    path: str
    size_bytes: int
    sha256: str
    rows: int
    wavelength_min_micrometres: float
    wavelength_max_micrometres: float


@dataclass(frozen=True)
class RebinSpec:
    resolving_power: float
    grid_anchor_micrometres: float
    first_edge_index: int
    last_edge_index: int
    edge_count: int
    output_bin_count: int
    edge_sha256: str
    edge_hash_encoding: str
    coverage_relative_tolerance: float
    minimum_coverage_fraction: float


@dataclass(frozen=True)
class AnalysisSpec:
    detector: str
    domain_micrometres: tuple[float, float]
    feature_micrometres: tuple[float, float]
    pivot_micrometres: float
    ar1_rho_sensitivities: tuple[float, ...]
    z_label: str


@dataclass(frozen=True)
class K218Manifest:
    schema_version: int
    benchmark_id: str
    description: str
    archive: ArchiveSpec
    program: dict[str, Any]
    members: tuple[MemberSpec, ...]
    schemas: dict[str, Any]
    rebinning: RebinSpec
    analysis: AnalysisSpec
    analysis_contract: dict[str, Any]
    output_contract: dict[str, Any]
    allowed_claim: str
    prohibited_claims: tuple[str, ...]
    citations: dict[str, str]
    canonical_sha256: str

    def member_for(self, reduction: str, visit: str, detector: str = "NRS2") -> MemberSpec:
        matches = [
            member
            for member in self.members
            if (member.reduction, member.visit, member.detector)
            == (reduction, visit, detector)
        ]
        if len(matches) != 1:
            raise ManifestError(
                f"expected one member for {reduction}/{visit}/{detector}, found {len(matches)}"
            )
        return matches[0]


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
            prohibited_claims=tuple(str(v) for v in raw["prohibited_claims"]),
            citations={
                str(key): _https(str(value), f"citations.{key}")
                for key, value in raw["citations"].items()
            },
            canonical_sha256=hashlib.sha256(canonical).hexdigest(),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ManifestError(f"invalid manifest field: {exc}") from exc
    _validate(manifest)
    return manifest


def _validate(manifest: K218Manifest) -> None:
    archive = manifest.archive
    if manifest.schema_version != 1:
        raise ManifestError("only schema_version 1 is supported")
    if manifest.canonical_sha256 != _FROZEN_CONTRACT_SHA256:
        raise ManifestError("manifest differs from the frozen pre-result contract")
    if Path(archive.filename).name != archive.filename or not archive.filename:
        raise ManifestError("archive filename must be a plain basename")
    if not _SHA256_RE.fullmatch(archive.sha256):
        raise ManifestError("archive SHA-256 must be 64 lowercase hex digits")
    if not 0 < archive.size_bytes <= archive.default_max_download_bytes:
        raise ManifestError("archive size must fit the default transfer guard")
    if not archive.default_max_download_bytes <= archive.hard_max_download_bytes:
        raise ManifestError("default transfer guard exceeds the archive hard limit")
    if archive.hard_max_download_bytes > PROJECT_HARD_MAX_DOWNLOAD_BYTES:
        raise ManifestError("archive hard limit exceeds the project 20 GB ceiling")
    if not 0 < archive.max_archive_members <= PROJECT_HARD_MAX_ARCHIVE_MEMBERS:
        raise ManifestError("archive member guard exceeds the project limit")
    if not 0 < archive.max_total_uncompressed_bytes <= PROJECT_HARD_MAX_UNCOMPRESSED_BYTES:
        raise ManifestError("uncompressed-size guard exceeds the project limit")
    if archive.license_spdx != "NOASSERTION":
        raise ManifestError("the OSF payload license must remain NOASSERTION")

    cells = {(m.reduction, m.visit, m.detector) for m in manifest.members}
    if len(manifest.members) != 4 or cells != _EXPECTED_CELLS:
        raise ManifestError("exactly the four frozen GO-2372 NRS2 reduction/visit views are required")
    if len({m.role for m in manifest.members}) != 4 or len({m.path for m in manifest.members}) != 4:
        raise ManifestError("member roles and paths must be unique")
    for member in manifest.members:
        if member.rows != 335 or member.wavelength_min_micrometres != 3.832 or member.wavelength_max_micrometres != 5.168:
            raise ManifestError("frozen NRS2 row counts or wavelength bounds changed")
        if member.size_bytes <= 0 or not _SHA256_RE.fullmatch(member.sha256):
            raise ManifestError("member size and SHA-256 fields must be valid")

    program = manifest.program
    inventory = program.get("complete_g395h_visit_inventory", {})
    if set(inventory) != {"visit_1", "visit_2", "visit_3"}:
        raise ManifestError("the complete C1/C2/C3 G395H visit inventory is required")
    if inventory["visit_1"].get("eligible") is not False or inventory["visit_1"].get("program_id") != "GO-2722":
        raise ManifestError("historical C1 must remain explicitly ineligible")
    if program.get("eligible_visits") != ["visit_2", "visit_3"]:
        raise ManifestError("the metadata-only rule must select C2 and C3 exactly")
    if program.get("selection_basis") != "metadata_only" or program.get("spectral_result_selection") is not False:
        raise ManifestError("spectral-result selection is prohibited")
    if program.get("evidence_units") != 2 or program.get("paired_correlated_views_per_evidence_unit") != 2:
        raise ManifestError("the evidence-unit structure changed")
    if program.get("reductions_are_independent") is not False or program.get("cross_reduction_combination") != "prohibited":
        raise ManifestError("correlated reductions cannot become independent evidence")

    rebin = manifest.rebinning
    if (
        rebin.resolving_power,
        rebin.grid_anchor_micrometres,
        rebin.first_edge_index,
        rebin.last_edge_index,
        rebin.edge_count,
        rebin.output_bin_count,
        rebin.edge_sha256,
    ) != (
        100.0,
        1.0,
        135,
        155,
        21,
        20,
        "7f7e418fc0bfde1478d7ade8a4fef0f774bc7bb0f3046a918be7bc763d3b2d28",
    ):
        raise ManifestError("the frozen global R=100 grid changed")
    if rebin.coverage_relative_tolerance != 1e-12 or rebin.minimum_coverage_fraction != 0.999999999999:
        raise ManifestError("the frozen full-coverage tolerance changed")
    analysis = manifest.analysis
    if analysis.detector != "NRS2" or analysis.domain_micrometres != (3.85, 4.75):
        raise ManifestError("analysis must remain NRS2-only over 3.85-4.75 micrometres")
    if analysis.feature_micrometres != (4.05, 4.55) or analysis.pivot_micrometres != 4.3:
        raise ManifestError("the frozen morphology model changed")
    if analysis.ar1_rho_sensitivities != (0.25, 0.5):
        raise ManifestError("the frozen AR(1) sensitivities changed")
    if analysis.z_label != "retrospective_standardized_contrast":
        raise ManifestError("z must remain a retrospective standardized contrast")
    rules = manifest.analysis_contract.get("outcome_rules", {})
    if set(rules) != {"repeatable_positive_morphology", "SCIENCE_UNRESOLVED"}:
        raise ManifestError("outcome states differ from the frozen fail-closed contract")
    combination = manifest.analysis_contract.get("combination_rules", {})
    if combination.get("cross_reduction_z_combination") != "prohibited" or combination.get("cross_reduction_voting") != "prohibited":
        raise ManifestError("cross-reduction z combination and voting are prohibited")
    expected_output = {
        "retrospective": True,
        "independent_reduction": False,
        "planetary_origin": "not_evaluated",
        "atmosphere": "not_evaluated",
        "molecule": "not_evaluated",
        "molecule_attribution": "not_evaluated",
        "biosignature": "not_evaluated",
        "biosignature_state": "not_evaluated",
        "evidence_of_life": False,
        "b3_completion": False,
        "claim_scope": "published-spectrum feature repeatability",
    }
    if manifest.output_contract != expected_output:
        raise ManifestError("non-promotional output contract changed")


def load_manifest(path: Path | None = None) -> K218Manifest:
    try:
        if path is None:
            text = resources.files("k218_repeatability").joinpath("data_manifest.json").read_text(encoding="utf-8")
        else:
            text = Path(path).read_text(encoding="utf-8")
        raw = json.loads(text)
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"could not read manifest {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ManifestError("manifest root must be a JSON object")
    return _parse(raw)
