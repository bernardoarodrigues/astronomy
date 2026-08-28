from __future__ import annotations

import hashlib
import os
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from .integrity import IntegrityError, verify_archive, verify_member
from .manifest import K218Manifest, MemberSpec


class ExtractionError(RuntimeError):
    """Raised when a ZIP violates the frozen safe-extraction policy."""


def _validate_member_name(name: str) -> PurePosixPath:
    if not name or "\\" in name or "\x00" in name:
        raise ExtractionError(f"unsafe ZIP member name: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise ExtractionError(f"unsafe ZIP member path: {name!r}")
    if path.parts and ":" in path.parts[0]:
        raise ExtractionError(f"drive-like ZIP member path: {name!r}")
    return path


def _validated_members(
    archive: zipfile.ZipFile, manifest: K218Manifest
) -> dict[str, zipfile.ZipInfo]:
    infos = archive.infolist()
    if len(infos) > manifest.archive.max_archive_members:
        raise ExtractionError(f"archive has {len(infos)} members, above the member guard")
    total = 0
    by_name: dict[str, zipfile.ZipInfo] = {}
    for info in infos:
        _validate_member_name(info.filename)
        if info.filename in by_name:
            raise ExtractionError(f"duplicate ZIP member: {info.filename}")
        by_name[info.filename] = info
        if info.flag_bits & 0x1:
            raise ExtractionError(f"encrypted ZIP member is not allowed: {info.filename}")
        mode = (info.external_attr >> 16) & 0xFFFF
        if stat.S_ISLNK(mode):
            raise ExtractionError(f"symbolic-link ZIP member is not allowed: {info.filename}")
        total += info.file_size
        if total > manifest.archive.max_total_uncompressed_bytes:
            raise ExtractionError("archive uncompressed size exceeds the extraction guard")
    for member in manifest.members:
        info = by_name.get(member.path)
        if info is None or info.is_dir():
            raise ExtractionError(f"required archive member is missing: {member.path}")
        if info.file_size != member.size_bytes:
            raise ExtractionError(
                f"member {member.path} advertises {info.file_size} bytes; expected {member.size_bytes}"
            )
    return by_name


def _copy_member(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    spec: MemberSpec,
    root: Path,
) -> None:
    destination = root.joinpath(*PurePosixPath(spec.path).parts)
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    total = 0
    with archive.open(info) as source, destination.open("xb") as target:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            total += len(chunk)
            if total > spec.size_bytes:
                raise ExtractionError(f"member {spec.path} exceeded its size guard")
            target.write(chunk)
            digest.update(chunk)
        target.flush()
        os.fsync(target.fileno())
    if total != spec.size_bytes:
        raise ExtractionError(f"member {spec.path} extracted {total} bytes; expected {spec.size_bytes}")
    if digest.hexdigest() != spec.sha256:
        raise ExtractionError(
            f"member {spec.path} SHA-256 mismatch: expected {spec.sha256}, got {digest.hexdigest()}"
        )


def verify_extracted(extracted_dir: Path, manifest: K218Manifest) -> list[dict[str, object]]:
    root = Path(extracted_dir)
    if root.is_symlink() or not root.is_dir():
        raise IntegrityError(f"extracted root is not a real directory: {root}")
    expected = {member.path for member in manifest.members}
    observed: set[str] = set()
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise IntegrityError(f"unexpected symbolic link in extracted directory: {relative}")
        if path.is_file():
            observed.add(relative)
        elif not path.is_dir():
            raise IntegrityError(f"unexpected filesystem entry in extracted directory: {relative}")
    if observed != expected:
        raise IntegrityError(
            "extracted file set differs from allowlist; "
            f"extras={sorted(observed - expected)}, missing={sorted(expected - observed)}"
        )
    return [
        verify_member(root / member.path, member)
        for member in sorted(manifest.members, key=lambda item: item.role)
    ]


def safe_extract_archive(
    archive_path: Path,
    destination_dir: Path,
    manifest: K218Manifest,
) -> Path:
    """Verify the ZIP and atomically extract only the four allowlisted NRS2 views."""

    verify_archive(archive_path, manifest.archive)
    destination_dir = Path(destination_dir)
    if destination_dir.exists():
        try:
            verify_extracted(destination_dir, manifest)
        except IntegrityError as exc:
            raise ExtractionError(f"existing extraction is invalid; refusing to overwrite it: {exc}") from exc
        return destination_dir
    destination_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{destination_dir.name}.",
            suffix=".extracting",
            dir=destination_dir.parent,
        )
    )
    try:
        try:
            with zipfile.ZipFile(archive_path) as archive:
                by_name = _validated_members(archive, manifest)
                for member in manifest.members:
                    _copy_member(archive, by_name[member.path], member, temporary)
        except zipfile.BadZipFile as exc:
            raise ExtractionError(f"invalid ZIP archive: {exc}") from exc
        verify_extracted(temporary, manifest)
        os.replace(temporary, destination_dir)
        return destination_dir
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
