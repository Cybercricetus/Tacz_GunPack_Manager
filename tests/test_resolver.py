from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from tacz_updater.config import Config
from tacz_updater.errors import PackError
from tacz_updater.models import LocalArchive
from tacz_updater.resolver import match_local_archives, select_target

from .helpers import cf_file


class ResolverTests(TestCase):
    def setUp(self) -> None:
        self.config = Config("/tmp/tacz", "1.20.1", loader="forge", channel="release")

    def test_selects_newest_compatible_release(self) -> None:
        current = cf_file(file_id=1, days=0)
        beta = cf_file(file_id=3, days=3, name="pack-3.zip", release_type=2)
        newest_release = cf_file(file_id=2, days=2, name="pack-2.zip")
        wrong_mc = cf_file(
            file_id=4,
            days=4,
            name="pack-4.zip",
            game_versions=("1.21.1", "NeoForge"),
        )
        self.assertEqual(select_target(current, [beta, newest_release, wrong_mc], self.config), newest_release)

    def test_ambiguous_equal_timestamp_fails_closed(self) -> None:
        current = cf_file(file_id=1, days=0)
        a = cf_file(file_id=2, days=2, name="a.zip")
        b = cf_file(file_id=3, days=2, name="b.zip")
        with self.assertRaises(PackError) as raised:
            select_target(current, [a, b], self.config)
        self.assertEqual(raised.exception.code, "AMBIGUOUS_VERSION")

    def test_duplicate_project_is_not_guessed(self) -> None:
        first = LocalArchive(Path("a.zip"), 1, 1, 10, "a")
        second = LocalArchive(Path("b.zip"), 1, 1, 20, "b")
        matches = {
            10: cf_file(file_id=1, mod_id=7, fingerprint=10),
            20: cf_file(file_id=2, mod_id=7, fingerprint=20),
        }
        resolved, failures = match_local_archives([first, second], matches)
        self.assertEqual(resolved, [])
        self.assertEqual({error.code for _, error in failures}, {"DUPLICATE_PROJECT"})

