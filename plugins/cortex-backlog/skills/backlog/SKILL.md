---
name: backlog
description: Manage project backlog items as individual markdown files with YAML frontmatter. Use when user says "/cortex-backlog:backlog", "backlog add", "backlog list", "backlog pick", "add to backlog", "show backlog", "archive backlog item", "what's ready", "pick a backlog item", or asks to create/view/manage/select items.
inputs:
  - "subcommand: string (required) — add|list|pick|ready|archive|reindex"
  - "title: string (optional, with add) — title of the new backlog item to create"
  - "item: string (optional, with archive) — slug or number of item to archive"
outputs:
  - "cortex/backlog/NNN-slug.md — for add subcommand"
  - "stdout — for list and ready subcommands"
  - "/cortex-core:lifecycle {{item}} invocation — for pick subcommand"
preconditions:
  - "Run from project root"
  - "cortex/backlog/ directory exists"
argument-hint: "<subcommand> [args]"
---

# Backlog

Manage a file-based project backlog. Each item is a standalone markdown file with YAML frontmatter in `cortex/backlog/` (active) or `cortex/backlog/archive/` (complete/abandoned).

Subcommand: $ARGUMENTS (first word = subcommand, remainder = subcommand args; empty = list backlog).

## Frontmatter Schema

Read `${CLAUDE_SKILL_DIR}/references/schema.md` when creating or validating items — it contains the field table, enum values, and item template.

## Filename Convention

Files are named `NNN-slug.md` where `NNN` is a zero-padded three-digit sequential ID and `slug` is a lowercase-kebab-case summary. The numeric prefix is the stable cross-reference ID (`blocks: [7]`); slug drift after retitling is cosmetic.

Examples: `001-complete-phase-commits.md`, `014-add-search-feature.md`

## Subcommands

When invoked without a `{{subcommand}}` (just `/cortex-backlog:backlog`), present the available actions — the `###` subcommands below — via `AskUserQuestion`.

### add

Create a new backlog item from `{{title}}`.

1. Run `cortex-create-backlog-item --title "{{title}}" --status backlog --type {{type}} --priority {{priority}}` (type defaults to `feature`, priority defaults to `medium` unless user specifies). Pass `--parent NNN` if the user specified a parent epic.
2. Open the created file for the user to review or edit the body

### new

Interview-driven backlog item creation. Delegates body authoring to `/backlog-author`, then writes the item file.

1. Invoke `/backlog-author interview "{{title}}"` to conduct a structured interview and obtain a fully authored body
2. Run `cortex-create-backlog-item --title "{{title}}" --status backlog --type {{type}} --body "..."` with the body returned by `backlog-author interview`

Unlike `add`, the file is not opened for editing — the body is already authored.

### list

Present the current backlog summary.

1. If `cortex/backlog/index.md` does not exist, run `cortex-generate-backlog-index` to regenerate it (the index is a local cache, not version-controlled)
2. Read `cortex/backlog/index.md`
3. Present the summary table to the user

### archive

Update the item's status in place using `update_item.py`:

```bash
cortex-update-item {{item}} --status complete             # mark complete
cortex-update-item {{item}} --status abandoned            # mark abandoned
```

This updates frontmatter in place (no file move), cascades `blocked-by` cleanup, auto-closes parent epics when all children are terminal, and regenerates the index.

Warn the user before closing a `backlog` or `in_progress` item — the script will close it
regardless of current status.

### pick

Interactive item selector. Presents open backlog items as a selectable list.

1. Run `cortex-backlog-ready`. If exit code is non-zero, parse the error JSON and report the message — suggest running `/cortex-backlog:backlog reindex` if the error indicates a malformed backlog index.
2. Iterate `groups` in order (`critical → contingent`); within each group, iterate `items`. The first non-empty group's items form the selection set. (Group ordering preserves `critical → low` priority; within a group, refined items come first.)
3. Present that group's items for selection: if none, report the backlog is clear; if one, offer it directly; otherwise present via `AskUserQuestion` — up to the top 4 by priority, noting any omitted — each option labeled `"NNN — Title"` with its priority and type from the index.
4. After the user selects an item, ask what they'd like to do with it using a second `AskUserQuestion`:
   - **Start lifecycle** — invoke `/cortex-core:lifecycle {{item}}` to begin structured development
   - **View details** — read and present the full item file
   - **Mark in-progress** — update the item's status to `in_progress` and `updated` date

### ready

Report which items are ready to work on.

1. Run `cortex-backlog-ready`. If exit code is non-zero, parse the error JSON and report the message — suggest running `/cortex-backlog:backlog reindex` if the error indicates a malformed backlog index.
2. For each non-empty group in `groups`, render a markdown subsection: `### {Priority Title}` heading (e.g. `### Critical`, `### High`, `### Medium`, `### Low`, `### Contingent`) followed by `- **{id}** {title}` bullets, in iteration order. If all groups are empty, report `Backlog is clear`.

### reindex

Regenerate the backlog index.

1. Run `cortex-generate-backlog-index`
2. Report the result (item count for both `index.json` and `index.md`)
