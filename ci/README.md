# Automation boundaries

`test.yml` is called by the image workflow at the same commit. Pull requests run
validation and build both API and worker images for amd64/arm64 with read-only
repository permissions. They do not log in, publish images, or export registry
caches. Pushes to the existing main/develop/version-tag triggers may publish only
after the reusable test jobs pass. This workflow does not deploy services.

Dispatch automation reads `GITHUB_EVENT_PATH` as JSON. Feedback IDs and branch
names are restricted before any file or Git operation. Titles remain literal
arguments, including shell-like text. Existing request records and symlinked
request directories are refused. Git and GitHub CLI commands use argument lists,
and the PR body uses a temporary file. No payload text is executed as shell code.

Run `python -m unittest discover -s ci -p 'test_*.py' -v` from the repository root.
The integration test uses a temporary real Git repository and intercepts push/PR
commands; it never contacts GitHub. Hosted workflow checks and container builds
are separate acceptance gates, not results established by these local tests.

`container_smoke.sh API_IMAGE WORKER_IMAGE` probes API health on container
loopback with networking disabled, imports the worker as its non-root user, and
checks a journal claim survives replacement of the container using a named volume.
It does not test the full Redis/GitHub processing loop. The runner applies a
90-second timeout; its temporary container and volume are removed on exit.
Image publication also requires this smoke job to pass.
