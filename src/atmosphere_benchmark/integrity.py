from __future__ import annotations

import hashlib
from pathlib import Path

from .manifest import ArchiveSpec, MemberSpec


class IntegrityError(RuntimeError):
    """Raised when atmospheric benchmark data differs from its manifest."""


def file_digests(path: Path, chunk_size: int = 1024 * 1024) -> tuple[str, str]:
    md5 = hashlib.md5(usedforsecurity=False)
    sha256 = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            md5.update(chunk)
            sha256.update(chunk)
    return md5.hexdigest(), sha256.hexdigest()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_archive(path: Path, spec: ArchiveSpec) -> dict[str, object]:
    path = Path(path)
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise IntegrityError(f"cannot stat archive {path}: {exc}") from exc
    if size != spec.size_bytes:
        raise IntegrityError(
            f"archive size mismatch: expected {spec.size_bytes}, got {size}"
        )
    md5, sha256 = file_digests(path)
    if md5 != spec.publisher_md5:
        raise IntegrityError(
            f"archive MD5 mismatch: expected {spec.publisher_md5}, got {md5}"
        )
    if sha256 != spec.sha256:
        raise IntegrityError(
            f"archive SHA-256 mismatch: expected {spec.sha256}, got {sha256}"
        )
    return {"size_bytes": size, "publisher_md5": md5, "sha256": sha256}


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
    return {"role": spec.role, "path": spec.path, "size_bytes": size, "sha256": sha256}
