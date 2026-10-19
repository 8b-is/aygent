"""Offline regressions for feedback persistence and its async request boundary."""

import json
import stat
import threading
import zlib
from pathlib import Path
from uuid import UUID

import httpx
import main
import pytest


@pytest.mark.asyncio
async def test_feedback_storage_runs_off_loop_and_preserves_format(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(main, "FEEDBACK_DIR", tmp_path)
    loop_thread = threading.get_ident()
    storage_threads = []
    original_mkdir = Path.mkdir

    def observed_mkdir(path, *args, **kwargs):
        if path.parent == tmp_path:
            storage_threads.append(threading.get_ident())
        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", observed_mkdir)
    payload = {
        "category": "bug",
        "title": "Synthetic storage regression",
        "description": "Synthetic feedback, including Unicode: café",
        "ai_model": "synthetic",
        "smart_tree_version": "3.3.0",
        "impact_score": 7,
        "frequency_score": 5,
        "tags": ["test"],
        "timestamp": "2026-10-19T16:00:00Z",
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/feedback",
            headers={
                "X-API-Key": "agent_claude_001:synthetic-api-test-key",
                "X-MCP-Client": "synthetic-client",
            },
            json=payload,
        )

    assert response.status_code == 200, response.text
    assert storage_threads and all(t != loop_thread for t in storage_threads)
    result = response.json()
    target = tmp_path / "2026-10-19" / f"{result['feedback_id']}.stfb"
    binary = target.read_bytes()
    assert binary[:6] == b"STFB\x01\x00"
    decoded = zlib.decompress(binary[14:])
    assert int.from_bytes(binary[6:10], "little") == len(decoded)
    assert int.from_bytes(binary[10:14], "little") == len(binary[14:])
    assert result["original_size"] == len(decoded)
    assert result["compressed_size"] == len(binary[14:])
    saved = json.loads(decoded)
    assert saved["description"] == payload["description"]
    assert saved["tags"] == [
        "test",
        "mcp_client:synthetic-client",
        "agent:agent_claude_001",
    ]
    summary = target.with_suffix(".summary.txt").read_text()
    assert f"ID: {result['feedback_id']}\n" in summary
    assert (
        "Tags: test, mcp_client:synthetic-client, agent:agent_claude_001\n" in summary
    )
    assert f"\nDescription:\n{payload['description']}...\n" in summary
    assert sorted(p.name for p in target.parent.iterdir()) == sorted(
        [target.name, target.with_suffix(".summary.txt").name]
    )


@pytest.mark.parametrize("existing", [False, True])
def test_file_is_complete_before_publication(tmp_path, monkeypatch, existing):
    target = tmp_path / "synthetic.stfb"
    if existing:
        target.write_bytes(b"previous complete file")
        target.chmod(0o640)
    replace = main.os.replace
    observations = []

    def observed_replace(source, destination):
        observations.append(source)
        assert source.read_bytes() == b"new complete file"
        assert destination == target
        assert list(tmp_path.glob("*.stfb")) == ([target] if existing else [])
        if existing:
            assert target.read_bytes() == b"previous complete file"
        return replace(source, destination)

    monkeypatch.setattr(main.os, "replace", observed_replace)
    main.write_atomic_file(target, b"new complete file")
    assert len(observations) == 1
    assert target.read_bytes() == b"new complete file"
    assert list(tmp_path.iterdir()) == [target]
    if existing:
        assert stat.S_IMODE(target.stat().st_mode) == 0o640


@pytest.mark.parametrize("existing", [False, True])
def test_failed_publication_cleans_temp_and_preserves_destination(
    tmp_path, monkeypatch, existing
):
    target = tmp_path / "synthetic.summary.txt"
    if existing:
        target.write_bytes(b"previous complete summary")

    def failed_replace(source, destination):
        assert source.read_bytes() == b"new complete summary"
        raise OSError("synthetic publication failure")

    monkeypatch.setattr(main.os, "replace", failed_replace)
    with pytest.raises(OSError, match="synthetic publication failure"):
        main.write_atomic_file(target, b"new complete summary")
    assert list(tmp_path.iterdir()) == ([target] if existing else [])
    if existing:
        assert target.read_bytes() == b"previous complete summary"


def test_exclusive_creation_does_not_remove_preexisting_temp(tmp_path, monkeypatch):
    identifier = UUID("00000000-0000-0000-0000-000000000001")
    monkeypatch.setattr(main, "uuid4", lambda: identifier)
    target = tmp_path / "synthetic.stfb"
    temporary = tmp_path / f".{target.name}.{identifier.hex}.tmp"
    temporary.write_bytes(b"preexisting temporary file")
    with pytest.raises(FileExistsError):
        main.write_atomic_file(target, b"new complete file")
    assert temporary.read_bytes() == b"preexisting temporary file"
    assert not target.exists()
