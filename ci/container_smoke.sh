#!/usr/bin/env bash
set -euo pipefail
api_image=${1:?API image required}
worker_image=${2:?Worker image required}
volume="aygent-smoke-${GITHUB_RUN_ID:-local}-$$"
api="${volume}-api"
cleanup() {
  docker rm -f "$api" >/dev/null 2>&1 || true
  docker volume rm "$volume" >/dev/null 2>&1 || true
}
trap cleanup EXIT
docker volume create "$volume" >/dev/null
docker run -d --name "$api" --network none "$api_image" >/dev/null
# Probe only loopback inside the isolated container; no host port is published.
docker exec -i "$api" python - <<'PYTHON'
import json
import time
import urllib.request
for attempt in range(30):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8420/health", timeout=1) as r:
            assert r.status == 200
            assert json.load(r)["status"] == "healthy"
        break
    except OSError:
        time.sleep(1)
else:
    raise SystemExit("API failed to become healthy")
PYTHON
# Run as the image's default non-root user, with no credentials or network.
docker run --rm --network none -v "$volume:/app/state" "$worker_image" python -c '
import os
from pathlib import Path
from worker import FeedbackWorker
from dispatch_journal import DispatchJournal
assert os.getuid() != 0
worker = FeedbackWorker()
assert worker.gh is None
journal = DispatchJournal(Path("/app/state/dispatch.sqlite"))
assert journal.claim("test/repo", "smoke")
journal.finish("test/repo", "smoke", "unknown")
'
docker run --rm --network none -v "$volume:/app/state" "$worker_image" python -c '
from pathlib import Path
from dispatch_journal import DispatchJournal
assert not DispatchJournal(Path("/app/state/dispatch.sqlite")).claim("test/repo", "smoke")
'
echo "API startup, non-root worker import, and journal persistence passed"
