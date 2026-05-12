# Specification: Add index regeneration to overnight pre-flight and investigate staleness gaps

## Problem Statement

The backlog index (`index.json`) can silently go stale when backlog `.md` files are edited directly, bypassing `update_item.py`'s automatic regeneration. `select_overnight_batch()` prefers `load_from_index()` and only falls back to `parse_backlog_dir()` on structural errors (`FileNotFoundError`, `json.JSONDecodeError`) — semantic staleness (changed status, renamed lifecycle slugs, added/removed items) passes through silently. This caused a real bug during overnight planning where a renamed lifecycle directory wasn't picked up. The fix is to regenerate the index at the point of consumption — before batch selection — ensuring the overnight runner always works with fresh data, and to eliminate the redundant `generate-index.sh` script that produces only `index.md` (not `index.json`).

## Requirements

1. **Pre-selection index regeneration**: The overnight skill runs `generate_index.py` before batch selection, ensuring `select_overnight_batch()` always reads a fresh `index.json`.
   - Acceptance criteria: `grep -c 'generate_index\|generate-backlog-index' skills/overnight/SKILL.md` ≥ 1; the instruction appears before the `select_overnight_batch()` call in the skill's step ordering.

2. **Silent auto-commit of regenerated index**: After regeneration, the overnight skill commits `backlog/index.json` and `backlog/index.md` with a standard message, silently. If the commit fails, the session must halt — uncommitted index files would cause a dirty-tree failure at the later uncommitted-files check with no useful context.
   - Acceptance criteria: The overnight skill's instructions include a `git add backlog/index.json backlog/index.md` and `git commit` step after regeneration and before the uncommitted-files check, with an explicit gate on commit success.

3. **Deprecate `generate-index.sh`**: Remove `skills/backlog/generate-index.sh`. Update any documentation references that point to it.
   - Acceptance criteria: `test ! -f skills/backlog/generate-index.sh`, pass if the file does not exist. `grep -r 'generate-index\.sh' docs/ skills/` returns no matches.

4. **Regeneration failure blocks session**: If `generate_index.py` fails (non-zero exit), the overnight skill must halt — not proceed with a stale index.
   - Acceptance criteria: The overnight skill's regeneration instruction explicitly gates on success before continuing to batch selection.

5. **Update internal cross-references after step insertion**: Inserting a new step before the current Step 2 will shift all subsequent step numbers. All internal cross-references within the overnight SKILL.md (e.g., "proceed to Step 6", "repeat Step 4", "Step 7.1") must be updated to reflect the new numbering. Sub-step references (e.g., "step 2" within the Launch section referring to a sub-step) must be disambiguated from the new top-level step.
   - Acceptance criteria: `grep -nE 'Step [0-9]|step [0-9]' skills/overnight/SKILL.md` — manual review confirms all step references are internally consistent with the new numbering.

## Non-Requirements

- **No pre-commit hook for backlog changes**: This spec fixes the overnight consumer — the critical path where the staleness bug was discovered. A pre-commit hook would address the broader root cause (direct edits bypassing `update_item.py`) for all consumers, but adds complexity (Claude Code PreToolUse hook infrastructure, filtering for `backlog/` paths) that is not justified by a known bug in other consumers. If other consumers surface staleness issues, a pre-commit hook becomes the natural next step.
- **No freshness validation in `select_overnight_batch()`**: The overnight path regenerates before consuming, so validation would be redundant there. Other consumers remain unprotected — this is an accepted gap, not a solved problem.
- **No `KeyError` catch in `select_overnight_batch()`**: A `KeyError` from `load_from_index()` indicates the index is structurally incompatible with the current `BacklogItem` schema — this should surface as an error, not silently fall back to `parse_backlog_dir()`.
- **No changes to `load_from_index()` or `select_overnight_batch()` internals**: The overnight staleness problem is operational (stale data at consumption time), and the fix is operational (regenerate before consuming). Structural changes to the Python code are not needed for this scope.
- **No multi-repo index regeneration**: The overnight skill's regeneration step runs from the session's CWD (the target project root). Features with a `repo:` field pointing to a different project will not have that repo's index regenerated. This is an accepted limitation — multi-repo index freshness is a separate concern.

## Edge Cases

- **No backlog items**: `generate_index.py` produces an empty index — `select_overnight_batch()` returns an empty selection. No special handling needed.
- **`generate_index.py` crashes**: The overnight session must halt with a clear error. The skill instruction should gate on exit code.
- **Auto-commit fails** (lock contention, permission error, hook rejection): The session must halt. If regeneration succeeds but the commit fails, uncommitted `backlog/index.json` and `backlog/index.md` would cause a confusing dirty-tree failure at the later uncommitted-files check. Halting immediately with a clear commit-failure message is better than a deferred, context-free dirty-tree error.
- **Index unchanged after regeneration**: `git add` + `git commit` with no diff produces no commit. The skill should handle this gracefully (commit only if there are staged changes).
- **`generate-index.sh` referenced in external docs or scripts**: Research found references in `docs/backlog.md` and `skills/discovery/references/decompose.md`. These must be updated or removed as part of requirement 3.
- **Internal cross-references cite old step numbers**: The overnight SKILL.md contains 8+ internal references by step number, including sub-step references like "step 2" within Step 7's Launch section. After insertion, the skill will have a new top-level step where Step 2 was — sub-step references must be disambiguated to avoid confusion for the LLM agent executing the skill overnight.

## Technical Constraints

- **Overnight skill is a SKILL.md file** (natural language instructions for Claude Code), not executable code. Changes are to the skill's prose instructions, not Python.
- **`generate_index.py` location**: `backlog/generate_index.py` (project-local) or `~/.local/bin/generate-backlog-index` (globally deployed). The overnight skill should use the global CLI name (`generate-backlog-index`), invoked from the target project root (the overnight skill's preconditions already require CWD to be the project root with `.git/` and `backlog/` present).
- **Auto-commit placement**: Must occur after regeneration and before the uncommitted-files check (`git status --porcelain -- lifecycle/ backlog/`). Both regeneration and commit must gate on success.
- **Step insertion shifts all subsequent numbers**: Inserting a new step before the current Step 2 will shift all subsequent step numbers. This is a certainty, not a possibility — the implementation must update all internal cross-references within the SKILL.md.

## Open Decisions

(None — all decisions resolved during research and interview.)
