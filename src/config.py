"""Configuration loaded from environment variables.

Fails loudly if required Aito credentials are missing — silent defaults
would hide configuration errors in a demo that's meant to teach.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values


@dataclass(frozen=True)
class Config:
    aito_api_url: str
    aito_api_key: str


_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Fill the environment from a dotenv file without overriding it.

    A variable the caller set wins over the file, so
    `AITO_API_URL=http://localhost:8080 ./do load-data` really reaches the
    local engine. This used `load_dotenv(override=True)`, where the file
    won: on 2026-09-20 a loader run pointed at localhost silently wrote to
    the production instance (shared.aito.ai) instead.

    An empty variable counts as unset, so a blank export still picks up
    the file's value rather than shadowing it.
    """
    for key, value in dotenv_values(path).items():
        if value is not None and not os.environ.get(key):
            os.environ[key] = value


def load_config(*, use_dotenv: bool = True) -> Config:
    """Load config from environment, with .env file fallback.

    An explicitly set environment variable wins over .env.

    Raises ValueError with a clear message if required variables are
    missing — never returns partial config.

    Set use_dotenv=False in tests to prevent .env from interfering
    with monkeypatched environment variables.
    """
    if use_dotenv:
        _load_dotenv(_PROJECT_ROOT / ".env")

    aito_api_url = os.environ.get("AITO_API_URL", "").rstrip("/")
    aito_api_key = os.environ.get("AITO_API_KEY", "")

    missing = []
    if not aito_api_url:
        missing.append("AITO_API_URL")
    if not aito_api_key:
        missing.append("AITO_API_KEY")

    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}. "
            f"Copy .env.example to .env and fill in your Aito credentials."
        )

    return Config(aito_api_url=aito_api_url, aito_api_key=aito_api_key)
