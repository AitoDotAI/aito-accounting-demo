"""Tests for configuration loading.

Verifies that config fails loudly on missing variables — silent
defaults would hide real configuration errors.

All tests use use_dotenv=False to prevent the real .env file from
interfering with monkeypatched environment variables.
"""

import pytest

from src import config
from src.config import load_config


def test_load_config_from_environment(monkeypatch):
    monkeypatch.setenv("AITO_API_URL", "https://test.aito.app")
    monkeypatch.setenv("AITO_API_KEY", "test-key-123")

    config = load_config(use_dotenv=False)

    assert config.aito_api_url == "https://test.aito.app"
    assert config.aito_api_key == "test-key-123"


def test_load_config_strips_trailing_slash(monkeypatch):
    monkeypatch.setenv("AITO_API_URL", "https://test.aito.app/")
    monkeypatch.setenv("AITO_API_KEY", "test-key-123")

    config = load_config(use_dotenv=False)

    assert config.aito_api_url == "https://test.aito.app"


def test_load_config_fails_on_missing_url(monkeypatch):
    monkeypatch.delenv("AITO_API_URL", raising=False)
    monkeypatch.setenv("AITO_API_KEY", "test-key-123")

    with pytest.raises(ValueError, match="AITO_API_URL"):
        load_config(use_dotenv=False)


def test_load_config_fails_on_missing_key(monkeypatch):
    monkeypatch.setenv("AITO_API_URL", "https://test.aito.app")
    monkeypatch.delenv("AITO_API_KEY", raising=False)

    with pytest.raises(ValueError, match="AITO_API_KEY"):
        load_config(use_dotenv=False)


def test_load_config_fails_on_both_missing(monkeypatch):
    monkeypatch.delenv("AITO_API_URL", raising=False)
    monkeypatch.delenv("AITO_API_KEY", raising=False)

    with pytest.raises(ValueError, match="AITO_API_URL.*AITO_API_KEY"):
        load_config(use_dotenv=False)


def test_explicit_env_var_wins_over_dotenv(monkeypatch, tmp_path):
    # The 2026-09-20 incident: a loader run with AITO_API_URL pointing at
    # localhost had it silently replaced by the file's production URL.
    monkeypatch.setattr(config, "_PROJECT_ROOT", tmp_path)
    (tmp_path / ".env").write_text(
        "AITO_API_URL=https://shared.aito.ai/db/prod\nAITO_API_KEY=file-key\n")
    monkeypatch.setenv("AITO_API_URL", "http://localhost:8080")
    monkeypatch.setenv("AITO_API_KEY", "explicit-key")

    cfg = load_config()

    assert cfg.aito_api_url == "http://localhost:8080"
    assert cfg.aito_api_key == "explicit-key"


def test_dotenv_fills_unset_and_empty_variables(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "_PROJECT_ROOT", tmp_path)
    (tmp_path / ".env").write_text(
        "AITO_API_URL=https://shared.aito.ai/db/demo\nAITO_API_KEY=file-key\n")
    monkeypatch.delenv("AITO_API_URL", raising=False)
    monkeypatch.setenv("AITO_API_KEY", "")  # a blank export must not shadow the file

    cfg = load_config()

    assert cfg.aito_api_url == "https://shared.aito.ai/db/demo"
    assert cfg.aito_api_key == "file-key"
