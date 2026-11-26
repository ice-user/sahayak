"""Deployment-facing behaviour: startup log about the LLM provider, HEAD health probe, production guard."""
import logging

import pytest
from fastapi.testclient import TestClient

from server.config import Settings
from server.main import create_app, log_startup_summary
from sahayak.tools import Toolbox

KEYS = ["LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "NVIDIA_API_KEY", "NVIDIA_MODEL"]


@pytest.fixture
def clean_env(monkeypatch):
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


def test_missing_key_logs_a_clear_warning_and_does_not_crash(clean_env, caplog):
    with caplog.at_level(logging.INFO, logger="sahayak.server"):
        app = create_app(settings=Settings())  # no injection: the production path
    assert any("NO LLM PROVIDER CONFIGURED" in r.message and "NVIDIA_API_KEY" in r.message and r.levelno == logging.WARNING
               for r in caplog.records)
    assert TestClient(app).get("/api/health").json()["ok"] is True


def test_configured_key_is_logged_without_the_secret(clean_env, caplog):
    clean_env.setenv("NVIDIA_API_KEY", "nvapi-super-secret-value")
    with caplog.at_level(logging.INFO, logger="sahayak.server"):
        log_startup_summary(Settings(), Toolbox(search_mode="bm25"))
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "LLM provider configured" in text and "NO LLM PROVIDER" not in text
    assert "nvapi-super-secret-value" not in text


def test_health_accepts_head_for_uptime_monitors():
    client = TestClient(create_app(settings=Settings()))
    assert client.head("/api/health").status_code == 200


def test_production_requires_allowed_origins(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    with pytest.raises(RuntimeError, match="ALLOWED_ORIGINS"):
        Settings.from_env()
