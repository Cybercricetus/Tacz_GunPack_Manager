from __future__ import annotations

import os

from .errors import CredentialError


SERVICE_NAME = "tacz-updater"
ACCOUNT_NAME = "curseforge-api-key"
ENV_NAME = "CURSEFORGE_API_KEY"


def _keyring_module():
    try:
        import keyring
        from keyring.errors import KeyringError
    except ImportError as exc:
        raise CredentialError(
            "The 'keyring' package is required. Reinstall tacz-updater with dependencies."
        ) from exc
    return keyring, KeyringError


def get_api_key() -> str:
    from_env = os.environ.get(ENV_NAME, "").strip()
    if from_env:
        return from_env
    keyring, keyring_error = _keyring_module()
    try:
        value = keyring.get_password(SERVICE_NAME, ACCOUNT_NAME)
    except keyring_error as exc:
        raise CredentialError(f"Cannot read the OS credential store: {exc}") from exc
    if not value:
        raise CredentialError("No CurseForge API key found. Run tacz-update init again.")
    return value


def store_api_key(value: str) -> None:
    value = value.strip()
    if not value:
        raise CredentialError("CurseForge API key cannot be empty")
    keyring, keyring_error = _keyring_module()
    try:
        keyring.set_password(SERVICE_NAME, ACCOUNT_NAME, value)
    except keyring_error as exc:
        raise CredentialError(f"Cannot store the API key in the OS credential store: {exc}") from exc

