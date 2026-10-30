# API tests and authentication

Run `python -m pytest -v` in this directory. The suite supplies temporary storage,
synthetic keys and an in-memory rate limiter. Network connections are rejected,
and no Redis, Postgres, LLM account or live webhook is needed. Webhook success
checks use an async mock; rejected dispatch requests must leave no dispatch file
and make no webhook call.

Admin logins are disabled unless their respective `ADMIN_PASSWORD` or
`HUE_PASSWORD` is explicitly configured and nonempty. There are no default admin
passwords. Configure them in the deployment environment; never commit them.

`POST /feedback/{feedback_id}/dispatch-fix` requires a Bearer JWT with
`feedback.dispatch` or the existing admin wildcard permission. Ordinary feedback
submission keys do not grant dispatch permission. Invalid or expired JWTs return
401. This is a source behavior change; no deployment settings are changed by the
repository update.
