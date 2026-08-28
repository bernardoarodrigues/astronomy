from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .analysis import AnalysisError, run_benchmark
from .data import DataError
from .downloader import DownloadError, download_archive
from .extraction import ExtractionError, safe_extract_archive, verify_extracted
from .integrity import IntegrityError, verify_archive
from .manifest import ManifestError, load_manifest


DEFAULT_DATA_DIR = Path("data/k218_repeatability")
DEFAULT_EXTRACTED_DIR = DEFAULT_DATA_DIR / "extracted"
DEFAULT_OUTPUT_DIR = Path("artifacts/k218_repeatability")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="k218-repeatability",
        description=(
            "Run the retrospective GO-2372 published-spectrum 4.3-micrometre "
            "morphology repeatability analysis; no molecule attribution."
        ),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="alternate manifest JSON (must match the frozen canonical contract)",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    download = commands.add_parser("download", help="guard-download the pinned OSF ZIP")
    download.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    download.add_argument("--max-bytes", type=int)

    extract = commands.add_parser("extract", help="safely extract four allowlisted NRS2 views")
    extract.add_argument("--archive", type=Path)
    extract.add_argument("--extracted-dir", type=Path, default=DEFAULT_EXTRACTED_DIR)

    verify = commands.add_parser("verify", help="verify the ZIP and exact extracted allowlist")
    verify.add_argument("--archive", type=Path)
    verify.add_argument("--extracted-dir", type=Path, default=DEFAULT_EXTRACTED_DIR)

    run = commands.add_parser("run", help="run the frozen retrospective morphology analysis")
    run.add_argument("--extracted-dir", type=Path, default=DEFAULT_EXTRACTED_DIR)
    run.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        default_archive = DEFAULT_DATA_DIR / manifest.archive.filename
        if args.command == "download":
            print(download_archive(manifest, args.data_dir, max_bytes=args.max_bytes))
            return 0
        if args.command == "extract":
            archive = args.archive or default_archive
            print(safe_extract_archive(archive, args.extracted_dir, manifest))
            return 0
        if args.command == "verify":
            archive = args.archive or default_archive
            print(
                json.dumps(
                    {
                        "archive": verify_archive(archive, manifest.archive),
                        "members": verify_extracted(args.extracted_dir, manifest),
                        "verified": True,
                    },
                    sort_keys=True,
                )
            )
            return 0
        result = run_benchmark(args.extracted_dir, args.output_dir, manifest)
        print(
            json.dumps(
                {
                    "execution_status": result["execution_status"],
                    "science_state": result["analysis"]["outcome"]["state"],
                    "reason": result["analysis"]["outcome"]["reason"],
                    "retrospective": result["retrospective"],
                    "molecule_attribution": result["molecule_attribution"],
                    "evidence_of_life": result["evidence_of_life"],
                },
                sort_keys=True,
            )
        )
        return 0
    except (
        AnalysisError,
        DataError,
        DownloadError,
        ExtractionError,
        IntegrityError,
        ManifestError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
