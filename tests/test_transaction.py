import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock

from tacz_updater.errors import PackError
from tacz_updater.transaction import TransactionManager


class TransactionTests(TestCase):
    def test_commit_moves_old_to_backup_and_installs_new(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / ".minecraft"
            tacz = root / "tacz"
            tacz.mkdir(parents=True)
            old = tacz / "old.zip"
            old.write_bytes(b"old")
            manager = TransactionManager(tacz)
            staging = manager.create_staging_dir()
            new = staging / "new.partial"
            new.write_bytes(b"new")

            backup = manager.commit(old, new, "new.zip")

            self.assertFalse(old.exists())
            self.assertEqual((tacz / "new.zip").read_bytes(), b"new")
            self.assertEqual(backup.read_bytes(), b"old")
            self.assertFalse(manager.journal_path.exists())

    def test_failed_second_replace_rolls_back(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / ".minecraft"
            tacz = root / "tacz"
            tacz.mkdir(parents=True)
            old = tacz / "old.zip"
            old.write_bytes(b"old")
            manager = TransactionManager(tacz)
            staging = manager.create_staging_dir()
            new = staging / "new.partial"
            new.write_bytes(b"new")
            real_replace = os.replace

            def failing_replace(src, dst):
                if Path(src) == new.resolve() and Path(dst) == tacz / "new.zip":
                    raise OSError("simulated failure")
                return real_replace(src, dst)

            with mock.patch("tacz_updater.transaction.os.replace", side_effect=failing_replace):
                with self.assertRaises(OSError):
                    manager.commit(old, new, "new.zip")

            self.assertEqual(old.read_bytes(), b"old")
            self.assertFalse((tacz / "new.zip").exists())

    def test_recovery_restores_old_moved_transaction(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / ".minecraft"
            tacz = root / "tacz"
            tacz.mkdir(parents=True)
            manager = TransactionManager(tacz)
            manager.workspace.mkdir()
            backup_dir = manager.backup_root / "run"
            backup_dir.mkdir(parents=True)
            old = tacz / "old.zip"
            backup = backup_dir / "old.zip"
            backup.write_bytes(b"old")
            target = tacz / "new.zip"
            manager.journal_path.write_text(
                json.dumps(
                    {
                        "old": str(old),
                        "target": str(target),
                        "backup": str(backup),
                        "staged": str(manager.staging_root / "new.partial"),
                        "state": "old_moved",
                    }
                ),
                encoding="utf-8",
            )

            manager.recover()
            self.assertEqual(old.read_bytes(), b"old")
            self.assertFalse(manager.journal_path.exists())

    def test_recovery_rejects_paths_outside_workspace(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / ".minecraft"
            tacz = root / "tacz"
            tacz.mkdir(parents=True)
            manager = TransactionManager(tacz)
            manager.workspace.mkdir(parents=True)
            outside = root / "outside.zip"
            outside.write_bytes(b"do not touch")
            journal = {
                "old": str(outside),
                "target": str(outside),
                "backup": str(manager.backup_root / "run" / "pack.zip"),
                "staged": str(manager.staging_root / "run" / "new.partial"),
                "state": "old_moved",
            }
            manager.journal_path.write_text(json.dumps(journal), encoding="utf-8")

            with self.assertRaises(PackError):
                manager.recover()

            self.assertEqual(outside.read_bytes(), b"do not touch")
