from __future__ import annotations

import json
import os
import platform
import tempfile
from dataclasses import asdict, dataclass
from importlib import metadata
from pathlib import Path
from typing import Any, Iterable

from .integrity import verify_file
from .manifest import DatasetManifest, SignalTarget


class AnalysisError(RuntimeError):
    """Raised when the benchmark cannot produce a valid result."""


@dataclass(frozen=True)
class Hit:
    top_hit_number: int
    drift_rate_hz_per_s: float
    snr: float
    uncorrected_frequency_mhz: float
    corrected_frequency_mhz: float


def parse_turbo_seti_dat(path: Path) -> list[Hit]:
    """Parse the stable leading columns of a turboSETI DAT hit table."""

    hits: list[Hit] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            fields = line.split()
            if len(fields) < 5:
                raise AnalysisError(
                    f"{path}:{line_number}: expected at least 5 hit columns"
                )
            try:
                hit = Hit(
                    top_hit_number=int(fields[0]),
                    drift_rate_hz_per_s=float(fields[1]),
                    snr=float(fields[2]),
                    uncorrected_frequency_mhz=float(fields[3]),
                    corrected_frequency_mhz=float(fields[4]),
                )
            except ValueError as exc:
                raise AnalysisError(
                    f"{path}:{line_number}: invalid numeric hit row"
                ) from exc
            hits.append(hit)
    return sorted(hits, key=lambda hit: hit.top_hit_number)


def _hits_in_frequency_window(
    target: SignalTarget, hits: Iterable[Hit]
) -> list[Hit]:
    tolerance_mhz = target.tolerance_hz / 1_000_000.0
    return [
        hit
        for hit in hits
        if abs(hit.uncorrected_frequency_mhz - target.frequency_mhz)
        <= tolerance_mhz
    ]


def evaluate_known_signal_recovery(
    manifest: DatasetManifest, hits: Iterable[Hit]
) -> dict[str, Any]:
    hit_list = list(hits)
    target_results = []
    for target in sorted(
        manifest.benchmark.known_signal_targets, key=lambda item: item.id
    ):
        frequency_candidates = _hits_in_frequency_window(target, hit_list)
        fully_matched = [
            hit
            for hit in frequency_candidates
            if abs(hit.drift_rate_hz_per_s - target.drift_rate_hz_per_s)
            <= target.drift_tolerance_hz_per_s
        ]
        ranked = fully_matched or frequency_candidates
        best_hit = (
            sorted(ranked, key=lambda hit: (-hit.snr, hit.top_hit_number))[0]
            if ranked
            else None
        )
        frequency_error_hz = (
            round(
                (best_hit.uncorrected_frequency_mhz - target.frequency_mhz)
                * 1_000_000.0,
                9,
            )
            if best_hit is not None
            else None
        )
        drift_error = (
            round(
                best_hit.drift_rate_hz_per_s - target.drift_rate_hz_per_s,
                9,
            )
            if best_hit is not None
            else None
        )
        frequency_ok = (
            frequency_error_hz is not None
            and abs(frequency_error_hz) <= target.tolerance_hz
        )
        drift_ok = (
            drift_error is not None
            and abs(drift_error) <= target.drift_tolerance_hz_per_s
        )
        target_results.append(
            {
                "id": target.id,
                "expected_frequency_mhz": target.frequency_mhz,
                "frequency_tolerance_hz": target.tolerance_hz,
                "expected_drift_rate_hz_per_s": target.drift_rate_hz_per_s,
                "drift_tolerance_hz_per_s": target.drift_tolerance_hz_per_s,
                "required": target.required,
                "frequency_error_hz": frequency_error_hz,
                "drift_error_hz_per_s": drift_error,
                "frequency_within_tolerance": frequency_ok,
                "drift_within_tolerance": drift_ok,
                "recovered": frequency_ok and drift_ok,
                "best_hit": asdict(best_hit) if best_hit is not None else None,
            }
        )
    required_targets_passed = all(
        result["recovered"] for result in target_results if result["required"]
    )
    by_id = {result["id"]: result for result in target_results}
    carrier = by_id.get("carrier")
    sidebands = [
        result
        for result in target_results
        if result["id"] != "carrier" and result["best_hit"] is not None
    ]
    carrier_strongest = (
        carrier is not None
        and carrier["best_hit"] is not None
        and bool(sidebands)
        and all(
            carrier["best_hit"]["snr"] > result["best_hit"]["snr"]
            for result in sidebands
        )
    )
    strongest_required = manifest.benchmark.carrier_must_be_strongest
    passed = required_targets_passed and (
        carrier_strongest or not strongest_required
    )
    return {
        "passed": passed,
        "required_targets_passed": required_targets_passed,
        "carrier_strongest": carrier_strongest,
        "carrier_strongest_required": strongest_required,
        "targets": target_results,
    }


def _package_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "unknown"


def _render_waterfall(
    data_path: Path, output_path: Path, manifest: DatasetManifest
) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        from matplotlib import pyplot as plt
        from matplotlib.ticker import FormatStrFormatter, MaxNLocator
        from blimpy import Waterfall
    except ImportError as exc:
        raise AnalysisError(
            "benchmark plotting dependencies are missing; run `uv sync`"
        ) from exc

    start = manifest.benchmark.plot_frequency_start_mhz
    stop = manifest.benchmark.plot_frequency_stop_mhz
    waterfall = Waterfall(str(data_path), f_start=start, f_stop=stop)
    waterfall.plot_waterfall(f_start=start, f_stop=stop, logged=True)
    figure = plt.gcf()
    axes = plt.gca()
    figure.set_size_inches(10, 6)
    axes.xaxis.set_major_locator(MaxNLocator(nbins=5))
    axes.xaxis.set_major_formatter(FormatStrFormatter("%.3f"))
    for target in manifest.benchmark.known_signal_targets:
        axes.axvline(
            target.frequency_mhz,
            color="white",
            linestyle="--",
            linewidth=0.7,
            alpha=0.55,
        )
    figure.suptitle("Voyager 1 known-signal benchmark")
    figure.savefig(
        output_path,
        dpi=150,
        bbox_inches="tight",
        metadata={"Software": "voyager-radio-benchmark 0.1.0"},
    )
    plt.close(figure)


def _run_turbo_seti(
    data_path: Path, work_dir: Path, manifest: DatasetManifest
) -> Path:
    try:
        from turbo_seti.find_doppler.find_doppler import FindDoppler
    except ImportError as exc:
        raise AnalysisError(
            "turboSETI is missing; run `uv sync` before the benchmark"
        ) from exc

    spec = manifest.benchmark
    finder = FindDoppler(
        datafile=str(data_path),
        max_drift=spec.max_drift_hz_per_s,
        min_drift=spec.min_drift_hz_per_s,
        snr=spec.snr_threshold,
        out_dir=str(work_dir),
    )
    finder.search()
    dat_files = sorted(work_dir.glob("*.dat"))
    if len(dat_files) != 1:
        raise AnalysisError(
            f"expected one turboSETI DAT output, found {len(dat_files)}"
        )
    return dat_files[0]


def run_benchmark(
    data_path: Path, output_dir: Path, manifest: DatasetManifest
) -> dict[str, Any]:
    """Verify, search, plot, and atomically publish deterministic artifacts."""

    data_path = Path(data_path)
    output_dir = Path(output_dir)
    dataset_sha256 = verify_file(data_path, manifest)
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix=".voyager-benchmark-", dir=output_dir) as raw:
        work_dir = Path(raw)
        plot_path = work_dir / "voyager_waterfall.png"
        _render_waterfall(data_path, plot_path, manifest)
        dat_path = _run_turbo_seti(data_path, work_dir, manifest)
        hits = parse_turbo_seti_dat(dat_path)
        recovery = evaluate_known_signal_recovery(manifest, hits)
        result: dict[str, Any] = {
            "schema_version": 1,
            "dataset": {
                "dataset_id": manifest.dataset_id,
                "filename": manifest.filename,
                "size_bytes": manifest.size_bytes,
                "sha256": dataset_sha256,
            },
            "parameters": {
                "searched_drift_range_hz_per_s": [
                    -manifest.benchmark.max_drift_hz_per_s,
                    manifest.benchmark.max_drift_hz_per_s,
                ],
                "turbo_seti_min_drift_magnitude_hz_per_s": manifest.benchmark.min_drift_hz_per_s,
                "turbo_seti_max_drift_magnitude_hz_per_s": manifest.benchmark.max_drift_hz_per_s,
                "snr_threshold": manifest.benchmark.snr_threshold,
            },
            "software": {
                "python": platform.python_version(),
                "blimpy": _package_version("blimpy"),
                "turbo_seti": _package_version("turbo-seti"),
            },
            "hit_count": len(hits),
            "hits": [asdict(hit) for hit in hits],
            "known_signal_recovery": recovery,
        }
        result_path = work_dir / "benchmark.json"
        result_path.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        published = {
            result_path: output_dir / "benchmark.json",
            plot_path: output_dir / "voyager_waterfall.png",
            dat_path: output_dir / "turbo_seti_hits.dat",
        }
        for source, destination in published.items():
            os.replace(source, destination)
    return result
