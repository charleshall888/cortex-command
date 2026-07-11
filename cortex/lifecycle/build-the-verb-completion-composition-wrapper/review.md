# Review: build-the-verb-completion-composition-wrapper (cycle 1)

Read-only review against `spec.md` (16 numbered Requirements) and `plan.md`
(Status lines + critical-review design decisions). Verified by reading the four
verb modules end-to-end, the generator + data file, the parity/roundtrip tests,
the registry, and the overnight prompt, plus running the affected test files.

Two KNOWN pre-existing environmental issues were observed and NOT charged to this
feature: (1) `just test` overall exit-1 from the network-sandbox failure in
`tests/test_mcp_subprocess_contract.py`; (2) `cortex-check-events-registry --audit`
reporting exactly 12 STALE_DEPRECATION rows at clean HEAD (all unrelated legacy
events — `confidence_check`, `discovery_reference`, `seatbelt_probe`, etc.; none
are cluster events).

## Stage 1 — Spec Compliance

**R1 — `just test` covers the lifecycle test tree · PASS**
`grep -c` returns 1 each for `cortex_command/lifecycle/tests`,
`cortex_command/backlog/tests`, and `cortex_command/tests/` in `justfile`. The
three trees are invoked via the `run_test` idiom.

**R2 — Environment-fixture guard tests (arm f) · PASS**
`cortex_command/lifecycle/tests/test_prepare_worktree_fixtures.py` stages real
on-disk fixtures: `test_acquire_live_owned_by_self_rejects`,
`_live_owned_by_other_rejects`, `_stale_esrch_recovers`,
`_stale_start_time_mismatch_recovers`, plus overnight `runner.pid` pairs
(`test_prepare_worktree_overnight_active_against_live_runner_pid`, stale/dead
variants). 8 fixture tests pass; only `os.kill`/liveness are seam-patched.

**R3 — Pause markers at all current sites · PASS**
18-marker census (SKILL.md:34 split into `empty-lifecycle-offer` +
`ambiguous-backlog-pick`); the retired 13-site count is not persisted as an
assertion. `test_marker_set_equals_data_set` enforces the durable invariant.

**R4 — Pause data file + generator · PASS**
`kept-pauses-data.toml` (18 `[[pause]]` rows, kind + optional `suppressed_by` +
rationale) and `generate_kept_pauses.py` (pure `generate_md()` + `main()`,
console script `cortex-generate-kept-pauses`) with a "generated — do not
hand-edit" header. Generator is idempotent (identical md5 over two runs); the
in-test freshness check (`test_committed_inventory_is_fresh`) confirms
regenerate-over-clean-tree produces no diff.

**R5 — Parity → exact marker-set equality + semantic sub-checks · PASS**
`tests/test_lifecycle_kept_pauses_parity.py`: (a) set-equality (orphan+missing
both fail), (b) freshness regenerate-and-diff, (c) per-kind semantic anchors —
`phase-exit-wait`→heading proximity, config-`suppressed_by`→wiring token,
`question`/`relayed-consent`→`_CONSENT_TOKENS` AskUserQuestion/approval-surface
proximity (`PROXIMITY_WINDOW=8`). `LINE_TOLERANCE` retired. Five negative
controls present (marker-without-data, data-without-marker, stale doc, config
wiring deleted, relayed-consent no-token). CI wired
(`grep -c test_lifecycle_kept_pauses_parity validate.yml` = 1). 10 tests pass.

**R6 — Requirements-doc supersession · PASS**
`grep -c 'two kinds' project.md` = 0; `project.md:27` now describes the 4-kind +
`suppressed_by` model and names `kept-pauses-data.toml` +
`cortex-generate-kept-pauses` + the parity test as the enforcement pair.
`docs/policies.md` re-targets to `kept-pauses-data` (grep = 1).

**R7 — Four verbs follow house conventions · PASS**
All four (`plan_decision`, `review_verdict`, `spec_approve`,
`implement_transition`) carry a `KNOWN_STATES` tuple, `main(argv)` that
`_telemetry.log_invocation`s first and never tracebacks (bare-except → JSON
`{"state":"error"}` envelope, exit 0), `# (a)/(b)/(c)` ordered emissions each
presence-checking via parsed-`event`-field `_event_exists` (never substring),
short-circuit arms returning before the first mutation, all emission through
`log_event` (flock + O_APPEND + spaced json — no hand-rolled `json.dumps`), a
`_reject_unsafe_slug` guard rejecting `/`,`\`,`..` before any filesystem access,
caller-passed args only (ADR-0019), and a documented CWD-only root-resolution
convention. Four `[project.scripts]` rows + four executable `bin/` wrappers;
`test_lifecycle_verb_deployment.py` (33 tests incl. deployment) passes.

**R8 — Plan-decision verb · PASS**
Discriminants `{branch-mode-approved, wait-approved, cancelled, revise}` route to
the exact ordered emissions specced. `phase_transition` guard matches
event+from/to (`{"from":"plan","to":"implement"}`), not the bare event name.
Typed `lifecycle-cancelled` subcommand added (`lifecycle_event.py:283`). 23 tests
incl. no-duplicate + double-invocation idempotency pass.

**R9 — Review-verdict verb · PASS**
`_route_target` implements APPROVED→complete / CHANGES_REQUESTED cycle-1→
implement-rework / else→escalated. Ordered `review_verdict` → optional
`drift_protocol_breach` (post-hoc `--breach --retries`) → routed
`phase_transition`. Single owner of `review→implement-rework` (implement.md §3
duplicate removed in Task 10 before wiring; registry note confirms).
`review_verdict` presence-check is cycle-qualified; transition presence-check is
from/to-qualified. 23 tests pass. Documented residual: `drift_protocol_breach`
presence-check is event-name-only, so a genuine second breach in a later cycle
would be suppressed — acknowledged in docstring + plan Risks, sound for the
dominant crash-recovery case.

**R10 — Spec-approve verb · PASS**
Discriminants `{approved, cancelled, revise}`; approved emits `spec_approved`
{decision:approved} → (under `--emit-transition`) `phase_transition specify→plan`
→ backend-gated `_apply_backlog_writeback` via in-process `update_item`.
`--areas` preserve-on-omit (key dropped when omitted; `--clear-areas` sentinel
writes `[]`). `_Exit2` ambiguous-slug carve-out mirrors finalize (exit 2, not
JSON-encoded). Mutually-exclusive `--emit-transition`/`--no-emit-transition` with
both production callers. ADR-0019 crossing recorded in docstring + ADR precedent
list. 33 tests (backend matrix × flag states × arms, `_Exit2`, areas, crash-repair).

**R11 — FILE_EVENTS retired to per-file zero sweeps · PASS**
`count_raw_emissions`/`ZERO_SWEEP_FILES` sweep the four cluster files for all
three raw-emission forms (`cortex-lifecycle-event` typed+log,
`cortex_command.lifecycle_event`, `log_event(`). `grep -cE` = 0 for all four
files. Three form-specific negative controls
(`test_zero_sweep_catches_console_script_form`, `_module_invocation_form`,
`_bare_log_event_call`). The four residual rows keep exact counts;
refine-delegation.md count-1 survives. 36 roundtrip tests pass.

**R12 — Implement-transition verb · PASS**
`batch_dispatch{batch,tasks}` (batch-qualified presence check) and §4 transition
reading criticality/tier via `common.reduce_lifecycle_state` (`.state.get(...)`
+ `.corrupted`, never raw parsing), emitting `phase_transition implement→
{review|complete} --tier`. Routing rule ("review when criticality ∈ {high,
critical} OR tier=complex") in `_resolve_route`; corrupted→(review, complex).
criticality-matrix.md:26 rewritten to defer to the verb. 27 tests incl.
corrupted arm.

**R13 — Cluster prose rewrites · PASS**
plan/review/implement/specify + refine SKILL.md §5 + refine-delegation route on
JSON discriminants (complete.md Step-7 pattern). Each call site carries a
"command not found → halt and instruct install; do NOT record by hand" arm that
names ONLY the verb (with an inline convention comment forbidding raw-emission
surfaces so it does not self-trip the sweep). plan.md keeps the
`feature_paused`-not-honored warning. `spec_approved.decision` enum-only field
added. `cortex-check-events-registry --audit`, `-check-skill-path`,
`-check-bare-python-import` pass.

**R14 — Events-registry re-registration · PASS**
Verb/Python-exclusive events flipped `gate-enforced`→`manual` with
replacement-enforcement rationale: `plan_approved`, `feature_paused`,
`lifecycle_cancelled`, `batch_dispatch`, `review_verdict`,
`drift_protocol_breach`, `spec_approved`. `phase_transition` correctly STAYS
`gate-enforced` — it remains multi-producer (refine-delegation.md, SKILL.md,
walkthrough.md prose producers persist). `lifecycle_cancelled` typed-subcommand
upgrade took an upgrade note, not a same-commit deletion. `--audit` exits with
only the 12 pre-existing STALE_DEPRECATION rows; no cluster row claims
gate-enforced with a Python-only producer.

**R15 — Overnight reads shared reducer in-process · PASS**
`orchestrator-round.md`: `grep -c '_read_criticality'` = 0; `_effective_criticality`
imports and calls `reduce_lifecycle_state` in-process. `gate_enabled` short-circuit
preserved (executes only when `synthesizer_overnight_enabled`). Corrupted-but-
criticality-present → uses the value AND warns; unknowable/exception →
single-agent path + morning-report warning via
`log_event(SYNTHESIZER_ERROR, stage=criticality_read)`; never defers. Single-agent
rationale comment present; corrupted→critical_subset rejected in-comment. Override
fix (overrides now honored) documented. `test_criticality_partition_uses_shared_reducer`
passes.

**R16 — Heading-citation pin retires · PASS**
`grep -c 'test_plan_md_has_1a_heading'` = 0; sibling 1b/§5 pins retained; stale
`:242` citation pruned. `test_skill_section_citations.py` passes.

**Cross-cutting critical-review decisions · all PASS**
- Implement-before-review ordering (Task 10 before 11): registry note confirms
  implement.md §3 duplicate removed first, verb becomes sole emitter of
  `review→implement-rework` at every commit boundary.
- refine-delegation boundary-enumeration guard: item-3 template drops
  `specify→plan` (keeps clarify→research + research→specify);
  `test_refine_delegation_phase_transition_enumerates_only_two_boundaries`
  guards it beyond the boundary-blind count-1 pin.
- Halt-arm-names-the-verb convention: verified in plan/implement/review/specify
  prose with an inline convention comment.

No Stage-1 FAIL.

## Stage 2 — Code Quality

- **Naming consistency**: The four verbs are near-identical in shape —
  `_reject_unsafe_slug`, `_event_exists(events_log, name, match_fields)`,
  `KNOWN_STATES`, `_build_parser`, `main(argv)`. Discriminant vocab is coherent
  (`state` echoes the routed outcome). Module/console-script names fit the
  existing verb vocabulary. Consistent, readable.
- **Error handling**: Never-traceback envelopes uniform across all four
  (`{"state":"error"}`, exit 0). `spec_approve._Exit2` carve-out faithfully
  mirrors `finalize._Exit2` (exit 2, candidate list to stderr, exempt from JSON
  encoding). Slug guards run before any filesystem access. `_event_exists`
  parses defensively (malformed lines skipped, never raised).
- **Test coverage**: The plan's per-task verification steps were executed — spot
  ran the named files: 106 verb tests, 36 roundtrip, 10 parity, 33
  deployment/citation/fixture tests, all green. Negative controls exist for every
  coarse net (zero-sweep×3 forms, parity×5, deployment×2).
- **Pattern consistency**: Verbs cite and follow the finalize/wontfix template
  (KNOWN_STATES, `_telemetry.log_invocation`, presence-check helpers, `# (a)/(b)/(c)`
  comments). Prose routing follows the complete.md Step-7 "act on the verdict; do
  not re-derive it" pattern.

Minor observation (not a defect, already documented): `review_verdict`'s
`drift_protocol_breach` presence-check keys on event-name only; a genuine second
breach in a later review cycle would be suppressed. The docstring and plan Risks
both surface this as a knowingly-accepted residual, sound for the dominant
crash-recovery case and consistent with the byte-identical-to-typed-subcommand
constraint (the subcommand carries no cycle field to qualify on). No change
requested.

## Requirements Drift

**State**: none
**Findings**: None. The `project.md:27` "two kinds"→4-kind supersession is the
intended requirements update this feature applies (Requirement 6), not drift.
The overnight criticality-override behavior fix (overrides honored when the gate
is enabled) is captured by the spec's "Changes to Existing Behavior" section.
The implementation adds no behavior the requirements do not reflect.
**Update needed**: None

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
