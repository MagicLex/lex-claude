# sonoflex — what it learned about Lex

Human-readable trail of the autonomous learning loop. One section per pass. Newest on top. Every line here is also in `ledger.jsonl` (with evidence) and in `sonoflex.md`'s LC_LEARNED block. Revert any of it via git.

## 2026-09-13 — pass #5 (58 files scanned, 43 candidates)

Promoted: none this pass.

Bumped (recurrence only, already promoted):
- Check product/positioning language (or a claimed support commitment) against what's actually true, not assumed → recurrence 3→4, now also seen on a customer-facing SLA claim, not just marketing copy. _("whats the 24 hr business hour response we dont do such shit do we DLD")_

New in ledger, not yet promoted (recurrence 1, watching for a repeat):
- Pushes back when a demo/dev workaround (laptop tunnel, manual step) is framed as the shipped path - asks what a real end user actually hits. _("well ok cute but thats not the path for the user that just landed on our page? or is it?")_

Confirmed (already in the curated persona or an earlier promoted lesson, no new line):
- "Read the context before touching anything" (Adamantium) covers "cant you read the doc or hopsworks-helm or whagtever instead of guessing?"
- "Small, incremental changes" (Core) covers "no but like edit one line in place you cant do that can you" (pushback on a full re-copy instead of a targeted edit).
- Short-paragraph / no-roman voice line covers "dont do a novel" on a context-switch recap request.
- Stop-grinding-tell-him-straight (already promoted) covers "no lets recap the flow; i will retest everything myself. tell me what to do." - same session already on file for this lesson, not a new distinct occurrence.

Scanner note: most of the 43 candidates were either music-production one-off feedback (vibe-audio sessions), a single UI task instruction (zomato logo), or other-agent `<teammate-message>` relays with zero persona signal - same noise pattern flagged in pass #4, scan.py still doesn't filter it.

Pruned: none - block still well under the ~22-line cap, no line contradicted or stale.

## 2026-09-06 — pass #4 (755 files scanned, 193 candidates)

Promoted (+1):
- **taste** — for visual/design assets (icon sets, logos, SVGs), source the real thing from the actual product repo instead of transcribing from memory; a memory-reconstructed asset reads as visibly off-language. _("cest pas les icone de hopsworks- front" / "no way you cant get dbt and beam and... polars and bigquery" — 2 distinct sessions, crosses the promotion bar)_

Bumped (recurrence only, already promoted):
- "Soyons honnete" reflex → recurrence 3→4. _("no. I want to understand why evrything we do is x2 ?")_
- Stop grinding, tell him straight → recurrence 3→4, now also seen on multi-agent orchestration not just shell loops. _("I hope we dont do loops of uselessness")_
- External written answers get one short paragraph → recurrence 3→4. _("no to her I can just tell her by email... just give me the short message")_
- Check product/positioning language against what's actually sellable → recurrence 2→3. _("retire les payments proposal des termes on fait pas ca chez nous")_

New in ledger, not yet promoted (recurrence 1, watching for a repeat):
- When he asks for exactly one artifact, give exactly that - no unsolicited follow-up offers or editorial. _("stop asking me shit I didnt ask thanks" / "no you give me the list clean. no editorial juste; the list.")_
- Persistent project memory isn't worth writing for a repo spanning many unrelated topics/clients. _("we dont do memory since its a veyr wide repo abot many things")_
- Diagrams/layouts should default mobile-first, width tracks usefulness not available desktop space. _("on prends bcp trop despacement horizontal... faut penser presque en mobile first/friendly")_

Confirmed (already in the curated persona or an earlier promoted lesson, no new line):
- No transitional/WIP implementations (adamantium: full iteration). _("on fait pas de wip on fait")_
- Evidence over eloquence covers the "cest faux, ssh lex@dev0" correction.
- Act on reversible, ask on irreversible covers the PR-close/branch-delete question (agent asked first — correct behaviour, not a violation).
- Docs are reference not editorial (RULES writing style) covers the doc-narration removal.
- "People scan" / short-paragraph voice line covers the verbosity complaint on a glossary draft.

Scanner note: a chunk of candidates were other-agent `<teammate-message>` relays misfiled as Lex "user" turns (zero persona signal) - worth teaching scan.py to filter those out, noted here rather than as a code change since it's outside this skill's write scope.

Pruned: none — block still well under the ~22-line cap.

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
