from __future__ import annotations

import hashlib
from pathlib import Path

from .manifest import ArchiveSpec, MemberSpec


class IntegrityError(RuntimeError):
    """Raised when a source object differs from the frozen manifest."""


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(chunk_size), b""):
                digest.update(chunk)
    except OSError as exc:
        raise IntegrityError(f"cannot read {path}: {exc}") from exc
    return digest.hexdigest()


def verify_archive(path: Path, spec: ArchiveSpec) -> dict[str, object]:
    path = Path(path)
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise IntegrityError(f"cannot stat archive {path}: {exc}") from exc
    if size != spec.size_bytes:
        raise IntegrityError(f"archive size mismatch: expected {spec.size_bytes}, got {size}")
    sha256 = sha256_file(path)
    if sha256 != spec.sha256:
        raise IntegrityError(f"archive SHA-256 mismatch: expected {spec.sha256}, got {sha256}")
    return {"size_bytes": size, "sha256": sha256}


def verify_member(path: Path, spec: MemberSpec) -> dict[str, object]:
    path = Path(path)
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise IntegrityError(f"cannot stat extracted member {path}: {exc}") from exc
    if size != spec.size_bytes:
        raise IntegrityError(
            f"member {spec.path} size mismatch: expected {spec.size_bytes}, got {size}"
        )
    sha256 = sha256_file(path)
    if sha256 != spec.sha256:
        raise IntegrityError(
            f"member {spec.path} SHA-256 mismatch: expected {spec.sha256}, got {sha256}"
        )
    return {
        "role": spec.role,
        "path": spec.path,
        "size_bytes": size,
        "sha256": sha256,
    }
