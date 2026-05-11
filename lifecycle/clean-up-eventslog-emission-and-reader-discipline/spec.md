# Specification: Clean up events.log emission and reader discipline

## Problem Statement

The per-feature `events.log` model has accumulated three flavors of write-only waste (dead-event emissions, `clarify_critic` payload bloat, unbounded `escalations.jsonl` re-inline) plus a structural discipline gap that lets the waste continue accumulating. The going-forward token cost is real but secondary; the load-bearing concern is that without an emission-discipline mechanism the next audit will find another batch of dead emissions — the same outcome epic #172's audit produced. This work cleans up the verified-dead emissions, prunes the `clarify_critic` payload via a schema bump, replaces the unbounded `all_entries` re-inline with a read-shape-matched index, and ships a CI-time gate that inverts the cost asymmetry for skill-prompt-driven emissions (which is the path the audit identified as asymmetric: emission is a 1-line skill-prompt edit, but proving-no-consumer is a repo-wide grep). Python emission sites are governed by their existing constraints (`cortex_command/overnight/events.py:90-148` `EVENT_TYPES` tuple with write-time `ValueError` for overnight scope; reviewed Python code for pipeline scope) and are out of scope for the new gate.

## Requirements

### R1. Per-event remediation table applied

The following per-event verdicts are applied to the canonical skill-prompt sources. Auto-mirror regeneration at `plugins/cortex-core/skills/*` is handled by the pre-commit hook.

| Event | Action | Site |
|---|---|---|
| `clarify_critic` | PRUNE-PAYLOAD inline (R3 below) | `skills/refine/references/clarify-critic.md:175` |
| `task_complete` | DELETE emit | `skills/lifecycle/references/implement.md:185-187` |
| `plan_comparison` | KEEP-AS-AUDIT-AFFORDANCE (no change) | `skills/lifecycle/references/plan.md:109-112` |
| `confidence_check` | DELETE emit | `skills/lifecycle/references/specify.md:65,76` |
| `decompose_flag`, `decompose_ack`, `decompose_drop` | DELETE emit | `skills/discovery/references/decompose.md:49-51` |
| `discovery_reference` | DELETE emit | `skills/lifecycle/SKILL.md:220` |
| `implementation_dispatch` | DELETE emit | `skills/lifecycle/references/implement.md:107` |
| `orchestrator_review`, `orchestrator_dispatch_fix`, `orchestrator_escalate` | DELETE emit | `skills/lifecycle/references/orchestrator-review.md:42,72,120` and `skills/discovery/references/orchestrator-review.md:27,55,98` |
| `requirements_updated` | DELETE emit + DELETE consumer scan | emit at `skills/lifecycle/references/review.md:182`; consumer scan at `skills/morning-review/references/walkthrough.md:301-320` (Section 2c) |

**Acceptance criteria**:
- `grep -rn '"event":\s*"confidence_check"' skills/ plugins/cortex-core/skills/` returns no skill-prompt instructional matches (only legacy-tolerance documentation is allowed).
- Same grep for each DELETE-row event name above — no skill-prompt instructional matches.
- `skills/morning-review/references/walkthrough.md` no longer contains the `## Section 2c — Requirements Drift Updates` block at lines 301-320, and the surrounding section numbering is consistent.
- `task_complete` event no longer appears in `skills/lifecycle/references/implement.md`; the plan.md `[x]` update at line 183 remains as the per-task affordance.
- `plan_comparison` emission at `skills/lifecycle/references/plan.md:109-112` and `cortex_command/overnight/prompts/orchestrator-round.md` is preserved verbatim.
- `clarify_critic` emit is preserved at `skills/refine/references/clarify-critic.md:175` but its payload schema follows R3.

### R2. Verified-dead claim re-validated per event before deletion

Each DELETE-row event in R1 must have a fresh repo-wide consumer-grep recorded in the implementation PR description, covering at minimum: `cortex_command/`, `bin/`, `hooks/`, `claude/`, `tests/`, and skill prompts (`skills/`, `plugins/cortex-core/skills/`, `cortex_command/overnight/prompts/`).

**Acceptance criteria**:
- Implementation PR description contains a table mapping each deleted event name to its consumer-grep result (`grep -rn '"<event_name>"' <scope> | wc -l`). The expected result for each is zero non-test, non-emitter, non-legacy-tolerance hits.
- If any DELETE-row event has a real consumer surfaced by the re-grep, that event is reclassified (KEEP-AS-AUDIT-AFFORDANCE or PRUNE-PAYLOAD) and the PR description records the reclassification.

### R3. `clarify_critic` payload pruning via schema v2 → v3 (inline-only)

The `clarify_critic` event row in events.log shrinks from ~1,961 chars avg to ~250 chars by **deleting** the `findings[]` and `dismissals[]` arrays from the row payload and keeping only count fields. No sibling artifact is introduced. The findings prose is not preserved — the audit's "zero non-test Python consumers" finding plus this work's adversarial review found no extant or imminent reader, so preservation would be the "dead-emission with extra steps" anti-pattern.

**Schema v3 event row** (single-line JSONL):
```json
{"schema_version": 3, "ts": "<ISO 8601>", "event": "clarify_critic", "feature": "<slug>", "parent_epic_loaded": <bool>, "findings_count": <int>, "dispositions": {"apply": <int>, "dismiss": <int>, "ask": <int>}, "applied_fixes_count": <int>, "dismissals_count": <int>, "status": "ok"}
```

**Acceptance criteria**:
- `skills/refine/references/clarify-critic.md` is updated so its event-emit template renders the v3 shape above (no `findings`, no `dismissals`, no `applied_fixes` arrays). The v2 example/structural breakdown is replaced by the v3 example.
- The legacy-tolerance table at `clarify-critic.md:162-166` is extended to enumerate v3 (current) plus existing v1/v1+dismissals/v2/YAML-block tolerated indefinitely. v3 is listed as the canonical write shape; all earlier shapes are read-tolerated forever.
- `tests/test_clarify_critic_alignment_integration.py:593-669` continues to pass unchanged. The existing `detections >= 1` invariant (line 666-669) is the gate; no new sibling-artifact assertion is added.
- For each archived v2 event in `lifecycle/archive/`, no rewrite occurs (archives are immutable). Readers tolerate v2 indefinitely per the legacy-tolerance extension.
- **Dual-source mirror regeneration verified**: the implementation PR's pre-commit hook output (or CI-equivalent) shows the regenerated `plugins/cortex-core/skills/refine/references/clarify-critic.md` content matches the canonical `skills/refine/references/clarify-critic.md`. If the verification is not surfaceable in CI, a one-line `just check-mirror-drift` or `git diff` on the mirrored file is recorded in the PR description after running the pre-commit hook locally.

### R4. `escalations.jsonl` re-inline bounded via read-shape index

`cortex_command/overnight/orchestrator_context.py:60-110` no longer emits `all_entries`. Instead, it emits `unresolved` (preserved as-is) and `prior_resolutions_by_feature: dict[str, list[dict]]` keyed by feature slug, containing only entries with `type == "resolution"`. The `_EXPECTED_SCHEMA_VERSION` constant at line 20 bumps from 1 to 2. **The inline payload literal that sets `"schema_version"` in the returned dict (currently at `orchestrator_context.py:105`) bumps in lockstep to 2.**

`cortex_command/overnight/prompts/orchestrator-round.md:54-61` is updated to read `ctx["escalations"]["prior_resolutions_by_feature"].get(entry["feature"], [])` instead of filtering `all_entries`.

**Acceptance criteria**:
- `cortex_command/overnight/orchestrator_context.py`: `aggregate_round_context` returns a dict where `escalations` contains only `unresolved` and `prior_resolutions_by_feature` keys; `all_entries` does not appear.
- `_EXPECTED_SCHEMA_VERSION` in `orchestrator_context.py` equals `2`. Drift-guard raise message is updated to reference the new shape.
- **The inline `"schema_version"` field of the dict returned from `aggregate_round_context` equals 2**, matching `_EXPECTED_SCHEMA_VERSION`. The strict-equality guard at line 115-116 thus passes under the new shape and fails under any drift. Both constants must move together — a test (`tests/test_orchestrator_context_schema_roundtrip.py` or equivalent) asserts that calling `aggregate_round_context` on a fixture session does not raise `RuntimeError("schema_version drift")`.
- `cortex_command/overnight/prompts/orchestrator-round.md:54-61` uses the precomputed dict via `.get(entry["feature"], [])`; no inline filter over `all_entries` remains.
- The producer change (`orchestrator_context.py`) and the consumer prompt change (`orchestrator-round.md`) ship in the same PR. PR description notes the deployment-atomicity risk (Edge Cases section below covers the mitigation contract).
- `cortex_command/overnight/tests/` updated to assert the new shape and the schema_version bump (the round-trip test above plus shape-of-return assertions).
- Per-feature dict-key collisions are not a concern: `escalations.jsonl` is per-session (`lifecycle/sessions/{session_id}/escalations.jsonl`); the aggregator reads only the current session's file (verifiable at `cortex_command/overnight/orchestrator_context.py:60`).

### R5. CI-time emission-registry gate (`bin/cortex-check-events-registry`) — skill-prompt scope only

A new stdlib-only Python script at `bin/cortex-check-events-registry`, modeled on `bin/cortex-check-parity`, statically validates that every emitted event name **in canonical skill-prompt sources** is declared in a registry file with a documented consumer. The script ships with the `cortex-log-invocation` shim in its first 50 lines per `.githooks/pre-commit` Phase 1.6.

**Scope rationale**: the audit's diagnosed asymmetry — "emission is cheap (1-line skill-prompt edit), proving-no-consumer is expensive (repo-wide grep)" — applies specifically to skill-prompt JSONL-emit instructions, which Claude executes verbatim at runtime. Python emission sites are governed by their existing constraints (`cortex_command/overnight/events.py:90-148` `EVENT_TYPES` tuple's write-time `ValueError` enforcement for overnight scope; reviewed code paths for pipeline scope; `bin/cortex-*` scripts are reviewed at PR time). Extending the static gate to Python's call-shape variety (bare-constant positional args, dict-built-incrementally, kwargs-style) would require AST-walking with constant-resolution and would not catch the dominant asymmetric pattern any better than the existing Python review process. The gate's promise is therefore narrowed to skill-prompt sources; Python emissions are out of scope for automatic detection but are documented manually in the registry for human reference.

**Registry file**: `bin/.events-registry.md`. (Chosen over `events/events-registry.md` for direct precedent fit with `bin/.parity-exceptions.md`.)

**Registry schema** (markdown table; one row per event name):

| Column | Required | Description |
|---|---|---|
| `event_name` | yes | The event-name string literal as it appears in emissions |
| `target` | yes | `per-feature-events-log` or `overnight-events-log` |
| `scan_coverage` | yes | `gate-enforced` (skill-prompt-driven; gate detects new emissions) or `manual` (Python or shell emissions; gate does NOT auto-detect; documented for reference) |
| `producers` | yes | `;`-separated list of `path:line` pointers to emission sites |
| `consumers` | yes | `;`-separated list of `path:line` pointers to read sites (skill prompts, Python, shell, tests count; tests-only carries a `tests-only` annotation; `human-skim` allowed for audit-affordance rows) |
| `category` | yes | `live` \| `audit-affordance` \| `deprecated-pending-removal` |
| `added_date` | yes | YYYY-MM-DD |
| `deprecation_date` | conditional | YYYY-MM-DD; required when `category=deprecated-pending-removal` |
| `rationale` | conditional | ≥30 chars; required when `category != live` |
| `owner` | conditional | Required when `category=deprecated-pending-removal`; identifies who has authority to bump `deprecation_date` |

**Scan surface** (narrowed for gate enforcement):
- `skills/**/*.md` (canonical skill-prompt sources)
- `cortex_command/overnight/prompts/*.md` (orchestrator-round and similar)

**Out of scan surface** (`scan_coverage: manual` rows only):
- `cortex_command/**/*.py` — Python emissions; governed by review, by `events.py:EVENT_TYPES` write-time enforcement (overnight scope), and by manual registry entry.
- `bin/cortex-*` Python scripts — same.
- `hooks/`, `claude/` shell scripts — none currently emit events; if any do in the future, they get `manual` rows.

**Acceptance criteria — gate behavior (pre-commit critical path)**:
- `bin/cortex-check-events-registry` exists, is executable, and contains the `cortex-log-invocation` shim in its first 50 lines.
- Running `bin/cortex-check-events-registry --staged` (the pre-commit invocation) scans only staged files within the scan surface above. If a staged skill-prompt or orchestrator-prompt file contains an emission whose `event_name` is not present in `bin/.events-registry.md`, the script exits non-zero with a positive-routing error message naming the file, line, event_name, and remediation step (add a row to `bin/.events-registry.md`).
- The gate does NOT enforce `deprecation_date` on the pre-commit path. Stale rows do not block unrelated commits.
- **Fails closed on missing registry**: if `bin/.events-registry.md` does not exist when the gate runs, the script exits non-zero with a `MISSING_REGISTRY` error message in positive-routing form (e.g., "Create `bin/.events-registry.md` to enable the events-registry gate. See `docs/internals/events-registry.md` for the schema."). This overrides the `cortex-check-parity` precedent which fails open on missing allowlist.
- Error messages: positive-routing form. No "you MUST" phrasing. Each error message identifies the offending file:line and the remediation action.
- The script is referenced from an in-scope `SKILL.md` / docs / hooks / justfile / tests reference per the parity contract — `justfile` recipe `check-events-registry` + `tests/test_check_events_registry.py`.

**Acceptance criteria — audit recipe (off critical path)**:
- A separate `just check-events-registry-audit` recipe invokes `bin/cortex-check-events-registry --audit`. The `--audit` mode runs a registry-wide scan that fires the `deprecation_date` check (any row with `category=deprecated-pending-removal` and `deprecation_date in the past` is an error) and emits a structured report.
- The audit recipe is intended for manual or scheduled invocation (e.g., morning-review surface, weekly cron, or operator on demand). It is NOT wired into `.githooks/pre-commit`.
- The audit recipe's output names the row's `owner` field for each stale row — i.e., who has bump authority. If `owner` is empty on a `deprecated-pending-removal` row, that itself is a violation surfaced at audit time.
- `--audit` does not modify the registry; it only reports.

**Acceptance criteria — self-tests**:
- At least 8 self-test cases covering: unregistered skill-prompt name (error, pre-commit path), registered name with valid consumer (pass), audit-mode finding a stale deprecation date (error, audit path only — NOT in pre-commit path), pre-commit path NOT firing the date check (pass even with stale rows present), audit-mode finding `deprecated-pending-removal` row missing `owner` (error), missing registry file (error with `MISSING_REGISTRY`), category-required-but-missing rationale (error), pre-commit path passing a commit unrelated to skill prompts even with stale rows present (pass).

### R6. Pre-commit wiring for the new gate

`.githooks/pre-commit` gains a new "Phase 1.7 — Events-registry enforcement" between Phase 1.6 (log-invocation shim) and Phase 2 (dual-source drift). The phase triggers narrowly on staged-paths that the gate can actually enforce.

**Acceptance criteria**:
- `.githooks/pre-commit` contains a Phase 1.7 block invoking `just check-events-registry --staged` (or equivalent direct invocation of `bin/cortex-check-events-registry --staged`).
- Phase 1.7 triggers when any of the following match staged paths: `skills/*`, `cortex_command/overnight/prompts/*`, `bin/cortex-check-events-registry`, `bin/.events-registry.md`. Crucially, the trigger does **NOT** include `cortex_command/**/*.py` — commits to Python files do not invoke this phase, so unrelated backend work is never blocked by a stale registry row.
- `justfile` gains two recipes: `check-events-registry` (pre-commit-equivalent invocation, `--staged` mode) and `check-events-registry-audit` (`--audit` mode for off-critical-path deprecation review).
- The phase's failure output points the committer at `bin/.events-registry.md` and the script's error message; no `MUST`/`CRITICAL`/`REQUIRED` phrasing.

### R7. Initial registry population

`bin/.events-registry.md` is populated as part of the implementation PR with rows covering:
- **All live events emitted by skill prompts and orchestrator templates** (`scan_coverage: gate-enforced`): `phase_transition`, `feature_complete`, `lifecycle_start`, `batch_dispatch`, `review_verdict`, `dispatch_complete`, `criticality_override`, `clarify_critic` (post-R3), `plan_comparison`.
- **All session-scope events from `cortex_command/overnight/events.py:90-148` `EVENT_TYPES` tuple** (`scan_coverage: manual`, `target: overnight-events-log`): each constant in the tuple gets a row. `producers` may point at `cortex_command/overnight/events.py:EVENT_TYPES` collectively; `consumers` enumerates the Python consumer sites identified in research.md's Codebase Analysis.
- **Python emission sites in `cortex_command/pipeline/` and `bin/cortex-*`** (`scan_coverage: manual`): the events identified in research.md's adversarial review (e.g., `complexity_override` from `bin/cortex-complexity-escalator`, `merge_*` events from `cortex_command/pipeline/merge.py`, `dispatch_*` events from `cortex_command/pipeline/dispatch.py`, `REPAIR_AGENT_*` from `cortex_command/pipeline/conflict.py`) each get a row with explicit consumer pointers.
- **All `deprecated-pending-removal` events that this work's deletion sweep cuts but in-flight features may still emit**. The `deprecation_date` for these is set to **today + 30 days** (not 14) to align with the repo's observed 25-day batch cadence. Each row has an `owner` field naming the person responsible for the cleanup follow-up PR.

**Acceptance criteria**:
- `bin/.events-registry.md` exists with at least one row per event name emitted in the codebase after R1 deletions.
- Every row has a non-empty `consumers` field (audit-affordance rows may use the literal value `human-skim` with a ≥30-char rationale).
- Every `deprecated-pending-removal` row has a non-empty `owner` field.
- Running `bin/cortex-check-events-registry --staged` (pre-commit mode) on the post-implementation tree exits 0 against the test fixtures and a clean working tree.
- Running `bin/cortex-check-events-registry --audit` (audit mode) on the post-implementation tree exits 0 (no rows have stale deprecation dates at implementation time).

### R8. CHANGELOG.md and docs updates

Per `requirements/project.md:23` Workflow Trimming: "Retired surfaces are documented in `CHANGELOG.md` with replacement entry points and any user-side cleanup paths."

**Acceptance criteria**:
- `CHANGELOG.md` contains an entry summarizing the events removed (R1 DELETE rows), the `clarify_critic` schema bump (R3), the orchestrator_context schema bump (R4), and the new gate (R5/R6).
- A new doc `docs/internals/events-registry.md` describes the registry schema, the `gate-enforced` vs `manual` scope split, the pre-commit-vs-audit two-mode design, the deprecation lifecycle, and the day-15 / stale-row recovery path (the audit recipe surfaces stale rows; the row's `owner` field identifies who runs the cleanup PR; rows can be bumped with explicit rationale-update for an additional cycle). Linked from `docs/internals/pipeline.md` and `docs/overnight-operations.md` where they discuss events.log.
- No user-side cleanup paths required (the deletions affect emission only; existing events.log rows remain parseable per Tolerant-Reader semantics).

## Non-Requirements

- **No consumer-side runtime drift detector** (e.g., a `cortex-validate-events` script that reads events.log files and warns on unknown names). Acknowledged as a complementary gate; deferred. Open Decisions §D1.
- **No automatic detection of new Python emission sites by the CI gate.** Python sites are governed by review, by the existing `EVENT_TYPES` write-time enforcement (overnight scope), and by manual registry entry for documentation. Extending the static gate to Python's call-shape variety is out of scope; the audit's diagnosed asymmetry is skill-prompt-specific.
- **No retroactive rewrite of `lifecycle/archive/`** events.log files. Archives are immutable; legacy-tolerance handles old shapes.
- **No 2-tier events.log split** (events.log spine + events-detail.log). Out of scope per the ticket and parent epic #172.
- **No OpenTelemetry-style structured tracing model**. Out of scope.
- **No changes to live-consumer parsing logic** (`extract_feature_metrics`, `parse_feature_events`, statusline, etc.) beyond the strictly required v3-awareness for `clarify_critic` row readers (none currently exist in non-test code).
- **No runtime emission registry** for the skill-prompt path (i.e., no Python helper that rejects unregistered names at emit time). The skill-prompt-driven emission path has no central emitter. The CI-time gate at PR time is the discipline mechanism.
- **No CODEOWNERS protection on `bin/.events-registry.md`** for v1. The allowlist-as-mutation-target concern is acknowledged; deferred.
- **No new policy entry in `CLAUDE.md`**. Gate error messages use positive-routing form.
- **No `clarify-critic-findings.json` sibling artifact**. The R3 inline-only pruning is sufficient for the row-shrink target; preservation of findings prose without a declared reader was rejected as the "dead-emission with extra steps" anti-pattern.
- **No pre-commit-path `deprecation_date` enforcement**. Stale rows surface via the `--audit` recipe, not the critical-path commit gate. Day-15 scenarios do not block unrelated work.

## Edge Cases

- **In-flight overnight feature emitting a deleted event mid-session**: the deletion is on the skill-prompt source. New subagent dispatches read the updated prompt and don't emit the deleted name. Any rows already written to the in-flight feature's events.log before the PR merge remain parseable by all consumers (Tolerant-Reader semantics; unknown event names are silently skipped). No reader breaks.
- **In-flight feature whose dispatch was spawned before the PR merge but completes after**: same. Mixed events.log parses cleanly.
- **A subagent invents a new event name not in the registry**: the CI gate catches the new name when the introducing commit is created (skill-prompt static check). The gate does not catch runtime invention by Claude deviating from a prompt — D1 (consumer-side detector) is the deferred follow-up.
- **Registry file deleted or malformed during a commit**: CI gate fails closed with `MISSING_REGISTRY` or malformed-row error; commit is rejected. No silent gate lapse.
- **Stale `deprecation_date` row** (date in the past, event still emitted): the pre-commit gate does NOT fire on this. The `--audit` recipe surfaces the row at morning-review or on-demand. The row's `owner` field identifies who runs the cleanup follow-up PR. If the cleanup is delayed, the owner may bump the date with a rationale update for an additional cycle; rows that have been bumped twice surface a stronger warning on the audit recipe.
- **`clarify_critic` row in events.log under v3**: the row contains only counts. No sibling file is written; the existing `detections >= 1` test gate continues to pass on the row presence.
- **Schema v3 reader meets v2 row in mixed events.log**: legacy-tolerance table extension makes v2 readable indefinitely.
- **Producer/consumer schema drift for R4 (deployment atomicity)**: the project ships as a versioned wheel installed via `uv tool install git+<url>@<tag>`. A user upgrading the CLI between overnight rounds, or an orchestrator subagent spawned with a stale prompt against new Python (or vice versa), can desynchronize the producer dict shape from the consumer prompt. The strict-equality guard at `orchestrator_context.py:115-116` will raise `RuntimeError` on the desync. Mitigation contract: (a) the implementation PR's CHANGELOG entry advises operators not to upgrade mid-session, (b) the runner's existing pre-install in-flight guard (`cortex_command.install_guard.check_in_flight_install`, per `requirements/observability.md`) blocks the upgrade path when an overnight session is detected — this is the existing structural defense, (c) for the (rare) split-revert case where the producer is reverted but the consumer prompt is not, the consumer's `.get(entry["feature"], [])` fallback at the per-feature key level prevents a KeyError on missing entries but does NOT prevent a KeyError on the top-level `prior_resolutions_by_feature` key if the producer reverts to emitting `all_entries` instead. The R4 PR description documents this as a coupled-revert hazard requiring both files to revert together. (Programmatic enforcement of the coupling is not in scope.)
- **Day-15 stale row with unrelated commit**: pre-commit gate does NOT block. Commit proceeds. Audit recipe surfaces the stale row at next morning-review or on-demand run; cleanup is scheduled as separate work.

## Changes to Existing Behavior

- **MODIFIED**: `clarify_critic` event payload shape — `findings[]`, `dismissals[]`, and `applied_fixes[]` arrays removed from the row; replaced by `findings_count`, `dismissals_count`, `applied_fixes_count` inline. `schema_version` bumps from 2 to 3.
- **MODIFIED**: `aggregate_round_context` payload shape — `escalations.all_entries` removed; `escalations.prior_resolutions_by_feature` added. `_EXPECTED_SCHEMA_VERSION` bumps from 1 to 2 AND the inline payload literal at `orchestrator_context.py:105` bumps from 1 to 2 in lockstep.
- **MODIFIED**: `cortex_command/overnight/prompts/orchestrator-round.md:54-61` — consumes the precomputed dict via `.get(entry["feature"], [])` instead of filtering `all_entries`.
- **MODIFIED**: `.githooks/pre-commit` — adds Phase 1.7 events-registry enforcement, scoped narrowly (no `cortex_command/**/*.py` trigger).
- **MODIFIED**: `skills/refine/references/clarify-critic.md` — v3 event-row template (no sibling file), extended legacy-tolerance table.
- **REMOVED**: 11 dead-event emission instructions in skill prompts (see R1).
- **REMOVED**: `skills/morning-review/references/walkthrough.md` Section 2c (`requirements_updated` consumer scan, lines 301-320).
- **REMOVED**: `task_complete` emission at `skills/lifecycle/references/implement.md:185-187`.
- **ADDED**: `bin/cortex-check-events-registry` static-analysis gate (skill-prompt scope; two modes: `--staged` for pre-commit, `--audit` for off-critical-path deprecation review).
- **ADDED**: `bin/.events-registry.md` registry file (initial population per R7).
- **ADDED**: `justfile` recipes `check-events-registry` and `check-events-registry-audit`.
- **ADDED**: `docs/internals/events-registry.md` documentation.
- **ADDED**: `tests/test_check_events_registry.py` self-test surface for the new gate.
- **ADDED**: `tests/test_orchestrator_context_schema_roundtrip.py` (or equivalent) — round-trip test ensuring the `_EXPECTED_SCHEMA_VERSION` constant and the inline payload literal stay in lockstep.

## Technical Constraints

- **Append-only JSONL log shape preserved**: all changes maintain JSONL one-object-per-line format with atomic write semantics (`tempfile + os.replace()`).
- **`jq`/`grep`-friendliness preserved**: schema v3 rows remain single-line JSONL parseable by `jq`.
- **`stdlib-only` for `bin/cortex-*` scripts** per the parity-linter precedent. `bin/cortex-check-events-registry` may not import third-party packages.
- **`cortex-log-invocation` shim** required in `bin/cortex-check-events-registry`'s first 50 lines per `.githooks/pre-commit` Phase 1.6.
- **Dual-source enforcement**: all skill-prompt edits land in canonical sources (`skills/`); the pre-commit hook regenerates the `plugins/cortex-core/skills/*` mirror automatically. R3 acceptance includes mirror-regen verification.
- **Strict-equality schema guard at `orchestrator_context.py:115-116`** is a hard equality check between the inline payload literal and `_EXPECTED_SCHEMA_VERSION`. Both must bump in lockstep (R4 acceptance enforces via round-trip test).
- **No new `CLAUDE.md` policy entry**: gate error messages are positive-routing form.
- **Mid-session safety preserved**: the deletion of dead-event emission instructions is read-side-safe because Tolerant-Reader semantics in all consumers (Python, shell, skill prompts) skip unknown event names without erroring.
- **Verification-grep mandate (R2)**: each DELETE event must have a fresh repo-wide consumer-grep recorded in the implementation PR description. Tests, hooks, shell scripts, and skill prompts are included in the grep scope.
- **Pre-commit critical-path discipline**: the events-registry gate's pre-commit invocation enforces only unregistered-emission detection in staged skill-prompt files. Time-based checks (deprecation date staleness) are off the critical path in the `--audit` recipe — a deliberate choice to avoid the day-15 tripwire pattern.
- **Indefinite legacy-tolerance** for `clarify_critic` event row shapes: v1, v1+dismissals, v2, v3, and YAML-block all parseable by future readers. No write-side cutoff date.

## Open Decisions

- **D1: Consumer-side runtime drift detector (out of scope for v1, but acknowledged)**: a `cortex-validate-events` script that reads emitted events.log files and warns on unknown event names would close the gap that the producer-side static gate cannot catch (Claude deviating from a prompt at runtime). Deferred because it requires per-session-write hook integration with the morning-review path. Cannot be resolved at spec time because the morning-review hook's runtime semantics need to be re-derived from current code.
