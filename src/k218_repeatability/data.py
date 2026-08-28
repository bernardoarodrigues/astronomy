from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .manifest import K218Manifest, MemberSpec


class DataError(ValueError):
    """Raised when a pinned published spectrum violates its frozen schema."""


@dataclass(frozen=True)
class VisitSpectrum:
    reduction: str
    visit: str
    detector: str
    wavelength_micrometres: np.ndarray
    lower_micrometres: np.ndarray
    upper_micrometres: np.ndarray
    depth_ppm: np.ndarray
    uncertainty_ppm: np.ndarray
    source_error_low_ppm: np.ndarray
    source_error_high_ppm: np.ndarray
    source_metadata: dict[str, str]


_EXOTEDRF_COLUMNS = (
    "instrname",
    "reference",
    "bandpass",
    "iwave",
    "wave",
    "waveMin",
    "waveMax",
    "xMin",
    "xMax",
    "yval",
    "yerrLow",
    "yerrUpp",
    "wlcLow",
    "wlcUpp",
    "ignore",
    "referenceLink",
)
_EUREKA_COLUMNS = (
    "wavelength",
    "bin_width",
    "rp^2_value",
    "rp^2_errorneg",
    "rp^2_errorpos",
)


def _read_text(path: Path) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise DataError(f"could not read spectrum {path}: {exc}") from exc


def _finite(*arrays: np.ndarray) -> None:
    if not all(np.all(np.isfinite(array)) for array in arrays):
        raise DataError("spectrum contains nonfinite numeric values")


def _validate_spectrum(spectrum: VisitSpectrum, spec: MemberSpec) -> VisitSpectrum:
    arrays = (
        spectrum.wavelength_micrometres,
        spectrum.lower_micrometres,
        spectrum.upper_micrometres,
        spectrum.depth_ppm,
        spectrum.uncertainty_ppm,
        spectrum.source_error_low_ppm,
        spectrum.source_error_high_ppm,
    )
    if any(array.ndim != 1 for array in arrays):
        raise DataError("spectrum arrays must be one-dimensional")
    if any(array.size != spec.rows for array in arrays):
        raise DataError(f"{spec.role} expected {spec.rows} data rows")
    _finite(*arrays)
    wave = spectrum.wavelength_micrometres
    lower = spectrum.lower_micrometres
    upper = spectrum.upper_micrometres
    if not np.all(np.diff(wave) > 0):
        raise DataError("wavelengths must be strictly increasing")
    if not np.all(lower < wave) or not np.all(wave < upper):
        raise DataError("every wavelength centre must lie inside its native interval")
    if not np.all(spectrum.source_error_low_ppm > 0) or not np.all(
        spectrum.source_error_high_ppm > 0
    ):
        raise DataError("both reported asymmetric errors must be positive")
    expected_sigma = np.maximum(
        spectrum.source_error_low_ppm, spectrum.source_error_high_ppm
    )
    if not np.array_equal(spectrum.uncertainty_ppm, expected_sigma):
        raise DataError("uncertainty is not the conservative maximum of reported errors")
    if not np.all(spectrum.uncertainty_ppm > 0):
        raise DataError("symmetrized uncertainties must be positive")
    if not np.all((spectrum.depth_ppm > 0) & (spectrum.depth_ppm < 100_000)):
        raise DataError("transit depth is outside the frozen ppm scale")
    if not np.all(spectrum.uncertainty_ppm < 100_000):
        raise DataError("uncertainty is outside the frozen ppm scale")
    if not np.allclose(lower[1:], upper[:-1], rtol=0.0, atol=1e-12):
        raise DataError("native wavelength cells must be contiguous and non-overlapping")
    if not np.isclose(wave[0], spec.wavelength_min_micrometres, rtol=0.0, atol=1e-12):
        raise DataError("first wavelength differs from the frozen manifest")
    if not np.isclose(wave[-1], spec.wavelength_max_micrometres, rtol=0.0, atol=1e-12):
        raise DataError("last wavelength differs from the frozen manifest")
    return spectrum


def _parse_exotedrf(text: str, spec: MemberSpec, manifest: K218Manifest) -> VisitSpectrum:
    lines = text.splitlines()
    required_metadata = (
        "# %ECSV 1.0",
        "# - {name: wave, unit: um, datatype: float64}",
        "# - {name: waveMin, unit: um, datatype: float64}",
        "# - {name: waveMax, unit: um, datatype: float64}",
        "# - {name: yval, unit: ppm, datatype: float64}",
        "# - {name: yerrLow, unit: ppm, datatype: float64}",
        "# - {name: yerrUpp, unit: ppm, datatype: float64}",
        "# delimiter: ','",
    )
    if any(item not in lines[:40] for item in required_metadata):
        raise DataError("malformed exoTEDRF ECSV schema or unit metadata")
    header = ",".join(_EXOTEDRF_COLUMNS)
    try:
        start = lines.index(header)
    except ValueError as exc:
        raise DataError("malformed exoTEDRF column header") from exc
    reader = csv.DictReader(io.StringIO("\n".join(lines[start:])))
    if tuple(reader.fieldnames or ()) != _EXOTEDRF_COLUMNS:
        raise DataError("exoTEDRF columns differ from the frozen schema")
    rows = list(reader)
    if len(rows) != spec.rows:
        raise DataError(f"{spec.role} expected {spec.rows} rows, found {len(rows)}")
    numeric: list[list[float]] = []
    for line_number, row in enumerate(rows, start=start + 2):
        if row["instrname"] != "NIRSPEC_G395H_NRS2" or row["reference"] != "ExoTEP":
            raise DataError(f"line {line_number}: unexpected instrument or reduction tag")
        if row["bandpass"] != "uniform" or row["ignore"] != "0":
            raise DataError(f"line {line_number}: unsupported bandpass or ignored data row")
        try:
            iwave = int(row["iwave"])
            values = [
                float(row[name])
                for name in ("wave", "waveMin", "waveMax", "yval", "yerrLow", "yerrUpp")
            ]
        except (TypeError, ValueError) as exc:
            raise DataError(f"line {line_number}: nonnumeric exoTEDRF field") from exc
        if iwave != len(numeric):
            raise DataError("exoTEDRF iwave must be the consecutive zero-based row index")
        numeric.append(values)
    values = np.asarray(numeric, dtype=np.float64)
    wave, lower, upper, depth, error_low, error_high = values.T
    date = str(
        manifest.program["complete_g395h_visit_inventory"][spec.visit][
            "observation_date_utc"
        ]
    )
    date_lines = [line for line in lines[:40] if line.startswith("# - {date:")]
    if len(date_lines) != 1 or date not in date_lines[0]:
        raise DataError("exoTEDRF observation date does not match the visit inventory")
    spectrum = VisitSpectrum(
        reduction=spec.reduction,
        visit=spec.visit,
        detector=spec.detector,
        wavelength_micrometres=wave,
        lower_micrometres=lower,
        upper_micrometres=upper,
        depth_ppm=depth,
        uncertainty_ppm=np.maximum(error_low, error_high),
        source_error_low_ppm=error_low,
        source_error_high_ppm=error_high,
        source_metadata={
            "format": "ECSV comma-separated",
            "depth_input_unit": "ppm",
            "embedded_visit_label": "1",
            "embedded_visit_label_scope": "reduction_local_not_science_visit",
            "observation_date_utc": date,
        },
    )
    return _validate_spectrum(spectrum, spec)


def _parse_eureka(text: str, spec: MemberSpec) -> VisitSpectrum:
    lines = text.splitlines()
    if "# %ECSV 1.0" not in lines[:10]:
        raise DataError("malformed Eureka ECSV schema")
    header = " ".join(_EUREKA_COLUMNS)
    try:
        start = lines.index(header)
    except ValueError as exc:
        raise DataError("malformed Eureka column header") from exc
    rows: list[list[float]] = []
    for line_number, raw in enumerate(lines[start + 1 :], start=start + 2):
        if not raw.strip():
            continue
        fields = raw.split()
        if len(fields) != len(_EUREKA_COLUMNS):
            raise DataError(f"line {line_number}: expected five Eureka numeric columns")
        try:
            rows.append([float(value) for value in fields])
        except ValueError as exc:
            raise DataError(f"line {line_number}: nonnumeric Eureka field") from exc
    if len(rows) != spec.rows:
        raise DataError(f"{spec.role} expected {spec.rows} rows, found {len(rows)}")
    values = np.asarray(rows, dtype=np.float64)
    _finite(values)
    wave, half_width, depth_fraction, error_low_fraction, error_high_fraction = values.T
    if not np.all(half_width > 0):
        raise DataError("Eureka native half-widths must be positive")
    if not np.all((depth_fraction > 0) & (depth_fraction < 0.1)):
        raise DataError("Eureka rp-squared values are outside the frozen fractional scale")
    if not np.all(error_low_fraction > 0) or not np.all(error_high_fraction > 0):
        raise DataError("both Eureka asymmetric errors must be positive")
    scale = 1_000_000.0
    error_low = error_low_fraction * scale
    error_high = error_high_fraction * scale
    spectrum = VisitSpectrum(
        reduction=spec.reduction,
        visit=spec.visit,
        detector=spec.detector,
        wavelength_micrometres=wave,
        lower_micrometres=wave - half_width,
        upper_micrometres=wave + half_width,
        depth_ppm=depth_fraction * scale,
        uncertainty_ppm=np.maximum(error_low, error_high),
        source_error_low_ppm=error_low,
        source_error_high_ppm=error_high,
        source_metadata={
            "format": "ECSV whitespace-separated",
            "depth_input_unit": "fractional_transit_depth",
            "depth_output_unit": "ppm",
            "bin_width_interpretation": "native_half_width_micrometres",
            "unit_basis": "frozen field semantics and validated value scale; ECSV tags absent",
        },
    )
    return _validate_spectrum(spectrum, spec)


def load_spectrum(path: Path, spec: MemberSpec, manifest: K218Manifest) -> VisitSpectrum:
    text = _read_text(path)
    if spec.reduction == "exoTEDRF":
        return _parse_exotedrf(text, spec, manifest)
    if spec.reduction == "Eureka":
        return _parse_eureka(text, spec)
    raise DataError(f"unsupported reduction {spec.reduction!r}")
