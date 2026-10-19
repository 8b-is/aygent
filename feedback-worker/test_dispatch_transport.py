"""Dispatch transport stays asynchronous and never contacts GitHub in tests."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import aiohttp
import pytest
from worker import FeedbackWorker


@pytest.fixture
def dispatcher(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "fake_token_for_testing")
    monkeypatch.setenv("GITHUB_REPO", "test/repo")
    worker = FeedbackWorker()
    worker.gh = object()
    worker.repo = object()
    return worker


@pytest.fixture
def feedback():
    return {"id": "synthetic123", "category": "bug", "impact_score": 8, "title": "Test"}


@pytest.mark.asyncio
@pytest.mark.parametrize("status,expected", [(204, True), (403, False), (500, False)])
async def test_dispatch_status_and_request_contract(
    dispatcher, feedback, status, expected
):
    @asynccontextmanager
    async def response():
        yield SimpleNamespace(status=status)

    post = Mock(side_effect=lambda *args, **kwargs: response())
    dispatcher.session = SimpleNamespace(post=post)
    assert await dispatcher.trigger_ai_fix_dispatch(feedback, 42) is expected
    args, kwargs = post.call_args
    assert args == ("https://api.github.com/repos/test/repo/dispatches",)
    assert kwargs["timeout"].total == 30
    assert kwargs["headers"]["Authorization"] == "token fake_token_for_testing"
    assert kwargs["json"]["event_type"] == "ai_fix_dispatch"
    assert kwargs["json"]["client_payload"]["issue_number"] == 42
    assert kwargs["json"]["client_payload"]["feedback_id"] == "synthetic123"


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [aiohttp.ClientConnectionError, TimeoutError])
async def test_dispatch_network_failure_returns_false(dispatcher, feedback, error):
    @asynccontextmanager
    async def response():
        raise error("synthetic failure")
        yield  # pragma: no cover

    dispatcher.session = SimpleNamespace(post=lambda *args, **kwargs: response())
    assert await dispatcher.trigger_ai_fix_dispatch(feedback, 42) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["no-github", "wrong-category", "low-impact"])
async def test_ineligible_feedback_never_dispatches(dispatcher, feedback, reason):
    if reason == "no-github":
        dispatcher.gh = None
    elif reason == "wrong-category":
        feedback["category"] = "enhancement"
    else:
        feedback["impact_score"] = 6
    post = Mock()
    dispatcher.session = SimpleNamespace(post=post)
    assert await dispatcher.trigger_ai_fix_dispatch(feedback, 42) is False
    post.assert_not_called()


@pytest.mark.asyncio
async def test_pending_dispatch_yields_to_other_tasks(dispatcher, feedback):
    started = asyncio.Event()
    release = asyncio.Event()
    closed = asyncio.Event()

    @asynccontextmanager
    async def response():
        started.set()
        try:
            await release.wait()
            yield SimpleNamespace(status=204)
        finally:
            closed.set()

    dispatcher.session = SimpleNamespace(post=lambda *args, **kwargs: response())
    task = asyncio.create_task(dispatcher.trigger_ai_fix_dispatch(feedback, 42))
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        assert not task.done()
        # This coroutine runs while the HTTP response remains pending.
        release.set()
        assert await asyncio.wait_for(task, timeout=1) is True
        assert closed.is_set()
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_dispatch_cancellation_releases_transport(dispatcher, feedback):
    started = asyncio.Event()
    closed = asyncio.Event()

    @asynccontextmanager
    async def response():
        started.set()
        try:
            await asyncio.Event().wait()
            yield SimpleNamespace(status=204)
        finally:
            closed.set()

    dispatcher.session = SimpleNamespace(post=lambda *args, **kwargs: response())
    task = asyncio.create_task(dispatcher.trigger_ai_fix_dispatch(feedback, 42))
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert closed.is_set()
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_dispatch_without_session_is_disabled(dispatcher, feedback):
    assert dispatcher.session is None
    assert await dispatcher.trigger_ai_fix_dispatch(feedback, 42) is False
