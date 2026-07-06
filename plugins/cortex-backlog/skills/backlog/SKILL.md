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

Manage a file-based project backlog: standalone markdown files with YAML frontmatter in `cortex/backlog/` (active) or `cortex/backlog/archive/` (complete/abandoned).

Subcommand: $ARGUMENTS (first word = subcommand, remainder = args; empty = list backlog).

## Schema & Filenames

Read `${CLAUDE_SKILL_DIR}/references/schema.md` when creating or validating items — field table and enum values. Files are named `NNN-slug.md`: `NNN` is a zero-padded three-digit sequential ID (the stable cross-reference used in `blocks: [7]`); `slug` is lowercase-kebab-case and may drift cosmetically after retitling.

## Subcommands

No `{{subcommand}}` (bare `/cortex-backlog:backlog`): present the subcommands below via `AskUserQuestion`.

### add

`cortex-create-backlog-item --title "{{title}}" --status backlog --type {{type}} --priority {{priority}}` (type defaults `feature`, priority `medium` unless specified; `--parent NNN` for a parent epic; `--tags`/`--areas` space-separated when specified), then open the created file for review.

### new

Invoke `/backlog-author interview "{{title}}"` for a fully authored body, then `cortex-create-backlog-item --title "{{title}}" --status backlog --type {{type}} --body "..."` with it (unlike `add`, not opened for editing — already authored).

### list

If `cortex/backlog/index.md` is missing, run `cortex-generate-backlog-index` (a local, non-version-controlled cache); read and present it as a summary table.

### archive

`cortex-update-item {{item}} --status complete` or `--status abandoned` updates frontmatter in place (no file move), cascades `blocked-by` cleanup, auto-closes parent epics when all children are terminal, and regenerates the index. Warn before closing a `backlog` or `in_progress` item — it closes regardless of status.

### pick

Run `cortex-backlog-ready` (error handling: see `ready`). Take the first non-empty priority group (`critical → contingent`) and present it via `AskUserQuestion`: one item → offer directly; several → top 4 by priority noting omissions, each labeled `"NNN — Title"` (priority, type); none → the backlog is clear. Then ask what to do via a second `AskUserQuestion`: **Start lifecycle** (`/cortex-core:lifecycle {{item}}`), **View details** (read and present it), or **Mark in-progress** (set status `in_progress`, bump `updated`).

### ready

Run `cortex-backlog-ready`; on non-zero exit, parse the error JSON and report it (suggest `/cortex-backlog:backlog reindex` if malformed). For each non-empty group, render `### {Priority Title}` (e.g. `### Critical`) then `- **{id}** {title}` bullets, in order. If all groups are empty, report `Backlog is clear`.

### reindex

Run `cortex-generate-backlog-index`; report the item count for both `index.json` and `index.md`.
