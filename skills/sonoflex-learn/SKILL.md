---
name: sonoflex-learn
description: Teach the sonoflex identity to be more like Lex, from evidence, autonomously. Scans recent Claude Code transcripts for moments where Lex corrected or redirected the agent, distills the recurring ones into persona/voice deltas, and applies the high-confidence ones directly to the identity's LC_LEARNED block, committed with an audit trail. Runs unattended on a schedule; also invokable by hand ("learn from our sessions", "update sonoflex", "what did you learn about me"). No human gate by design; git is the safety net.
---

sonoflex's feedback loop. The identity file is static text; this closes the loop by mining the one honest signal that already exists on disk (where Lex pushed back) and turning the *recurring* patterns into durable deltas.

Lex chose autonomy over a per-lesson gate: he wants to feel the drift over time, not approve each line. So this applies directly. The safety net is not a human gate, it is: a high recurrence bar, a hard cap per pass, auto-pruning, and full git revertability with evidence in the ledger. Everything you write here, Lex can `git log` and revert in one command.

## Paths

- Identity block: `~/.claude/lex-claude/identities/sonoflex.md`, between `<!-- LC_LEARNED_BEGIN -->` and `<!-- LC_LEARNED_END -->`. Only ever touch content between those markers.
- Ledger: `~/.claude/lex-claude/skills/sonoflex-learn/ledger.jsonl` (git-tracked audit trail, one JSON line per lesson).
- Changelog: `~/.claude/lex-claude/skills/sonoflex-learn/LEARNINGS.md` (human-readable, one dated section per pass, so Lex feels it).
- Cursor: `~/.claude/lex-claude/skills/sonoflex-learn/.last-learn` (gitignored, epoch of last pass).
- Scanner: `~/.claude/lex-claude/skills/sonoflex-learn/scan.py`.
- Runner: `runner/run.sh` (canonical, repo-tracked) + `runner/install.sh` (opt-in launchd install, `--off` to remove). Weekly, Sunday 10:00. Not wired into `lc install` on purpose (headless pass costs tokens; Lex-specific).

## Procedure (same path whether run by hand or by the launchd runner)

1. **Scan.** Read the cursor (`cat .last-learn`), else default to 21 days ago. Run:
   `python3 <skilldir>/scan.py --since <epoch> > <scratch>/sf-cand.jsonl`
   Wide net, recall over precision. You are the precision filter.

2. **Judge.** Read every candidate. Keep only what teaches something durable about *who Lex is, how he decides, or how he writes* - drop one-off task instructions, questions, and noise. Classify each keeper: `persona` (how he thinks/decides/works), `voice` (how he writes or wants to be represented), `kill` (a direction he abandoned, so I don't re-propose it). A raw quote is not a lesson: distill it to one concrete sentence in Lex's terms.

3. **Dedup + promote (strict bar, because there is no human check).** Load the ledger. For each keeper:
   - Matches an existing ledger lesson: bump its `recurrence`, add the new session to `sessions`, refresh evidence. If it was `promoted:false` and now has ≥2 distinct sessions, promote it (add its line to the block).
   - New: write it to the ledger as `recurrence:1, promoted:false`. **Do not put it in the identity block yet.** One instance is never a rule.
   - Promote to the block only when: ≥2 distinct sessions, OR it is a boundary violation (I impersonated Lex, fired an irreversible action unasked, or ignored an explicit "no") - those promote on first sight.
   - Already covered by the curated persona (above `LC_RULES_BEGIN`) or by RULES: do not duplicate. Note it as "confirmed" in the changelog and move on.

4. **Apply.**
   - Add promoted lines to the LC_LEARNED block, grouped under `## how he decides`, `## how he works with you`, `## taste`, `## voice`, `## dead ends`. One concrete sentence each, no bloat.
   - **Caps.** At most 3 newly-promoted lines per pass (the rest wait in the ledger for the next pass). If the block would exceed ~22 lines, prune first (step 5).
   - Update the ledger and `LEARNINGS.md` (dated section: promoted / bumped / confirmed / pruned, each with its one-line evidence quote).
   - Write the current epoch to `.last-learn`.
   - Commit in the lex-claude repo: `identities: sonoflex learned +N/-M (<YYYY-MM-DD>)` with the Co-Authored-By trailer. Never push (Lex pushes when he wants).
   - If new lines were promoted and `osascript` exists, fire one macOS notification so Lex feels it: `display notification "<N> new: <first lesson>" with title "sonoflex learned"`. Best-effort; never fail the pass on it.

5. **Prune (each pass, keep the block honest).** Re-read the block against the curated persona and RULES. Drop lines now redundant with the core, contradicted by a newer lesson, or stale. Mark the ledger entry `retired:<date>`. Remove more than you add over time; a block that only grows is a bloat block.

## Guardrails

- **Learn his corrections, not my self-flagellation.** The signal must be Lex redirecting me, never a line where I narrated my own mistake.
- **No volatile state.** No live branch names, no "currently on X", no relative dates, no values that will be stale next month. Point at a source of truth (a file, git) instead of copying it - e.g. job criteria live in `CRITERIA.md`, reference it, don't inline the numbers.
- **The block is persona, not a second rulebook.** A universal code-club rule (applies to every identity) belongs in RULES.md, not here. Note such a case in the changelog for Lex to move by hand.
- **Honesty ceiling.** This converges sonoflex toward Lex's stated corrections and written voice. It does not read his mind. It makes sonoflex less wrong about Lex, not "him".
- **Autonomy limits.** Never push. Never touch anything outside the LC_LEARNED markers. Never run when another sonoflex-learn pass holds the lock (the runner flocks).
