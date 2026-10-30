"""Offline regressions for submission, release lookup and credit failures."""

import asyncio
import zlib
from threading import Event
from unittest.mock import Mock

import httpx
import main
import pytest
import requests
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def clear_release_cache():
    main.get_cached_version.cache_clear()
    yield
    main.get_cached_version.cache_clear()


@pytest.mark.asyncio
async def test_release_lookup_keeps_health_responsive(monkeypatch):
    entered = Event()
    release = Event()
    finished = Event()

    def stalled_release(*args, **kwargs):
        assert kwargs["timeout"] == 5
        entered.set()
        try:
            # Bound the failing control too: a blocked event loop cannot release us.
            release.wait(3)
            return Mock(status_code=503)
        finally:
            finished.set()

    monkeypatch.setattr(requests, "get", stalled_release)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url="http://test"
    ) as client:
        lookup = asyncio.create_task(client.get("/smart-tree/latest"))
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            health = await asyncio.wait_for(client.get("/health"), 2)
            assert health.status_code == 200
            assert not finished.is_set(), "Release lookup blocked the health request"
        finally:
            release.set()
            response = await lookup
        assert response.status_code == 200
        assert response.json()["version"] == "3.3.5"


@pytest.mark.parametrize("failure", [OSError, zlib.error, RuntimeError])
def test_submission_error_boundary(monkeypatch, tmp_path, failure):
    monkeypatch.setattr(main, "FEEDBACK_DIR", tmp_path)
    secret_detail = "synthetic-private-storage-path"

    def fail(*args, **kwargs):
        raise failure(secret_detail)

    monkeypatch.setattr(
        main, "compress_feedback" if failure is zlib.error else "store_feedback", fail
    )
    payload = {
        "category": "bug",
        "title": "Synthetic",
        "description": "Example",
        "ai_model": "synthetic",
        "smart_tree_version": "3.0.0",
        "impact_score": 7,
        "frequency_score": 5,
    }
    with TestClient(main.app) as client:
        if failure is RuntimeError:
            with pytest.raises(RuntimeError, match=secret_detail):
                client.post(
                    "/feedback",
                    headers={"X-API-Key": "agent_claude_001:synthetic-api-test-key"},
                    json=payload,
                )
        else:
            response = client.post(
                "/feedback",
                headers={"X-API-Key": "agent_claude_001:synthetic-api-test-key"},
                json=payload,
            )
            assert response.status_code == 500
            assert response.json() == {"detail": "Failed to save feedback"}
            assert secret_detail not in response.text
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "error",
    [
        requests.ConnectionError("offline"),
        requests.Timeout("slow"),
        requests.exceptions.JSONDecodeError("bad", "?", 0),
        RuntimeError("bug"),
    ],
)
def test_release_request_error_boundary(monkeypatch, error):
    monkeypatch.setattr(requests, "get", Mock(side_effect=error))
    if isinstance(error, RuntimeError):
        with pytest.raises(RuntimeError):
            main.get_cached_version(1)
    else:
        assert main.get_cached_version(1)["version"] == "3.3.5"


@pytest.mark.parametrize("status", [403, 404, 503])
def test_release_non_success_retains_fallback(monkeypatch, status):
    response = Mock(status_code=status)
    monkeypatch.setattr(requests, "get", Mock(return_value=response))
    assert main.get_cached_version(1)["version"] == "3.3.5"
    response.json.assert_not_called()


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        "bad",
        {"tag_name": None},
        {"tag_name": 3},
        {"body": None},
        {"body": []},
        {"published_at": None},
        {"published_at": 5},
    ],
)
def test_malformed_release_retains_fallback(monkeypatch, payload):
    response = Mock(status_code=200)
    response.json.return_value = payload
    monkeypatch.setattr(requests, "get", Mock(return_value=response))
    assert main.get_cached_version(1)["version"] == "3.3.5"


def test_release_success_and_cache(monkeypatch):
    response = Mock(status_code=200)
    response.json.return_value = {
        "tag_name": "v9.2.1",
        "published_at": "2030-01-01T12:00:00Z",
        "body": "## Features\n- Useful feature\n## AI Benefits\n- Useful benefit",
        "html_url": "https://github.com/8b-is/smart-tree/releases/tag/v9.2.1",
    }
    get = Mock(return_value=response)
    monkeypatch.setattr(requests, "get", get)
    first = main.get_cached_version(1)
    assert first["version"] == "9.2.1"
    assert first["release_date"] == "2030-01-01"
    assert first["features"] == ["Useful feature"]
    assert first["ai_benefits"] == ["Useful benefit"]
    assert main.get_cached_version(1) == first
    assert get.call_count == 1
    assert main.get_cached_version(2) == first
    assert get.call_count == 2
    assert get.call_args.kwargs["timeout"] == 5


@pytest.mark.parametrize(
    "content,expected",
    [
        ("Model: vendor:first\nModel: second\n", "vendor:first"),
        ("Model: \n", ""),
        ("No model line\n", None),
    ],
)
def test_credit_model_boundary(tmp_path, monkeypatch, content, expected):
    directory = tmp_path / "2030-01-01"
    directory.mkdir()
    target = directory / "synthetic.summary.txt"
    target.write_text(content)
    monkeypatch.setattr(main, "FEEDBACK_DIR", tmp_path)
    with TestClient(main.app) as client:
        response = client.get("/feedback/synthetic/credits")
    if expected is None:
        assert response.status_code == 500
        assert response.json() == {
            "detail": "Feedback summary has no model attribution"
        }
    else:
        assert response.status_code == 200
        assert response.json()["reporter"]["model"] == expected
    assert target.read_text() == content
