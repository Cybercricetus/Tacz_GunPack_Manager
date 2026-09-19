from __future__ import annotations

import asyncio
import zipfile
from pathlib import Path

from .errors import PackError
from .fingerprint import fingerprint_and_sha256
from .models import LocalArchive


SUPPORTED_SUFFIXES = {".zip", ".jar"}


def archive_candidates(tacz_dir: Path) -> tuple[list[Path], list[tuple[Path, PackError]]]:
    candidates: list[Path] = []
    failures: list[tuple[Path, PackError]] = []
    for path in sorted(tacz_dir.iterdir(), key=lambda item: item.name.casefold()):
        if path.suffix.casefold() not in SUPPORTED_SUFFIXES:
            continue
        if path.is_symlink():
            failures.append((path, PackError("SYMLINK_IGNORED", "symbolic links are not supported")))
            continue
        if not path.is_file():
            continue
        if not zipfile.is_zipfile(path):
            failures.append((path, PackError("INVALID_ARCHIVE", "file is not a valid ZIP archive")))
            continue
        candidates.append(path)
    return candidates, failures


def inspect_archive(path: Path) -> LocalArchive:
    before = path.stat()
    fingerprint, sha256 = fingerprint_and_sha256(path)
    after = path.stat()
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise PackError("LOCAL_FILE_CHANGED", "file changed while it was being scanned")
    return LocalArchive(
        path=path,
        size=after.st_size,
        mtime_ns=after.st_mtime_ns,
        fingerprint=fingerprint,
        sha256=sha256,
    )


async def inspect_archives(paths: list[Path], concurrency: int = 2) -> tuple[list[LocalArchive], list[tuple[Path, PackError]]]:
    semaphore = asyncio.Semaphore(max(1, concurrency))
    successes: list[LocalArchive] = []
    failures: list[tuple[Path, PackError]] = []

    async def worker(path: Path) -> None:
        async with semaphore:
            try:
                item = await asyncio.to_thread(inspect_archive, path)
            except PackError as exc:
                failures.append((path, exc))
            except OSError as exc:
                failures.append((path, PackError("READ_FAILED", str(exc))))
            else:
                successes.append(item)

    async with asyncio.TaskGroup() as group:
        for path in paths:
            group.create_task(worker(path))

    successes.sort(key=lambda item: item.path.name.casefold())
    failures.sort(key=lambda item: item[0].name.casefold())
    return successes, failures

