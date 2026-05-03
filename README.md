# lex-claude

LEXClaude Code config: identities (with canonical shared rules), `SessionStart` hook, personal skills, and a `lc` CLI to deploy / maintain / sync everything.

## Bootstrap (new machine or new user)

```bash
curl -fsSL https://raw.githubusercontent.com/MagicLex/lex-claude/main/bin/lex-claude | bash -s install
```

Clones the repo into `~/.claude/lex-claude`, syncs the rules into every identity, symlinks `~/.claude/CLAUDE.md` to the active identity, deploys the skills, wires the hook into `settings.json`, and installs the CLI on `PATH` (`~/.local/bin/lex-claude` + alias `lc`).

> Requirements: `git`, `bash`, `jq` (to patch `settings.json` cleanly).

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
- `lc-invariants` — audit a project against universal invariants (standardized errors, tenant isolation, secrets, migrations, containers, mocks, etc.). Use during dev or before merge.
- `lc-review-project` — read project docs and produce a sharp summary (state, next steps).
- `lc-exploration` — adopt the mindset of a senior in a domain you give it, to explore.

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
│   └── lc-exploration/SKILL.md
└── README.md
```

## Adding an identity (manual or CLI)

CLI: `lc identity new --name pierre --desc "senior security engineer, 20 years in infosec, dry humour"` → file created, rules inlined, commit + push auto.

Manual: create `identities/<name>.md` with a prelude + the `<!-- LC_RULES_BEGIN --> <!-- LC_RULES_END -->` markers, then `lc rules sync` to inject the content.

## Editing the shared rules

Edit `RULES.md`, commit, push. On your machines: `lc update` (or wait for auto-update within 24h) — every identity is resynced automatically.
