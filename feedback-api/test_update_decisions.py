"""Offline tests for daily update-decision persistence."""

import asyncio
import builtins
import json
import threading
from pathlib import Path

import httpx
import main
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def decision_store(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "STATS_DIR", tmp_path)
    return tmp_path


def payload(decision="update", model="synthetic"):
    return {
        "current_version": "1.0.0",
        "latest_version": "1.0.1",
        "user_decision": decision,
        "ai_model": model,
    }


@pytest.mark.parametrize(
    "decision,next_step",
    [
        ("update", "Run the auto-update command provided"),
        ("skip", "You can update manually anytime"),
        ("remind_later", "We'll remind you in 7 days"),
    ],
)
def test_decision_format_and_reply_remain_compatible(
    decision_store, decision, next_step
):
    with TestClient(main.app) as client:
        response = client.post("/version/notify-update", json=payload(decision))
    assert response.status_code == 200
    assert response.json() == {"message": "Decision recorded", "next_steps": next_step}
    files = list(decision_store.glob("update_decisions_*.json"))
    assert len(files) == 1
    stored = json.loads(files[0].read_text())
    assert len(stored) == 1
    assert {k: v for k, v in stored[0].items() if k != "timestamp"} == {
        "current_version": "1.0.0",
        "latest_version": "1.0.1",
        "decision": decision,
        "ai_model": "synthetic",
    }
    assert " " in stored[0]["timestamp"] and stored[0]["timestamp"].endswith("+00:00")


def test_failed_update_preserves_prior_file(decision_store, monkeypatch):
    with TestClient(main.app, raise_server_exceptions=False) as client:
        assert client.post("/version/notify-update", json=payload()).status_code == 200
        target = next(decision_store.glob("*.json"))
        previous = target.read_bytes()

        def fail(*args, **kwargs):
            raise OSError("synthetic serialization failure")

        monkeypatch.setattr(main.json, "dump", fail)
        monkeypatch.setattr(main.json, "dumps", fail)
        response = client.post(
            "/version/notify-update",
            content='{"current_version":"1.0.0","latest_version":"1.0.1","user_decision":"skip","ai_model":"synthetic"}',
            headers={"Content-Type": "application/json"},
        )
    assert response.status_code == 500
    assert target.read_bytes() == previous
    assert list(decision_store.iterdir()) == [target]


@pytest.mark.asyncio
async def test_decision_disk_io_runs_off_loop(decision_store, monkeypatch):
    loop_thread = threading.get_ident()
    observed = []

    def observe(method):
        def opened(path, *args, **kwargs):
            if isinstance(path, (str, Path)) and Path(path).parent == decision_store:
                observed.append(threading.get_ident())
            return method(path, *args, **kwargs)

        return opened

    monkeypatch.setattr(builtins, "open", observe(builtins.open))
    monkeypatch.setattr(Path, "open", observe(Path.open))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url="http://test"
    ) as client:
        first = await client.post("/version/notify-update", json=payload())
        second = await client.post("/version/notify-update", json=payload("skip"))
    assert first.status_code == second.status_code == 200
    assert observed and all(t != loop_thread for t in observed)


@pytest.mark.asyncio
async def test_concurrent_decisions_all_survive(decision_store):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url="http://test"
    ) as client:
        responses = await asyncio.gather(
            *(
                client.post(
                    "/version/notify-update", json=payload(model=f"synthetic-{i}")
                )
                for i in range(20)
            )
        )
    assert all(r.status_code == 200 for r in responses)
    stored = json.loads(next(decision_store.glob("*.json")).read_text())
    assert len(stored) == 20
    assert {entry["ai_model"] for entry in stored} == {
        f"synthetic-{i}" for i in range(20)
    }
