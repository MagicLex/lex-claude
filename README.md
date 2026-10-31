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

Codex hooks and succession require Python 3.11+ and a Codex version with native hooks (tested with `codex-cli 0.164.0`). Install/update merges SessionStart, PostToolUse, and Stop handlers into `$CODEX_HOME/hooks.json` and adds a native context meter when no custom `tui.status_line` exists. Existing handlers and custom status lines are preserved. `CODEX_HOME` takes precedence over `CODEX_DIR`, then defaults to `~/.codex`.

After installation, review and trust the new handlers in Codex's `/hooks`, then start a fresh session. Codex skips untrusted hooks. Hook trust is managed by Codex, not by the installer. See [Codex hooks](https://learn.chatgpt.com/docs/hooks).

`lc tokens --json` reads the exact session selected by `CODEX_THREAD_ID`; outside a session, use `lc tokens --session <id>`. Context usage comes from the latest `token_count.info.last_token_usage.total_tokens`. Cached input is already included. Lifetime usage is reported separately. Missing usage is reported as unknown, with exit status 1. The reader does not infer usage from file size, choose a session by cwd, or reuse a count from before compaction.

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
lc tokens --session <id> --json
```

## CLI

### Additional Claude accounts

Create a separate configuration directory and share the reusable settings:

```bash
mkdir -m 700 "$HOME/.claude-alt"
for name in CLAUDE.md settings.json skills rules agents commands hooks statusline-command.sh; do
  [ ! -e "$HOME/.claude/$name" ] || ln -s "$HOME/.claude/$name" "$HOME/.claude-alt/$name"
done
```

Add this function to `~/.zshrc` or `~/.bashrc`:

```bash
claude-alt() { CLAUDE_CONFIG_DIR="$HOME/.claude-alt" command lex-claude claude "$@"; }
```

Open a new terminal, run `claude-alt`, and sign in with the second account.
`claude` and `claude-alt` can run concurrently. Credentials and session history
stay separate. Settings, identity, skills, and hooks are shared. Settings edits
in either account apply to both. Plugins and user MCP connections need separate
setup. Do not copy `.claude.json` or credential files between accounts.

For a third account, create `~/.claude-alt2` with the same shared settings:

```bash
mkdir -m 700 "$HOME/.claude-alt2"
for name in CLAUDE.md settings.json skills rules agents commands hooks statusline-command.sh; do
  [ ! -e "$HOME/.claude/$name" ] || ln -s "$HOME/.claude/$name" "$HOME/.claude-alt2/$name"
done
```

Add this function to the same shell configuration file:

```bash
claude-alt2() { CLAUDE_CONFIG_DIR="$HOME/.claude-alt2" command lex-claude claude "$@"; }
```

Open a new terminal, run `claude-alt2`, and sign in with the third account.

For a fourth account, repeat the commands above with `claude-alt3` in place of
`claude-alt2`. Open a new terminal, run `claude-alt3`, and sign in with that account.

When one account hits its usage limit, `lc move --to <account>` moves every
live session of every other account, or the ids given, into the target
account. `main` is `~/.claude`, any other name is `~/.claude-<name>`
(`--to alt3` targets `~/.claude-alt3`). Each transcript is symlinked into the
target's `projects/`, so both accounts append to one file. The old process is stopped and
`--resume <id>` is typed into the same herdr pane with a kickoff prompt.
Folder trust is accepted only where the source account already trusts the
folder. Background agents, shells and monitors do not survive the move.
Sessions outside herdr are skipped with a printed resume command. Sessions map
to panes through the session id herdr's Claude integration reports
(`herdr agent list`).
`--dry-run` lists what would move.

### Room

`lc say MESSAGE` types a broadcast into the herdr pane of every live Claude
session (every account) and Codex session whose cwd is in the current repo or
one of its worktrees, except the caller's own. A Claude session is named by its
session name, a Codex session by its herdr workspace label. The header `[room ID] Broadcast from
Lex` tells the session the text did not come from its own chat. `--to NAME`
(repeatable) limits it to named sessions. A session with an open dialog
(herdr status `blocked`) is reported as `FAIL`. herdr cannot see a draft in
the prompt: the broadcast joins it and is submitted with it.

A session answers with `lc reply ID "text"`, never in its own chat. Replies
are appended to `~/.claude/lex-claude/state/room/ID.log`, and `say` prints them
until every reached session answered or `--wait MIN` minutes (default 5, 0 for
no wait) pass. `lc room ID` prints them later.

### Lane

`lc lane [TASK]` opens a new herdr workspace at the repo root running `lc claude`,
with the repo's `docs/LANE.md` as the first prompt. `{task}` in that file is
replaced by TASK, or by "open TODO work" without one. The kickoff text lives in
the project, next to its team rules. `--account main|alt|alt2|...` picks the
Claude account (same names as `lc move`); without it the lane runs on the
caller's account.

Transcript lookup and successor launches honor `CLAUDE_CONFIG_DIR`. The `lc`
installer and identity commands manage the shared configuration in `~/.claude`.

### Commands

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
lc tokens [--session ID] [--json]                 # Codex context usage and handoff threshold
lc move --to <account> [--dry-run] [ID...]         # resume live sessions on another account
lc say [--to NAME]... [--wait MIN] MESSAGE         # broadcast to every live session of this repo
lc reply ID TEXT                                   # answer a broadcast (run by the receiving session)
lc room ID                                         # print the replies to a broadcast
lc lane [--account NAME] [TASK]                    # start a lane with the repo's docs/LANE.md as first prompt
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

**Auto-update**: `lc` checks `origin/main` 1× / 24h, but only on unknown commands. The known local subcommands (`install` `update` `identity` `rules` `lang` `skip` `version` `github-login` `awake` `codex` `init` `doctor` `usage` `tokens` `help`) skip the network check. If newer → pull + sync + redeploy + re-exec. Network failure → silent.

### Agent Chrome

`lc install`/`lc update` (macOS) runs a dedicated Chrome for agent-browser:

- LaunchAgent `~/Library/LaunchAgents/com.lex-claude.agent-chrome.plist` (`RunAtLoad`, `KeepAlive`) starts real Chrome with `--remote-debugging-port=9333 --user-data-dir=~/.chrome-agent`. Port override: `LEX_CLAUDE_AGENT_CHROME_PORT`.
- `~/.agent-browser/config.json` gets `"cdp": "<port>"`, so every `agent-browser` call attaches there with no flag.

The `chrome://inspect` toggle (Chrome 144+) asks "Allow remote debugging?" on every new CDP connection, and agent-browser up to v0.38.2 deletes `DevToolsActivePort` while that prompt is pending ([#2041](https://github.com/vercel-labs/agent-browser/issues/2041)). The port flag has no prompt. Since Chrome 136 it needs a non-default `--user-data-dir` ([Chrome blog](https://developer.chrome.com/blog/remote-debugging-port)), so logins live in `~/.chrome-agent`: log in once in that window.

```
lc doctor                                                     # ok    agent-chrome listening on 9333
launchctl bootout gui/$(id -u)/com.lex-claude.agent-chrome   # stop it (lc update starts it again)
```

Tabs in the user's own Chrome (sign-in and OAuth flows) still need `--auto-connect` and one Allow click per connection. agent-browser finds that Chrome through `~/Library/Application Support/Google/Chrome/DevToolsActivePort`; macOS denies the terminal app read access to it until the app has Full Disk Access (System Settings, Privacy & Security). Without it: "No running Chrome instance found".

### agent-browser-bg

Stock agent-browser (up to v0.39.2) calls `Page.bringToFront` when it creates or switches tabs, so it pulls Chrome over whatever app you are in. Upstream issue [#1247](https://github.com/vercel-labs/agent-browser/issues/1247), fix in PR [#1880](https://github.com/vercel-labs/agent-browser/pull/1880), not merged yet. Until it ships, build v0.39.2 plus that PR as a separate binary and pin brew to the same base:

```
brew install rust
git clone https://github.com/vercel-labs/agent-browser.git && cd agent-browser
git checkout -b bg v0.39.2
git fetch origin pull/1880/head:pr-1880 && git cherry-pick pr-1880
cd cli && cargo build --release
ln -sf "$PWD/target/release/agent-browser" ~/.local/bin/agent-browser-bg
brew upgrade agent-browser && brew pin agent-browser   # stock stays at the same base
```

Check: `agent-browser-bg tab new https://example.com` opens a tab and your terminal keeps focus. Background tabs cannot be screenshotted; run `agent-browser-bg bringtofront` first. Once upstream ships the fix: `brew unpin agent-browser && brew upgrade agent-browser`, delete the clone and the symlink, and drop the `agent-browser-bg` line from `RULES.md`.

## Kill switches (env vars)

Three escape hatches if you want to neutralise a piece without uninstalling.

- `LEX_CLAUDE_DISABLE=1`: hook.sh exits early; nothing gets injected at SessionStart. Useful when debugging context bloat or comparing with/without the hook.
- `LEX_CLAUDE_NO_AUTO_UPDATE=1`: disables the daily `git pull` + re-exec on `lc <cmd>`. Use when you want frozen behaviour (CI runs, shared machines, long-running scripts).
- `LEX_CLAUDE_YES=1`: equivalent to `lc install --yes`; skips the destructive-overwrite prompt. Use only when you've read the warning above and accept it.
- `LEX_CLAUDE_NO_USAGE=1`: turns off usage logging (`lc usage` keeps reading the existing log but records nothing new). `LEX_CLAUDE_DISABLE=1` also stops it.
- `LEX_CLAUDE_DIGEST_EVERY=0`: turns off the periodic rules digest (any other value sets the cadence in prompts, default 5). `LEX_CLAUDE_DISABLE=1` also stops it, along with the style hook.
- `LEX_CLAUDE_HANDOFF_DISABLE=1`: turns off the token-triggered succession (the `Stop` hook fires nothing near the limit). `LEX_CLAUDE_DISABLE=1` also stops it.
- `LEX_CLAUDE_COLDSTART_DISABLE=1`: turns off the `lc claude` pre-flight; the launcher hands over the seat without verifying identity/rules load first.
- `LEX_CLAUDE_HANDOFF_TOKENS` (default 600000): Claude context-token threshold at which succession fires. `LEX_CLAUDE_SUCCESSION_MAX` (default 3): reroll cap. `LEX_CLAUDE_MASTER_MODEL` (default haiku): the drift-judge model.
- `LEX_CODEX_HANDOFF_PERCENT` (default 95): Codex handoff threshold as a percentage of its native auto-compaction limit. The Claude token cap does not apply. The limit uses the reported window, model metadata, and `model_auto_compact_token_limit` from the Codex configuration. Unknown context does not trigger a handoff. `LEX_CODEX_MASTER_MODEL` selects the Codex judge model; unset uses Codex config. `LEX_CODEX_SUCCESSION_TIMEOUT` (default 180 seconds) bounds each Codex verification call. The Claude model pin is not used for Codex.
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

## Session flow

Identity and rules loading is verified live by a judge. Work near the context limit is handed to a fresh, verified successor. Nothing is persisted between sessions except the project memory below.

- **Master** (`master.sh`). A neutral judge spawned on demand with `claude -p` and the identity hook disabled, so it does not judge itself. Ground truth is the resolved `~/.claude/CLAUDE.md`, plus the briefing for the project phases. Two phases: `identity` (did the subject load the identity and rules) and `project` (did it understand the briefed work). Verdict is strict JSON. Anything unparseable fails.
- **Cold start** (`lc claude`). The launcher runs the identity self-report as turn 1 of a fresh session and has the master judge it before handing over the seat. On failure it repairs the identity symlink and rerolls, up to `LEX_CLAUDE_SUCCESSION_MAX` times, then launches anyway with a warning. Skip with `LEX_CLAUDE_COLDSTART_DISABLE=1`.
- **Succession** (`succeed.sh` + `/lc-succession`). The `Stop` hook reads the context size from the transcript. Past `LEX_CLAUDE_HANDOFF_TOKENS` it blocks once and invokes the skill. The skill writes a briefing from the live context, then `succeed.sh run` spawns a successor, has the master check its identity and then its first move on the work, and rerolls on failure. On pass it prints `claude --resume <id>`, plus a kickoff prompt in continue mode so the successor starts working without a nudge. With `--open` it opens the resume in a new herdr workspace, iTerm window, or Terminal window, through `lc claude`, so both sessions share the same model and permission mode. Successors, lanes and `lc claude` seats drop every inherited `CLAUDECODE` and `CLAUDE_*` variable except `CLAUDE_CONFIG_DIR`: a terminal app started from inside Claude leaks them into every shell, and a session carrying `CLAUDE_CODE_CHILD_SESSION` saves no transcript. On pass it also records the lineage (`state/lineage/<id>`: generation and predecessor id), which the statusline shows as `genN ←<id>`. On exhaustion it stops and native compaction takes over.
- **Retirement** (`retirement.py`). The resumed successor acknowledges the handover through its hooks. The parent is retired right away, with no review window. The helper checks the recorded parent process identity and herdr pane, closes that pane, and stops the process. A failed launch leaves the parent available. Retired sessions are blocked from running tools if resumed. Outside herdr, the process stops but the terminal tab remains.

`etat.sh` at `SessionStart` injects the active identity and the live git line. That is the état the opener reports and the master verifies against.

`herdr-name.sh` at `SessionStart` names the herdr workspace after the session's agent name (the `ListAgents` / `SendMessage` name, e.g. `hopsable-87`, from `~/.claude/sessions/<pid>.json`). A title that already holds the name is left alone. A title that starts with an older name of the same project gets that prefix swapped and keeps the rest, so `hopsable 91 (lead)` becomes `hopsable-6d (lead)`. A default title (`Claude Code`, a path, the dir name, `successor <id>`) becomes the name. Any other title gets the name prefixed. No-op outside herdr.

Codex uses `succeed.sh --runtime codex run [--open] [--briefing <file>]`. `codex.py` starts a persisted `codex exec` session, verifies identity and the opening move through a Codex judge, and prints an exact `codex resume` command. Verification is read-only. Resume carries the predecessor's model, reasoning effort, sandbox mode, and approval policy when available.

Codex PostToolUse injects one notice when measured context crosses the threshold; Stop requests one continuation if needed. Handoff defaults to 95% of the native auto-compaction limit, leaving room for the briefing. A large tool result can still cross both thresholds before a hook runs. SessionStart, PreToolUse, and UserPromptSubmit also handle retirement. `--open` uses the same macOS terminal launcher as Claude; it does not create a Codex desktop tab. If no terminal opens, use the printed resume command.

Kill switch: `LEX_CLAUDE_HANDOFF_DISABLE=1` disables the trigger and the succession. `git revert` + `lc update` removes the wiring.

Retirement requires a session-bound ancestor process. Claude uses its session
registry; Codex uses `CODEX_THREAD_ID` and its `codex` ancestor process. A mismatched
session cannot bind to the calling agent. Before closing a herdr pane, the helper
checks the process start time, the pane's terminal id, and that the pane's tty
is the process's tty.

Run the hook checks with a real Codex transcript and a running herdr server:

```bash
python3 tests/integration_codex.py --transcript /path/to/rollout.jsonl
python3 tests/integration_retirement.py
```

The retirement suite creates disposable terminals and makes no model requests.

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
- `lc-invariants`: audit a project against 19 universal invariants (errors, tenant isolation, secrets, mutation feedback, migrations, containers, mocks, deploy, billing, public tokens, upstream-failure handling, stabilised patterns, lifecycle-owned resources, true final states, bounded waits, copies reconciled, exact deletes) plus a conditional kill-switch check for host-injected components. Use during dev or before merge.
- `lc-review-project`: read project docs (CLAUDE.md, PHILOSOPHY, CONTEXT, PRINCIPLES, INVARIANTS, OPS, TODO) and produce a sharp summary of state and next actions.
- `lc-exploration`: explore an unfamiliar topic, codebase, or domain as a senior practitioner. Outputs five fixed sections (load-bearing concepts, common misconceptions, stable vs hype, where to dig, first concrete move).
- `lc-docs-init`: scaffold the standard `docs/` layout (PHILOSOPHY, CONTEXT, PRINCIPLES, INVARIANTS, OPS, TODO) with empty headers. Skips existing files. Use to bootstrap a project.
- `lc-docs-cleanup`: audit the project's docs for staleness, archives, dead refs, and duplicates. Reports a punch list, never edits.
- `lc-succession`: hand work to a fresh, verified Claude Code or Codex session. Persists narrow memory, composes a live briefing, verifies identity and the opening move, then prints a resume command. Triggered by native hooks near the context limit or invoked by hand.
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
├── succeed.sh                   ← Claude succession
├── codex.py                     ← Codex hooks, context usage, verified succession, native meter setup
├── retirement.py                ← verified parent shutdown and herdr pane closure
├── memory.py                    ← persistent project memory: forget-by-use + write-time supersession
├── watch.sh                     ← SessionStart watchPaths + FileChanged staleness nudge
├── herdr-name.sh                ← SessionStart: herdr workspace label = agent name
├── digest.sh                    ← UserPromptSubmit rules-digest re-injection
├── style.sh                     ← PostToolUse em-dash check on user-facing md
├── usage.sh                     ← usage logger + `lc usage` report (debloat aid)
├── statusline-command.sh        ← managed statusline
├── move.sh                      ← `lc move`: resume live sessions on the other account
├── room.sh                      ← `lc say` / `reply` / `room`: broadcasts to live sessions
├── lane.sh                      ← `lc lane`: start a lane from the repo's docs/LANE.md
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

## Codex integration checks

Replay a local Codex rollout through the CLI and hooks using an isolated home:

```bash
python3 tests/integration_codex.py --transcript /path/to/rollout.jsonl
```

The suite checks measured usage, the installed CLI symlink, compaction, partial writes, threshold boundaries, trigger latches, kill switches, session isolation, and config preservation. It does not call a model. Live succession requires Codex authentication and can be checked with `succeed.sh --runtime codex run --briefing <file>` using a read-only task.
