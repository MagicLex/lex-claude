# lex-claude

LEXClaude Code config: identities (with canonical shared rules), `SessionStart` hook, personal skills, and a `lc` CLI to deploy / maintain / sync everything.

> ## ⚠️ Heads up — this is **my** personal config
>
> `lc install` is **destructive** to your existing Claude Code setup. If you run it as-is:
>
> - **`~/.claude/CLAUDE.md`** — if you have one, it gets backed up to `CLAUDE.md.bak.<ts>` and **replaced** by a symlink to the first identity found in `identities/` (alphabetical order). Your global instructions stop being loaded until you restore them.
> - **`~/.claude/settings.json`** — backed up to `settings.json.bak.<ts>`, then any prior `lex-claude` `SessionStart` hook (and legacy `JeanJean` hooks from earlier versions) is stripped and replaced. Other hooks are preserved, but you're trusting `jq` + my filter logic.
> - **`~/.claude/skills/lc*`** — any skill you happen to have named `lc`, `lc-invariants`, `lc-exploration`, `lc-review-project`, `lc-docs-init`, or `lc-docs-cleanup` will be silently overwritten by symlinks into the install dir.
> - **`~/.local/bin/lex-claude` and `~/.local/bin/lc`** — created/replaced as symlinks. If you already have a binary called `lc`, it gets shadowed.
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

## CLI

```
lc install                                         # bootstrap (idempotent)
lc update                                          # git pull + sync rules + redeploy
lc identity                                        # list, active marked *
lc identity <name>                                 # switch (global)
lc identity new --name <n> --desc "<persona>"      # create identity (persona + shared rules)
lc identity new --name <n> --empty                 # create identity without shared rules
lc rules sync                                      # re-inject RULES.md into every managed identity
lc doctor                                          # check symlinks, hook, skills
lc -help | -h | --help | help                      # all variants
```

**Auto-update**: on every command (except `install` / `update` / `rules` / `help`), checks `origin/main` 1× / 24h. If newer → pull + sync + redeploy + re-exec. Network failure → silent.

## Identity architecture

Every identity shares the **same canonical rules**, because Claude reads multiple files badly — everything must live in a single self-contained file.

- `RULES.md` is the canonical source for shared rules.
- Each `identities/<name>.md` contains:
  - a personal prelude (the "you are X, ..." that defines the character)
  - a managed block between `<!-- LC_RULES_BEGIN -->` and `<!-- LC_RULES_END -->`, rewritten on every `lc update` / `lc rules sync` from `RULES.md`
- `lc identity new` splices the prelude + the rules automatically
- `lc identity new --empty` only creates the prelude, no markers, no sync — for special cases

When you edit `RULES.md` and push, every identity on every machine picks up the update on the next `lc <anything>` (auto-update).

## Auto commit/push on `identity new`

When creating an identity, the CLI:
- `git add identities/<name>.md`
- `git commit -m "add identity: <name>"`
- `git push` (to the configured remote — fork or upstream depending on the clone)

If push fails (no rights, offline, etc.) → the identity stays committed locally with an explicit message; push it later yourself.

## Tree loaded by the hook

On every session, `hook.sh` injects into context:

```
~/.claude/CLAUDE.md          ← active identity (symlink → identities/<name>.md, rules inlined)
$CLAUDE_PROJECT_DIR/
├── CLAUDE.md                ← project-specific rules (optional)
└── docs/
    ├── PHILOSOPHY.md
    ├── PRINCIPLES.md
    ├── INVARIANTS.md
    ├── OPS.md
    └── TODO.md
```

All optional — only what exists is loaded.

## Skills included

All custom skills are prefixed `lc-` to avoid drowning in native skills / other plugins. Exception: `lc` itself, which is also the name of the `/lc` slash command.

- `lc` — surface the current lex-claude state (active identity, installed skills, doctor). Invoke via `/lc`.
- `lc-invariants` — audit a project against universal invariants (errors, tenant isolation, secrets, migrations, containers, mocks, billing, public tokens, upstream-failure handling, etc.). Use during dev or before merge.
- `lc-review-project` — read project docs and produce a sharp summary (state, next steps).
- `lc-exploration` — adopt the mindset of a senior in a domain you give it, to explore.
- `lc-docs-init` — scaffold the standard `docs/` layout (PHILOSOPHY, PRINCIPLES, INVARIANTS, OPS, TODO) with empty headers. Skips existing files. Use to bootstrap a project.
- `lc-docs-cleanup` — audit the project's docs for staleness, archives, dead refs, and duplicates. Reports a punch list, never edits.

## Repo structure

```
lex-claude/
├── bin/lex-claude               ← CLI
├── hook.sh                      ← SessionStart hook
├── RULES.md                     ← canonical shared rules
├── identities/
│   └── jeanjean.md              ← persona + synced rules block
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

Edit `RULES.md`, commit, push. On your machines: `lc update` (or wait for auto-update within 24h) — every identity is resynced automatically.
