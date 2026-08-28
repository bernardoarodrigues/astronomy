from __future__ import annotations

import hashlib
import io
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from k218_repeatability.downloader import DownloadError, download_archive
from k218_repeatability.manifest import load_manifest


class FakeResponse:
    def __init__(self, payload: bytes, length: int | None = None):
        self._stream = io.BytesIO(payload)
        self.headers = {} if length is None else {"Content-Length": str(length)}

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


_DEFAULT_LENGTH = object()


class FakeOpener:
    def __init__(self, head_length: int | None, payload: bytes, get_length=_DEFAULT_LENGTH):
        self.head_length = head_length
        self.payload = payload
        self.get_length = len(payload) if get_length is _DEFAULT_LENGTH else get_length
        self.methods: list[str] = []

    def __call__(self, request, timeout=0):
        del timeout
        self.methods.append(request.get_method())
        if request.get_method() == "HEAD":
            return FakeResponse(b"", self.head_length)
        return FakeResponse(self.payload, self.get_length)


def synthetic_manifest(payload: bytes, *, sha256: str | None = None, size: int | None = None):
    manifest = load_manifest()
    archive = replace(
        manifest.archive,
        filename="tiny.zip",
        size_bytes=len(payload) if size is None else size,
        sha256=sha256 or hashlib.sha256(payload).hexdigest(),
        default_max_download_bytes=1024,
    )
    return replace(manifest, archive=archive)


class K218DownloaderTests(unittest.TestCase):
    def test_guarded_atomic_success_and_verified_cache(self) -> None:
        payload = b"frozen-archive"
        manifest = synthetic_manifest(payload)
        opener = FakeOpener(len(payload), payload)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = download_archive(manifest, root, opener=opener)
            self.assertEqual(result.read_bytes(), payload)
            self.assertEqual(opener.methods, ["HEAD", "GET"])
            cached = download_archive(manifest, root, opener=lambda *_a, **_k: self.fail("network used"))
            self.assertEqual(cached, result)
            self.assertFalse(list(root.glob("*.part")))

    def test_header_guard_prevents_get(self) -> None:
        payload = b"small"
        manifest = synthetic_manifest(payload)
        opener = FakeOpener(2000, payload)
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(DownloadError, "above the .* guard"):
                download_archive(manifest, Path(temporary), max_bytes=1000, opener=opener)
        self.assertEqual(opener.methods, ["HEAD"])

    def test_stream_overflow_and_checksum_failure_are_atomic(self) -> None:
        payload = b"expected"
        overflow_manifest = synthetic_manifest(payload, size=len(payload) - 1)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            opener = FakeOpener(None, payload, get_length=None)
            with self.assertRaisesRegex(DownloadError, "manifested archive size"):
                download_archive(overflow_manifest, root, opener=opener)
            self.assertFalse((root / "tiny.zip").exists())
            self.assertFalse(list(root.glob("*.part")))
        bad_digest = synthetic_manifest(payload, sha256="0" * 64)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(DownloadError, "SHA-256 mismatch"):
                download_archive(bad_digest, root, opener=FakeOpener(len(payload), payload))
            self.assertFalse((root / "tiny.zip").exists())

    def test_global_hard_limit_cannot_be_overridden(self) -> None:
        manifest = load_manifest()
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(DownloadError, "must be between"):
                download_archive(
                    manifest,
                    Path(temporary),
                    max_bytes=manifest.archive.hard_max_download_bytes + 1,
                    opener=lambda *_a, **_k: self.fail("network used"),
                )


if __name__ == "__main__":
    unittest.main()
