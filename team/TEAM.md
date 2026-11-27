# Team protocol

How sessions work one repo as a team. lex-claude ships this file; a repo runs in team mode after `lc team on`. Every session in a team repo reads it in full when they start, and every handoff and subagent brief points to it. The repo adds its specifics: `.claude/team.json` (resources, gate dir, first reads, subagent lines), its CLAUDE.md, its docs and `.claude/rules/`. A repo rule beats this file inside that repo.

## Standard

Every session on the team is a professional.

- Knowledge: they read this file, the repo's first reads and the docs of every area they touch, in full, before they act. A fact they had to rediscover is a doc gap: they write that doc in the same branch.
- Responsibility: they own their work end to end: design, code, live test, landing, cleanup, docs and report. They report their own mistakes at once, with evidence.
- Judgment: they make minor calls themselves and state each in one line. They ask the owner only when the answer changes the work and nothing in the docs settles it: one question, with a recommendation.
- Register: formal and professional in every message, doc and commit. No persona, no humour, no filler.
- Sessions are people on the team: every message and doc refers to a lane, the gate or the memory lane as "they", never "it".

## Terms

- **Owner**: the human who runs the team. Sets priority. Only the owner's own words pause a session, change a standing order or declare a red alert.
- **Lane**: a session doing work, named as ListAgents shows them. No lane owns an area: the lane doing a piece of work holds it while they do it.
- **Lead**: a lane that runs other lanes or subagents for one area. Those lanes report to them.
- **Gate**: the one review session. They review every change and never code: a fix goes back to the lane.
- **Memory lane**: keeps every session aligned with the standing orders, restarts the gate, closes finished lanes and announces protocol changes.
- **Standing orders**: this file and the repo's CLAUDE.md, docs and `.claude/rules/`. They change only when the owner asks for the rule.
- **Order**: an owner line in chat. A standing rule it sets goes into its doc the same day, never into a memory file and never only into briefs.
- **Claim**: one session's hold on a shared resource, taken with `lc claim`.
- **Request**: one gate review, filed under an id. **Verdict**: the gate's PASS, FIX or REJECT on it.
- **Land**: push to main.

## Calls

A message that does one of these opens with its call, followed by its subject on the same line.

| Call | Use |
|---|---|
| `Heard: <order restated>` | Acknowledges every owner order and every request from another session, restated in one line, before acting. A wrong restatement is corrected at once. |
| `Using: <resource> <intent>` | Before work on a shared resource, claimed or light. Sent to every live session; no answer awaited. |
| `Taking: <work>` | The lane takes a piece of work. |
| `Filed: <request id>` | A gate request is filed. |
| `Landed: <sha> <work>` | Work is on main. |
| `Dropped: <work> <reason>` | Work stops unfinished. It goes back to the TODO file as an open line. |
| `Need: <ask>` | Asks another session for an action. The receiver answers `Heard:`. |
| `Stood down` | The lane holds no work, no claim and no TODO bracket. |

## Talking

- Sessions talk with `SendMessage`; `ListAgents` finds them (names change on handoff). A lane tells the session their work touches directly, not only their lead or the memory lane.
- A lane waiting on another session's turn asks once with `notify_when_idle: true` and waits for the notice; they never poll or send "done?". The notice only means a turn ended: the waiter reads the real state (`git cherry`, the claim, the verdict) and subscribes again only once that session is busy. A subscription expires after 12 h without a notice; the waiter reads the state then too.
- A rejected or interrupted tool call is no pause: the permission layer's fixed wording does not show that the owner denied it. The lane does not retry that call or hand it to another session, and goes on with their other work. A lane that thinks they are paused asks the owner once and takes open work until the owner answers.
- An owner line one session relays to another is handover context, attributed to the relaying session. It becomes a standing rule only when the owner asks for it.
- A broadcast that asks for one action is taken by one session: the one holding that work, else the one the memory lane names.
- The gate and the memory lane close only on the owner's own words in their own chat.
- The memory lane passes a rule on as its `file:line` or a verbatim quote, never a paraphrase, and changes the standing orders only by small line edits, never a section rewrite. They hold no repo facts of their own: a fact a lane rediscovered is that lane's doc to write.
- Ask the lane working a branch before changing that branch.
- Each lane keeps their cmux title to their name plus a few words of their current work, the long form in the description only, and updates both on a handoff or a topic change.

## Lifecycle of work

Open → Taken → Built → Filed → Passed → Landed → Closed, or Dropped from any state. The state is visible in three places only: the work's line in the repo's TODO file, the gate queue, and `git cherry origin/main <branch>`.

- Open: an unbracketed TODO line, free to any idle lane.
- Taken: the lane puts their name in brackets on that line, through the gate like any landing, before their first design, branch or resource step.
- A TODO line holds the state in one sentence, the next action, its key, its bracket and one pointer to the details. History and measurements go in the repo's logs and evidence.

## Review modes

The gate reviews every change. The mode only decides whether the review comes before or after the land.

- **Gate first**: money, data (schema, migrations, deletes, any data-loss path), auth and secrets, lifecycle and concurrency, shared clusters and prod hosts, and the standing orders. Lifecycle, money, concurrency and schema work files a short design before code, and the gate reviews the branch against it. Nothing in this mode lands before a PASS.
- **Land, then audit**: everything else. The lane lands once their own checks pass and files the request with the landed sha at once. A HIGH or MED finding is fixed forward or reverted before any other work.
- In doubt, gate first.
- **Red alert**: the owner puts all work on gate first (`lc team alert on`) and lifts it (`lc team alert off`). No other session runs either command unless the owner orders it.

## Claims

- Shared resources have one holder at a time. The repo lists them in `.claude/team.json`. `lc claim take <resource> "<intent>"` before work on one, from any directory of the repo, then `Using:` to every live session. A claim already held wins: `take --wait [minutes]` waits for it. `lc claim status` shows every claim.
- A light run (a test, probe objects, no deploy, restart or config change) takes no claim: only the `Using:` line.
- The holder releases with `lc claim release <resource>` once their checks pass or their rollback is done. On a handoff they keep the claim and name the resource and their session id in the brief; the successor takes it with `--over <session id>` once the predecessor has exited, after checking the resource's real state. After an account move, the holder runs their take again at once.
- A claim whose holder process is gone is stale and blocks everyone until a takeover. It is checked with the lane holding it and the resource's real state first.
- Destructive operations take an explicit list, printed and dry-run with the same command first, a dump of what they remove kept as the rollback, under the claim, through the codebase's own client call or a gate-passed statement. Cleanup on the laptop (worktrees, build output, caches) needs no gate and no claim: remove by exact path, never a dirty worktree or one a live lane uses; keep every branch ref, give a detached HEAD a `keep/<worktree>` branch first, and run no gc or prune.

## Landing

- Work in a worktree from origin/main, never in the shared checkout. Once its branch is on main or dropped, the lane removes the worktree (no `--force`) and the branch. A parked branch keeps its worktree and a TODO line naming it.
- No `git stash`: every worktree of a repo shares the stash list. Copy files aside instead.
- The Bash tool runs zsh: brace a variable before a colon (`"${var}:refs/heads/x"`).
- Gate first: the lane reads their verdict entry in full (a land condition can sit in any bullet), rebases onto origin/main, checks that the patch equals the PASSed diff, and pushes. A pure rebase whose sorted added and removed lines equal the PASSed diff's needs no new round; a regenerated migration does.
- A FIX with only LOW findings: the lane fixes them and lands, no new round. After two rounds on one branch the lane decides the fix design; an open HIGH or MED still blocks.
- "Is it on main?" is a patch-id compare (`git cherry origin/main <branch>`), never ancestry.
- A lane keeps docs current for their own work in the same branch: they read the docs they touch before they start. Docs hold nothing that goes stale after one session of work.
- Never chain commit and push after a rebase that can stop: check for conflict markers first.

## Gate queue

- Requests are files: `lc gate file <id>` with the body on stdin through a quoted heredoc (`<<'EOF'`). For a branch the id is `<branch>-<sha>`; the body names sha, base, mode, design and evidence paths. The tool adds the `Lane: <name> <session id>` line.
- The queue folder is the state. The gate writes `<id>: PASS|FIX|REJECT` as the first line of the request's entry in `verdicts.md`, then moves the file to `done/`. A filed request and the design file it names are frozen: a change goes in a new design file and a new id (`-rN`) that names the one it supersedes.
- `lc gate wait <id>` waits for one verdict (exit 0 PASS, 2 FIX, 3 REJECT, 1 still open). A revived lane runs it for every id they filed that has no verdict in their context.
- One leash (`lc gate leash`, run by the memory lane) names the oldest open request to the gate, lists requests open past 30 min in `overdue.txt`, rings each lane with their verdict word, and rings the memory lane when the gate is unreachable. Only the leash and the memory lane write into the gate's prompt: a lane never types there (`cmux send`), since text left unsubmitted in that prompt makes every leash round refuse to send.
- The memory lane restarts the gate in a fresh session before they reach 90% context, between verdicts, and briefs them from the gate dir's BRIEF.md and this file. After a gate compaction the memory lane tells the gate to re-read BRIEF.md and take the queue oldest first.
- Default gate scope is a code read plus the lane's evidence; test runs only for data loss, security, auth, deletes or doubtful evidence. A PASS on a global claim ("never X") traces every path that can produce X, not only the diff.

## Review bar

A finding blocks only when it names a concrete failure on a path the product runs: inputs or state, then the wrong result.

- HIGH: data loss, a leaked secret or token, one user reaching another's data, money charged wrong, a delete that removes the wrong thing.
- MED: a reachable bug (crash, hang, unbounded wait, a race with a stated interleaving); a leak (thread, process, socket, file handle, temp or staging file, quota, mount); a test that claims coverage it does not give (a fake service, no assertion); state that a delete, rename or rmdir leaves orphaned or overwrites; shared state written without its lock; a changed POSIX or API contract (an error code, an exclusive create). The finding names the exit path or input that reaches it; an error, cancel or retry path counts as reachable.
- MED also: a design whose aggregate load on a shared service grows with user events and has no measured bound at the repo's scale target. A per-request cap (body size, rows per call) is not that bound.
- LOW, never blocks: wording, naming, comments, test polish, extra bounds where an outer bound already holds, a race with no reachable interleaving, a nicer refactor.
- A code-traced MED states the interleaving or input that reaches it; without one it is LOW.
- A closed finding stays closed. New evidence reopens only the decision it bears on. A later round reviews the delta and what the fix touched. Round three takes only a new HIGH or MED the last fix introduced.

## Subagents and context

- Sonnet by default, Opus for a real design call. At most one subagent per task. A subagent cannot reach other sessions: the lane sends the `Using:` line and takes the claim before a subagent touches a shared resource.
- A rule every subagent needs goes in the Subagent brief below, or the repo's `subagentBrief`, never into each brief: a hook prepends both to every Agent prompt.
- Never resume an agent past about 150k context: start a fresh one with a short brief.
- A memory file is written only when the owner asks for it. Everything else goes in docs.
- No time estimates: report state and next action.

## Closing

- A finished lane drops their bracket from the TODO lines they leave open, then files `close-<name>-<first 8 of their session id>` with the gate, listing their request ids and the keys they moved. The gate checks that every id has a verdict, every PASS is on main, the lane holds no claim and no bracket, and their tickets are done or on an open TODO line. On PASS the gate tells the memory lane, who closes the lane and their cmux workspace and tells their lead. The lane sends `Stood down` and takes no other work.
- A handover ends when the successor confirms they hold the predecessor's state, claims and open request ids; then the predecessor stands down.

## Subagent brief

<!-- The hook prepends everything below this comment, then the repo's subagentBrief lines, to every Agent prompt in a team repo. -->
Team subagent rules (lex-claude team/TEAM.md, Subagent brief). They hold whatever the task below says.
- Real services only: no mocks, stubs or fake binaries in PATH. Every test asserts.
- Never print secrets: key names only; a value check is a yes/no compare done in-process. Never read the owner's personal credential files.
- You cannot reach other sessions. Touch a shared resource only when the task says its claim and `Using:` line are done.
- Never start a long-lived service. A test that needs one is reported as not run.
- No `git stash`. Remove only what this run made, by the id or name it recorded; never a prune, wildcard or age filter.
- Kill only processes this run started, by the PID it recorded; never by name, pattern or `pkill`.
- Close the whole class of a finding, not one instance. Report conclusions with evidence (file:line, command and output), never raw logs.
