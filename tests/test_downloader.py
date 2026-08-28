from __future__ import annotations

import hashlib
import io
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from voyager_benchmark.downloader import DownloadError, download_dataset
from voyager_benchmark.manifest import HARD_MAX_DOWNLOAD_BYTES, load_manifest


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


def fake_opener(body: bytes, *, advertised_length: int | None = None):
    length = len(body) if advertised_length is None else advertised_length

    def open_request(request, timeout):
        del timeout
        if request.get_method() == "HEAD":
            return FakeResponse(b"", length)
        return FakeResponse(body, length)

    return open_request


class DownloaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = b"small deterministic observation"
        self.manifest = replace(
            load_manifest(),
            filename="sample.h5",
            url="https://example.test/sample.h5",
            size_bytes=len(self.payload),
            sha256=hashlib.sha256(self.payload).hexdigest(),
        )

    def test_downloads_verifies_and_reuses_cached_file(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            destination = download_dataset(
                self.manifest,
                Path(raw_dir),
                max_bytes=100,
                opener=fake_opener(self.payload),
            )
            self.assertEqual(destination.read_bytes(), self.payload)

            def unexpected_opener(*args, **kwargs):
                raise AssertionError("valid cached data should not touch the network")

            cached = download_dataset(
                self.manifest,
                Path(raw_dir),
                max_bytes=100,
                opener=unexpected_opener,
            )
            self.assertEqual(cached, destination)

    def test_rejects_user_limit_above_hard_cap(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            with self.assertRaisesRegex(DownloadError, "max_bytes"):
                download_dataset(
                    self.manifest,
                    Path(raw_dir),
                    max_bytes=HARD_MAX_DOWNLOAD_BYTES + 1,
                    opener=fake_opener(self.payload),
                )

    def test_rejects_manifest_before_network_when_over_limit(self) -> None:
        calls = 0

        def counting_opener(*args, **kwargs):
            nonlocal calls
            calls += 1
            return FakeResponse(b"", 0)

        with tempfile.TemporaryDirectory() as raw_dir:
            with self.assertRaisesRegex(DownloadError, "manifest size"):
                download_dataset(
                    self.manifest,
                    Path(raw_dir),
                    max_bytes=len(self.payload) - 1,
                    opener=counting_opener,
                )
        self.assertEqual(calls, 0)

    def test_rejects_advertised_remote_size_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            with self.assertRaisesRegex(DownloadError, "remote size"):
                download_dataset(
                    self.manifest,
                    Path(raw_dir),
                    max_bytes=100,
                    opener=fake_opener(
                        self.payload, advertised_length=len(self.payload) + 1
                    ),
                )
            self.assertFalse((Path(raw_dir) / self.manifest.filename).exists())

    def test_streaming_guard_catches_unadvertised_overflow(self) -> None:
        overflow = self.payload + b"!"

        def opener(request, timeout):
            del timeout
            if request.get_method() == "HEAD":
                return FakeResponse(b"", self.manifest.size_bytes)
            return FakeResponse(overflow, None)

        with tempfile.TemporaryDirectory() as raw_dir:
            with self.assertRaisesRegex(DownloadError, "manifested size"):
                download_dataset(
                    self.manifest,
                    Path(raw_dir),
                    max_bytes=100,
                    opener=opener,
                )
            self.assertEqual(list(Path(raw_dir).iterdir()), [])

    def test_checksum_mismatch_never_publishes_destination(self) -> None:
        changed = self.payload[:-1] + b"!"
        with tempfile.TemporaryDirectory() as raw_dir:
            with self.assertRaisesRegex(DownloadError, "SHA-256 mismatch"):
                download_dataset(
                    self.manifest,
                    Path(raw_dir),
                    max_bytes=100,
                    opener=fake_opener(changed),
                )
            self.assertEqual(list(Path(raw_dir).iterdir()), [])


if __name__ == "__main__":
    unittest.main()

