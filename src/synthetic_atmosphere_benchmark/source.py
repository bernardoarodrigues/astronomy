from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .canonical import sha256_file
from .manifest import SyntheticManifest


class SourceError(ValueError):
    """Raised when a pinned source member or derived scaffold is invalid."""


@dataclass(frozen=True)
class SourcePaths:
    transmission: Path
    water: Path
    stellar: Path


@dataclass(frozen=True)
class Scaffold:
    wavelength_um: np.ndarray
    bin_width_um: np.ndarray
    uncertainty_ppm: np.ndarray
    detector_nrs2: np.ndarray
    planet_template_ppm: np.ndarray
    stellar_template_ppm: np.ndarray
    nuisance_design: np.ndarray


def resolve_source_paths(manifest: SyntheticManifest, extracted_root: Path) -> SourcePaths:
    root = Path(extracted_root)
    return SourcePaths(
        transmission=root / manifest.member_for_role("eureka_grid_uncertainties").path,
        water=root / manifest.member_for_role("picaso_water_template").path,
        stellar=root / manifest.member_for_role("phoenix_m1_m3_models").path,
    )


def _verify_member(path: Path, *, size_bytes: int, sha256: str) -> dict[str, object]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise SourceError(f"missing source member {path}: {exc}") from exc
    if size != size_bytes:
        raise SourceError(f"size mismatch for {path}: expected {size_bytes}, found {size}")
    actual = sha256_file(path)
    if actual != sha256:
        raise SourceError(f"SHA-256 mismatch for {path}: expected {sha256}, found {actual}")
    return {"path": str(path), "size_bytes": size, "sha256": actual, "status": "verified"}


def verify_sources(manifest: SyntheticManifest, extracted_root: Path) -> list[dict[str, object]]:
    paths = resolve_source_paths(manifest, extracted_root)
    by_role = {
        "eureka_grid_uncertainties": paths.transmission,
        "picaso_water_template": paths.water,
        "phoenix_m1_m3_models": paths.stellar,
    }
    records = []
    for role in sorted(by_role):
        member = manifest.member_for_role(role)
        record = _verify_member(by_role[role], size_bytes=member.size_bytes, sha256=member.sha256)
        record["role"] = role
        records.append(record)
    return records


def _lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise SourceError(f"could not read {path}: {exc}") from exc


def _validate_vector(value: np.ndarray, *, name: str, positive: bool = False) -> None:
    if value.ndim != 1 or value.size == 0 or not np.all(np.isfinite(value)):
        raise SourceError(f"{name} must be a finite nonempty vector")
    if positive and not np.all(value > 0):
        raise SourceError(f"{name} must be positive")


def load_eureka_scaffold(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Load only wavelength, width, and uncertainty; observed depths are never parsed."""

    rows: list[tuple[float, float, float]] = []
    for line_number, raw in enumerate(_lines(path), start=1):
        fields = raw.split()
        if not fields or fields[0] != "Eureka":
            continue
        if len(fields) != 5:
            raise SourceError(f"Eureka line {line_number}: expected five columns")
        try:
            # fields[3] is the observed transit depth and is intentionally ignored.
            rows.append((float(fields[1]), float(fields[2]), float(fields[4])))
        except ValueError as exc:
            raise SourceError(f"Eureka line {line_number}: invalid grid/uncertainty value") from exc
    if len(rows) != 110:
        raise SourceError(f"expected 110 Eureka rows, found {len(rows)}")
    values = np.asarray(rows, dtype=np.float64)
    wavelength, width, uncertainty = values.T
    _validate_vector(wavelength, name="Eureka wavelengths")
    _validate_vector(width, name="Eureka bin widths", positive=True)
    _validate_vector(uncertainty, name="Eureka uncertainties", positive=True)
    if not np.all(np.diff(wavelength) > 0):
        raise SourceError("Eureka wavelengths must be strictly increasing")
    keep = wavelength >= 2.87
    if int(np.count_nonzero(keep)) != 109:
        raise SourceError("the frozen >=2.87 micrometre selection must contain 109 rows")
    return wavelength[keep], width[keep], uncertainty[keep]


def _numeric_pairs(path: Path, *, accepted_prefixes: tuple[str, ...] = ()) -> dict[str, np.ndarray] | np.ndarray:
    if accepted_prefixes:
        grouped: dict[str, list[tuple[float, float]]] = {item: [] for item in accepted_prefixes}
        for raw in _lines(path):
            fields = raw.split()
            if not fields or fields[0] not in grouped or len(fields) != 3:
                continue
            try:
                grouped[fields[0]].append((float(fields[1]), float(fields[2])))
            except ValueError as exc:
                raise SourceError(f"invalid {fields[0]} model row") from exc
        return {key: np.asarray(value, dtype=np.float64) for key, value in grouped.items()}
    rows: list[tuple[float, float]] = []
    for raw in _lines(path):
        fields = raw.split()
        if len(fields) != 2:
            continue
        try:
            rows.append((float(fields[0]), float(fields[1])))
        except ValueError:
            continue
    return np.asarray(rows, dtype=np.float64)


def _validate_model(values: np.ndarray, *, expected_rows: int, name: str) -> None:
    if values.shape != (expected_rows, 2) or not np.all(np.isfinite(values)):
        raise SourceError(f"{name} must contain {expected_rows} finite two-column rows")
    if not np.all(np.diff(values[:, 0]) > 0):
        raise SourceError(f"{name} wavelengths must be strictly increasing")
    if not np.all(values[:, 1] > 0):
        raise SourceError(f"{name} values must be positive")


def _bin_average(model_x: np.ndarray, model_y: np.ndarray, centers: np.ndarray, widths: np.ndarray) -> np.ndarray:
    result = np.empty_like(centers)
    for index, (center, width) in enumerate(zip(centers, widths, strict=True)):
        low = center - width / 2.0
        high = center + width / 2.0
        if low < model_x[0] or high > model_x[-1]:
            raise SourceError("requested bin lies outside a template wavelength range")
        internal = model_x[(model_x > low) & (model_x < high)]
        sample_x = np.concatenate(([low], internal, [high]))
        sample_y = np.interp(sample_x, model_x, model_y)
        integral = np.sum((sample_y[:-1] + sample_y[1:]) * np.diff(sample_x) / 2.0)
        result[index] = integral / width
    return result


def _project_and_normalize(template: np.ndarray, nuisance: np.ndarray, uncertainty: np.ndarray) -> np.ndarray:
    weights = 1.0 / np.square(uncertainty)
    normal = nuisance.T @ (weights[:, None] * nuisance)
    beta = np.linalg.solve(normal, nuisance.T @ (weights * template))
    centered = template - nuisance @ beta
    norm = float(np.sqrt(centered @ (weights * centered)))
    if not np.isfinite(norm) or norm <= 0:
        raise SourceError("template has no nuisance-orthogonal information")
    return centered / norm


def build_scaffold(manifest: SyntheticManifest, extracted_root: Path) -> Scaffold:
    verify_sources(manifest, extracted_root)
    paths = resolve_source_paths(manifest, extracted_root)
    wavelength, width, uncertainty = load_eureka_scaffold(paths.transmission)
    detector = wavelength >= float(manifest.raw["grid"]["detector_split_micrometres"])
    trend = wavelength - float(np.average(wavelength, weights=1.0 / np.square(uncertainty)))
    trend /= float(np.ptp(wavelength))
    nuisance = np.column_stack((np.ones(wavelength.size), trend, detector.astype(np.float64)))

    water = _numeric_pairs(paths.water)
    assert isinstance(water, np.ndarray)
    _validate_model(water, expected_rows=665, name="PICASO water model")
    water_ppm = _bin_average(water[:, 0], water[:, 1] * 1_000_000.0, wavelength, width)

    stellar = _numeric_pairs(paths.stellar, accepted_prefixes=("M1", "M3"))
    assert isinstance(stellar, dict)
    _validate_model(stellar["M1"], expected_rows=9465, name="PHOENIX M1 model")
    _validate_model(stellar["M3"], expected_rows=9465, name="PHOENIX M3 model")
    m1_x, m1_flux = stellar["M1"].T
    m3_x, m3_flux = stellar["M3"].T
    contrast_ppm = (np.interp(m1_x, m3_x, m3_flux) / m1_flux - 1.0) * 1_000_000.0
    # The deposited stellar grid ends just short of the final Eureka centers.
    # The frozen B3a contrast therefore uses center interpolation with NumPy's
    # explicit constant endpoint behavior; it does not bridge the detector gap.
    stellar_ppm = np.interp(wavelength, m1_x, contrast_ppm)

    planet_template = _project_and_normalize(water_ppm, nuisance, uncertainty)
    stellar_template = _project_and_normalize(stellar_ppm, nuisance, uncertainty)
    if not all(
        np.all(np.isfinite(item))
        for item in (wavelength, width, uncertainty, planet_template, stellar_template, nuisance)
    ):
        raise SourceError("derived scaffold contains nonfinite values")
    return Scaffold(
        wavelength_um=wavelength,
        bin_width_um=width,
        uncertainty_ppm=uncertainty,
        detector_nrs2=detector,
        planet_template_ppm=planet_template,
        stellar_template_ppm=stellar_template,
        nuisance_design=nuisance,
    )


def scaffold_fingerprints(scaffold: Scaffold) -> dict[str, object]:
    import hashlib

    def digest(value: np.ndarray) -> str:
        array = np.asarray(value, dtype="<f8")
        return hashlib.sha256(array.tobytes(order="C")).hexdigest()

    weights = 1.0 / np.square(scaffold.uncertainty_ppm)
    correlation = float(
        (scaffold.planet_template_ppm @ (weights * scaffold.stellar_template_ppm))
        / np.sqrt(
            (scaffold.planet_template_ppm @ (weights * scaffold.planet_template_ppm))
            * (scaffold.stellar_template_ppm @ (weights * scaffold.stellar_template_ppm))
        )
    )
    return {
        "rows": int(scaffold.wavelength_um.size),
        "wavelength_sha256": digest(scaffold.wavelength_um),
        "width_sha256": digest(scaffold.bin_width_um),
        "uncertainty_sha256": digest(scaffold.uncertainty_ppm),
        "planet_template_sha256": digest(scaffold.planet_template_ppm),
        "stellar_template_sha256": digest(scaffold.stellar_template_ppm),
        "template_weighted_correlation": correlation,
    }
