"""Expiration is compared in UTC for new and legacy announcement records."""

import json
from datetime import UTC, datetime

import main
import pytest
from fastapi.testclient import TestClient
from test_announcement_auth import headers


@pytest.fixture
def store(tmp_path, monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2030, 1, 2, 12, tzinfo=UTC)

    monkeypatch.setattr(main, "datetime", Clock)
    monkeypatch.setattr(main, "STATS_DIR", tmp_path)
    monkeypatch.setattr(main, "announcements_cache", {})
    target = tmp_path / "announcements.json"
    target.write_text("{}")
    return target


def notice(expiry):
    return {
        "id": "synthetic",
        "title": "Synthetic notice",
        "message": "Synthetic body",
        "priority": "info",
        "expires_at": expiry,
    }


@pytest.mark.parametrize("source", ["http", "legacy-store"])
@pytest.mark.parametrize(
    "expiry,visible",
    [
        (None, True),
        ("2030-01-02T11:59:59", False),
        ("2030-01-02T12:00:01", True),
        ("2030-01-02T12:00:00", True),
        ("2030-01-02T11:59:59Z", False),
        ("2030-01-02T12:00:01Z", True),
        ("2030-01-02T20:59:59+09:00", False),
        ("2030-01-02T21:00:01+09:00", True),
        ("2030-01-02T07:59:59-04:00", False),
        ("2030-01-02T08:00:01-04:00", True),
    ],
)
def test_expiration_for_new_and_legacy_records(
    store, monkeypatch, source, expiry, visible
):
    with TestClient(main.app, raise_server_exceptions=False) as client:
        if source == "http":
            assert (
                client.post(
                    "/announcements", json=notice(expiry), headers=headers("write")
                ).status_code
                == 200
            )
        else:
            store.write_text(json.dumps({"synthetic": notice(expiry)}))
        original = store.read_bytes()
        for _ in range(2):
            monkeypatch.setattr(main, "announcements_cache", {})
            response = client.get("/announcements")
            assert response.status_code == 200
            assert response.json()["count"] == int(visible)
            cached = main.announcements_cache["synthetic"].expires_at
            if expiry is None:
                assert cached is None
            else:
                expected = datetime.fromisoformat(expiry)
                if expected.tzinfo is None:
                    expected = expected.replace(tzinfo=UTC)
                assert cached == expected
                assert cached.utcoffset() == expected.utcoffset()
            assert store.read_bytes() == original


@pytest.mark.parametrize(
    "invalid", ["not-a-date", "2030-13-02T00:00:00", {"time": "no"}]
)
def test_invalid_expiration_rejected_before_storage(store, invalid):
    original = store.read_bytes()
    with TestClient(main.app) as client:
        response = client.post(
            "/announcements", json=notice(invalid), headers=headers("write")
        )
    assert response.status_code == 422
    assert store.read_bytes() == original


def test_naive_expiration_persisted_with_explicit_utc(store, monkeypatch):
    with TestClient(main.app) as client:
        assert (
            client.post(
                "/announcements",
                json=notice("2030-01-03T12:00:00"),
                headers=headers("write"),
            ).status_code
            == 200
        )
    stored = json.loads(store.read_text())["synthetic"]["expires_at"]
    assert datetime.fromisoformat(stored).utcoffset().total_seconds() == 0
    monkeypatch.setattr(main, "announcements_cache", {})
    loaded = main.load_announcements()["synthetic"].expires_at
    assert loaded == datetime(2030, 1, 3, 12, tzinfo=UTC)
