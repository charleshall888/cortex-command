# Plan: 378 — 374 follow-ups (lifecycle_slug coercion, spec-approve routing, CLI_PIN dedup)

## Overview
Clear three #374 residues durably: a key-scoped frontmatter quoter + reader coercion + backfill (Phase 1), a lifecycle_phase write-omission fix across ALL completion writers + backfill (Phase 2), a verb-owned spec-approve write-back with prose reroute (Phase 3), and self-guarding CLI_PIN convergence + CI wiring (Phase 4). Key decisions: quote-by-key-allowlist (not blanket); status stays `_project_status`-owned in advance.py; pin bump + multi-target rewriter co-commit atomically; the absorbed-verb guard extends the existing roundtrip test rather than a new whole-tree scanner.
**Architectural Pattern**: shared-state

## Outline

### Phase 1: Numeric slug fix (tasks: 1, 2, 3)
**Goal**: Stop the `resolve.py` TypeError crash and green `test_lifecycle_references_resolve.py`; keep numeric IDs valid as string slugs.
**Checkpoint**: `pytest tests/test_lifecycle_references_resolve.py -q` green AND `grep -rnE '^(lifecycle_slug|feature): [0-9]+$' cortex/backlog cortex/lifecycle` = 0.

### Phase 2: Stale lifecycle_phase (tasks: 4, 5)
**Goal**: ALL completion writers (including the served-loop `advance.py` path) advance `lifecycle_phase`; backfill the frozen items.
**Checkpoint**: no `status: complete` item still carries `lifecycle_phase: research`, and the served-loop `review→complete` path advances phase.

### Phase 3: spec-approve reroute (tasks: 6, 7, 8)
**Goal**: advance.py's spec-approve arm owns spec/areas (status stays events-first); ALL prose (refine + lifecycle trees) commands the served verb; the existing roundtrip test guards regression.
**Checkpoint**: no commanding `cortex-lifecycle-spec-approve` invocation remains in `skills/`, `cortex-lifecycle-advance spec-approve` is present, `just build-plugin` drift-clean.

### Phase 4: CLI_PIN + guards + CI (tasks: 9, 10, 11)
**Goal**: Converge the pins with the multi-target rewriter co-committed (no re-drift window), bind via a target-set invariant, wire regression guards into CI.
**Checkpoint**: both `CLI_PIN[0]` equal, rewriter references both pin files, target-set test passes, `validate.yml` references the resolve test.

## Tasks

### Task 1: Key-scoped YAML-safe scalar writer helper + route the three writers
- **Files**: `cortex_command/backlog/update_item.py`, `cortex_command/lifecycle/create_index.py`, `cortex_command/overnight/report.py`, `cortex_command/backlog/frontmatter_quote.py` (new helper module), `tests/test_frontmatter_quoting.py` (new)
- **What**: Add a single-scalar, key-scoped quoter and route all three unquoted writers through it, per spec req-1.
- **Depends on**: none
- **Complexity**: complex
- **Context**: `update_item.py:372` calls `_set_frontmatter_value(text, key, str(value))` (type erased); `:370` passes literal `"null"` for None. `create_item.py:51-75` `_yaml_safe_title_value` (under `backlog/`) is the title-scoped precedent — reuse its escaping approach, NOT `safe_dump`, for generic keys. String-intended allowlist: `lifecycle_slug`, `feature`, `parent`, `spec` (+ bare slug/path/id-string scalars). Quote when the value mis-resolves under YAML 1.1 (int/float, bool words + case/short variants, sexagesimal `12:34`, `.inf/.nan`, hex/octal, empty, leading YAML indicator/inline `#`) EXCEPT the `null`/`~` None sentinel (stays bare). Leave non-allowlist keys bare (`updated`/`created` dates, `blocked-by`/`parent_backlog_id` ints). The three writers: `update_item.py::_set_frontmatter_value` (all scalars); `cortex_command/lifecycle/create_index.py:115` `_render` emits `f"feature: {feature}\n"` (route) and `parent_backlog_id:` (leave bare); `overnight/report.py:460` emits `f"lifecycle_slug: {name}\n"` (route). NOTE: `create_index.py` is under `cortex_command/lifecycle/`, not `backlog/`.
- **Verification**: `.venv/bin/pytest tests/test_frontmatter_quoting.py -q` passes (asserts `lifecycle_slug=378`/`feature`/`parent` with `378`/`yes`/`12:34` → quoted; `updated` date, numeric `blocked-by`, None → bare; a value with `"`/`\`/`:` round-trips through `yaml.safe_load` to the exact string) AND `grep -c 'safe_dump' cortex_command/backlog/update_item.py` = 0 AND each of the three writers references the helper — `grep -c <helper_name> cortex_command/backlog/update_item.py cortex_command/lifecycle/create_index.py cortex_command/overnight/report.py` shows ≥1 per file
- **Status**: [ ] pending

### Task 2: Backfill the 4 malformed files and confirm the gate greens
- **Files**: `cortex/backlog/374-phase-c-gate-decide-the-served-next-advance-loop-on-post-composition-evidence.md`, `cortex/backlog/378-374-follow-ups-lifecycle-slug-frontmatter-coercion-refine-spec-approve-routing-residue-cli-pin-dedup.md`, `cortex/lifecycle/374/index.md`, `cortex/lifecycle/378/index.md`
- **What**: Quote the numeric `lifecycle_slug`/`feature` values (`374`→`"374"`, `378`→`"378"`), satisfying spec req-2 and req-4.
- **Depends on**: none
- **Complexity**: simple
- **Context**: These 4 are the only numeric-valued occurrences (verified). The `374` backlog file is ALSO a Task 5 target (it is `status: complete` with `lifecycle_phase: research`) — Task 5 depends on [2] to serialize the shared-file edits, so this task edits only the slug value and Task 5 later edits only the phase value on the post-Task-2 base. `test_lifecycle_references_resolve.py` parses only `lifecycle_slug` (not `feature:`), so it proves the 2 backlog files; the 2 index `feature:` files are proven by the grep.
- **Verification**: `grep -rnE '^(lifecycle_slug|feature): [0-9]+$' cortex/backlog cortex/lifecycle` = 0 AND `.venv/bin/pytest tests/test_lifecycle_references_resolve.py::test_every_lifecycle_reference_resolves -q` passes
- **Status**: [ ] pending

### Task 3: Defensive reader coercion at the yaml.safe_load sites
- **Files**: `cortex_command/backlog/resolve_item.py`, `cortex_command/lifecycle/resolve.py`, `tests/test_resolve_numeric_slug_coercion.py` (new)
- **What**: Coerce a non-None `lifecycle_slug` to `str` at `resolve_item.py:136` and before `resolve.py:181`'s `lifecycle_base / slug`, keeping the `resolve_item.py:218` `isinstance` guard tolerant (spec req-3).
- **Depends on**: none
- **Complexity**: simple
- **Context**: `resolve_item.py:133-136` `_resolve_lifecycle_slug` returns `fm["lifecycle_slug"]` raw; `resolve.py:179-186` remap + `:181` `(lifecycle_base / slug).is_dir()` raises `TypeError` on an int. Disjoint from Task 1/2 files.
- **Verification**: `.venv/bin/pytest tests/test_resolve_numeric_slug_coercion.py -q` passes (feeds `lifecycle_slug=374` int through both paths; asserts no `TypeError`/`AttributeError`, `str` result)
- **Status**: [ ] pending

### Task 4: Advance lifecycle_phase on ALL completion writers (incl. the served-loop path)
- **Files**: `cortex_command/lifecycle/finalize.py`, `cortex_command/overnight/close_tickets.py`, `cortex_command/lifecycle/advance.py`, `tests/test_lifecycle_phase_tracks_status.py` (new)
- **What**: Make every `status: complete` writer also advance `lifecycle_phase` to the completion phase (spec req-5). Audit the full set first: `grep -rn "update_item.*status.*complete\|'status': 'complete'\|status=.complete" cortex_command/`.
- **Depends on**: none
- **Complexity**: complex
- **Context**: Confirmed `status: complete` writers: `finalize.py:160`, `overnight/close_tickets.py:147` (NOT `lifecycle/close_tickets.py` — that path does not exist), and — critically — `advance.py:710` `_project_status_inner` (`_STATE_TO_STATUS["complete"]="complete"` at `:449`) is the events-first `review→complete` served-loop completion path that MUST also advance phase, else new served-loop completions re-freeze at their prior phase. Choose the terminal value (`complete`) from the completion event, not blindly (a `wontfix` item must not become `complete`). This task OWNS all advance.py edits for phase; Task 6 (spec-approve arm) depends on [4] to serialize advance.py, so no worktree race.
- **Verification**: `.venv/bin/pytest tests/test_lifecycle_phase_tracks_status.py -q` passes (drives an item to `status: complete` via BOTH the finalize path AND the advance.py `review→complete` path, asserting `lifecycle_phase` != `research` / equals the completion value in each)
- **Status**: [ ] pending

### Task 5: Backfill the stale lifecycle_phase items
- **Files**: `cortex/backlog/` (the `status: complete` items still at `lifecycle_phase: research`, incl. the `374` file)
- **What**: Rewrite `lifecycle_phase` on completed items to the terminal value chosen in Task 4 (spec req-6).
- **Depends on**: [2, 4]
- **Complexity**: simple
- **Context**: Depends on [4] for the terminal value and [2] because the `374` file is shared (Task 2 quotes its slug first; this task, branching after Task 2 merges, edits only its phase — avoiding the same-file race). Identify targets via `grep -lE '^status: complete' cortex/backlog/*.md | xargs grep -lE '^lifecycle_phase: research$'`.
- **Verification**: `grep -lE '^status: complete' cortex/backlog/*.md | xargs grep -lE '^lifecycle_phase: research$'` returns 0 files AND `grep -rnE '^(lifecycle_slug|feature): [0-9]+$' cortex/backlog` = 0 (the shared `374` file's slug-quote survived)
- **Status**: [ ] pending

### Task 6: Extend advance.py spec-approve arm with spec/areas projection (status stays _project_status-owned)
- **Files**: `cortex_command/lifecycle/advance.py`, `tests/test_advance_spec_approve_writeback.py` (new)
- **What**: Add `--spec-path`, `--areas`/`--clear-areas`, `--backend`, `--backlog-file` to the `spec-approve` subparser and project ONLY `spec:`/`areas:` (NOT status), per spec req-7.
- **Depends on**: [4]
- **Complexity**: complex
- **Context**: `advance.py` spec-approve subparser is at ~line 950. `_project_status` (advance.py:681, `_STATE_TO_STATUS["plan"]="refined"` at :444) already writes lattice-guarded `status: refined` for `to_state==plan` — do NOT re-write status. Reference `spec_approve.py:167-221` `_apply_backlog_writeback` for the write shape and areas preserve-on-omit / `--clear-areas`, but IMPLEMENT the projection in advance.py — do NOT edit `spec_approve.py`. Depends on [4] so advance.py edits serialize (Task 4 owns the `_project_status_inner` completion edit; this task edits the spec-approve subparser/arm on the post-Task-4 base). Preserve emission-only back-compat.
- **Verification**: `.venv/bin/pytest tests/test_advance_spec_approve_writeback.py -q` passes (approved spec-approve yields `status: refined`+`spec:`+`areas:`; an item already at `complete`/`in_progress` is NOT demoted; an omit-flags caller is unchanged)
- **Status**: [ ] pending

### Task 7: Reroute ALL prose off the legacy verb (refine + lifecycle trees)
- **Files**: `skills/refine/references/specify.md` (lines 149 command + 168 halt-arm), `skills/refine/SKILL.md` (line 90 description), `skills/lifecycle/references/refine-delegation.md` (lines 7, 55 descriptions), plus the regenerated `plugins/cortex-core/skills/refine/**` and `plugins/cortex-core/skills/lifecycle/references/refine-delegation.md` mirrors via `just build-plugin`
- **What**: Replace the commanding `cortex-lifecycle-spec-approve` call and update every descriptive/halt-arm mention to `cortex-lifecycle-advance spec-approve` across BOTH skill trees, then regenerate the mirror (spec req-8).
- **Depends on**: [6]
- **Complexity**: complex
- **Context**: Commanding invocation at `specify.md:149`; sanctioned mentions at `specify.md:168` (halt-arm — keep the convention, update the verb name), `SKILL.md:90`, and `refine-delegation.md:7,55` (descriptions of which verb records the `specify→plan` transition — these become stale after the reroute and are in the `skills/lifecycle/` tree, outside `skills/refine/`). All are lifecycle-gated + dual-source: edit canonical `skills/**` only, run `just build-plugin`, stage the regenerated mirror IN THE SAME COMMIT (a partial edit leaves the drift loop blocking every subsequent commit). Sequence away from any concurrent skill-editing session. Legacy binary stays deployed (ADR-0024).
- **Verification**: `grep -rn 'cortex-lifecycle-spec-approve' skills/` = 0 AND `grep -rn 'cortex-lifecycle-advance spec-approve' skills/refine/` ≥ 1 (replacement present) AND `just build-plugin` then `git diff --exit-code plugins/cortex-core/` is clean (drift-free)
- **Status**: [ ] pending

### Task 8: Extend the existing roundtrip test to guard the spec-approve reroute
- **Files**: `tests/test_lifecycle_event_roundtrip.py`
- **What**: Extend the existing per-file zero-sweep test (referenced by `specify.md:168`'s convention comment) to assert `specify.md`/`SKILL.md` command `cortex-lifecycle-advance spec-approve` and contain NO commanding `cortex-lifecycle-spec-approve` (spec req-9, re-scoped from a new whole-tree scanner to extending existing machinery — narrower, satisfiable, no command-vs-mention heuristic needed).
- **Depends on**: [7]
- **Complexity**: simple
- **Context**: `test_lifecycle_event_roundtrip.py` already runs `test_refine_delegation_no_longer_emits_typed_phase_transition` (a per-file grep sweep). Add an assertion targeting the `cortex-lifecycle-spec-approve` COMMANDING form in `skills/refine/` (not descriptive mentions — but after Task 7 the whole-`skills/` grep is 0 anyway, so a simple `cortex-lifecycle-spec-approve` sweep over `skills/refine/` suffices). Do NOT build a general absorbed-verb scanner over `skills/**` — the tree carries sanctioned descriptive mentions and actively-used verbs (`cortex-lifecycle-event phase-transition`) that a substring scanner would wrongly flag.
- **Verification**: `.venv/bin/pytest tests/test_lifecycle_event_roundtrip.py -q` passes AND, temporarily reverting Task 7's `specify.md` edit, the new assertion fails (proves it catches a re-introduction) — `Interactive/session-dependent: the negative check is demonstrated once during implementation, not gated in CI`
- **Status**: [ ] pending

### Task 9: Converge the pin AND make the rewriter + workflows multi-target (one commit)
- **Files**: `plugins/cortex-core/install_core.py`, `bin/cortex-rewrite-cli-pin`, `.github/workflows/auto-release.yml`, `.github/workflows/release.yml`, plus the regenerated `plugins/cortex-core/bin/cortex-rewrite-cli-pin` mirror via `just build-plugin`
- **What**: In ONE commit (no re-drift window): bump `install_core.py:69` `CLI_PIN`→`("v2.35.0","2.0")`, make `bin/cortex-rewrite-cli-pin` target both pin files, and have `auto-release.yml` + `release.yml` bump/`git add`/lint both (spec req-10 + req-11a/b). Merging the bump and the multi-target rewriter into one task/commit prevents the "pin bumped alone, still single-target rewriter" re-drift the dependency-graph alone would not prevent.
- **Depends on**: none
- **Complexity**: complex
- **Context**: `bin/cortex-rewrite-cli-pin` today has only a required positional `tag`, `--path`, `--no-verify` (no dry-run/list mode) and `DEFAULT_TARGET` overnight-only; `auto-release.yml:131/138` invokes+`git add`s overnight only; `release.yml` drift lint (~:22-76) overnight-only. Add `plugins/cortex-core/install_core.py` as a rewrite target (regex-based — surrounding code, not a standalone tuple module). `install_core.py` stays stdlib-only. `bin/cortex-*` IS dual-source-mirrored (unconditional): run `just build-plugin` and stage the mirror in this commit.
- **Verification**: `grep -h 'CLI_PIN' plugins/cortex-overnight/cli_pin.py plugins/cortex-core/install_core.py` shows matching `v2.35.0` AND `grep -c 'install_core.py' bin/cortex-rewrite-cli-pin` ≥ 1 (rewriter source names the second target) AND `grep -c 'install_core.py' .github/workflows/auto-release.yml` ≥ 1 (workflow git-adds it) AND `just build-plugin` then `git diff --exit-code plugins/cortex-core/bin/` is clean
- **Status**: [ ] pending

### Task 10: Target-set invariant + release-invariant tests for both pins
- **Files**: `tests/test_cli_pin_target_set.py` (new), `tests/test_release_artifact_invariants.py`
- **What**: Assert the rewriter's target set contains both pin files (the req-11c invariant, not point-in-time equality) and extend the release-artifact invariants to the cortex-core pin.
- **Depends on**: [9]
- **Complexity**: simple
- **Context**: `test_release_artifact_invariants.py` (`CLI_PIN_PY_RELATIVE`) reads only the overnight path today. `test_cli_pin_target_set.py` asserts both pin files are in the rewriter's target set (parse `bin/cortex-rewrite-cli-pin`'s target list / run it against a fixture and assert both files' pins change) and fails on single-target — structurally binding multi-targetness going forward.
- **Verification**: `.venv/bin/pytest tests/test_cli_pin_target_set.py tests/test_release_artifact_invariants.py -q` passes (target set contains both pin files; both paths read; a single-target fixture fails)
- **Status**: [ ] pending

### Task 11: Wire the regression guards into CI
- **Files**: `.github/workflows/validate.yml`
- **What**: Add `tests/test_lifecycle_references_resolve.py`, `tests/test_lifecycle_event_roundtrip.py`, and `tests/test_cli_pin_target_set.py` to the CI critical path (spec req-12).
- **Depends on**: [2, 8, 10]
- **Complexity**: simple
- **Context**: `validate.yml` currently blocking-runs only `test_check_contract.py` + `test_lifecycle_kept_pauses_parity.py` + a dashboard smoke test. Add the three regression tests so a re-introduced malformed slug / spec-approve reroute regression / pin single-targeting fails CI. Depends on [2] (resolve test green), [8] (roundtrip assertion added), [10] (target-set test exists) — else CI goes red on merge.
- **Verification**: `grep -Ec 'test_lifecycle_references_resolve|test_cli_pin_target_set|test_lifecycle_event_roundtrip' .github/workflows/validate.yml` ≥ 3
- **Status**: [ ] pending

## Risks
- **lifecycle_phase terminal value (Task 4/5)**: some completed items ended at a non-`complete` phase (e.g. `wontfix`) — Task 4 must derive the value from the actual completion event, not a constant, and Task 5's backfill must respect that.
- **Key allowlist maintenance (Task 1 / ADR-0027)**: a future numeric-looking string field left off the allowlist re-exposes the bug — the CI wiring (Task 11) is the backstop.
- **advance.py two-editor serialization (Tasks 4, 6)**: both edit advance.py; the `6→[4]` edge serializes them, but the edits touch different functions (`_project_status_inner` vs the spec-approve subparser) — verify no incidental overlap during implementation.
- **Reroute completeness (Task 7)**: the `specify.md:168` halt-arm and `refine-delegation.md:7,55` descriptions are easy to miss; the `grep -rn 'cortex-lifecycle-spec-approve' skills/` = 0 verification is the backstop.

## Acceptance
The whole feature is done when, on a clean tree: `.venv/bin/pytest tests/test_lifecycle_references_resolve.py -q` is green; `grep -rnE '^(lifecycle_slug|feature): [0-9]+$' cortex/backlog cortex/lifecycle` = 0; no `status: complete` item carries `lifecycle_phase: research` AND the advance.py `review→complete` path advances phase; `grep -rn 'cortex-lifecycle-spec-approve' skills/` = 0 with `cortex-lifecycle-advance spec-approve` present and `just build-plugin` drift-clean; both `CLI_PIN[0]` equal with the rewriter naming both targets and the target-set test passing; and `just test` is green.
