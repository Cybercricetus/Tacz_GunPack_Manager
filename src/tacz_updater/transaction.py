from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .errors import PackError


class TransactionManager:
    """Per-file journaled replacement manager.

    The workspace is a sibling of tacz, keeping staging, backups, and the target
    on the same filesystem so os.replace() retains its strongest semantics.
    """

    def __init__(self, tacz_dir: Path):
        self.tacz_dir = tacz_dir.resolve()
        self.workspace = self.tacz_dir.parent / ".tacz-updater"
        self.staging_root = self.workspace / "staging"
        self.backup_root = self.workspace / "backups"
        self.journal_path = self.workspace / "journal.json"

    def create_staging_dir(self) -> Path:
        self.staging_root.mkdir(parents=True, exist_ok=True)
        run_dir = self.staging_root / uuid.uuid4().hex
        run_dir.mkdir()
        return run_dir

    def _write_journal(self, payload: dict[str, str]) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)
        temporary = self.journal_path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.journal_path)

    def _read_journal(self) -> dict[str, str]:
        try:
            payload = json.loads(self.journal_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise PackError("RECOVERY_FAILED", f"cannot read transaction journal: {exc}") from exc
        required = {"old", "target", "backup", "staged", "state"}
        if not required.issubset(payload):
            raise PackError("RECOVERY_FAILED", "transaction journal is incomplete")
        return payload

    def _validated_journal_paths(
        self, payload: dict[str, str]
    ) -> tuple[Path, Path, Path, Path]:
        old = Path(payload["old"]).resolve()
        target = Path(payload["target"]).resolve()
        backup = Path(payload["backup"]).resolve()
        staged = Path(payload["staged"]).resolve()
        if old.parent != self.tacz_dir or target.parent != self.tacz_dir:
            raise PackError("RECOVERY_FAILED", "journal target is outside the tacz directory")
        if not backup.is_relative_to(self.backup_root.resolve()):
            raise PackError("RECOVERY_FAILED", "journal backup is outside the backup directory")
        if not staged.is_relative_to(self.staging_root.resolve()):
            raise PackError("RECOVERY_FAILED", "journal staging file is outside the staging directory")
        return old, target, backup, staged

    def recover(self) -> None:
        if not self.journal_path.exists():
            return
        payload = self._read_journal()
        old, target, backup, _staged = self._validated_journal_paths(payload)
        state = payload["state"]

        if state == "prepared":
            self.journal_path.unlink(missing_ok=True)
            return
        if state == "old_moved":
            if backup.exists() and not old.exists():
                old.parent.mkdir(parents=True, exist_ok=True)
                os.replace(backup, old)
            elif not old.exists():
                raise PackError("RECOVERY_FAILED", "both the original archive and backup are missing")
            self.journal_path.unlink(missing_ok=True)
            return
        if state == "new_moved":
            if target.exists():
                self.journal_path.unlink(missing_ok=True)
                return
            if backup.exists() and not old.exists():
                os.replace(backup, old)
                self.journal_path.unlink(missing_ok=True)
                return
            raise PackError("RECOVERY_FAILED", "cannot resolve an interrupted committed transaction")
        raise PackError("RECOVERY_FAILED", f"unknown transaction state: {state}")

    def commit(self, old: Path, staged: Path, target_name: str) -> Path:
        old = old.resolve()
        staged = staged.resolve()
        if old.parent != self.tacz_dir:
            raise PackError("UNSAFE_PATH", "source archive is outside the configured tacz directory")
        if not staged.is_relative_to(self.staging_root.resolve()):
            raise PackError("UNSAFE_PATH", "staged archive is outside the updater staging directory")
        target = self.tacz_dir / Path(target_name).name
        if target.name != target_name:
            raise PackError("UNSAFE_PATH", "target filename contains path components")
        if target.exists() and target != old:
            raise PackError("TARGET_COLLISION", "target filename already exists")

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_dir = self.backup_root / f"{stamp}-{uuid.uuid4().hex[:8]}"
        backup_dir.mkdir(parents=True, exist_ok=False)
        backup = backup_dir / old.name
        journal = {
            "old": str(old),
            "target": str(target),
            "backup": str(backup),
            "staged": str(staged),
            "state": "prepared",
        }
        self._write_journal(journal)

        try:
            os.replace(old, backup)
            journal["state"] = "old_moved"
            self._write_journal(journal)
            os.replace(staged, target)
            journal["state"] = "new_moved"
            self._write_journal(journal)
        except BaseException:
            try:
                if backup.exists() and not old.exists():
                    if target.exists() and target != old:
                        target.unlink()
                    os.replace(backup, old)
                self.journal_path.unlink(missing_ok=True)
            except OSError:
                # Leave the journal in place for deterministic recovery next run.
                pass
            raise
        else:
            self.journal_path.unlink(missing_ok=True)
            return backup

    def cleanup_staging(self, run_dir: Path) -> None:
        try:
            resolved = run_dir.resolve()
            if resolved.parent == self.staging_root.resolve() and resolved.exists():
                shutil.rmtree(resolved)
        except OSError:
            pass
