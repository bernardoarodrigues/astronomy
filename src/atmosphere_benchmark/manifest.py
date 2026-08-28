from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse


_MD5_RE = re.compile(r"^[0-9a-f]{32}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PROJECT_HARD_MAX_DOWNLOAD_BYTES = 20_000_000_000
PROJECT_HARD_MAX_ARCHIVE_MEMBERS = 10_000
PROJECT_HARD_MAX_UNCOMPRESSED_BYTES = 20_000_000_000


class ManifestError(ValueError):
    """Raised when the atmospheric benchmark manifest is malformed or unsafe."""


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
    columns: tuple[str, ...]
    row_count: int
    units: dict[str, str]


@dataclass(frozen=True)
class AnalysisSpec:
    window_micrometres: tuple[float, float]
    window_inclusive: bool
    expected_window_rows: int
    rebinning: bool
    pivot_micrometres: float
    feature_sigma_micrometres: float
    amplitude_signed: bool
    variance_model: str
    expected_fingerprint: dict[str, float]
    acceptance: dict[str, Any]
    covariance_stress: dict[str, Any]
    null_monte_carlo: dict[str, Any]


@dataclass(frozen=True)
class AtmosphereManifest:
    schema_version: int
    benchmark_id: str
    description: str
    archive: ArchiveSpec
    members: tuple[MemberSpec, ...]
    spectrum: SpectrumSpec
    analysis: AnalysisSpec
    citations: dict[str, str]
    allowed_claim: str
    prohibited_claims: tuple[str, ...]

    def member_for_role(self, role: str) -> MemberSpec:
        matches = [member for member in self.members if member.role == role]
        if len(matches) != 1:
            raise ManifestError(f"expected exactly one member with role {role!r}")
        return matches[0]


def _require_url(value: str, field_name: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ManifestError(f"{field_name} must be an absolute HTTPS URL")
    return value


def _safe_member_path(value: str) -> str:
    if "\\" in value:
        raise ManifestError("member paths must use POSIX separators")
    path = PurePosixPath(value)
    if path.is_absolute() or not value or ".." in path.parts:
        raise ManifestError(f"unsafe archive member path: {value!r}")
    return value


def _pair(values: Any, field_name: str) -> tuple[float, float]:
    if not isinstance(values, list) or len(values) != 2:
        raise ManifestError(f"{field_name} must contain exactly two values")
    lower, upper = float(values[0]), float(values[1])
    if lower > upper:
        raise ManifestError(f"{field_name} lower bound exceeds upper bound")
    return lower, upper


def _parse(raw: dict[str, Any]) -> AtmosphereManifest:
    try:
        archive_raw = raw["archive"]
        archive = ArchiveSpec(
            record_version=str(archive_raw["record_version"]),
            doi=str(archive_raw["doi"]),
            url=_require_url(str(archive_raw["url"]), "archive.url"),
            filename=str(archive_raw["filename"]),
            size_bytes=int(archive_raw["size_bytes"]),
            publisher_md5=str(archive_raw["publisher_md5"]).lower(),
            sha256=str(archive_raw["sha256"]).lower(),
            license_spdx=str(archive_raw["license_spdx"]),
            default_max_download_bytes=int(
                archive_raw["default_max_download_bytes"]
            ),
            hard_max_download_bytes=int(archive_raw["hard_max_download_bytes"]),
            max_archive_members=int(archive_raw["max_archive_members"]),
            max_total_uncompressed_bytes=int(
                archive_raw["max_total_uncompressed_bytes"]
            ),
        )
        members = tuple(
            MemberSpec(
                role=str(item["role"]),
                path=_safe_member_path(str(item["path"])),
                size_bytes=int(item["size_bytes"]),
                sha256=str(item["sha256"]).lower(),
            )
            for item in raw["members"]
        )
        spectrum_raw = raw["spectrum"]
        spectrum = SpectrumSpec(
            columns=tuple(str(item) for item in spectrum_raw["columns"]),
            row_count=int(spectrum_raw["row_count"]),
            units={str(key): str(value) for key, value in spectrum_raw["units"].items()},
        )
        analysis_raw = raw["analysis"]
        analysis = AnalysisSpec(
            window_micrometres=_pair(
                analysis_raw["window_micrometres"], "analysis.window_micrometres"
            ),
            window_inclusive=bool(analysis_raw["window_inclusive"]),
            expected_window_rows=int(analysis_raw["expected_window_rows"]),
            rebinning=bool(analysis_raw["rebinning"]),
            pivot_micrometres=float(analysis_raw["pivot_micrometres"]),
            feature_sigma_micrometres=float(
                analysis_raw["feature_sigma_micrometres"]
            ),
            amplitude_signed=bool(analysis_raw["amplitude_signed"]),
            variance_model=str(analysis_raw["variance_model"]),
            expected_fingerprint={
                str(key): float(value)
                for key, value in analysis_raw["expected_fingerprint"].items()
            },
            acceptance=dict(analysis_raw["acceptance"]),
            covariance_stress=dict(analysis_raw["covariance_stress"]),
            null_monte_carlo=dict(analysis_raw["null_monte_carlo"]),
        )
        manifest = AtmosphereManifest(
            schema_version=int(raw["schema_version"]),
            benchmark_id=str(raw["benchmark_id"]),
            description=str(raw["description"]),
            archive=archive,
            members=members,
            spectrum=spectrum,
            analysis=analysis,
            citations={str(key): _require_url(str(value), f"citations.{key}") for key, value in raw["citations"].items()},
            allowed_claim=str(raw["allowed_claim"]),
            prohibited_claims=tuple(str(item) for item in raw["prohibited_claims"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ManifestError(f"invalid manifest field: {exc}") from exc

    if manifest.schema_version != 1:
        raise ManifestError("only schema_version 1 is supported")
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
        raise ManifestError(
            "manifest hard download limit exceeds the project hard limit"
        )
    if archive.max_archive_members <= 0 or archive.max_total_uncompressed_bytes <= 0:
        raise ManifestError("archive extraction guards must be positive")
    if archive.max_archive_members > PROJECT_HARD_MAX_ARCHIVE_MEMBERS:
        raise ManifestError("archive member guard exceeds the project hard limit")
    if archive.max_total_uncompressed_bytes > PROJECT_HARD_MAX_UNCOMPRESSED_BYTES:
        raise ManifestError(
            "archive uncompressed-size guard exceeds the project hard limit"
        )
    if len(members) == 0 or len({item.role for item in members}) != len(members):
        raise ManifestError("member roles must be non-empty and unique")
    if len({item.path for item in members}) != len(members):
        raise ManifestError("member paths must be unique")
    if any(item.size_bytes <= 0 or not _SHA256_RE.fullmatch(item.sha256) for item in members):
        raise ManifestError("member sizes and SHA-256 values must be valid")
    if spectrum.columns != ("wv_center", "transit_depth", "wv_wdth", "tran_unc"):
        raise ManifestError("the frozen FIREFLy column schema changed")
    if spectrum.row_count != 95 or analysis.expected_window_rows != 20:
        raise ManifestError("the frozen FIREFLy row counts changed")
    if analysis.rebinning or not analysis.window_inclusive:
        raise ManifestError("Milestone B1 requires an inclusive, unre-binned window")
    if analysis.feature_sigma_micrometres <= 0:
        raise ManifestError("feature sigma must be positive")
    for field in ("amplitude", "z", "delta_chi2"):
        if field not in analysis.expected_fingerprint:
            raise ManifestError(f"expected fingerprint is missing {field}")
        _pair(analysis.acceptance[field], f"analysis.acceptance.{field}")
    if archive.license_spdx != "CC-BY-4.0":
        raise ManifestError("the frozen archive license must be CC-BY-4.0")
    for role in (
        "primary_spectrum",
        "attribution_full_model",
        "attribution_no_co2_model",
    ):
        manifest.member_for_role(role)
    return manifest


def load_manifest(path: Path | None = None) -> AtmosphereManifest:
    if path is None:
        resource = resources.files("atmosphere_benchmark").joinpath(
            "data_manifest.json"
        )
        raw = json.loads(resource.read_text(encoding="utf-8"))
    else:
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ManifestError(f"could not read manifest {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ManifestError("manifest root must be a JSON object")
    return _parse(raw)
