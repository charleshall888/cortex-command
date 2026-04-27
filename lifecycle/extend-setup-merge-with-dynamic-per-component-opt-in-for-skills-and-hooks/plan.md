# Plan: Foundation cleanup for /setup-merge hook discovery and REQUIRED/OPTIONAL reconciliation

## Overview

Single-task foundation cleanup for `/setup-merge` implementing R1/R2/R3 from the spec as one atomic edit to two files: `.claude/skills/setup-merge/scripts/merge_settings.py` and `.claude/skills/setup-merge/SKILL.md`. The spec mandates "must land in same commit" to avoid mid-flight states where the Python module and the skill markdown disagree on the detect JSON schema. The lifecycle implement phase enforces one-commit-per-task via `skills/lifecycle/references/implement.md` L48/L96/L151 and `claude/overnight/batch_runner.py` L919-948 — so "same commit" and "one task" must be the same thing. A prior draft of this plan split the work into 5 tasks with a trailing "single commit" ceremony; critical review showed that structure is incompatible with the worktree-per-task dispatch model (each sub-task would commit independently, leaving Task 5 nothing to sweep up). Collapse to one task restores compatibility without sacrificing the atomicity invariant.

## Tasks

### Task 1: R1 + R2 + R3 foundation cleanup — single commit

- **Files**: `.claude/skills/setup-merge/scripts/merge_settings.py`, `.claude/skills/setup-merge/SKILL.md`
- **What**: Implement all three spec requirements as one atomic change, producing one commit.

  **R1 — Extend `discover_symlinks()` to walk `claude/hooks/cortex-*`** (`merge_settings.py` L94-185). Add a second hooks-directory walk immediately after the existing `hooks/cortex-*` block (L141-158), mirroring its pattern: `for item in sorted(hooks_dir.glob("cortex-*"))`, target = `home / ".claude" / "hooks" / item.name`, `ln_flag: "-sf"`, `classify(source, target)`. Do NOT duplicate the hardcoded `cortex-notify.sh → ~/.claude/notify.sh` special case — no `cortex-notify.sh` lives in `claude/hooks/`. Add a one-line comment above the pair of walks noting that hooks live in two directories by design. The `cortex-*` glob matches all 8 files in `claude/hooks/` including the Python file `cortex-sync-permissions.py` and excludes `bell.ps1`, `output-filters.conf`, `setup-github-pat.sh` naturally.

  **R2 — Reshape `REQUIRED_HOOK_SCRIPTS` and purge `OPTIONAL_HOOK_SCRIPTS`** (`merge_settings.py` L14-32 for constants, then 9 downstream edits). Expand `REQUIRED_HOOK_SCRIPTS` from 9 to 13 entries (exact set below). Delete `OPTIONAL_HOOK_SCRIPTS` and its comment. Replace the existing "Required hooks: ..." comment with: "Every hook referenced in `claude/settings.json`'s hooks block must appear in this set. If you add or remove a hook in settings.json, update this set in the same commit. Mismatch produces latent bugs — hooks invisible to merge logic, or prompts asking about hooks that cannot actually be disabled." Then purge all downstream references in the same file:
  1. Update `detect_hooks()` docstring at L280 — drop `and hooks_optional`
  2. Delete the `optional_present`, `optional_absent`, `optional_present_seen` local initializations in `detect_hooks()`
  3. Delete the `elif filename in OPTIONAL_HOOK_SCRIPTS:` branch (L315-321) — be careful not to weld the deleted else-body onto the surviving `if filename in REQUIRED_HOOK_SCRIPTS:` branch
  4. Delete the `"hooks_optional": {...}` key from `detect_hooks()` return dict (L328-331) — keep `"hooks_required"` intact
  5. Delete the `"hooks_optional": hooks["hooks_optional"]` line from `detect_settings()` return dict (L493)
  6. Remove the `approved_optional_hooks: list[str]` parameter from `run_merge()` signature (L693-697) and its docstring entry (L702)
  7. Delete the entire "Optional hooks — only approved ones" block in `run_merge()` (L744-752) — preserve the following `apply_hooks(settings, hooks_to_add)` call (L755) at its original indentation
  8. Delete the `_extract_script_from_command()` helper (~L879, underscored — do NOT delete the unrelated `extract_script_filename()` helper at L198 which has a live caller at L236)
  9. In `cmd_merge()` (L913-935), delete the `optional_hooks = json.loads(args.optional_hooks) if args.optional_hooks else []` parsing block (L915-920) and drop the `optional_hooks` positional from the `run_merge(...)` call (L932)
  10. Delete the `--optional-hooks` argparse argument in `main()` (L1000-1004)

  **R3 — Purge optional-hook references from `/setup-merge` SKILL.md**. Delete the entire `### 5b. Optional hooks` section (L178-205). Remove the `| Optional hooks | N to review / already installed |` row from the Step 3 Settings summary table (L80). Remove the `APPROVED_OPTIONAL_HOOKS is empty (no optional hooks approved)` bullet from the Step 5d check list (L345). Remove the `--optional-hooks '<APPROVED_OPTIONAL_HOOKS as JSON array string>' \` line from the Step 5e merge invocation (L361). Remove the `APPROVED_OPTIONAL_HOOKS is the JSON array ...` bullet from the Step 5e "Where:" list (L372). Renumber remaining subsections: `### 5c. Per-category settings` → `### 5b.`, `### 5d. Check if anything to merge` → `### 5c.`, `### 5e. Merge Invocation` → `### 5d.`. Verified by grep that no body text cross-references the numbers themselves — only the headers do.

  After all edits land in the worktree, invoke the `/commit` skill to produce the single commit. Commit message: imperative-mood, ≤72 char subject, referencing the foundation-cleanup scope (not the original opt-in feature title). Example subject: `Reconcile /setup-merge hook discovery with claude/hooks and settings.json wiring`.

- **Depends on**: none
- **Complexity**: simple
- **Context**: The 13-name set for R2 (exact, ordered to match spec): `{cortex-sync-permissions.py, cortex-scan-lifecycle.sh, cortex-setup-gpg-sandbox-home.sh, cortex-cleanup-session.sh, cortex-validate-commit.sh, cortex-output-filter.sh, cortex-notify.sh, cortex-notify-remote.sh, cortex-permission-audit-log.sh, cortex-tool-failure-tracker.sh, cortex-skill-edit-advisor.sh, cortex-worktree-create.sh, cortex-worktree-remove.sh}`. Caller enumeration (whole-repo grep verified, not just local file): `OPTIONAL_HOOK_SCRIPTS`, `hooks_optional`, `approved_optional_hooks`, `_extract_script_from_command`, and `--optional-hooks` have zero external consumers anywhere in `justfile`, `bin/`, `tests/`, `docs/`, `hooks/`, `claude/`, `skills/`, or `.claude/` outside the two files this task edits — only historical markdown in `lifecycle/archive/build-setup-merge-local-skill/plan.md` and the current ticket's own artifacts mention the symbols as documentation. The `_extract_script_from_command` helper's only live call site is the L750 block deleted in step 7. The `run_merge()` signature has exactly one caller, `cmd_merge()` at L932, also edited in step 9. The `hooks_optional` detect-JSON key has exactly one consumer, SKILL.md Step 5b, also deleted here. `extract_script_filename()` at L198 (different function, no underscore prefix) survives because it has a live caller at L236.
- **Verification** (run both checks after edits, before invoking `/commit`):

  1. **End-to-end detect smoke test** — execute the post-refactor code path against real input and assert its output shape:
     ```
     DETECT_OUT=$(python3 .claude/skills/setup-merge/scripts/merge_settings.py detect --repo-root "$(git rev-parse --show-toplevel)" --settings ~/.claude/settings.json)
     python3 -c "
     import json
     d = json.loads(open('$DETECT_OUT').read())
     s = d['settings']
     assert 'hooks_required' in s, 'hooks_required key missing'
     assert 'hooks_optional' not in s, f'hooks_optional still present: {s.get(\"hooks_optional\")}'
     srcs = [e['source'] for e in d['symlinks']]
     assert sum(1 for src in srcs if 'claude/hooks/cortex-' in src) >= 7, 'claude/hooks/cortex-* not discovered'
     assert not [src for src in srcs if any(b in src for b in ['bell.ps1', 'output-filters.conf', 'setup-github-pat'])], 'non-hook files leaked'
     print('ok')
     "
     ```
     Pass if exit 0 and stdout = `ok`. Transitively exercises `discover_symlinks` (R1), the reshaped `REQUIRED_HOOK_SCRIPTS` set and the absence of `hooks_optional` key (R2), and the claude/hooks/cortex-* discovery (R1). Catches KeyError/NameError/TypeError from botched downstream edits, missing dict keys, broken control flow, typos in the REQUIRED set, leakage of non-hook files.

  2. **SKILL.md optional-hook references purged**:
     ```
     grep -ciE 'optional hook|hooks_optional|APPROVED_OPTIONAL_HOOKS' .claude/skills/setup-merge/SKILL.md
     ```
     Pass if count = 0. SKILL.md is interpreted by an LLM at skill-invocation time, not by the Python module, so gate 1 cannot catch residual references in it.

- **Status**: [x] completed (commit `5d747fbd`)
