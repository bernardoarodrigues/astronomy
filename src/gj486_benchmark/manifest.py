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
_MD5_RE = re.compile(r"^[0-9a-f]{32}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PROGRAM_PROVENANCE = {
    "GO-1981": "NIRSpec/G395H transmission",
    "GO-1743": "MIRI/LRS eclipse",
    "GO-5866": "NIRISS/SOSS transmission",
}
_EXTERNAL_CONTEXT = {
    "MIRI_context": "specific_1bar_pure_H2O_model_disfavored; airless_or_thin_unresolved",
    "NIRISS_5866": "public_archive_time_series_products; no_B2_interpretation",
}
_EXTERNAL_CLASSIFICATION = "specific_thick_water_model_disfavored"
_EXTERNAL_CLAIM_LIMIT = (
    "Reproduction of the publisher fixed-model comparison; not a general "
    "atmosphere exclusion and not transmission-spectrum evidence."
)
_ALLOWED_CLAIM = (
    "The harness reproduces the pinned GO 1981 NIRSpec water-template regressions "
    "and exposes their reduction, detector-side, influential-bin, covariance, and "
    "nuisance sensitivity; no direct planet-versus-star origin comparison is "
    "available in the deposited products."
)
_PROHIBITED_CLAIMS = (
    "planetary-atmosphere detection",
    "water detection on GJ 486 b",
    "independent detection or confirmation",
    "independent evidence from correlated reductions",
    "stellar contamination confirmed",
    "POSEIDON posterior reproduction",
    "NIRISS resolution of the ambiguity",
    "definitively airless planet",
    "habitability",
    "biosignature",
    "technosignature",
    "evidence of life",
)
_FROZEN_CONTRACT_SHA256 = "ff2dd6b804e134c7073a40130a22bd1ae6e6e1b73800e1063076723527c3c154"


class ManifestError(ValueError):
    """Raised when the GJ 486 b manifest is malformed or unsafe."""


@dataclass(frozen=True)
class ArchiveSpec:
    record_version: str
    doi: str
    url: str
    filename: str
    size_bytes: int
    publisher_md5: str
    sha256: str
    license_spdx: str
    default_max_download_bytes: int
    hard_max_download_bytes: int
    max_archive_members: int
    max_total_uncompressed_bytes: int


@dataclass(frozen=True)
class MemberSpec:
    role: str
    path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class SpectrumSpec:
    reductions: tuple[str, ...]
    columns: tuple[str, ...]
    units: dict[str, str]
    row_counts: dict[str, int]


@dataclass(frozen=True)
class WaterModelSpec:
    columns: tuple[str, ...]
    row_count: int
    units: dict[str, str]
    provenance: str


@dataclass(frozen=True)
class StellarSpec:
    columns: tuple[str, ...]
    row_counts: dict[str, int]
    model_definitions: dict[str, str]
    normalization_nuisance: str


@dataclass(frozen=True)
class AnalysisSpec:
    minimum_wavelength_micrometres: float
    detector_split_micrometres: float
    expected_filtered_rows: dict[str, int]
    expected_z: dict[str, dict[str, float]]
    z_tolerance: float
    unit_invariance_tolerance: float
    covariance_stress: dict[str, Any]


@dataclass(frozen=True)
class ExternalConstraintSpec:
    role: str
    archive: ArchiveSpec
    members: tuple[MemberSpec, ...]
    analysis: dict[str, Any]
    classification: str
    claim_limit: str

    def member_for_role(self, role: str) -> MemberSpec:
        matches = [member for member in self.members if member.role == role]
        if len(matches) != 1:
            raise ManifestError(f"expected exactly one external member with role {role!r}")
        return matches[0]


@dataclass(frozen=True)
class GJ486Manifest:
    schema_version: int
    benchmark_id: str
    description: str
    archive: ArchiveSpec
    members: tuple[MemberSpec, ...]
    external_constraint: ExternalConstraintSpec
    program_provenance: dict[str, str]
    spectrum: SpectrumSpec
    water_model: WaterModelSpec
    stellar: StellarSpec
    analysis: AnalysisSpec
    expected_feature_state: str
    expected_science_state: str
    external_context: dict[str, str]
    citations: dict[str, str]
    allowed_claim: str
    prohibited_claims: tuple[str, ...]

    def member_for_role(self, role: str) -> MemberSpec:
        matches = [member for member in self.members if member.role == role]
        if len(matches) != 1:
            raise ManifestError(f"expected exactly one member with role {role!r}")
        return matches[0]


def _https(value: str, field_name: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ManifestError(f"{field_name} must be an absolute HTTPS URL")
    return value


def _safe_member_path(value: str) -> str:
    path = PurePosixPath(value)
    if not value or "\\" in value or path.is_absolute() or ".." in path.parts:
        raise ManifestError(f"unsafe archive member path: {value!r}")
    return value


def _archive(raw: dict[str, Any], *, url_field: str) -> ArchiveSpec:
    return ArchiveSpec(
        record_version=str(raw["record_version"]),
        doi=str(raw["doi"]),
        url=_https(str(raw["url"]), url_field),
        filename=str(raw["filename"]),
        size_bytes=int(raw["size_bytes"]),
        publisher_md5=str(raw["publisher_md5"]).lower(),
        sha256=str(raw["sha256"]).lower(),
        license_spdx=str(raw["license_spdx"]),
        default_max_download_bytes=int(raw["default_max_download_bytes"]),
        hard_max_download_bytes=int(raw["hard_max_download_bytes"]),
        max_archive_members=int(raw["max_archive_members"]),
        max_total_uncompressed_bytes=int(raw["max_total_uncompressed_bytes"]),
    )


def _members(raw: list[dict[str, Any]]) -> tuple[MemberSpec, ...]:
    return tuple(
        MemberSpec(
            role=str(item["role"]),
            path=_safe_member_path(str(item["path"])),
            size_bytes=int(item["size_bytes"]),
            sha256=str(item["sha256"]).lower(),
        )
        for item in raw
    )


def _validate_archive(archive: ArchiveSpec) -> None:
    if Path(archive.filename).name != archive.filename or not archive.filename:
        raise ManifestError("archive filename must be a plain basename")
    if not _MD5_RE.fullmatch(archive.publisher_md5):
        raise ManifestError("archive publisher_md5 must be 32 lowercase hex digits")
    if not _SHA256_RE.fullmatch(archive.sha256):
        raise ManifestError("archive sha256 must be 64 lowercase hex digits")
    if not 0 < archive.size_bytes <= archive.default_max_download_bytes:
        raise ManifestError("archive size must fit the default download guard")
    if not archive.default_max_download_bytes <= archive.hard_max_download_bytes:
        raise ManifestError("default download guard exceeds the hard limit")
    if archive.hard_max_download_bytes > PROJECT_HARD_MAX_DOWNLOAD_BYTES:
        raise ManifestError("manifest hard download limit exceeds the project hard limit")
    if not 0 < archive.max_archive_members <= PROJECT_HARD_MAX_ARCHIVE_MEMBERS:
        raise ManifestError("archive member guard exceeds the project hard limit")
    if not 0 < archive.max_total_uncompressed_bytes <= PROJECT_HARD_MAX_UNCOMPRESSED_BYTES:
        raise ManifestError("archive uncompressed-size guard exceeds the project hard limit")


def _validate_members(members: tuple[MemberSpec, ...]) -> None:
    if len({item.role for item in members}) != len(members):
        raise ManifestError("member roles must be unique")
    if len({item.path for item in members}) != len(members):
        raise ManifestError("member paths must be unique")
    if any(item.size_bytes <= 0 or not _SHA256_RE.fullmatch(item.sha256) for item in members):
        raise ManifestError("member sizes and SHA-256 values must be valid")


def _parse(raw: dict[str, Any]) -> GJ486Manifest:
    try:
        archive = _archive(raw["archive"], url_field="archive.url")
        members = _members(raw["members"])
        external_raw = raw["external_constraint"]
        external_constraint = ExternalConstraintSpec(
            role=str(external_raw["role"]),
            archive=_archive(external_raw["archive"], url_field="external_constraint.archive.url"),
            members=_members(external_raw["members"]),
            analysis=dict(external_raw["analysis"]),
            classification=str(external_raw["classification"]),
            claim_limit=str(external_raw["claim_limit"]),
        )
        spectrum_raw = raw["spectrum"]
        spectrum = SpectrumSpec(
            reductions=tuple(str(item) for item in spectrum_raw["reductions"]),
            columns=tuple(str(item) for item in spectrum_raw["columns"]),
            units={str(k): str(v) for k, v in spectrum_raw["units"].items()},
            row_counts={str(k): int(v) for k, v in spectrum_raw["row_counts"].items()},
        )
        water_raw = raw["water_model"]
        water_model = WaterModelSpec(
            columns=tuple(str(item) for item in water_raw["columns"]),
            row_count=int(water_raw["row_count"]),
            units={str(k): str(v) for k, v in water_raw["units"].items()},
            provenance=str(water_raw["provenance"]),
        )
        stellar_raw = raw["stellar"]
        stellar = StellarSpec(
            columns=tuple(str(item) for item in stellar_raw["columns"]),
            row_counts={str(k): int(v) for k, v in stellar_raw["row_counts"].items()},
            model_definitions={str(k): str(v) for k, v in stellar_raw["model_definitions"].items()},
            normalization_nuisance=str(stellar_raw["normalization_nuisance"]),
        )
        analysis_raw = raw["analysis"]
        analysis = AnalysisSpec(
            minimum_wavelength_micrometres=float(analysis_raw["minimum_wavelength_micrometres"]),
            detector_split_micrometres=float(analysis_raw["detector_split_micrometres"]),
            expected_filtered_rows={str(k): int(v) for k, v in analysis_raw["expected_filtered_rows"].items()},
            expected_z={
                str(reduction): {str(k): float(v) for k, v in values.items()}
                for reduction, values in analysis_raw["expected_z"].items()
            },
            z_tolerance=float(analysis_raw["z_tolerance"]),
            unit_invariance_tolerance=float(analysis_raw["unit_invariance_tolerance"]),
            covariance_stress=dict(analysis_raw["covariance_stress"]),
        )
        manifest = GJ486Manifest(
            schema_version=int(raw["schema_version"]),
            benchmark_id=str(raw["benchmark_id"]),
            description=str(raw["description"]),
            archive=archive,
            members=members,
            external_constraint=external_constraint,
            program_provenance={str(k): str(v) for k, v in raw["program_provenance"].items()},
            spectrum=spectrum,
            water_model=water_model,
            stellar=stellar,
            analysis=analysis,
            expected_feature_state=str(raw["expected_feature_state"]),
            expected_science_state=str(raw["expected_science_state"]),
            external_context={str(k): str(v) for k, v in raw["external_context"].items()},
            citations={str(k): _https(str(v), f"citations.{k}") for k, v in raw["citations"].items()},
            allowed_claim=str(raw["allowed_claim"]),
            prohibited_claims=tuple(str(item) for item in raw["prohibited_claims"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ManifestError(f"invalid manifest field: {exc}") from exc

    if manifest.schema_version != 1:
        raise ManifestError("only schema_version 1 is supported")
    _validate_archive(archive)
    _validate_archive(external_constraint.archive)
    if len(members) != 3 or len({item.role for item in members}) != 3:
        raise ManifestError("exactly three unique allowlisted member roles are required")
    _validate_members(members)
    if len(external_constraint.members) != 4:
        raise ManifestError("exactly four external-constraint members are required")
    _validate_members(external_constraint.members)
    for role in ("transmission_spectrum", "water_model", "stellar_spectra_models"):
        manifest.member_for_role(role)
    for role in ("miri_spectrum", "ultramafic_model", "pure_h2o_1bar_model", "blackbody_824k_model"):
        external_constraint.member_for_role(role)
    if archive.license_spdx != "CC-BY-4.0":
        raise ManifestError("the frozen archive license must be CC-BY-4.0")
    if external_constraint.archive.license_spdx != "CC-BY-4.0":
        raise ManifestError("the MIRI archive license must be CC-BY-4.0")
    if manifest.program_provenance != _PROGRAM_PROVENANCE:
        raise ManifestError("JWST program provenance does not match the frozen contract")
    if spectrum.reductions != ("Eureka", "Firefly", "Tiberius"):
        raise ManifestError("the three frozen reductions changed")
    if spectrum.columns != ("Reduction", "Wave", "Width", "Depth", "e_Depth"):
        raise ManifestError("the frozen transmission-spectrum schema changed")
    if set(spectrum.row_counts) != set(spectrum.reductions):
        raise ManifestError("spectrum row counts must cover every reduction")
    if water_model.columns != ("wavelength", "transit_depth") or water_model.row_count != 665:
        raise ManifestError("the frozen water-model schema changed")
    if stellar.columns != ("Type", "Wave", "Flux", "e_Flux"):
        raise ManifestError("the frozen stellar schema changed")
    if stellar.row_counts != {"V1": 3203, "V2": 3203, "M1": 9465, "M2": 9465, "M3": 9465}:
        raise ManifestError("the frozen stellar group counts changed")
    if set(analysis.expected_filtered_rows) != set(spectrum.reductions):
        raise ManifestError("filtered row counts must cover every reduction")
    if set(analysis.expected_z) != set(spectrum.reductions):
        raise ManifestError("z fingerprints must cover every reduction")
    if analysis.z_tolerance <= 0 or analysis.unit_invariance_tolerance <= 0:
        raise ManifestError("analysis tolerances must be positive")
    if manifest.expected_feature_state != "retrospective_template_regression_reproduced":
        raise ManifestError("the frozen feature state must remain a retrospective regression reproduction")
    if manifest.expected_science_state != "science_unresolved":
        raise ManifestError("the frozen science state must remain science_unresolved")
    if manifest.external_context != _EXTERNAL_CONTEXT:
        raise ManifestError("the frozen external evidence context changed")
    if external_constraint.classification != _EXTERNAL_CLASSIFICATION:
        raise ManifestError("the frozen MIRI classification changed")
    if external_constraint.claim_limit != _EXTERNAL_CLAIM_LIMIT:
        raise ManifestError("the frozen MIRI claim limit changed")
    if manifest.allowed_claim != _ALLOWED_CLAIM:
        raise ManifestError("the frozen allowed claim changed")
    if manifest.prohibited_claims != _PROHIBITED_CLAIMS:
        raise ManifestError("the frozen prohibited claims changed")
    miri_expected = external_constraint.analysis.get("expected_chi2_per_point")
    if miri_expected != {"ultramafic": 1.1793, "blackbody_824k": 1.0461, "pure_h2o_1bar": 6.3887}:
        raise ManifestError("the frozen MIRI model-ranking fingerprints changed")
    canonical = json.dumps(
        raw,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    if hashlib.sha256(canonical).hexdigest() != _FROZEN_CONTRACT_SHA256:
        raise ManifestError("manifest differs from the frozen canonical scientific contract")
    return manifest


def load_manifest(path: Path | None = None) -> GJ486Manifest:
    try:
        if path is None:
            text = resources.files("gj486_benchmark").joinpath("data_manifest.json").read_text(encoding="utf-8")
        else:
            text = Path(path).read_text(encoding="utf-8")
        raw = json.loads(text)
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"could not read manifest {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ManifestError("manifest root must be a JSON object")
    return _parse(raw)
