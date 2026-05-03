# lex-claude

Ma config globale pour Claude Code : identités (avec règles partagées canoniques), hook `SessionStart`, skills perso, et un CLI `lc` pour tout déployer/maintenir/synchroniser.

## Bootstrap (nouveau PC ou nouvel utilisateur)

```bash
curl -fsSL https://raw.githubusercontent.com/MagicLex/lex-claude/main/bin/lex-claude | bash -s install
```

Ça clone le repo dans `~/.claude/lex-claude`, sync les règles dans toutes les identités, symlinke `~/.claude/CLAUDE.md` vers l'identité active, déploie les skills, câble le hook dans `settings.json`, et installe le CLI sur le `PATH` (`~/.local/bin/lex-claude` + alias `lc`).

> Pré-requis : `git`, `bash`, `jq` (pour patcher `settings.json` proprement).

## CLI

```
lc install                                         # bootstrap (idempotent)
lc update                                          # git pull + sync rules + redeploy
lc identity                                        # liste, active marquée *
lc identity <name>                                 # switch (global)
lc identity new --name <n> --desc "<persona>"      # crée identité (persona + règles partagées)
lc identity new --name <n> --empty                 # crée identité sans règles partagées
lc rules sync                                      # ré-injecte RULES.md dans toutes les identités managées
lc doctor                                          # check symlinks, hook, skills
lc -help | -h | --help | help                      # toutes les variantes
```

**Auto-update** : à chaque commande (sauf `install`/`update`/`rules`/`help`), check 1× / 24h sur `origin/main`. Si nouveau → pull + sync + redeploy + re-exec. Échec réseau → silencieux.

## Architecture des identités

Chaque identité partage les **mêmes règles canoniques**, parce que Claude lit mal plusieurs fichiers — tout doit être dans un seul fichier self-contained.

- `RULES.md` est la source canonique des règles partagées.
- Chaque `identities/<name>.md` contient :
  - une prelude perso (le "you are X, ..." qui distingue le personnage)
  - un bloc géré entre `<!-- LC_RULES_BEGIN -->` et `<!-- LC_RULES_END -->`, ré-écrit à chaque `lc update` / `lc rules sync` à partir de `RULES.md`
- `lc identity new` splice la prelude + les règles automatiquement
- `lc identity new --empty` crée juste la prelude, pas de marqueurs, pas de sync — pour cas spéciaux

Quand tu modifies `RULES.md` et que tu push, toutes les identités sur toutes tes machines récupèrent la mise à jour au prochain `lc <anything>` (auto-update).

## Auto commit/push sur `identity new`

À la création d'une identité, le CLI :
- `git add identities/<name>.md`
- `git commit -m "add identity: <name>"`
- `git push` (sur le remote configuré — fork ou upstream selon le clone)

Si push échoue (pas de droits, offline, etc.) → l'identité reste committée localement, message explicite, à toi de pousser plus tard.

## Tree chargé par le hook

À chaque session, `hook.sh` injecte dans le contexte :

```
~/.claude/CLAUDE.md          ← identité active (symlink → identities/<name>.md, rules incluses)
$CLAUDE_PROJECT_DIR/
├── CLAUDE.md                ← règles spécifiques au projet (optionnel)
└── docs/
    ├── PHILOSOPHY.md
    ├── PRINCIPLES.md
    ├── INVARIANTS.md
    ├── OPS.md
    └── TODO.md
```

Tous optionnels — seul ce qui existe est chargé.

## Skills inclus

- `invariants` — audite un projet contre les invariants universels (erreurs standardisées, isolation tenant, secrets, migrations, containers, mocks, etc.). Utiliser pendant le dev ou avant merge.
- `lc` — surface l'état lex-claude courant (identité active, skills installés, doctor) à Claude. Invocable via `/lc`.
- `review-project` — lit la doc projet et produit un résumé incisif (état, prochaines étapes).
- `exploration` — adopte la posture d'un senior du domaine que tu lui donnes pour explorer.

## Structure du repo

```
lex-claude/
├── bin/lex-claude               ← CLI
├── hook.sh                      ← SessionStart hook
├── RULES.md                     ← règles canoniques partagées
├── identities/
│   └── jeanjean.md              ← persona + bloc rules synced
├── skills/
│   ├── invariants/SKILL.md
│   ├── lc/SKILL.md
│   ├── review-project/SKILL.md
│   └── exploration/SKILL.md
└── README.md
```

## Ajouter une identité (manuelle ou CLI)

CLI : `lc identity new --name pierre --desc "senior security engineer, 20 ans en infosec, dry humour"` → fichier créé, règles inlinées, commit + push auto.

Manuel : créer `identities/<name>.md` avec une prelude + les marqueurs `<!-- LC_RULES_BEGIN --> <!-- LC_RULES_END -->`, puis `lc rules sync` pour injecter le contenu.

## Modifier les règles partagées

Éditer `RULES.md`, commit, push. Sur tes machines : `lc update` (ou attends l'auto-update sous 24h) — toutes les identités sont resynchronisées automatiquement.
