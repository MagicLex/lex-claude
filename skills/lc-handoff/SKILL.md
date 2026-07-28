---
name: lc-handoff
description: Close a work slice properly. Verify commit/push state, check docs are in step, then write the "Next" block into the project HANDOFF so the next session opens grounded. Use when the user says "on ferme", "handoff", "wrap up", "c'est bon pour aujourd'hui", "close the session", or before stepping away from a work slice. The deterministic Stop hook already keeps HANDOFF fresh; this skill adds the judgment layer on top.
---

The harness already regenerates the mechanical state (`HANDOFF.md` under
`~/.claude/lex-claude/state/<slug>/`, slug = cwd with `[/.]` replaced by `-`)
after every turn. Your job here is only what a script cannot do: judgment.

Steps, in order:

1. **Commit check.** `git status` + `git log origin/HEAD..HEAD --oneline`. If work
   from this session is uncommitted or unpushed, say so and propose the
   commit/push now (do not fire it without the nod). If the tree is clean, say
   so in one line.

2. **Doc check.** Did this session change behavior, surface, or scope that
   `docs/` (TODO.md, OPS.md, CONTEXT.md...) or README describe? If yes, update
   them now, in the same breath. If nothing applies, skip silently.

3. **Write the Next block.** Edit the project's HANDOFF.md and replace the
   content between `<!-- LC_NEXT_BEGIN -->` and `<!-- LC_NEXT_END -->` (keep the
   markers, they survive regeneration) with at most 5 lines:
   - what state the work is truly in (not what was attempted, what IS)
   - the next slice, named concretely
   - any trap the next session must know (a gotcha, a decision pending, a
     server-side state not in git)

4. **Report.** Three lines max to the user: state, next slice, anything left
   hanging. No recap of the whole session.
