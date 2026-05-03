# First Rules of Code Club
- First rule of code club; we do not do what the user never asked to do.
- Second rule of code club; we do not invent stuff that has already been invented.
- Third rule of code club; no bloat, no shit script for the giggles.

# Core Philosophy
- Complexity is the enemy - prefer simple, obvious solutions.
- Say "no" to features/abstractions unless absolutely necessary.
- Working code > elegant code > clever code.

# Commandments
- KISS > LoB > DRY > SOLID - simplicity trumps all, keep behaviour where it belongs over separating concerns.
- Do not fix based on assumption but only certitude, if you are not sure that something is the actual issue, don't just implement something; you move to another assumption, see if you can find the actual explicit issue and if not; report back.
- Wait for natural boundaries before abstracting.
- DO NOT be a sycophant; we are here to do good work not to be overly pleasant.
- ABSOLUTELY NEVER HARDCODE, or Mock and remove if you see any.
- Hors scope n'existe pas. If you stumble on a broken test, dead code, a hardcoded value, or an obvious bug while doing something else, fix it in the same session. Follow-up commit if it would bloat the diff. Never "I'll open a ticket"; the ticket never happens and rot compounds.

# Project Processes
- Summarise the problem statement before starting any fix
- Small, incremental changes only - no big rewrites

# Technical Considerations
- We don't do transitional implementation; all in or not
- Log strategically at decision points only - no noise
- Review the codebase and existing documentation before implementing new items
- Integration tests > unit tests for real validation
- Master debugging tools over adding print statements; we prefer directly in the CLI debugging.
- Prefer active polling loops over passive waits. Don't block, retry with bounded attempts. Ref: `for i in $(seq 1 $END); do echo $i; done`

# Code Quality
- Don't bloat.
- If you find a naming, api or alike issue, always do a broad search to see if its applied anywhere else as well
- In general, when relevant; remove more code than you add - fight complexity actively
- This is not a demo project, this is production, be mindful everything is sensible
- Readable code with intermediate variables > clever one-liners
- 80/20 solutions - Favor delivering core value without bells and whistles

# Code Organisation
- NO EXCESSIVE LAYERS of new functionalities on top of old one - be purposeful

# Writing Style (user-facing content)
Applies to anything a user reads: docs, blog, marketing copy, MDX, README, changelog, error messages, OG/meta. Does NOT apply to assistant chat replies in this session.
- No em dashes (—). They read as LLM tells. Use periods, commas, colons, or restructure.
- No "it's not X, it's Y" / "not X — Y" rhetorical pattern. Same tell.
- Docs are reference material, not editorial. No "Why this matters" sections, no vendor comparisons, no salesmanship. Show the command, show the response. The reader decides if it's good without being told.
- Before shipping any user-facing text, grep for `—` and rewrite.

# Tools Available
- `agent-browser` (CLI, installed at `/opt/homebrew/bin/agent-browser`): browser automation for agents. Use it to drive Chrome from the shell: navigate, inspect, interact, screenshot. Daemon persists between calls, so chain with `&&`.
  - Inspect: `agent-browser snapshot -i` (a11y tree with refs `@e1`, `@e2`…), `agent-browser screenshot [--annotate|--full]`
  - Navigate: `agent-browser open <url>`, `back`, `reload`
  - Interact by ref: `click @e2`, `fill @e3 "text"`, `press Enter`, `hover @e1`
  - Find semantically: `agent-browser find role button click --name Submit`
  - Attach to running Chrome: `--cdp 9222` or `--auto-connect`
  - Reuse login state: `--profile Default` or `--session-name <name>`
  - Typical flow: `open` → `snapshot -i` → act by ref → `screenshot` if vision needed
  - Use it for: testing local dev UIs, reproducing UI bugs, scraping rendered pages, verifying frontend changes end-to-end. Prefer it over guessing when a visual check would settle the question.
