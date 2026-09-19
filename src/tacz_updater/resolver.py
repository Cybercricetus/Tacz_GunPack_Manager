from __future__ import annotations

import asyncio
import re
from collections import defaultdict

from .config import Config
from .curseforge import CurseForgeClient
from .errors import ApiError, PackError
from .models import CfFile, LocalArchive, MatchedArchive, UpdatePlan


_LOADER_TAGS = {"forge", "neoforge", "fabric", "quilt"}
_EXCLUDED_NAME = re.compile(r"(?:^|[-_.])(sources?|dev|deobf|javadoc|server[-_.]?pack)(?:[-_.]|$)", re.I)
_CHANNEL_RELEASE_TYPES = {
    "release": {1},
    "beta": {1, 2},
    "alpha": {1, 2, 3},
}


def match_local_archives(
    archives: list[LocalArchive], matches: dict[int, CfFile]
) -> tuple[list[MatchedArchive], list[tuple[LocalArchive, PackError]]]:
    resolved: list[MatchedArchive] = []
    failures: list[tuple[LocalArchive, PackError]] = []
    by_mod: dict[int, list[LocalArchive]] = defaultdict(list)

    for archive in archives:
        remote = matches.get(archive.fingerprint)
        if remote is None:
            failures.append(
                (archive, PackError("UNMATCHED", "CurseForge exact fingerprint match not found"))
            )
        else:
            by_mod[remote.mod_id].append(archive)

    duplicate_mods = {mod_id for mod_id, items in by_mod.items() if len(items) > 1}
    for archive in archives:
        remote = matches.get(archive.fingerprint)
        if remote is None:
            continue
        if remote.mod_id in duplicate_mods:
            failures.append(
                (
                    archive,
                    PackError(
                        "DUPLICATE_PROJECT",
                        "multiple local archives belong to the same CurseForge project",
                    ),
                )
            )
        else:
            resolved.append(MatchedArchive(local=archive, current=remote))

    resolved.sort(key=lambda item: item.local.path.name.casefold())
    failures.sort(key=lambda item: item[0].path.name.casefold())
    return resolved, failures


def _loader_compatible(file: CfFile, configured_loader: str) -> bool:
    if configured_loader == "any":
        return True
    declared = {tag.casefold() for tag in file.game_versions} & _LOADER_TAGS
    return not declared or configured_loader in declared


def select_target(current: CfFile, files: list[CfFile], config: Config) -> CfFile | None:
    allowed_release_types = _CHANNEL_RELEASE_TYPES[config.channel]
    current_suffix = current.file_name.rsplit(".", 1)[-1].casefold()
    candidates = []
    for item in files:
        suffix = item.file_name.rsplit(".", 1)[-1].casefold()
        if item.id == current.id or item.file_date <= current.file_date:
            continue
        if not item.is_available or item.is_server_pack or item.is_early_access:
            continue
        if item.release_type not in allowed_release_types:
            continue
        if suffix not in {"zip", "jar"} or suffix != current_suffix:
            continue
        if config.minecraft_version not in item.game_versions:
            continue
        if not _loader_compatible(item, config.loader):
            continue
        if _EXCLUDED_NAME.search(item.file_name):
            continue
        candidates.append(item)

    if not candidates:
        return None
    candidates.sort(key=lambda item: (item.file_date, item.id), reverse=True)
    newest = candidates[0]
    equally_new = [item for item in candidates if item.file_date == newest.file_date]
    if len(equally_new) > 1:
        raise PackError(
            "AMBIGUOUS_VERSION",
            "multiple equally-new compatible files were found",
        )
    return newest


async def resolve_plans(
    matched: list[MatchedArchive], client: CurseForgeClient, config: Config
) -> tuple[list[UpdatePlan], list[tuple[LocalArchive, PackError]]]:
    plans: list[UpdatePlan] = []
    failures: list[tuple[LocalArchive, PackError]] = []

    async def worker(item: MatchedArchive) -> None:
        try:
            files = await client.list_mod_files(item.current.mod_id, config.minecraft_version)
            target = select_target(item.current, files, config)
            plans.append(UpdatePlan(local=item.local, current=item.current, target=target))
        except PackError as exc:
            failures.append((item.local, exc))
        except ApiError as exc:
            failures.append((item.local, PackError(exc.code, str(exc))))

    async with asyncio.TaskGroup() as group:
        for item in matched:
            group.create_task(worker(item))

    plans.sort(key=lambda item: item.local.path.name.casefold())
    failures.sort(key=lambda item: item[0].path.name.casefold())
    return plans, failures


def preflight_target_collisions(plans: list[UpdatePlan]) -> dict[str, PackError]:
    failures: dict[str, PackError] = {}
    target_names: dict[str, list[UpdatePlan]] = defaultdict(list)
    local_by_name = {plan.local.path.name.casefold(): plan for plan in plans}

    for plan in plans:
        if plan.target is None:
            continue
        target_names[plan.target.file_name.casefold()].append(plan)

    for normalized, colliding in target_names.items():
        if len(colliding) > 1:
            for plan in colliding:
                failures[str(plan.local.path)] = PackError(
                    "TARGET_COLLISION", "multiple projects resolve to the same target filename"
                )
            continue
        plan = colliding[0]
        occupied = local_by_name.get(normalized)
        if occupied is not None and occupied.local.path != plan.local.path:
            failures[str(plan.local.path)] = PackError(
                "TARGET_COLLISION", "target filename is occupied by another local archive"
            )
    return failures

