"""Offline announcement durability, restart and concurrency checks."""

import asyncio
import builtins
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import httpx
import main
import pytest
import storage
from fastapi.testclient import TestClient
from test_announcement_auth import headers


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "STATS_DIR", tmp_path)
    monkeypatch.setattr(main, "announcements_cache", {})
    return tmp_path / "announcements.json"


def notice(identifier, **changes):
    return {
        "id": identifier,
        "title": "Synthetic notice",
        "message": "Synthetic body",
        "priority": "info",
        **changes,
    }


def seed(store):
    value = main.Announcement(**notice("existing"))
    store.write_text(json.dumps({"existing": value.model_dump(mode="json")}))
    main.announcements_cache["existing"] = value


def test_stored_notices_survive_new_process(store, tmp_path):
    with TestClient(main.app) as client:
        for identifier in ("active", "inactive"):
            assert (
                client.post(
                    "/announcements", json=notice(identifier), headers=headers("write")
                ).status_code
                == 200
            )
        assert (
            client.delete(
                "/announcements/inactive", headers=headers("write")
            ).status_code
            == 200
        )
    output = tmp_path / "restart-result.json"
    script = """
import json, socket, sys
from pathlib import Path
original_connect = socket.socket.connect
def guarded(sock, address):
    if sock.family in (socket.AF_INET, socket.AF_INET6):
        raise AssertionError('No network in restart test')
    return original_connect(sock, address)
socket.socket.connect = guarded
import main
from fastapi.testclient import TestClient
with TestClient(main.app) as client:
    response = client.get('/announcements')
    assert response.status_code == 200
Path(sys.argv[1]).write_text(json.dumps(response.json()))
"""
    subprocess.run(
        [sys.executable, "-c", script, str(output)],
        env={**os.environ, "STATS_DIR": str(store.parent)},
        check=True,
        timeout=20,
        capture_output=True,
    )
    ids = {item["id"] for item in json.loads(output.read_text())["announcements"]}
    assert "active" in ids and "inactive" not in ids
    assert json.loads(store.read_text())["inactive"]["active"] is False


@pytest.mark.parametrize("operation", ["create", "deactivate"])
def test_failed_write_preserves_store_and_cache(store, monkeypatch, operation):
    seed(store)
    previous = store.read_bytes()
    authorization = headers("write")
    cached = {key: item.model_dump() for key, item in main.announcements_cache.items()}

    def fail(*args, **kwargs):
        raise OSError("synthetic serialization failure")

    monkeypatch.setattr(main.json, "dump", fail)
    monkeypatch.setattr(main.json, "dumps", fail)
    with TestClient(main.app, raise_server_exceptions=False) as client:
        if operation == "create":
            response = client.post(
                "/announcements",
                content='{"id":"new","title":"Synthetic","message":"Body","priority":"info"}',
                headers={**authorization, "Content-Type": "application/json"},
            )
        else:
            response = client.delete("/announcements/existing", headers=authorization)
    assert response.status_code == 500
    assert store.read_bytes() == previous
    assert {
        key: item.model_dump() for key, item in main.announcements_cache.items()
    } == cached


def test_default_deactivation_survives_cold_cache(store, monkeypatch):
    with TestClient(main.app) as client:
        defaults = client.get("/announcements").json()
        assert {item["id"] for item in defaults["announcements"]} == {
            "welcome",
            "hot_tub",
            "trisha_tips",
        }
        assert (
            client.delete(
                "/announcements/welcome", headers=headers("write")
            ).status_code
            == 200
        )
        monkeypatch.setattr(main, "announcements_cache", {})
        assert "welcome" not in {
            item["id"] for item in client.get("/announcements").json()["announcements"]
        }
    assert json.loads(store.read_text())["welcome"]["active"] is False


def test_explicit_empty_store_stays_empty(store):
    store.write_text("{}")
    with TestClient(main.app) as client:
        assert client.get("/announcements").json()["announcements"] == []


def test_failed_replacement_keeps_old_file_and_cache(store, monkeypatch):
    seed(store)
    previous = store.read_bytes()

    def fail(*args):
        raise OSError("synthetic replacement failure")

    monkeypatch.setattr(storage.os, "replace", fail)
    with TestClient(main.app, raise_server_exceptions=False) as client:
        assert (
            client.delete(
                "/announcements/existing", headers=headers("write")
            ).status_code
            == 500
        )
    assert store.read_bytes() == previous
    assert main.announcements_cache["existing"].active is True
    assert list(store.parent.iterdir()) == [store]


def test_persisted_filtering_and_missing_id(store):
    values = [
        notice("matching", priority="important", targets=["synthetic"]),
        notice("all", priority="important"),
        notice("expired", priority="important", expires_at="2000-01-01T00:00:00Z"),
        notice("inactive", priority="important", active=False),
        notice("different-model", priority="important", targets=["other"]),
        notice("different-priority"),
    ]
    store.write_text(json.dumps({item["id"]: item for item in values}))
    previous = store.read_bytes()
    with TestClient(main.app) as client:
        response = client.get("/announcements?ai_model=synthetic&priority=important")
        assert response.status_code == 200
        assert {item["id"] for item in response.json()["announcements"]} == {
            "matching",
            "all",
        }
        assert (
            client.delete(
                "/announcements/missing", headers=headers("write")
            ).status_code
            == 404
        )
    assert store.read_bytes() == previous


@pytest.mark.parametrize("invalid", ['{"broken":', '{"broken":{}}', "[]"])
def test_invalid_store_is_not_overwritten(store, invalid):
    store.write_text(invalid)
    with TestClient(main.app, raise_server_exceptions=False) as client:
        assert client.get("/announcements").status_code == 500
        assert (
            client.post(
                "/announcements", json=notice("new"), headers=headers("write")
            ).status_code
            == 500
        )
    assert store.read_text() == invalid
    assert main.announcements_cache == {}


@pytest.mark.asyncio
async def test_announcement_disk_io_runs_off_loop(store, monkeypatch):
    seed(store)
    observed = []
    loop_thread = threading.get_ident()

    def observe(method):
        def opened(path, *args, **kwargs):
            if isinstance(path, (str, Path)) and Path(path).parent == store.parent:
                observed.append(threading.get_ident())
            return method(path, *args, **kwargs)

        return opened

    monkeypatch.setattr(builtins, "open", observe(builtins.open))
    monkeypatch.setattr(Path, "open", observe(Path.open))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url="http://test"
    ) as client:
        for method, url, kwargs in [
            ("get", "/announcements", {}),
            (
                "post",
                "/announcements",
                {"json": notice("new"), "headers": headers("write")},
            ),
            ("delete", "/announcements/new", {"headers": headers("write")}),
        ]:
            assert (await client.request(method, url, **kwargs)).status_code == 200
    assert observed and all(identifier != loop_thread for identifier in observed)


@pytest.mark.asyncio
async def test_concurrent_creates_and_deactivations_survive(store):
    store.write_text("{}")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url="http://test"
    ) as client:
        created = await asyncio.gather(
            *(
                client.post(
                    "/announcements", json=notice(f"item-{i}"), headers=headers("write")
                )
                for i in range(20)
            )
        )
        assert all(response.status_code == 200 for response in created)
        removed = await asyncio.gather(
            *(
                client.delete(f"/announcements/item-{i}", headers=headers("write"))
                for i in range(0, 20, 2)
            )
        )
        assert all(response.status_code == 200 for response in removed)
        visible = (await client.get("/announcements")).json()["announcements"]
    stored = json.loads(store.read_text())
    assert len(stored) == 20
    assert (
        {key for key, item in stored.items() if item["active"]}
        == {f"item-{i}" for i in range(1, 20, 2)}
        == {item["id"] for item in visible}
    )
