"""Offline dispatch reservation and delivery outcome checks."""

import asyncio
import json
import threading
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import main
import pytest
from fastapi.testclient import TestClient
from test_auth_boundaries import token

IDENTIFIER = "1234567890abcdef"


@pytest.fixture
def dispatch_store(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "FEEDBACK_DIR", tmp_path)
    monkeypatch.setenv("SMART_TREE_FIX_WEBHOOK", "https://webhook.invalid/dispatch")
    date = tmp_path / "synthetic-date"
    date.mkdir()
    (date / f"{IDENTIFIER}.stfb").write_bytes(b"synthetic")
    post = AsyncMock(return_value=httpx.Response(204))
    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    return date, post


def request(client, identifier=IDENTIFIER):
    return client.post(
        f"/feedback/{identifier}/dispatch-fix",
        headers={"Authorization": "Bearer " + token(["feedback.dispatch"])},
    )


def test_full_branch_and_durable_reservation_before_delivery(dispatch_store):
    date, post = dispatch_store
    target = date / f"{IDENTIFIER}.dispatch.json"

    async def observe(*args, **kwargs):
        data = json.loads(target.read_text())
        assert data["delivery_status"] == "attempting"
        assert kwargs["json"]["branch_name"] == f"fix/{IDENTIFIER}-auto-fix"
        return httpx.Response(204)

    post.side_effect = observe
    with TestClient(main.app) as client:
        response = request(client)
    assert response.status_code == 200
    assert json.loads(target.read_text())["delivery_status"] == "accepted"


@pytest.mark.parametrize("status", ["pending", "in_progress", "completed", "failed"])
def test_existing_records_never_reset_or_redeliver(dispatch_store, status):
    date, post = dispatch_store
    target = date / f"{IDENTIFIER}.dispatch.json"
    data = main.FixDispatch(
        feedback_id=IDENTIFIER, branch_name="fix/12345678-auto-fix", status=status
    ).model_dump(mode="json")
    data.update(
        pr_url="https://github.com/8b-is/smart-tree/pull/123", delivery_status="unknown"
    )
    target.write_text(json.dumps(data))
    before = target.read_bytes()
    with TestClient(main.app) as client:
        assert request(client).status_code == 200
    assert target.read_bytes() == before
    post.assert_not_awaited()


@pytest.mark.parametrize("status", [301, 400, 429, 500])
def test_rejected_delivery_recorded_without_blind_retry(dispatch_store, status):
    date, post = dispatch_store
    post.return_value = httpx.Response(status)
    with TestClient(main.app) as client:
        assert request(client).status_code == 502
        assert request(client).status_code == 200
    assert post.await_count == 1
    assert (
        json.loads((date / f"{IDENTIFIER}.dispatch.json").read_text())[
            "delivery_status"
        ]
        == "rejected"
    )


def test_timeout_keeps_unknown_outcome_without_retry(dispatch_store):
    date, post = dispatch_store
    post.side_effect = httpx.ReadTimeout("synthetic timeout")
    with TestClient(main.app, raise_server_exceptions=False) as client:
        assert request(client).status_code == 502
        assert request(client).status_code == 200
    assert post.await_count == 1
    assert (
        json.loads((date / f"{IDENTIFIER}.dispatch.json").read_text())[
            "delivery_status"
        ]
        == "unknown"
    )


def test_missing_webhook_is_recorded_without_success_claim(dispatch_store, monkeypatch):
    date, post = dispatch_store
    monkeypatch.delenv("SMART_TREE_FIX_WEBHOOK")
    with TestClient(main.app) as client:
        response = request(client)
    assert response.status_code == 200
    assert "not configured" in response.json()["message"]
    assert (
        json.loads((date / f"{IDENTIFIER}.dispatch.json").read_text())[
            "delivery_status"
        ]
        == "not_configured"
    )
    post.assert_not_awaited()


def test_delivery_update_preserves_concurrent_webhook_status(dispatch_store):
    date, post = dispatch_store
    target = date / f"{IDENTIFIER}.dispatch.json"

    async def observe(*args, **kwargs):
        data = json.loads(target.read_text())
        data.update(
            status="completed", pr_url="https://github.com/8b-is/smart-tree/pull/123"
        )
        target.write_text(json.dumps(data))
        return httpx.Response(204)

    post.side_effect = observe
    with TestClient(main.app) as client:
        assert request(client).status_code == 200
    data = json.loads(target.read_text())
    assert data["status"] == "completed" and data["delivery_status"] == "accepted"


@pytest.mark.asyncio
async def test_concurrent_requests_send_once_and_storage_is_off_loop(
    dispatch_store, monkeypatch
):
    date, post = dispatch_store
    observed = []
    loop = threading.get_ident()
    original = Path.open

    def opened(path, *args, **kwargs):
        if path.parent == date:
            observed.append(threading.get_ident())
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", opened)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url="http://test"
    ) as client:
        responses = await asyncio.gather(
            *(
                client.request(
                    "POST",
                    f"/feedback/{IDENTIFIER}/dispatch-fix",
                    headers={"Authorization": "Bearer " + token(["feedback.dispatch"])},
                )
                for _ in range(8)
            )
        )
    assert all(response.status_code == 200 for response in responses)
    assert post.await_count == 1
    assert observed and all(t != loop for t in observed)


def test_ambiguous_feedback_id_is_not_dispatched(dispatch_store):
    date, post = dispatch_store
    other = date.parent / "other-date"
    other.mkdir()
    (other / f"{IDENTIFIER}.stfb").write_bytes(b"synthetic")
    with TestClient(main.app) as client:
        assert request(client).status_code == 409
    post.assert_not_awaited()
    assert not list(date.parent.glob("*/*.dispatch.json"))


@pytest.mark.parametrize(
    "identifier", ["../outside", "/absolute", "bad\\name", "bad\x00name"]
)
def test_unsafe_identifier_rejected_before_disk_lookup(dispatch_store, identifier):
    date, post = dispatch_store
    with pytest.raises(main.HTTPException) as error:
        main.prepare_fix_dispatch(identifier, None, True)
    assert error.value.status_code == 422
    assert list(date.glob("*.dispatch.json")) == []
    post.assert_not_awaited()


def test_failed_reservation_never_delivers(dispatch_store, monkeypatch):
    date, post = dispatch_store

    def fail(*args):
        raise OSError("synthetic persistence failure")

    monkeypatch.setattr(main, "write_atomic_file", fail)
    with TestClient(main.app, raise_server_exceptions=False) as client:
        assert request(client).status_code == 500
    assert not list(date.glob("*.dispatch.json"))
    post.assert_not_awaited()


def test_accepted_but_unrecorded_result_is_not_redelivered(dispatch_store, monkeypatch):
    date, post = dispatch_store
    original = main.write_atomic_file
    calls = 0

    def fail_second(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic outcome persistence failure")
        return original(*args)

    monkeypatch.setattr(main, "write_atomic_file", fail_second)
    with TestClient(main.app, raise_server_exceptions=False) as client:
        assert request(client).status_code == 500
        assert request(client).status_code == 200
    assert (
        json.loads((date / f"{IDENTIFIER}.dispatch.json").read_text())[
            "delivery_status"
        ]
        == "attempting"
    )
    assert post.await_count == 1


@pytest.mark.asyncio
async def test_cancelled_delivery_keeps_reservation_without_retry(dispatch_store):
    date, post = dispatch_store
    entered = asyncio.Event()

    async def pending(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    post.side_effect = pending
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url="http://test"
    ) as client:
        authorization = {"Authorization": "Bearer " + token(["feedback.dispatch"])}
        task = asyncio.create_task(
            client.request(
                "POST", f"/feedback/{IDENTIFIER}/dispatch-fix", headers=authorization
            )
        )
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        response = await client.request(
            "POST", f"/feedback/{IDENTIFIER}/dispatch-fix", headers=authorization
        )
    assert response.status_code == 200
    assert post.await_count == 1
    assert (
        json.loads((date / f"{IDENTIFIER}.dispatch.json").read_text())[
            "delivery_status"
        ]
        == "attempting"
    )
