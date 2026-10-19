"""Offline coverage for feedback listings and their disk-access boundary."""

import threading
from pathlib import Path

import httpx
import main
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def feedback_store(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "FEEDBACK_DIR", tmp_path)
    for index, category in enumerate(["bug", "critical", "tool_request"]):
        feedback = main.SmartTreeFeedback(
            category=category,
            title=f"Synthetic {category}",
            description=f"Synthetic description {index}",
            ai_model="vendor:synthetic",
            smart_tree_version="3.3.0",
            impact_score=7,
            frequency_score=5,
            timestamp="2026-10-19T16:00:00Z",
        )
        compressed, _, original_size = main.compress_feedback(feedback)
        main.store_feedback(feedback, f"synthetic{index}", compressed, original_size)
    return tmp_path


def test_stats_include_supported_tool_request_category(feedback_store):
    with TestClient(main.app) as client:
        response = client.get("/feedback/stats")
    assert response.status_code == 200
    assert response.json()["total_feedback"] == 3
    assert response.json()["by_category"] == {
        "bug": 1,
        "critical": 1,
        "nice_to_have": 0,
        "tool_request": 1,
    }


def test_requested_tools_find_binary_companion(feedback_store):
    with TestClient(main.app) as client:
        response = client.get("/tools/requested")
    assert response.status_code == 200
    assert response.json()["total_requests"] == 1
    assert response.json()["requests"] == [
        {
            "id": "synthetic2",
            "date": "2026-10-19",
            "summary": "Synthetic description 2...",
        }
    ]


@pytest.mark.parametrize("offset,limit", [(0, 2), (1, 1), (2, 2), (3, 2), (0, 10)])
def test_pending_pagination_applies_offset_before_limit(feedback_store, offset, limit):
    with TestClient(main.app) as client:
        complete = client.get("/feedback/pending", params={"limit": 10}).json()
        response = client.get(
            "/feedback/pending", params={"offset": offset, "limit": limit}
        )
    assert len(complete) == 3
    assert response.status_code == 200
    assert response.json() == complete[offset : offset + limit]


def test_pending_excludes_processed_items(feedback_store):
    (feedback_store / "2026-10-19" / "synthetic1.processed").touch()
    with TestClient(main.app) as client:
        response = client.get("/feedback/pending")
    assert response.status_code == 200
    assert {item["category"] for item in response.json()} == {"bug", "tool_request"}


@pytest.mark.parametrize(
    "route",
    ["/feedback/synthetic0/credits", "/feedback/stats", "/stats/model-activity"],
)
def test_namespaced_model_identity_is_preserved(feedback_store, route):
    with TestClient(main.app) as client:
        response = client.get(route)
    assert response.status_code == 200
    data = response.json()
    if route.endswith("/credits"):
        assert data["reporter"]["model"] == "vendor:synthetic"
    elif route.endswith("/stats"):
        assert data["top_models"] == {"vendor:synthetic": 3}
    else:
        assert data["models"]["vendor:synthetic"]["feedback_submitted"] == 3
        assert "vendor" not in data["models"]


def test_leaderboard_aggregates_feedback(feedback_store):
    with TestClient(main.app) as client:
        response = client.get("/credits/leaderboard")
    assert response.status_code == 200
    data = response.json()
    assert data["total_feedback"] == 3
    assert data["total_impact_points"] == 21
    assert data["top_reporter"]["ai"] == "vendor:synthetic"
    assert data["top_reporter"]["issues_found"] == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "route,expected_status",
    [
        ("/feedback/stats", 200),
        ("/feedback/pending", 200),
        ("/tools/requested", 200),
        ("/feedback/missing/credits", 404),
        ("/credits/leaderboard", 200),
    ],
)
async def test_reader_disk_scans_run_off_loop(
    tmp_path, monkeypatch, route, expected_status
):
    monkeypatch.setattr(main, "FEEDBACK_DIR", tmp_path)
    loop_thread = threading.get_ident()
    storage_threads = []

    def observe(method):
        def scan(path, *args, **kwargs):
            if path == tmp_path:
                storage_threads.append(threading.get_ident())
            return method(path, *args, **kwargs)

        return scan

    monkeypatch.setattr(Path, "glob", observe(Path.glob))
    monkeypatch.setattr(Path, "iterdir", observe(Path.iterdir))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url="http://test"
    ) as client:
        response = await client.get(route)
    assert response.status_code == expected_status
    assert storage_threads and all(t != loop_thread for t in storage_threads)
