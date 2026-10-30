# Dispatch attempt journal

The worker claims each repository/feedback-id pair in SQLite before contacting GitHub.
A retained claim suppresses automatic replay, including after cancellation, timeout,
HTTP rejection or restart. SQLite work runs outside the event loop. A journal error
prevents sending and propagates; there is no memory-only fallback.

The default file is `/app/state/dispatch.sqlite`; `DISPATCH_JOURNAL_PATH` overrides it.
Compose supplies `worker-state`, and the image provisions its directory for the
non-root worker. Local runs must provision a writable durable parent directory.
All workers processing the same feedback must share the same journal storage.

Records contain a SHA-256 key of the repository/id pair, status and timestamp, not
credentials or feedback text. `attempting` may mean a request was sent before a
crash; `unknown` means transport outcome is uncertain. `accepted` means GitHub
returned 204, not that a fix or PR completed. Other HTTP responses are `rejected`.

Do not delete records or the volume to retry. Reconcile uncertain attempts against
GitHub Actions and the resulting branch/PR before any operator-authorized recovery.
There is intentionally no automatic reset or expiration. Volume loss or independent
journals can permit duplicates; this is not an exactly-once external transaction.
Historical dispatches before this journal was introduced are not backfilled.
