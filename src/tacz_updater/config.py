from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from .errors import ConfigError


VALID_LOADERS = {"any", "forge", "neoforge", "fabric", "quilt"}
VALID_CHANNELS = {"release", "beta", "alpha"}


def app_config_dir() -> Path:
    if sys.platform == "win32":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "tacz-updater"


def config_path() -> Path:
    return app_config_dir() / "config.json"


@dataclass(frozen=True)
class Config:
    tacz_dir: str
    minecraft_version: str
    loader: str = "forge"
    channel: str = "release"
    api_concurrency: int = 4
    download_concurrency: int = 3

    @property
    def tacz_path(self) -> Path:
        return Path(self.tacz_dir)

    def validate(self) -> None:
        path = self.tacz_path
        if not path.is_dir():
            raise ConfigError(f"TaCZ directory does not exist: {path}")
        if self.loader not in VALID_LOADERS:
            raise ConfigError(f"Unsupported loader: {self.loader}")
        if self.channel not in VALID_CHANNELS:
            raise ConfigError(f"Unsupported channel: {self.channel}")
        if not self.minecraft_version.strip():
            raise ConfigError("Minecraft version cannot be empty")
        if not 1 <= self.api_concurrency <= 16:
            raise ConfigError("api_concurrency must be between 1 and 16")
        if not 1 <= self.download_concurrency <= 8:
            raise ConfigError("download_concurrency must be between 1 and 8")


def resolve_tacz_dir(user_path: str | Path) -> Path:
    supplied = Path(user_path).expanduser()
    candidates = [supplied, supplied / "tacz", supplied / ".minecraft" / "tacz"]
    for candidate in candidates:
        if candidate.is_dir() and candidate.name.casefold() == "tacz":
            return candidate.resolve()
    raise ConfigError(
        "Could not find a tacz directory. Pass the tacz directory, the .minecraft "
        "directory, or the instance root."
    )


def save_config(config: Config) -> Path:
    config.validate()
    destination = config_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
    os.replace(temporary, destination)
    return destination


def load_config() -> Config:
    source = config_path()
    if not source.is_file():
        raise ConfigError("Not initialized. Run: tacz-update init <path-to-tacz>")
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
        config = Config(**payload)
    except (OSError, ValueError, TypeError) as exc:
        raise ConfigError(f"Cannot read configuration: {exc}") from exc
    config.validate()
    return config

