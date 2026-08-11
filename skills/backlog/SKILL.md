---
name: backlog
description: Manage project backlog items as individual markdown files with YAML frontmatter. Use when user says "/cortex-backlog:backlog", "backlog add", "backlog list", "backlog pick", "add to backlog", "show backlog", "archive backlog item", "what's ready", "pick a backlog item", or asks to create/view/manage/select items.
argument-hint: "<subcommand> [args]"
---

# Backlog

Standalone markdown files with YAML frontmatter in `cortex/backlog/`, named `NNN-slug.md` — `NNN` is the stable cross-reference used in `blocks: [7]`; the slug may drift cosmetically after retitling. Read `${CLAUDE_SKILL_DIR}/references/schema.md` when creating or validating items. Every item verb accepts any reference form: numeric ID, slug, UUID prefix, lifecycle slug, or title phrase.

Subcommand: $ARGUMENTS (first word = subcommand, remainder = args). Bare invocation: present the subcommands below via `AskUserQuestion`.

### add

`cortex-create-backlog-item --title "{{title}}" --status backlog --type {{type}} --priority {{priority}}` (defaults `feature`/`medium`; `--parent NNN`, `--blocked-by NNN...`, `--blocks NNN...`, `--tags`, `--areas` when specified), then open the created file for review.

### new

Invoke `/backlog-author compose` for an authored body, then `cortex-create-backlog-item --title "{{title}}" --status backlog --type {{type}} --body "..."` with it. Unlike `add`, not opened for editing — already authored.

### list

Run `cortex-generate-backlog-index` if `cortex/backlog/index.md` is missing (a local, non-version-controlled cache), then present it as a summary table.

### archive

`cortex-update-item {{item}} --status complete|abandoned` — updates frontmatter in place, cascades `blocked-by` cleanup, auto-closes parent epics when all children are terminal, regenerates the index. Closes regardless of status, so warn before closing a `backlog` or `in_progress` item.

### pick

Run `cortex-backlog-ready`. Take the first non-empty priority group (`critical → contingent`) and present it via `AskUserQuestion` — one item offered directly, several as the top 4 by priority (label `"NNN — Title"`) noting omissions, none as "the backlog is clear". Then ask: **Start work** (`/cortex-core:refine {{item}}`, or `/cortex-core:build {{item}}` when already refined), **View details**, or **Mark in-progress** (status `in_progress`, bump `updated`).

### ready

Run `cortex-backlog-ready`; on non-zero exit parse the error JSON and report it (suggest `reindex` if malformed). Render each non-empty group as `### {Priority}` then `- **{id}** {title}`. All empty → `Backlog is clear`.

### reindex

Run `cortex-generate-backlog-index`; report the item count for `index.json` and `index.md`.
