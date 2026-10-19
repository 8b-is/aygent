"""File publication shared by feedback, consent, statistics and the LLM cache."""

import os
import stat
from pathlib import Path
from uuid import uuid4


def write_atomic_file(destination: Path, data: bytes) -> None:
    """Publish a complete file without exposing a partially written destination."""
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    created = False
    try:
        # Exclusive creation keeps temporary files out of feedback-reader globs.
        # Ordinary open permissions match the previous direct-write behavior.
        with temporary.open("xb") as stream:
            created = True
            stream.write(data)
            if destination.exists():
                os.fchmod(stream.fileno(), stat.S_IMODE(destination.stat().st_mode))
        os.replace(temporary, destination)
    finally:
        if created:
            temporary.unlink(missing_ok=True)
