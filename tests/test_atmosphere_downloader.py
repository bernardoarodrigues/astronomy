from __future__ import annotations

import hashlib
import io
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from atmosphere_benchmark.downloader import DownloadError, download_archive
from atmosphere_benchmark.manifest import load_manifest


class FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, content_length: int | None) -> None:
        super().__init__(body)
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def opener_for(payload: bytes, content_length: int | None = None):
    advertised = len(payload) if content_length is None else content_length

    def opener(request, timeout):
        del timeout
        if request.get_method() == "HEAD":
            return FakeResponse(b"", advertised)
        return FakeResponse(payload, advertised)

    return opener


def manifest_for(payload: bytes):
    manifest = load_manifest()
    archive = replace(
        manifest.archive,
        url="https://example.test/archive.zip",
        filename="test.zip",
        size_bytes=len(payload),
        publisher_md5=hashlib.md5(payload, usedforsecurity=False).hexdigest(),
        sha256=hashlib.sha256(payload).hexdigest(),
        default_max_download_bytes=1024,
    )
    return replace(manifest, archive=archive)


class AtmosphereDownloaderTests(unittest.TestCase):
    def test_guarded_download_and_verified_cache(self) -> None:
        payload = b"deterministic tiny archive"
        manifest = manifest_for(payload)
        with tempfile.TemporaryDirectory() as raw:
            result = download_archive(
                manifest,
                Path(raw),
                opener=opener_for(payload),
            )
            self.assertEqual(result.read_bytes(), payload)

            def fail_if_called(*args, **kwargs):
                raise AssertionError("verified cache must not access the network")

            cached = download_archive(manifest, Path(raw), opener=fail_if_called)
            self.assertEqual(cached, result)

    def test_checksum_failure_is_not_published(self) -> None:
        payload = b"deterministic tiny archive"
        changed = payload[:-1] + b"!"
        manifest = manifest_for(payload)
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(DownloadError, "MD5 mismatch"):
                download_archive(
                    manifest,
                    Path(raw),
                    opener=opener_for(changed),
                )
            self.assertEqual(list(Path(raw).iterdir()), [])

    def test_manifest_over_requested_guard_fails_before_network(self) -> None:
        payload = b"deterministic tiny archive"
        manifest = manifest_for(payload)
        calls = 0

        def counting_opener(*args, **kwargs):
            nonlocal calls
            calls += 1
            return FakeResponse(b"", 0)

        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(DownloadError, "manifest size"):
                download_archive(
                    manifest,
                    Path(raw),
                    max_bytes=len(payload) - 1,
                    opener=counting_opener,
                )
        self.assertEqual(calls, 0)


if __name__ == "__main__":
    unittest.main()
