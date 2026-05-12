# Research: Remove dangling remote/SETUP.md references from docs/setup.md

## Codebase Analysis

**File that will change:**
- `docs/setup.md` — the only file requiring edits

**Three specific locations:**
1. **Line 166** — `remote/SETUP.md` row in the "Customize for Your Machine" table
2. **Line 284** — `> **Customize**` blockquote referencing `remote/SETUP.md`
3. **Line 286** — Paragraph with markdown link to `../remote/SETUP.md`

**Confirmed:** The `remote/` directory does not exist in the repo. All three references are dangling.

**Other files mentioning `remote/SETUP.md`** (all historical context documenting the problem — no changes needed):
- `requirements/remote-access.md` line 80 — flags as open question
- `backlog/009`, `011`, `012` — mention in passing
- Various lifecycle artifacts — document the gap

**Patterns to follow:**
- Retain the `## Remote Access` section heading — Remote Access is a real feature area per `requirements/remote-access.md`
- Keep `---` horizontal rule separators between sections (consistent throughout the file)
- Several sections use `> **Customize**: ...` blockquotes (lines 37, 168, 284) — the one on line 284 should be removed since there's nothing to customize in this repo
- The OS Compatibility table (lines 292–305) does not reference "Remote Access," so no changes needed there

## Web Research

**Best-fit pattern: section stub with pointer.** Keep a minimal section heading with a one-liner pointing to the other repo, so users scanning the TOC still discover the capability exists.

**Anti-patterns to avoid:**
- Leaving broken links (worse than no link)
- Duplicating remote-access setup instructions (creates maintenance drift)
- Vague "see elsewhere" without a specific repo name

## Requirements & Constraints

**Supporting requirements:**
- `requirements/remote-access.md` line 80: explicitly flags the broken reference as "a documentation gap [that] should be addressed as a separate task"
- `requirements/project.md` lines 48, 51: remote access setup automation belongs in machine-config, not cortex-command
- `requirements/project.md` line 44: cortex-command owns remote access *integration* (hooks, notifications, session management); machine-config owns the *setup* (installation, configuration)

**Architectural constraints:**
- Complexity must earn its place (`requirements/project.md` line 19) — a brief redirect note is the simplest correct solution
- The remote-access *requirements* (session persistence, reattachment, mobile alerting) are unaffected by this documentation change
