"""Expected storage failures stay recoverable; unexpected bugs stay visible."""

import asyncio
import builtins
import json
import runpy
import zlib
from pathlib import Path

import auth
import main
import pytest
import redis


@pytest.mark.parametrize(
    "error,recoverable",
    [
        (ValueError("synthetic URL"), True),
        (redis.exceptions.RedisError("synthetic Redis error"), True),
        (RuntimeError("synthetic bug"), False),
        (AssertionError("synthetic assertion"), False),
        (KeyboardInterrupt(), False),
        (SystemExit(2), False),
        (asyncio.CancelledError(), False),
    ],
)
def test_redis_setup_exception_boundary(monkeypatch, error, recoverable):
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(redis, "from_url", fail)
    if recoverable:
        assert runpy.run_path(auth.__file__)["redis_client"] is None
    else:
        with pytest.raises(type(error)):
            runpy.run_path(auth.__file__)


def test_redis_setup_retains_successful_client(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(redis, "from_url", lambda *a, **k: sentinel)
    assert runpy.run_path(auth.__file__)["redis_client"] is sentinel


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [OSError("synthetic I/O"), RuntimeError("bug")])
async def test_health_scan_error_boundary(monkeypatch, error):
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(Path, "glob", fail)
    if isinstance(error, OSError):
        result = await main.health_check()
        assert result["status"] == "degraded"
        assert "feedback_count" not in result
    else:
        with pytest.raises(RuntimeError):
            await main.health_check()


@pytest.mark.parametrize(
    "reader,suffix",
    [(main.get_leaderboard, ".summary.txt"), (main.get_pending_feedback, ".stfb")],
)
@pytest.mark.parametrize("error", [OSError("synthetic I/O"), RuntimeError("bug")])
def test_reader_open_error_boundary(tmp_path, monkeypatch, reader, suffix, error):
    directory = tmp_path / "2030-01-01"
    directory.mkdir()
    target = directory / ("synthetic" + suffix)
    target.write_bytes(b"synthetic")
    monkeypatch.setattr(main, "FEEDBACK_DIR", tmp_path)

    def fail_target(path, *args, **kwargs):
        if Path(path) == target:
            raise error
        return builtins.open(path, *args, **kwargs)

    monkeypatch.setattr(main, "open", fail_target, raising=False)
    if isinstance(error, OSError):
        result = reader()
        assert result == [] if suffix == ".stfb" else result["total_feedback"] == 0
    else:
        with pytest.raises(RuntimeError):
            reader()
    assert target.read_bytes() == b"synthetic"


@pytest.mark.parametrize(
    "corrupt", [b"invalid zlib", zlib.compress(b"\xff"), zlib.compress(b"not JSON")]
)
def test_pending_skips_corrupt_file_and_keeps_valid_item(
    tmp_path, monkeypatch, corrupt
):
    directory = tmp_path / "2030-01-01"
    directory.mkdir()
    good = {"id": "synthetic-valid", "title": "Example"}
    for name, payload in [
        ("bad", corrupt),
        ("good", zlib.compress(json.dumps(good).encode())),
    ]:
        (directory / (name + ".stfb")).write_bytes(
            b"STFB\x01\x00"
            + (0).to_bytes(4, "little")
            + len(payload).to_bytes(4, "little")
            + payload
        )
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    monkeypatch.setattr(main, "FEEDBACK_DIR", tmp_path)
    assert main.get_pending_feedback() == [good]
    assert {p.name: p.read_bytes() for p in directory.iterdir()} == before


def test_leaderboard_skips_invalid_text(tmp_path, monkeypatch):
    directory = tmp_path / "2030-01-01"
    directory.mkdir()
    (directory / "bad.summary.txt").write_bytes(b"\xff")
    (directory / "good.summary.txt").write_text(
        "Model: synthetic\nImpact: 7/10\nCategory: bug\n"
    )
    monkeypatch.setattr(main, "FEEDBACK_DIR", tmp_path)
    assert main.get_leaderboard()["total_feedback"] == 1
