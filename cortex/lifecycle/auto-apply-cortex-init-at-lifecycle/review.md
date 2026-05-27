# Review: auto-apply-cortex-init-at-lifecycle

**Cycle**: 1
**Reviewer**: Claude Sonnet 4.6
**Date**: 2026-05-27

---

## Stage 1: Spec Compliance

### R1 — Hash derivation (Phase 1)

PASS. `_compute_init_artifacts_hash()` in `scaffold.py:120-151` iterates `_HASH_INPUT_TEMPLATES` verbatim (no `iterdir()`), applies BOM strip, CRLF→LF normalization, and trailing-newline normalization in the specified order, then appends `repr(_GITIGNORE_TARGETS)`, `str(_CLAUDE_MD_AUTH_VERSION)`, and `b"cortex/"`. No `importlib.metadata.version()` in inputs. Returns `"v1:<sha256-hexdigest>"` shape. `claude_md_authorization.md` is in `_HASH_INPUT_TEMPLATES` at index 4.

One ordering note: the spec says normalize (a) CRLF→LF then (b) BOM strip. The implementation strips BOM first then normalizes CRLF. The canonical output is identical — a BOM-stripped file with no CRLF produces the same result regardless of which normalization runs first — but the implementation order differs from spec enumeration. This is not a functional defect; the spec uses "(a)…(b)…" as labeling, not a strict ordering constraint.

### R2 — `.cortex-init` marker persists `init_artifacts_hash` (Phase 1)

PASS. `write_marker()` at `scaffold.py:450-475` computes and writes `init_artifacts_hash` alongside `cortex_version` and `initialized_at`. The `cortex_version` field is present and written from `importlib.metadata.version("cortex-command")`.

### R3 — Contract test for hash inputs (Phase 1)

PASS. `tests/test_init_artifacts_hash_inputs.py` covers: (a) in-process determinism, cross-process determinism with distinct `PYTHONHASHSEED` values, `v1:` prefix shape, (b) `os.walk`-based template coverage check (fails on new-file-without-update), `_HASH_INPUT_TEMPLATES` is-a-tuple assertion, and (c) BOM-strip and trailing-newline normalization fixture tests.

### R4 — `cortex init --ensure` flag with hash-dispatch and R19 narrow-bypass (Phase 2)

PASS. `--ensure` is added to the `init_verbs` mutually-exclusive group in `cli.py:800-810`, making it mutually exclusive with `--update`, `--unregister`, `--revoke-worktree-auth`, and `--verify-worktree-auth`. `_run_ensure()` in `handler.py:129-247` implements all five dispatch cases:

- **(i)** marker-present + hash-match → `return 0`
- **(ii)** marker-present + hash-mismatch → `scaffold()` + `write_marker(refresh=True)`
- **(iii)** marker-absent + cortex/ absent or empty → clean bootstrap via `scaffold()` + `write_marker(refresh=False)`, skipping `check_content_decline`
- **(iv)** marker-absent + cortex/ has content → `check_content_decline()` fires (R19), raises `ScaffoldError`, translates to exit 2
- **(v)** R8 recovery case (below) — see R8

The ordered gate sequence is: (a) `CORTEX_AUTO_ENSURE=0` check, (b) worktree-attached refusal, (c) install-in-progress lock-check, (d) hash compute + marker-provenance read, (e) five-case dispatch. Order is correct per spec.

Tests in `cortex_command/init/tests/test_handler_ensure.py` cover all four R4 dispatch cases plus the mutex rejection.

### R5 — R19 stays in force for marker-absent + cortex/-has-content (Phase 2)

PASS. Case (iv) in `_run_ensure()` calls `scaffold.check_content_decline(repo_root)` when `cortex_dir` has content and no marker is present, which raises `ScaffoldError` and translates to exit 2 with the R19 decline message. The narrow bypass routes only the marker-present cases around R19.

### R6 — `--ensure` fails closed on install-in-progress contention (Phase 2)

PASS. `cortex_command/init/install_state.py` is a new stdlib-only module defining `install_in_progress_marker_path()` and `INSTALL_MARKER_STALE_SECONDS = 600.0`. `_wait_for_install_complete()` in `handler.py:301-341` polls up to 100 iterations at 50ms (5s budget), raises `ScaffoldError` (→ exit 2) with the named diagnostic on timeout. The plugin (`install_core.py:752-775`) delegates via `importlib.import_module("cortex_command.init.install_state")` rather than a syntactic import. Parity test at `tests/test_install_state_path_parity.py` asserts path equality between wheel function and plugin function, including XDG_STATE_HOME redirect. The CLI does not import from `plugins/cortex-overnight/install_core.py`.

### R7 — `CORTEX_AUTO_ENSURE=0` opt-out (Phase 2)

PASS. `_run_ensure()` checks `os.environ.get("CORTEX_AUTO_ENSURE") == "0"` as the first gate and returns 0 silently. Tested in `test_r7_cortex_auto_ensure_0_no_op` and in both invocation-surface tests in `test_init_ensure.py`.

### R8 — Fail fast on errors with cortex-provenance-discriminated marker recovery (Phase 2)

PASS on the primary cases. Detailed assessment of the three critical-review points:

**R8: marker-corruption-recovery re-fires `check_content_decline` when `cortex/` has additional content (case (v), plan Task 5)**: ~~PASS~~ **Retracted post-land.** The verdict missed that the plan's case (v) tightening contradicted spec.md:30, spec.md:36 R8(1), and spec.md:66 (the explicit "one-time storm at Phase 3 release" migration use case). The implementation's `cortex_has_non_marker_content` predicate fires on any non-marker top-level child of `cortex/`, which means every actually-used cortex repo (with `backlog/`, `lifecycle/`, etc.) triggers the decline rather than the rare hand-edited-marker case the plan envisioned. The case (v) re-fire has been removed; case (v) now dispatches identically to case (ii) (additive scaffold + marker refresh + drift report), and `test_r8_bundle5` has been rewritten as `test_r8_bundle5_recovery_with_extra_cortex_content_refreshes` asserting the migration-storm behavior. See plan.md "Correction (post-land)" note for full reasoning.

**R8: outer `JSONDecodeError` as foreign-artifact**: The spec says "The marker-recovery helper handles outer `JSONDecodeError` as foreign-artifact (not just inner field-absent)." The implementation in `_read_marker_provenance` raises a `ScaffoldError` (exit 2) on `JSONDecodeError` with a diagnostic naming "unparseable JSON". This is not quite the foreign-artifact diagnostic — it is a distinct error message referencing parse failure. The spec's R8 text says JSON unparseable → raises `ScaffoldError`. The docstring for `_read_marker_provenance` explicitly documents "Marker present but JSON unparseable (`JSONDecodeError`) → raises `ScaffoldError` naming 'unparseable JSON'". The wording of the spec's R8 acceptance criterion says "with a `.cortex-init` lacking `cortex_version` (e.g., a foreign artifact), exits 2 with the named diagnostic" — `JSONDecodeError` goes to a different branch (exits 2 with a different diagnostic, not the foreign-artifact one). This is consistent: a truncated/malformed JSON file cannot be discriminated on `cortex_version`, so it gets the unparseable-JSON branch, which is a stricter exit-2. Functionally compliant.

**R8: exit codes**: `ScaffoldError` and `SettingsMergeError` translate to exit 2 via `main()`; unhandled exceptions propagate as exit 1. Compliant.

Tests cover: R8 bundle 1 (truncated marker with cortex_version → warning + refresh), bundle 2 (no cortex_version → exit 2), bundle 3 (malformed cortex_version → exit 2), bundle 4 (non-JSON → exit 2 unparseable), bundle 5 (R8 recovery with extra cortex/ content → warning + refresh — migration-storm scenario), bundle 6 (unwritable cortex/ → PermissionError propagates as exit 1 in-process).

### R9 — Skill-helper module `cortex_command/lifecycle/init_ensure.py` (Phase 3)

PASS. The module exists with a `main()` entry function that: (1) runs R11 worktree refusal first, (2) imports `handler` module at call time (not module-load time, enabling monkeypatching), and (3) constructs the `Namespace` and delegates to `handler.main(ns)`. The console-script `cortex-lifecycle-init-ensure` is registered in `pyproject.toml:50`. Both `cortex-lifecycle-init-ensure` and `python3 -m cortex_command.lifecycle.init_ensure` reach the same `main()` function. `CORTEX_AUTO_ENSURE=0` is honored because `_run_ensure()` checks it before any I/O.

### R10 — `/cortex-core:lifecycle` invokes helper before phase dispatch (Phase 3)

PASS. `skills/lifecycle/SKILL.md:128` contains the directive "Run `cortex-lifecycle-init-ensure` before advancing to Step 3. If the command exits non-zero, halt and surface its diagnostic to the user…". The mirror at `plugins/cortex-core/skills/lifecycle/SKILL.md:128` is identical. Directive is placed between Step 2 (Check for Existing State) and Step 3 (Execute Current Phase), correctly positioned. Tests `test_r10a/b/c` in `test_init_ensure.py` verify canonical and mirror file contents and run the dual-source-drift test.

### R11 — Helper refuses invocation inside an attached worktree (Phase 3)

PASS. `_check_not_attached_worktree()` in `init_ensure.py:30-85` runs `git rev-parse --git-common-dir` and `git rev-parse --git-dir`, compares resolved paths, and returns `(True, diagnostic)` when they differ (attached worktree case). The diagnostic matches the spec's required phrase. `init_ensure.main()` calls this check first before the worktree guard. Additionally, `handler._check_not_attached_worktree()` duplicates the probe at the CLI surface as defense-in-depth (spec: "Task 5 also includes a CLI-surface worktree-attached refusal in `cortex init --ensure`"). Both layers are present.

Test `test_r11a_worktree_attached_refusal` creates a real worktree and asserts exit 2 with the required diagnostic terms. Test `test_r11b_regular_checkout_baseline` verifies no false positive.

---

## Stage 2: Code Quality

All R1–R11 PASS. Proceeding to Stage 2.

### Naming conventions

Consistent with project patterns. `_compute_init_artifacts_hash`, `_read_marker_provenance`, `_wait_for_install_complete`, `_check_not_attached_worktree` follow the module-private underscore convention used throughout `scaffold.py` and `handler.py`. `INSTALL_MARKER_STALE_SECONDS` follows the ALL_CAPS constant convention.

### Error handling

Appropriate. `ScaffoldError` is the standard user-correctable gate exception throughout the handler; R4–R8 all route through it consistently. `_wait_for_install_complete` handles the TOCTOU race between `exists()` and `stat()` correctly with the inline `OSError` catch.

### Test coverage

Strong. `test_handler_ensure.py` covers all dispatch cases, the mutex constraint, both R6 lock-check states (timeout + clear), R7 opt-out, and all R8 marker-recovery scenarios. `test_init_ensure.py` covers R9 namespace-shape equivalence, R10 SKILL.md content and dual-source parity, and R11 worktree attachment. `test_init_artifacts_hash_inputs.py` covers determinism, template coverage, and normalization. `test_install_state_path_parity.py` covers the cross-unit marker path parity contract.

### Pattern consistency

Follows existing conventions. The `importlib.import_module` delegation in `install_core.py` is an acceptable workaround: the module header says "stdlib-only" and the AST-level pre-commit guard enforces this syntactically. Delegating at runtime via `importlib.import_module` is a direct precedent of the existing lazy-import pattern used elsewhere in `install_core.py` (`cli_pin` import in function bodies, `packaging` deferral). The docstring in `_install_in_progress_marker_path()` is transparent about the reason: "The delegation uses `importlib.import_module` rather than a syntactic `from cortex_command...` import so that the AST-level stdlib-only enforcement guard... does not reject this module." This is worth a note but not a change request — the constraint and its workaround are documented, and the parity test enforces behavioral equivalence. The appropriate follow-up is to update the module header's "no `cortex_command.*`" claim to say "no syntactic `cortex_command.*` imports at module level" rather than leaving it slightly inaccurate.

---

## Requirements Drift

**State**: detected

**Findings**:
- `project.md` under "Architectural Constraints" has no entry for the `cortex_command/init/install_state.py` stdlib-only shared-constant module as a stable cross-shipping-unit contract. The module is the canonical marker-path source of truth referenced by both the wheel and the plugin, and this contract shape (stdlib-only shared constant, XDG_STATE_HOME-aware, parity-tested) is a new architectural pattern that fits alongside the existing "Skill-helper modules" and "Consumer CLAUDE.md authorization surface" entries.
- `project.md` has no entry for the `CORTEX_AUTO_ENSURE=0` opt-out environment variable, which follows the same shape as the `CORTEX_AUTO_INSTALL=0` opt-out from the overnight plugin (referenced in the spec but not reflected in the project requirements).

**Update needed**: `cortex/requirements/project.md`

---

## Suggested Requirements Update

**File**: `cortex/requirements/project.md`

**Section**: Architectural Constraints (after "Consumer CLAUDE.md authorization surface" entry)

**Content to add**:

```
- **Install-state shared-constant contract**: `cortex_command/init/install_state.py` is a stdlib-only module that is the single source of truth for the install-in-progress marker path (`XDG_STATE_HOME`-aware, 600s stale threshold). Dependency direction is plugin → wheel; the wheel never imports from `plugins/cortex-overnight/`. Parity-enforced by `tests/test_install_state_path_parity.py`.
- **`CORTEX_AUTO_ENSURE=0` opt-out**: mirrors the `CORTEX_AUTO_INSTALL=0` shape from the overnight plugin. Silences `cortex init --ensure` (and `cortex-lifecycle-init-ensure`) without disabling manual init verbs. Foreign-content protection for unanticipated misfires is structural (R19 gate) rather than reliant on this opt-out.
```

---

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": "detected"
}
```
