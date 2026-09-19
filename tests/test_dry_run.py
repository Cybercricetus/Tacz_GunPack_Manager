import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock

from tacz_updater.config import Config
from tacz_updater.fingerprint import curseforge_fingerprint
from tacz_updater.models import Action
from tacz_updater.updater import run_update

from .helpers import cf_file, make_zip


class FakeCurseForgeClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def match_fingerprints(self, fingerprints):
        return {self.fingerprint: self.current}

    async def list_mod_files(self, mod_id, game_version):
        return [self.current, self.target]


class DryRunTests(TestCase):
    def test_dry_run_makes_no_filesystem_changes(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "instance" / ".minecraft"
            tacz = root / "tacz"
            tacz.mkdir(parents=True)
            archive = tacz / "pack-1.zip"
            make_zip(archive)
            fingerprint = curseforge_fingerprint(archive)
            FakeCurseForgeClient.fingerprint = fingerprint
            FakeCurseForgeClient.current = cf_file(
                file_id=1,
                name="pack-1.zip",
                days=0,
                fingerprint=fingerprint,
                path=archive,
            )
            FakeCurseForgeClient.target = cf_file(
                file_id=2,
                name="pack-2.zip",
                days=1,
                fingerprint=999,
                path=archive,
            )
            before = {item.relative_to(root): item.read_bytes() for item in root.rglob("*") if item.is_file()}
            config = Config(str(tacz), "1.20.1", loader="forge")

            with mock.patch("tacz_updater.updater.CurseForgeClient", FakeCurseForgeClient):
                results = asyncio.run(run_update(config, "secret", dry_run=True))

            after = {item.relative_to(root): item.read_bytes() for item in root.rglob("*") if item.is_file()}
            self.assertEqual(before, after)
            self.assertFalse((root / ".tacz-updater").exists())
            self.assertEqual(results[0].action, Action.WOULD_UPDATE)

    def test_real_run_recovers_before_scanning(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "instance" / ".minecraft"
            tacz = root / "tacz"
            tacz.mkdir(parents=True)
            workspace = root / ".tacz-updater"
            backup = workspace / "backups" / "interrupted" / "pack.zip"
            backup.parent.mkdir(parents=True)
            make_zip(backup)
            staged = workspace / "staging" / "interrupted" / "new.partial"
            staged.parent.mkdir(parents=True)
            journal = {
                "old": str(tacz / "pack.zip"),
                "target": str(tacz / "pack.zip"),
                "backup": str(backup),
                "staged": str(staged),
                "state": "old_moved",
            }
            (workspace / "journal.json").write_text(json.dumps(journal), encoding="utf-8")

            fingerprint = curseforge_fingerprint(backup)
            FakeCurseForgeClient.fingerprint = fingerprint
            FakeCurseForgeClient.current = cf_file(
                file_id=1,
                name="pack.zip",
                days=0,
                fingerprint=fingerprint,
                path=backup,
            )
            FakeCurseForgeClient.target = FakeCurseForgeClient.current
            config = Config(str(tacz), "1.20.1", loader="forge")

            with mock.patch("tacz_updater.updater.CurseForgeClient", FakeCurseForgeClient):
                results = asyncio.run(run_update(config, "secret", dry_run=False))

            self.assertTrue((tacz / "pack.zip").is_file())
            self.assertFalse((workspace / "journal.json").exists())
            self.assertEqual(results[0].action, Action.CURRENT)
