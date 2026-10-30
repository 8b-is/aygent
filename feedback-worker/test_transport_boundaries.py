"""Offline transport failures are distinct from cancellation and coding defects."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import aiohttp
import pytest
import requests
import worker as module
from github import GithubException


@pytest.fixture
def worker(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "fake_token_for_testing")
    result = module.FeedbackWorker()
    result.gh = object()
    result.repo = object()
    return result


@pytest.mark.parametrize(
    "error",
    [
        GithubException(503, {"message": "synthetic"}),
        requests.ConnectionError("offline"),
        RuntimeError("bug"),
        AssertionError("bug"),
    ],
)
def test_github_setup_error_boundary(monkeypatch, error):
    monkeypatch.setenv("GITHUB_TOKEN", "synthetic-worker-key")
    github = Mock()
    github.return_value.get_repo.side_effect = error
    monkeypatch.setattr(module, "Github", github)
    if isinstance(error, (GithubException, requests.RequestException)):
        assert module.FeedbackWorker().repo is None
    else:
        with pytest.raises(type(error)):
            module.FeedbackWorker()


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [RuntimeError("bug"), asyncio.CancelledError()])
async def test_dispatch_unexpected_error_propagates(worker, error):
    worker.session = SimpleNamespace(post=Mock(side_effect=error))
    with pytest.raises(type(error)):
        await worker.trigger_ai_fix_dispatch(
            {"id": "synthetic", "category": "bug", "impact_score": 8}, 42
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        aiohttp.ClientConnectionError("offline"),
        TimeoutError("slow"),
        json.JSONDecodeError("bad", "?", 0),
        UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad"),
        RuntimeError("bug"),
        asyncio.CancelledError(),
    ],
)
async def test_pending_error_boundary(worker, error):
    response = SimpleNamespace(status=200, json=AsyncMock(side_effect=error))
    context = AsyncMock()
    context.__aenter__.return_value = response
    worker.session = SimpleNamespace(get=Mock(return_value=context))
    if isinstance(error, (RuntimeError, asyncio.CancelledError)):
        with pytest.raises(type(error)):
            await worker.fetch_pending_feedback()
    else:
        assert await worker.fetch_pending_feedback() == []
    context.__aexit__.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload", [None, {}, "bad", [None], ["bad"], [{"id": "ok"}, 5]]
)
async def test_pending_rejects_non_object_batches(worker, payload):
    response = SimpleNamespace(status=200, json=AsyncMock(return_value=payload))
    context = AsyncMock()
    context.__aenter__.return_value = response
    worker.session = SimpleNamespace(get=Mock(return_value=context))
    assert await worker.fetch_pending_feedback() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 403, 503])
async def test_pending_status_timeout_and_payload(worker, status):
    items = [{"id": "synthetic", "title": "Example"}]
    response = SimpleNamespace(status=status, json=AsyncMock(return_value=items))
    context = AsyncMock()
    context.__aenter__.return_value = response
    get = Mock(return_value=context)
    worker.session = SimpleNamespace(get=get)
    assert await worker.fetch_pending_feedback() == (items if status == 200 else [])
    assert get.call_args.kwargs["timeout"].total == 30
    assert get.call_args.args == (worker.feedback_api_url + "/feedback/pending",)
    if status != 200:
        response.json.assert_not_awaited()
    context.__aexit__.assert_awaited_once()
