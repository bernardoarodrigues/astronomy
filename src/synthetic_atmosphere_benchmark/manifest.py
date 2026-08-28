from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path, PurePosixPath
from typing import Any

from .canonical import canonical_json_text


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_CLAIM = (
    "The public B3a synthetic engineering preflight executed the frozen linear-Gaussian "
    "challenge and met its predeclared smoke gates in the locked environment. This is "
    "not the sealed B3 scientific gate and is not evidence about any real atmosphere."
)
_INCOMPLETE_CLAIM = (
    "The B3a public synthetic preflight executed all 648 cases but remains incomplete "
    "because unsafe-specific-classification and diagnostic-classification gates were not met."
)
_PROHIBITED_CLAIMS = (
    "B3 complete",
    "K2-18 b authorized",
    "validated atmospheric retrieval",
    "ready to detect K2-18 b",
    "real atmosphere detected",
    "molecule detected",
    "biosignature",
    "habitability",
    "life",
    "real-data false-positive rate",
    "robust to unknown systematics",
)
_FROZEN_CONTRACT_SHA256 = "b4b5a59dbecfa24ab1330afa483983e5ce4b1fae9a4dab83cd275d1cfe9d52a8"


class ManifestError(ValueError):
    """Raised when the synthetic-preflight contract is incomplete or changed."""


@dataclass(frozen=True)
class MemberSpec:
    role: str
    path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class SyntheticManifest:
    raw: dict[str, Any]
    schema_version: int
    benchmark_id: str
    contract_sha256: str
    members: tuple[MemberSpec, ...]
    source_root: str
    cases_per_family: int
    families: tuple[str, ...]
    root_entropy: tuple[int, ...]
    promotion_z: float
    allowed_claim: str
    incomplete_claim: str
    prohibited_claims: tuple[str, ...]

    def member_for_role(self, role: str) -> MemberSpec:
        matches = [item for item in self.members if item.role == role]
        if len(matches) != 1:
            raise ManifestError(f"expected exactly one member for role {role!r}")
        return matches[0]


def _safe_path(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value:
        raise ManifestError(f"unsafe member path: {value!r}")
    return value


def _contract_hash(raw: dict[str, Any]) -> str:
    content = dict(raw)
    content.pop("contract_sha256", None)
    return hashlib.sha256(canonical_json_text(content).encode("utf-8")).hexdigest()


def _parse(raw: dict[str, Any]) -> SyntheticManifest:
    try:
        source = raw["source"]
        suite = raw["public_preflight"]
        members = tuple(
            MemberSpec(
                role=str(item["role"]),
                path=_safe_path(str(item["path"])),
                size_bytes=int(item["size_bytes"]),
                sha256=str(item["sha256"]).lower(),
            )
            for item in source["members"]
        )
        manifest = SyntheticManifest(
            raw=raw,
            schema_version=int(raw["schema_version"]),
            benchmark_id=str(raw["benchmark_id"]),
            contract_sha256=str(raw["contract_sha256"]),
            members=members,
            source_root=str(source["default_extracted_root"]),
            cases_per_family=int(suite["cases_per_family"]),
            families=tuple(str(item) for item in suite["families"]),
            root_entropy=tuple(int(item) for item in raw["rng"]["root_entropy_uint32"]),
            promotion_z=float(raw["decision_rule"]["promotion_z"]),
            allowed_claim=str(raw["allowed_claim"]),
            incomplete_claim=str(raw["incomplete_claim"]),
            prohibited_claims=tuple(str(item) for item in raw["prohibited_claims"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ManifestError(f"malformed synthetic-preflight manifest: {exc}") from exc
    _validate(manifest)
    return manifest


def _validate(manifest: SyntheticManifest) -> None:
    raw = manifest.raw
    expected_families = (
        "null",
        "correlated_null",
        "strong_planet",
        "weak_planet",
        "stellar_only",
        "detector_only",
        "planet_stellar",
        "omitted_template",
        "ambiguous_cancellation",
    )
    if manifest.schema_version != 1:
        raise ManifestError("schema_version must be 1")
    if manifest.benchmark_id != "synthetic_atmosphere_engineering_preflight_v1":
        raise ManifestError("benchmark_id changed")
    if manifest.contract_sha256 != _contract_hash(raw):
        raise ManifestError("manifest contract SHA-256 mismatch")
    if manifest.allowed_claim != _ALLOWED_CLAIM:
        raise ManifestError("allowed claim changed")
    if manifest.incomplete_claim != _INCOMPLETE_CLAIM:
        raise ManifestError("incomplete-result claim changed")
    if manifest.prohibited_claims != _PROHIBITED_CLAIMS:
        raise ManifestError("prohibited claims changed")
    if manifest.contract_sha256 != _FROZEN_CONTRACT_SHA256:
        raise ManifestError("frozen manifest contract changed")
    if manifest.families != expected_families:
        raise ManifestError("public family inventory changed")
    if manifest.cases_per_family != 72:
        raise ManifestError("public cases-per-family changed")
    if len(manifest.root_entropy) != 4 or any(not 0 <= value < 2**32 for value in manifest.root_entropy):
        raise ManifestError("root entropy must contain four uint32 values")
    if raw["rng"]["bit_generator"] != "PCG64DXSM":
        raise ManifestError("bit generator must remain PCG64DXSM")
    if raw["rng"]["case_id_domain"] != "b3a-public-id-v1" or raw["rng"][
        "family_seed_aliases"
    ] != {"ambiguous_cancellation": "nonidentifiable"}:
        raise ManifestError("public identifier or seed-alias contract changed")
    if raw["states"] != {
        "science_state": "not_applicable_synthetic",
        "real_data_readiness": "not_established",
    }:
        raise ManifestError("synthetic-only states changed")
    if raw["scope"]["milestone"] != "B3a" or raw["scope"]["full_b3_gate"] is not False:
        raise ManifestError("B3a scope boundary changed")
    if raw["source"]["doi"] != "10.5281/zenodo.10408056":
        raise ManifestError("source DOI changed")
    if raw["source"]["license_spdx"] != "CC-BY-4.0":
        raise ManifestError("source license changed")
    if (
        len(manifest.members) != 3
        or {item.role for item in manifest.members}
        != {"eureka_grid_uncertainties", "picaso_water_template", "phoenix_m1_m3_models"}
        or len({item.path for item in manifest.members}) != 3
    ):
        raise ManifestError("expected exactly three unique source members")
    if any(item.size_bytes <= 0 or not _SHA256_RE.fullmatch(item.sha256) for item in manifest.members):
        raise ManifestError("invalid source member integrity record")
    if manifest.promotion_z != 3.0:
        raise ManifestError("promotion threshold changed")
    full = raw["future_sealed_b3b"]
    if (
        full["negative_cases_per_family"] != 2000
        or full["power_cases_per_cell"] != 1000
        or full["coverage_cases_per_key_cell"] != 2000
        or full["status"] != "pending_not_executed"
    ):
        raise ManifestError("future sealed-run requirements changed")


def load_manifest(path: Path | None = None) -> SyntheticManifest:
    try:
        if path is None:
            text = resources.files("synthetic_atmosphere_benchmark").joinpath("data_manifest.json").read_text(
                encoding="utf-8"
            )
        else:
            text = Path(path).read_text(encoding="utf-8")
        raw = json.loads(text)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"could not read manifest: {exc}") from exc
    if not isinstance(raw, dict):
        raise ManifestError("manifest root must be an object")
    return _parse(raw)
