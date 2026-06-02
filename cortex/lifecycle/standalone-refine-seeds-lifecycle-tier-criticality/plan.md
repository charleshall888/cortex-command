# Plan: standalone-refine-seeds-lifecycle-tier-criticality

## Overview
Add a structural `cortex-refine reconcile-clarify` subcommand that appends `to`-keyed `complexity_override`/`criticality_override` rows to bring the lifecycle `events.log` into agreement with the Clarify-determined tier/criticality, guarded by state-based no-op, monotonic no-downgrade, tolerant-read, and append-only invariants — then wire it into `skills/refine/SKILL.md` at Spec-phase entry (before the first §3a/§3b tier/criticality read) so standalone `/refine` runs the same spec-phase gates and produces the same overnight sizing as `/lifecycle`.
**Architectural Pattern**: event-driven
<!-- The fix is a compensating-event append onto the existing events.log event stream; no new store, no read-side change. -->

## Outline

### Phase 1: Reconciliation emitter (tasks: 1, 2)
**Goal**: A single-concern `cortex-refine reconcile-clarify` subcommand in `cortex_command/refine.py` that reconciles `events.log` to a desired tier/criticality with all four guards, plus its R1–R7 unit tests.
**Checkpoint**: `.venv/bin/pytest tests/test_refine_module.py -q` exits 0; after a `simple/medium` seed, invoking reconcile-clarify with `complex/high` makes `state_cli._reduce_events(...) == {"tier":"complex","criticality":"high"}` and both `common.py` readers agree.

### Phase 2: Skill wiring + gates (tasks: 3, 4, 5, 6, 7)
**Goal**: Invoke the subcommand from the refine skill before the first spec-phase tier/criticality read; document the new Python producer in the events registry and the `gate` field in the criticality-matrix doc; preserve kept-pauses parity; regenerate the plugin mirror; add the wiring and end-to-end/delegated-path regression tests.
**Checkpoint**: All touched pytest files green; events-registry, kept-pauses parity, and dual-source mirror diff all clean; the positional wiring test (Task 3) structurally proves the reconcile invocation precedes the `specify.md` delegation (hence the §3a/§3b reads).

## Tasks

### Task 1: Add the `reconcile-clarify` subcommand + guards to `cortex_command/refine.py`
- **Files**: `cortex_command/refine.py`
- **What**: Add a `reconcile-clarify` subcommand and its `_cmd_reconcile_clarify` handler that appends `to`-keyed `complexity_override`/`criticality_override` rows to reconcile `events.log` to the Clarify-determined tier/criticality, with state-based no-op (R3), monotonic no-downgrade (R4), graceful-on-unreadable (R5), append-only (R6), and `gate: "clarify_reconcile"` provenance (R7).
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Argparse: add a sibling parser to the existing `emit-lifecycle-start` block in `_build_parser` (refine.py:193–218). Signature: `reconcile-clarify --lifecycle-slug <slug> (required) [--backlog-slug <slug>] [--complexity simple|complex] [--criticality low|medium|high|critical]`; `el.set_defaults(func=_cmd_reconcile_clarify)`. Reuse `_ALLOWED_COMPLEXITY` / `_ALLOWED_CRITICALITY` (refine.py:22–23) for `choices=`.
  - Desired-value resolution: when `--complexity`/`--criticality` flags are passed, use them (Context B); else call the existing `_read_backlog_frontmatter(backlog_slug)` (refine.py:26) which returns `(tier, criticality)` and already validates/exits 64 on bad values (Context A).
  - Current-state read: implement a *tolerant* local reduce (mirror `_lifecycle_start_present` at refine.py:83–102 — read lines, `json.loads` each, skip `JSONDecodeError`) that replays `lifecycle_start.tier`/`.criticality` then `complexity_override.to`/`criticality_override.to` to compute the current reduced `(tier, criticality)`. Defaults `("simple","medium")` when `events.log` is absent. Do NOT shell out to `state_cli` (it reduce-to-nulls on a torn line — see Risks); the local tolerant reduce is the R5 mechanism. Distinguish "events.log missing" (baseline) from "reduce returned empty" — never treat a malformed-but-present log as "unset and safe to emit blindly."
  - Comparator ordering: tier `simple < complex`; criticality `low < medium < high < critical`. Per field, append an override ONLY when desired ≠ current AND desired is strictly higher than current (no-downgrade). Emit nothing for a field that already matches or where desired is lower.
  - Row shape (append, never rewrite): `{"ts": _now_iso(), "event": "complexity_override", "feature": <lifecycle_slug>, "from": <current_tier>, "to": <desired_tier>, "gate": "clarify_reconcile"}` and the `criticality_override` analog (`from`/`to` are the criticality values). Values lowercase. **Omit `schema_version`** to match the canonical override producer `cortex_command/lifecycle/complexity_escalator.py:_emit_event`, which emits no `schema_version` on override rows — do not invent a third convention (no consumer reads the field on these rows; the seed fixture happens to stamp `3`, the escalator omits it, so `1` would be a novel non-monotonic value). Reuse `_now_iso()` (refine.py:79) and the append + `PermissionError/OSError → exit 70` idiom from `_cmd_emit_lifecycle_start` (refine.py:135–146). Never touch the `lifecycle_start` row. Behavioral correctness — including the Context-A backlog-sourcing branch — is verified by Task 2.
- **Verification**: `.venv/bin/python -c "from cortex_command.refine import _build_parser; a=_build_parser().parse_args(['reconcile-clarify','--lifecycle-slug','s','--complexity','complex','--criticality','high']); assert a.func.__name__=='_cmd_reconcile_clarify'"` — pass if exit 0 (the subcommand parser is wired to its handler with the documented flags).
- **Status**: [ ] pending

### Task 2: Add R1–R7 emitter unit tests to `tests/test_refine_module.py`
- **Files**: `tests/test_refine_module.py`
- **What**: Add in-process unit tests covering R1–R7 of the `reconcile-clarify` emitter: reduce-agreement, both-readers-agree, idempotency, no-downgrade, malformed-line tolerance, append-only seed preservation, and provenance marker — plus a Context-A case that sources desired values from a written backlog file and a precedence case.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Test style: in-process `cortex_command.refine.main([...])` + `monkeypatch.chdir(tmp_path)`, asserting appended JSON row shape — model on the existing R3/R11 cases already in this file.
  - R1-CtxA (Context-A backlog sourcing — the real production trigger): write a `cortex/backlog/{slug}.md` with `complexity: complex` / `criticality: high` frontmatter, seed `events.log` `simple/medium`, invoke `reconcile-clarify --lifecycle-slug … --backlog-slug …` with **no** explicit `--complexity`/`--criticality` flags, and assert the reduced state becomes `complex/high` — exercising the `_read_backlog_frontmatter` resolution branch rather than the explicit-flag branch. This is the branch the headline bug actually fires through; without it a mis-wired `_read_backlog_frontmatter` call (wrong key, wrong slug, complexity↔criticality swap) would pass every other case.
  - R1-Prec (precedence): when explicit flags AND `--backlog-slug` are both passed, assert the explicit flags win (Context B precedence over backlog read).
  - R1 reduce-agreement: seed `simple/medium`, reconcile `complex/high`, assert `cortex_command.lifecycle.state_cli._reduce_events(events_log) == {"tier":"complex","criticality":"high"}`.
  - R2 both-readers-agree: after reconcile, call `cortex_command.common.read_tier.__wrapped__.cache_clear()` and `read_criticality.__wrapped__.cache_clear()` (lru_cache caveat, common.py:569/640), then assert `read_tier(...)`/`read_criticality(...)` equal `_reduce_events(...)["tier"]`/`["criticality"]` — both `complex`/`high`.
  - R3 idempotency: invoke twice with the same values; `grep -c '"event": "complexity_override"'` identical after the second run and file size unchanged.
  - R4 no-downgrade: pre-populate so the reduced state is `complex/high`, reconcile `simple/medium`, assert reduced state stays `complex/high` and no override row was appended.
  - R5 malformed-line tolerance: write a malformed line alongside a valid seed, reconcile `complex/high`, assert exit 0 and the appropriate override(s) appended without raising.
  - R6 append-only: assert the original `lifecycle_start` line is byte-identical present after reconciliation.
  - R7 provenance: `grep -c '"gate": "clarify_reconcile"'` equals the number of fields actually reconciled in the scenario.
- **Verification**: `.venv/bin/pytest tests/test_refine_module.py -q` — pass if exit 0 and all R1–R7 cases pass.
- **Status**: [ ] pending

### Task 3: Wire `reconcile-clarify` into `skills/refine/SKILL.md` Step 5 + add static wiring guard test
- **Files**: `skills/refine/SKILL.md`, `tests/test_refine_reconcile_wiring.py`
- **What**: Invoke `cortex-refine reconcile-clarify` at Spec-phase entry (Step 5), positioned before the `Read … specify.md and follow it` delegation so it precedes both §3a Orchestrator Review and §3b Critical Review reads; update the §3b adaptation note to record that the lifecycle state is reconciled to the Clarify assessment; add a guard test that asserts both the literal's presence AND its position before the `specify.md` delegation.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Insertion point: between the `## Step 5: Spec Phase` heading (SKILL.md:159) and the `Read … specify.md and follow it` line (SKILL.md:161). Describe both invocation forms — Context A: `cortex-refine reconcile-clarify --lifecycle-slug {lifecycle-slug} --backlog-slug {backlog-filename-slug}` (sources the Clarify values from backlog frontmatter, covering the `resume=spec` path where Step-3 Clarify is skipped); Context B: `cortex-refine reconcile-clarify --lifecycle-slug {lifecycle-slug} --complexity {value} --criticality {value}` (passes in-context Clarify values when no backlog exists). State that the subcommand is idempotent (state-based no-op guard) and safe on resume/double-fire — mirror the phrasing of the Step-2 `emit-lifecycle-start` note (SKILL.md:66).
  - Update the §3b adaptation bullet (SKILL.md:165) to note the lifecycle state has been reconciled to the Clarify assessment at Spec entry, so the §3b tier/criticality read observes the Clarify values rather than the stale seed.
  - No bare-Python import — invoke via the `cortex-refine` console script only (constraint L201). This is a CLI call, not new prose telling the model to emit JSON, satisfying structural-over-prose.
  - Guard test: model on `tests/test_refine_lifecycle_start_wiring.py` (resolves repo root via `git rev-parse --show-toplevel`, reads `skills/refine/SKILL.md`). Assert `"cortex-refine reconcile-clarify"` is present AND `content.index("cortex-refine reconcile-clarify") < content.index("specify.md")` (the §5 delegation line `Read … specify.md and follow it`). The positional assertion makes the ordering guarantee — reconcile runs before the §3a/§3b reads that live inside the delegated `specify.md` — structurally enforced rather than prose-only (per CLAUDE.md "prefer structural separation over prose-only enforcement for sequential gates"), and binds the requirement that reconcile precede §3a (the *earliest* tier/criticality read), not merely §3b.
- **Verification**: `.venv/bin/pytest tests/test_refine_reconcile_wiring.py -q` exits 0 — pass if exit 0 (the test asserts both literal presence AND position before the `specify.md` delegation).
- **Status**: [ ] pending

### Task 4: Add `cortex_command/refine.py` as a producer to the override events-registry rows
- **Files**: `bin/.events-registry.md`
- **What**: Add `cortex_command/refine.py` to the `producers` column (column 4) of the `complexity_override` and `criticality_override` rows so the new Python emitter is documented (no new registry rows — the events are already registered).
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Column order (registry header): `event_name | target | scan_coverage | producers | consumers | category | added_date | deprecation_date | rationale | owner`. Edit the producers cell (4th).
  - `criticality_override` row (bin/.events-registry.md:17): producers currently `skills/lifecycle/SKILL.md` — append `; cortex_command/refine.py`.
  - `complexity_override` row (bin/.events-registry.md:101): producers currently `bin/cortex-complexity-escalator:197` — append `; cortex_command/refine.py`.
  - Follow the existing precedent in the `lifecycle_start` row, which already lists `cortex_command/refine.py:128` as a producer. The events-registry gate scans only `.md` skill/prompt corpus for `"event":` literals (Python emitters are `scan_coverage: manual`), so no scanned literal is introduced and no new row is needed.
- **Verification**: `.venv/bin/pytest tests/test_check_events_registry.py -q` exits 0 AND `grep -c 'cortex_command/refine.py' bin/.events-registry.md` ≥ 3 — pass if both hold (lifecycle_start + two override rows).
- **Status**: [ ] pending

### Task 5: Document the optional `gate` field in the criticality-matrix `criticality_override` shape
- **Files**: `skills/lifecycle/references/criticality-matrix.md`
- **What**: Update the documented `criticality_override` JSON shape (currently `{ts, event, feature, from, to}` at criticality-matrix.md:8) to acknowledge the optional `gate` field this fix emits, AND reconcile the doc's standing "no automated process may override the user's choice" invariant with the new automated Clarify-reconciliation emitter.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: At criticality-matrix.md:5–8, the doc shows the override append shape. Add a note that a Clarify-driven reconciliation also carries `gate: "clarify_reconcile"` (optional; escalator-emitted overrides carry their own gate vocabulary), so consumers that inspect `gate` can distinguish provenance. Separately, the doc asserts (criticality-matrix.md:11) "The user's criticality setting is always final. No automated process … may override the user's choice." Task 1 introduces an automated `criticality_override` producer, so add a one-clause carve-out reconciling the two: the Clarify reconciliation is **not** a user-override — it transcribes the Clarify-determined criticality (which the user can correct *during* Clarify) into lifecycle state, is monotonic-up-only (never lowers), and is `gate`-marked `clarify_reconcile`; an explicit user criticality request still wins via the existing user-override path. Keep the user-final principle intact for explicit user choices; do not change any emission instruction.
- **Verification**: `grep -c 'clarify_reconcile' skills/lifecycle/references/criticality-matrix.md` ≥ 1 — pass if count ≥ 1 (both the `gate`-marker note and the automated-emitter carve-out reference the marker).
- **Status**: [ ] pending

### Task 6: Add end-to-end regression + delegated-path no-op test
- **Files**: `tests/test_refine_reconcile_clarify.py`
- **What**: A new test file with (a) the headline standalone scenario — fresh ticket → seed `simple/medium` → reconcile to `complex/high` → `cortex-lifecycle-state --feature {slug} --field tier` emits `{"tier":"complex"}`; and (b) the delegated-path ordering test — pre-populate `[seed(simple/medium), lifecycle_start(complex/high)]`, invoke reconcile-clarify, assert it no-ops (no new override row appended) and the final reduce is `complex/high`.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Standalone half (R12) — reproduce the headline trigger via Context A: write a fresh `cortex/backlog/{slug}.md` with `complexity: complex` / `criticality: high` frontmatter (simulating the Clarify write-back), seed `events.log` with a `simple/medium` `lifecycle_start` row, invoke `reconcile-clarify --lifecycle-slug … --backlog-slug …` (in-process `main([...])`, **no** explicit tier/criticality flags — values are sourced from the backlog file, the real production path), then read tier via the `cortex-lifecycle-state` CLI surface (`cortex_command.lifecycle.state_cli.main`) and assert `{"tier":"complex"}` (and criticality `high`). This makes the "headline standalone scenario" label accurate — it exercises the Clarify→backlog→reconcile data-flow, not a Context-B shortcut. Pattern reference: `tests/test_complexity_escalator.py` for read-after-write; `tests/test_refine_module.py` for in-process `main` + `monkeypatch.chdir`.
  - Delegated half (R12): write two rows — `lifecycle_start(simple/medium)` then `lifecycle_start(complex/high)` (lifecycle's correct post-Clarify seed, logged before Research). Capture the override-row count, invoke `reconcile-clarify` with `complex/high`, assert the override-row count is unchanged (the no-op guard R3 suppresses it because the reduced state already reads `complex/high` — NOT via supersession) and the final reduce is `complex/high`. The assertion must reflect that reconcile is the would-be most-recent write the no-op guard suppresses, not an authoritative write.
  - Note: live `cortex-refine` reads the installed wheel; in-process `main([...])` / direct module import exercises the source without a wheel reinstall, so prefer the in-process surface (or set `CORTEX_COMMAND_FORCE_SOURCE=1` for any subprocess CLI invocation).
- **Verification**: `.venv/bin/pytest tests/test_refine_reconcile_clarify.py -q` — pass if exit 0 and both scenarios pass.
- **Status**: [ ] pending

### Task 7: Re-verify kept-pauses parity and regenerate the dual-source plugin mirror
- **Files**: `plugins/cortex-core/skills/refine/SKILL.md`, `skills/lifecycle/SKILL.md`, `tests/test_lifecycle_kept_pauses_parity.py`
- **What**: After the Task-3 SKILL.md edit, run `just build-plugin` to regenerate the plugin mirror and stage it; re-verify the refine §4 pick-menu anchor recorded in `skills/lifecycle/SKILL.md`'s kept-pauses inventory — update the inventory anchor and the parity test in lockstep ONLY if the line drifted beyond the ±35-line tolerance.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**:
  - Mirror (R11): `just build-plugin` regenerates `plugins/cortex-core/skills/refine/SKILL.md` from the canonical `skills/refine/SKILL.md`. `cortex_command/` is NOT mirrored (ships via the wheel). Stage the regenerated mirror so the dual-source pre-commit drift hook passes.
  - Kept-pauses (R10): the inventory entry `skills/refine/SKILL.md:166 — refine §4 complexity-value gate pick-menu` and the parity test enforce a ±35-line tolerance. Task 3 inserts ~5–10 lines above line 166, shifting the §4 pick-menu down — expected to stay within tolerance, so no inventory/test edit is anticipated. Only if the drift exceeds ±35 lines: update both `skills/lifecycle/SKILL.md`'s inventory anchor and `tests/test_lifecycle_kept_pauses_parity.py` in lockstep. (`skills/lifecycle/SKILL.md` and the parity test are listed in Files solely to authorize that conditional edit; leave them untouched if parity already passes.)
- **Verification**: `.venv/bin/pytest tests/test_lifecycle_kept_pauses_parity.py -q` exits 0 AND `diff skills/refine/SKILL.md plugins/cortex-core/skills/refine/SKILL.md` is empty — pass if both hold.
- **Status**: [ ] pending

## Risks
- **Reusing `complexity_override`/`criticality_override` overloads their semantics.** The `complexity_override` event also drives the dashboard "complexity override" badge (`parse_complexity_overrides` reads `from`/`to`/`ts`, never `gate`/`schema_version`), so the `gate: "clarify_reconcile"` marker (R7) breaks no consumer and the escalator's `read_effective_tier` is gate-agnostic. The genuinely-new `criticality_override` Python emitter has a narrower blast radius still: there is **no** dashboard `criticality_override` consumer at all — its only readers are `common.py` (reads `.to` only) and `state_cli.py` (reads `.to or .criticality`), both of which honor a `to`-keyed row identically (the R2 both-readers-agree test pins exactly this). Relabeling the dashboard badge is an explicit Non-Requirement (cosmetic follow-up).
- **Tier+criticality scope (Fork A).** The spec chose to reconcile BOTH fields (not tier-only), closing the overnight `_MODEL_MATRIX`/`_EFFORT_MATRIX` demotion in addition to the §3b silent-skip — accepted on Solution-Horizon grounds (refine's purpose is overnight prep; the demotion is named and concrete). The cost is the net-new `criticality_override` Python emitter and the dual-reader `to`-keyed constraint (pinned by R2's both-readers-agree test).
- **Torn-log residual silent-skip — pre-existing, not regressed, tracked as #287.** `state_cli._reduce_events` collapses to null on ANY malformed `events.log` line (diverging from `common.py`'s tolerant skip), so on a torn log the §3a/§3b reads default to `simple` and §3b silently skips *regardless of what reconciliation appends*; the guard's deliberately-tolerant local reduce (Task 1) reads `complex` on that same torn log and correctly suppresses the futile override. This is the one case the fix does NOT close — and critically it is **not a regression**: without this fix a torn log already skips §3b, and with it the torn-log behavior is unchanged. The read-path divergence is already filed as backlog **#287** (`cortex-lifecycle-state collapses to null on any malformed events.log line`); fixing it requires read-path changes affecting every `cortex-lifecycle-state` consumer (much wider blast radius), so per Solution Horizon it is correctly a separate ticket, not bundled here. The Acceptance criterion below is scoped to a well-formed `events.log` accordingly.

## Acceptance
On a **well-formed** `events.log`, a standalone `/cortex-core:refine` on a fresh ticket that Clarify assesses `complex/high` ends Spec-phase entry with `cortex-lifecycle-state --field tier` → `complex` and `--field criticality` → `high`, so §3b critical-review fires (instead of silently skipping on the stale `simple/medium` seed), while a `/cortex-core:lifecycle`-delegated run no-ops the reconciliation (no duplicate override row) because lifecycle's post-Clarify `lifecycle_start` already moved the reduced state. (The torn-log read-path case is out of scope — pre-existing and tracked as #287; see Risks.) All touched pytest files, the events-registry gate, the kept-pauses parity test, and the dual-source mirror diff are green.
