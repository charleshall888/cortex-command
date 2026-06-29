# Review: offload-refine-step-2-state-checking

## Stage 1: Spec Compliance

### Requirement 1: New `cortex-refine resume-point --lifecycle-slug {slug}` subcommand (single-line compact JSON, classification logic, read-only)
- **Expected**: `_cmd_*`/`add_parser`/`set_defaults` handler printing `json.dumps(..., separators=(",",":"))` → `{"resume":...,"spec_exists":...,"research_exists":...}`; determination `spec∧research→complete`, `spec→research`, `research→spec`, `else→clarify`; no writes/backend/events; a new test drives all four states + missing-dir.
- **Actual**: `refine.py:319-361` `_cmd_resume_point` follows the idiom; parser block `refine.py:467-481` with `--lifecycle-slug required=True`/`set_defaults(func=...)`. Output uses compact separators (verified live: `{"resume":"clarify","spec_exists":false,"research_exists":false}`, key order resume/spec_exists/research_exists). Determination branch matches spec exactly. Read-only — only `is_file()` stats, no `mkdir`/write/events read/`resolve_backlog_backend`. `tests/test_refine_resume_point.py` drives all four states + missing dir + edge cases.
- **Verdict**: PASS
- **Notes**: Compact-separator byte output confirmed by direct CLI run.

### Requirement 2: existence semantics are `is_file()` (directory does NOT count; empty file DOES)
- **Expected**: `is_file()` not `exists()`; a directory named `spec.md`/`research.md` excluded; an empty-but-present `spec.md` counts.
- **Actual**: `refine.py:339-340` uses `(base/"spec.md").is_file()` / `(base/"research.md").is_file()`. `test_empty_spec_file_counts_as_present` asserts `spec_exists is True`; `test_directory_named_research_md_does_not_count` creates a dir and asserts `research_exists is False`.
- **Verdict**: PASS

### Requirement 3: exit-code contract (0 for all four states; 2 for usage error; never 64/70)
- **Expected**: every state exits 0; missing `--lifecycle-slug` → argparse exit 2; no 64/70 path.
- **Actual**: `_cmd_resume_point` ends in `return 0` with no IO-write path. Verified live: missing-dir slug → exit 0. `test_missing_lifecycle_slug_flag_exits_two` asserts `SystemExit.code == 2`; the four state tests each assert `rc == 0`.
- **Verdict**: PASS

### Requirement 4: Step 2 resume-tree replaced by one `resume-point` call + retained judgment guards
- **Expected**: skill calls the verb, branches on `resume`, keeps complete/research/spec guards (incl. the re-run status-reset to `in_progress`); old pseudo-code gone.
- **Actual**: `SKILL.md:41-50` invokes `cortex-refine resume-point` and branches on all four enum keys (`complete|research|spec|clarify`). Guards retained: `complete` (announce, skip to Step 6, no menu, explicit-re-run-only, overwrite + reset `status` to `in_progress`); `research` (warn overnight needs both, skip Clarify); `spec` (Research Sufficiency Check §6); `clarify` (none). Acceptance greps: `cortex-refine resume-point`=1, `research.md does NOT exist`=0, `spec.md exists AND`=0, `in_progress`=1.
- **Verdict**: PASS

### Requirement 5: `--backend {value}` structural guard + diagnostic (no backend resolution, `.strip()`, path-accurate message)
- **Expected**: optional flag default `cortex-backlog`; `.strip()` before compare; when stripped `!= cortex-backlog` AND a slug was passed → coerce `backlog_slug=None` + stderr diagnostic naming slug+backend; verbs MUST NOT call `resolve_backlog_backend`/read config; emit default-seed and reconcile flags drive.
- **Actual**: `_apply_backend_guard` (`refine.py:88-111`) fires only on `backend != "cortex-backlog" and backlog_slug is not None`, returns `None`, prints `cortex-refine: ignoring --backlog-slug {slug!r} on non-local backend {backend!r}`. Callers strip at `refine.py:178` and `:251`. No `resolve_backlog_backend`/config read anywhere in the module (grep finds only a docstring stating it does NOT read config). Diagnostic correctly omits any "seeding from defaults" clause (per plan Task 4 refinement of the spec example), so it stays true on emit-seed, idempotent short-circuit, and reconcile paths. Tests: emit + reconcile stale-file guard, trailing-whitespace-treated-as-local.
- **Verdict**: PASS
- **Notes**: The guard is a pure arg-actor — ADR-0019/ADR-0016 compliant (acts only on the caller-passed flag, never resolves backend).

### Requirement 6: Step 2 seed + Step 5 reconcile collapse to one `--backend {resolved}` call each; two-arm prose removed
- **Expected**: one unconditional `--backend {resolved}` call per site; `cortex-read-backlog-backend` resolution retained; slug-omission two-arm prose gone.
- **Actual**: `SKILL.md:54-60` (seed) and `:143-146` (reconcile) each lead with `--backend {resolved}`. Acceptance greps: `emit-lifecycle-start --backend`=1, `reconcile-clarify --backend`=2, `cortex-read-backlog-backend`=1; negative controls `non-local arm omits`=0 and `omit .*--backlog-slug.* non-local`=0. The Step 2 narration now says the verb's guard owns the non-local slug-drop; the item-existence (Context A/B) distinction is retained as designed.
- **Verdict**: PASS

### Requirement 7: Local arm byte-identical, verified against a HARDCODED literal for BOTH verbs, ts masked via raw-string
- **Expected**: both invocation paths (`--backend` absent + `cortex-backlog`) of EACH verb match a human-written literal pinning key order + separators; `ts` masked by raw-string substitution, NOT a `json.loads→json.dumps` round-trip (which would re-normalize and re-introduce the tautology).
- **Actual**: `test_emit_row_byte_identical_to_hardcoded_contract` and `test_reconcile_override_row_byte_identical_to_hardcoded_contract` each assert against a hand-written `expected` literal (lifecycle_start row and complexity_override row respectively), looping over `[[], ["--backend","cortex-backlog"]]`. `_mask_ts` (`tests/test_refine_module.py:678-685`) uses `re.sub(r'"ts": "[^"]*"', '"ts": "<TS>"', line.strip())` — a raw-string regex on the production bytes, not a round-trip. The literals carry the default `", "`/`": "` separators that production `json.dumps(row)` emits, so a compact-separator or key-order regression would fail the assert. Genuinely non-self-sealing and ts-robust.
- **Verdict**: PASS

### Requirement 8: `test_refine_non_local_reconcile_branch_is_value_aware` rewritten to one-call shape WITHOUT dropping value-aware negative controls
- **Expected**: assert the `--backend {resolved}` one-call shape AND preserve positive Context A/B shape-pins AND the `#285/#317` no-seed-default-literal negative control AND `cortex-read-backlog-backend` reference.
- **Actual**: `tests/test_refine_reconcile_clarify.py:252-281`. Asserts both verbs lead with `--backend {resolved}`; positive contiguous pins for Context A (`--backlog-slug {backlog-filename-slug}`) and Context B (`--complexity {value} --criticality {value}`) — so a collapse dropping either flag set fails; negative control via `re.search` rejecting `--complexity simple`/`--criticality medium`; `cortex-read-backlog-backend` referenced. Item-existence invariant is positively guarded, not negative-only.
- **Verdict**: PASS
- **Notes**: Wiring/anchor tests (`test_refine_lifecycle_start_wiring`, `test_refine_reconcile_wiring` incl. specify.md ordering anchor, `test_refine_skill` Complexity/value-gate anchor) and `test_critical_review_gate_nonlocal_failsafe` all still green (32 passed).

### Requirement 9: Canonical sources only; mirror regenerated; no bin wrapper/parity row for the wheel-only console-script
- **Expected**: canonical + mirror in sync; drift hook + `cortex-check-parity` pass; no `bin/` wrapper needed.
- **Actual**: `diff skills/refine/SKILL.md plugins/cortex-core/skills/refine/SKILL.md` → identical (MIRROR_IN_SYNC). `bin/cortex-check-parity` exits 0. ADR `0019` is the next free number (no duplicate `NNNN` prefixes), `status: proposed`, single matching filename. `cortex-refine` is a wheel console-script, so no `bin/` mirror/parity-allowlist row is introduced.
- **Verdict**: PASS

### Edge Cases
- Missing lifecycle dir → `clarify`, exit 0 (`test_missing_lifecycle_dir_resolves_clarify_exit_zero`, verified live). PASS
- Empty `spec.md` counts; directory `research.md` does not (`is_file()`). PASS
- `--backend` absent → `cortex-backlog` (default); trailing-whitespace stripped to local arm. PASS
- Non-local + stale local file → slug coerced to None + diagnostic. PASS
- Non-local resume-to-spec / §3b fail-safe untouched (`test_critical_review_gate_nonlocal_failsafe` green). PASS

### Changes to Existing Behavior
All six listed ADDED/MODIFIED items present and match (new `resume-point` verb, optional `--backend` on both verbs with non-local diagnostic, Step 2 resume-tree + seed/reconcile rewrites, rewritten value-aware test). PASS

## Requirements Drift
**State**: detected
**Findings**:
- `cortex/requirements/backlog.md` (Architectural Constraints, line 100; Consumer routing, line 50) states the rule unqualified — "the `cortex-*` CLI tools remain cortex-backlog-only (they *are* the local engine)." #322 ships a `cortex-*` CLI (`cortex-refine`) that now carries a `--backend` flag and branches on it. The deliberate, bounded exception is recorded in ADR-0019 but is not reflected in the area doc, which already demonstrates the ADR-back-pointer convention (line 106 → ADR-0016). The rule is scoped *in spirit* to the backlog-*engine* CLIs (its own enumerated console-script list at line 111 excludes `cortex-refine`), so "none" is also defensible and the spec author deliberately scoped it that way (spec Technical Constraints, "ADR-0016 boundary"). Flagging as low-severity drift because the normative text now carries an un-pointed exception. Observation only — does not affect the verdict.

**Update needed**: `cortex/requirements/backlog.md`

## Suggested Requirements Update
**File**: `cortex/requirements/backlog.md`
**Section**: Architectural Constraints
**Content**:
```markdown
- The backend-blind rule applies to the backlog-*engine* `cortex-*` CLIs (the local engine; see line 111). A skill-helper verb (`cortex-refine`) may carry a caller-passed `--backend` flag purely as a structural guard — without resolving the backend itself — per [ADR-0019](../adr/0019-skill-helper-verb-backend-structural-guard.md).
```

## Stage 2: Code Quality
- **Naming conventions**: Consistent with the existing `refine.py` idiom — `_cmd_resume_point`/`_apply_backend_guard` follow the module's `_cmd_*`/`_*` helper naming; parser uses the same `add_parser`/`set_defaults(func=...)` pattern as `emit-lifecycle-start`/`reconcile-clarify`; `--lifecycle-slug required=True` mirrors the sibling subparsers. Docstrings match the module's expository style.
- **Error handling**: Appropriate. `resume-point` has no write path and cannot fail (always exit 0; argparse owns the exit-2 usage error). `_apply_backend_guard` is a pure read-only arg-actor (coerce + stderr diagnostic, no raise). The pre-existing emit/reconcile 64/70 paths are untouched. The guard fires only on the genuine footgun condition (`backend != cortex-backlog AND slug is not None`), staying silent on the common no-slug Context-B call.
- **Test coverage**: Strong and non-self-sealing. The byte-identity tests assert against hand-written literals (not captured from the serializer) with a raw-string `ts` mask — a key-order or separator regression in production `json.dumps` would fail them; both verbs and both invocation paths are covered. The rewritten reconcile test positively pins Context A (`--backlog-slug`) and Context B (`--complexity {value} --criticality {value}`) shapes so an accidental flag drop fails, and keeps the `#285/#317` no-seed-default-literal negative control. Guard, whitespace, four-state, and edge-case (empty file, directory, missing dir, missing flag) cases all present. Full suite: 2118 passed, 26 skipped, 1 xfailed, 0 failed.
- **Pattern consistency**: The new subcommand follows the `_cmd_*`/`add_parser`/`set_defaults` idiom faithfully. The guard correctly does NOT resolve the backend — no `resolve_backlog_backend`/config read in the module (only a docstring stating the negative) — so it stays within ADR-0019's carve-out and respects ADR-0016 (the skill resolves via `cortex-read-backlog-backend` and passes the value in). Mirror in sync; parity clean; ADR-0019 lands at the next free number with `status: proposed` and argues criterion-1 (hard-to-reverse precedent, not code).

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "detected"}
```
