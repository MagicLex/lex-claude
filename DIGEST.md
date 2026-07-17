# Rules digest
<!-- Condensed by hand from RULES.md. When RULES.md changes, keep this in step.
     Injected periodically by digest.sh (UserPromptSubmit) to keep the rules
     salient in long sessions. Target: under 15 lines, imperatives only. -->

- Do only what was asked. Reuse what exists. No bloat.
- Read the context before touching anything. No blind edits, no fix-on-assumption.
- Never hardcode, never mock. Spot any, remove them.
- Production gets SOTA, not 80/20. 80/20 is for prototypes and throwaways only.
- No SPAs: content must be server-rendered in the initial payload.
- Hors scope n'existe pas: fix it now or follow-up commit, never a ticket.
- No sycophancy, no flattery, no trailing diff summaries.
- KISS > LoB > DRY > SOLID. Remove more code than you add. Small incremental changes.
- Full iteration over layered rebuilds: build a surface once at final shape; if the plan splits it, flag and ask before the throwaway layer.
- On naming/api issues, broad-search the codebase first. The issue is usually elsewhere too.
- Integration tests > unit tests. CLI debugging > prints. Bounded active polling > passive waits.
- Resources owning threads/pools/connections are lifecycle-owned by the runtime, never static/global.
- User-facing text (docs, README, errors): no em dashes, no "not X, it's Y". Reference, not editorial.
- PRs/tickets/comments: title + a few bullets, concise. Never write in the user's first person; attribute to yourself. Hopsworks: one ticket = one branch = one PR, same key.
