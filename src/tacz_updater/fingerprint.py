from __future__ import annotations

import hashlib
from pathlib import Path


_DELETE_BYTES = b"\x09\x0a\x0d\x20"
_MURMUR_M = 0x5BD1E995
_UINT32 = 0xFFFFFFFF
_SEED = 1
_CHUNK_SIZE = 1024 * 1024


def _normalized_length_and_sha256(path: Path) -> tuple[int, str]:
    normalized_length = 0
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_CHUNK_SIZE):
            digest.update(chunk)
            normalized_length += len(chunk.translate(None, _DELETE_BYTES))
    return normalized_length, digest.hexdigest()


def _murmur2_normalized(path: Path, normalized_length: int) -> int:
    h = (_SEED ^ normalized_length) & _UINT32
    carry = b""

    with path.open("rb") as stream:
        while chunk := stream.read(_CHUNK_SIZE):
            data = carry + chunk.translate(None, _DELETE_BYTES)
            end = len(data) - (len(data) % 4)
            for offset in range(0, end, 4):
                k = int.from_bytes(data[offset : offset + 4], "little")
                k = (k * _MURMUR_M) & _UINT32
                k ^= k >> 24
                k = (k * _MURMUR_M) & _UINT32
                h = (h * _MURMUR_M) & _UINT32
                h ^= k
            carry = data[end:]

    if len(carry) == 3:
        h ^= carry[2] << 16
    if len(carry) >= 2:
        h ^= carry[1] << 8
    if carry:
        h ^= carry[0]
        h = (h * _MURMUR_M) & _UINT32

    h ^= h >> 13
    h = (h * _MURMUR_M) & _UINT32
    h ^= h >> 15
    return h & _UINT32


def fingerprint_and_sha256(path: Path) -> tuple[int, str]:
    """Return CurseForge-compatible fingerprint and a raw SHA-256 digest."""

    normalized_length, sha256 = _normalized_length_and_sha256(path)
    return _murmur2_normalized(path, normalized_length), sha256


def curseforge_fingerprint(path: Path) -> int:
    normalized_length, _ = _normalized_length_and_sha256(path)
    return _murmur2_normalized(path, normalized_length)


def raw_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()

