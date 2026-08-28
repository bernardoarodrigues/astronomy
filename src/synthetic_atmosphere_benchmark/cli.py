from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .analysis import run_preflight, write_artifacts
from .manifest import load_manifest
from .source import build_scaffold, scaffold_fingerprints, verify_sources


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="synthetic-atmosphere-benchmark",
        description="Run the non-promotional B3a synthetic atmospheric engineering preflight.",
    )
    parser.add_argument("--manifest", type=Path, help="optional manifest override for validation/testing")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("verify", "run"):
        command = subparsers.add_parser(name)
        command.add_argument(
            "--input-root",
            type=Path,
            default=Path("data/gj486/nirspec/extracted"),
            help="root containing the already-extracted pinned GJ486 v3 members",
        )
        if name == "run":
            command.add_argument(
                "--output-dir",
                type=Path,
                default=Path("artifacts/synthetic-atmosphere"),
            )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        if args.command == "verify":
            records = verify_sources(manifest, args.input_root)
            fingerprints = scaffold_fingerprints(build_scaffold(manifest, args.input_root))
            print(json.dumps({"fingerprints": fingerprints, "sources": records}, sort_keys=True))
            return 0
        result = run_preflight(manifest, args.input_root)
        artifacts = write_artifacts(args.output_dir, result)
        status = result["score"]["engineering_preflight_status"]
        print(
            json.dumps(
                {
                    "artifacts": artifacts,
                    "engineering_preflight_status": status,
                    "execution_status": result["execution_status"],
                    "real_data_readiness": result["real_data_readiness"],
                    "science_state": result["science_state"],
                },
                sort_keys=True,
            )
        )
        return 0 if status == "PASS" else 2
    except Exception as exc:
        parser.exit(1, f"synthetic-atmosphere-benchmark: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
