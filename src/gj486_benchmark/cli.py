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
from .manifest import GJ486Manifest, ManifestError, load_manifest


DEFAULT_DATA_ROOT = Path("data/gj486")
DEFAULT_OUTPUT_DIR = Path("artifacts/gj486")


def _archive_spec(manifest: GJ486Manifest, source: str):
    return manifest.archive if source == "nirspec" else manifest.external_constraint.archive


def _source_dir(root: Path, source: str) -> Path:
    return Path(root) / source


def _sources(value: str) -> tuple[str, ...]:
    return ("nirspec", "miri") if value == "all" else (value,)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gj486-benchmark",
        description="Run the ambiguity-preserving GJ 486 b NIRSpec benchmark and separate MIRI constraint.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="path to a semantically identical copy of the frozen canonical manifest",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    download = commands.add_parser("download", help="guard-download one or both frozen Zenodo archives")
    download.add_argument("--source", choices=("nirspec", "miri", "all"), default="all")
    download.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    download.add_argument("--max-bytes", type=int)

    extract = commands.add_parser("extract", help="safely extract only allowlisted members")
    extract.add_argument("--source", choices=("nirspec", "miri", "all"), default="all")
    extract.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    extract.add_argument("--archive", type=Path, help="single-source archive override")

    verify = commands.add_parser("verify", help="verify archives and extracted allowlisted members")
    verify.add_argument("--source", choices=("nirspec", "miri", "all"), default="all")
    verify.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    verify.add_argument("--archive", type=Path, help="single-source archive override")

    run = commands.add_parser("run", help="run the frozen NIRSpec and MIRI calculations")
    run.add_argument("--nirspec-extracted-dir", type=Path, default=DEFAULT_DATA_ROOT / "nirspec" / "extracted")
    run.add_argument("--miri-extracted-dir", type=Path, default=DEFAULT_DATA_ROOT / "miri" / "extracted")
    run.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        if args.command in {"extract", "verify"} and args.archive is not None and args.source == "all":
            raise ExtractionError("--archive requires --source nirspec or --source miri")
        if args.command == "download":
            paths = {}
            for source in _sources(args.source):
                paths[source] = str(
                    download_archive(
                        manifest,
                        _source_dir(args.data_root, source),
                        source=source,
                        max_bytes=args.max_bytes,
                    )
                )
            print(json.dumps(paths, sort_keys=True))
            return 0
        if args.command == "extract":
            paths = {}
            for source in _sources(args.source):
                source_dir = _source_dir(args.data_root, source)
                archive = args.archive or source_dir / _archive_spec(manifest, source).filename
                paths[source] = str(
                    safe_extract_archive(
                        archive,
                        source_dir / "extracted",
                        manifest,
                        source=source,
                    )
                )
            print(json.dumps(paths, sort_keys=True))
            return 0
        if args.command == "verify":
            results = {}
            for source in _sources(args.source):
                source_dir = _source_dir(args.data_root, source)
                archive = args.archive or source_dir / _archive_spec(manifest, source).filename
                results[source] = {
                    "archive": verify_archive(archive, _archive_spec(manifest, source)),
                    "members": verify_extracted(source_dir / "extracted", manifest, source=source),
                }
            print(json.dumps({"sources": results, "verified": True}, sort_keys=True))
            return 0
        result = run_benchmark(
            args.nirspec_extracted_dir,
            args.miri_extracted_dir,
            args.output_dir,
            manifest,
        )
        summary = {
            "feature_state": result["analysis"]["feature_state"],
            "miri_classification": result["analysis"]["miri_external_constraint"]["classification"],
            "passed": result["analysis"]["passed"],
            "pipeline_status": result["analysis"]["pipeline_status"],
            "science_state": result["analysis"]["science_state"],
        }
        print(json.dumps(summary, sort_keys=True))
        return 0 if summary["passed"] else 2
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
