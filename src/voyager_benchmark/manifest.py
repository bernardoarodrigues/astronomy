from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


HARD_MAX_DOWNLOAD_BYTES = 20_000_000_000
DEFAULT_MAX_DOWNLOAD_BYTES = 100_000_000
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_OID_RE = re.compile(r"^[0-9a-f]{40}$")


class ManifestError(ValueError):
    """Raised when a dataset manifest is unsafe or malformed."""


@dataclass(frozen=True)
class SignalTarget:
    id: str
    frequency_mhz: float
    tolerance_hz: float
    drift_rate_hz_per_s: float
    drift_tolerance_hz_per_s: float
    required: bool


@dataclass(frozen=True)
class BenchmarkSpec:
    parameter_source_url: str
    min_drift_hz_per_s: float
    max_drift_hz_per_s: float
    snr_threshold: float
    plot_frequency_start_mhz: float
    plot_frequency_stop_mhz: float
    known_signal_targets: tuple[SignalTarget, ...]
    carrier_must_be_strongest: bool


@dataclass(frozen=True)
class DatasetManifest:
    schema_version: int
    dataset_id: str
    description: str
    filename: str
    url: str
    documentation_url: str
    publisher_provenance_url: str
    size_bytes: int
    sha256: str
    git_blob_oid: str
    data_license_spdx: str
    checksum_provenance: str
    benchmark: BenchmarkSpec


def _read_default_manifest() -> dict[str, Any]:
    manifest = resources.files("voyager_benchmark").joinpath("data_manifest.json")
    return json.loads(manifest.read_text(encoding="utf-8"))


def _require_url(value: str, field_name: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ManifestError(f"{field_name} must be an absolute HTTP(S) URL")
    return value


def _parse_manifest(raw: dict[str, Any]) -> DatasetManifest:
    try:
        benchmark_raw = raw["benchmark"]
        targets = tuple(
            SignalTarget(
                id=str(target["id"]),
                frequency_mhz=float(target["frequency_mhz"]),
                tolerance_hz=float(target["tolerance_hz"]),
                drift_rate_hz_per_s=float(target["drift_rate_hz_per_s"]),
                drift_tolerance_hz_per_s=float(
                    target["drift_tolerance_hz_per_s"]
                ),
                required=bool(target["required"]),
            )
            for target in benchmark_raw["known_signal_targets"]
        )
        benchmark = BenchmarkSpec(
            parameter_source_url=_require_url(
                str(benchmark_raw["parameter_source_url"]),
                "benchmark.parameter_source_url",
            ),
            min_drift_hz_per_s=float(benchmark_raw["min_drift_hz_per_s"]),
            max_drift_hz_per_s=float(benchmark_raw["max_drift_hz_per_s"]),
            snr_threshold=float(benchmark_raw["snr_threshold"]),
            plot_frequency_start_mhz=float(
                benchmark_raw["plot_frequency_start_mhz"]
            ),
            plot_frequency_stop_mhz=float(
                benchmark_raw["plot_frequency_stop_mhz"]
            ),
            known_signal_targets=targets,
            carrier_must_be_strongest=bool(
                benchmark_raw["carrier_must_be_strongest"]
            ),
        )
        manifest = DatasetManifest(
            schema_version=int(raw["schema_version"]),
            dataset_id=str(raw["dataset_id"]),
            description=str(raw["description"]),
            filename=str(raw["filename"]),
            url=_require_url(str(raw["url"]), "url"),
            documentation_url=_require_url(
                str(raw["documentation_url"]), "documentation_url"
            ),
            publisher_provenance_url=_require_url(
                str(raw["publisher_provenance_url"]),
                "publisher_provenance_url",
            ),
            size_bytes=int(raw["size_bytes"]),
            sha256=str(raw["sha256"]).lower(),
            git_blob_oid=str(raw["git_blob_oid"]).lower(),
            data_license_spdx=str(raw["data_license_spdx"]),
            checksum_provenance=str(raw["checksum_provenance"]),
            benchmark=benchmark,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ManifestError(f"invalid manifest field: {exc}") from exc

    if manifest.schema_version != 1:
        raise ManifestError("only manifest schema_version 1 is supported")
    if not manifest.dataset_id or not manifest.description:
        raise ManifestError("dataset_id and description must be non-empty")
    if Path(manifest.filename).name != manifest.filename or not manifest.filename:
        raise ManifestError("filename must be a plain basename")
    if not 0 < manifest.size_bytes <= HARD_MAX_DOWNLOAD_BYTES:
        raise ManifestError(
            f"size_bytes must be between 1 and {HARD_MAX_DOWNLOAD_BYTES}"
        )
    if not _SHA256_RE.fullmatch(manifest.sha256):
        raise ManifestError("sha256 must contain exactly 64 lowercase hex digits")
    if not _GIT_OID_RE.fullmatch(manifest.git_blob_oid):
        raise ManifestError("git_blob_oid must contain exactly 40 lowercase hex digits")
    if manifest.data_license_spdx != "NOASSERTION":
        raise ManifestError("Phase 1 data_license_spdx must be NOASSERTION")
    if not targets or len({target.id for target in targets}) != len(targets):
        raise ManifestError("known signal targets must be non-empty and have unique ids")
    if any(target.tolerance_hz <= 0 for target in targets):
        raise ManifestError("target tolerances must be positive")
    if any(target.drift_tolerance_hz_per_s <= 0 for target in targets):
        raise ManifestError("target drift tolerances must be positive")
    if benchmark.carrier_must_be_strongest and not any(
        target.id == "carrier" for target in targets
    ):
        raise ManifestError("strongest-carrier check requires a carrier target")
    if benchmark.min_drift_hz_per_s > benchmark.max_drift_hz_per_s:
        raise ManifestError("min drift must not exceed max drift")
    if benchmark.snr_threshold <= 0:
        raise ManifestError("SNR threshold must be positive")
    if benchmark.plot_frequency_start_mhz >= benchmark.plot_frequency_stop_mhz:
        raise ManifestError("plot frequency start must be below stop")
    return manifest


def load_manifest(path: Path | None = None) -> DatasetManifest:
    """Load and validate the bundled manifest or an explicit JSON manifest."""

    if path is None:
        raw = _read_default_manifest()
    else:
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ManifestError(f"could not read manifest {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ManifestError("manifest root must be a JSON object")
    return _parse_manifest(raw)
