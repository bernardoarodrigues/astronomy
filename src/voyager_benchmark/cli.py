from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .analysis import AnalysisError, run_benchmark
from .downloader import DownloadError, download_dataset
from .integrity import IntegrityError, verify_file
from .manifest import (
    DEFAULT_MAX_DOWNLOAD_BYTES,
    HARD_MAX_DOWNLOAD_BYTES,
    ManifestError,
    load_manifest,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="voyager-benchmark",
        description="Reproduce a Voyager 1 known-signal recovery benchmark.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="alternate manifest JSON (default: bundled Phase 1 manifest)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    download = subparsers.add_parser("download", help="download and verify sample data")
    download.add_argument("--data-dir", type=Path, default=Path("data"))
    download.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_DOWNLOAD_BYTES,
        help=(
            f"transfer ceiling (default: {DEFAULT_MAX_DOWNLOAD_BYTES}; "
            f"hard maximum: {HARD_MAX_DOWNLOAD_BYTES})"
        ),
    )

    verify = subparsers.add_parser("verify", help="verify an existing sample")
    verify.add_argument("--input", type=Path)

    run = subparsers.add_parser("run", help="run search, recovery check, and plot")
    run.add_argument("--input", type=Path)
    run.add_argument("--output-dir", type=Path, default=Path("artifacts"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        if args.command == "download":
            path = download_dataset(
                manifest, args.data_dir, max_bytes=args.max_bytes
            )
            print(path)
            return 0

        data_path = args.input or Path("data") / manifest.filename
        if args.command == "verify":
            digest = verify_file(data_path, manifest)
            print(
                json.dumps(
                    {
                        "path": str(data_path),
                        "size_bytes": manifest.size_bytes,
                        "sha256": digest,
                        "verified": True,
                    },
                    sort_keys=True,
                )
            )
            return 0

        result = run_benchmark(data_path, args.output_dir, manifest)
        print(json.dumps(result["known_signal_recovery"], sort_keys=True))
        return 0 if result["known_signal_recovery"]["passed"] else 2
    except (AnalysisError, DownloadError, IntegrityError, ManifestError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

