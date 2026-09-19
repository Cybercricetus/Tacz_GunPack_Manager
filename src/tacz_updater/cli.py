from __future__ import annotations

import argparse
import asyncio
import os
import sys
from getpass import getpass
from pathlib import Path

from . import __version__
from .config import Config, app_config_dir, load_config, resolve_tacz_dir, save_config
from .credentials import ENV_NAME, get_api_key, store_api_key
from .curseforge import CurseForgeClient
from .errors import ApiError, ConfigError, CredentialError, PackError, TaczUpdaterError
from .output import print_results
from .updater import run_update, with_overrides


def _init_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tacz-update init", description="Initialize TaCZ updater")
    parser.add_argument("path", help="tacz directory, .minecraft directory, or instance root")
    parser.add_argument("--minecraft", required=True, dest="minecraft_version")
    parser.add_argument(
        "--loader", choices=["any", "forge", "neoforge", "fabric", "quilt"], default="forge"
    )
    parser.add_argument("--channel", choices=["release", "beta", "alpha"], default="release")
    return parser


def _update_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tacz-update",
        description="Safely update TaCZ gun pack archives from CurseForge",
    )
    parser.add_argument("--dry-run", action="store_true", help="resolve updates without downloading or writing")
    parser.add_argument("--tacz-dir", type=Path, help="override the configured tacz directory")
    parser.add_argument("--channel", choices=["release", "beta", "alpha"])
    parser.add_argument("--jobs", type=int, choices=range(1, 9), metavar="1-8")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


async def _run_init(args: argparse.Namespace) -> int:
    tacz_dir = resolve_tacz_dir(args.path)
    config = Config(
        tacz_dir=str(tacz_dir),
        minecraft_version=args.minecraft_version,
        loader=args.loader,
        channel=args.channel,
    )
    config.validate()

    api_key = os.environ.get(ENV_NAME, "").strip()
    if not api_key:
        api_key = getpass("CurseForge API key: ").strip()
    if not api_key:
        raise CredentialError("CurseForge API key cannot be empty")

    async with CurseForgeClient(api_key) as client:
        await client.validate_key()
    store_api_key(api_key)
    destination = save_config(config)
    print(f"SUCCESS [INITIALIZED] {tacz_dir}")
    print(f"Configuration: {destination}")
    return 0


async def _run_update(args: argparse.Namespace) -> int:
    config = load_config()
    override_dir = resolve_tacz_dir(args.tacz_dir) if args.tacz_dir else None
    config = with_overrides(
        config,
        tacz_dir=override_dir,
        channel=args.channel,
        jobs=args.jobs,
    )
    api_key = get_api_key()

    lock = None
    if not args.dry_run:
        try:
            from filelock import FileLock, Timeout
        except ImportError as exc:
            raise ConfigError(
                "The 'filelock' package is required. Reinstall tacz-updater with dependencies."
            ) from exc
        lock_path = app_config_dir() / "update.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock = FileLock(lock_path, timeout=0)
        try:
            lock.acquire()
        except Timeout as exc:
            raise ConfigError("another tacz-update process is already running") from exc

    try:
        results = await run_update(config, api_key, dry_run=args.dry_run)
    finally:
        if lock is not None:
            lock.release()

    print_results(results)
    return 1 if any(not item.success for item in results) else 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        if argv and argv[0] == "init":
            args = _init_parser().parse_args(argv[1:])
            return asyncio.run(_run_init(args))
        args = _update_parser().parse_args(argv)
        return asyncio.run(_run_update(args))
    except (ConfigError, CredentialError) as exc:
        print(f"FAILURE [CONFIG] {exc}", file=sys.stderr)
        return 2
    except ApiError as exc:
        print(f"FAILURE [{exc.code}] {exc}", file=sys.stderr)
        return 2 if exc.code in {"UNAUTHORIZED", "FORBIDDEN"} else 3
    except PackError as exc:
        print(f"FAILURE [{exc.code}] {exc}", file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        print("FAILURE [CANCELLED] interrupted by user", file=sys.stderr)
        return 130
    except TaczUpdaterError as exc:
        print(f"FAILURE [ERROR] {exc}", file=sys.stderr)
        return 3

