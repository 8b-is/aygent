"""Credential discovery requires explicit development mode and full authority."""

import main
import pytest
from fastapi.testclient import TestClient
from test_auth_boundaries import token


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(
        main,
        "AGENT_KEYS",
        {
            "synthetic": {
                "name": "Synthetic administrator",
                "secret": "synthetic-key-not-for-deployment",
                "permissions": ["*"],
                "rate_limit": 100,
            }
        },
    )
    return TestClient(main.app)


def bearer(value):
    return {"Authorization": "Bearer " + value}


@pytest.mark.parametrize(
    "environment",
    [
        None,
        "",
        "production",
        "staging",
        "Development",
        "development ",
        " development",
        "test",
        "development",
    ],
)
def test_key_discovery_environment(client, monkeypatch, environment):
    monkeypatch.delenv("ENV", raising=False)
    if environment is not None:
        monkeypatch.setenv("ENV", environment)
    response = client.get("/auth/keys", headers=bearer(token(["*"])))
    assert response.status_code == (200 if environment == "development" else 403)
    if environment == "development":
        assert response.json() == {
            "message": "API keys for testing (use X-API-Key header)",
            "format": "agent_id:api_key",
            "keys": {
                "synthetic": {
                    "name": "Synthetic administrator",
                    "api_key": "synthetic:synthetic-key-not-for-deployment",
                    "permissions": ["*"],
                    "rate_limit": 100,
                }
            },
        }
    else:
        assert "synthetic-key-not-for-deployment" not in response.text


@pytest.mark.parametrize(
    "case,status",
    [
        ("missing", 403),
        ("feedback", 403),
        ("read", 403),
        ("write", 403),
        ("wildcard", 200),
        ("expired", 401),
        ("wrong-signature", 401),
        ("malformed", 401),
    ],
)
def test_key_discovery_authority(client, monkeypatch, case, status):
    monkeypatch.setenv("ENV", "development")
    values = {
        "feedback": token(["feedback.read"]),
        "read": token(["admin.read"]),
        "write": token(["admin.write"]),
        "wildcard": token(["*"]),
        "expired": token(["*"], expired=True),
        "wrong-signature": token(["*"], secret="different-synthetic-key"),
        "malformed": "not-a-token",
    }
    headers = {} if case == "missing" else bearer(values[case])
    response = client.get("/auth/keys", headers=headers)
    assert response.status_code == status
    if status != 200:
        assert "synthetic-key-not-for-deployment" not in response.text


@pytest.mark.parametrize(
    "environment,authenticated",
    [("development", False), ("production", True), (None, True)],
)
def test_denied_discovery_never_reads_keys(
    client, monkeypatch, environment, authenticated
):
    class UnreadableKeys:
        def items(self):
            pytest.fail("Denied credential discovery accessed the key registry")

    monkeypatch.setattr(main, "AGENT_KEYS", UnreadableKeys())
    monkeypatch.delenv("ENV", raising=False)
    if environment is not None:
        monkeypatch.setenv("ENV", environment)
    headers = bearer(token(["*"])) if authenticated else {}
    assert client.get("/auth/keys", headers=headers).status_code == 403
