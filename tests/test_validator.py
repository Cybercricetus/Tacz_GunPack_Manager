from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from tacz_updater.errors import PackError
from tacz_updater.fingerprint import curseforge_fingerprint
from tacz_updater.validator import validate_download

from .helpers import cf_file, make_zip


class ValidatorTests(TestCase):
    def test_valid_archive_passes_all_checks(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "pack.zip"
            make_zip(path)
            remote = cf_file(
                file_id=2,
                name="pack.zip",
                path=path,
                fingerprint=curseforge_fingerprint(path),
            )
            validate_download(path, remote)

    def test_hash_mismatch_is_rejected(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "pack.zip"
            make_zip(path)
            remote = cf_file(file_id=2, name="pack.zip", path=path)
            path.write_bytes(path.read_bytes() + b"changed")
            with self.assertRaises(PackError) as raised:
                validate_download(path, remote)
            self.assertIn(raised.exception.code, {"SIZE_MISMATCH", "HASH_MISMATCH"})

