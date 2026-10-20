"""Offline authorization checks for announcement mutations."""

import json
import time

import auth
import jwt
import main
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def announcement_store(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "STATS_DIR", tmp_path)
    announcement = main.Announcement(
        id="existing", title="Synthetic", message="Synthetic notice", priority="info"
    )
    monkeypatch.setattr(main, "announcements_cache", {"existing": announcement})
    target = tmp_path / "announcements.json"
    target.write_text(json.dumps({"existing": announcement.model_dump(mode="json")}))
    return target


def headers(case):
    if case == "missing":
        return {}
    if case == "invalid":
        return {"Authorization": "Bearer not-a-token"}
    permissions = {
        "read": ["admin.read"],
        "write": ["admin.write"],
        "wildcard": ["*"],
        "expired": ["admin.write"],
    }[case]
    token = jwt.encode(
        {
            "sub": "synthetic",
            "permissions": permissions,
            "exp": 1 if case == "expired" else int(time.time()) + 120,
        },
        auth.JWT_SECRET,
        algorithm="HS256",
    )
    return {"Authorization": "Bearer " + token}


@pytest.mark.parametrize("operation", ["create", "deactivate"])
@pytest.mark.parametrize(
    "case,status",
    [
        ("missing", 403),
        ("invalid", 401),
        ("expired", 401),
        ("read", 403),
        ("write", 200),
        ("wildcard", 200),
    ],
)
def test_mutation_permission_precedes_state_changes(
    announcement_store, operation, case, status
):
    before = announcement_store.read_bytes()
    cached = {
        key: value.model_dump() for key, value in main.announcements_cache.items()
    }
    with TestClient(main.app) as client:
        if operation == "create":
            response = client.post(
                "/announcements",
                json={
                    "id": "new",
                    "title": "Synthetic new",
                    "message": "Synthetic notice",
                    "priority": "important",
                },
                headers=headers(case),
            )
        else:
            response = client.delete("/announcements/existing", headers=headers(case))
    assert response.status_code == status, response.text
    if status != 200:
        assert announcement_store.read_bytes() == before
        assert {
            key: value.model_dump() for key, value in main.announcements_cache.items()
        } == cached
    elif operation == "create":
        assert response.json() == {
            "message": "Announcement created!",
            "id": "new",
            "active": True,
        }
        assert "new" in main.announcements_cache
        assert (
            json.loads(announcement_store.read_text())["new"]["title"]
            == "Synthetic new"
        )
    else:
        assert response.json() == {"message": "Announcement existing deactivated"}
        assert main.announcements_cache["existing"].active is False
        assert json.loads(announcement_store.read_text())["existing"]["active"] is False


def test_public_announcements_remain_readable(announcement_store):
    with TestClient(main.app) as client:
        response = client.get("/announcements")
    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["announcements"][0]["id"] == "existing"
