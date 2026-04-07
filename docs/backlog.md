# Backlog System Reference

**For:** Users creating and managing features in the backlog — including preparing items for overnight execution.
**Assumes:** Git and Claude Code are set up.

The backlog is a flat directory of numbered markdown files (`backlog/NNN-slug.md`). Each file contains YAML frontmatter describing the item, followed by an optional markdown body. The overnight orchestration system reads these files to select work; the `/backlog` skill manages them interactively.

---

## YAML Frontmatter Schema

Every backlog item uses the following YAML frontmatter contract. Fields listed as required must be present; optional fields default to `null` or `[]` when absent.

| Field | Type | Required | Values / Notes |
|-------|------|----------|----------------|
| `schema_version` | string | yes | `"1"` |
| `uuid` | string | yes | UUID v4 — stable cross-reference key |
| `title` | string | yes | Short human-readable name |
| `status` | enum | yes | `backlog`, `refined`, `in_progress`, `implementing`, `review`, `complete`, `abandoned` |
| `priority` | enum | yes | `critical`, `high`, `medium`, `low` |
| `type` | enum | yes | `feature`, `bug`, `chore`, `spike`, `idea`, `epic` |
| `tags` | array | no | Inline YAML only: `[tag1, tag2]` |
| `created` | date | yes | `YYYY-MM-DD` |
| `updated` | date | yes | `YYYY-MM-DD` — auto-updated by `update_item.py` |
| `lifecycle_slug` | string | no | Kebab-case slug linking to `lifecycle/{slug}/`; or `null` |
| `lifecycle_phase` | string | no | Current lifecycle phase (`research`, `specify`, `plan`, `implement`, `review`, `complete`); or `null` |
| `session_id` | string | no | ID of the overnight session currently working on this item; or `null` |
| `blocks` | array | no | Inline YAML only: `[1, 5]` (numeric IDs of items this item blocks) |
| `blocked-by` | array | no | Inline YAML only: `[3, 7]` (numeric IDs of items blocking this one) |
| `parent` | integer | no | Numeric ID of a parent epic item |
| `research` | string | no | Path to prior research artifact (e.g. `research/topic/research.md`); set by `/discovery` |
| `spec` | string | no | Path to spec artifact; set by `/refine` (e.g. `lifecycle/{slug}/spec.md`) |
| `discovery_source` | string | no | Path to the `/discovery` research artifact that produced this ticket; triggers auto-copy to lifecycle on `/lifecycle` start |
| `repo` | string | no | Absolute path to target repository (e.g. `~/Workspaces/wild-light`); `null` = current repo (default) |
| `complexity` | string | no | Lifecycle complexity tier (`simple`, `standard`, `complex`) |
| `criticality` | string | no | Criticality tier (`low`, `medium`, `high`, `critical`) |

**Inline array syntax is mandatory.** All array fields (`tags`, `blocks`, `blocked-by`) must use `[value1, value2]` form — never the multiline `- item` form.

### Minimal item template

```markdown
---
schema_version: "1"
uuid: <uuid4>
title: Short descriptive name
status: backlog
priority: medium
type: feature
tags: []
created: YYYY-MM-DD
updated: YYYY-MM-DD
lifecycle_slug: null
lifecycle_phase: null
session_id: null
blocks: []
blocked-by: []
---

Optional markdown body describing the problem and acceptance criteria.
```

---

## `/backlog` Skill Workflow

The `/backlog` skill manages backlog items interactively. Invoke with a subcommand:

```
/backlog <subcommand>
```

When invoked without a subcommand, the skill presents the available actions.

### `add`

Creates a new backlog item from a title.

1. Scans `backlog/` and `backlog/archive/` for the highest existing numeric ID.
2. Assigns the next sequential ID (zero-padded to three digits).
3. Derives a slug from the title (lowercase, kebab-case).
4. Creates `backlog/NNN-slug.md` with populated frontmatter and defaults (`status: backlog`, `priority: medium`, `type: feature`).
5. Opens the file for review or editing.
6. Regenerates the backlog index.

### `list`

Reads `backlog/index.md` and presents the summary table. Suggests running `reindex` if the index does not exist.

### `pick`

Interactive item selector. Filters to actionable items (status `backlog` or `in_progress`, not blocked), sorts by priority then ID, and presents a selection. After selection, offers to start a lifecycle, view details, or mark as in-progress.

### `ready`

Reads `backlog/index.md` and presents items from the Ready section (items with no unresolved `blocked-by` entries).

### `archive`

Updates item status in place using `update_item.py`:

```bash
python3 backlog/update_item.py <item> status=complete
python3 backlog/update_item.py <item> status=abandoned
```

No file is moved. The script cascades `blocked-by` cleanup across the backlog and auto-closes parent epics when all children reach a terminal status.

### `reindex`

Runs `generate-backlog-index` to regenerate `backlog/index.md` and `backlog/index.json`.

---

## Overnight Readiness Gates

Before an item is eligible for overnight execution, `filter_ready()` in `claude/overnight/backlog.py` applies five checks in order. An item fails at the first gate it does not pass.

**Gate 1 — Status.** The item's `status` must be one of the eligible values: `backlog`, `in_progress`, `implementing`, or `refined`. Items in any other status (including `complete`, `abandoned`, `review`) are excluded.

**Gate 2 — Blocked.** The item's `blocked-by` list must not contain any item that is itself in a non-terminal status. If any blocker is still active, the item is ineligible. Terminal statuses that satisfy this gate are (canonical source: `claude/common.py`): `complete`, `abandoned`, `done`, `resolved`, `wontfix`, `wont-do`, `won't-do`.

**Gate 3 — Type (epics excluded).** Items with `type: epic` are non-implementable and always excluded. Epics are containers produced by `/discovery`; their children are the actionable items.

**Gate 4 — Research artifact.** The file `lifecycle/{slug}/research.md` must exist on disk, where `{slug}` is taken from `lifecycle_slug` (falling back to a slugified form of the title). The item's `research` frontmatter field is not consulted for this check.

**Gate 5 — Spec artifact.** The file `lifecycle/{slug}/spec.md` must exist on disk. A `plan.md` is not required at this stage — if missing, it is generated by the overnight session before implementation begins.

> **Note — gates check file existence, not content quality.** Gates 4 and 5 only verify that `research.md` and `spec.md` exist on disk. A spec file that exists but contains only a one-line problem statement will pass Gate 5 — the item will be queued — but the overnight session will be unable to produce a verifiable plan and may produce incorrect or incomplete work. See the thin spec example below.

**Thin spec example.** A spec like the following passes Gate 5 because the file exists, but causes the plan agent to defer or produce low-quality output — it has no Requirements section and no acceptance criteria for the plan agent to check against:

```markdown
# Specification: add-dark-mode

## Problem Statement

Users want a dark mode.
```

When the plan agent opens this spec, it has no verifiable criteria (no requirements, no acceptance criteria, no scope boundaries) to build a task list against. The overnight session may produce an over-broad plan, miss key constraints, or stall at review. To avoid this, ensure every spec includes at minimum a Requirements section with concrete acceptance criteria before the item enters the overnight queue.

Items that pass all five gates are scored and grouped into batches for overnight execution.

---

## Discovery Bootstrapping Lifecycle Artifacts

When `/discovery` decomposes research into backlog tickets, it writes a `discovery_source` frontmatter field on each created item pointing to the research artifact (e.g. `research/my-topic/research.md`).

When `/lifecycle` starts on an item that has `discovery_source` set, it automatically loads the prior research, presents a summary, and asks whether to skip re-investigation (default: skip). In overnight contexts the skip is applied automatically. If the user declines, the research artifact is loaded as additional context and investigation proceeds normally.

This coupling means that features discovered via `/discovery` arrive at lifecycle with research already in hand, avoiding redundant investigation.

---

## `update_item.py` CLI Reference

`backlog/update_item.py` is the canonical tool for automated write-backs to backlog frontmatter. It is used by the `/refine` skill, lifecycle hooks, and the overnight pipeline to update items without manual editing.

```
python3 backlog/update_item.py <slug-or-uuid> key=value [key=value ...]
```

**Lookup.** The first argument is matched against item filenames (exact stem, then substring), then against `uuid` fields. UUID prefix matching is supported.

**Field updates.** Each `key=value` argument sets a frontmatter field. The `updated` field is always set to today's date automatically. Use `key=null` or `key=none` to clear a field.

**Side effects on every update:**
- Writes the updated file atomically (write-then-rename).
- Appends `status_changed` or `phase_changed` events to the sidecar `{stem}.events.jsonl` log.
- Regenerates `backlog/index.json` and `backlog/index.md` via `generate_index.py`.

**Additional side effects for terminal status transitions** (`complete`, `abandoned`, `done`, `resolved`, `wontfix`, `wont-do`, `won't-do` — full list in `claude/common.py`):
- Removes the closed item's ID and UUID from `blocked-by` arrays across all active backlog items.
- Auto-closes the parent epic if all sibling items have reached a terminal status.

**Exit codes:** 0 on success; 1 if the item is not found or no fields are provided.

### Examples

```bash
# Mark an item complete by slug
python3 backlog/update_item.py 030-cf-tunnel-fallback-polish status=complete

# Update lifecycle phase by UUID
python3 backlog/update_item.py 550e8400-... lifecycle_phase=implement

# Clear the session_id field
python3 backlog/update_item.py 030-cf-tunnel-fallback-polish session_id=null

# Update multiple fields at once
python3 backlog/update_item.py 030-cf-tunnel-fallback-polish status=complete session_id=null
```

---

## Global Deployment (Cross-Repo Use)

Backlog scripts can be deployed to `~/.local/bin/` so they are available as commands in any working directory, not just when invoked via `python3 backlog/...` from the repo root.

### Adding a new deployable script

1. **Add the script file to the repo** (e.g., `backlog/my_script.py`).
2. **Add a symlink entry to `just deploy-bin`** in `justfile`:
   ```
   ln -sf $(pwd)/backlog/my_script.py ~/.local/bin/my-script
   ```
3. **Add a check entry to `just check-symlinks`** in `justfile`:
   ```
   check ~/.local/bin/my-script
   ```
4. **Use `Path.cwd()` for repo-local directory references** inside the script (not `_PROJECT_ROOT` or `Path(__file__).parent`).

Run `just deploy-bin` to create the symlinks on the current machine.

### How symlink resolution works

When a script is invoked via the `~/.local/bin/` symlink, Python resolves `__file__` to the **real script path** (not the symlink path). This means `Path(__file__).resolve().parent` correctly points into the repo regardless of how the script was invoked — making it safe to use for Python import path setup:

```python
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
```

### Why repo-local dirs must use `Path.cwd()`

Even though `Path(__file__).resolve().parent` correctly locates the script inside the repo, **it does not know which repo the user is currently working in**. When running `generate-backlog-index` from a different project, `Path(__file__).parent` would still resolve to the cortex-command backlog directory — the wrong project.

Use `Path.cwd()` for any directory that is relative to the user's current working directory:

```python
BACKLOG_DIR = Path.cwd() / "backlog"
```

### Currently-deployed scripts

| Command | Source file |
|---------|-------------|
| `update-item` | `backlog/update_item.py` |
| `create-backlog-item` | `backlog/create_item.py` |
| `generate-backlog-index` | `backlog/generate_index.py` |

---

## Keeping This Document Current

This document describes the backlog system as implemented at the time of writing. When any of the following change, update this document:

- `claude/overnight/backlog.py` — changes to `ELIGIBLE_STATUSES`, `TERMINAL_STATUSES`, or `filter_ready()` gate logic
- `skills/backlog/references/schema.md` — additions or removals from the frontmatter schema
- `skills/backlog/SKILL.md` — new subcommands or changed subcommand behavior
- `backlog/update_item.py` — changes to the CLI interface or side-effect behavior
- `skills/discovery/SKILL.md` — changes to how `discovery_source` is written or consumed
