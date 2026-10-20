"""Cache identity and authenticated caller isolation using synthetic transports."""

import json
from collections import defaultdict

import auth
import httpx
import llm_assistant as llm
import main
import pytest


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    stats = tmp_path / "stats"
    cache.mkdir()
    stats.mkdir()
    monkeypatch.setattr(llm, "CACHE_DIR", cache)
    monkeypatch.setattr(main, "STATS_DIR", stats)
    monkeypatch.setattr(
        main,
        "tool_stats_cache",
        defaultdict(
            lambda: {"count": 0, "models": defaultdict(int), "last_used": None}
        ),
    )
    for name in ["synthetic-a", "synthetic-b"]:
        monkeypatch.setitem(
            auth.AGENT_KEYS,
            name,
            {
                "name": name,
                "secret": "synthetic-test-key",
                "permissions": ["llm.query"],
                "rate_limit": 100,
            },
        )
    return cache


def task():
    return llm.SmartTreeTask(
        task_type="documentation",
        context="X" * 600,
        request="Synthetic task",
        language="Python",
        constraints=["first"],
        examples=["first"],
    )


@pytest.mark.parametrize(
    "change",
    [
        {"context": "X" * 500 + "Y" * 100},
        {"language": "Rust"},
        {"constraints": ["second"]},
        {"examples": ["second"]},
    ],
)
def test_cache_key_includes_complete_task(change):
    assistant = llm.SmartTreeAssistant.__new__(llm.SmartTreeAssistant)
    original = task()
    assert assistant._get_cache_key(original) != assistant._get_cache_key(
        original.model_copy(update=change)
    )


def test_delimiter_ambiguity_cannot_alias_tasks():
    assistant = llm.SmartTreeAssistant.__new__(llm.SmartTreeAssistant)
    first = task().model_copy(update={"task_type": "one:two", "request": "three"})
    second = task().model_copy(update={"task_type": "one", "request": "two:three"})
    assert assistant._get_cache_key(first) != assistant._get_cache_key(second)


def test_changed_model_invalidates_cache_identity(monkeypatch):
    assistant = llm.SmartTreeAssistant.__new__(llm.SmartTreeAssistant)
    original = assistant._get_cache_key(task())
    monkeypatch.setitem(
        llm.MODEL_PREFERENCES, "documentation", "synthetic-replacement-model"
    )
    assert assistant._get_cache_key(task()) != original


@pytest.mark.asyncio
@pytest.mark.parametrize("changed_context", [False, True])
@pytest.mark.parametrize(
    "first_route,second_route",
    [
        ("/llm/assist", "/llm/assist"),
        ("/llm/assist", "/llm/batch"),
        ("/llm/batch", "/llm/assist"),
        ("/llm/batch", "/llm/batch"),
    ],
)
async def test_http_cache_isolated_by_authenticated_agent(
    isolated_cache, monkeypatch, first_route, second_route, changed_context
):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": f"Synthetic model response {len(calls)}"}}
                ],
                "usage": {"total_tokens": 1},
            },
        )

    assistant = llm.SmartTreeAssistant.__new__(llm.SmartTreeAssistant)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://model.invalid"
    ) as model_client:
        assistant.client = model_client
        monkeypatch.setattr(main, "get_assistant", lambda: assistant)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app), base_url="http://test"
        ) as client:

            async def submit(route, agent):
                payload = task().model_dump(mode="json")
                if changed_context and agent == "synthetic-b":
                    payload["context"] = "X" * 500 + "Y" * 100
                response = await client.post(
                    route,
                    json=[payload] if route.endswith("batch") else payload,
                    headers={"X-API-Key": f"{agent}:synthetic-test-key"},
                )
                assert response.status_code == 200, response.text
                return (
                    response.json()[0] if route.endswith("batch") else response.json()
                )

            first = await submit(first_route, "synthetic-a")
            second = await submit(second_route, "synthetic-b")
            repeat = await submit(second_route, "synthetic-b")
    assert len(calls) == 2
    assert first["response"] == "Synthetic model response 1"
    assert second["response"] == repeat["response"] == "Synthetic model response 2"
    assert (
        first["cached"] is False
        and second["cached"] is False
        and repeat["cached"] is True
    )
    assert first["task_id"] != second["task_id"] == repeat["task_id"]
    # Caller identifiers and credentials are not saved as new cache metadata.
    for path in isolated_cache.glob("*.json"):
        content = path.read_text()
        assert (
            "synthetic-test-key" not in content
            and "synthetic-a" not in content
            and "synthetic-b" not in content
        )
        assert json.loads(content)["task_id"] == path.stem


@pytest.mark.asyncio
async def test_unscoped_library_calls_do_not_share_persistent_cache(isolated_cache):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "Synthetic response"}}]}
        )

    assistant = llm.SmartTreeAssistant.__new__(llm.SmartTreeAssistant)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://model.invalid"
    ) as client:
        assistant.client = client
        await assistant.assist(task())
        await assistant.assist(task())
    assert len(calls) == 2
    assert not list(isolated_cache.iterdir())


@pytest.mark.asyncio
async def test_legacy_entry_is_preserved_but_not_reused(isolated_cache):
    import hashlib

    current = task()
    old_key = hashlib.sha256(
        f"{current.task_type}:{current.request}:{current.context[:500]}".encode()
    ).hexdigest()[:16]
    legacy = isolated_cache / (old_key + ".json")
    legacy.write_text(
        llm.LLMResponse(
            task_id=old_key,
            model_used="synthetic",
            response="Legacy response",
            tokens_used=1,
            cost_estimate=0,
        ).model_dump_json()
    )
    before = legacy.read_bytes()

    def handler(request):
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Fresh synthetic response"}}]},
        )

    assistant = llm.SmartTreeAssistant.__new__(llm.SmartTreeAssistant)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://model.invalid"
    ) as client:
        assistant.client = client
        response = await assistant.assist(current, cache_scope="synthetic-caller")
    assert response.response == "Fresh synthetic response" and response.cached is False
    assert response.task_id.startswith("v2-") and len(response.task_id) == 67
    assert legacy.read_bytes() == before
    assert len(list(isolated_cache.glob("*.json"))) == 2


@pytest.mark.asyncio
async def test_batch_error_keeps_scoped_task_identity(isolated_cache):
    def handler(request):
        raise ValueError("synthetic invalid model response")

    assistant = llm.SmartTreeAssistant.__new__(llm.SmartTreeAssistant)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://model.invalid"
    ) as client:
        assistant.client = client
        responses = await assistant.batch_assist(
            [task()], cache_scope="synthetic-caller"
        )
    assert len(responses) == 1 and responses[0].model_used == "error"
    assert responses[0].task_id == assistant._get_cache_key(task(), "synthetic-caller")
    assert not list(isolated_cache.iterdir())
