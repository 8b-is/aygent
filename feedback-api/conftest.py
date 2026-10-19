"""Temporary API test storage and synthetic identity; never use live services."""

import os
import socket
import tempfile
from pathlib import Path

import pytest

_STORAGE = tempfile.TemporaryDirectory(prefix="aygent-api-tests-")
for name in ("FEEDBACK_DIR", "STATS_DIR", "CONSENT_DIR", "LLM_CACHE_DIR"):
    directory = Path(_STORAGE.name) / name
    directory.mkdir()
    os.environ[name] = str(directory)
os.environ["AGENT_CLAUDE_KEY"] = "synthetic-api-test-key"
os.environ["JWT_SECRET"] = "synthetic-jwt-test-key-not-for-deployment"
for name in (
    "OPENROUTER_API_KEY",
    "SMART_TREE_FIX_WEBHOOK",
    "GITHUB_WEBHOOK_SECRET",
    "ADMIN_PASSWORD",
    "HUE_PASSWORD",
):
    os.environ.pop(name, None)


@pytest.fixture(autouse=True)
def isolated_services(monkeypatch):
    import auth

    monkeypatch.setattr(auth, "redis_client", None)
    auth.rate_limit_cache.clear()
    attempts = []

    def guarded(method):
        def connect(sock, address):
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                attempts.append(address)
                raise AssertionError("API tests must mock network connections")
            return method(sock, address)

        return connect

    monkeypatch.setattr(socket.socket, "connect", guarded(socket.socket.connect))
    monkeypatch.setattr(socket.socket, "connect_ex", guarded(socket.socket.connect_ex))
    yield
    assert not attempts, "An API test attempted a network connection"


def pytest_sessionfinish(session, exitstatus):
    _STORAGE.cleanup()
