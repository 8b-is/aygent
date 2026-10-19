"""Consume dispatch JSON as data; never interpolate it into shell source."""

import json
import os
import re
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path


def validate(payload):
    if not isinstance(payload, dict):
        raise ValueError("client_payload must be an object")
    feedback = payload.get("feedback_id")
    branch = payload.get("branch_name")
    title = payload.get("title")
    if not isinstance(feedback, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", feedback
    ):
        raise ValueError("Invalid feedback identifier")
    if not isinstance(branch, str) or not re.fullmatch(
        r"ai-fix-[A-Za-z0-9][A-Za-z0-9_-]{0,63}", branch
    ):
        raise ValueError("Invalid fix branch")
    if (
        not isinstance(title, str)
        or not title.strip()
        or len(title) > 200
        or any(ord(c) < 32 or ord(c) == 127 for c in title)
    ):
        raise ValueError("Invalid request title")
    return feedback, branch, title


def create_request(payload, workspace, runner=subprocess.run):
    feedback, branch, title = validate(payload)
    workspace = Path(workspace)
    directory = workspace / ".ai-fixes"
    if directory.is_symlink():
        raise ValueError("Fix directory must not be a symlink")
    directory.mkdir(exist_ok=True)
    relative = f".ai-fixes/{feedback}.json"
    record = dict(
        feedback_id=feedback,
        branch=branch,
        status="pending",
        created_at=datetime.now(UTC).isoformat(),
        assigned_to="next-available-ai",
    )
    # Exclusive creation also refuses an existing file or symlink.
    with (workspace / relative).open("x") as handle:
        json.dump(record, handle, indent=2)
        handle.write("\n")

    def run(args):
        runner(args, cwd=workspace, check=True, timeout=60)

    run(["git", "checkout", "-b", branch])
    run(["git", "add", "--", relative])
    run(
        [
            "git",
            "-c",
            "user.name=github-actions[bot]",
            "-c",
            "user.email=41898282+github-actions[bot]@users.noreply.github.com",
            "commit",
            "-m",
            f"AI Fix Request: {feedback}",
        ]
    )
    run(["git", "push", "origin", f"HEAD:refs/heads/{branch}"])
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md") as body:
        body.write(
            f"## AI Fix Request\n\nFeedback ID: `{feedback}`\n\n"
            "- [ ] AI assigned\n- [ ] Fix implemented\n- [ ] Tests updated\n- [ ] Documentation updated\n\n"
            "This is an unimplemented request. Review the original feedback before making changes.\n"
        )
        body.flush()
        run(
            [
                "gh",
                "pr",
                "create",
                "--title",
                f"[AI Fix] {title}",
                "--body-file",
                body.name,
                "--draft",
                "--label",
                "ai-fix",
                "--label",
                "auto-generated",
                "--label",
                "needs-implementation",
                "--base",
                "main",
                "--head",
                branch,
            ]
        )


if __name__ == "__main__":
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    create_request(event.get("client_payload"), Path.cwd())
