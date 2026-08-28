from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class TruthError(ValueError):
    """Raised when the scorer's separate truth bundle is malformed."""


@dataclass(frozen=True)
class CaseTruth:
    case_id: str
    family: str
    replicate: int
    planet_coefficient: float
    stellar_coefficient: float
    detector_step_ppm: float
    expected_origin: str
    coverage_eligible: bool
    spawn_key: tuple[int, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "coverage_eligible": self.coverage_eligible,
            "detector_step_ppm": self.detector_step_ppm,
            "expected_origin": self.expected_origin,
            "family": self.family,
            "planet_coefficient": self.planet_coefficient,
            "replicate": self.replicate,
            "spawn_key": list(self.spawn_key),
            "stellar_coefficient": self.stellar_coefficient,
        }


@dataclass(frozen=True)
class TruthBundle:
    schema_version: int
    benchmark_id: str
    contract_sha256: str
    cases: tuple[CaseTruth, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "benchmark_id": self.benchmark_id,
            "cases": [item.to_dict() for item in self.cases],
            "contract_sha256": self.contract_sha256,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "TruthBundle":
        try:
            result = cls(
                schema_version=int(raw["schema_version"]),
                benchmark_id=str(raw["benchmark_id"]),
                contract_sha256=str(raw["contract_sha256"]),
                cases=tuple(
                    CaseTruth(
                        case_id=str(item["case_id"]),
                        family=str(item["family"]),
                        replicate=int(item["replicate"]),
                        planet_coefficient=float(item["planet_coefficient"]),
                        stellar_coefficient=float(item["stellar_coefficient"]),
                        detector_step_ppm=float(item["detector_step_ppm"]),
                        expected_origin=str(item["expected_origin"]),
                        coverage_eligible=bool(item["coverage_eligible"]),
                        spawn_key=tuple(int(value) for value in item["spawn_key"]),
                    )
                    for item in raw["cases"]
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise TruthError(f"malformed truth bundle: {exc}") from exc
        if result.schema_version != 1 or len({item.case_id for item in result.cases}) != len(result.cases):
            raise TruthError("invalid truth schema or duplicate case ID")
        return result
