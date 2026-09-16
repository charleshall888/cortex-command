---
name: backlog
description: Add, list, pick, or archive project backlog items.
argument-hint: "<subcommand> [args]"
---

# Backlog

Markdown files with YAML frontmatter in `cortex/backlog/`, named `NNN-slug.md` — `NNN` is the stable cross-reference (`blocks: [7]`); the slug may drift after retitling. Read `${CLAUDE_SKILL_DIR}/references/schema.md` when creating or validating items. Every item verb accepts any reference form: numeric ID, slug, UUID prefix, lifecycle slug, or title phrase.

Subcommand: $ARGUMENTS (first word = subcommand). Bare invocation → offer the subcommands as choices.

- **add** — `cortex-create-backlog-item --title "{{title}}" --status backlog --type {{type}} --priority {{priority}}` (defaults `feature`/`medium`; `--parent NNN`, `--blocked-by NNN...`, `--blocks NNN...`, `--tags`, `--areas` when given), then open the file for review.
- **new** — `/backlog-author compose` for an authored body, then `cortex-create-backlog-item --title "{{title}}" --status backlog --type {{type}} --body "..."`; not opened for editing.
- **list** — `cortex-generate-backlog-index` if `cortex/backlog/index.md` is missing (a local cache), then present it as a summary table.
- **archive** — `cortex-update-item {{item}} --status complete|abandoned` — updates in place, cascades `blocked-by` cleanup, auto-closes parent epics when all children are terminal, regenerates the index. Closes regardless of status, so warn before closing a `backlog` or `in_progress` item.
- **pick** — `cortex-backlog-ready`; take the first non-empty priority group (`critical → contingent`): one item offered directly, several as the top 4 by priority (`"NNN — Title"`, noting omissions), none as "the backlog is clear". Then ask **Start work** (`/cortex-core:refine {{item}}`, or `/cortex-core:build {{item}}` when refined), **View details**, or **Mark in-progress** (status `in_progress`, bump `updated`).
- **ready** — `cortex-backlog-ready`; non-zero exit → report the error JSON (suggest `reindex` if malformed). Render each non-empty group as `### {Priority}` then `- **{id}** {title}`; all empty → `Backlog is clear`.
- **reindex** — `cortex-generate-backlog-index`; report the item count for `index.json` and `index.md`.
