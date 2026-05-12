# Research: Add index regeneration to overnight pre-flight and investigate staleness gaps

## Codebase Analysis

### Overnight Skill Pre-flight Structure

The overnight skill (`skills/overnight/SKILL.md`) follows a Steps 1–8 "New Session Flow":

- **Step 2** (lines 59–73): Batch selection — calls `select_overnight_batch()` from `claude/overnight/backlog.py`. This is where the index is first consumed.
- **Step 7.0** (line 158): `validate_target_repos(selection)`
- **Step 7.1** (line 167): Uncommitted-files check — `git status --porcelain -- lifecycle/ backlog/`
- Steps 7.2–7.7: Session bootstrap, spec extraction, event logging, dashboard check, runner command

**Critical finding**: Batch selection runs in Step 2, not Step 7. The backlog item's proposed insertion point ("Step 7 pre-flight, right before the uncommitted-files check") would only benefit the *next* session, not the current one. To fix the current session's batch selection, regeneration must run before Step 2.

### `select_overnight_batch()` — Load Path and Fallback

File: `claude/overnight/backlog.py`, lines 1005–1114

```python
try:
    all_items = load_from_index(backlog_dir)
except (FileNotFoundError, json.JSONDecodeError) as exc:
    warnings.warn(f"index.json unavailable ({exc}), falling back to file reads")
    all_items = parse_backlog_dir(backlog_dir)
```

Only two exceptions trigger the fallback: `FileNotFoundError` (no `index.json`) and `json.JSONDecodeError` (corrupt JSON). All semantic staleness passes through silently — stale status, renamed lifecycle slugs, added/removed items, new fields.

### `load_from_index()` — No Validation

File: `claude/overnight/backlog.py`, lines 317–354

- Five hard-required fields (`id`, `title`, `status`, `priority`, `type`) raise `KeyError` if absent — but `KeyError` is **not** caught by `select_overnight_batch()`'s fallback guard, so it would propagate as an uncaught exception
- All optional fields use `.get()` with `None` defaults — missing new fields silently return `None`
- No schema version check, no mtime comparison, no field presence validation

### `generate_index.py` vs `generate-index.sh`

| | `generate_index.py` | `generate-index.sh` |
|---|---|---|
| Location | `backlog/generate_index.py` | `skills/backlog/generate-index.sh` |
| Produces | `index.json` + `index.md` | `index.md` only |
| Detects `lifecycle_phase` | Yes (scans `lifecycle/{slug}/` on disk) | No |
| Called by | `just backlog-index`, `update_item.py`, `create_item.py`, skill reindex | No active call sites |
| Global deploy | `~/.local/bin/generate-backlog-index` | Not deployed |

`generate-index.sh` is already bypassed in all active code paths. It produces only `index.md` — never `index.json`. Deprecation is safe.

### `update_item.py` Regeneration

File: `backlog/update_item.py`, lines 409–421

`update_item.py` regenerates the index (both files) after every `update_item()` call. This is non-fatal — failures are warned but don't abort. `create_item.py` also regenerates on item creation.

**The staleness gap**: Index regeneration only triggers through `update_item.py` or `create_item.py`. Direct edits to backlog `.md` files (text editor, `git checkout`, `sed`, manual frontmatter editing) bypass both scripts, leaving `index.json` stale.

### Pre-commit Hook Infrastructure

No hook exists that auto-regenerates the index on commit. The existing hooks system uses Claude Code's PreToolUse/SessionStart/SessionEnd events, not native git hooks. No native `pre-commit` hook is installed. Building one would require either a native git pre-commit hook or a Claude Code PreToolUse hook on `git commit` commands that detect `backlog/` changes.

### `just backlog-index` Recipe

File: `justfile`, lines 640–644 — calls `python3 backlog/generate_index.py` directly. This is the correct mechanism for freshening the index.

## Open Questions

- Should regeneration be added before Step 2 (fixing the current session) or before Step 7.1 (fixing only the next session)? **Resolved: Before Step 2** — regenerate before `select_overnight_batch()` so the current session uses fresh data.
- If regeneration runs before Step 2, it creates uncommitted files early in the flow — how to handle? **Resolved: Auto-commit** — commit `index.json` and `index.md` automatically after regeneration, before the Step 7.1 dirty-tree check.
- Should `load_from_index()` catch `KeyError` in addition to `FileNotFoundError`/`json.JSONDecodeError`? **Resolved: No** — a `KeyError` means the index is structurally broken in a way that warrants attention, not silent fallback.
