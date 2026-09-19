from __future__ import annotations

import asyncio
import uuid
from dataclasses import replace
from pathlib import Path

from .config import Config
from .curseforge import CurseForgeClient
from .errors import ApiError, PackError
from .fingerprint import raw_sha256
from .models import Action, PreparedUpdate, Result, UpdatePlan
from .resolver import match_local_archives, preflight_target_collisions, resolve_plans
from .scanner import archive_candidates, inspect_archives
from .transaction import TransactionManager
from .validator import validate_download


def _failure(name: str, error: PackError) -> Result:
    return Result(
        success=False,
        action=Action.FAILED,
        source_name=name,
        message=str(error),
        code=error.code,
    )


async def _prepare_downloads(
    plans: list[UpdatePlan], client: CurseForgeClient, staging_dir: Path
) -> tuple[list[PreparedUpdate], list[Result]]:
    prepared: list[PreparedUpdate] = []
    failures: list[Result] = []

    async def worker(plan: UpdatePlan) -> None:
        assert plan.target is not None
        target = plan.target
        partial = staging_dir / f"{target.id}-{uuid.uuid4().hex}.partial"
        try:
            url = target.download_url
            if url:
                client._validate_download_url(url)
            else:
                url = await client.get_download_url(target.mod_id, target.id)
            await client.download(url, partial)
            await asyncio.to_thread(validate_download, partial, target)
            prepared.append(PreparedUpdate(plan=plan, staged_path=partial))
        except ApiError as exc:
            partial.unlink(missing_ok=True)
            failures.append(_failure(plan.local.path.name, PackError(exc.code, str(exc))))
        except PackError as exc:
            partial.unlink(missing_ok=True)
            failures.append(_failure(plan.local.path.name, exc))
        except OSError as exc:
            partial.unlink(missing_ok=True)
            failures.append(_failure(plan.local.path.name, PackError("DOWNLOAD_FAILED", str(exc))))

    async with asyncio.TaskGroup() as group:
        for plan in plans:
            group.create_task(worker(plan))

    prepared.sort(key=lambda item: item.plan.local.path.name.casefold())
    failures.sort(key=lambda item: item.source_name.casefold())
    return prepared, failures


async def run_update(config: Config, api_key: str, *, dry_run: bool = False) -> list[Result]:
    results: list[Result] = []
    transactions: TransactionManager | None = None
    if not dry_run:
        transactions = TransactionManager(config.tacz_path)
        transactions.recover()

    candidates, scan_failures = archive_candidates(config.tacz_path)
    results.extend(_failure(path.name, error) for path, error in scan_failures)

    archives, inspect_failures = await inspect_archives(candidates)
    results.extend(_failure(path.name, error) for path, error in inspect_failures)
    if not archives:
        return results

    async with CurseForgeClient(
        api_key,
        api_concurrency=config.api_concurrency,
        download_concurrency=config.download_concurrency,
    ) as client:
        matches = await client.match_fingerprints([item.fingerprint for item in archives])
        matched, match_failures = match_local_archives(archives, matches)
        results.extend(_failure(item.path.name, error) for item, error in match_failures)

        plans, resolve_failures = await resolve_plans(matched, client, config)
        results.extend(_failure(item.path.name, error) for item, error in resolve_failures)

        collision_failures = preflight_target_collisions(plans)
        viable: list[UpdatePlan] = []
        for plan in plans:
            error = collision_failures.get(str(plan.local.path))
            if error:
                results.append(_failure(plan.local.path.name, error))
            else:
                viable.append(plan)

        for plan in viable:
            if plan.target is None:
                results.append(
                    Result(True, Action.CURRENT, plan.local.path.name, "already current")
                )

        updates = [plan for plan in viable if plan.target is not None]
        if dry_run:
            for plan in updates:
                assert plan.target is not None
                results.append(
                    Result(
                        True,
                        Action.WOULD_UPDATE,
                        plan.local.path.name,
                        f"CurseForge file {plan.current.id} -> {plan.target.id}",
                        target_name=plan.target.file_name,
                    )
                )
            return results

        if not updates:
            return results

        assert transactions is not None
        staging_dir = transactions.create_staging_dir()
        try:
            prepared, download_failures = await _prepare_downloads(updates, client, staging_dir)
            results.extend(download_failures)

            for item in prepared:
                plan = item.plan
                assert plan.target is not None
                try:
                    current_stat = plan.local.path.stat()
                    if (
                        current_stat.st_size != plan.local.size
                        or current_stat.st_mtime_ns != plan.local.mtime_ns
                        or await asyncio.to_thread(raw_sha256, plan.local.path) != plan.local.sha256
                    ):
                        raise PackError(
                            "LOCAL_FILE_CHANGED", "local archive changed after it was scanned"
                        )
                    transactions.commit(
                        plan.local.path,
                        item.staged_path,
                        plan.target.file_name,
                    )
                    results.append(
                        Result(
                            True,
                            Action.UPDATED,
                            plan.local.path.name,
                            f"CurseForge file {plan.current.id} -> {plan.target.id}",
                            target_name=plan.target.file_name,
                        )
                    )
                except PackError as exc:
                    results.append(_failure(plan.local.path.name, exc))
                except OSError as exc:
                    results.append(
                        _failure(plan.local.path.name, PackError("COMMIT_FAILED", str(exc)))
                    )
        finally:
            transactions.cleanup_staging(staging_dir)
    return results


def with_overrides(
    config: Config,
    *,
    tacz_dir: Path | None = None,
    channel: str | None = None,
    jobs: int | None = None,
) -> Config:
    updated = replace(
        config,
        tacz_dir=str(tacz_dir.resolve()) if tacz_dir else config.tacz_dir,
        channel=channel or config.channel,
        api_concurrency=jobs or config.api_concurrency,
        download_concurrency=min(jobs or config.download_concurrency, 8),
    )
    updated.validate()
    return updated
