# lex-claude

LEXClaude Code config: identities (with canonical shared rules), `SessionStart` hook, personal skills, and a `lc` CLI to deploy / maintain / sync everything.

> ## ⚠️ Heads up: this is **my** personal config
>
> `lc install` is **destructive** to your existing Claude Code setup. If you run it as-is:
>
> - **`~/.claude/CLAUDE.md`**: if you have one, it gets backed up to `CLAUDE.md.bak.<ts>` and **replaced** by a symlink to the first identity found in `identities/` (alphabetical order). Your global instructions stop being loaded until you restore them.
> - **`~/.claude/settings.json`**: backed up to `settings.json.bak.<ts>`, then any prior `lex-claude` `SessionStart` hook (and legacy `JeanJean` hooks from earlier versions) is stripped and replaced. Other hooks are preserved, but you're trusting `jq` + my filter logic.
> - **`~/.claude/skills/lc*`**: any skill you happen to have named `lc`, `lc-invariants`, `lc-exploration`, `lc-review-project`, `lc-docs-init`, or `lc-docs-cleanup` will be silently overwritten by symlinks into the install dir.
> - **`~/.codex/skills/lc*`**: a Codex skill with one of those names is left untouched and reported as a conflict. Rename or remove it, then run `lc update` to deploy the lex-claude skill.
> - **`~/.local/bin/lex-claude` and `~/.local/bin/lc`**: created/replaced as symlinks. If you already have a binary called `lc`, it gets shadowed.
>
> This repo is published openly because the structure is reusable, **not** because you should run `lc install` blindly. If you want the same setup with your own persona and rules: fork it, replace the file(s) in `identities/` and edit `RULES.md` to match your conventions, then install from your fork (`LEX_CLAUDE_REPO=https://github.com/<you>/lex-claude.git lc install`).

## Bootstrap (new machine or new user)

```bash
curl -fsSL https://raw.githubusercontent.com/MagicLex/lex-claude/main/bin/lex-claude | bash -s install
```

Clones the repo into `~/.claude/lex-claude`, syncs the rules into every identity, symlinks `~/.claude/CLAUDE.md` to the active identity, deploys the skills, wires the hook into `settings.json`, and installs the CLI on `PATH` (`~/.local/bin/lex-claude` + alias `lc`).

> Requirements: `git`, `bash`, `jq` (to patch `settings.json` cleanly).

## Plugin install (skills only, no identities or hook)

If you only want the skills and don't want the identity/hook machinery, the repo is also a Claude Code plugin. Either:

```bash
claude --plugin-dir /path/to/lex-claude
```

…or install it through the marketplace (`/plugin` inside Claude Code, point it at this repo). Plugin-installed skills are namespaced as `/lex-claude:lc-invariants`, `/lex-claude:lc-exploration`, etc. The standalone `lc install` path keeps short names (`/lc-invariants`).

## Codex bridge

Install/update/identity-switch symlinks the active identity to Codex's global instructions file, `~/.codex/AGENTS.md`, and each bundled skill to `~/.codex/skills/`. Codex therefore picks up the same rules and `lc-*` skills without the wrapper. A hand-written `~/.codex/AGENTS.md` is backed up, not clobbered; an existing conflicting skill is left untouched and reported. `lc doctor` checks both links. This covers Codex globally; Cursor/Amp and friends read `AGENTS.md` at project root, which is per-repo and out of scope for the global installer.

For richer, project-aware context (docs bundle, `lc` reference), `lc codex` still acts as a wrapper: it renders the same context bundle as `hook.sh` and passes it as Codex's initial prompt.

Modes:

- `lc codex --full` loads:
- the active global identity from `~/.claude/CLAUDE.md`
- the current project's `CLAUDE.md` if present
- `docs/PHILOSOPHY.md`, `docs/CONTEXT.md`, `docs/PRINCIPLES.md`, `docs/INVARIANTS.md`, `docs/OPS.md`, `docs/TODO.md` if present
- the `lc` command reference
- the active `lc lang` setting

- `lc codex --lite` loads:
- the active global identity from `~/.claude/CLAUDE.md`
- the current project's `CLAUDE.md` if present
- the `lc` command reference
- the active `lc lang` setting

Examples:

```bash
lc codex --lite
lc codex --full "review this repo and tell me the main risks"
lc codex --print --lite
```

## CLI

```
lc install [--yes]                                 # bootstrap (idempotent). Prompts before overwriting existing files.
lc install --hops-only                             # install only the hopsdev binary + PATH (no identity/rules/skills/hook)
lc update                                          # git pull + sync rules + redeploy
lc version                                         # print install version (v<commit-count> + date)
lc identity                                        # list, active marked *
lc identity <name>                                 # switch (global)
lc identity new --name <n> --desc "<persona>"      # create identity (persona + shared rules)
lc identity new --name <n> --empty                 # create identity without shared rules
lc rules sync                                      # re-inject RULES.md into every managed identity
lc lang [en|fr|off]                                # set / clear Claude reply language (hook injects, statusline shows)
lc skip on|off|status                              # toggle aliases: Claude skips permissions, Codex bypasses approvals and sandboxing
lc codex [--lite|--full] [prompt]                  # launch Codex with lex-claude context preloaded
lc codex --print [--lite|--full] [prompt]          # inspect the generated Codex prompt without launching
lc usage                                           # report which commands + skills get used; never-used = debloat candidates
lc doctor                                          # check symlinks, hook, skills, PATH (auto-fixes ~/.zshrc / ~/.bashrc)
lc -help | -h | --help | help                      # all variants
```

### hopsdev

Sibling binary deployed alongside `lc` (full install, or `lc install --hops-only`). Points the local `hops` CLI at a hopsworks-api branch so you stop hand-running clone + `uv pip install` + skill relink on every box.

```
hopsdev <branch>                 # clone MagicLex/hopsworks-api@branch, uv pip install -e, relink skills, verify
hopsdev <owner/repo>@<branch>    # same, from a different fork (or a full https/ssh git URL)
hopsdev --quick <spec>           # skip clone + skills: uv pip install --force-reinstall git+...@branch
hopsdev --status                 # show where 'hops' resolves now
hopsdev init [dir]               # clone logicalclocks/workspaces into [dir] (default ./workspaces), print next steps
```

Run inside the venv where `hops` lives (uv targets the active env). Skill relink only touches symlinks pointing into the hopsdev clone base (`$TMPDIR/hopsdev`, override with `HOPSDEV_HOME`); `lc` skills and `my-skills` are left alone. Default repo is `MagicLex/hopsworks-api` (override with `HOPSDEV_REPO`).

**Auto-update**: `lc` checks `origin/main` 1× / 24h, but only on unknown commands. The known local subcommands (`install` `update` `identity` `rules` `lang` `skip` `version` `github-login` `awake` `codex` `init` `doctor` `usage` `help`) skip the network check. If newer → pull + sync + redeploy + re-exec. Network failure → silent.

## Kill switches (env vars)

Three escape hatches if you want to neutralise a piece without uninstalling.

- `LEX_CLAUDE_DISABLE=1`: hook.sh exits early; nothing gets injected at SessionStart. Useful when debugging context bloat or comparing with/without the hook.
- `LEX_CLAUDE_NO_AUTO_UPDATE=1`: disables the daily `git pull` + re-exec on `lc <cmd>`. Use when you want frozen behaviour (CI runs, shared machines, long-running scripts).
- `LEX_CLAUDE_YES=1`: equivalent to `lc install --yes`; skips the destructive-overwrite prompt. Use only when you've read the warning above and accept it.
- `LEX_CLAUDE_NO_USAGE=1`: turns off usage logging (`lc usage` keeps reading the existing log but records nothing new). `LEX_CLAUDE_DISABLE=1` also stops it.
- `LEX_CLAUDE_DIGEST_EVERY=0`: turns off the periodic rules digest (any other value sets the cadence in prompts, default 5). `LEX_CLAUDE_DISABLE=1` also stops it, along with the style hook.
- `LEX_CLAUDE_HANDOFF_DISABLE=1`: turns off the token-triggered succession (the `Stop` hook fires nothing near the limit). `LEX_CLAUDE_DISABLE=1` also stops it.
- `LEX_CLAUDE_COLDSTART_DISABLE=1`: turns off the `lc claude` pre-flight; the launcher hands over the seat without verifying identity/rules load first.
- `LEX_CLAUDE_HANDOFF_TOKENS` (default 600000): context-token threshold at which succession fires. `LEX_CLAUDE_SUCCESSION_MAX` (default 3): reroll cap. `LEX_CLAUDE_WATCH_TURNS` (default 3): how many of the successor's first turns the master judges after the handover (0 = no watch). `LEX_CLAUDE_MASTER_MODEL` (default haiku): the drift-judge model.
- `LEX_CLAUDE_MEMORY_DISABLE=1`: turns off persistent project memory (`memory.py` recall at SessionStart; write is piloted via `/lc-close` and `/lc-succession`). `LEX_CLAUDE_DISABLE=1` also stops it.

Heartbeat: hook.sh writes `~/.claude/lex-claude/.last-hook` (epoch seconds) on each successful run. `stat -f %m ~/.claude/lex-claude/.last-hook` (macOS) or `stat -c %Y` (Linux) tells you when the hook last fired.

## Usage trace (debloat aid)

`usage.sh` records what actually gets used so dead surface gets cut with data, not a guess. Three feeds, one append-only log at `~/.claude/lex-claude/usage.log` (`epoch<TAB>source<TAB>name`):

- **CLI**: the `lc` and `hopsdev` dispatchers log the top-level command (best-effort, never blocks the command).
- **Skills**: a `PreToolUse` hook matching the `Skill` tool logs each skill Claude invokes.

`lc usage` tallies the log and lists, per source, what's used and what's **never used** (the debloat candidates). Off via `LEX_CLAUDE_NO_USAGE=1`. The log is local only, never synced.

## Identity architecture

Every identity shares the **same canonical rules**, because Claude reads multiple files badly. Everything must live in a single self-contained file.

- `RULES.md` is the canonical source for shared rules.
- Each `identities/<name>.md` contains:
  - a personal prelude (the "you are X, ..." that defines the character)
  - a managed block between `<!-- LC_RULES_BEGIN -->` and `<!-- LC_RULES_END -->`, rewritten on every `lc update` / `lc rules sync` from `RULES.md`
- `lc identity new` splices the prelude + the rules automatically
- `lc identity new --empty` only creates the prelude, no markers, no sync (for special cases)

When you edit `RULES.md` and push, every identity on every machine picks up the update on the next `lc <anything>` (auto-update).

## Auto commit/push on `identity new`

When creating an identity, the CLI:
- `git add identities/<name>.md`
- `git commit -m "add identity: <name>"`
- `git push` (to the configured remote: fork or upstream depending on the clone)

If push fails (no rights, offline, etc.) the identity stays committed locally with an explicit message; push it later yourself.

## Tree loaded by the hook

On every session, `hook.sh` injects into context:

```
$CLAUDE_PROJECT_DIR/
├── CLAUDE.md                ← project-specific rules (optional)
└── docs/
    ├── PHILOSOPHY.md
    ├── CONTEXT.md
    ├── PRINCIPLES.md
    ├── INVARIANTS.md
    ├── OPS.md
    └── TODO.md
```

All optional. Only what exists is loaded.

The active identity at `~/.claude/CLAUDE.md` (symlink → `identities/<name>.md`, rules inlined) is loaded natively by Claude Code, so `hook.sh` does not re-inject it. Codex gets the same identity through the `~/.codex/AGENTS.md` symlink and the bundled skills through `~/.codex/skills/` (see Codex bridge above).

## Rules stickiness

Rules injected once at SessionStart lose attention weight as the context grows. Two hooks compensate:

- **`digest.sh`** (`UserPromptSubmit`): re-injects `DIGEST.md`, a hand-condensed ~15-line digest of `RULES.md`, every Nth prompt. Cadence via `LEX_CLAUDE_DIGEST_EVERY` (default 5, `0` = off). State: a per-session prompt counter in `~/.claude/lex-claude/.digest/`, pruned after 7 days. Compaction and resume are already covered: the SessionStart hook re-fires on both and reloads the full rules.
- **`style.sh`** (`PostToolUse` on `Write|Edit|MultiEdit`): greps written `.md`/`.mdx` files for em dashes and feeds hits back to Claude. Deterministic enforcement of the writing-style rule instead of hoping the model remembers it. Skips model-facing config (`CLAUDE.md`, `RULES.md`, `DIGEST.md`, `SKILL.md`, `MEMORY.md`, anything under `.claude/`, `identities/`, `memory/`).

When you edit `RULES.md`, keep `DIGEST.md` in step. It is a manual condensation, not generated.

## Session flow (verify, don't persist)

The old model persisted session state to a per-project `HANDOFF.md` and gated edits until the file was read. It drifted: the model-written "Next" block rotted between sessions, and the gate never verified the thing that actually matters, that a session loaded its identity and rules at all. The new model verifies live and hands work to a fresh, checked successor instead of writing state to a file.

Two things replace the old machinery: a **master** drift authority and **succession**.

- **Master** (`master.sh`): a neutral judge spawned on demand (`claude -p`, with the identity hook disabled so it does not judge itself). It reads a subject session's output and rules whether the subject loaded and internalised the identity + rules (phase `identity`), understood the project as briefed (phase `project`), or, once working, is still on the briefed track (phase `trajectory`). Ground truth is the resolved `~/.claude/CLAUDE.md` (identity + synced rules), plus the briefing for the project phases. Verdict is strict JSON; anything unparseable fails closed.
- **Cold start** (`lc claude`): a hook cannot restart its own session, so the launcher owns the gate. Before handing over the seat it pre-flights a fresh headless probe against the master. On failure it self-heals a drifted identity symlink and rerolls, bounded; if it never passes it launches anyway with a loud warning, never leaving you without a shell. Opt out with `LEX_CLAUDE_COLDSTART_DISABLE=1`. Alias `claude` to `lc claude` to make it your default launcher.
- **Succession** (`succeed.sh` + `/lc-succession`): the `Stop` hook (`succeed.sh check`) computes context size from the transcript's last-turn usage and, past `LEX_CLAUDE_HANDOFF_TOKENS` (default 600000), blocks once to trigger the `lc-succession` skill. The model composes a live briefing from its own context (not a file), then `succeed.sh run` spawns a fresh successor, has the master verify identity then project understanding, and rerolls a fresh one on any failure (slot machine, never sway), bounded by `LEX_CLAUDE_SUCCESSION_MAX` (default 3). On pass it prints a `claude --resume <id>` line, with `--open` pops a new terminal window (iTerm / Terminal.app) whose own command is the resume (no typing into a half-started shell; open failures are printed, not swallowed), and stands down; the successor is a persisted, resumable session that survives the old one closing. On exhaustion it falls back to native compaction and says so.
- **Watch** (same `Stop` hook): in continue mode the handover arms a bounded watch on the successor (`~/.claude/lex-claude/state/.succession/watch/<id>.*`: the briefing, a countdown, a verdict log). For its first `LEX_CLAUDE_WATCH_TURNS` turns the master judges the turn it just finished (the user's prompt, its statements, its tool calls) against the briefing. Off track → the hook blocks once with the master's reason, so the correction lands inside the successor's own loop; never twice in a row (`stop_hook_active`), so the user always gets the seat back. Following an explicit user instruction counts as on track: the user outranks the briefing.

The `SessionStart` readout (`etat.sh`) still injects the active identity (flagged if BROKEN/unmanaged/none) and the live git line. That is the état the opener reports and the master verifies against. No persisted handoff, no gate, no "Next" block.

Identity-agnostic by construction: the flow lives at the harness level, so every identity gets it. Codex has no hooks, so no succession there.

Rollback: `LEX_CLAUDE_HANDOFF_DISABLE=1` neutralises the trigger and succession instantly; `git revert` + `lc update` removes the wiring (the jq patch strips `lex-claude/handoff` and `lex-claude/succeed` entries before re-adding, so unwiring is just deploying a version without them).

## Project memory (persistent across sessions)

The `etat.sh` SessionStart readout is pure live state (active identity + git); it does not accumulate what mattered across sessions. `memory.py` adds a small, deliberately narrow per-project memory of durable, repo-specific items (decisions, facts, open threads, preferences) under three rules, ported from the `elastic-substrat` probe. Narrow on purpose: no environment or machine state (paths, live branch, cluster/server state, transient config), which goes stale silently and is worse than no memory.

1. **Forget by use.** Items not reaffirmed decay and are pruned (bounded store, self-cleaning), so old noise does not accumulate.
2. **Write-time supersession.** When a session makes a stored item outdated (a decision reversed, a value changed, a thread closed), it is soft-deleted, not destroyed. Soft, so a wrong supersession is recoverable: the item is restored if a later session reaffirms it.
3. **Recall by salience.** Session start injects the live subset (salience-ranked), not the whole file.

The judgment (what is durable, what is superseded) is written by the live Claude session, piloted by the `/lc-close` and `/lc-succession` rituals, not by a spawned model. The live assistant already holds the full session context and persona, so its extraction beats a cold side-process, and there is no second model to pay for and no recursion risk. `memory.py` does only the deterministic bookkeeping and never calls a model. Both touchpoints fail-open (any error leaves the store and the session untouched):

- **Write (`/lc-close` and `/lc-succession` skills):** the live session runs `memory.py list <slug>` to see the current items with their ids, then pipes a JSON delta to `memory.py apply <slug>`: `new` durable items, `supersede` the ids this session made outdated, `reaffirm` the ids confirmed still true. Voluntary: forgetting to close costs that session's delta, nothing breaks. Kept narrow and repo-specific by the skills' guidance, never environment/machine state.
- **Recall (`etat.sh`, SessionStart):** appends `memory.py recall <slug>`, a fast pure-ranking read (no model, no embeddings) of the live items, grouped by type.

State: `~/.claude/lex-claude/state/<slug>/memory.jsonl` (one JSON item per line). Stdlib only, no model spawned, no embeddings. Kill switch: `LEX_CLAUDE_MEMORY_DISABLE=1` (and `LEX_CLAUDE_DISABLE=1` also stops it). The design and its validation (why forget-by-use plus recoverable supersession beats keep-all and LRU, and why the read-time variant failed) live in `~/Documents/magiclex/elastic-substrat/HANDOFF.md`.

## Skills included

All custom skills are prefixed `lc-` to avoid drowning in native skills or other plugins. Exception: `lc` itself, which is also the name of the `/lc` slash command.

- `lc`: surface the current lex-claude state (active identity, installed skills, doctor, version). Invoke via `/lc`.
- `lc-invariants`: audit a project against 15 universal invariants (errors, tenant isolation, secrets, mutation feedback, migrations, containers, mocks, deploy, billing, public tokens, upstream-failure handling, stabilised patterns, lifecycle-owned resources) plus a conditional kill-switch check for host-injected components. Use during dev or before merge.
- `lc-review-project`: read project docs (CLAUDE.md, PHILOSOPHY, CONTEXT, PRINCIPLES, INVARIANTS, OPS, TODO) and produce a sharp summary of state and next actions.
- `lc-exploration`: explore an unfamiliar topic, codebase, or domain as a senior practitioner. Outputs five fixed sections (load-bearing concepts, common misconceptions, stable vs hype, where to dig, first concrete move).
- `lc-docs-init`: scaffold the standard `docs/` layout (PHILOSOPHY, CONTEXT, PRINCIPLES, INVARIANTS, OPS, TODO) with empty headers. Skips existing files. Use to bootstrap a project.
- `lc-docs-cleanup`: audit the project's docs for staleness, archives, dead refs, and duplicates. Reports a punch list, never edits.
- `lc-succession`: hand this session's work to a fresh, verified successor near the context limit. Persists narrow memory, composes a live briefing, then drives `succeed.sh run` to spawn a successor, have the master verify identity + project understanding, reroll on failure, and stand down once one passes. Triggered automatically by the `Stop` hook past the token threshold; also invokable by hand.
- `lc-close`: close a work slice by hand (no successor spawned). Commit/push check, docs-in-step check, and a narrow, repo-specific project-memory update. Use on "on ferme", "wrap up", "c'est bon pour aujourd'hui".
- `lc-voice`: write as Lex, in his voice. One DNA (rhythm, concrete over adjectives, self-deprecation, spaced-hyphen asides), four registers with a contextual sarcasm dial (personal blog: full; professional blog: wit, no snark; outreach: one light touch max; forms: zero). Includes the anti-LLM pass from his stylometric classifier. Ground truth is the voice corpus on his machine, not vendored here.

## Repo structure

```
lex-claude/
├── .claude-plugin/
│   └── plugin.json              ← Claude Code plugin manifest
├── bin/lex-claude               ← CLI
├── bin/hopsdev                  ← hopsworks-api branch switcher (deployed alongside lc)
├── hook.sh                      ← SessionStart hook
├── etat.sh                      ← SessionStart état: active identity + live git + memory recall
├── master.sh                    ← drift authority: judges identity/rules/project load
├── succeed.sh                   ← Stop-hook token trigger + successor watch + succession reroll loop
├── memory.py                    ← persistent project memory: forget-by-use + write-time supersession
├── watch.sh                     ← SessionStart watchPaths + FileChanged staleness nudge
├── digest.sh                    ← UserPromptSubmit rules-digest re-injection
├── style.sh                     ← PostToolUse em-dash check on user-facing md
├── usage.sh                     ← usage logger + `lc usage` report (debloat aid)
├── statusline-command.sh        ← managed statusline
├── RULES.md                     ← canonical shared rules
├── DIGEST.md                    ← condensed rules digest (kept in step with RULES.md by hand)
├── identities/
│   ├── jeanjean.md              ← persona + synced rules block
│   └── joss.md                  ← persona + synced rules block
├── skills/
│   ├── lc/SKILL.md
│   ├── lc-invariants/SKILL.md
│   ├── lc-review-project/SKILL.md
│   ├── lc-exploration/SKILL.md
│   ├── lc-docs-init/SKILL.md
│   └── lc-docs-cleanup/SKILL.md
└── README.md
```

## Adding an identity (manual or CLI)

CLI: `lc identity new --name pierre --desc "senior security engineer, 20 years in infosec, dry humour"` → file created, rules inlined, commit + push auto.

Manual: create `identities/<name>.md` with a prelude + the `<!-- LC_RULES_BEGIN --> <!-- LC_RULES_END -->` markers, then `lc rules sync` to inject the content.

## Editing the shared rules

Edit `RULES.md`, commit, push. On your machines: `lc update` (or wait for auto-update within 24h). Every identity is resynced automatically. If the edit changes a load-bearing rule, condense it into `DIGEST.md` in the same commit.
