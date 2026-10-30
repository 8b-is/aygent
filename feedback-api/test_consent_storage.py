"""Consent persistence must not escape its directory or publish failed writes."""

import builtins
import json
import threading
from pathlib import Path

import httpx
import main
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def consent_store(tmp_path, monkeypatch):
    directory = tmp_path / "consent"
    directory.mkdir()
    monkeypatch.setattr(main, "CONSENT_DIR", directory)
    monkeypatch.setattr(main, "consent_cache", {})
    return directory


@pytest.mark.parametrize(
    "user_id", ["../escaped", "nested/user", "nested\\user", "nul\x00id"]
)
def test_rejects_path_identifiers_before_storage(consent_store, user_id):
    with TestClient(main.app, raise_server_exceptions=False) as client:
        response = client.post(
            "/consent/set", json={"user_id": user_id, "consent_level": "never"}
        )
    assert response.status_code == 422
    assert not main.consent_cache
    assert list(consent_store.parent.iterdir()) == [consent_store]
    assert not list(consent_store.iterdir())


def test_rejects_absolute_path_inside_synthetic_fixture(consent_store):
    with TestClient(main.app) as client:
        response = client.post(
            "/consent/set",
            json={
                "user_id": str(consent_store.parent / "absolute"),
                "consent_level": "never",
            },
        )
    assert response.status_code == 422
    assert list(consent_store.parent.iterdir()) == [consent_store]
    assert not main.consent_cache


@pytest.mark.parametrize(
    "key,url", [("nested\\user", "nested%5Cuser"), ("nul\x00id", "nul%00id")]
)
def test_read_validation_cannot_be_bypassed_by_cached_entry(consent_store, key, url):
    main.consent_cache[key] = main.ConsentRequest(user_id="safe", consent_level="never")
    with TestClient(main.app) as client:
        response = client.get(f"/consent/check/{url}")
    assert response.status_code == 422


@pytest.mark.parametrize("user_id", ["hue123", "synthetic@example.test", "café", None])
def test_safe_identifiers_and_legacy_files_round_trip(consent_store, user_id):
    key = user_id or "anonymous"
    with TestClient(main.app) as client:
        response = client.post(
            "/consent/set", json={"user_id": user_id, "consent_level": "never"}
        )
        assert response.status_code == 200
        stored = json.loads((consent_store / f"{key}.json").read_text())
        main.consent_cache.clear()
        response = client.get(f"/consent/check/{key}")
    assert response.status_code == 200
    assert response.json() == stored
    assert response.json()["consent_level"] == "never"


def test_failed_write_preserves_previous_cached_preference(consent_store):
    main.consent_cache["synthetic"] = main.ConsentRequest(
        user_id="synthetic", consent_level="never"
    )
    # An existing directory cannot be replaced by a JSON file.
    (consent_store / "synthetic.json").mkdir()
    with TestClient(main.app, raise_server_exceptions=False) as client:
        response = client.post(
            "/consent/set",
            json={"user_id": "synthetic", "consent_level": "always_credited"},
        )
    assert response.status_code == 500
    assert main.consent_cache["synthetic"].consent_level == "never"
    assert [p.name for p in consent_store.iterdir()] == ["synthetic.json"]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["read", "write"])
async def test_consent_disk_io_runs_off_loop(consent_store, monkeypatch, operation):
    payload = {"user_id": "synthetic", "consent_level": "never"}
    (consent_store / "synthetic.json").write_text(json.dumps(payload))
    loop_thread = threading.get_ident()
    io_threads = []

    def observe(method):
        def open_file(file, *args, **kwargs):
            if isinstance(file, (str, Path)) and Path(file).parent == consent_store:
                io_threads.append(threading.get_ident())
            return method(file, *args, **kwargs)

        return open_file

    monkeypatch.setattr(builtins, "open", observe(builtins.open))
    monkeypatch.setattr(Path, "open", observe(Path.open))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url="http://test"
    ) as client:
        response = (
            await client.post("/consent/set", json=payload)
            if operation == "write"
            else await client.get("/consent/check/synthetic")
        )
    assert response.status_code == 200
    assert io_threads and all(thread != loop_thread for thread in io_threads)
