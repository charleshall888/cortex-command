---
name: backlog
description: Manage project backlog items as individual markdown files with YAML frontmatter. Use when user says "/backlog", "backlog add", "backlog list", "backlog pick", "add to backlog", "show backlog", "archive backlog item", "what's ready", "pick a backlog item", or asks to create/view/manage/select backlog items.
inputs:
  - "subcommand: string (required) — add|list|pick|ready|archive|reindex"
  - "title: string (optional, with add) — title of the new backlog item to create"
  - "item: string (optional, with archive) — slug or number of item to archive"
outputs:
  - "backlog/NNN-slug.md — for add subcommand"
  - "stdout — for list and ready subcommands"
  - "/lifecycle {{item}} invocation — for pick subcommand"
preconditions:
  - "Run from project root"
  - "backlog/ directory exists"
argument-hint: "<subcommand> [args]"
---

# Backlog

Manage a file-based project backlog. Each item is a standalone markdown file with YAML frontmatter in `backlog/` (active) or `backlog/archive/` (complete/abandoned).

Subcommand: $ARGUMENTS (first word = subcommand, remainder = subcommand args; empty = list backlog).

## Invocation

`/backlog {{subcommand}}` — run the specified subcommand. When `{{subcommand}}` is `add`, provide `{{title}}` to name the new item. When `{{subcommand}}` is `archive`, provide `{{item}}` to identify the target.

## Frontmatter Schema

Read `${CLAUDE_SKILL_DIR}/references/schema.md` when creating or validating items — it contains the field table, enum values, and item template.

## Filename Convention

Files are named `NNN-slug.md` where `NNN` is a zero-padded three-digit sequential ID and `slug` is a lowercase-kebab-case summary. The numeric prefix is the stable ID used in cross-references (`blocks: [7]`). Slug drift after title changes is cosmetic and does not break references.

Examples: `001-complete-phase-commits.md`, `014-add-search-feature.md`

## Subcommands

When invoked without a `{{subcommand}}` (just `/backlog`), present the available actions via `AskUserQuestion`:

- **pick** — Select an open item to work on
- **list** — Show the backlog summary table
- **add** — Create a new backlog item
- **ready** — Show unblocked items ready to work on
- **archive** — Move a resolved item to the archive
- **reindex** — Regenerate the backlog index

### add

Create a new backlog item from `{{title}}`.

1. Run `cortex-create-backlog-item --title "{{title}}" --status backlog --type {{type}} --priority {{priority}}` (type defaults to `feature`, priority defaults to `medium` unless user specifies). Pass `--parent NNN` if the user specified a parent epic.
2. Open the created file for the user to review or edit the body

### list

Present the current backlog summary.

1. Read `backlog/index.md`
2. Present the summary table to the user
3. If `backlog/index.md` does not exist, suggest running `reindex` first

### archive

Update the item's status in place using `update_item.py`:

```bash
cortex-update-item {{item}} status=complete               # mark complete
cortex-update-item {{item}} status=abandoned              # mark abandoned
```

This updates frontmatter in place (no file move), cascades `blocked-by` cleanup, auto-closes parent epics when all children are terminal, and regenerates the index.

Warn the user before closing a `backlog` or `in_progress` item — the script will close it
regardless of current status.

### pick

Interactive item selector. Presents open backlog items as a selectable list.

1. Read `backlog/index.json`. If missing, report "Run `/backlog reindex` first" and stop.
2. Filter to actionable items: `status` is `backlog`, `refined`, or `in_progress`, and `blocked_by` is empty (`[]`) or all blockers resolved. Prefer `status: refined` items (spec-approved, overnight-eligible) — list them first within each priority tier.
3. Sort by priority (critical → low), then ID ascending
5. If no actionable items exist, report that the backlog is clear
6. If only 1 item exists, present it directly and ask if the user wants to start it
7. If 2-4 items exist, present all via `AskUserQuestion` with one question:
   - Each option's `label` is `"NNN — Title"` (ID and title)
   - Each option's `description` includes priority and type from the index
8. If 5+ items exist, present the top 4 by priority via `AskUserQuestion` and note how many additional items were omitted
9. After the user selects an item, ask what they'd like to do with it using a second `AskUserQuestion`:
   - **Start lifecycle** — invoke `/lifecycle {{item}}` to begin structured development
   - **View details** — read and present the full item file
   - **Mark in-progress** — update the item's status to `in_progress` and `updated` date

### ready

Report which items are ready to work on.

1. Read `backlog/index.md`
2. Present items from the **Refined** and **Backlog** sections (items with no unresolved `blocked-by` entries)
3. If `backlog/index.md` does not exist, suggest running `reindex` first

### reindex

Regenerate the backlog index.

1. Run `cortex-generate-backlog-index`
2. Report the result (item count for both `index.json` and `index.md`)
