from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zipfile import ZipFile

from tacz_updater.models import CfFile, CfHash


def make_zip(path: Path, content: bytes = b"data") -> None:
    with ZipFile(path, "w") as archive:
        archive.writestr("pack.mcmeta", b'{"pack":{"pack_format":15,"description":"test"}}')
        archive.writestr("assets/test/item.bin", content)


def cf_file(
    *,
    file_id: int,
    mod_id: int = 100,
    name: str = "pack.zip",
    days: int = 0,
    fingerprint: int | None = None,
    path: Path | None = None,
    release_type: int = 1,
    game_versions: tuple[str, ...] = ("1.20.1", "Forge"),
) -> CfFile:
    length = path.stat().st_size if path else 10
    sha1 = hashlib.sha1(path.read_bytes()).hexdigest() if path else "0" * 40
    return CfFile(
        id=file_id,
        mod_id=mod_id,
        file_name=name,
        file_date=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=days),
        file_length=length,
        release_type=release_type,
        is_available=True,
        download_url="https://mediafilez.forgecdn.net/files/test/pack.zip",
        game_versions=game_versions,
        hashes=(CfHash(1, sha1),),
        fingerprint=fingerprint,
        is_server_pack=False,
        is_early_access=False,
        raw={},
    )

