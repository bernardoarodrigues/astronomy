from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .integrity import IntegrityError, verify_archive
from .manifest import K218Manifest


class DownloadError(RuntimeError):
    """Raised when the archive cannot meet the guarded transfer contract."""


Opener = Callable[..., Any]


def _content_length(response: Any) -> int | None:
    raw = response.headers.get("Content-Length")
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise DownloadError(f"invalid HTTP Content-Length: {raw!r}") from exc
    if value < 0:
        raise DownloadError("negative HTTP Content-Length")
    return value


def _guard_length(length: int | None, *, expected: int, maximum: int) -> None:
    if length is None:
        return
    if length > maximum:
        raise DownloadError(f"remote object is {length} bytes, above the {maximum}-byte guard")
    if length != expected:
        raise DownloadError(f"remote size {length} does not match manifest size {expected}")


def download_archive(
    manifest: K218Manifest,
    destination_dir: Path,
    *,
    max_bytes: int | None = None,
    timeout_seconds: float = 30.0,
    opener: Opener = urlopen,
) -> Path:
    spec = manifest.archive
    maximum = spec.default_max_download_bytes if max_bytes is None else int(max_bytes)
    if not 0 < maximum <= spec.hard_max_download_bytes:
        raise DownloadError(f"max_bytes must be between 1 and {spec.hard_max_download_bytes}")
    if spec.size_bytes > maximum:
        raise DownloadError(f"manifest size {spec.size_bytes} exceeds {maximum}-byte guard")

    destination_dir = Path(destination_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / spec.filename
    if destination.exists():
        try:
            verify_archive(destination, spec)
        except IntegrityError as exc:
            raise DownloadError(f"existing archive is invalid; refusing to overwrite it: {exc}") from exc
        return destination

    # Some object stores reject HEAD even though GET works. A 403/405 HEAD is
    # non-authoritative; the streamed byte guard and final digest remain mandatory.
    try:
        with opener(Request(spec.url, method="HEAD"), timeout=timeout_seconds) as response:
            _guard_length(_content_length(response), expected=spec.size_bytes, maximum=maximum)
    except HTTPError as exc:
        if exc.code not in (403, 405):
            raise DownloadError(f"HEAD request failed for {spec.url}: {exc}") from exc
    except DownloadError:
        raise
    except Exception as exc:
        raise DownloadError(f"HEAD request failed for {spec.url}: {exc}") from exc

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{spec.filename}.",
            suffix=".part",
            dir=destination_dir,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            digest = hashlib.sha256()
            total = 0
            with opener(Request(spec.url, method="GET"), timeout=timeout_seconds) as response:
                _guard_length(_content_length(response), expected=spec.size_bytes, maximum=maximum)
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > maximum or total > spec.hard_max_download_bytes:
                        raise DownloadError(f"stream exceeded the {maximum}-byte transfer guard")
                    if total > spec.size_bytes:
                        raise DownloadError("stream exceeded the manifested archive size")
                    temporary.write(chunk)
                    digest.update(chunk)
            temporary.flush()
            os.fsync(temporary.fileno())
        if total != spec.size_bytes:
            raise DownloadError(f"downloaded {total} bytes, expected {spec.size_bytes}")
        if digest.hexdigest() != spec.sha256:
            raise DownloadError(
                f"SHA-256 mismatch: expected {spec.sha256}, got {digest.hexdigest()}"
            )
        os.replace(temporary_path, destination)
        temporary_path = None
        return destination
    except DownloadError:
        raise
    except Exception as exc:
        raise DownloadError(f"download failed for {spec.url}: {exc}") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
