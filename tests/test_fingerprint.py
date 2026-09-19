from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from tacz_updater.fingerprint import curseforge_fingerprint, fingerprint_and_sha256


class FingerprintTests(TestCase):
    def test_golden_vectors(self) -> None:
        samples = {
            b"": 1540447798,
            b"abc": 1621425345,
            b"a b\nc\r\td": 3376380438,
            b"The quick brown fox jumps over the lazy dog": 3751777527,
        }
        with TemporaryDirectory() as temporary:
            for index, (content, expected) in enumerate(samples.items()):
                path = Path(temporary) / str(index)
                path.write_bytes(content)
                self.assertEqual(curseforge_fingerprint(path), expected)

    def test_curseforge_whitespace_normalization(self) -> None:
        with TemporaryDirectory() as temporary:
            left = Path(temporary) / "left"
            right = Path(temporary) / "right"
            left.write_bytes(b"abcdef")
            right.write_bytes(b"a b\tc\nd\re f")
            self.assertEqual(curseforge_fingerprint(left), curseforge_fingerprint(right))
            _, left_sha = fingerprint_and_sha256(left)
            _, right_sha = fingerprint_and_sha256(right)
            self.assertNotEqual(left_sha, right_sha)

