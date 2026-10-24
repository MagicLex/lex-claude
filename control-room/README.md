# Control Room

`app.py` serves a local control room for any project.
It attaches to existing cmux panes. It does not start agents, send messages,
run tests, or deploy. Python 3.9+ and cmux are required. Tested with cmux 0.65.1.

```bash
python3 app.py add-project my-project /path/to/project
python3 app.py add-source my-project blockers /path/to/STATE.md
python3 app.py add-source my-project review /path/to/verdicts.md
python3 app.py add-source my-project handoff /path/to/handoff.md
python3 app.py add-source my-project docs /path/to/INVARIANTS.md
python3 app.py serve
```

Open the printed loopback URL in a cmux browser pane. `serve --port <port>`
keeps a chosen port. Ctrl-C stops the server and its collector. Configuration
lives in the ignored `.control-room/config.json`; `--config <file>` selects
another store. Registration changes are picked up while the server runs.

| View | Content |
|------|---------|
| Work | Input requests, changed review targets, saved work-state bullets, lead and reviewer panes |
| Flow | Agent graph, recorded routes, setup roles, live hook activity, pane navigation |
| Traces | Claude token counters, session and subagent usage, execution timelines, tool inputs and results |
| Sessions | cmux terminals, reported activity, assigned roles, pane navigation |
| Reviews | Latest verdict per exact subject per source, commit binding, original evidence |
| Sources | Docs, handoffs, blockers, evidence, repository state |

Work-state bullets are quoted from the registered file. They are not verified
task states. Reviews accept `subject <commit>: PASS` or `FIX` headers.
Headers covering several repositories remain unbound. A recorded PASS does
not certify tests or deployment. File modification time is shown separately
from the unknown per-verdict time. Full history remains in the original source.

```bash
python3 app.py bind-target 'review subject' /path/to/worktree
python3 app.py set-role <surface-uuid> Lead
python3 app.py snapshot
```

Roles: `Lead`, `Worker`, `Gate`, `Review`, `Docs`. Gate covers invariants.
The setup displays it as one `Gate / Invariants` role. A pane can hold
several roles, for example `set-role <surface-uuid> Gate Review`. Pane UUIDs come from
`cmux --json --id-format uuids tree --all`. A bound review requires revalidation
when HEAD changes or the working tree is dirty. Missing sources and failed
collectors show errors. Expired snapshots hide their data. The browser refreshes
every 15 seconds, except while reading expanded evidence or using a control.
Initial content, filters, refresh, disclosures, and navigation also work without JS.

Flow uses a light canvas with zoom, drag, keyboard pan, and node selection.
Select a node to inspect its routes and open its existing pane. Setup shows
unassigned roles. Panes without a recorded role or route appear under Other panes.
Arrows come from registered source lines, not pane titles:

```bash
python3 app.py link <sender-uuid> <receiver-uuid> --label 'Requests review' --source /path/to/handoff.md --line 9
python3 app.py unlink <sender-uuid> <receiver-uuid>
```

A route disappears if its quoted source line changes or either pane disappears.
Roles can follow a registered surface pointer or confirmed session succession:

```bash
python3 app.py add-source my-project evidence /path/to/LEAD_SURFACE
python3 app.py set-role <original-surface-uuid> Lead --project my-project --pointer /path/to/LEAD_SURFACE
python3 app.py set-role <original-surface-uuid> Worker --project my-project --session <session-uuid> --lineage-dir /path/to/lineage
```

The pointer contains one current cmux surface UUID. A lineage file is named
with the successor session UUID and contains `generation<TAB>predecessor-uuid`.
For lex-claude's Claude sessions, these records live in
`~/.claude/lex-claude/state/lineage`. Only a unique chain and a unique current
session-to-pane match within the registered project can receive the role.
The original surface UUID remains the binding key used by recorded routes.
Routes follow resolved endpoints while retaining their source-line checks.
All configured roles on the binding move together. Closed or ambiguous
successors, unreadable lineage, and missing or invalid pointers leave the
binding unavailable. No fallback to the predecessor is made. A pointer is
authoritative even when a different successor is running.

Bindings are resolved on each collection, normally every 15 seconds and on
observed hook events. Flow refreshes its HTML every two seconds. The inspector
shows binding UUIDs, resolved sessions, pointer paths, and lineage records.
Selection follows a binding across refreshes. Open predecessors stay navigable
under Other panes without an inferred lifecycle state. Plain `set-role` keeps
a surface pinned; repeat it without follow options to remove automatic binding.

The room listens to existing `cmux events --category agent` hooks. It installs
no hooks. Flow refreshes every two seconds, preserving selection and zoom.
Running states pulse; received state changes flash once. Reduced motion is respected.
The activity list contains observed events only. Hook state expires after 90 seconds;
registry state then takes over, or activity stays unreported. A disconnected event
stream is marked offline. The server owns and stops its event listener.

The wordmark follows Audiolex's Roboto Black Italic outline treatment. The SVG
needs no font download. The interface uses system fonts and a light palette.
Build mode is not implemented. Starting the room never starts a team.

### Claude tracing

Tracing reads the loopback HTTP API of
[claude-devtools](https://github.com/matt1398/claude-devtools), tested with 0.5.0.
Run claude-devtools with its HTTP server enabled, then register its URL:

```bash
python3 app.py set-tracing-url http://127.0.0.1:<port>
```

The Traces view shows up to 12 recent or pane-linked sessions per registered
project. A session opens its subagent timeline, separate agent counters, and
tool calls with expandable inputs and results. Each tool page contains 50 calls.
Inputs and results are limited to 65,536 characters each. Flow nodes show main
conversation usage and link to the trace through their inspector.

Counters come from claude-devtools: input, cache creation, cache reads, and
output. Main and subagent counters stay separate. These are retained-history
usage counters, not current context size, subscription quota, or a bill.
Estimated context-category attribution and dollar costs are not displayed.
Closed sessions remain available while their transcripts are retained.

The adapter only reads registered project data. It makes GET requests to a
configured loopback address, with no proxies or redirects. Failed reads hide
the affected trace data. The room installs no Claude hooks and starts no agents.
claude-devtools runs independently; closing it makes tracing unavailable.
Its HTTP API is internal, so upgrades need the live tracing check below.

The optional w9s adapter adds Claude registry state and recorded jobs:

```bash
python3 app.py set-workspaces-root /path/to/workspaces
WORKSPACES_DIR=/path/to/workspaces python3 /path/to/workspaces/scripts/w9s --snapshot-json --include-external
```

The adapter runs the external `<workspaces-root>/scripts/w9s`. Use
`set-workspaces-root /path/to/workspaces --w9s /path/to/other/scripts/w9s`
when the script lives in another checkout. The script must support
`--snapshot-json --include-external`. w9s is not bundled with Control Room.

`--snapshot-json` skips the curses UI and makes no cluster or GitHub calls.
`--include-external` adds sessions whose cwd is outside the workspace root.
Native Codex panes are navigable through cmux. Activity stays unreported unless
an existing hook reports it.
Nothing is inferred from pane names. Source paths, roles, and project paths stay
in local configuration. No machine-specific paths are checked in.

Checks:

```bash
python3 -m unittest discover -s . -p 'test_*.py' -v
python3 check_live.py <room-url>
python3 check_live.py <room-url> --config .control-room/config.json
python3 check_live.py <room-url> --browser <surface> --project <name> --other-project <name>
python3 check_tracing.py <room-url> --config .control-room/config.json
```

Focus the cmux browser pane before running browser checks.
The live check reads a running cmux instance and registered sources. It creates
a temporary git repository for file checks. Browser checks switch project views
and open a review, then restore the supplied URL. They do not send agent input.

Design references: [NN/g progressive disclosure](https://www.nngroup.com/articles/progressive-disclosure/),
[NASA display guidance](https://www.nasa.gov/reference/appendix-f-vol-2/),
[Factory Mission Control](https://docs.factory.com/missions/running-app),
[AgentScope teams](https://docs.agentscope.io/en/versions/2.0.11dev/deploy/agent-team),
[Dify run logs](https://docs.dify.ai/en/cloud/use-dify/monitor/logs),
[ChatDev](https://github.com/OpenBMB/ChatDev),
[Coze Studio](https://github.com/coze-dev/coze-studio).
