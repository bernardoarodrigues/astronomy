from __future__ import annotations

import hashlib
from pathlib import Path

from .manifest import DatasetManifest


class IntegrityError(RuntimeError):
    """Raised when local data differs from the fixed manifest baseline."""


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_file(path: Path, manifest: DatasetManifest) -> str:
    path = Path(path)
    try:
        actual_size = path.stat().st_size
    except OSError as exc:
        raise IntegrityError(f"cannot stat dataset {path}: {exc}") from exc
    if actual_size != manifest.size_bytes:
        raise IntegrityError(
            f"size mismatch for {path}: expected {manifest.size_bytes}, got {actual_size}"
        )
    actual_sha256 = sha256_file(path)
    if actual_sha256 != manifest.sha256:
        raise IntegrityError(
            f"SHA-256 mismatch for {path}: expected {manifest.sha256}, "
            f"got {actual_sha256}"
        )
    return actual_sha256

