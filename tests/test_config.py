"""Tests for configuration loading.

Verifies that config fails loudly on missing variables — silent
defaults would hide real configuration errors.

All tests use use_dotenv=False to prevent the real .env file from
interfering with monkeypatched environment variables.
"""

import pytest

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
