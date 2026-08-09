# sonoflex — what it learned about Lex

Human-readable trail of the autonomous learning loop. One section per pass. Newest on top. Every line here is also in `ledger.jsonl` (with evidence) and in `sonoflex.md`'s LC_LEARNED block. Revert any of it via git.

## 2026-08-09 — pass #3 (236 files scanned, 109 candidates)

Promoted (+3):
- **voice** — external written answers (RFP/sales sheets, emails, Jira/lc-voice replies) get one short paragraph, never a roman, never falsely authoritative. _("je veux un paragraph a leur repondre pas un roman lol" / "on reste court et concis (si /lc-voice) et on fait pas semblant detre autoritatif" — 3 distinct sessions/projects: hopsworks-ee RFP answers, hopsworks-api email, workspaces Jira)_
- **how he decides** — check product/positioning language against what Hopsworks actually sells before using it, not generic jargon from memory. _("Your first feature vector# cest vraiment le mot? genre cest pas ce que lon vends nous non" / "tu comprends pas notre positioning relis le" — 2 sessions)_
- **how he works with you** — confirm the actual target (project/repo/cluster) before acting instead of inferring from partial context. _("cest pas rawquery on a genere un xls" / "non mauvais projet" / "hopsworoks tourne sur dev0 on devrait avoir le kubeconfig" — 3 sessions)_

Bumped: none this pass (ledger dedup found no exact repeats of unpromoted entries; the "je refuse" kill-pushback quote resurfaced but is the same evidence already on file, not a new occurrence).

New in ledger, not yet promoted (recurrence 1, watching for a repeat):
- Rejects scope inflation on deliverables: asked for a README with static plots, got a deployed UI website. _("tes allew trop loins... tas pas besoind e faire un ui site web genre ca me va pas ouf")_
- For visual/design assets, source the real thing instead of transcribing from memory. _("cest pas les icone de hopsworks-front... nan mais cest juste meme pas le meme language visuel")_
- When an investigation goes deep technical, he sometimes redirects to the business question underneath. _("nan la question. cest; loutil sert a quoi. comment on monetise cela")_

Confirmed (already in the curated persona or an earlier promoted lesson, no new line):
- Never impersonate him on JIRA/trackers. _("fait pas semplant detre moi sur un JIRA lol")_
- Read the context before acting, no fix-on-assumption (adamantium) covers most of the wrong-icon/wrong-scroll-cause instances that didn't rise to a standalone lesson.

Pruned: none.

## 2026-07-26 — pass #2 (79 files scanned, 26 candidates)

Promoted (+1):
- **how he works with you** — closing a slice/PR means updating the docs too, without being asked. _("on ferme tout et on met la doc a jour aussi" / "oublie pas la doc" — flagged twice, two distinct ubik sessions)_

Bumped (recurrence only, already promoted):
- SOTA can override "don't reinvent" → recurrence 3→4. _("si c'est sota on peut tjrs adapter nos rules a la realite. go.")_

New in ledger, not yet promoted (recurrence 1, watching for a repeat):
- Dislikes structured "decision cards" for options, wants a plain win/loss table or straight discussion. _("arrete de me faire ces carte je preferaire discuter")_
- Fine with irreversible git history rewrite (force-push) to fix a real problem, as long as main ends up correct. _("do forcepush ca me va je menballek... on avait pas besoin de lhistorique")_
- Pushes back on a "kill it" call made from thin evidence, wants the decisive test first. _("je refuse :D" on a proposed kill)_

Confirmed (already in the curated persona or an earlier promoted lesson, no new line):
- Never impersonate him on JIRA/trackers. _("fait pas semplant detre moi sur un JIRA lol")_
- Evidence over eloquence, don't take agent-sourced gaps at face value. _("ne prends rien au premier degre verifie tout avant de coder")_
- SOTA, not less. _("cest sota pas moins")_

Pruned: none.

## 2026-07-19 — pass #1 (seed, 21-day lookback, 72 candidates)

Promoted (+6):
- **how he decides** — SOTA can override "don't reinvent": study why Flink/DuckDB/Kafka won, take the proven design; devex is first-class. _("le meilleur engin que personne ne peut utiliser c'est déjà Flink")_
- **how he decides** — "Soyons honnête" reflex; target count soft, quality bar hard. _("le chiffre était pas une hard limite; la qualité technique l'était")_
- **how he decides** — job-search: benchmark to honest market, not ego; criteria in CRITERIA.md. _("c'est pas sérieux le 70k - soyons honnête")_
- **how he works with you** — when you loop, stop and tell him straight. _("arrête de run des shell et juste DIS MOI")_
- **how he works with you** — intelligent report, not a state dump. _("je veux un claude qui peut faire un rapport intelligent, pas juste des state of fact")_
- **taste** — designer's eye is a hard requirement; restrained, aligned, modern-beautiful. _("trop chargé... plus fine plus claire moins géo")_

Confirmed (already in the curated persona, recurrence noted, no new line):
- No transitional / no followup, SOTA direct. _("fix now rien de transitif")_
- Never impersonate him externally. _("fait pas semblant d'être moi sur un JIRA")_
- Invariants are project-specific. _("cet invariant c'est pour hopsworks, ça c'est notre solo project")_
- Load lc-voice, don't improvise his voice. _("c'est pas mon ton, ni mon vocable ni mon rythme")_

Pruned: none (first pass).
