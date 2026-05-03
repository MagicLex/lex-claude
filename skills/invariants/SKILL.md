---
name: invariants
description: Audit a project against universal production invariants (errors, secrets, tenant isolation, mutations feedback, migrations, containers, mocks, deploy). Use during dev review or before merging significant changes.
---

Pass the current project under these checks. For each: search the code, report **PASS / FAIL / N/A** with a one-line reason and a file ref. Don't fix unless asked.

1. **Errors standardized** — single helper produces `{code, message, hint}`; no raw `HTTPException`/`throw new Error("...")` in API/handlers.
2. **Mutations give feedback** — every user-triggered action surfaces success/error (toast, status, notification). No silent mutations.
3. **Secrets safe** — env-based, never in logs/responses/disk; encrypted at rest if persisted.
4. **Tenant isolation** — every data route validates workspace/user membership; no global queries; RBAC enforced.
5. **No mocks / no hardcoded values** in production paths.
6. **Idempotent migrations** — schema versioned, `IF NOT EXISTS` patterns, no manual DB tweaks.
7. **Containers non-root** — explicit user, no writes to `/app/` at runtime.
8. **Stale-state reapers** — long-lived state (jobs, sessions, heartbeats) has periodic cleanup with thresholds.
9. **Destructive actions explicit** — confirmation step + reversibility (Reset / undo) where data can be lost.
10. **Manual deploy** — no auto-deploy webhooks; rebuilds scoped to changed services.

End with a one-line verdict: green if all pass, red with the failed numbers if any fail.
