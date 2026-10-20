"""Offline worker timestamp and successive-batch concurrency checks."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest
import worker as module


@pytest.fixture
def worker(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "fake_token_for_testing")
    instance = module.FeedbackWorker()
    instance.redis = AsyncMock()
    return instance


@pytest.mark.asyncio
async def test_processed_timestamp_has_explicit_utc(worker):
    worker.create_github_issue = AsyncMock(return_value=42)
    worker.trigger_ai_fix_dispatch = AsyncMock(return_value=False)
    response = AsyncMock()
    response.status = 200
    context = AsyncMock()
    context.__aenter__.return_value = response
    worker.session = Mock()
    worker.session.post.return_value = context
    before = datetime.now(UTC)
    result = await worker.process_feedback({"id": "synthetic", "title": "Example"})
    after = datetime.now(UTC)
    assert result["issue_number"] == 42
    value = worker.session.post.call_args.kwargs["json"]["processed_at"]
    observed = datetime.fromisoformat(value)
    assert observed.utcoffset() is not None
    assert observed.utcoffset().total_seconds() == 0
    assert before <= observed <= after
    worker.redis.lpush.assert_not_awaited()


@pytest.mark.asyncio
async def test_successive_batches_keep_limit_and_cleanup(worker, monkeypatch):
    worker.setup = AsyncMock()
    worker.teardown = AsyncMock()
    worker.redis.rpop.return_value = None
    worker.fetch_pending_feedback = AsyncMock(
        side_effect=[[{"id": n} for n in range(8)], [{"id": n} for n in range(8, 16)]]
    )
    active = 0
    peak = 0
    processed = []
    yield_once = asyncio.sleep

    async def process(item):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await yield_once(0)
        processed.append(item["id"])
        active -= 1

    polls = 0

    async def pause(seconds):
        nonlocal polls
        assert seconds == 30
        polls += 1
        if polls == 2:
            raise asyncio.CancelledError

    worker.process_feedback = process
    monkeypatch.setattr(module.asyncio, "sleep", pause)
    with pytest.raises(asyncio.CancelledError):
        await worker.run()
    assert peak == 3
    assert active == 0
    assert sorted(processed) == list(range(16))
    worker.setup.assert_awaited_once()
    worker.teardown.assert_awaited_once()
    assert worker.fetch_pending_feedback.await_count == 2


@pytest.mark.asyncio
async def test_retry_is_paced_and_does_not_starve_fresh_work(worker, monkeypatch):
    worker.setup = AsyncMock()
    worker.teardown = AsyncMock()
    worker.redis.rpop.return_value = '{"id": "retry"}'
    worker.fetch_pending_feedback = AsyncMock(
        return_value=[{"id": "retry"}, {"id": "fresh"}]
    )
    processed = []

    async def process(item):
        processed.append(item["id"])
        if len(processed) > 3:
            raise AssertionError("retry loop did not yield")

    async def pause(seconds):
        assert seconds == 30
        raise asyncio.CancelledError

    worker.process_feedback = process
    monkeypatch.setattr(module.asyncio, "sleep", pause)
    with pytest.raises(asyncio.CancelledError):
        await worker.run()
    assert processed == ["retry", "fresh"]
    worker.redis.rpop.assert_awaited_once()
    worker.fetch_pending_feedback.assert_awaited_once()
    worker.teardown.assert_awaited_once()
