from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from . import __version__
from .errors import ApiError
from .models import CfFile, CfHash


API_BASE = "https://api.curseforge.com/v1"
MINECRAFT_GAME_ID = 432
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _parse_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def parse_cf_file(payload: dict[str, Any]) -> CfFile:
    return CfFile(
        id=int(payload["id"]),
        mod_id=int(payload["modId"]),
        file_name=str(payload["fileName"]),
        file_date=_parse_datetime(payload.get("fileDate")),
        file_length=int(payload.get("fileLength") or payload.get("fileSizeOnDisk") or 0),
        release_type=int(payload.get("releaseType") or 3),
        is_available=bool(payload.get("isAvailable", True)),
        download_url=payload.get("downloadUrl"),
        game_versions=tuple(str(item) for item in payload.get("gameVersions", [])),
        hashes=tuple(
            CfHash(algorithm=int(item["algo"]), value=str(item["value"]))
            for item in payload.get("hashes", [])
            if "algo" in item and "value" in item
        ),
        fingerprint=int(payload["fileFingerprint"]) if payload.get("fileFingerprint") is not None else None,
        is_server_pack=bool(payload.get("isServerPack", False)),
        is_early_access=bool(payload.get("isEarlyAccessContent", False)),
        raw=payload,
    )


class CurseForgeClient:
    def __init__(self, api_key: str, *, api_concurrency: int = 4, download_concurrency: int = 3):
        try:
            import httpx
        except ImportError as exc:
            raise ApiError(
                "MISSING_DEPENDENCY",
                "The 'httpx' package is required. Reinstall tacz-updater with dependencies.",
            ) from exc

        self._httpx = httpx
        self._api_semaphore = asyncio.Semaphore(api_concurrency)
        self._download_semaphore = asyncio.Semaphore(download_concurrency)
        self._client = httpx.AsyncClient(
            base_url=API_BASE,
            headers={
                "Accept": "application/json",
                "x-api-key": api_key,
                "User-Agent": f"tacz-updater/{__version__}",
            },
            timeout=httpx.Timeout(connect=10.0, read=45.0, write=30.0, pool=10.0),
            follow_redirects=True,
            limits=httpx.Limits(max_connections=max(8, api_concurrency + download_concurrency)),
        )

    async def __aenter__(self) -> "CurseForgeClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self._client.aclose()

    async def _sleep_before_retry(self, response: Any | None, attempt: int) -> None:
        retry_after = None
        if response is not None:
            retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                delay = min(float(retry_after), 60.0)
            except ValueError:
                delay = 0.5 * (2**attempt)
        else:
            delay = 0.5 * (2**attempt)
        await asyncio.sleep(delay + random.uniform(0.0, 0.25))

    async def _request_json(self, method: str, path: str, **kwargs: Any) -> Any:
        last_error: Exception | None = None
        for attempt in range(3):
            response = None
            try:
                async with self._api_semaphore:
                    response = await self._client.request(method, path, **kwargs)
                if response.status_code in RETRYABLE_STATUS and attempt < 2:
                    await self._sleep_before_retry(response, attempt)
                    continue
                if response.status_code == 401:
                    raise ApiError("UNAUTHORIZED", "CurseForge API key was rejected", status_code=401)
                if response.status_code == 403:
                    raise ApiError("FORBIDDEN", "CurseForge denied access", status_code=403)
                if response.status_code == 404:
                    raise ApiError("NOT_FOUND", "CurseForge resource was not found", status_code=404)
                response.raise_for_status()
                return response.json()
            except ApiError:
                raise
            except (self._httpx.TimeoutException, self._httpx.TransportError) as exc:
                last_error = exc
                if attempt < 2:
                    await self._sleep_before_retry(response, attempt)
                    continue
            except self._httpx.HTTPStatusError as exc:
                raise ApiError(
                    "HTTP_ERROR",
                    f"CurseForge returned HTTP {exc.response.status_code}",
                    status_code=exc.response.status_code,
                ) from exc
            except ValueError as exc:
                raise ApiError("INVALID_RESPONSE", "CurseForge returned invalid JSON") from exc
        raise ApiError("NETWORK_ERROR", f"CurseForge request failed: {last_error}")

    async def validate_key(self) -> None:
        await self._request_json("GET", f"/games/{MINECRAFT_GAME_ID}")

    async def match_fingerprints(self, fingerprints: list[int]) -> dict[int, CfFile]:
        matches: dict[int, CfFile] = {}
        for offset in range(0, len(fingerprints), 1000):
            chunk = fingerprints[offset : offset + 1000]
            payload = await self._request_json(
                "POST",
                f"/fingerprints/{MINECRAFT_GAME_ID}",
                json={"fingerprints": chunk},
            )
            data = payload.get("data", {})
            for entry in data.get("exactMatches", []):
                file_payload = entry.get("file")
                if not file_payload:
                    continue
                parsed = parse_cf_file(file_payload)
                if parsed.fingerprint is not None:
                    matches[parsed.fingerprint] = parsed
        return matches

    async def list_mod_files(self, mod_id: int, game_version: str) -> list[CfFile]:
        files: list[CfFile] = []
        index = 0
        while True:
            payload = await self._request_json(
                "GET",
                f"/mods/{mod_id}/files",
                params={"gameVersion": game_version, "index": index, "pageSize": 50},
            )
            page = payload.get("data", [])
            files.extend(parse_cf_file(item) for item in page)
            pagination = payload.get("pagination", {})
            result_count = int(pagination.get("resultCount", len(page)))
            total_count = int(pagination.get("totalCount", len(files)))
            if result_count == 0 or len(files) >= total_count:
                break
            index += result_count
            if index >= 10_000:
                break
        return files

    async def get_download_url(self, mod_id: int, file_id: int) -> str:
        payload = await self._request_json(
            "GET", f"/mods/{mod_id}/files/{file_id}/download-url"
        )
        url = payload.get("data")
        if not isinstance(url, str) or not url:
            raise ApiError("DOWNLOAD_FORBIDDEN", "download URL is unavailable")
        self._validate_download_url(url)
        return url

    @staticmethod
    def _validate_download_url(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ApiError("UNSAFE_DOWNLOAD_URL", "CurseForge returned a non-HTTPS download URL")

    async def download(self, url: str, destination: Path) -> int:
        self._validate_download_url(url)
        last_error: Exception | None = None
        for attempt in range(3):
            response = None
            try:
                destination.unlink(missing_ok=True)
                async with self._download_semaphore:
                    async with self._client.stream("GET", url) as response:
                        if response.status_code in RETRYABLE_STATUS and attempt < 2:
                            await response.aread()
                            await self._sleep_before_retry(response, attempt)
                            continue
                        if response.status_code in {401, 403}:
                            raise ApiError("DOWNLOAD_FORBIDDEN", "download was denied", status_code=response.status_code)
                        if response.status_code == 404:
                            raise ApiError("DOWNLOAD_NOT_FOUND", "download file was not found", status_code=404)
                        response.raise_for_status()
                        size = 0
                        with destination.open("wb") as stream:
                            async for chunk in response.aiter_bytes(1024 * 1024):
                                stream.write(chunk)
                                size += len(chunk)
                        return size
            except ApiError:
                destination.unlink(missing_ok=True)
                raise
            except (self._httpx.TimeoutException, self._httpx.TransportError) as exc:
                last_error = exc
                destination.unlink(missing_ok=True)
                if attempt < 2:
                    await self._sleep_before_retry(response, attempt)
                    continue
            except self._httpx.HTTPStatusError as exc:
                destination.unlink(missing_ok=True)
                raise ApiError(
                    "DOWNLOAD_HTTP_ERROR",
                    f"download returned HTTP {exc.response.status_code}",
                    status_code=exc.response.status_code,
                ) from exc
            except OSError as exc:
                destination.unlink(missing_ok=True)
                raise ApiError("WRITE_FAILED", f"cannot write downloaded file: {exc}") from exc
        raise ApiError("DOWNLOAD_NETWORK_ERROR", f"download failed: {last_error}")

