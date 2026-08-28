from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from k218_repeatability.analysis import AnalysisError
from k218_repeatability.data import DataError
from k218_repeatability.downloader import DownloadError, download_archive
from k218_repeatability.extraction import ExtractionError, safe_extract_archive, verify_extracted
from k218_repeatability.integrity import IntegrityError, verify_archive

from .analysis import run_diagnostic
from .manifest import ManifestError, load_manifest


DEFAULT_ARCHIVE_DIR = Path("data/k218_repeatability")
DEFAULT_EXTRACTED_DIR = Path("data/k218_c1_context/extracted")
DEFAULT_OUTPUT_DIR = Path("artifacts/k218_c1_context")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="k218-c1-context",
        description="Run the isolated retrospective GO-2722 C1 historical-context diagnostic.",
    )
    parser.add_argument("--manifest", type=Path, help="alternate file matching the frozen contract")
    commands = parser.add_subparsers(dest="command", required=True)
    download = commands.add_parser("download", help="guard-download or reuse the pinned OSF ZIP")
    download.add_argument("--data-dir", type=Path, default=DEFAULT_ARCHIVE_DIR)
    download.add_argument("--max-bytes", type=int)
    extract = commands.add_parser("extract", help="safely extract exactly two C1 NRS2 views")
    extract.add_argument("--archive", type=Path)
    extract.add_argument("--extracted-dir", type=Path, default=DEFAULT_EXTRACTED_DIR)
    verify = commands.add_parser("verify", help="verify archive and isolated C1 extraction")
    verify.add_argument("--archive", type=Path)
    verify.add_argument("--extracted-dir", type=Path, default=DEFAULT_EXTRACTED_DIR)
    run = commands.add_parser("run", help="run the unchanged local-contrast method on C1")
    run.add_argument("--extracted-dir", type=Path, default=DEFAULT_EXTRACTED_DIR)
    run.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        default_archive = DEFAULT_ARCHIVE_DIR / manifest.archive.filename
        if args.command == "download":
            print(download_archive(manifest, args.data_dir, max_bytes=args.max_bytes))
            return 0
        if args.command == "extract":
            print(safe_extract_archive(args.archive or default_archive, args.extracted_dir, manifest))
            return 0
        if args.command == "verify":
            print(
                json.dumps(
                    {
                        "archive": verify_archive(args.archive or default_archive, manifest.archive),
                        "members": verify_extracted(args.extracted_dir, manifest),
                        "verified": True,
                    },
                    sort_keys=True,
                )
            )
            return 0
        result = run_diagnostic(args.extracted_dir, args.output_dir, manifest)
        print(
            json.dumps(
                {
                    "execution_status": result["execution_status"],
                    "science_state": result["science_state"],
                    "context_descriptor": result["context_descriptor"],
                    "independent_reduction_evidence": result["independent_reduction_evidence"],
                    "comparison_to_go2372": result["comparison_to_go2372"],
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
