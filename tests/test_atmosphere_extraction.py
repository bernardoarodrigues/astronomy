from __future__ import annotations

import hashlib
import tempfile
import unittest
import zipfile
from dataclasses import replace
from pathlib import Path

from atmosphere_benchmark.extraction import ExtractionError, safe_extract_archive
from atmosphere_benchmark.manifest import MemberSpec, load_manifest


def member(path: str, role: str, payload: bytes) -> MemberSpec:
    return MemberSpec(
        role=role,
        path=path,
        size_bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def write_zip(path: Path, entries: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)


def manifest_for_archive(path: Path, members: tuple[MemberSpec, ...]):
    payload = path.read_bytes()
    base = load_manifest()
    archive = replace(
        base.archive,
        filename=path.name,
        size_bytes=len(payload),
        publisher_md5=hashlib.md5(payload, usedforsecurity=False).hexdigest(),
        sha256=hashlib.sha256(payload).hexdigest(),
        default_max_download_bytes=max(1024, len(payload)),
        max_total_uncompressed_bytes=1024,
    )
    return replace(base, archive=archive, members=members)


class AtmosphereExtractionTests(unittest.TestCase):
    def test_extracts_only_verified_allowlist(self) -> None:
        primary = b"primary"
        model = b"model"
        no_co2 = b"no co2"
        specs = (
            member("safe/primary.txt", "primary_spectrum", primary),
            member("safe/model.txt", "attribution_full_model", model),
            member("safe/no_co2.txt", "attribution_no_co2_model", no_co2),
        )
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            archive_path = root / "archive.zip"
            write_zip(
                archive_path,
                {
                    specs[0].path: primary,
                    specs[1].path: model,
                    specs[2].path: no_co2,
                    "safe/not-allowlisted.txt": b"ignored",
                },
            )
            destination = root / "extracted"
            safe_extract_archive(
                archive_path,
                destination,
                manifest_for_archive(archive_path, specs),
            )
            self.assertEqual((destination / specs[0].path).read_bytes(), primary)
            self.assertFalse((destination / "safe/not-allowlisted.txt").exists())

    def test_path_traversal_rejects_entire_archive(self) -> None:
        payloads = (b"primary", b"model", b"no co2")
        specs = (
            member("safe/primary.txt", "primary_spectrum", payloads[0]),
            member("safe/model.txt", "attribution_full_model", payloads[1]),
            member("safe/no_co2.txt", "attribution_no_co2_model", payloads[2]),
        )
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            archive_path = root / "archive.zip"
            entries = {spec.path: value for spec, value in zip(specs, payloads)}
            entries["../escape.txt"] = b"escape"
            write_zip(archive_path, entries)
            with self.assertRaisesRegex(ExtractionError, "unsafe ZIP member path"):
                safe_extract_archive(
                    archive_path,
                    root / "extracted",
                    manifest_for_archive(archive_path, specs),
                )
            self.assertFalse((root / "escape.txt").exists())
            self.assertFalse((root / "extracted").exists())

    def test_member_checksum_failure_is_atomic(self) -> None:
        payloads = (b"primary", b"model", b"no co2")
        specs = (
            replace(
                member("safe/primary.txt", "primary_spectrum", payloads[0]),
                sha256="0" * 64,
            ),
            member("safe/model.txt", "attribution_full_model", payloads[1]),
            member("safe/no_co2.txt", "attribution_no_co2_model", payloads[2]),
        )
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            archive_path = root / "archive.zip"
            write_zip(
                archive_path,
                {spec.path: value for spec, value in zip(specs, payloads)},
            )
            with self.assertRaisesRegex(ExtractionError, "SHA-256 mismatch"):
                safe_extract_archive(
                    archive_path,
                    root / "extracted",
                    manifest_for_archive(archive_path, specs),
                )
            self.assertFalse((root / "extracted").exists())


if __name__ == "__main__":
    unittest.main()
