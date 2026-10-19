"""Synthetic cache and admin storage checks; no model service is contacted."""

import builtins
import json
import os
import threading
import time
from pathlib import Path

import auth
import httpx
import jwt
import llm_assistant as llm
import main
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def storage_dirs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    directories = {}
    for key in ["FEEDBACK_DIR", "LLM_CACHE_DIR"]:
        directory = tmp_path / key
        directory.mkdir()
        monkeypatch.setenv(key, str(directory))
        directories[key] = directory
    monkeypatch.setattr(llm, "CACHE_DIR", directories["LLM_CACHE_DIR"])
    return directories


def admin_headers(permission="admin.read"):
    token = jwt.encode(
        {
            "sub": "synthetic",
            "permissions": [permission],
            "exp": int(time.time()) + 120,
        },
        auth.JWT_SECRET,
        algorithm="HS256",
    )
    return {"Authorization": "Bearer " + token}


def cached_response():
    return llm.LLMResponse(
        task_id="synthetic",
        model_used="synthetic",
        response="Synthetic reply",
        tokens_used=1,
        cost_estimate=0,
        timestamp="2026-10-19T16:00:00Z",
    )


@pytest.mark.parametrize(
    "age,valid", [(10, True), (3590, True), (3610, False), (86410, False), (-60, False)]
)
def test_cache_expiry_does_not_wrap_at_day_boundaries(storage_dirs, age, valid):
    assistant = llm.SmartTreeAssistant.__new__(llm.SmartTreeAssistant)
    target = llm.CACHE_DIR / "synthetic.json"
    target.write_text(cached_response().model_dump_json())
    timestamp = time.time() - age
    os.utime(target, (timestamp, timestamp))
    result = assistant._get_cached_response("synthetic")
    assert (result is not None) is valid
    if valid:
        assert result.cached is True
        assert result.response == "Synthetic reply"


def test_missing_cache_is_a_miss(storage_dirs):
    assistant = llm.SmartTreeAssistant.__new__(llm.SmartTreeAssistant)
    assert assistant._get_cached_response("missing") is None


def test_cache_publication_preserves_prior_file_on_replace_failure(
    storage_dirs, monkeypatch
):
    assistant = llm.SmartTreeAssistant.__new__(llm.SmartTreeAssistant)
    target = llm.CACHE_DIR / "synthetic.json"
    target.write_text('{"previous": true}')
    previous = target.read_bytes()

    def fail_replace(source, destination):
        assert target.read_bytes() == previous
        assert json.loads(source.read_bytes())["response"] == "Synthetic reply"
        raise OSError("synthetic replacement failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="synthetic replacement failure"):
        assistant._save_to_cache("synthetic", cached_response())
    assert target.read_bytes() == previous
    assert list(llm.CACHE_DIR.iterdir()) == [target]


@pytest.mark.asyncio
async def test_assist_cache_hit_and_miss_io_runs_off_loop(storage_dirs, monkeypatch):
    loop_thread = threading.get_ident()
    observed = []

    def observe(method):
        def opened(path, *args, **kwargs):
            if isinstance(path, (str, Path)) and Path(path).parent == llm.CACHE_DIR:
                observed.append(threading.get_ident())
            return method(path, *args, **kwargs)

        return opened

    monkeypatch.setattr(builtins, "open", observe(builtins.open))
    monkeypatch.setattr(Path, "open", observe(Path.open))
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Synthetic reply"}}],
                "usage": {"total_tokens": 1},
            },
        )

    assistant = llm.SmartTreeAssistant.__new__(llm.SmartTreeAssistant)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://model.invalid"
    ) as client:
        assistant.client = client
        task = llm.SmartTreeTask(
            task_type="documentation", context="synthetic", request="synthetic"
        )
        first = await assistant.assist(task)
        second = await assistant.assist(task)
    assert len(requests) == 1 and first.cached is False and second.cached is True
    assert first.response == second.response == "Synthetic reply"
    assert observed and all(t != loop_thread for t in observed)


@pytest.mark.parametrize("route", ["/admin/api/feedback", "/admin/api/llm/tasks"])
@pytest.mark.parametrize(
    "permission,status", [("admin.read", 200), ("feedback.read", 403)]
)
def test_admin_uses_configured_storage_and_preserves_auth(
    storage_dirs, route, permission, status
):
    date = storage_dirs["FEEDBACK_DIR"] / "2026-10-19"
    date.mkdir()
    (date / "synthetic.summary.txt").write_text(
        "Title: Synthetic title\nModel: vendor:synthetic\nCategory: bug\nImpact: malformed\n"
    )
    (llm.CACHE_DIR / "synthetic.json").write_text(cached_response().model_dump_json())
    with TestClient(main.app) as client:
        response = client.get(route, headers=admin_headers(permission))
    assert response.status_code == status
    if status == 200:
        data = response.json()
        assert len(data) == 1
        if route.endswith("feedback"):
            assert data[0]["ai_model"] == "vendor:synthetic"
            assert data[0]["impact_score"] == 5
        else:
            assert data[0]["model"] == "synthetic" and data[0]["tokens"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "route,key",
    [
        ("/admin/api/feedback", "FEEDBACK_DIR"),
        ("/admin/api/llm/tasks", "LLM_CACHE_DIR"),
    ],
)
async def test_admin_directory_scans_run_off_loop(
    storage_dirs, monkeypatch, route, key
):
    observed = []
    loop_thread = threading.get_ident()
    original = Path.exists

    def exists(path):
        if path == storage_dirs[key] or path.name in ["feedback", "llm_cache"]:
            observed.append(threading.get_ident())
        return original(path)

    monkeypatch.setattr(Path, "exists", exists)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url="http://test"
    ) as client:
        response = await client.get(route, headers=admin_headers())
    assert response.status_code == 200
    assert observed and all(t != loop_thread for t in observed)


def test_admin_skips_invalid_cache_records(storage_dirs):
    for name, value in [
        ("invalid", "not JSON"),
        ("list", "[]"),
        ("valid", cached_response().model_dump_json()),
    ]:
        (llm.CACHE_DIR / (name + ".json")).write_text(value)
    with TestClient(main.app) as client:
        response = client.get("/admin/api/llm/tasks", headers=admin_headers())
    assert response.status_code == 200
    assert len(response.json()) == 1 and response.json()[0]["model"] == "synthetic"
