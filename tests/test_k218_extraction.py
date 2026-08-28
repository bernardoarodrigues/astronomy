from __future__ import annotations

import hashlib
import tempfile
import unittest
import zipfile
from dataclasses import replace
from pathlib import Path

from k218_repeatability.extraction import ExtractionError, safe_extract_archive, verify_extracted
from k218_repeatability.integrity import IntegrityError
from k218_repeatability.manifest import MemberSpec, load_manifest


def member(role: str, path: str, payload: bytes) -> MemberSpec:
    return MemberSpec(
        role=role,
        reduction="Eureka",
        visit="visit_2",
        detector="NRS2",
        path=path,
        size_bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        rows=1,
        wavelength_min_micrometres=1.0,
        wavelength_max_micrometres=1.0,
    )


def write_zip(path: Path, entries: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)


def manifest_for(path: Path, members: tuple[MemberSpec, ...]):
    payload = path.read_bytes()
    base = load_manifest()
    archive = replace(
        base.archive,
        filename=path.name,
        size_bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        default_max_download_bytes=max(1024, len(payload)),
        max_total_uncompressed_bytes=4096,
    )
    return replace(base, archive=archive, members=members)


class K218ExtractionTests(unittest.TestCase):
    def test_extracts_only_exact_allowlist(self) -> None:
        payloads = [b"one", b"two", b"three", b"four"]
        specs = tuple(member(f"role_{i}", f"safe/{i}.txt", payload) for i, payload in enumerate(payloads))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "source.zip"
            entries = {spec.path: payload for spec, payload in zip(specs, payloads)}
            entries["safe/not-allowlisted.txt"] = b"ignored"
            write_zip(archive, entries)
            destination = root / "extracted"
            safe_extract_archive(archive, destination, manifest_for(archive, specs))
            self.assertEqual({path.name for path in destination.rglob("*.txt")}, {"0.txt", "1.txt", "2.txt", "3.txt"})
            self.assertEqual(len(verify_extracted(destination, manifest_for(archive, specs))), 4)

    def test_path_traversal_rejects_entire_archive(self) -> None:
        payloads = [b"one", b"two", b"three", b"four"]
        specs = tuple(member(f"role_{i}", f"safe/{i}.txt", payload) for i, payload in enumerate(payloads))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "source.zip"
            entries = {spec.path: payload for spec, payload in zip(specs, payloads)}
            entries["../escape.txt"] = b"escape"
            write_zip(archive, entries)
            with self.assertRaisesRegex(ExtractionError, "unsafe ZIP member path"):
                safe_extract_archive(archive, root / "extracted", manifest_for(archive, specs))
            self.assertFalse((root / "escape.txt").exists())
            self.assertFalse((root / "extracted").exists())

    def test_member_checksum_failure_is_atomic(self) -> None:
        payloads = [b"one", b"two", b"three", b"four"]
        specs = list(member(f"role_{i}", f"safe/{i}.txt", payload) for i, payload in enumerate(payloads))
        specs[2] = replace(specs[2], sha256="0" * 64)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "source.zip"
            write_zip(archive, {spec.path: payload for spec, payload in zip(specs, payloads)})
            with self.assertRaisesRegex(ExtractionError, "SHA-256 mismatch"):
                safe_extract_archive(archive, root / "extracted", manifest_for(archive, tuple(specs)))
            self.assertFalse((root / "extracted").exists())

    def test_verifier_rejects_extra_extracted_file(self) -> None:
        payloads = [b"one", b"two", b"three", b"four"]
        specs = tuple(member(f"role_{i}", f"safe/{i}.txt", payload) for i, payload in enumerate(payloads))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "source.zip"
            write_zip(archive, {spec.path: payload for spec, payload in zip(specs, payloads)})
            manifest = manifest_for(archive, specs)
            destination = safe_extract_archive(archive, root / "extracted", manifest)
            (destination / "extra.txt").write_text("extra", encoding="utf-8")
            with self.assertRaisesRegex(IntegrityError, "differs from allowlist"):
                verify_extracted(destination, manifest)


if __name__ == "__main__":
    unittest.main()
