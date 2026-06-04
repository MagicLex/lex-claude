# lex-claude

LEXClaude Code config: identities (with canonical shared rules), `SessionStart` hook, personal skills, and a `lc` CLI to deploy / maintain / sync everything.

> ## ⚠️ Heads up: this is **my** personal config
>
> `lc install` is **destructive** to your existing Claude Code setup. If you run it as-is:
>
> - **`~/.claude/CLAUDE.md`**: if you have one, it gets backed up to `CLAUDE.md.bak.<ts>` and **replaced** by a symlink to the first identity found in `identities/` (alphabetical order). Your global instructions stop being loaded until you restore them.
> - **`~/.claude/settings.json`**: backed up to `settings.json.bak.<ts>`, then any prior `lex-claude` `SessionStart` hook (and legacy `JeanJean` hooks from earlier versions) is stripped and replaced. Other hooks are preserved, but you're trusting `jq` + my filter logic.
> - **`~/.claude/skills/lc*`**: any skill you happen to have named `lc`, `lc-invariants`, `lc-exploration`, `lc-review-project`, `lc-docs-init`, or `lc-docs-cleanup` will be silently overwritten by symlinks into the install dir.
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

Codex does not expose the same `SessionStart` hook surface as Claude Code, so `lc codex` acts as a wrapper: it renders the same context bundle as `hook.sh` and passes it as Codex's initial prompt.

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
lc codex [--lite|--full] [prompt]                  # launch Codex with lex-claude context preloaded
lc codex --print [--lite|--full] [prompt]          # inspect the generated Codex prompt without launching
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
```

Run inside the venv where `hops` lives (uv targets the active env). Skill relink only touches symlinks pointing into the hopsdev clone base (`$TMPDIR/hopsdev`, override with `HOPSDEV_HOME`); `lc` skills and `my-skills` are left alone. Default repo is `MagicLex/hopsworks-api` (override with `HOPSDEV_REPO`).

**Auto-update**: on every command (except `install` / `update` / `rules` / `lang` / `version` / `help`), checks `origin/main` 1× / 24h. If newer → pull + sync + redeploy + re-exec. Network failure → silent.

## Kill switches (env vars)

Three escape hatches if you want to neutralise a piece without uninstalling.

- `LEX_CLAUDE_DISABLE=1`: hook.sh exits early; nothing gets injected at SessionStart. Useful when debugging context bloat or comparing with/without the hook.
- `LEX_CLAUDE_NO_AUTO_UPDATE=1`: disables the daily `git pull` + re-exec on `lc <cmd>`. Use when you want frozen behaviour (CI runs, shared machines, long-running scripts).
- `LEX_CLAUDE_YES=1`: equivalent to `lc install --yes`; skips the destructive-overwrite prompt. Use only when you've read the warning above and accept it.

Heartbeat: hook.sh writes `~/.claude/lex-claude/.last-hook` (epoch seconds) on each successful run. `stat -f %m ~/.claude/lex-claude/.last-hook` (macOS) or `stat -c %Y` (Linux) tells you when the hook last fired.

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
~/.claude/CLAUDE.md          ← active identity (symlink → identities/<name>.md, rules inlined)
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

## Skills included

All custom skills are prefixed `lc-` to avoid drowning in native skills or other plugins. Exception: `lc` itself, which is also the name of the `/lc` slash command.

- `lc`: surface the current lex-claude state (active identity, installed skills, doctor, version). Invoke via `/lc`.
- `lc-invariants`: audit a project against 14 universal invariants (errors, tenant isolation, secrets, mutation feedback, migrations, containers, mocks, deploy, billing, public tokens, upstream-failure handling, stabilised patterns) plus a conditional kill-switch check for host-injected components. Use during dev or before merge.
- `lc-review-project`: read project docs (CLAUDE.md, PHILOSOPHY, CONTEXT, PRINCIPLES, INVARIANTS, OPS, TODO) and produce a sharp summary of state and next actions.
- `lc-exploration`: explore an unfamiliar topic, codebase, or domain as a senior practitioner. Outputs five fixed sections (load-bearing concepts, common misconceptions, stable vs hype, where to dig, first concrete move).
- `lc-docs-init`: scaffold the standard `docs/` layout (PHILOSOPHY, CONTEXT, PRINCIPLES, INVARIANTS, OPS, TODO) with empty headers. Skips existing files. Use to bootstrap a project.
- `lc-docs-cleanup`: audit the project's docs for staleness, archives, dead refs, and duplicates. Reports a punch list, never edits.

## Repo structure

```
lex-claude/
├── .claude-plugin/
│   └── plugin.json              ← Claude Code plugin manifest
├── bin/lex-claude               ← CLI
├── bin/hopsdev                  ← hopsworks-api branch switcher (deployed alongside lc)
├── hook.sh                      ← SessionStart hook
├── RULES.md                     ← canonical shared rules
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

Edit `RULES.md`, commit, push. On your machines: `lc update` (or wait for auto-update within 24h). Every identity is resynced automatically.
