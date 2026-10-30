"""Offline durability and concurrent claim tests."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from dispatch_journal import DispatchJournal


@pytest.mark.parametrize("status", [None, "accepted", "rejected", "unknown"])
def test_reopening_never_reclaims_attempt(tmp_path, status):
    path = tmp_path / "journal.sqlite"
    first = DispatchJournal(path)
    assert first.claim("owner/repo", "feedback")
    if status:
        first.finish("owner/repo", "feedback", status)
    assert not DispatchJournal(path).claim("owner/repo", "feedback")
    assert DispatchJournal(path).claim("owner/other", "feedback")


def test_concurrent_claims_have_one_winner(tmp_path):
    path = tmp_path / "journal.sqlite"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: DispatchJournal(path).claim("owner/repo", "same"), range(8)
            )
        )
    assert results.count(True) == 1


def test_final_outcome_cannot_be_overwritten(tmp_path):
    journal = DispatchJournal(tmp_path / "journal.sqlite")
    assert journal.claim("owner/repo", "feedback")
    journal.finish("owner/repo", "feedback", "accepted")
    with pytest.raises(ValueError, match="already finalized"):
        journal.finish("owner/repo", "feedback", "rejected")


def test_claim_survives_process_exit(tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    path = tmp_path / "journal.sqlite"
    subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from dispatch_journal import DispatchJournal; from pathlib import Path; "
                "import sys; assert DispatchJournal(Path(sys.argv[1])).claim('repo', 'id')"
            ),
            str(path),
        ],
        cwd=Path(__file__).parent,
        check=True,
        timeout=10,
    )
    assert not DispatchJournal(path).claim("repo", "id")
