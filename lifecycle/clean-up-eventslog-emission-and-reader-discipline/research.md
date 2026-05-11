# Research: Clean up events.log emission and reader discipline

Topic: Close four sources of events.log waste/risk (dead-event emissions, `clarify_critic` payload accumulation, unbounded `escalations.jsonl` re-inline, and the structural discipline gap that lets dead types accumulate) such that the live consumer surface and dashboard phase-transition timeline keep working, in-flight features keep parsing through a grandfathered window, and the next audit will not find the same accumulation pattern.

## Codebase Analysis

### Per-feature events.log emission inventory

Twenty distinct event names are emitted via skill-prompt JSONL-emit instructions (Claude writes the JSONL line directly per template). Canonical sources only — `plugins/cortex-core/skills/*` is the auto-generated mirror:

| File | Events emitted |
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

### Audit verification (consumer counts, excluding tests)

| Event | Non-test Python consumer hits | Status |
|---|---|---|
| `feature_complete` | 10 | live |
| `phase_transition` | 4 | live |
| `review_verdict` | 4 | live |
| `dispatch_complete` | 4 | live |
| `lifecycle_start` | 3 | live |
| `batch_dispatch` | 1 (metrics.py:232) | live |
| `criticality_override` | 1 (orchestrator-round.md prompt only) | live |
| `clarify_critic` | 0 | **see adversarial — has test consumer** |
| `confidence_check` | 0 | dead |
| `decompose_ack`, `decompose_drop`, `decompose_flag` | 0 | dead |
| `discovery_reference` | 0 | dead |
| `implementation_dispatch` | 0 | dead |
| `orchestrator_dispatch_fix`, `orchestrator_escalate`, `orchestrator_review` | 0 | dead |
| `plan_comparison` | 0 (tests only) | dead-for-Python |
| `requirements_updated` | 0 | dead |
| `task_complete` | 0 | **see adversarial — human-skim affordance** |

Archive base-rate: 145 archived feature events.log files contain ~127,460 bytes of dead-emission rows out of ~897,811 total `"event":` row bytes (~14% storage share). **Adversarial caveat:** this is storage, not context-window cost; per-session live-context cost is the load-bearing metric and was not measured by the audit.

### Live consumer surface (expanded beyond `extract_feature_metrics`)

**Python consumers of per-feature events.log:**
- `cortex_command/pipeline/metrics.py:212-247` — `extract_feature_metrics` parses `feature_complete`, `lifecycle_start`, `batch_dispatch`, `phase_transition`, `review_verdict`.
- `cortex_command/dashboard/data.py:281-336` — `parse_feature_events` reads only `phase_transition` (the timeline view).
- `cortex_command/common.py:195-197,298,339` — generic phase detection; `read_criticality` / `read_tier`.
- `cortex_command/overnight/report.py:618-624,749-754` — reads `phase_transition`, `tier`.
- `bin/cortex-complexity-escalator:55-71,299` — reads `complexity_override`, `read_effective_tier`.
- `bin/cortex-archive-sample-select:108-132` — reads `feature_complete`.
- `hooks/cortex-scan-lifecycle.sh:107` — substring-greps `"feature_complete"`.
- `claude/statusline.sh:321,391` — substring-greps `"feature_complete"`.

**Tests as consumers:**
- `tests/test_clarify_critic_alignment_integration.py:193-668` is a schema-conformance gate that walks `lifecycle/*/events.log` for `clarify_critic` rows in both JSONL and YAML-block shapes (`_JSONL_RE`, `_YAML_EVENT_LINE_RE` at lines 579-581), asserts schema-version invariants, and at line 666-669 requires `detections >= 1`. Deleting `clarify_critic` emission requires coordinated deletion of this test, `tests/fixtures/clarify_critic_v1.json` (line 551), `tests/fixtures/jsonl_emission_cutoff.txt`, and the schema-version handling.

### Python-side emitter universe (NOT in the skill-prompt scan surface)

`cortex_command/pipeline/dispatch.py` lines 654, 686, 703, 714, 738, 745, 755, 764, 789, 808 emit at least 8 distinct names via `log_event(log_path, ...)`: `dispatch_start`, `dispatch_progress`, `tool_call`, `tool_result`, `dispatch_truncation`, `dispatch_complete`, `turn_complete`, `dispatch_error`.

`cortex_command/pipeline/merge.py:205-326` emits ~12 names: `merge_start`, `ci_check_start`, `ci_check_pending`, `ci_check_failed`, `ci_check_skipped`, `ci_check_passed`, `merge_error`, `merge_conflict_classified`, `merge_complete`, `merge_test_failure`, `merge_revert_error`, `merge_reverted`, `merge_success`.

`cortex_command/pipeline/conflict.py:257-442` emits `REPAIR_AGENT_*` constants.

`cortex_command/overnight/events.py:90-148` has a separate `EVENT_TYPES` closed registry with write-time enforcement (`ValueError` at lines 216-218) — but this governs session-scope `overnight-events.log`, **not** per-feature events.log. The two logs have no shared registry today.

Implication: any discipline mechanism that only scans `skills/**/*.md` (the `bin/cortex-check-parity` SCAN_GLOBS pattern) covers a strict subset of the emitter universe. A complete gate must include `cortex_command/**/*.py` `log_event` call literals OR partition responsibility (skill-prompt registry for per-feature events.log; the existing `EVENT_TYPES` tuple for session-scope events).

### `clarify_critic` payload accumulation (verified)

- Write site: `skills/refine/references/clarify-critic.md:130-220` instructs Claude to write the full single-line JSONL including the entire `findings[]` array (~150-300 chars per finding) plus `dismissals[].rationale`.
- Archive base-rate verified: **95 rows, 186,340 total bytes, 1,961 avg chars/row, max 6,825 chars/row.** Top-5 sizes: 4,395 / 5,309 / 5,472 / 5,517 / 6,825.
- Schema_version: 2 (latest); legacy v1, v1+dismissals, YAML-block tolerated per `clarify-critic.md:162-166`.

### `escalations.jsonl` re-inline path

- Writer-side: `cortex_command/overnight/orchestrator_context.py:60-75` fully concatenates the file into `all_entries: list[dict]` every round; line 108-110 returns `escalations: {unresolved, all_entries}`.
- Sole consumer of `all_entries`: `cortex_command/overnight/prompts/orchestrator-round.md:54-61` — a per-feature filter `[e for e in all_entries if e.get("type") == "resolution" and e.get("feature") == entry["feature"]]`. The full list is otherwise unused.
- `unresolved` is computed once at aggregator time (lines 79-94) and consumed independently.
- **Strict schema-version equality guard at `orchestrator_context.py:115-116`:** `if payload["schema_version"] != _EXPECTED_SCHEMA_VERSION: raise RuntimeError(...)`. No tolerant-reader window. A payload-shape change requires a bump and co-deployed reader update.

### Discipline-gate precedent inspection

`bin/cortex-check-parity` is the in-codebase precedent for "registry-with-allowlist pre-commit gate":
- Top-level constants `PLUGIN_NAMES` / `RESERVED_NON_BIN_NAMES` (lines 34, 51), `SCAN_GLOBS` (line 69), `ALLOWED_CATEGORIES` (line 117).
- Wired in `.githooks/pre-commit:72-92` as "Phase 1.5 — SKILL.md-to-bin parity enforcement."
- **Fails OPEN on missing allowlist:** `bin/cortex-check-parity:386` `if not p.is_file(): return [], [], False` — missing `.parity-exceptions.md` silently returns an empty rowset.
- `.parity-exceptions.md` currently has **2 entries** added 2026-04-27 (#102) and 2026-04-29 (#151) — ~12-14 days of operation as of 2026-05-11. Not yet evidence of anti-accumulation, just a young pattern.
- `ALLOWED_CATEGORIES` includes `deprecated-pending-removal` but the linter has **no code path enforcing removal-by-date** — stale rows can sit indefinitely.

### Files that will change (depends on Spec decisions)

**Always:**
- `cortex_command/overnight/orchestrator_context.py:60-110` — drop `all_entries`, add `prior_resolutions_by_feature` (and optionally `prior_promotions_by_feature`). Bump `_EXPECTED_SCHEMA_VERSION` per the strict-equality guard.
- `cortex_command/overnight/prompts/orchestrator-round.md:54-61` — switch the prior-resolutions filter to consume the precomputed dict. Co-deployed in the same PR.
- `cortex_command/overnight/tests/` — update tests of `aggregate_round_context`.

**Conditionally (depends on per-event decisions):**
- `skills/lifecycle/references/orchestrator-review.md`, `skills/discovery/references/orchestrator-review.md`, `skills/discovery/references/decompose.md`, `skills/lifecycle/references/specify.md`, `skills/lifecycle/references/implement.md`, `skills/lifecycle/references/review.md`, `skills/lifecycle/SKILL.md`, `skills/lifecycle/references/plan.md`, `cortex_command/overnight/prompts/orchestrator-round.md` — skill-prompt edits per event-by-event remediation table.
- `skills/refine/references/clarify-critic.md:113-216` — payload-pruning or full deletion.
- `tests/test_clarify_critic_alignment_integration.py`, `tests/fixtures/clarify_critic_v1.json`, `tests/fixtures/jsonl_emission_cutoff.txt` — coordinated with any `clarify_critic` change.

**For the discipline mechanism (if chosen):**
- New `bin/cortex-check-events-registry` (modeled on `bin/cortex-check-parity`).
- New `events/events-registry.md` (or `bin/.events-exceptions.md`) — registry/allowlist artifact.
- `.githooks/pre-commit` — new Phase 1.7.
- `justfile` — new `check-events-registry` recipe.

### Conventions to follow

- Dual-source enforcement: edit canonical sources under `skills/`, `hooks/`, `bin/cortex-*`; `plugins/cortex-core/*` auto-regenerates via pre-commit.
- stdlib-only for `bin/cortex-*` scripts (per parity-linter precedent).
- `cortex-log-invocation` shim required in the first 50 lines of new `bin/cortex-*` scripts (Phase 1.6 of pre-commit enforces this).
- Atomic writes (`tempfile + os.replace()`) for state files; JSONL appends are byte-offset-tolerant for readers.
- Hard-deletion preferred over deprecation when consumers are verified zero (`requirements/project.md:23`).
- Schema-version bumps with `_EXPECTED_SCHEMA_VERSION` constants and explicit drift-guard raising.
- CLAUDE.md ≤100 lines (extract policy entries to `docs/policies.md` on overflow).

## Web Research

### Closest prior-art pattern: EventCatalog (producer/consumer registry)

[EventCatalog](https://www.eventcatalog.dev/docs/development/developer-tools/eventcatalog-linter) treats producer/consumer relationships as first-class metadata: a registry directory of event-type markdown files, each with `producers:` and `consumers:` lists. Its linter enforces *Reference Validation* (every reference must resolve to an existing event-type doc) — exactly the asymmetry-inversion the audit calls for. The [Architecture Change Detection](https://www.eventcatalog.dev/docs/development/governance/architecture-change-detection/introduction) tool emits `producer_added`, `producer_removed`, `consumer_added`, `consumer_removed` triggers; the symmetric "emit-without-consumer" detection is the same pattern.

**Transfer:** ship a flat registry directory (or single markdown table modeled on `.parity-exceptions.md`) with `event_name`, `producers`, `consumers`, `added_date`, optional `deprecation_date`. CI fails if a producer references an event with empty `consumers`.

### Consumer-Driven Contract Testing (Pact / Pactflow)

Heavyweight version of the same idea: [consumers, not producers, define the contract](https://pactflow.io/what-is-consumer-driven-contract-testing/). Lightweight adaptation for Cortex: each consumer module declares its consumed event names (e.g., `CONSUMES = {"phase_transition", ...}`); CI takes the union of all `CONSUMES` sets as the valid-emit list. This sidesteps dual-maintenance of producer-side and consumer-side registries.

### Bounded re-inline patterns

- **Tail-since-cursor** ([tailsince](https://github.com/codeforkjeff/tailsince)): durable on-disk history, bounded re-inline via cursor. Mismatch for the cycle-break reader, which needs *all* prior resolutions per feature, not recent ones.
- **Snapshot-plus-tail** ([Microsoft event-sourcing](https://learn.microsoft.com/en-us/azure/architecture/patterns/event-sourcing)): periodically materialize a snapshot from `escalations.jsonl`; re-inline only snapshot + new tail. Preserves "filter prior resolutions per-feature" semantics. Overkill for current scale (sub-100 entries typical) but correct shape.
- **Ring buffer**: rejected — loses durable history.
- **Pre-computed read-shape index** (the recommended fit, see Tradeoffs §3): aggregator emits exactly the dict shape the reader uses; full file remains durable on disk.

### Schema evolution and grandfathering

- **[Tolerant Reader](https://martinfowler.com/bliki/TolerantReader.html) (Fowler):** readers ignore unknown fields, accept missing optional fields, dispatch on a type discriminator before validating. Direct fit for per-feature events.log; current readers already follow this pattern implicitly (unknown event names are skipped, not failed).
- **[Confluent BACKWARD compatibility](https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html)** rule: upgrade consumers before producers. For Cortex: ship the reader-tolerant change first, change emitters second, close the window when no events older than window-start remain in active logs.
- **[Protobuf deprecation](https://protobuf.dev/best-practices/dos-donts/):** mark with `deprecated: true`, keep tolerant reader, remove after window. Matches the `deprecated-pending-removal` allowlist category precedent.

### CI-time emission gates

- **[ESLint custom rules](https://eslint.org/docs/latest/extend/custom-rules):** canonical "small script, fail CI" pattern.
- **[EventCatalog Linter rules](https://www.eventcatalog.dev/docs/development/developer-tools/eventcatalog-linter)** with severity tiers (Documentation Validation + Reference Validation). Severity tiers map cleanly to "error on new dead types, warn on grandfathered ones."
- **[Knip / dead-code detectors](https://github.com/webpro/knip):** treat unreferenced symbols as failures; same pattern applies to events with empty `consumers` lists.

### Anti-patterns flagged

- **OpenTelemetry's "events may have whatever payload"** default ([OTel issue #505](https://github.com/open-telemetry/semantic-conventions/issues/505)) is the *exact* permissive default that produces dead-payload accumulation. Cortex needs the inverse — closed-by-default registry.
- **Documentation-only registries** (OTel-style) provide no structural guarantee against accumulation.
- **Heavy schema-registry stacks** (Confluent, EventBridge, Avro toolchains) — correct in principle, wildly oversized for a file-based JSONL log. Take the principles, re-implement with markdown + one CI script.
- **Ring buffer for durable escalations** — silently loses history; wrong tool for "filter prior resolutions per-feature."

## Requirements & Constraints

### Append-only JSONL log shape (hard constraints)

- `events.log` is per-feature, append-only JSONL (`docs/agentic-layer.md:244`).
- Writer is `events.py` (`docs/overnight-operations.md:83`).
- Append-only audit trail is a non-functional requirement (`requirements/pipeline.md:129`).
- Atomic writes via `tempfile + os.replace()`; JSONL byte-offset tailers tolerate partial-line writes (`docs/overnight-operations.md:557`, `requirements/pipeline.md:21,126`).

### Schema versioning conventions

- "Absent means v1" is established convention (`docs/internals/mcp-contract.md:86`; `requirements/pipeline.md:28`).
- `runner.pid` schema_version range convention: `1 ≤ schema_version ≤ MAX_KNOWN_RUNNER_PID_SCHEMA_VERSION`.
- `aggregate_round_context` carries `schema_version`; *strict equality* check at `orchestrator_context.py:115-116` (not tolerant). Drift raises `RuntimeError("schema_version drift")` (`docs/overnight-operations.md:633,639`).
- `clarify_critic` event has v2 schema; readers MUST tolerate absence as v1, plus YAML-block legacy shape (`skills/refine/references/clarify-critic.md:162-166`).

### Hard-deletion vs deprecation (project policy)

`requirements/project.md:23`: "**Workflow trimming**: Workflows that have not earned their place are removed wholesale rather than deprecated in stages. Hard-deletion is preferred over deprecation notices, tombstone skills, or env-var soft-deletes when the surface has zero downstream consumers (verified per-PR). Retired surfaces are documented in `CHANGELOG.md` with replacement entry points and any user-side cleanup paths the scaffolder cannot auto-prune."

`requirements/project.md:19`: "**Complexity**: Must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct."

### Live consumer surface (binding)

- Statusline (`requirements/observability.md:16,20`): reads events.log; feature name + phase must match.
- Dashboard (`requirements/observability.md:30,33`): reads per-feature events.log; phase progress reflects state within 7s.
- Lifecycle resume (`docs/agentic-layer.md:244`): reads events.log to determine restart phase.
- Metrics (`requirements/pipeline.md:100,104`): parses `feature_complete` events; in-progress excluded.
- Review subsystem (`requirements/pipeline.md:65,68`): `batch_runner` owns all events.log writes; APPROVED-cycle writes `review_verdict`, `phase_transition`, `feature_complete`.
- Morning report (`requirements/pipeline.md:70`): writes synthetic `review_verdict: APPROVED, cycle: 0` events for skipped reviews.

### Rationale field convention

`requirements/pipeline.md:130`: "When the orchestrator resolves an escalation or makes a non-obvious feature selection decision … the events.log entry should include a `rationale` field … Routine forward-progress decisions do not require this field." Not directly affected by this work, but the per-event change set must not break the rationale-bearing events.

### MUST-escalation policy (CLAUDE.md:51-59)

- Default to soft positive-routing phrasing for new authoring (post-Opus-4.7 harness adaptation).
- Adding new MUST/CRITICAL/REQUIRED requires evidence-artifact (events.log F-row or transcript) AND a prior effort=high dispatch attempt that demonstrably fails.
- OQ3 applies to all behavior-correctness failure modes; tone perception is exempt (OQ6).

**Applicability to this work:** the policy's plain text scopes the constraint to *authored* MUST/CRITICAL/REQUIRED phrasing in skill prompts and agent-facing rails. A *code-layer* CI gate that rejects unregistered emissions at commit time is a structural enforcement, not authored MUST language. **However**, the gate's error messages (shown to a human committer at commit time) are authored content; writing them in positive-routing form ("Register this event in `events-registry.md` to allow the commit") avoids the auditor-flag risk. Cost: zero.

### CLAUDE.md size cap

`CLAUDE.md:67`: capped at 100 lines. Any new policy entry that pushes it past 100 lines must extract all policy entries (OQ3, OQ6, plus new) to `docs/policies.md`. `docs/policies.md` does not yet exist. No new policy entry is required by this work if the gate ships without authored MUST phrasing.

### Skill/hook/CLI deployment model

- Lifecycle wrapper required for canonical-source edits in `skills/`, `hooks/`, `claude/hooks/`, `bin/cortex-*`, `cortex_command/common.py`, `plugins/cortex-pr-review/`, `plugins/cortex-ui-extras/`.
- Dual-source drift pre-commit hook enforces auto-mirror regeneration into `plugins/cortex-core/*`.
- SKILL.md-to-bin parity enforcement (`requirements/project.md:29`): the precedent for "registry-with-exceptions pre-commit gate with intentional friction."

### Out of scope (reinforced by parent epic)

- Full 2-tier events.log split (events.log spine + events-detail.log) — deferred per epic #172 pending the ~71-event consumer audit. **Relocation to `events-detail.log` for any event in this work pre-decides #172's deferred architectural choice and is therefore out-of-scope.**
- Retroactive deletion of archived events.log content.
- Replacement of events.log with OpenTelemetry-style tracing.
- Changes to live-consumer parsing logic beyond what's strictly required.

## Tradeoffs & Alternatives

### Sub-problem 1: Dead-event remediation (per-event action)

**A1a. Delete-without-replacement** — remove the emission instruction from the skill prompt.
- Complexity XS; maintainability highest; performance best; alignment strongest with `project.md` "Workflow trimming."
- Pro: cheapest, cleanest, structurally correct when data has no downstream use.
- Con: loses human-skim/`jq`-grep audit trail. Memory rule "user-facing affordances are load-bearing even when artifact production is empty" applies and must be explicitly checked per-event.

**A1b. Relocate-to-artifact** — move payload to a per-feature `.md` or `.json` with a *declared* consumer.
- Complexity M; maintainability lower than A1a (new file surface to keep earning its place).
- Pro: preserves rich content when reconstruction from other artifacts isn't possible.
- Con: without a declared reader, this is dead-emission with extra steps — accumulates a new per-feature artifact-file surface that will resurface in a future audit.

**A1c. Relocate-to-events-detail.log** — sibling tier-2 log.
- **Out of scope** per ticket and parent epic #172. Rejected.

**Decision rule** (Spec input): for each event in the verified-dead list, classify as:
1. **DELETE** — no human-skim use, no audit value, no test coverage. → A1a.
2. **KEEP-AS-AUDIT-AFFORDANCE** — instructed for human-skim use (e.g., `task_complete` reviewing batch outcomes); cheap; payload is already minimal. → keep emission, no change to events.log.
3. **PRUNE-PAYLOAD** — keep the event row but shrink the payload to its load-bearing fields, removing accumulated prose. → emission stays; payload schema bumps. Applies to `clarify_critic` (see Sub-problem 2).
4. **COORDINATED-DELETE** — event has test/fixture/positive-control consumer. → A1a but with coordinated deletion of test + fixture + cutoff handling.

### Sub-problem 2: `clarify_critic` payload

**Adversarial correction:** `clarify_critic` has a live test consumer (`tests/test_clarify_critic_alignment_integration.py:593-669`) that requires `detections >= 1` over `lifecycle/` events. The test is a schema-conformance gate, not an arbitrary consumer; deleting `clarify_critic` invalidates the gate.

**Recommended action: PRUNE-PAYLOAD** rather than delete or relocate. The 95×1,961-char accumulation comes from the `findings[]` and `dismissals[].rationale` arrays — full prose stored per row.

Concrete shape:
- Keep the event row in events.log (preserves the test gate's `detections >= 1` invariant).
- Replace `findings[]` and `dismissals[]` with `findings_count`, `dismissals_count`, `applied_fixes_count`, and a `findings_path: "lifecycle/{feature}/clarify-critic-findings.json"` reference.
- Write the full prose to `lifecycle/{feature}/clarify-critic-findings.json` (atomic write, byte-stable schema).
- Bump `schema_version: 2 → 3`.
- Extend the legacy-tolerance table in `clarify-critic.md:162-166` to accept v3 (new) and continue tolerating v2/v1/v1+dismissals/YAML-block for the grandfather window.
- Update the integration test to scan both the events.log row (for `detections >= 1` invariant) and the per-feature findings.json file (for content invariants).

Net effect: events.log row drops from ~1,961 chars to ~250 chars (one bullet-list reduction). Findings prose lives in a sibling file where the schema-conformance test reads it; the discipline of "the file has a declared consumer" is satisfied by the test.

### Sub-problem 3: Bounded escalation re-inline

**A3a. Cap-to-N** — last N entries. Rejected: per-feature filter on `prior_resolutions` may miss older entries for the same feature, breaking cycle-detection.

**A3b. since=last_round_ts** — cursor-style. Rejected: same correctness regression; cycle-break needs full history per-feature.

**A3c. Pre-compute read-shape indexes** — drop `all_entries`; emit `unresolved: list[dict]` + `prior_resolutions_by_feature: dict[str, list[dict]]` from the aggregator. Update reader prompt at `orchestrator-round.md:54-61` co-deployed. **Recommended.**

**Refinements (adversarial input):**
- Key collision risk: a feature slug that repeats across sessions could collide. Key the dict on the `(session_id, feature_slug)` tuple, encoded as `"{session_id}::{slug}"` per JSON-key constraints, OR scope the aggregator to current-session-only (`escalations.jsonl` is already per-session — `lifecycle/sessions/{session_id}/escalations.jsonl` — so within-session collisions are not possible; cross-session collisions don't apply because each session has its own file). Verification: confirm at Spec time that the aggregator reads only the current session's file.
- Schema-version bump: `_EXPECTED_SCHEMA_VERSION` in `orchestrator_context.py:20,115` must bump from 1 to 2; the reader prompt and the orchestrator must be co-deployed in the same PR (no tolerant-reader window currently exists). Rollback semantics: a revert of the producer requires a revert of the consumer prompt in the same commit; document this in the PR description.
- Optional extension: also pre-compute `prior_promotions_by_feature` if the reader needs it (currently uses `unresolved` for promotions — Spec to confirm).

### Sub-problem 4: Discipline mechanism

**A4a. Runtime registry (emitter rejects).** Rejected:
- No central emitter exists for skill-prompt JSONL writes; building one is out of scope.
- Mid-session fragility — a feature in-flight emitting an unregistered name would fail mid-execution. The "in-flight features must continue parsing through a grandfathered window" constraint applies on the *read* side; runtime rejection adds *write*-side fragility the constraint doesn't authorize.
- MUST-policy adjacent — easier to author in positive-routing form via the CI path.

**A4b/A4e. CI-time gate (with grandfathering allowlist).** **Recommended with adversarial-driven refinements.** Model on `bin/cortex-check-parity`. New `bin/cortex-check-events-registry`:
- Scans skill-prompt markdown (`skills/**/*.md`, `cortex_command/overnight/prompts/*.md`) AND Python emitters (`cortex_command/**/*.py` `log_event(...)` literal-key extraction) for emitted event-name string literals.
- Asserts each name appears in `events/events-registry.md` (or `bin/.events-exceptions.md`) with required schema: `event_name`, `producers[]`, `consumers[]`, `added_date`, optional `deprecation_date`, category.
- Emits E-class violations for unregistered names; W-class for `registered-without-consumer` (drift detection).
- **Fails closed on missing registry file** (override the `cortex-check-parity` fail-open default).
- **Enforces `deprecation_date`**: if `deprecation_date` is in the past and the event is still emitted, fail. Adds the deadline-enforcement loop the parity precedent lacks.
- Includes a `--lenient` mode for warning-only operation in transitional periods.
- Self-tested per the parity-linter discipline (8-16 self-test cases).
- Error messages written in positive-routing form per CLAUDE.md MUST-policy adjacency.

**Coverage extensions over A4b baseline:**
- *Python emitter scanning.* The `cortex-check-parity` SCAN_GLOBS pattern excludes `.py` files; A4e must include them. Spec input: do Python emitters and skill-prompt emitters share one registry, or two partitioned registries (skill prompts for per-feature events.log, the existing `EVENT_TYPES` tuple in `cortex_command/overnight/events.py:90-148` for session-scope events)? Recommended: one registry, marked per-row with `target: per-feature-events-log` vs `target: overnight-events-log`. Avoids dual-source confusion.
- *Consumer-side runtime drift detector* (optional second gate). Static producer-side gate cannot catch runtime drift — Claude can deviate from the prompt. A complementary `cortex-validate-events` script that reads emitted events.log files and warns on unknown event names, run periodically by the morning-review hook, would catch the gap. Spec input: ship this as part of the same PR, or defer as out-of-scope?

**A4c. Human-review checklist.** Rejected: same asymmetry that produced the original 49+10 dead events; "please remember to" doesn't change incentives.

**A4d. Periodic audit.** Rejected: institutionalizes the diagnosed problem.

### Cross-coupling summary

| Sub-problem | Recommendation | Spec input needed |
|---|---|---|
| 1. Dead events | Per-event classification using DELETE / KEEP-AFFORDANCE / PRUNE-PAYLOAD / COORDINATED-DELETE rule | Per-event verdict (table) |
| 2. clarify_critic | PRUNE-PAYLOAD via schema bump v2→v3 with sibling findings.json file | Confirm pruning over deletion |
| 3. Escalation bound | A3c pre-compute indexes + schema_version bump 1→2 + co-deployed reader | Confirm `prior_promotions_by_feature` need |
| 4. Discipline | A4e CI gate w/ fail-closed + deprecation-date enforcement + Python emitter scanning + positive-routing error messages | Confirm registry partitioning (one vs two); confirm consumer-side drift detector in/out of scope |

## Adversarial Review

### Confirmed-real failure modes (must be addressed in spec)

1. **`clarify_critic` is not dead** — `tests/test_clarify_critic_alignment_integration.py:593-669` is a positive-control schema-conformance gate. Required action: PRUNE-PAYLOAD (recommended above), not DELETE. Coordinated changes: the test, `tests/fixtures/clarify_critic_v1.json`, `tests/fixtures/jsonl_emission_cutoff.txt`, schema-version handling.

2. **`task_complete` is a human-skim audit affordance** — `skills/lifecycle/references/implement.md:185-187` instructs Claude to emit per-task. Per the user's recorded preference ("user-facing affordances are load-bearing even when artifact production is empty"), deletion requires explicit confirmation that no human relies on this row. Default: KEEP-AS-AUDIT-AFFORDANCE.

3. **Python emitters bypass the skill-prompt scan surface entirely** — `cortex_command/pipeline/dispatch.py`, `merge.py`, `conflict.py` emit ~20+ event names invisible to a `skills/**/*.md` scan. Required: A4e gate must include `cortex_command/**/*.py` scanning OR the registry must explicitly scope to per-feature events.log only.

4. **`cortex-check-parity` fails open on missing allowlist** — `bin/cortex-check-parity:386` returns empty rowset when `.parity-exceptions.md` is missing. Required: A4e overrides this to fail closed.

5. **`.parity-exceptions.md` is too young to validate as anti-accumulation precedent** — 2 entries, ~14 days operation. The audit's "this pattern works" claim is unproven. Mitigation: A4e adds the `deprecation_date` enforcement loop the parity precedent lacks.

6. **`orchestrator_context.py:115-116` is a strict-equality schema guard**, not a tolerant reader. The A3c rewrite must bump `_EXPECTED_SCHEMA_VERSION` 1→2 and co-deploy the reader-prompt change in the same PR. No grandfathered window exists for this payload — document the no-rollback-without-revert semantics in the PR description.

7. **Static CI gate cannot catch runtime injection** — Claude can deviate from prompts and emit a mistyped name or a new name not in any file. A consumer-side `cortex-validate-events` runtime detector complements the producer-side static gate. Spec input: in or out of scope for this work?

8. **Live consumer list extends beyond `extract_feature_metrics`** — `hooks/cortex-scan-lifecycle.sh`, `claude/statusline.sh`, `bin/cortex-complexity-escalator`, `bin/cortex-archive-sample-select` all consume per-feature events.log. The registry's initial population must walk all these consumers, not just the Python metrics pipeline.

### Lower-priority concerns (note and proceed)

9. **The 14% archive figure is a storage metric, not a context-window metric** — the headline-cost claim should be rebaselined against per-session live-context emission cost during overnight rounds. Not blocking; affects how the value case is framed in the spec.

10. **MUST-policy applies (loosely) to gate error messages** — write them in positive-routing form. Cost: zero. Already incorporated in A4e.

11. **Allowlist becomes a mutation target** — possible CODEOWNERS protection on `events-registry.md` / `.events-exceptions.md`. Out of scope for v1; note for follow-up.

### Lower-priority concerns dismissed by current architecture

- **Per-feature key collision in `prior_resolutions_by_feature`** — `escalations.jsonl` is per-session (`lifecycle/sessions/{session_id}/escalations.jsonl`), so within-session collisions cannot happen and cross-session collisions don't apply because the aggregator reads only the current session's file. Verification step at Spec time only.

- **Mid-session safety for cleanup sweep** — skill prompts ARE re-read by subagent dispatches per Anthropic SDK semantics, but the deletion of a *dead* emission instruction simply means new dispatches don't emit it. Existing events.log rows remain parseable; the constraint "in-flight features must continue parsing" applies on the read side, which is unaffected. (The `clarify_critic` test consumer concern is real but separately addressed.)

## Open Questions

The following must be resolved at Spec time (Step 5 of the refine flow). Marked **resolved** with inline answer or **deferred** with rationale per the Research Exit Gate.

1. **Per-event remediation table — DELETE vs KEEP-AS-AFFORDANCE vs PRUNE-PAYLOAD vs COORDINATED-DELETE per dead event.**
   - **Deferred:** the table is a primary spec deliverable. Research has identified the decision rule, the audit's verified-dead list, the test/affordance overlay, and the consumer-side grep coverage. Spec will produce the per-event verdict with the user, using the decision rule.

2. **`clarify_critic` action: PRUNE-PAYLOAD (recommended) or DELETE-with-coordinated-test-removal?**
   - **Resolved:** PRUNE-PAYLOAD recommended on the strength of (a) the schema-conformance test is a legitimate consumer; (b) the payload's findings prose is the actual waste, not the row itself; (c) the relocation-to-artifact alternative has no consumer contract and would resurface in a future audit. The pruning preserves the test's `detections >= 1` invariant.

3. **`task_complete` action: KEEP-AFFORDANCE or DELETE?**
   - **Deferred:** requires user confirmation that no human-skim audit use exists. Default recommendation: KEEP-AFFORDANCE per the memory rule about user-facing affordances. Spec to confirm.

4. **Discipline mechanism scope: per-feature events.log only, OR per-feature events.log + session-scope `overnight-events.log` unified registry?**
   - **Resolved:** unified registry with `target` column per row. The existing `cortex_command/overnight/events.py:90-148` `EVENT_TYPES` tuple is a closed registry already for session-scope events and is the canonical source for those; the new gate registers entries pointing at it as a satellite import (e.g., `target: overnight-events-log, source-of-truth: cortex_command/overnight/events.py:EVENT_TYPES`). Avoids two parallel discipline systems.

5. **Discipline mechanism coverage: skill-prompt markdown only, OR also Python emitters?**
   - **Resolved:** also Python emitters (`cortex_command/**/*.py` `log_event(...)` literal-key extraction). Without this, the gate misses ~20+ emission sites and the audit's "discipline" is half-built.

6. **Consumer-side runtime drift detector: in or out of scope for this work?**
   - **Deferred:** Spec to decide. Research observes that the static producer-side gate cannot catch runtime injection (Claude can deviate from prompts), and a complementary consumer-side validator (`cortex-validate-events`) reading emitted events.log files and warning on unknown names would close the gap. Cost is modest (~100-200 LOC of stdlib Python). Recommendation: include if the work allows, defer otherwise — not strictly required for the asymmetry-inversion goal but improves robustness.

7. **MUST-escalation policy applicability to CI gate error messages?**
   - **Resolved:** the policy's plain text scopes to authored MUST/CRITICAL/REQUIRED phrasing in agent-facing rails; CI tooling is structural enforcement. However, gate error messages are authored content surfaced to committers, so write them in positive-routing form (cost: zero). No evidence-artifact precondition required for the gate itself.

8. **Schema-version bump on `orchestrator_context` (A3c)?**
   - **Resolved:** required. `_EXPECTED_SCHEMA_VERSION` bumps 1 → 2. Producer (`orchestrator_context.py`) and consumer prompt (`orchestrator-round.md`) co-deployed in the same PR. Document no-tolerant-reader and rollback-as-coupled-revert in the PR description.

9. **Dashboard parser schema-version check (open question from clarify)?**
   - **Resolved:** not required for this work. `cortex_command/dashboard/data.py:281-336` reads only `phase_transition` and uses a Tolerant-Reader pattern implicitly (skips unrecognized rows). None of the recommended changes alter `phase_transition` shape. If a future change does, the schema-version check should ship with that change.

10. **Audit base-rate rebaselined to per-session live-context cost?**
    - **Deferred:** Spec to decide framing. Research notes the 14% archive-storage figure is misleading for the token-context-cost story but the qualitative finding (dead emissions accumulate; the discipline gap is real) stands either way. Re-baselining is improvement-of-framing, not a precondition for the work.

11. **Verification re-run of the audit's "zero non-test Python consumers" claim per event before deletion?**
    - **Resolved:** yes, mandatory. Spec will require a fresh repo-wide grep against `cortex_command/`, `bin/`, `hooks/`, `claude/`, `tests/` per event, AND cross-check against the live-consumer list documented in Codebase Analysis above. Tests are NOT excluded from this re-run after the `clarify_critic` near-miss surfaced via this research.

12. **Grandfathering window length for `clarify_critic` payload schema (v2 → v3)?**
    - **Deferred:** Spec to set. Research recommendation: indefinite read-tolerance (v1, v2, YAML-block, and v3 all parseable forever) because the tolerance is cheap and the legacy-tolerance table already exists. No write-side cutoff date needed.

13. **`bin/.events-exceptions.md` or `events/events-registry.md` location and naming?**
    - **Deferred:** Spec to decide. Both are reasonable. The `bin/.events-exceptions.md` form mirrors the `.parity-exceptions.md` precedent exactly; the `events/events-registry.md` form is more discoverable but introduces a new top-level directory. Default recommendation: `bin/.events-exceptions.md` for precedent fit.

The Research Exit Gate passes: every item is either resolved inline or explicitly deferred to Spec with a documented rationale.
