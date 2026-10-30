"""Signed webhook record matching and durable state transitions."""

import json
import threading
from pathlib import Path

import httpx
import main
import pytest
import storage
from fastapi.testclient import TestClient
from test_webhook_auth import SECRET, deliver, signature

REPO = "8b-is/smart-tree"
BRANCH = "fix/12345678-auto-fix"


@pytest.fixture
def record(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "FEEDBACK_DIR", tmp_path)
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)
    date = tmp_path / "synthetic-date"
    date.mkdir()
    path = date / "1234567890abcdef.dispatch.json"
    path.write_text(
        main.FixDispatch(
            feedback_id="1234567890abcdef", branch_name=BRANCH
        ).model_dump_json()
    )
    return path


def event(action="opened", **changes):
    payload = {
        "repository": {"full_name": REPO},
        "action": action,
        "pull_request": {
            "number": 123,
            "html_url": f"https://github.com/{REPO}/pull/123",
            "head": {"ref": BRANCH, "repo": {"full_name": REPO}},
            "base": {"repo": {"full_name": REPO}},
            "merged": action == "closed",
        },
    }
    payload.update(changes)
    return payload


def send(client, payload):
    content = json.dumps(payload).encode()
    return deliver(client, content, signature(content))


def test_full_id_record_matches_branch_and_merge_is_durable(record):
    with TestClient(main.app) as client:
        assert send(client, event()).status_code == 200
        assert json.loads(record.read_text())["status"] == "in_progress"
        response = send(client, event("closed"))
    assert response.status_code == 200
    assert "credits recorded" not in response.text.lower()
    assert json.loads(record.read_text())["status"] == "completed"


@pytest.mark.parametrize("terminal", ["completed", "failed"])
def test_delayed_open_does_not_regress_terminal_record(record, terminal):
    data = json.loads(record.read_text())
    data.update(status=terminal, pr_url=f"https://github.com/{REPO}/pull/123")
    record.write_text(json.dumps(data))
    before = record.read_bytes()
    with TestClient(main.app) as client:
        assert send(client, event()).status_code == 200
    assert record.read_bytes() == before


@pytest.mark.parametrize("field", ["repository", "head", "base", "branch"])
def test_unrelated_repository_or_branch_is_ignored(record, field):
    payload = event()
    if field == "repository":
        payload["repository"]["full_name"] = "8b-is/aygent"
    elif field == "branch":
        payload["pull_request"]["head"]["ref"] = "ai-fix-12345678"
    else:
        payload["pull_request"][field]["repo"]["full_name"] = "unrelated/fork"
    before = record.read_bytes()
    with TestClient(main.app) as client:
        assert send(client, payload).status_code == 200
    assert record.read_bytes() == before


@pytest.mark.parametrize("bad", [None, [], {"head": None}, {"number": True}])
def test_malformed_pr_rejected_without_mutation(record, bad):
    before = record.read_bytes()
    with TestClient(main.app, raise_server_exceptions=False) as client:
        assert send(client, event(pull_request=bad)).status_code == 422
    assert record.read_bytes() == before


def test_ambiguous_legacy_branch_is_not_guessed(record):
    other = record.with_name("12345678ffffffff.dispatch.json")
    other.write_text(
        main.FixDispatch(
            feedback_id="12345678ffffffff", branch_name=BRANCH
        ).model_dump_json()
    )
    before = [p.read_bytes() for p in (record, other)]
    with TestClient(main.app) as client:
        assert send(client, event()).status_code == 409
    assert [p.read_bytes() for p in (record, other)] == before


def test_conflicting_pr_binding_is_rejected(record):
    data = json.loads(record.read_text())
    data["pr_url"] = f"https://github.com/{REPO}/pull/321"
    record.write_text(json.dumps(data))
    before = record.read_bytes()
    with TestClient(main.app) as client:
        assert send(client, event()).status_code == 409
    assert record.read_bytes() == before


def test_duplicate_delivery_does_not_rewrite_record(record):
    with TestClient(main.app) as client:
        assert send(client, event()).status_code == 200
        before = (record.read_bytes(), record.stat().st_mtime_ns)
        assert send(client, event()).status_code == 200
    assert (record.read_bytes(), record.stat().st_mtime_ns) == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("html_url", "https://unrelated.invalid/pr"),
        ("number", True),
        ("merged", "true"),
    ],
)
def test_invalid_identity_or_merge_flag_preserves_record(record, field, value):
    payload = event("closed")
    payload["pull_request"][field] = value
    before = record.read_bytes()
    with TestClient(main.app) as client:
        assert send(client, payload).status_code == 422
    assert record.read_bytes() == before


def test_failed_atomic_publish_preserves_dispatch(record, monkeypatch):
    before = record.read_bytes()

    def fail(*args):
        raise OSError("synthetic replacement failure")

    monkeypatch.setattr(storage.os, "replace", fail)
    with TestClient(main.app, raise_server_exceptions=False) as client:
        assert send(client, event()).status_code == 500
    assert record.read_bytes() == before
    assert list(record.parent.iterdir()) == [record]


@pytest.mark.asyncio
async def test_webhook_storage_runs_off_loop(record, monkeypatch):
    original = Path.open
    observed = []
    loop = threading.get_ident()

    def opened(path, *args, **kwargs):
        if path.parent == record.parent:
            observed.append(threading.get_ident())
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", opened)
    content = json.dumps(event()).encode()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/webhook/github",
            content=content,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": signature(content),
            },
        )
    assert response.status_code == 200
    assert observed and all(t != loop for t in observed)
