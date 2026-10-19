import time
from unittest.mock import AsyncMock

import auth
import httpx
import jwt
import main
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    return TestClient(main.app)


def token(permissions, secret=None, expired=False):
    return jwt.encode(
        {
            "sub": "synthetic",
            "permissions": permissions,
            "exp": 1 if expired else int(time.time()) + 120,
        },
        secret or auth.JWT_SECRET,
        algorithm="HS256",
    )


@pytest.mark.parametrize("case", ["valid", "expired", "bad-signature", "malformed"])
def test_jwt_http_boundary(client, case):
    value = {
        "valid": token(["*"]),
        "expired": token(["*"], expired=True),
        "bad-signature": token(["*"], secret="different-synthetic-key"),
        "malformed": "not-a-token",
    }[case]
    response = client.get(
        "/admin/api/verify", headers={"Authorization": "Bearer " + value}
    )
    assert response.status_code == (200 if case == "valid" else 401)


@pytest.mark.parametrize(
    "username,variable", [("admin", "ADMIN_PASSWORD"), ("hue", "HUE_PASSWORD")]
)
@pytest.mark.parametrize("configured", [None, "", "synthetic-password"])
def test_admin_configuration(client, monkeypatch, username, variable, configured):
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("HUE_PASSWORD", raising=False)
    if configured is not None:
        monkeypatch.setenv(variable, configured)
    monkeypatch.setattr(auth, "ADMIN_USERS", auth.load_admin_users())
    assert (username in auth.ADMIN_USERS) == bool(configured)
    response = client.post(
        "/admin/api/login", json={"username": username, "password": configured or ""}
    )
    assert response.status_code == (200 if configured else 401)
    wrong = client.post(
        "/admin/api/login", json={"username": username, "password": "wrong"}
    )
    assert wrong.status_code == 401


@pytest.mark.parametrize(
    "permissions", [None, ["feedback.read"], ["feedback.dispatch"], ["*"]]
)
def test_dispatch_auth_precedes_side_effects(
    client, monkeypatch, tmp_path, permissions
):
    monkeypatch.setattr(main, "FEEDBACK_DIR", tmp_path)
    dated = tmp_path / "synthetic-date"
    dated.mkdir()
    (dated / "synthetic.stfb").write_bytes(b"synthetic fixture")
    monkeypatch.setenv("SMART_TREE_FIX_WEBHOOK", "https://webhook.invalid/dispatch")
    post = AsyncMock(return_value=httpx.Response(200))
    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    headers = (
        {} if permissions is None else {"Authorization": "Bearer " + token(permissions)}
    )
    response = client.post("/feedback/synthetic/dispatch-fix", headers=headers)
    allowed = permissions is not None and any(
        p in permissions for p in ["*", "feedback.dispatch"]
    )
    if allowed:
        assert response.status_code == 200
        assert (dated / "synthetic.dispatch.json").exists()
        post.assert_awaited_once()
    else:
        assert response.status_code in (401, 403)
        assert not (dated / "synthetic.dispatch.json").exists()
        post.assert_not_awaited()
