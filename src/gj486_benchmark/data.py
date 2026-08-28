from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


class DataError(ValueError):
    """Raised when a frozen GJ 486 b table is malformed."""


@dataclass(frozen=True)
class TransmissionSpectrum:
    reduction: str
    wavelength: np.ndarray
    bin_width: np.ndarray
    depth_ppm: np.ndarray
    uncertainty_ppm: np.ndarray

    def subset(self, mask: np.ndarray) -> "TransmissionSpectrum":
        return TransmissionSpectrum(
            reduction=self.reduction,
            wavelength=self.wavelength[mask],
            bin_width=self.bin_width[mask],
            depth_ppm=self.depth_ppm[mask],
            uncertainty_ppm=self.uncertainty_ppm[mask],
        )


@dataclass(frozen=True)
class NumericModel:
    wavelength: np.ndarray
    values: np.ndarray


@dataclass(frozen=True)
class StellarGroup:
    name: str
    wavelength: np.ndarray
    flux_mjy: np.ndarray
    uncertainty_mjy: np.ndarray | None


@dataclass(frozen=True)
class EclipseSpectrum:
    wavelength: np.ndarray
    eclipse_depth_ppm: np.ndarray
    uncertainty_ppm: np.ndarray


def _read_lines(path: Path) -> list[str]:
    try:
        return Path(path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise DataError(f"could not read {path}: {exc}") from exc


def _validate_numeric(values: np.ndarray, *, label: str) -> None:
    if not np.all(np.isfinite(values)):
        raise DataError(f"{label} contains nonfinite values")


def load_transmission_spectra(
    path: Path,
    *,
    reductions: tuple[str, ...] = ("Eureka", "Firefly", "Tiberius"),
    expected_rows: dict[str, int] | None = None,
) -> dict[str, TransmissionSpectrum]:
    lines = _read_lines(path)
    required_header = (
        "Reduction  Reduction identifier",
        "Wave       Wavelength",
        "Width      Wavelength bin width",
        "Depth      Transit depth; parts per million",
        "e_Depth      Uncertainty in Depth",
    )
    if not all(any(fragment in line for line in lines[:40]) for fragment in required_header):
        raise DataError("malformed transmission-spectrum schema")
    start = next((index for index, line in enumerate(lines) if line.split()[:1] == [reductions[0]]), None)
    if start is None:
        raise DataError("transmission spectrum contains no data rows")
    grouped: dict[str, list[list[float]]] = {name: [] for name in reductions}
    for line_number, raw in enumerate(lines[start:], start=start + 1):
        fields = raw.split()
        if not fields:
            continue
        if fields[0] not in grouped or len(fields) != 5:
            raise DataError(f"line {line_number}: expected reduction plus four numeric columns")
        try:
            grouped[fields[0]].append([float(value) for value in fields[1:]])
        except ValueError as exc:
            raise DataError(f"line {line_number}: nonnumeric value") from exc

    result: dict[str, TransmissionSpectrum] = {}
    for reduction in reductions:
        values = np.asarray(grouped[reduction], dtype=np.float64)
        if values.size == 0:
            raise DataError(f"reduction {reduction} contains no rows")
        if expected_rows is not None and values.shape[0] != expected_rows[reduction]:
            raise DataError(f"reduction {reduction} expected {expected_rows[reduction]} rows, found {values.shape[0]}")
        _validate_numeric(values, label=f"reduction {reduction}")
        wavelength, width, depth, uncertainty = values.T
        if not np.all(np.diff(wavelength) > 0):
            raise DataError(f"reduction {reduction} wavelengths must be strictly increasing")
        if not np.all(width > 0):
            raise DataError(f"reduction {reduction} bin widths must be positive")
        if not np.all(uncertainty > 0):
            raise DataError(f"reduction {reduction} uncertainties must be positive")
        result[reduction] = TransmissionSpectrum(reduction, wavelength, width, depth, uncertainty)
    return result


def load_water_model(path: Path, *, expected_rows: int | None = None) -> NumericModel:
    rows: list[list[float]] = []
    for line_number, raw in enumerate(_read_lines(path), start=1):
        fields = raw.split()
        if len(fields) != 2:
            continue
        try:
            row = [float(value) for value in fields]
        except ValueError:
            continue
        rows.append(row)
    if expected_rows is not None and len(rows) != expected_rows:
        raise DataError(f"water model expected {expected_rows} rows, found {len(rows)}")
    if not rows:
        raise DataError("water model contains no numeric rows")
    values = np.asarray(rows, dtype=np.float64)
    _validate_numeric(values, label="water model")
    wavelength, depth = values.T
    if not np.all(np.diff(wavelength) > 0):
        raise DataError("water-model wavelengths must be strictly increasing")
    if not np.all(depth > 0):
        raise DataError("water-model transit depths must be positive")
    return NumericModel(wavelength, depth)


def load_stellar_groups(
    path: Path,
    *,
    expected_rows: dict[str, int] | None = None,
) -> dict[str, StellarGroup]:
    lines = _read_lines(path)
    required_header = ("Type   Data type", "Wave   Wavelength", "Flux   Flux density", "e_Flux   ? Uncertainty")
    if not all(any(fragment in line for line in lines[:50]) for fragment in required_header):
        raise DataError("malformed stellar-spectrum schema")
    names = ("V1", "V2", "M1", "M2", "M3")
    grouped: dict[str, list[list[float]]] = {name: [] for name in names}
    start = None
    for index, line in enumerate(lines):
        fields = line.split()
        if len(fields) != 4 or fields[0] != "V1":
            continue
        try:
            [float(value) for value in fields[1:]]
        except ValueError:
            continue
        start = index
        break
    if start is None:
        raise DataError("stellar table contains no data rows")
    for line_number, raw in enumerate(lines[start:], start=start + 1):
        fields = raw.split()
        if not fields:
            continue
        if fields[0] not in grouped:
            raise DataError(f"line {line_number}: unknown stellar group")
        expected_columns = 4 if fields[0].startswith("V") else 3
        if len(fields) != expected_columns:
            raise DataError(f"line {line_number}: wrong stellar column count")
        try:
            grouped[fields[0]].append([float(value) for value in fields[1:]])
        except ValueError as exc:
            raise DataError(f"line {line_number}: nonnumeric stellar value") from exc

    result: dict[str, StellarGroup] = {}
    for name in names:
        values = np.asarray(grouped[name], dtype=np.float64)
        if values.size == 0:
            raise DataError(f"stellar group {name} contains no rows")
        if expected_rows is not None and values.shape[0] != expected_rows[name]:
            raise DataError(f"stellar group {name} expected {expected_rows[name]} rows, found {values.shape[0]}")
        _validate_numeric(values, label=f"stellar group {name}")
        wavelength = values[:, 0]
        if not np.all(np.diff(wavelength) > 0):
            raise DataError(f"stellar group {name} wavelengths must be strictly increasing")
        uncertainty = values[:, 2] if name.startswith("V") else None
        if uncertainty is not None and not np.all(uncertainty > 0):
            raise DataError(f"stellar group {name} uncertainties must be positive")
        result[name] = StellarGroup(name, wavelength, values[:, 1], uncertainty)
    return result


def _numeric_table(path: Path, *, columns: int, label: str) -> np.ndarray:
    rows: list[list[float]] = []
    for line_number, raw in enumerate(_read_lines(path), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) != columns:
            raise DataError(f"{label} line {line_number}: expected {columns} columns")
        try:
            rows.append([float(value) for value in fields])
        except ValueError as exc:
            raise DataError(f"{label} line {line_number}: nonnumeric value") from exc
    if not rows:
        raise DataError(f"{label} contains no data rows")
    values = np.asarray(rows, dtype=np.float64)
    _validate_numeric(values, label=label)
    return values


def load_miri_spectrum(path: Path, *, expected_rows: int = 22) -> EclipseSpectrum:
    values = _numeric_table(path, columns=3, label="MIRI spectrum")
    if values.shape[0] != expected_rows:
        raise DataError(f"MIRI spectrum expected {expected_rows} rows, found {values.shape[0]}")
    wavelength, depth, uncertainty = values.T
    if not np.all(np.diff(wavelength) > 0):
        raise DataError("MIRI spectrum wavelengths must be strictly increasing")
    if not np.all(uncertainty > 0):
        raise DataError("MIRI spectrum uncertainties must be positive")
    return EclipseSpectrum(wavelength, depth, uncertainty)


def load_miri_atmosphere_model(path: Path) -> NumericModel:
    values = _numeric_table(path, columns=7, label="MIRI atmosphere model")
    wavelength = values[:, 1]
    ratio = values[:, 6]
    if not np.all(np.diff(wavelength) > 0):
        raise DataError("MIRI atmosphere-model wavelengths must be strictly increasing")
    if not np.all(ratio >= 0):
        raise DataError("MIRI atmosphere-model eclipse ratios must be nonnegative")
    return NumericModel(wavelength, ratio)


def load_miri_blackbody_model(path: Path) -> NumericModel:
    values = _numeric_table(path, columns=2, label="MIRI blackbody model")
    wavelength, ratio = values.T
    if not np.all(np.diff(wavelength) > 0):
        raise DataError("MIRI blackbody wavelengths must be strictly increasing")
    if not np.all(ratio >= 0):
        raise DataError("MIRI blackbody eclipse ratios must be nonnegative")
    return NumericModel(wavelength, ratio)
