"""Persistent attempt claims; an uncertain external outcome is never auto-replayed."""

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path


class DispatchJournal:
    def __init__(self, path: Path):
        self.path = path

    @staticmethod
    def key(repository: str, feedback_id: str) -> str:
        if not repository or not feedback_id:
            raise ValueError("Repository and feedback id are required")
        return hashlib.sha256(
            json.dumps([repository, feedback_id]).encode()
        ).hexdigest()

    def claim(self, repository: str, feedback_id: str) -> bool:
        key = self.key(repository, feedback_id)
        # Parent must be provisioned as durable storage by the caller.
        with closing(sqlite3.connect(self.path, timeout=5)) as db, db:
            db.execute("PRAGMA synchronous=FULL")
            db.execute(
                "CREATE TABLE IF NOT EXISTS attempts "
                "(key TEXT PRIMARY KEY, status TEXT NOT NULL, updated TEXT NOT NULL)"
            )
            cursor = db.execute(
                "INSERT OR IGNORE INTO attempts VALUES (?, 'attempting', ?)",
                (key, datetime.now(UTC).isoformat()),
            )
            return cursor.rowcount == 1

    def finish(self, repository: str, feedback_id: str, status: str) -> None:
        if status not in {"accepted", "rejected", "unknown"}:
            raise ValueError("Invalid dispatch outcome")
        with closing(sqlite3.connect(self.path, timeout=5)) as db, db:
            db.execute("PRAGMA synchronous=FULL")
            cursor = db.execute(
                "UPDATE attempts SET status=?, updated=? "
                "WHERE key=? AND status='attempting'",
                (
                    status,
                    datetime.now(UTC).isoformat(),
                    self.key(repository, feedback_id),
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("Dispatch attempt missing or already finalized")
