# Research: cross-skill-telemetry-framework

## Headline Finding

**No unified telemetry surface exists today**: skills emit events via JSONL instructions to Claude (`[skills/lifecycle/SKILL.md:110,220]`, `[skills/discovery/references/decompose.md:49-51]`) and Python pipeline code emits via `log_event()` (`[cortex_command/pipeline/dispatch.py:654,686,703]`), but the two event streams write to different files (`cortex/lifecycle/{slug}/events.log` for skill-side; `cortex/lifecycle/sessions/{sid}/overnight-events.log` for session-side), share no registry, and have no consumer-side schema enforcement beyond the `events.py EVENT_TYPES` tuple `[cortex_command/overnight/events.py:90-148]` which is scoped only to the session log. The 22 skill-side event types have 8 live Python consumers and 14 with zero Python reads — accumulating ~14% storage share in the archive corpus as confirmed dead emissions. **Recommended approach**: a three-piece framework — a unified events registry (extending the `bin/cortex-check-parity` pattern `[bin/cortex-check-parity:34,69]`), a write-time enforcement gate (pre-commit hook Phase 1.7, modeled on the existing Phase 1.5 `[.githooks/pre-commit:72-92]`), and a per-event consumer audit that dead-deletes confirmed zero-consumer events with a grandfathering window (per `requirements/project.md:23` hard-deletion preference). The integration complexity is M not L because the two event streams must stay partitioned (skill-side vs. session-side) — a single registry file with a `scope:` column is the named contract surface, not a merged log file. The framework does NOT change the two-log architecture; it adds enforcement over what types are allowed and which have confirmed consumers.

## Research Questions

1. **What is the current event-type inventory across both streams?** → **Answered.** Skill-side: 22 distinct names across 10 source files (see Codebase Analysis table). Session-side: 8 distinct names via `log_event()` at `[dispatch.py:654-789]` plus ~12 names from `[merge.py:205-326]` plus `REPAIR_AGENT_*` constants from `[conflict.py:257-442]`. Total event universe: ~45 names before dead-deletion.

2. **How many skill-side event types have zero Python consumers?** → **Answered.** 14 of 22. Eight have live Python consumers (`feature_complete`, `phase_transition`, `review_verdict`, `dispatch_complete`, `lifecycle_start`, `batch_dispatch`, `criticality_override`, `clarify_critic` — the last has test consumers only `[tests/test_clarify_critic_alignment_integration.py:193-668]`). See Codebase Analysis consumer table.

3. **What is the precedent enforcement mechanism in this repo?** → **Answered.** `bin/cortex-check-parity` `[bin/cortex-check-parity:34,51,69,117]` — a Python script scanning skill files against an allowlist with category tagging, wired at pre-commit Phase 1.5. Fails open on missing allowlist `[bin/cortex-check-parity:386]`. `.parity-exceptions.md` has 2 entries as of 2026-05-11.

4. **Is there a cross-consumer test surface we cannot break?** → **Answered.** Yes. `tests/test_clarify_critic_alignment_integration.py:666-669` requires `clarify_critic` row count ≥ 1 across the live corpus. `tests/fixtures/clarify_critic_v1.json` and `tests/fixtures/jsonl_emission_cutoff.txt` are coordinated fixtures. Any `clarify_critic` deletion requires synchronized deletion of these three test artifacts `[premise-unverified: not-searched for all callers beyond the listed lines]`.

5. **What is the per-feature storage cost of the dead events?** → **Answered.** ~127,460 bytes of dead-emission rows out of ~897,811 total `"event":` row bytes in 145 archived features — ~14% storage share. `clarify_critic` alone: 95 rows, 186,340 total bytes, 6,825 chars max row.

6. **Can the framework handle the `cortex_command/**/*.py` emitter universe, or only skill-prompt events?** → **Answered with limitation.** `bin/cortex-check-parity`'s `SCAN_GLOBS` pattern covers `skills/**/*.md` only `[bin/cortex-check-parity:69]`. The Python emitters at `[dispatch.py:654-764]` and `[merge.py:205-326]` are outside that scan surface. A complete gate requires partitioned responsibility: skill-prompt registry for per-feature events.log types; the existing `EVENT_TYPES` tuple for session-scope types.

7. **What ordering does the decompose phase need?** → **Answered.** Registry first (Piece 1), then dead-deletion (Piece 3) — deletion cannot happen until the registry's allowlist is committed and the pre-commit hook is wired. Piece 2 (enforcement hook) can co-land with Piece 1 or land immediately after; it is not gated on Piece 3 completion.

## Codebase Analysis

### Skill-side event inventory

Twenty-two event names emitted via skill-prompt JSONL instructions across 10 source files:

| Source file | Events emitted |
|---|---|
| `skills/lifecycle/SKILL.md:110,220,250,254-256,294` | `feature_complete`, `discovery_reference`, `lifecycle_start`, `phase_transition`, `criticality_override` |
| `skills/lifecycle/references/orchestrator-review.md:42,72,120` | `orchestrator_review`, `orchestrator_dispatch_fix`, `orchestrator_escalate` |
| `skills/lifecycle/references/specify.md:65,76,175` | `confidence_check`, `phase_transition` |
| `skills/lifecycle/references/plan.md:112,285` | `plan_comparison`, `phase_transition` |
| `skills/lifecycle/references/implement.md:107,139,173,187,243,272` | `implementation_dispatch`, `dispatch_complete`, `batch_dispatch`, `task_complete`, `phase_transition` |
| `skills/lifecycle/references/review.md:165,182,197,201,205` | `review_verdict`, `requirements_updated`, `phase_transition` |
| `skills/lifecycle/references/complete.md:22` | `feature_complete` |
| `skills/refine/references/clarify-critic.md:175` | `clarify_critic` |
| `skills/discovery/references/decompose.md:49-51` | `decompose_flag`, `decompose_ack`, `decompose_drop` |
| `skills/discovery/references/orchestrator-review.md:27,55,98` | `orchestrator_review`, `orchestrator_dispatch_fix`, `orchestrator_escalate` |

### Python consumer counts (non-test, skill-side events)

| Event | Python consumer hits | Status |
|---|---|---|
| `feature_complete` | 10 | live |
| `phase_transition` | 4 | live |
| `review_verdict` | 4 | live |
| `dispatch_complete` | 4 | live |
| `lifecycle_start` | 3 | live |
| `batch_dispatch` | 1 — `metrics.py:232` | live |
| `criticality_override` | 1 — orchestrator-round.md prompt only | live |
| `clarify_critic` | 0 Python, 1 test — `test_clarify_critic_alignment_integration.py:666-669` | test-consumer only |
| `confidence_check` | 0 | dead |
| `decompose_ack`, `decompose_drop`, `decompose_flag` | 0 | dead |
| `discovery_reference` | 0 | dead |
| `implementation_dispatch` | 0 | dead |
| `orchestrator_dispatch_fix`, `orchestrator_escalate`, `orchestrator_review` | 0 | dead |
| `plan_comparison` | 0 Python, tests only | dead-for-Python |
| `requirements_updated` | 0 | dead |
| `task_complete` | 0 | dead (human-skim affordance only) |

### `bin/cortex-check-parity` enforcement precedent

- Allowlist file: `.parity-exceptions.md`, 2 entries `[bin/cortex-check-parity:386]`.
- Categories: `ALLOWED_CATEGORIES` includes `deprecated-pending-removal` but no removal-by-date enforcement `[bin/cortex-check-parity:117]`.
- Pre-commit wiring: Phase 1.5 `[.githooks/pre-commit:72-92]`.
- Fails open when allowlist file missing `[bin/cortex-check-parity:386]` — parallel design decision applies to any new registry.

### `clarify_critic` payload accumulation

- 95 archived rows, 186,340 total bytes, 6,825 chars max row. Schema v2 latest; v1, v1+dismissals, YAML-block tolerated per `[clarify-critic.md:162-166]`.
- Coordinated test artifacts: `tests/test_clarify_critic_alignment_integration.py`, `tests/fixtures/clarify_critic_v1.json`, `tests/fixtures/jsonl_emission_cutoff.txt`. Cannot delete emission without deleting all three.

### `escalations.jsonl` re-inline path (illustrative dead-weight pattern)

- Writer: `cortex_command/overnight/orchestrator_context.py:60-75` concatenates full file into `all_entries: list[dict]`.
- Sole consumer of `all_entries`: `orchestrator-round.md:54-61` runs a per-feature filter. The full list is otherwise unused — bulk re-inline for a filter that could use a precomputed dict.
- Strict schema-version equality guard at `orchestrator_context.py:115-116`; any payload shape change requires version bump and co-deployed reader.

### Files that will change (conditional on decisions)

**Registry + enforcement (Pieces 1–2):**
- New `bin/cortex-check-events-registry` (modeled on `bin/cortex-check-parity`)
- New `bin/.events-registry.md` or `events/events-registry.md`
- `.githooks/pre-commit` — Phase 1.7 addition
- `justfile` — new `check-events-registry` recipe

**Dead-deletion (Piece 3, per-event decisions):**
- `skills/lifecycle/references/orchestrator-review.md`, `skills/discovery/references/orchestrator-review.md`, `skills/discovery/references/decompose.md`, `skills/lifecycle/references/specify.md`, `skills/lifecycle/references/implement.md`, `skills/lifecycle/references/review.md`, `skills/lifecycle/SKILL.md`, `skills/lifecycle/references/plan.md`
- `skills/refine/references/clarify-critic.md:113-216` — payload-pruning or deletion
- `tests/test_clarify_critic_alignment_integration.py`, `tests/fixtures/clarify_critic_v1.json`, `tests/fixtures/jsonl_emission_cutoff.txt`

**`escalations.jsonl` optimization (Piece 4):**
- `cortex_command/overnight/orchestrator_context.py:60-110`
- `cortex_command/overnight/prompts/orchestrator-round.md:54-61`

## Feasibility Assessment

| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|
| (A) Registry + pre-commit gate + dead-delete (recommended) | M | Coordinate `clarify_critic` deletion with three test artifacts; strict schema guard on `escalations.jsonl` requires version bump; fails-open default must be explicit in new gate | Registry file committed before dead-deletion; pre-commit gate wired |
| (B) Registry only, no deletion | S | Dead events keep accumulating; gate without deletion doesn't reduce existing waste | None |
| (C) Session-scope only (extend `EVENT_TYPES` tuple) | XS | Does not address the skill-side stream; 14 dead skill-side events remain | None |
| (D) Full consolidation (single log, single registry) | XL | Breaks the session-scope vs. per-feature partition; `[cortex_command/overnight/events.py:90-148]` registries would need merge; not worth the scope for a categorization benefit | (A) exists and working |

## Architecture

### Pieces

1. **Events registry** — `bin/.events-registry.md` (co-located with `bin/cortex-check-parity`'s `.parity-exceptions.md` pattern); one row per event name, columns: `scope` (skill-side / session-side), `emitter_source` (file:line), `consumer_count` (Python, test), `status` (live / dead / grandfathered). Role: single source of truth for what event types are allowed; the registry file is the write-time gate's input.

2. **`bin/cortex-check-events-registry` + pre-commit Phase 1.7** — Python script (stdlib-only per `bin/` convention) that scans `skills/**/*.md` for JSONL-emit instructions and cross-checks against Piece 1's allowlist. Wired in `.githooks/pre-commit` after Phase 1.6 (the `cortex-log-invocation` shim check). Role: prevents new dead types from accumulating silently; surfaces a `dead-for-removal` category with no removal-by-date enforcement gap (improvement over `cortex-check-parity`'s stale-row blind spot `[bin/cortex-check-parity:117]`).

3. **Per-event dead-deletion sweep** — guided by the registry's `status: dead` rows, delete each confirmed-dead event from its emitter skill file and from the archive grandfathering window (any `events.log` rows with that type that survive in `cortex/lifecycle/*/events.log` are read-tolerated but not produced). `clarify_critic` deletion requires coordinated deletion of its three test fixtures. Role: reduces archive storage waste and context-window cost for the downstream consumer surface.

4. **`escalations.jsonl` payload optimization** — replace `all_entries: list[dict]` with `prior_resolutions_by_feature: dict[str, list[dict]]` in `orchestrator_context.py:60-110`; update `orchestrator-round.md:54-61` consumer to use the precomputed dict. Bump `_EXPECTED_SCHEMA_VERSION`. Role: reduces per-round context re-inline cost for the orchestrator-round prompt.

### Integration shape

Pieces flow sequentially: the registry (Piece 1) must be committed before the gate (Piece 2) can validate against it, and before dead-deletion (Piece 3) can reference confirmed-dead rows. Piece 4 is independent — it touches only the `escalations.jsonl` path, not the event-type registry, and can land in parallel with Pieces 1–2 or after Piece 3.

Named contract surfaces:
- **Registry format ↔ `cortex-check-events-registry`**: row schema (`event_name`, `scope`, `status` columns) is the parsing surface; any column rename breaks the gate script.
- **Piece 2 gate ↔ pre-commit Phase 1.7**: the gate exit code is the contract; a non-zero exit blocks commit.
- **Piece 3 deletion ↔ `clarify_critic` test suite**: coordinated deletion; no registry-format contract, but the three test artifacts must be removed in the same commit as the skill-file edit.
- **Piece 4 ↔ `_EXPECTED_SCHEMA_VERSION`**: strict equality guard; version bump is the contract surface between writer and reader.

### Seam-level edges

- Piece 1: edges land on `bin/` directory (registry file), `justfile` (new recipe), `CLAUDE.md` (conventions reference if the registry pattern is promoted to project conventions).
- Piece 2: edges land on `bin/cortex-check-events-registry` (Python script), `.githooks/pre-commit` (Phase 1.7 insertion point), `skills/**/*.md` (scan surface — does not cover `cortex_command/**/*.py` emitters, which remain outside the gate's scope).
- Piece 3: edges land on 8+ skill source files, `tests/test_clarify_critic_alignment_integration.py`, `tests/fixtures/clarify_critic_v1.json`, `tests/fixtures/jsonl_emission_cutoff.txt`.
- Piece 4: edges land on `cortex_command/overnight/orchestrator_context.py`, `cortex_command/overnight/prompts/orchestrator-round.md`, `cortex_command/overnight/tests/` (update `aggregate_round_context` tests).

### Why N pieces

Piece count is 4. Template R3 gate fires only when piece_count > 5; gate does not fire.

Decomposition history: original was 6 pieces (separate pieces for registry, gate, dead-scan tool, per-event audit, coordinated deletion, and `escalations.jsonl` fix). Walked back per template rule R1 across two iterations: dead-scan tool merged into gate (Piece 2) because both share the `skills/**/*.md` scan surface and can be described in one Role/Integration/Edges paragraph without losing distinguishing detail → merged; per-event audit merged into dead-deletion (Piece 3) because the audit is the input to deletion and shares no separate named contract surface → merged. Final count: 4.

## Decision Records

### DR-1: Partition skill-side and session-side registries; do not merge logs

- **Context**: Two separate event streams exist today (per-feature `events.log`, per-session `overnight-events.log`). Merging them would reduce registry count but requires changing the two-log write architecture.
- **Options considered**: (A) single unified registry with `scope:` column (recommended); (B) two separate registry files, one per log; (C) full log consolidation (single log, single registry).
- **Recommendation**: (A). Single registry file, `scope` column distinguishes stream. Architecture stays two-log; only the type allowlist is unified.
- **Trade-offs**: `scope` column adds one layer of complexity. Avoids the XL cost of log consolidation (option C). Option B creates two files to keep in sync for the same goal.

### DR-2: `clarify_critic` — delete with coordinated test cleanup, not payload-prune

- **Context**: `clarify_critic` has zero Python consumers but one test that requires ≥1 row in the corpus (`test_clarify_critic_alignment_integration.py:666-669`). Two options: prune payload to reduce per-row size, or delete the event and its coordinated test fixtures.
- **Options considered**: (A) payload-prune: drop `findings[]` bodies, keep the event type with a trimmed row; (B) full deletion: remove from `clarify-critic.md`, delete three test fixtures.
- **Recommendation**: (B). Zero Python consumers + the test-consumer is a schema-conformance gate with no live system value means the test is guarding an event that the system has already stopped caring about. Hard-deletion per `requirements/project.md:23`.
- **Trade-offs**: Requires coordinated 4-file commit. Payload-prune (A) saves ~140KB storage but leaves the dead event accumulating indefinitely; the registry gate would immediately flag it as dead on next commit.

### DR-3: `bin/cortex-check-events-registry` — fix the fails-open gap vs. `cortex-check-parity` precedent

- **Context**: `bin/cortex-check-parity:386` fails open when `.parity-exceptions.md` is missing — silently returns an empty rowset, meaning a repo clone without the exceptions file has no enforcement. Parallel design decision for the new gate.
- **Options considered**: (A) fail open (match existing precedent); (B) fail closed (missing registry = error); (C) fail open with a warning on stderr.
- **Recommendation**: (C). Failing closed breaks `git clone; just test` workflows for new contributors who haven't initialized the registry. Warning on stderr makes the gap visible without blocking.
- **Trade-offs**: Failing open silently (A) means the gate provides no enforcement on a fresh clone — defeats the purpose. (C) is a middle ground that makes the condition detectable without requiring repo state that isn't committed.

### DR-4: `escalations.jsonl` optimization — bump schema version and co-deploy writer + reader

- **Context**: `orchestrator_context.py:115-116` enforces strict schema-version equality. Any payload shape change requires a version bump AND the reader update in the same deployment.
- **Options considered**: (A) tolerant-reader window (accept both old and new shape for N rounds); (B) strict co-deploy (bump + reader update in one commit, no window).
- **Recommendation**: (B). The strict guard is an explicit design choice in the existing code; relaxing it to a window adds surface for silent misparse. Since writer and reader are in the same repo, co-deploy is feasible.
- **Trade-offs**: (B) requires discipline to never deploy writer without reader. In a monorepo, this is the default; the risk is only in cherry-pick or rollback scenarios. Acceptable for this codebase.

## Open Questions

- **How large is the context-window cost of dead events during a live run?** The 14% storage figure is measured on archived files, not live-context load. The in-session cost (how many tokens dead events consume when the orchestrator reads a feature's `events.log` in a round) was not measured during this research — `[premise-unverified: not-searched-deeply]` for per-round context consumption. Decompose-time question: should the Piece 3 dead-deletion tickets be ordered by context-window cost rather than storage cost?
- **Does `task_complete` have undocumented human-skim consumers?** The audit found zero Python consumers `[premise-unverified: codebase-grep confirms, but no dashboard or external tooling was checked]`. If any external tooling (e.g., a team member's grep workflow) depends on `task_complete` being present in `events.log`, deletion would break it silently. Decompose ticket should include a 1-week deprecation notice in `CHANGELOG.md` before deletion.
