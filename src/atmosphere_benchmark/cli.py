from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .analysis import AnalysisError, run_benchmark
from .downloader import DownloadError, download_archive
from .extraction import ExtractionError, safe_extract_archive, verify_extracted
from .integrity import IntegrityError, verify_archive
from .manifest import ManifestError, load_manifest
from .spectrum import SpectrumError


DEFAULT_DATA_DIR = Path("data/atmosphere")
DEFAULT_EXTRACTED_DIR = DEFAULT_DATA_DIR / "extracted"
DEFAULT_OUTPUT_DIR = Path("artifacts/atmosphere")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atmosphere-benchmark",
        description="Reproduce the pinned WASP-39 b 4.3-micrometre positive control.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="alternate manifest JSON (default: bundled Milestone B1 manifest)",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    download = commands.add_parser("download", help="guard-download the Zenodo ZIP")
    download.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    download.add_argument("--max-bytes", type=int)

    extract = commands.add_parser("extract", help="safely extract allowlisted members")
    extract.add_argument("--archive", type=Path)
    extract.add_argument("--extracted-dir", type=Path, default=DEFAULT_EXTRACTED_DIR)

    verify = commands.add_parser("verify", help="verify ZIP and extracted members")
    verify.add_argument("--archive", type=Path)
    verify.add_argument("--extracted-dir", type=Path, default=DEFAULT_EXTRACTED_DIR)

    run = commands.add_parser("run", help="run the frozen regression and diagnostics")
    run.add_argument("--extracted-dir", type=Path, default=DEFAULT_EXTRACTED_DIR)
    run.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        default_archive = DEFAULT_DATA_DIR / manifest.archive.filename
        if args.command == "download":
            path = download_archive(
                manifest,
                args.data_dir,
                max_bytes=args.max_bytes,
            )
            print(path)
            return 0
        if args.command == "extract":
            archive = args.archive or default_archive
            path = safe_extract_archive(archive, args.extracted_dir, manifest)
            print(path)
            return 0
        if args.command == "verify":
            archive = args.archive or default_archive
            archive_result = verify_archive(archive, manifest.archive)
            members = verify_extracted(args.extracted_dir, manifest)
            print(
                json.dumps(
                    {
                        "archive": archive_result,
                        "members": members,
                        "verified": True,
                    },
                    sort_keys=True,
                )
            )
            return 0
        result = run_benchmark(args.extracted_dir, args.output_dir, manifest)
        summary = {
            "passed": result["analysis"]["passed"],
            "amplitude": result["analysis"]["primary"]["amplitude"],
            "z": result["analysis"]["primary"]["z"],
            "delta_chi2": result["analysis"]["primary"]["delta_chi2"],
        }
        print(json.dumps(summary, sort_keys=True))
        return 0 if summary["passed"] else 2
    except (
        AnalysisError,
        DownloadError,
        ExtractionError,
        IntegrityError,
        ManifestError,
        SpectrumError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
