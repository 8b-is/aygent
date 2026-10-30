# Worker tests

Run `python -m pytest -v` in this directory for unit tests. These use synthetic
GitHub configuration and mocks; the network guard rejects IPv4/IPv6 connections,
including localhost. A swallowed connection error still fails the test teardown.
No running Redis, API, or GitHub credentials are needed.

The former live `test_worker.py` is now `check_local_services.py`, outside pytest
discovery. It only targets `127.0.0.1` and requires `--allow-local-writes` even when
`CI` is set. Use it only with disposable local data and a worker disconnected from
real GitHub automation. It submits feedback, so it is never part of routine CI.
Authentication must be configured for the local API before attempting this manual
check; its request format still needs updating for the current agent auth API.
