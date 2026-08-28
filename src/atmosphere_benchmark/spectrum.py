from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


class SpectrumError(ValueError):
    """Raised when a spectrum violates the frozen tabular schema."""


@dataclass(frozen=True)
class Spectrum:
    wavelength: np.ndarray
    transit_depth: np.ndarray
    bin_width: np.ndarray
    uncertainty: np.ndarray

    def subset(self, mask: np.ndarray) -> "Spectrum":
        return Spectrum(
            wavelength=self.wavelength[mask],
            transit_depth=self.transit_depth[mask],
            bin_width=self.bin_width[mask],
            uncertainty=self.uncertainty[mask],
        )


def load_spectrum(
    path: Path,
    *,
    expected_columns: tuple[str, ...] = (
        "wv_center",
        "transit_depth",
        "wv_wdth",
        "tran_unc",
    ),
    expected_rows: int | None = None,
) -> Spectrum:
    try:
        lines = [
            line.strip()
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, UnicodeError) as exc:
        raise SpectrumError(f"could not read spectrum {path}: {exc}") from exc
    if not lines or tuple(lines[0].split()) != expected_columns:
        actual = tuple(lines[0].split()) if lines else ()
        raise SpectrumError(
            f"malformed spectrum schema: expected {expected_columns}, got {actual}"
        )

    rows: list[list[float]] = []
    for line_number, line in enumerate(lines[1:], start=2):
        fields = line.split()
        if len(fields) != 4:
            raise SpectrumError(f"line {line_number}: expected exactly 4 columns")
        try:
            rows.append([float(field) for field in fields])
        except ValueError as exc:
            raise SpectrumError(f"line {line_number}: nonnumeric value") from exc
    if expected_rows is not None and len(rows) != expected_rows:
        raise SpectrumError(
            f"expected {expected_rows} data rows, found {len(rows)}"
        )
    if not rows:
        raise SpectrumError("spectrum contains no data rows")

    values = np.asarray(rows, dtype=np.float64)
    if not np.all(np.isfinite(values)):
        raise SpectrumError("spectrum contains nonfinite values")
    wavelength, depth, width, uncertainty = values.T
    if not np.all(np.diff(wavelength) > 0):
        raise SpectrumError("wavelengths must be strictly increasing")
    if not np.all(width > 0):
        raise SpectrumError("bin widths must be positive")
    if not np.all(uncertainty > 0):
        raise SpectrumError("uncertainties must be positive")
    return Spectrum(wavelength, depth, width, uncertainty)


def load_two_column_model(path: Path) -> tuple[np.ndarray, np.ndarray]:
    rows: list[list[float]] = []
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise SpectrumError(f"could not read model {path}: {exc}") from exc
    for line_number, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) != 2:
            raise SpectrumError(f"model line {line_number}: expected 2 columns")
        try:
            rows.append([float(field) for field in fields])
        except ValueError as exc:
            raise SpectrumError(f"model line {line_number}: nonnumeric value") from exc
    if not rows:
        raise SpectrumError("model contains no numeric rows")
    values = np.asarray(rows, dtype=np.float64)
    if not np.all(np.isfinite(values)):
        raise SpectrumError("model contains nonfinite values")
    wavelength, depth = values.T
    if not np.all(np.diff(wavelength) > 0):
        raise SpectrumError("model wavelengths must be strictly increasing")
    return wavelength, depth
