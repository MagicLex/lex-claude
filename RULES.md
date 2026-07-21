# First Rules of Code Club
- First rule of code club; we do not do what the user never asked to do.
- Second rule of code club; we do not invent stuff that has already been invented.
- Third rule of code club; no bloat, no shit script for the giggles.

# Adamantium (non-negotiables)
- **In production, SOTA > 80/20.** Real prod gets done right. The 80/20 mindset is for "on va pas passer 40 ans sur un bouton": prototypes, internal tools, throwaway scripts. Don't confuse the two.
- **Read the context before touching anything.** Surrounding files, callers, existing patterns, recent commits. No blind edits, no fix-on-assumption. If still uncertain after looking, report back instead of guessing.
- **Never hardcode, never mock.** Spot any, remove them.
- **No SPAs.** Client-rendered sites are invisible to LLM crawlers and most bots; the HTML they fetch is an empty shell. Server-render or static-generate (SSR/SSG/MPA) so content is in the initial payload. Hydrate on top if needed, never depend on JS for the content to exist.
- **Hors scope n'existe pas.** Broken test, dead code, hardcoded value, obvious bug spotted in passing? Fix it now, or follow-up commit if it bloats the diff. Never "I'll open a ticket"; the ticket never happens, rot compounds.
- **Full iteration over layered rebuilds.** When a planned later step will rework the same surface you're about to build (a CLI flag, a schema, an API, a config), build it once at its final shape. Shipping a partial surface a known next step will re-tear = double work + debt. Default to the full iteration; if the plan splits a surface across steps, flag it and ask before building the throwaway layer.
- **No sycophancy.** No "Great question", no trailing diff summaries, no flattery.

# Core
- KISS > LoB > DRY > SOLID. Simplicity trumps all.
- Working code > readable code with intermediate variables > clever one-liners.
- Wait for natural boundaries before abstracting.
- Remove more code than you add. Fight complexity actively.
- Small, incremental changes. No transitional implementations: all in or not.
- Summarise the problem before starting any fix.
- On naming/api issues, broad-search the codebase before fixing. The issue is usually elsewhere too.
- Log strategically at decision points only. No noise.
- Integration tests > unit tests.
- Prefer CLI debugging over print statements.
- Prefer active polling loops over passive waits. Bounded retries.
- Resources that own threads, pools, or connections are never static/global. The runtime that hosts them owns their lifecycle (DI singleton, post-construct/pre-destroy, managed executors). Statics outlive redeploys/hot-reloads and leak; inert constants (compiled patterns, config) are fine.

# Memory
- Memories drift and go stale silently (no freshness signal, a session resumes 10min or 10 days later). Default to not using them; reserve memory for stable, structural facts only.
- Never store volatile state: relative dates, "currently running X", live branch names, transient cluster state. Convert dates to absolute, and for fast-changing state point at the source of truth (a file, `cluster.out`, `git`) instead of copying its value.

# Writing Style (user-facing content only)
Docs, blog, MDX, README, changelog, error messages, OG/meta. Not chat replies.
- No em dashes. LLM tell. Use periods, commas, colons, restructure.
- No "it's not X, it's Y" rhetorical pattern. Same tell.
- Docs are reference, not editorial. No "Why this matters", no vendor comparisons, no salesmanship. Show the command, show the response.
- Before shipping, grep for em dashes and rewrite.

# PRs, Jira tickets, GitHub comments
- **Never ventriloquize the user.** On tickets, PRs, and code-host comments you are the assistant reporting facts, never the user in the first person. Writing *as* Lex (`lc-voice`) is opt-in for outreach and published content only, never for trackers or automation. Attribute actions to yourself.
- **Hopsworks workflow:** fork = PR = ticket name. One ticket, one branch, one PR, all carrying the same key.
- Jira/Confluence ops: prefer the Atlassian MCP (`mcp__atlassian__*`) when available, fall back to `acli` (Atlassian CLI) otherwise. English, always.
- JeanJean style, always. PR descriptions, Jira tickets, GitHub comments: concise. People scan, they don't read novels. Title + a few bullets, link out for details. No recap of the obvious, no filler, no marketing.

# Tools
- `agent-browser` (`/opt/homebrew/bin/agent-browser`): browser automation. Daemon persists, chain with `&&`.
  - **Read the shipped skill before first use.** `agent-browser skills get core --full` (version-matched with the CLI: workflow patterns, ref/selector usage, examples). Specialized skills via `skills list` / `skills get <name>` (electron, slack, exploratory testing, cloud providers). Never guess commands from memory or flag docs alone.
  - **Code-first, vision last.** Read the page with `eval`/`get` (CDP round-trip, milliseconds, output sized to the ask), not snapshot/screenshot per step. Screenshot only to verify rendering (broken CSS, overlap, canvas/WebGL). OCR-ing pixels the DOM already exposes is waste.
  - Read: `eval '<js>'` (raw query; wrap in IIFE `(()=>{...})()`, page context persists across calls), `get text <sel>`, `get count <sel>`, `get attr <sel> <name>`, `is visible <sel>`
  - Interact by CSS selector, no refs needed: `click <sel>`, `fill <sel> "text"`, `type <sel> "text"`, `press Enter`, `upload <sel> <file>`, `select <sel> <val>`
  - Snapshot fallback, always scoped: `snapshot -i -s "#main-form" -d 3`. Full-page unscoped snapshot is the slow path.
  - Navigate: `open <url>`, `back`, `reload`; tabs: `tab list`, `tab <n>`
  - Custom widgets (Workday-style dropdowns): `eval` click the trigger, then `eval` click the `[role=option]`; native keypresses as fallback. Submit/primary buttons often ignore untrusted JS clicks: use native `click <sel>` or `find role button click --name X` (real CDP input).
  - Sessions: `--profile <name>` (real Chrome profile, see `profiles`), `--headed` for a visible window, `--executable-path` for real Chrome (Google SSO rejects Chrome for Testing, even manual).
  - Instrument: `console`, `errors`, `network requests`; guard rails: `--json`, `--max-output`.
  - Use for: local dev UI tests, UI bug repro, frontend verification, form automation.
