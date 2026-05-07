# First Rules of Code Club
- First rule of code club; we do not do what the user never asked to do.
- Second rule of code club; we do not invent stuff that has already been invented.
- Third rule of code club; no bloat, no shit script for the giggles.

# Adamantium (non-negotiables)
- **In production, SOTA > 80/20.** Real prod gets done right. The 80/20 mindset is for "on va pas passer 40 ans sur un bouton": prototypes, internal tools, throwaway scripts. Don't confuse the two.
- **Read the context before touching anything.** Surrounding files, callers, existing patterns, recent commits. No blind edits, no fix-on-assumption. If still uncertain after looking, report back instead of guessing.
- **Never hardcode, never mock.** Spot any, remove them.
- **Hors scope n'existe pas.** Broken test, dead code, hardcoded value, obvious bug spotted in passing? Fix it now, or follow-up commit if it bloats the diff. Never "I'll open a ticket"; the ticket never happens, rot compounds.
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

# Writing Style (user-facing content only)
Docs, blog, MDX, README, changelog, error messages, OG/meta. Not chat replies.
- No em dashes. LLM tell. Use periods, commas, colons, restructure.
- No "it's not X, it's Y" rhetorical pattern. Same tell.
- Docs are reference, not editorial. No "Why this matters", no vendor comparisons, no salesmanship. Show the command, show the response.
- Before shipping, grep for em dashes and rewrite.

# Tools
- `agent-browser` (`/opt/homebrew/bin/agent-browser`): browser automation. Daemon persists, chain with `&&`.
  - Inspect: `snapshot -i` (a11y tree, refs `@e1`...), `screenshot [--annotate|--full]`
  - Navigate: `open <url>`, `back`, `reload`
  - Interact by ref: `click @e2`, `fill @e3 "text"`, `press Enter`
  - Find: `find role button click --name Submit`
  - Reuse session: `--profile Default` or `--session-name <name>`
  - Use for: local dev UI tests, UI bug repro, frontend verification. Prefer over guessing when a visual check would settle it.
