---
name: backlog
description: Add, list, pick, or archive project backlog items.
argument-hint: "<subcommand> [args]"
---

# Backlog

Markdown files with YAML frontmatter in `cortex/backlog/`, named `NNN-slug.md`. `NNN` is the stable id other items cite (`blocks: [7]`); the slug can go stale after a retitle. Read `${CLAUDE_SKILL_DIR}/references/schema.md` when creating or validating items. Every item command accepts a numeric ID, slug, UUID prefix, lifecycle slug, or title phrase.

Subcommand: $ARGUMENTS (first word = subcommand). No subcommand → offer them as choices.

- **add** — `cortex-create-backlog-item --title "{{title}}" --status backlog --type {{type}} --priority {{priority}}` (defaults `feature`/`medium`; add `--parent NNN`, `--blocked-by NNN...`, `--blocks NNN...`, `--tags`, `--areas` when given). Then open the file for review.
- **new** — `/backlog-author compose` writes the body, then `cortex-create-backlog-item --title "{{title}}" --status backlog --type {{type}} --body "..."`. Do not open it for editing.
- **list** — if `cortex/backlog/index.md` (a local cache) is missing, run `cortex-generate-backlog-index`. Then show it as a summary table.
- **archive** — `cortex-update-item {{item}} --status complete|abandoned`. It updates in place, clears the item from others' `blocked-by`, closes parent epics whose children are all done, and regenerates the index. It closes an item in any status, so warn before closing a `backlog` or `in_progress` item.
- **pick** — `cortex-backlog-ready`; take the first non-empty priority group (`critical → contingent`). One item → offer it. Several → offer the top 4 by priority (`"NNN — Title"`) and note omissions. None → "the backlog is clear". Then ask **Start work** (`/cortex-core:refine {{item}}`, or `/cortex-core:build {{item}}` when refined), **View details**, or **Mark in-progress** (status `in_progress`, bump `updated`).
- **ready** — `cortex-backlog-ready`. Non-zero exit → report the error JSON (suggest `reindex` if malformed). Show each non-empty group as `### {Priority}` then `- **{id}** {title}`. All empty → `Backlog is clear`.
- **reindex** — `cortex-generate-backlog-index`; report the item count for `index.json` and `index.md`.
