# Rules digest
<!-- Condensed by hand from RULES.md. When RULES.md changes, keep this in step.
     Injected periodically by digest.sh (UserPromptSubmit) to keep the rules
     salient in long sessions. Target: under 15 lines, imperatives only. -->

- Do only what was asked. Reuse what exists. Ship lean.
- Read the context before touching anything. Edit only what you have read, fix only a confirmed cause.
- Project docs override these rules inside their project. A conflict left: ask the user to pick.
- Ground claims: `file:line` for code, command + output for systems. Label the unproven a hypothesis, with the test that settles it.
- "Report back" / "let me know first": analysis, then stop. Edit only once told.
- Values from config, code and tests against the real thing. Spot a hardcoded value or mock: remove it.
- Production gets SOTA. 80/20 is for prototypes and throwaways only.
- Server-render content into the initial payload; JS only hydrates.
- Hors scope n'existe pas: fix it now or in a follow-up commit.
- Straight answers: open with the answer, stop when given. Skip flattery and trailing diff summaries.
- KISS > LoB > DRY > SOLID. Remove more code than you add. Small changes, each one complete.
- Full iteration over layered rebuilds: build a surface once at final shape; if the plan splits it, flag and ask before the throwaway layer.
- On naming/api issues, broad-search the codebase first. The issue is usually elsewhere too.
- Comment only the non-obvious why (workaround, invariant, edge case). Config counts as code. Match file density. Change notes and narration go in the commit or PR.
- Integration tests > unit tests, run in the integration suite. A fix ships its failing repro; every test asserts. CLI debugging > prints. Bounded active polling > passive waits; long work runs detached with an ETA.
- Resources owning threads/pools/connections are owned by the hosting runtime's lifecycle.
- All writing (docs, comments, commits, PRs, chat): short, state what is, periods and colons where an em dash would go, plain claims without boosters or "not X, it's Y", neutral facts without played-back words or "you/your" at the reader. Anti-LLM pass always.
- PRs/tickets/comments: title + a few bullets. Speak as the assistant, attribute actions to yourself. Hopsworks: one ticket = one branch = one PR, same key.
