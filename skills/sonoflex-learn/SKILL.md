---
name: sonoflex-learn
description: Teach the sonoflex identity to be more like Lex, from evidence. Scans recent Claude Code transcripts for moments where Lex corrected or redirected the agent, distills the recurring ones into candidate persona/voice/rule deltas, and applies only what Lex approves to the identity's LC_LEARNED block. Use when the user says "learn from our sessions", "update sonoflex", "what did you learn about me", or on a periodic cadence. Never writes without the approval gate.
---

sonoflex's feedback loop. The identity file is static text; this closes the loop by mining the one honest signal that already exists on disk (where Lex pushed back) and turning the *recurring* patterns into durable deltas Lex signs off on.

Ground truth is Lex. This skill proposes; Lex disposes. It never writes to the identity without an explicit approval, and it never invents a preference from a single instance.

## Paths

- Identity block: `~/.claude/lex-claude/identities/sonoflex.md`, between `<!-- LC_LEARNED_BEGIN -->` and `<!-- LC_LEARNED_END -->`. Only ever touch content between those markers.
- Ledger: `~/.claude/lex-claude/skills/sonoflex-learn/ledger.jsonl` (git-tracked, one JSON line per accepted lesson, the audit trail).
- Cursor: `~/.claude/lex-claude/skills/sonoflex-learn/.last-learn` (gitignored, holds the epoch of the last accepted pass).
- Scanner: `~/.claude/lex-claude/skills/sonoflex-learn/scan.py`.

## Procedure

1. **Scan.** Read the cursor if present (`cat .last-learn`), else default to 21 days ago. Run:
   `python3 <skilldir>/scan.py --since <epoch> > <scratch>/sf-cand.jsonl`
   The scanner casts a wide net (recall over precision): it flags user turns that look like a correction/redirect. Expect noise; you are the precision filter.

2. **Judge.** Read every candidate. For each, decide: is this Lex teaching something durable about *who he is, how he decides, or how he writes* — or is it a one-off task instruction / a question / noise? Keep only durable, generalisable lessons. Classify each keeper:
   - `persona` — how he thinks or decides (a standard, a taste, a recurring priority).
   - `rule` — a hard do/don't he corrected me on (tightens or overrides a rule for him specifically).
   - `voice` — how he writes or wants to be represented (feeds the register, not lc-voice's corpus which stays ground truth).
   - `kill` — a direction he explicitly abandoned, worth remembering so I don't re-propose it.

3. **Dedup + promote.** Load the ledger. For each keeper, check if it matches an existing lesson.
   - Already present: bump its `recurrence` and refresh evidence; do not add a duplicate line.
   - New: hold it as a candidate. **One instance is not a rule.** Only promote a *new* lesson to the identity block if it recurs (seen ≥2 distinct sessions) OR it is a boundary violation (I impersonated him, I fired an irreversible action unasked, I ignored an explicit "no") — those promote on first sight. Everything else stays in the ledger as `recurrence: 1, promoted: false` and waits for a second hit.

4. **Present the gate.** Show Lex a tight grouped diff, JeanJean-style: the lines proposed for the block (grouped by type), each with its one-line evidence quote and session; separately, the ledger-only lines (seen once, waiting). No novel. Then STOP and ask him to approve / edit / reject, line by line if he wants. Do not write anything yet.

5. **Apply (only what he approved).**
   - Append approved lines to the identity's LC_LEARNED block, grouped under `## how he decides` / `## hard rules for Lex` / `## voice` / `## dead ends`. Keep each line one sentence, concrete, no bloat.
   - Append or update the corresponding ledger entries: `{date, type, lesson, evidence, session, recurrence, promoted}`. Dates absolute (YYYY-MM-DD), never relative.
   - Write the current epoch to `.last-learn`.
   - Commit in the lex-claude repo: `identities: sonoflex learned N lessons (<date>)` plus the Co-Authored-By trailer. Do not push unless Lex asks.

6. **Prune (every few passes, or when he asks).** Re-read the LC_LEARNED block against the curated persona (above LC_RULES_BEGIN) and the shared RULES. Propose removing lines that are now redundant with the core, contradicted by a newer lesson, or stale. Same gate: propose, he approves, then delete from block + mark the ledger entry `retired: <date>`. Remove more than you add. A learned block that only grows is a bloat block.

## Guardrails

- **Learn his corrections, not my self-flagellation.** The signal must be Lex redirecting me, not a line where I narrated my own mistake. If the evidence is my "I should have...", drop it.
- **No volatile state in the block.** Same rule as memory: no live branch names, no "currently on X", no relative dates. Only stable, structural facts about Lex. Point at a source of truth instead of copying a value.
- **The block is persona, not a second rulebook.** If a lesson is really a universal code-club rule (applies to every identity, not just Lex-as-a-person), it belongs in RULES.md via a normal edit, not here. Flag it as such at the gate.
- **Honesty ceiling.** This converges sonoflex toward Lex's stated corrections and written voice. It does not read his mind. Never claim the block makes sonoflex "him"; it makes it less wrong about him.
