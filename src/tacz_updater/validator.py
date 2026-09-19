from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path, PurePosixPath

from .errors import PackError
from .fingerprint import curseforge_fingerprint
from .models import CfFile


MAX_ARCHIVE_ENTRIES = 200_000
MAX_UNCOMPRESSED_SIZE = 8 * 1024 * 1024 * 1024


def _digest(path: Path, algorithm: str) -> str:
    value = hashlib.new(algorithm)
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest().lower()


def validate_download(path: Path, remote: CfFile) -> None:
    actual_size = path.stat().st_size
    if remote.file_length and actual_size != remote.file_length:
        raise PackError(
            "SIZE_MISMATCH",
            f"expected {remote.file_length} bytes, received {actual_size}",
        )

    expected_sha1 = remote.hash_value(1)
    expected_md5 = remote.hash_value(2)
    if expected_sha1:
        if _digest(path, "sha1") != expected_sha1:
            raise PackError("HASH_MISMATCH", "SHA-1 does not match CurseForge metadata")
    elif expected_md5:
        if _digest(path, "md5") != expected_md5:
            raise PackError("HASH_MISMATCH", "MD5 does not match CurseForge metadata")
    else:
        raise PackError("NO_REMOTE_HASH", "CurseForge did not provide a file hash")

    if remote.fingerprint is not None and curseforge_fingerprint(path) != remote.fingerprint:
        raise PackError("FINGERPRINT_MISMATCH", "download fingerprint does not match CurseForge metadata")

    if not zipfile.is_zipfile(path):
        raise PackError("INVALID_ARCHIVE", "download is not a valid ZIP archive")

    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if not entries:
                raise PackError("EMPTY_ARCHIVE", "downloaded archive is empty")
            if len(entries) > MAX_ARCHIVE_ENTRIES:
                raise PackError("ARCHIVE_TOO_LARGE", "archive contains too many entries")
            uncompressed = 0
            for entry in entries:
                member = PurePosixPath(entry.filename.replace("\\", "/"))
                if member.is_absolute() or ".." in member.parts:
                    raise PackError("UNSAFE_ARCHIVE_PATH", f"unsafe member path: {entry.filename}")
                uncompressed += entry.file_size
                if uncompressed > MAX_UNCOMPRESSED_SIZE:
                    raise PackError("ARCHIVE_TOO_LARGE", "archive expands beyond the safety limit")
            bad_member = archive.testzip()
            if bad_member is not None:
                raise PackError("CRC_FAILED", f"CRC check failed for: {bad_member}")
    except zipfile.BadZipFile as exc:
        raise PackError("INVALID_ARCHIVE", str(exc)) from exc

