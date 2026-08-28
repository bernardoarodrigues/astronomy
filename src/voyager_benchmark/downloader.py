from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen

from .integrity import IntegrityError, verify_file
from .manifest import HARD_MAX_DOWNLOAD_BYTES, DatasetManifest


class DownloadError(RuntimeError):
    """Raised when a download cannot meet the manifest's safety contract."""


Opener = Callable[..., Any]


def _parse_content_length(response: Any) -> int | None:
    value = response.headers.get("Content-Length")
    if value is None:
        return None
    try:
        length = int(value)
    except (TypeError, ValueError) as exc:
        raise DownloadError(f"invalid HTTP Content-Length: {value!r}") from exc
    if length < 0:
        raise DownloadError(f"invalid negative HTTP Content-Length: {length}")
    return length


def _guard_length(length: int | None, manifest: DatasetManifest, max_bytes: int) -> None:
    if length is None:
        return
    if length > max_bytes or length > HARD_MAX_DOWNLOAD_BYTES:
        raise DownloadError(
            f"remote object is {length} bytes, above the {max_bytes}-byte guard"
        )
    if length != manifest.size_bytes:
        raise DownloadError(
            f"remote size {length} does not match manifest size {manifest.size_bytes}"
        )


def download_dataset(
    manifest: DatasetManifest,
    destination_dir: Path,
    *,
    max_bytes: int,
    timeout_seconds: float = 30.0,
    opener: Opener = urlopen,
) -> Path:
    """Download one manifest object through size, hash, and atomic-file guards."""

    if not 0 < max_bytes <= HARD_MAX_DOWNLOAD_BYTES:
        raise DownloadError(
            f"max_bytes must be between 1 and {HARD_MAX_DOWNLOAD_BYTES}"
        )
    if manifest.size_bytes > max_bytes:
        raise DownloadError(
            f"manifest size {manifest.size_bytes} exceeds {max_bytes}-byte guard"
        )

    destination_dir = Path(destination_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / manifest.filename
    if destination.exists():
        try:
            verify_file(destination, manifest)
        except IntegrityError as exc:
            raise DownloadError(
                f"existing destination is not the manifested dataset; refusing to "
                f"overwrite it: {exc}"
            ) from exc
        return destination

    head_request = Request(manifest.url, method="HEAD")
    try:
        with opener(head_request, timeout=timeout_seconds) as response:
            _guard_length(_parse_content_length(response), manifest, max_bytes)
    except DownloadError:
        raise
    except Exception as exc:
        raise DownloadError(f"HEAD request failed for {manifest.url}: {exc}") from exc

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{manifest.filename}.",
            suffix=".part",
            dir=destination_dir,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            digest = hashlib.sha256()
            total = 0
            get_request = Request(manifest.url, method="GET")
            with opener(get_request, timeout=timeout_seconds) as response:
                _guard_length(_parse_content_length(response), manifest, max_bytes)
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes or total > HARD_MAX_DOWNLOAD_BYTES:
                        raise DownloadError(
                            f"stream exceeded the {max_bytes}-byte guard"
                        )
                    if total > manifest.size_bytes:
                        raise DownloadError("stream exceeded the manifested size")
                    temporary.write(chunk)
                    digest.update(chunk)
            temporary.flush()
            os.fsync(temporary.fileno())

        if total != manifest.size_bytes:
            raise DownloadError(
                f"downloaded {total} bytes, expected {manifest.size_bytes}"
            )
        actual_sha256 = digest.hexdigest()
        if actual_sha256 != manifest.sha256:
            raise DownloadError(
                f"SHA-256 mismatch: expected {manifest.sha256}, got {actual_sha256}"
            )
        os.replace(temporary_path, destination)
        temporary_path = None
        return destination
    except DownloadError:
        raise
    except Exception as exc:
        raise DownloadError(f"download failed for {manifest.url}: {exc}") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

