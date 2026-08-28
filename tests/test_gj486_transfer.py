from __future__ import annotations

import hashlib
import io
import tempfile
import unittest
import zipfile
from dataclasses import replace
from pathlib import Path

from gj486_benchmark.downloader import DownloadError, download_archive
from gj486_benchmark.extraction import ExtractionError, safe_extract_archive, verify_extracted
from gj486_benchmark.integrity import IntegrityError
from gj486_benchmark.manifest import ArchiveSpec, ExternalConstraintSpec, MemberSpec, load_manifest


class Response(io.BytesIO):
    def __init__(self, payload: bytes, length: int | None):
        super().__init__(payload)
        self.headers = {} if length is None else {"Content-Length": str(length)}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class Opener:
    def __init__(self, payload: bytes, *, advertised: int | None = None):
        self.payload = payload
        self.advertised = len(payload) if advertised is None else advertised

    def __call__(self, request, timeout):
        if request.get_method() == "HEAD":
            return Response(b"", self.advertised)
        return Response(self.payload, self.advertised)


def archive_spec(payload: bytes, filename: str = "fixture.zip") -> ArchiveSpec:
    return ArchiveSpec(
        record_version="test",
        doi="test",
        url="https://example.test/fixture.zip",
        filename=filename,
        size_bytes=len(payload),
        publisher_md5=hashlib.md5(payload, usedforsecurity=False).hexdigest(),
        sha256=hashlib.sha256(payload).hexdigest(),
        license_spdx="CC-BY-4.0",
        default_max_download_bytes=max(1, len(payload)),
        hard_max_download_bytes=20_000_000_000,
        max_archive_members=20,
        max_total_uncompressed_bytes=10_000,
    )


class GJ486TransferTests(unittest.TestCase):
    def test_network_free_download_and_cache(self) -> None:
        payload = b"frozen"
        manifest = replace(load_manifest(), archive=archive_spec(payload))
        with tempfile.TemporaryDirectory() as raw:
            destination = Path(raw)
            path = download_archive(manifest, destination, opener=Opener(payload))
            self.assertEqual(path.read_bytes(), payload)
            self.assertEqual(download_archive(manifest, destination, opener=lambda *_a, **_k: self.fail()), path)

    def test_download_guards_advertised_and_streamed_sizes(self) -> None:
        payload = b"abc"
        manifest = replace(load_manifest(), archive=archive_spec(payload))
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(DownloadError, "remote object"):
                download_archive(manifest, Path(raw), opener=Opener(payload, advertised=4))
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(DownloadError, "manifest size"):
                download_archive(manifest, Path(raw), max_bytes=2, opener=Opener(payload))

    def fixture_manifest(self, *, traversal: bool = False):
        base = load_manifest()
        payloads = {"a.txt": b"a", "b.txt": b"bb", "c.txt": b"ccc"}
        members = tuple(
            MemberSpec(role=f"role_{index}", path=name, size_bytes=len(value), sha256=hashlib.sha256(value).hexdigest())
            for index, (name, value) in enumerate(payloads.items())
        )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for name, value in payloads.items():
                archive.writestr(name, value)
            if traversal:
                archive.writestr("../escape.txt", b"bad")
        archive_bytes = buffer.getvalue()
        return replace(base, archive=archive_spec(archive_bytes), members=members), archive_bytes

    def test_safe_extraction_allowlists_only_required_members(self) -> None:
        manifest, archive_bytes = self.fixture_manifest()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            archive = root / "fixture.zip"
            archive.write_bytes(archive_bytes)
            destination = safe_extract_archive(archive, root / "out", manifest)
            self.assertEqual(sorted(path.name for path in destination.iterdir()), ["a.txt", "b.txt", "c.txt"])

    def test_existing_extraction_rejects_unexpected_files(self) -> None:
        manifest, archive_bytes = self.fixture_manifest()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            archive = root / "fixture.zip"
            archive.write_bytes(archive_bytes)
            destination = safe_extract_archive(archive, root / "out", manifest)
            (destination / "unexpected.txt").write_text("not allowlisted", encoding="utf-8")
            with self.assertRaisesRegex(IntegrityError, "differs from allowlist"):
                verify_extracted(destination, manifest)
            with self.assertRaisesRegex(ExtractionError, "refusing to overwrite"):
                safe_extract_archive(archive, destination, manifest)

    def test_safe_extraction_rejects_traversal_and_checksum_failure(self) -> None:
        manifest, archive_bytes = self.fixture_manifest(traversal=True)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            archive = root / "fixture.zip"
            archive.write_bytes(archive_bytes)
            with self.assertRaisesRegex(ExtractionError, "unsafe ZIP member path"):
                safe_extract_archive(archive, root / "out", manifest)

        manifest, archive_bytes = self.fixture_manifest()
        bad = replace(manifest.members[0], sha256="0" * 64)
        manifest = replace(manifest, members=(bad, *manifest.members[1:]))
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            archive = root / "fixture.zip"
            archive.write_bytes(archive_bytes)
            with self.assertRaisesRegex(ExtractionError, "failed its extracted size or SHA-256"):
                safe_extract_archive(archive, root / "out", manifest)

    def test_miri_source_uses_its_own_guard(self) -> None:
        payload = b"miri"
        base = load_manifest()
        external = replace(base.external_constraint, archive=archive_spec(payload, "miri.zip"))
        manifest = replace(base, external_constraint=external)
        with tempfile.TemporaryDirectory() as raw:
            path = download_archive(manifest, Path(raw), source="miri", opener=Opener(payload))
            self.assertEqual(path.name, "miri.zip")


if __name__ == "__main__":
    unittest.main()
