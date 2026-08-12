---
name: lc-handoff
description: Close a work slice properly. Verify commit/push state, check docs are in step, update the persistent project memory, then write the "Next" block into the project HANDOFF so the next session opens grounded. Use when the user says "on ferme", "handoff", "wrap up", "c'est bon pour aujourd'hui", "close the session", or before stepping away from a work slice. The deterministic Stop hook already keeps HANDOFF fresh; this skill adds the judgment layer on top.
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

3. **Update project memory.** This is the piloted step: you are the live session
   with the full context, so you write the durable cross-session memory (a script
   cannot judge what mattered). `memory.py` does only the deterministic
   bookkeeping (dedup, soft-supersede, decay, cap, persist).
   - Compute `slug` = the cwd with every `/`, `.` and space replaced by `-`.
   - See what is already stored:
     `python3 ~/.claude/lex-claude/memory.py list <slug>`
     (prints `id<TAB>type<TAB>text` for the current live items).
   - From THIS session, decide the delta and pipe it as JSON to
     `python3 ~/.claude/lex-claude/memory.py apply <slug>`:
     - `new`: durable items this session established that are not already stored.
       Each `{"type": one of [decision,fact,thread,preference], "text": one
       concise sentence}`. Only things worth recalling in a future session
       (decisions made, stable facts, open threads/next steps, preferences), not
       transient chatter.
     - `supersede`: the `id`s of listed items this session made outdated (a
       decision reversed, a value changed, a thread closed). Be conservative:
       only when genuinely replaced. Soft-delete is recoverable, but do not
       supersede on a guess.
     - `reaffirm`: the `id`s of listed items this session confirmed still true.
   - Example:
     ```
     echo '{"new":[{"type":"decision","text":"Auth tokens are JWT."}],
            "supersede":["a1b2c3d4e5"],"reaffirm":["f6g7h8i9j0"]}' \
       | python3 ~/.claude/lex-claude/memory.py apply <slug>
     ```
   - If nothing durable changed this session, skip. Never invent items to fill.

4. **Write the Next block.** Edit the project's HANDOFF.md and replace the
   content between `<!-- LC_NEXT_BEGIN -->` and `<!-- LC_NEXT_END -->` (keep the
   markers, they survive regeneration) with at most 5 lines:
   - what state the work is truly in (not what was attempted, what IS)
   - the next slice, named concretely
   - any trap the next session must know (a gotcha, a decision pending, a
     server-side state not in git)

5. **Report.** Three lines max to the user: state, next slice, anything left
   hanging. No recap of the whole session.
