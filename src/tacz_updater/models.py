from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class Action(str, Enum):
    CURRENT = "CURRENT"
    WOULD_UPDATE = "WOULD_UPDATE"
    UPDATED = "UPDATED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class LocalArchive:
    path: Path
    size: int
    mtime_ns: int
    fingerprint: int
    sha256: str


@dataclass(frozen=True)
class CfHash:
    algorithm: int
    value: str


@dataclass(frozen=True)
class CfFile:
    id: int
    mod_id: int
    file_name: str
    file_date: datetime
    file_length: int
    release_type: int
    is_available: bool
    download_url: str | None
    game_versions: tuple[str, ...]
    hashes: tuple[CfHash, ...]
    fingerprint: int | None
    is_server_pack: bool
    is_early_access: bool
    raw: dict[str, Any] = field(repr=False, compare=False)

    def hash_value(self, algorithm: int) -> str | None:
        for item in self.hashes:
            if item.algorithm == algorithm:
                return item.value.lower()
        return None


@dataclass(frozen=True)
class MatchedArchive:
    local: LocalArchive
    current: CfFile


@dataclass(frozen=True)
class UpdatePlan:
    local: LocalArchive
    current: CfFile
    target: CfFile | None


@dataclass(frozen=True)
class PreparedUpdate:
    plan: UpdatePlan
    staged_path: Path


@dataclass(frozen=True)
class Result:
    success: bool
    action: Action
    source_name: str
    message: str = ""
    target_name: str | None = None
    code: str | None = None

