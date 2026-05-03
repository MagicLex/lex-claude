---
name: lc-invariants
description: Audit a project against universal production invariants (errors, secrets, tenant isolation, mutations feedback, migrations, containers, mocks, deploy, billing, public tokens, upstream-failure handling). Use during dev review or before merging significant changes.
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
11. **Billing & plan resolution** — documented chain (`plan_override → subscription → free`), instant suspension check, payment provider acts as Merchant of Record (we never handle card data).
12. **Public tokens hashed** — share/public links looked up by SHA256 hash, never plaintext; secret shown once at creation.
13. **Upstream failure → hide, not stale** — when a data source or background job fails past its threshold (heartbeat lost, crawler down, sync errored), the read path **hides** the affected entity. Never serve stale data labelled as fresh.

**Conditional — host-injected systems only** (agents, collectors, hooks, sidecars):

14. **Kill switch & silent failure** — env-var disable without restart (`<NAME>_DISABLE=1`); on its own failure the injected component **silently skips**, never crashes the host process; heartbeat written to local disk for outside observability.

End with a one-line verdict: green if all applicable pass, red with the failed numbers if any fail.
