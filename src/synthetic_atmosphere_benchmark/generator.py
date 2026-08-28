from __future__ import annotations

import hashlib

import numpy as np

from .challenge import ChallengeBundle, ChallengeCase
from .manifest import SyntheticManifest
from .source import Scaffold
from .truth import CaseTruth, TruthBundle


def within_detector_ar1_covariance(
    uncertainty: np.ndarray, detector: np.ndarray, rho: float
) -> np.ndarray:
    uncertainty = np.asarray(uncertainty, dtype=np.float64)
    detector = np.asarray(detector, dtype=bool)
    if uncertainty.ndim != 1 or detector.shape != uncertainty.shape:
        raise ValueError("uncertainty and detector vectors must have matching shapes")
    if not np.all(np.isfinite(uncertainty)) or not np.all(uncertainty > 0):
        raise ValueError("uncertainties must be finite and positive")
    if not 0 <= rho < 1:
        raise ValueError("rho must be in [0, 1)")
    index = np.arange(uncertainty.size)
    distance = np.abs(index[:, None] - index[None, :])
    same_detector = detector[:, None] == detector[None, :]
    correlation = np.where(same_detector, np.power(rho, distance), 0.0)
    return uncertainty[:, None] * uncertainty[None, :] * correlation


def covariance_for_case(
    uncertainty: np.ndarray, detector: np.ndarray, kind: str, rho: float
) -> np.ndarray:
    if kind == "diagonal":
        if rho != 0.0:
            raise ValueError("diagonal covariance requires rho=0")
        return np.diag(np.square(uncertainty))
    if kind == "within_detector_ar1":
        return within_detector_ar1_covariance(uncertainty, detector, rho)
    raise ValueError(f"unsupported covariance kind {kind!r}")


def _seed_family(family: str) -> str:
    # Preserve the prereview synthetic draws when correcting the misleading
    # public family name. This alias is part of the frozen manifest contract.
    return {"ambiguous_cancellation": "nonidentifiable"}.get(family, family)


def _spawn_key(family: str, replicate: int, stream: str) -> tuple[int, ...]:
    payload = (
        f"synthetic-atmosphere-b3a-v1|{stream}|{_seed_family(family)}|{replicate}"
    ).encode("ascii")
    digest = hashlib.sha256(payload).digest()
    return tuple(int.from_bytes(digest[index : index + 4], "little") for index in range(0, 16, 4))


def _rng(manifest: SyntheticManifest, family: str, replicate: int, stream: str) -> np.random.Generator:
    seed = np.random.SeedSequence(
        entropy=manifest.root_entropy,
        spawn_key=_spawn_key(family, replicate, stream),
    )
    return np.random.Generator(np.random.PCG64DXSM(seed))


def _public_case_id(family: str, replicate: int) -> str:
    # This is a non-semantic identifier, not a secret or blinding mechanism:
    # the public generator permits enumeration back to family and replicate.
    payload = f"b3a-public-id-v1|{family}|{replicate}".encode("ascii")
    return hashlib.sha256(payload).hexdigest()[:24]


def _covariance_assignment(family: str, replicate: int) -> tuple[str, float]:
    if family == "null":
        return "diagonal", 0.0
    if family == "correlated_null":
        return "within_detector_ar1", (0.25, 0.5)[replicate % 2]
    options = (("diagonal", 0.0), ("within_detector_ar1", 0.25), ("within_detector_ar1", 0.5))
    return options[replicate % len(options)]


def _omitted_template(scaffold: Scaffold) -> np.ndarray:
    phase = (scaffold.wavelength_um - scaffold.wavelength_um[0]) / np.ptp(scaffold.wavelength_um)
    raw = np.sin(2.0 * np.pi * (3.25 * phase + 0.11))
    full = np.column_stack(
        (scaffold.nuisance_design, scaffold.planet_template_ppm, scaffold.stellar_template_ppm)
    )
    weights = 1.0 / np.square(scaffold.uncertainty_ppm)
    beta = np.linalg.solve(full.T @ (weights[:, None] * full), full.T @ (weights * raw))
    residual = raw - full @ beta
    return residual / np.sqrt(residual @ (weights * residual))


def _truth_parameters(family: str) -> tuple[float, float, float, float, str, bool]:
    # Planet and stellar coefficients are signed, standardized template amplitudes.
    table = {
        "null": (0.0, 0.0, 0.0, 0.0, "none", True),
        "correlated_null": (0.0, 0.0, 0.0, 0.0, "none", True),
        "strong_planet": (6.0, 0.0, 0.0, 0.0, "planetary_supported", True),
        "weak_planet": (1.5, 0.0, 0.0, 0.0, "none", True),
        "stellar_only": (0.0, 6.0, 0.0, 0.0, "stellar_supported", True),
        "detector_only": (0.0, 0.0, 60.0, 0.0, "none", True),
        "planet_stellar": (6.0, 6.0, 0.0, 0.0, "joint_supported", True),
        "omitted_template": (0.0, 0.0, 0.0, 10.0, "model_inadequate", False),
        "ambiguous_cancellation": (
            3.0,
            -3.0,
            0.0,
            0.0,
            "conflicting_single_template_support",
            True,
        ),
    }
    return table[family]


def generate_public_suite(
    manifest: SyntheticManifest,
    scaffold: Scaffold,
    *,
    family_order: tuple[str, ...] | None = None,
) -> tuple[ChallengeBundle, TruthBundle]:
    families = manifest.families if family_order is None else family_order
    if set(families) != set(manifest.families) or len(families) != len(manifest.families):
        raise ValueError("family_order must be a permutation of the frozen family inventory")
    omitted = _omitted_template(scaffold)
    challenge_cases: list[ChallengeCase] = []
    truths: list[CaseTruth] = []
    for family in families:
        planet, stellar, step, omitted_amplitude, expected, coverage = _truth_parameters(family)
        for replicate in range(manifest.cases_per_family):
            kind, rho = _covariance_assignment(family, replicate)
            nuisance_rng = _rng(manifest, family, replicate, "nuisance")
            noise_rng = _rng(manifest, family, replicate, "noise")
            intercept = float(nuisance_rng.normal(1350.0, 30.0))
            trend = float(nuisance_rng.normal(0.0, 35.0))
            incidental_step = float(nuisance_rng.normal(0.0, 8.0))
            true_step = step + incidental_step
            mean = (
                scaffold.nuisance_design @ np.asarray([intercept, trend, true_step])
                + planet * scaffold.planet_template_ppm
                + stellar * scaffold.stellar_template_ppm
                + omitted_amplitude * omitted
            )
            covariance = covariance_for_case(scaffold.uncertainty_ppm, scaffold.detector_nrs2, kind, rho)
            # np.dot avoids a spurious floating-point warning emitted by some
            # macOS Accelerate builds for finite matrix-vector matmul inputs.
            noise = np.dot(np.linalg.cholesky(covariance), noise_rng.standard_normal(mean.size))
            case_id = _public_case_id(family, replicate)
            challenge_cases.append(
                ChallengeCase(
                    case_id=case_id,
                    synthetic_depth=tuple(float(value) for value in mean + noise),
                    covariance_kind=kind,
                    covariance_rho=float(rho),
                )
            )
            truths.append(
                CaseTruth(
                    case_id=case_id,
                    family=family,
                    replicate=replicate,
                    planet_coefficient=planet,
                    stellar_coefficient=stellar,
                    detector_step_ppm=true_step,
                    expected_origin=expected,
                    coverage_eligible=coverage,
                    spawn_key=_spawn_key(family, replicate, "noise"),
                )
            )
    # Presentation order has no family label and does not depend on loop order.
    order = lambda case_id: hashlib.sha256(f"b3a-order-v1|{case_id}".encode("ascii")).hexdigest()
    challenge_cases.sort(key=lambda item: order(item.case_id))
    truths.sort(key=lambda item: item.case_id)
    challenge = ChallengeBundle(
        schema_version=1,
        benchmark_id=manifest.benchmark_id,
        contract_sha256=manifest.contract_sha256,
        depth_unit="ppm",
        wavelength_unit="micrometre",
        wavelength=tuple(float(value) for value in scaffold.wavelength_um),
        bin_width=tuple(float(value) for value in scaffold.bin_width_um),
        uncertainty=tuple(float(value) for value in scaffold.uncertainty_ppm),
        detector_split=float(manifest.raw["grid"]["detector_split_micrometres"]),
        planet_template=tuple(float(value) for value in scaffold.planet_template_ppm),
        stellar_template=tuple(float(value) for value in scaffold.stellar_template_ppm),
        cases=tuple(challenge_cases),
    )
    challenge.validate()
    truth = TruthBundle(
        schema_version=1,
        benchmark_id=manifest.benchmark_id,
        contract_sha256=manifest.contract_sha256,
        cases=tuple(truths),
    )
    return challenge, truth
