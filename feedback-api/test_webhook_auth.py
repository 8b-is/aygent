"""Verify webhook authentication before any dispatch state is touched."""

import hashlib
import hmac
import json

import auth
import main
import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

SECRET = "synthetic-webhook-secret-not-for-deployment"


@pytest.fixture
def dispatch_record(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "FEEDBACK_DIR", tmp_path)
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)
    date = tmp_path / "synthetic-date"
    date.mkdir()
    target = date / "12345678.dispatch.json"
    target.write_text(
        json.dumps(
            {
                "feedback_id": "12345678",
                "branch_name": "fix/12345678-auto-fix",
                "status": "pending",
            }
        )
    )
    return target


def body(action="opened", *, indent=None, ensure_ascii=True):
    return json.dumps(
        {
            "action": action,
            "repository": {"full_name": "8b-is/smart-tree"},
            "pull_request": {
                "head": {
                    "ref": "fix/12345678-auto-fix",
                    "repo": {"full_name": "8b-is/smart-tree"},
                },
                "base": {"repo": {"full_name": "8b-is/smart-tree"}},
                "number": 999999,
                "html_url": "https://github.com/8b-is/smart-tree/pull/999999",
                "title": "Synthetic 🌲",
                "merged": action == "closed",
            },
        },
        indent=indent,
        ensure_ascii=ensure_ascii,
    ).encode("utf-8")


def signature(content, secret=SECRET):
    return "sha256=" + hmac.new(secret.encode(), content, hashlib.sha256).hexdigest()


def deliver(client, content, value, event="pull_request"):
    headers = {"Content-Type": "application/json", "X-GitHub-Event": event}
    if value is not None:
        headers["X-Hub-Signature-256"] = value
    return client.post("/webhook/github", content=content, headers=headers)


@pytest.mark.parametrize("action", ["opened", "closed"])
@pytest.mark.parametrize(
    "case", ["missing", "wrong-secret", "sha1", "truncated", "tampered"]
)
def test_rejected_delivery_preserves_dispatch(dispatch_record, action, case):
    content = body(action)
    value = {
        "missing": None,
        "wrong-secret": signature(content, "another-synthetic-secret"),
        "sha1": "sha1=" + "a" * 40,
        "truncated": "sha256=abc",
        "tampered": signature(content + b" "),
    }[case]
    previous = dispatch_record.read_bytes()
    with TestClient(main.app) as client:
        response = deliver(client, content, value)
    assert response.status_code == 403
    assert dispatch_record.read_bytes() == previous


@pytest.mark.parametrize("configured", [None, ""])
def test_unconfigured_webhook_is_disabled(dispatch_record, monkeypatch, configured):
    if configured is None:
        monkeypatch.delenv("GITHUB_WEBHOOK_SECRET")
    else:
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", configured)
    content = body()
    previous = dispatch_record.read_bytes()
    with TestClient(main.app) as client:
        response = deliver(client, content, signature(content))
    assert response.status_code == 503
    assert dispatch_record.read_bytes() == previous


@pytest.mark.parametrize("indent,ensure_ascii", [(None, True), (2, False)])
def test_exact_signed_bytes_reach_handler(dispatch_record, indent, ensure_ascii):
    content = body(indent=indent, ensure_ascii=ensure_ascii)
    with TestClient(main.app) as client:
        response = deliver(client, content, signature(content))
    assert response.status_code == 200
    assert response.json() == {"status": "webhook processed"}
    record = json.loads(dispatch_record.read_text())
    assert record["status"] == "in_progress"
    assert record["pr_url"] == "https://github.com/8b-is/smart-tree/pull/999999"


def test_signed_ping_does_not_mutate_records(dispatch_record):
    content = b'{"zen":"Synthetic ping"}'
    previous = dispatch_record.read_bytes()
    with TestClient(main.app) as client:
        response = deliver(client, content, signature(content), event="ping")
    assert response.status_code == 200
    assert dispatch_record.read_bytes() == previous


@pytest.mark.asyncio
async def test_github_published_signature_vector(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "It's a Secret to Everybody")

    async def receive():
        return {"type": "http.request", "body": b"Hello, World!", "more_body": False}

    request = Request(
        {"type": "http", "method": "POST", "path": "/", "headers": []}, receive
    )
    await auth.verify_github_webhook(
        request,
        "sha256=757107ea0eb2509fc211221cce984b8a37570b6d7586c22c46f4379c8b043e17",
    )
