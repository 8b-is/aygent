"""Never interpret failed duplicate checks as permission to create an issue."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import aiohttp
import pytest
import requests
import worker as module
from github import GithubException
from redis.exceptions import RedisError


@pytest.fixture
def worker(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "fake_token_for_testing")
    result = module.FeedbackWorker()
    result.repo = Mock()
    result.repo.get_issues.return_value = []
    result.repo.create_issue.return_value = SimpleNamespace(
        number=42, title="Synthetic"
    )
    result.redis = AsyncMock()
    result.redis.get.return_value = None
    result.trigger_ai_fix_dispatch = AsyncMock(return_value=False)
    context = AsyncMock()
    context.__aenter__.return_value = SimpleNamespace(status=200)
    result.session = SimpleNamespace(post=Mock(return_value=context))
    return result


@pytest.fixture
def feedback():
    return {
        "id": "synthetic",
        "title": "Synthetic issue",
        "description": "Example feedback",
        "category": "bug",
        "impact_score": 8,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        GithubException(503, {"message": "synthetic"}),
        requests.ConnectionError("offline"),
        RuntimeError("bug"),
    ],
)
async def test_failed_duplicate_lookup_never_creates_issue(worker, feedback, error):
    worker.repo.get_issues.side_effect = error
    if isinstance(error, RuntimeError):
        with pytest.raises(RuntimeError):
            await worker.process_feedback(feedback)
        worker.redis.lpush.assert_not_awaited()
    else:
        assert await worker.process_feedback(feedback) is None
        worker.redis.lpush.assert_awaited_once_with(
            "feedback:retry", json.dumps(feedback)
        )
    worker.repo.create_issue.assert_not_called()
    worker.session.post.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("existing", [True, False])
async def test_cache_write_failure_preserves_confirmed_issue(
    worker, feedback, existing
):
    if existing:
        worker.repo.get_issues.return_value = [
            SimpleNamespace(
                number=42,
                title=feedback["title"],
                body=feedback["description"],
                pull_request=None,
            )
        ]
    worker.redis.setex.side_effect = RedisError("cache offline")
    result = await worker.process_feedback(feedback)
    assert result["issue_number"] == 42
    assert result["processed"] is True
    assert worker.repo.create_issue.call_count == (0 if existing else 1)
    worker.session.post.assert_called_once()
    worker.redis.lpush.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        GithubException(503, {"message": "synthetic"}),
        requests.Timeout("slow"),
        RuntimeError("bug"),
        asyncio.CancelledError(),
    ],
)
async def test_issue_creation_error_boundary(worker, feedback, error):
    worker.repo.create_issue.side_effect = error
    if isinstance(error, (RuntimeError, asyncio.CancelledError)):
        with pytest.raises(type(error)):
            await worker.process_feedback(feedback)
        worker.redis.lpush.assert_not_awaited()
    else:
        assert await worker.process_feedback(feedback) is None
        worker.redis.lpush.assert_awaited_once_with(
            "feedback:retry", json.dumps(feedback)
        )
    worker.repo.create_issue.assert_called_once()
    worker.redis.setex.assert_not_awaited()
    worker.session.post.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [RedisError("cache offline"), RuntimeError("bug"), asyncio.CancelledError()],
)
async def test_cache_read_error_never_creates_issue(worker, feedback, error):
    worker.redis.get.side_effect = error
    if isinstance(error, RedisError):
        assert await worker.process_feedback(feedback) is None
        worker.redis.lpush.assert_awaited_once()
    else:
        with pytest.raises(type(error)):
            await worker.process_feedback(feedback)
        worker.redis.lpush.assert_not_awaited()
    worker.repo.get_issues.assert_not_called()
    worker.repo.create_issue.assert_not_called()


@pytest.mark.asyncio
async def test_retry_queue_failure_is_not_reported_as_success(worker, feedback):
    worker.session.post.side_effect = aiohttp.ClientConnectionError("offline")
    worker.redis.lpush.side_effect = RedisError("retry unavailable")
    with pytest.raises(RedisError):
        await worker.process_feedback(feedback)
    worker.repo.create_issue.assert_called_once()
    worker.redis.lpush.assert_awaited_once()
