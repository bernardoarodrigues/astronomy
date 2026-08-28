from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


class ChallengeError(ValueError):
    """Raised when a truth-free challenge does not match its public schema."""


@dataclass(frozen=True)
class ChallengeCase:
    case_id: str
    synthetic_depth: tuple[float, ...]
    covariance_kind: str
    covariance_rho: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "covariance": {"kind": self.covariance_kind, "rho": self.covariance_rho},
            "synthetic_depth": list(self.synthetic_depth),
        }


@dataclass(frozen=True)
class ChallengeBundle:
    schema_version: int
    benchmark_id: str
    contract_sha256: str
    depth_unit: str
    wavelength_unit: str
    wavelength: tuple[float, ...]
    bin_width: tuple[float, ...]
    uncertainty: tuple[float, ...]
    detector_split: float
    planet_template: tuple[float, ...]
    stellar_template: tuple[float, ...]
    cases: tuple[ChallengeCase, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "benchmark_id": self.benchmark_id,
            "cases": [case.to_dict() for case in self.cases],
            "contract_sha256": self.contract_sha256,
            "depth_unit": self.depth_unit,
            "grid": {
                "bin_width": list(self.bin_width),
                "detector_split": self.detector_split,
                "uncertainty": list(self.uncertainty),
                "wavelength": list(self.wavelength),
                "wavelength_unit": self.wavelength_unit,
            },
            "schema_version": self.schema_version,
            "templates": {
                "planet": list(self.planet_template),
                "stellar": list(self.stellar_template),
            },
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ChallengeBundle":
        try:
            grid = raw["grid"]
            templates = raw["templates"]
            cases = tuple(
                ChallengeCase(
                    case_id=str(item["case_id"]),
                    synthetic_depth=tuple(float(value) for value in item["synthetic_depth"]),
                    covariance_kind=str(item["covariance"]["kind"]),
                    covariance_rho=float(item["covariance"]["rho"]),
                )
                for item in raw["cases"]
            )
            bundle = cls(
                schema_version=int(raw["schema_version"]),
                benchmark_id=str(raw["benchmark_id"]),
                contract_sha256=str(raw["contract_sha256"]),
                depth_unit=str(raw["depth_unit"]),
                wavelength_unit=str(grid["wavelength_unit"]),
                wavelength=tuple(float(value) for value in grid["wavelength"]),
                bin_width=tuple(float(value) for value in grid["bin_width"]),
                uncertainty=tuple(float(value) for value in grid["uncertainty"]),
                detector_split=float(grid["detector_split"]),
                planet_template=tuple(float(value) for value in templates["planet"]),
                stellar_template=tuple(float(value) for value in templates["stellar"]),
                cases=cases,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ChallengeError(f"malformed challenge: {exc}") from exc
        bundle.validate()
        return bundle

    def validate(self) -> None:
        if self.schema_version != 1:
            raise ChallengeError("challenge schema_version must be 1")
        if self.depth_unit not in {"ppm", "fraction", "percent"}:
            raise ChallengeError("unsupported depth unit")
        if self.wavelength_unit not in {"micrometre", "nanometre"}:
            raise ChallengeError("unsupported wavelength unit")
        arrays = [self.wavelength, self.bin_width, self.uncertainty, self.planet_template, self.stellar_template]
        lengths = {len(item) for item in arrays}
        if len(lengths) != 1 or next(iter(lengths), 0) < 6:
            raise ChallengeError("grid, uncertainty, and template lengths must agree")
        numeric = [np.asarray(item, dtype=np.float64) for item in arrays]
        if not all(np.all(np.isfinite(item)) for item in numeric):
            raise ChallengeError("challenge scaffold contains nonfinite values")
        if not np.all(np.diff(numeric[0]) > 0):
            raise ChallengeError("wavelengths must be strictly increasing")
        if not np.all(numeric[1] > 0) or not np.all(numeric[2] > 0):
            raise ChallengeError("bin widths and uncertainties must be positive")
        if len({case.case_id for case in self.cases}) != len(self.cases):
            raise ChallengeError("case IDs must be unique")
        for case in self.cases:
            if len(case.synthetic_depth) != len(self.wavelength):
                raise ChallengeError(f"case {case.case_id}: depth length mismatch")
            if not np.all(np.isfinite(np.asarray(case.synthetic_depth, dtype=np.float64))):
                raise ChallengeError(f"case {case.case_id}: nonfinite depth")
            if case.covariance_kind not in {"diagonal", "within_detector_ar1"}:
                raise ChallengeError(f"case {case.case_id}: unsupported covariance")
            if case.covariance_kind == "diagonal" and case.covariance_rho != 0.0:
                raise ChallengeError(f"case {case.case_id}: diagonal covariance must use rho=0")
            if case.covariance_kind == "within_detector_ar1" and not 0 < case.covariance_rho < 1:
                raise ChallengeError(f"case {case.case_id}: AR(1) rho must be between zero and one")
