# Review: cortex-init-scaffolds-cortex-gitignore-for

## Stage 1: Spec Compliance

### Requirement 1: Corrected, depth-complete seed content (transient artifacts ignored at all depths)
- **Expected**: Shipped `cortex/.gitignore` ignores residue/session/lock/activity at active AND archive depth; `overnight-events-*.log` widened to also catch `overnight-events.log`. `--no-index` probes for `archive/x/critical-review-residue.json`, `feat/critical-review-residue.json`, `archive/x/.session`, `overnight-events.log` all exit 0.
- **Actual**: Template uses `lifecycle/**/<basename>` form for `.session`, `.session-owner`, `.dispatching`, `.lock`, `agent-activity.jsonl`, `learnings/recovery-log.md`, and `critical-review-residue.json`; `overnight-events*.log` (no hyphen) catches both. Independently re-ran the full `--no-index` exit-0 matrix against a fresh temp repo carrying only the shipped template — all 17 transient probes (active + archive depth for every widened rule, plus single-level `metrics.json`, `sessions/`, `backlog/index.{json,md}`, `backlog/*.events.jsonl`, `_adhoc/`) exit 0.
- **Verdict**: PASS
- **Notes**: Re-verified independently, not taken on faith. Every widened rule confirmed at archive depth, including `archive/x/learnings/recovery-log.md` and `archive/x/agent-activity.jsonl`.

### Requirement 2: Must-track project state never ignored (narrow learnings rule)
- **Expected**: Template ignores ONLY transient artifacts; `learnings/` rule stays narrow to `recovery-log.md` even at archive depth. `--no-index` exits 1 for `backlog/x.md`, `lifecycle/feat/spec.md`, `lifecycle/feat/learnings/outline.md`, `lifecycle/archive/x/learnings/outline.md`, `requirements/project.md`, `adr/x.md`.
- **Actual**: The learnings rule is `lifecycle/**/learnings/recovery-log.md` (basename-scoped, never whole `learnings/`). Independently re-ran the exit-1 matrix — all 7 must-track probes exit 1, critically including `cortex/lifecycle/archive/x/learnings/outline.md` (exit 1), proving the narrow `recovery-log.md` rule does not over-match the sibling work-product at archive depth.
- **Verdict**: PASS
- **Notes**: The load-bearing `learnings/outline.md`-at-archive-depth case passes exactly as the spec singles out.

### Requirement 3: Copy-if-absent via the scaffold path (no clobber, no new writer)
- **Expected**: Ship template at `cortex_command/init/templates/cortex/.gitignore`; `scaffold(overwrite=False)` lays it down only when absent via `if dest.exists() and not overwrite: continue`. Tests assert fresh repo gets the file (`exists()`, `st_size > 0`) and a sentinel survives byte-identical across default/`--update`. `just test-init` exits 0.
- **Actual**: Template present at the specified path; `scaffold.py:310` is the unchanged copy-if-absent primitive (no new writer added). `test_cortex_gitignore_fresh_write` asserts `exists()` + `st_size > 0` + equality to shipped bytes; `test_cortex_gitignore_sentinel_survives_copy_if_absent` writes a hand-edit and asserts byte-identity after `scaffold(overwrite=False)`. The single init-code change is the one-line `_HASH_INPUT_TEMPLATES` tuple entry. Re-ran `just test-init`: 123 passed.
- **Verdict**: PASS
- **Notes**: No `ensure_cortex_gitignore` writer; the template auto-discovers via `_iter_template_files` (`_TEMPLATE_ROOT = cortex_command.init.templates`).

### Requirement 4: Hash participation with copy-if-absent semantics (staleness visible, never auto-overwritten)
- **Expected**: Template added to `_HASH_INPUT_TEMPLATES` so coverage stays green and a diverged file surfaces in the `--update` drift report, but an existing file is NEVER auto-overwritten on default/`--ensure`. The `--update` drift assertion must be path-specific.
- **Actual**: `"cortex/.gitignore"` added to `_HASH_INPUT_TEMPLATES` (scaffold.py:68). `test_cortex_gitignore_update_drift_report_names_path` plants a marker via terminal `--update`, diverges the on-disk file, re-runs `--update`, and asserts `"cortex/.gitignore" in captured.err` AND that the file is left == `diverged` (read-only drift report, not overwritten) — path-specific, not exit-0-only. `test_cortex_gitignore_ensure_preserves_hand_edit` forces a hash mismatch (monkeypatches `_compute_init_artifacts_hash`) so `--ensure` reaches Case (ii) where the scaffold pass actually runs, then asserts the hand-edit survives byte-identical — proving copy-if-absent protects the file even when the refresh pass executes. Re-ran both targeted tests: pass.
- **Verdict**: PASS
- **Notes**: The drift assertion is correctly pinned to the operator-facing `--update` path (`captured.err`), not the buried auto-`--ensure` stderr.

### Requirement 5: `--force` updates with backup
- **Expected**: `cortex init --force` backs up an existing `cortex/.gitignore` and overwrites with shipped content via the existing `--force` backup path. Test asserts prior file lands under `cortex/.cortex-init-backup/<ts>/cortex/.gitignore` and live file equals shipped content.
- **Actual**: `test_cortex_gitignore_force_backs_up_and_overwrites` writes a sentinel, runs `scaffold(overwrite=True, backup_dir=None)`, asserts live file == shipped bytes AND `sorted(backup_root.glob("*/cortex/.gitignore"))[-1]` == the sentinel. Backup path matches `backup_existing` semantics (scaffold.py:346-347: `repo_root/cortex/.cortex-init-backup/<ts>/<rel>`). Test passes on re-run.
- **Verdict**: PASS

### Requirement 6: Hash-coverage test stays green
- **Expected**: Adding the dotfile to `_HASH_INPUT_TEMPLATES` keeps `tests/test_init_artifacts_hash_inputs.py` passing (it `os.walk`s `templates/cortex/**` and requires every file be registered).
- **Actual**: Independently re-ran `.venv/bin/pytest tests/test_init_artifacts_hash_inputs.py -q`: 7 passed. The dotfile is correctly registered and surfaced by the walk.
- **Verdict**: PASS

### Requirement 7: Root `.gitignore` de-dup
- **Expected**: Remove cortex-scoped transient rules now owned by the nested file; keep `.claude/worktrees/`, the `.cortex-init`/`.cortex-init-backup/` markers, all non-`cortex/` rules. `grep -c 'cortex/lifecycle/\*/\.session' .gitignore` = 0; `grep -c '.cortex-init' .gitignore` >= 1; `git check-ignore --no-index cortex/lifecycle/feat/.session` exits 0.
- **Actual**: Root `.gitignore` diff removed all 11 cortex-scoped transient blocks (`.session*`/`.lock`/`.dispatching`, `agent-activity.jsonl`, `overnight-events-*.log`, `learnings/recovery-log.md`, `backlog/*.events.jsonl`, `backlog/index.*`, `sessions/`, `metrics.json`, `_adhoc/`) while keeping `.claude/worktrees/`, `cortex/.cortex-init`, `cortex/.cortex-init-backup/`, and non-cortex rules. Re-ran the three checks: grep session = 0, grep `.cortex-init` = 2, `check-ignore --no-index cortex/lifecycle/feat/.session` exits 0 (now via the nested file).
- **Verdict**: PASS

### Requirement 8: Reconcile residue wording (clarify, don't falsify) + mirror regen
- **Expected**: Preserve the enumerated-staging guard; stop the bare universal "un-gitignored residue" claim; regenerate the plugin mirror byte-clean. `grep -c 'enumerated' complete.md` >= 1; `grep -c 'un-gitignored residue' complete.md` = 0; `just build-plugin` then `git diff --quiet plugins/cortex-core/skills/lifecycle/references/` exits 0.
- **Actual**: `complete.md:254` reframed to "residue that is un-ignored *or* already-tracked", preserving the `learnings/*`/`outline.md` rationale (correctly not stale) and scoping the `critical-review-residue.json` ignore claim to fresh consumer repos. The enumerated-staging guard sentence is intact. Canonical and `plugins/cortex-core/` mirror carry byte-identical edits. Re-ran: grep enumerated = 2, grep `un-gitignored residue` = 0, `just build-plugin` then `git diff --quiet` on the mirror exits 0 (already in sync). No new MUST language; no bare `cortex-*` prose invocations introduced. (`post-refine-commit.md` correctly left untouched — its staging-set argument does not make the universal claim.)
- **Verdict**: PASS

### Requirement 9: Fix stale code-comment reference
- **Expected**: `cortex_command/overnight/runner.py` `.gitignore:41` line reference generalized. `grep -c 'gitignore:41' runner.py` = 0.
- **Actual**: Comment at runner.py:730 generalized to "gitignored by the `lifecycle/sessions/` rule in the umbrella `cortex/.gitignore`" — no line number, names the actual owning rule/file. Re-ran `grep -c 'gitignore:41' cortex_command/overnight/runner.py` = 0.
- **Verdict**: PASS

## Requirements Drift

**State**: none
**Findings**:
- None. The implementation aligns with project.md Philosophy of Work ("Complexity must earn its place; simpler wins") and Solution-horizon (copy-if-absent rides existing scaffold/hash/`--force`/`drift_files` plumbing with no new mechanism — a scoped use of existing layers, not a stop-gap). The documented departure from ADR-0006's versioned-fence discipline is recorded in the spec's Non-Requirements and Proposed-ADR section (judged reversible, unsurprising, operator-decided), so it is a deliberate scoped choice rather than drift.
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Consistent with project patterns. Template registered POSIX-relative in `_HASH_INPUT_TEMPLATES` matching the existing tuple style; test names follow the `test_cortex_gitignore_<behavior>` convention and the `Spec Req N` docstring-anchoring convention already used in `test_handler_ensure.py`/`test_scaffold.py`. Module-level `_SHIPPED_GITIGNORE` / `_TEMPLATE_BYTES` sourced from the same `importlib.resources` handle the scaffolder uses, never hardcoded — exactly as the spec's Technical Constraints require.
- **Error handling**: Appropriate and unchanged. No new writer or error path introduced; the feature relies entirely on the existing `scaffold()` copy-if-absent skip, `backup_existing`, and `drift_files` paths. The widened globs pattern-match already-tracked archive residue and the tracked `overnight-events.log` seed fixture in this repo, which is safe (git never retroactively untracks) and explicitly reasoned about in the spec Technical Constraints and plan Risks.
- **Test coverage**: Strong and regression-pinning. The plan's verification steps were genuinely executed (re-ran `just test-init` = 123 passed, hash-coverage = 7 passed, the full `--no-index` exit-0/exit-1 matrix). `test_cortex_gitignore_template.py` probes archive depth for EVERY widened rule (not just the two the spec enumerates), so a regression that silently leaves any rule single-level is caught — including the `archive/x/learnings/outline.md` exit-1 must-track proof. The `test_partial_scaffold_update_recovery` repair is correct: the injection filter changed from a prefix match (`startswith`) to exact `rel in SCAFFOLD_FILES`, which deliberately excludes the new first-sorted dotfile so the test still exercises a genuine "3 of 4 land, 1 missing" partial failure (re-verified: `len(present) == 3` / `len(missing) == 1` hold, `SCAFFOLD_FILES` is the unchanged 4-tuple). The `--update` drift assertion is path-specific (`"cortex/.gitignore" in captured.err`), and the `--ensure` preserve test forces Case (ii) so the scaffold pass actually runs.
- **Pattern consistency**: Rides the existing scaffold/hash/`--force`/`drift_files` plumbing with no new writer, exactly per spec Non-Requirements. Independently confirmed the Non-Requirements were honored: no `_CORTEX_GITIGNORE_VERSION`/version sigil (the only matches are negated plan.md prose), no dedicated writer, no `_iter_template_files` exclusion for the gitignore, no `git rm --cached` untracking, and the init package is not mirrored into any plugin (only the `complete.md` references edit is plugin-mirrored). Repo `cortex/.gitignore` is byte-identical to the shipped template (`diff` exit 0).

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
