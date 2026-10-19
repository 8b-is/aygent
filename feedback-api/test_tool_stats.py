"""Offline persistence, concurrency and event-loop coverage for usage statistics."""

import asyncio
import builtins
import json
import threading
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

import httpx
import main
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def stats_store(tmp_path, monkeypatch):
    stats = tmp_path / "stats"
    feedback = tmp_path / "feedback"
    stats.mkdir()
    feedback.mkdir()
    monkeypatch.setattr(main, "STATS_DIR", stats)
    monkeypatch.setattr(main, "FEEDBACK_DIR", feedback)
    monkeypatch.setattr(
        main,
        "tool_stats_cache",
        defaultdict(
            lambda: {"count": 0, "models": defaultdict(int), "last_used": None}
        ),
    )
    return stats


def usage(model="vendor:synthetic", count=1):
    return {
        "tool_name": "synthetic",
        "model_type": model,
        "usage_count": count,
        "success_rate": 1,
        "timestamp": "2026-10-19T16:00:00Z",
    }


def test_usage_persists_and_aggregates(stats_store):
    with TestClient(main.app) as client:
        for payload in [usage(count=2), usage("other", 3)]:
            result = client.post("/tools/usage", json=payload)
            assert result.status_code == 200
            assert result.json() == {"message": "Stats recorded", "tool": "synthetic"}
        popular = client.get("/tools/popular").json()
        activity = client.get("/stats/model-activity").json()
    files = list(stats_store.glob("tool_stats_*.json"))
    assert len(files) == 1
    stored = json.loads(files[0].read_text())["synthetic"]
    assert stored["count"] == 5
    assert stored["models"] == {"vendor:synthetic": 2, "other": 3}
    assert popular["total_unique_tools"] == 1
    assert popular["tools"][0]["total_uses"] == 5
    assert popular["tools"][0]["top_models"] == {"other": 3, "vendor:synthetic": 2}
    assert activity["models"]["vendor:synthetic"]["tools_used"] == {"synthetic": 2}


def test_failed_write_keeps_file_and_cache(stats_store, monkeypatch):
    with TestClient(main.app, raise_server_exceptions=False) as client:
        assert client.post("/tools/usage", json=usage(count=2)).status_code == 200
        target = next(stats_store.glob("tool_stats_*.json"))
        before = target.read_bytes()

        def fail_dump(*args, **kwargs):
            raise OSError("synthetic serialization failure")

        monkeypatch.setattr(main.json, "dump", fail_dump)
        monkeypatch.setattr(main.json, "dumps", fail_dump)
        # Send encoded content so the test client's encoder is unaffected.
        response = client.post(
            "/tools/usage",
            content='{"tool_name":"synthetic","model_type":"other","success_rate":1}',
            headers={"Content-Type": "application/json"},
        )
    assert response.status_code == 500
    assert target.read_bytes() == before
    assert main.tool_stats_cache["synthetic"]["count"] == 2
    assert dict(main.tool_stats_cache["synthetic"]["models"]) == {"vendor:synthetic": 2}
    assert list(stats_store.iterdir()) == [target]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "route", ["/tools/usage", "/stats/model-activity", "/llm/assist"]
)
async def test_stats_io_runs_off_loop(stats_store, monkeypatch, route):
    loop_thread = threading.get_ident()
    observed = []

    def observe(method):
        def call(path, *args, **kwargs):
            if isinstance(path, (str, Path)) and (
                Path(path).parent == stats_store or Path(path) == main.FEEDBACK_DIR
            ):
                observed.append(threading.get_ident())
            return method(path, *args, **kwargs)

        return call

    monkeypatch.setattr(builtins, "open", observe(builtins.open))
    monkeypatch.setattr(Path, "open", observe(Path.open))
    monkeypatch.setattr(Path, "glob", observe(Path.glob))

    async def assist(task):
        return main.LLMResponse(
            task_id="synthetic",
            model_used="synthetic",
            response="Offline reply",
            tokens_used=1,
            cost_estimate=0,
        )

    monkeypatch.setattr(main, "get_assistant", lambda: SimpleNamespace(assist=assist))
    agent = main.AGENT_KEYS["agent_claude_001"]
    monkeypatch.setitem(
        main.AGENT_KEYS,
        "agent_claude_001",
        {**agent, "permissions": [*agent["permissions"], "llm.query"]},
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url="http://test"
    ) as client:
        if route == "/tools/usage":
            response = await client.post(route, json=usage())
        elif route == "/llm/assist":
            response = await client.post(
                route,
                json={
                    "task_type": "documentation",
                    "context": "synthetic",
                    "request": "synthetic",
                },
                headers={"X-API-Key": "agent_claude_001:synthetic-api-test-key"},
            )
        else:
            response = await client.get(route)
    assert response.status_code == 200
    assert observed and all(t != loop_thread for t in observed)


@pytest.mark.asyncio
async def test_concurrent_usage_preserves_all_counts(stats_store):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url="http://test"
    ) as client:
        responses = await asyncio.gather(
            *(
                client.post("/tools/usage", json=usage(f"model:{i % 2}"))
                for i in range(20)
            )
        )
        assert all(r.status_code == 200 for r in responses)
        popular = (await client.get("/tools/popular")).json()
    stored = json.loads(next(stats_store.glob("tool_stats_*.json")).read_text())[
        "synthetic"
    ]
    assert stored["count"] == 20
    assert stored["models"] == {"model:0": 10, "model:1": 10}
    assert popular["tools"][0]["total_uses"] == 20


@pytest.mark.parametrize("incomplete_first", [True, False])
def test_incomplete_summary_does_not_reuse_previous_identity(
    stats_store, monkeypatch, incomplete_first
):
    date = main.FEEDBACK_DIR / "2026-10-19"
    date.mkdir()
    valid = date / "valid.summary.txt"
    invalid = date / "invalid.summary.txt"
    valid.write_text("Model: vendor:synthetic\nCategory: bug\n")
    invalid.write_text("Category: critical\n")
    original = Path.glob

    def ordered(path, pattern):
        if path == date and pattern == "*.summary.txt":
            return iter([invalid, valid] if incomplete_first else [valid, invalid])
        return original(path, pattern)

    monkeypatch.setattr(Path, "glob", ordered)
    with TestClient(main.app, raise_server_exceptions=False) as client:
        response = client.get("/stats/model-activity")
    assert response.status_code == 200
    assert response.json()["models"] == {
        "vendor:synthetic": {
            "feedback_submitted": 1,
            "tools_used": {},
            "categories": {"bug": 1},
        }
    }
