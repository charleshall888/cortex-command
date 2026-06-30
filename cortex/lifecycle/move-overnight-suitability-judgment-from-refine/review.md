# Review: move-overnight-suitability-judgment-from-refine

## Stage 1: Spec Compliance

### Requirement 1: Launch accepts an explicit curated selection set (`--only`)
- **Expected**: `cortex overnight launch --help` lists a new option; `--only` appears in the cli.py launch subparser (grep = 1).
- **Actual**: `cortex_command/cli.py:1052-1064` adds `launch.add_argument("--only", dest="only", default=None, ...)` with a help string describing the curated/frozen set, the absent-default re-selection, the empty refusal, and the dependency-closure requirement.
- **Verdict**: PASS
- **Notes**: Option name appears in the subparser → present in `--help`.

### Requirement 2: handle_launch executes exactly the supplied set; absent input unchanged; empty → nothing_ready
- **Expected**: curated set → state features == subset; `only is None` → full re-selection; empty → `nothing_ready`.
- **Actual**: `cli_handler.py:2160-2185`. `only_arg = getattr(args, "only", None)`; when `not None`, splits/strips to `curated`; empty `curated` returns the `nothing_ready` envelope (exit 1); otherwise calls `filter_selection_to_curated_set` and replaces `selection` with the restricted result. Absent (`None`) skips the block entirely → unchanged full selection. Covered by `test_launch_only_executes_curated_subset` (bootstrap receives exactly {alpha}), `test_launch_only_none_is_full_selection` (bootstrap receives {alpha,beta,gamma}), `test_launch_only_empty_returns_nothing_ready` (bootstrap tripwire, `nothing_ready`).
- **Verdict**: PASS
- **Notes**: The absent-vs-empty distinction (`getattr(... ) is None` vs empty list) is implemented exactly as specified.

### Requirement 3: Frozen set must be dependency-closed; launch refuses non-closed fail-loud
- **Expected**: dropping an in-session blocker while keeping its dependent → `dependency_not_closed`-style error naming the blocker; never bootstraps a dangling `intra_session_blocked_by`. Step 6 rubric is blocker-aware.
- **Actual**: `backlog.py:1191-1214` iterates each curated slug's `intra_session_deps` and collects any blocker not in `curated_set` → returns `{"error": "dependency_not_closed", "blockers": [...], "dependents": [...], "message": ...}` before any batch construction. `handle_launch` returns 1 on this error before `validate_target_repos`/`bootstrap`. Tests `test_curated_drop_blocker_keep_dependent_refuses` and `test_launch_only_dependency_not_closed_refuses` (with `validate_target_repos`/`bootstrap` tripwires). Rubric blocker-awareness present in `new-session-flow.md:82`.
- **Verdict**: PASS
- **Notes**: Transitive chains are covered: each dependent's direct blockers are checked, and a kept blocker is itself checked against its own `intra_session_deps`, so a dropped grand-blocker is still caught.

### Requirement 4: Skill passes the post-curation frozen set to launch; approved == executed
- **Expected**: Step 7 references the new launch selection input (grep = 1).
- **Actual**: `new-session-flow.md:162-168` calls `cortex overnight launch --format json --only <comma-separated active slugs>` and states "the active list shown at approval IS the frozen set IS the executed set; there is no re-selection between approval and execution" (3 `--only` occurrences). SKILL.md L1 step 7.2 mirrors it.
- **Verdict**: PASS

### Requirement 5: `[R]emove` now sticks at execution (latent-bug fix)
- **Expected**: a removed feature does not appear in the bootstrapped set (covered by R2's curated-subset test).
- **Actual**: Removal excludes the slug from the `--only` set; `filter_selection_to_curated_set` drops non-kept items from each batch and drops emptied batches. `test_launch_only_executes_curated_subset` confirms the excluded slugs never reach bootstrap. Prose `new-session-flow.md:123` directs `[R]` to mutate the active pool directly (no re-selection).
- **Verdict**: PASS

### Requirement 6: Step 6 sets aside poor-fit specs with reasons, biased to exclusion
- **Expected**: set-aside rubric/section present (grep = 1); names mechanical + soft signals; bias-to-exclude.
- **Actual**: `new-session-flow.md:75-88` — "Suitability triage (judged once, on first Step 6 entry)", "Bias toward exclusion", mechanical signals (`Interactive/session-dependent` AC; genuinely unresolved `## Open Decisions`) and soft signals (network/credentials; human-visual/judgment verification; exploratory/under-specified). SKILL.md:68 summarizes. The `- None.`/placeholder idiom is explicitly excluded (line 79).
- **Verdict**: PASS

### Requirement 7: No silent drop; structural guarantee at approval→launch boundary
- **Expected**: every set-aside shown with reason; `[I]` re-add verb (rendered only when set-aside pool non-empty); re-display complete state before every approval (grep both = 1).
- **Actual**: `new-session-flow.md:108` ("Re-display before every approval"), `:110` + `:117` render `[I]` only when the set-aside pool is non-empty, `:124` defines the `[I]` handler. Approval==execution tie restated. SKILL.md:68 mirrors the conditional `[I]`.
- **Verdict**: PASS

### Requirement 8: Three pools with correct re-add semantics
- **Expected**: hard-ineligible (display-only, never re-addable), suitability set-aside (always re-addable), active; hard-ineligible re-add refused with reason.
- **Actual**: `new-session-flow.md:84-88` defines the three pools; hard-ineligible "display-only, never re-addable" with refusal-on-re-add; suitability "excluded by default but always re-addable". Line 124's `[I]` handler refuses a hard-ineligible target with its reason.
- **Verdict**: PASS

### Requirement 9: Mutations and re-renders preserve decisions (no flicker); judge-once
- **Expected**: judge-once / re-apply-curation direction present (grep = 1); `[T]` re-renders but re-applies maintained pools.
- **Actual**: `new-session-flow.md:75` ("judged once, on first Step 6 entry") and `:125` ("re-apply the existing curation ... do not re-judge suitability from scratch, so no candidate ... flickers"). SKILL.md:68 states `[R]`/`[I]` mutate pools without re-selection; only `[T]` re-runs `prepare` then re-applies curation.
- **Verdict**: PASS

### Requirement 10: Remove the `/refine` Step 6 overnight-candidate advisory in full; §5 skip-note intact
- **Expected**: `grep -c 'Overnight-candidate advisory' skills/refine/SKILL.md` = 0 AND `grep -c 'phase_transition'` ≥ 1.
- **Actual**: advisory count = 0; `phase_transition` count = 1, the surviving §5 skip-note at line 156 ("Skip the `phase_transition` event emission ..."). Run-mode-detection `grep -c '"event": "phase_transition"'` block is gone.
- **Verdict**: PASS

### Requirement 11: No residual suitability or run-mode-detection logic in `/refine`
- **Expected**: the single `phase_transition` match is the §5 skip-note; `grep -ci 'overnight candidate'` = 0.
- **Actual**: `overnight candidate` (case-insensitive) = 0; the sole `phase_transition` line is the §5 skip-note. `/refine` no longer reasons about overnight execution.
- **Verdict**: PASS

### Requirement 12: Affordance-preservation documented
- **Expected**: commit body or PR description records that the protection is preserved at overnight curation for the overnight path, and plainly states the standalone-refine→interactive-build (or never-overnight) population loses the signal with no replacement (deletion, not relocation).
- **Actual**: commit `3497ea5c` body carries a full "Affordance-preservation (CLAUDE.md authoring guideline)" paragraph: PRESERVED at overnight curation FOR THE OVERNIGHT PATH; REMOVED WITH NO REPLACEMENT — "a deletion, not a relocation" — for the standalone/never-overnight population, with the accepted-trade rationale.
- **Verdict**: PASS

### Requirement 13: Plugin mirrors regenerated; governance gates green
- **Expected**: `plugins/cortex-core/skills/refine/` and `plugins/cortex-overnight/skills/overnight/` (+ references) regenerated; canonical + mirror committed together; `just test` exits 0; drift hook passes.
- **Actual**: `diff -q` shows MATCH for refine SKILL.md (cortex-core mirror), overnight SKILL.md and new-session-flow.md (cortex-overnight mirror). The launch/prepare test module passes (13 passed). Note the overnight mirror is correctly under **cortex-overnight**, per the spec's stale-touch-point correction.
- **Verdict**: PASS

### Non-Requirements (negative checks)
- **No persistent/cross-session re-add memory**: `new-session-flow.md:124` states the re-add is "a one-shot, session-scoped override ... not remembered to suppress the same set-aside in a future curation." No store added. PASS.
- **No new `set_aside` field in the selection envelope**: `grep -rn set_aside` over non-test source = none; `_selection_summary_payload` not extended with a suitability channel. PASS.
- **No suitability logic in `filter_ready` / `select_overnight_batch` / the runner**: `grep -i suitab` over backlog.py/plan.py/state.py/runner.py = none; `filter_ready` adds no spec-body reads (the two `read_text` hits are the pre-existing frontmatter parse and index load, both outside `filter_ready`); runner does not call `select_overnight_batch`. PASS.
- **No backend-awareness in the relocated logic**: `filter_selection_to_curated_set` contains no backend resolution/branching; `handle_launch`'s backend guard (`_refuse_unsupported_backlog_backend`) is the pre-existing fail-closed in-process guard, not new branching for the curated set. PASS.
- **No change to `/refine`'s `phase_transition` logging boundary**: §5 skip-note retained verbatim. PASS.
- **No session-size cap introduced**: `new-session-flow.md:110` retains "no recommended upper limit on session size." PASS.

### Edge Cases
- **Drop in-session blocker, keep dependent** → `dependency_not_closed` naming the blocker; never bootstraps a dangling dep (test + code). Handled.
- **Re-add hard-ineligible** → refused with the item's reason (`new-session-flow.md:88,124`). Handled.
- **`--only` includes an ineligible slug (typo / drift / curation-induced)** → `ineligible_slug` error whose message disambiguates the three causes (`backlog.py:1182-1188`); the dependency-closed case routes to R3's blocker-named message. Handled.
- **prepare-time vs launch-time drift** → fail-loud via `ineligible_slug` (the curated slug is absent from launch-time `selected_slugs`). Handled.
- **Empty `--only`** → `nothing_ready` (test `test_launch_only_empty_returns_nothing_ready`). Handled.
- **All candidates set aside** → empty active pool surfaced obviously (`new-session-flow.md:106`). Handled.
- **Under-flagging** → accepted residual risk, documented (operator gate + recoverable overnight failure backstop). Handled.
- **`## Open Decisions: - None.` idiom** → explicitly not a trigger (`new-session-flow.md:79`). Handled.
- **`launch` without `--only` (direct CLI)** → unchanged full selection (test `test_launch_only_none_is_full_selection`). Handled.

### Special-attention items (per review instructions)
- **(a) R2/R3/R5** — `filter_selection_to_curated_set` + `handle_launch` execute exactly the curated set, refuse a non-closed set fail-loud, and behave unchanged when `--only` absent / `nothing_ready` when empty. Confirmed by code + 4 helper tests + 4 handler tests.
- **(b) Post-filter mechanism** — the helper post-filters the already-computed `SelectionResult` rather than re-running `select_overnight_batch`/`filter_ready` over a restricted universe. The docstring (`backlog.py:1146-1157`) documents why this is load-bearing: a dependent eligible *because its blocker is terminal/complete* has no `intra_session_deps` entry, so re-selecting a restricted universe would reclassify it as externally-blocked and silently drop it. This matches the spec's Open-Decision resolution exactly. Correct and durable.
- **(c) Non-Requirements** — all six confirmed negative (see above).
- **(d) R10/R11** — refine advisory fully gone; §5 `phase_transition` skip-note survives. Confirmed.

## Stage 2: Code Quality
- **Naming conventions**: Consistent. `filter_selection_to_curated_set` reads clearly; error envelopes use the established `{"error", "message", ...}` shape with cause-specific keys (`ineligible_slug`/`slugs`, `dependency_not_closed`/`blockers`/`dependents`), matching the existing `nothing_ready`/`invalid_target_repos`/`bootstrap_failed`/`selection_failed` envelopes. The `--only` arg uses the existing `dest=`/`getattr(args, ..., default)` idiom.
- **Error handling**: Fail-loud and pre-mutation. The helper returns a `(restricted, None)` / `(None, error)` tuple; `handle_launch` surfaces the error envelope and returns exit 1 *before* `validate_target_repos`/`bootstrap_session`. The absent (`None`) vs empty (`""` → no slugs) distinction is handled precisely, with empty routing to the existing `nothing_ready` refusal.
- **Test coverage**: Discriminating, not tautological. The closure-refusal test uses a real `intra_session_deps` edge (gamma→beta) and asserts on the specific blocker/dependent names and message; the curated-subset test asserts the bootstrap fake received exactly {alpha}; the none-vs-curated pair discriminates the unchanged path; the empty and dependency-not-closed handler tests install `_boom` tripwires on `bootstrap_session` (and `validate_target_repos`) to prove no mutation occurs on refusal. The unknown-slug test exercises the `ineligible_slug` branch.
- **Pattern consistency**: Follows the existing `handle_launch` conventions — lazy `backlog_module`/`plan_module` imports, `_emit_json` envelopes, `getattr` defaults, fail-closed backend guard untouched. The skill prose follows the established What/Why authoring style (soft positive-routing, no new MUST), consistent with the MUST-escalation policy.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
