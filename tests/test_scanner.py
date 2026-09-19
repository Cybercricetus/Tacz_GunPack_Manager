import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from tacz_updater.scanner import archive_candidates, inspect_archive

from .helpers import make_zip


class ScannerTests(TestCase):
    def test_only_top_level_zip_and_jar_are_candidates(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_zip(root / "a.zip")
            make_zip(root / "b.jar")
            (root / "notes.txt").write_text("ignored", encoding="utf-8")
            (root / "broken.zip").write_bytes(b"not a zip")
            nested = root / "nested"
            nested.mkdir()
            make_zip(nested / "hidden.zip")

            candidates, failures = archive_candidates(root)
            self.assertEqual([item.name for item in candidates], ["a.zip", "b.jar"])
            self.assertEqual(failures[0][0].name, "broken.zip")
            self.assertEqual(failures[0][1].code, "INVALID_ARCHIVE")

    def test_inspection_records_stable_file_state(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "pack.zip"
            make_zip(path)
            result = inspect_archive(path)
            self.assertEqual(result.path, path)
            self.assertEqual(result.size, path.stat().st_size)
            self.assertEqual(len(result.sha256), 64)

