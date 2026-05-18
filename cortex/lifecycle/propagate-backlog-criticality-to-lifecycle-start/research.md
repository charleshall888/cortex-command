# Research: Propagate backlog criticality to lifecycle_start event in refine workflow

Clarified intent: When `/cortex-core:refine` runs from a backlog item, emit a `lifecycle_start` event into `cortex/lifecycle/{feature}/events.log` as the first event in the log (before `clarify_critic`), with `criticality` populated from the backlog item's `criticality` frontmatter (default `medium` if absent), so the canonical state read returns the user-curated value at every downstream phase gate.

## Codebase Analysis

### Root cause confirmed

- `lifecycle_start` is currently emitted **only** by `skills/lifecycle/SKILL.md` §3 step 4 prose ("After the full Clarify phase completes — before Research begins"). When `/cortex-core:refine` is invoked directly (the bug observation in #234), or when the lifecycle SKILL.md prose is silently skipped, no `lifecycle_start` event is ever written. This is consistent with backlog #227's events.log, where the first row is `clarify_critic` (refine-emitted) with no preceding `lifecycle_start`.
- `cortex_command/dashboard/seed.py:506,1016` emits `lifecycle_start` only in **fixture-seeder mode**, not production. Per the file's docstring, it exists for dashboard visual testing without running real overnight workflows.

### Emit-site slot options

- **Refine SKILL.md Step 1/2 (recommended per adversarial review)** — emit at refine entry, before Step 3 Clarify delegation. Catches the resume-from-spec/resume-from-research paths. Gated by an idempotency check against existing events.log content.
- Refine SKILL.md Step 3 prologue — emits before clarify-critic dispatch but is silently skipped when `Step 2: Check State` routes the run directly to the research or spec phase.
- `skills/lifecycle/references/clarify.md` §1.5 (between §1 Resolve Input and §2 Load Requirements Context) — physically precedes clarify-critic dispatch. Same resume-path skip problem.

### Schema and shape

- Existing emit template (`skills/lifecycle/SKILL.md:146`): `{"ts": "<ISO 8601>", "event": "lifecycle_start", "feature": "<name>", "tier": "simple|complex", "criticality": "<level>"}`.
- Real production emits in `cortex/lifecycle/extend-output-floorsmd-.../events.log` carry additional fields: `backlog_id`, `entry_point: refine`, `status: ok`. Existing readers (`cortex_command/common.py:_read_criticality_inner`, `_read_tier_inner`) only key on `event` + `criticality`/`tier`.
- **No `schema_version` is currently set** on `lifecycle_start` rows. Sibling `clarify_critic` uses `schema_version: 3`. Adding `schema_version: 1` to new emits is forward-compatible (readers tolerate absence as v1 per `clarify-critic.md:166`).

### Canonical readers

- `cortex_command/common.py:_read_criticality_inner` (lines 412–448) — most-recent `lifecycle_start.criticality` superseded by most-recent `criticality_override.to`; default `"medium"`. lru_cached on `(path, exists, mtime_ns, size)`.
- `cortex_command/common.py:_read_tier_inner` (lines 485–521) — same shape for tier; default `"simple"`.
- `bin/cortex-lifecycle-state:82-101` mirrors the rule in shell jq; `tests/test_bin_lifecycle_state_parity.py` enforces parity.
- **`cortex_command/pipeline/metrics.py:222-223`** reads `start_events[0]` (first-wins) for tier — different from `common.py` last-wins. If `lifecycle_start` is ever emitted twice, these two readers will disagree.

### Backlog frontmatter readers

- `cortex_command/overnight/backlog.py:232-255` (`_parse_frontmatter` returns dict; `BacklogItem` dataclass does **not** currently expose `criticality`).
- `bin/cortex-resolve-backlog-item:56-72` (`_parse_frontmatter` uses `yaml.safe_load`; JSON output is a closed 4-field shape — does not surface `criticality`).
- `cortex_command/backlog/update_item.py:39-53` (`_get_frontmatter_value(text, key)` — stdlib regex reader for any key).
- Backlog also carries `complexity:` frontmatter (verified on #234 itself: `complexity: complex`). This is the tier-source counterpart to `criticality:`.

### Events-registry gate

- `bin/.events-registry.md:13` already lists `lifecycle_start` with `gate-enforced` scan coverage. Adding a new emit site requires updating the `producers` column with `path:line` of the new producer — but does **not** require a new registry row.
- The static gate (`bin/cortex-check-events-registry --staged`, wired into `.githooks/pre-commit` Phase 1.8) scans `skills/**/*.md` for `"event": "<name>"` literals. Python emit sites in `cortex_command/` are out of the scan surface but still go in the `producers` column for documentation.

### Idempotency and atomic-write conventions

- `bin/cortex-complexity-escalator:192-235` is the only existing per-feature event emitter — uses bare `open(...,"a")` append + read-after-write verify. No "skip if event already present" pattern exists in production code.
- Append-only-JSONL writes are atomic for lines below `PIPE_BUF` (~4KB on macOS/Linux) per `pipeline.md` Atomicity constraints.
- Adding lifecycle_start emit requires implementing an idempotency guard from scratch.

### Test patterns

- `tests/test_clarify_critic_alignment_integration.py:95-100` — subprocess + `CORTEX_BACKLOG_DIR` env var + `tmp_path` fixture, invoking a bin helper.
- `tests/test_common_utils.py:141-210` — direct unit-test pattern for `read_criticality`/`read_tier` against synthetic events.log under `tmp_path`.
- **Gap**: a pytest unit test of a helper does NOT verify that refine SKILL.md actually invokes the helper. Wiring tests need a separate pattern — either a static-analysis grep test (similar to `bin/cortex-check-prescriptive-prose`, `tests/test_lifecycle_kept_pauses_parity.py`) or a true end-to-end harness.

### Refine SKILL.md "no phase transitions" rule

- Refine SKILL.md §5 transition: "Skip — /cortex-core:refine does not log phase transitions… the caller (/cortex-core:lifecycle) owns phase-transition logging and commit-artifacts."
- Adding `lifecycle_start` emit in refine is a **session-start sentinel**, not a phase-transition. The carve-out is semantically tight. The §5 prose should be reworded to specify "phase_transition events" (the literal event name) rather than "events to events.log" as the boundary.

### Plugin distribution constraint

- `plugins/cortex-core/bin/` is a file-mirror; pre-commit regenerates from `bin/`. Skills mirror from `skills/`.
- `[project.scripts]` console-script entries in `pyproject.toml` are **CLI-wheel-only** (per ADR-0002 split). A plugin-only install (no `uv tool install`) cannot invoke `cortex-refine` directly.
- A new helper must ship via `bin/` to ride the plugin mirror. The shell shim can wrap `python3 -m cortex_command.refine` (assumes CLI installed) or contain emit logic inline. The Python module remains the testable surface; the bin script is a thin wrapper.

## Web Research

### "Started/Created/Opened" first-event idiom is the canonical prior art

- Marten's `StartStream<Aggregate>(id, firstEvent)` — first event in a stream is a "creation" event that seeds aggregate state. eventsourcing.readthedocs.io's `AggregateCreated` class is documented as "extended to define particular 'created' events." Naming convention is past-participle (`Started`, `Opened`, `Created`) — matches `lifecycle_start`.
- Event-Driven.io's projections guide: state is a left-fold over events; later events override earlier (same as `common.py:read_criticality`'s "most recent wins"). The seed event is fired **at the boundary, atomically**, before any other phase event. Lazy seeding ("write seed first time someone reads") is an explicit anti-pattern.
- CodeOpinion ("Event Sourcing Do's and Don'ts"): "events must be appended to the event store in a single atomic transaction" with stream creation. Separate setup steps are discouraged because they create a window where the stream exists but is uninitialized.

### Snapshot-at-entry vs. live-re-read

- GitHub Actions ecosystem split: `joerick/pr-labels-action` snapshots labels from the triggering event into step outputs (deterministic); `Require Labels` action calls the GitHub API at runtime to re-read (picks up edits).
- For "canonical state read returns the user-curated value at every downstream phase gate" — **snapshot-at-entry is the right shape**. Mid-flight backlog edits (user changes `criticality: high` → `critical` while a lifecycle is in-flight) are a separate concern, addressed via override events not by re-reading.
- Mastra workflow snapshots: serialize boundary state via `suspendSchema` custom metadata at workflow start. Direct analog to "capture user-curated value into the event log."

### Idempotency consensus

- Three named patterns, in ascending robustness: (1) file-existence/sentinel guard; (2) unique-constraint with conflict-do-nothing; (3) idempotency-store with three-state model. The cortex-command file-based log maps to (1) or (2).
- **Silent skip on duplicate is the consensus default** — natural behavior of `ON CONFLICT DO NOTHING` and the idempotent-consumer pattern. Blocking on duplicate is anti-pattern.
- Anti-patterns: branching on replay/first-run in business logic (Temporal's `isReplaying` warning), mutating seed events in place, "sand foundation" idempotency (consistency model weaker than assumed).

### Temporal-style WorkflowId idempotency

- Starting a workflow with the same ID yields a duplicate error rather than a second workflow. In our model, the analog is "events.log already has `lifecycle_start` → don't append a second one." Temporal also exposes `workflowInfo().unsafe.isReplaying` as a guard for first-execution-only logic — with a sharp warning never to use it for business-logic branching.

## Requirements & Constraints

### Architectural

- **ADR-0001 (file-based state, no database)** — per-feature `events.log` is canonical state; plain text, diffable, grep-able, PR-reviewable. Preserve.
- **ADR-0002 (CLI wheel + plugin distribution)** — `[project.scripts]` ships in the CLI wheel, not the plugin. Plugin-installed users invoke through `bin/` shims, which are mirrored to `plugins/cortex-core/bin/`. New helper must ship a `bin/` shim.
- **ADR-0003 (per-repo sandbox registration)** — `cortex/` umbrella is pre-authorized for sandbox writes via `cortex init`. Appending to events.log is in-scope. Edge case: a fresh checkout that has not run `cortex init` would fail with sandbox-deny; helper should surface a clear diagnostic.

### Project.md directives

- **Skill-helper modules** (`project.md:31`): "when a SKILL.md dispatch ceremony invites paraphrase, collapse it into atomic `cortex_command/<skill>.py` subcommands fusing validation+mutation+telemetry. Promoted modules expose a `[project.scripts]` console-script entry."
- **SKILL.md-to-bin parity** (`project.md:29`): new `bin/cortex-*` scripts must wire through an in-scope SKILL.md/requirements/docs/hooks/justfile/tests reference. `bin/cortex-check-parity` blocks drift.
- **Backlog `grep -c` resolution** (`project.md:34`): any acceptance criterion using `grep -c "<token>"` must reference tokens that appear in the events-registry or as literal strings under `cortex_command/`. `lifecycle_start` is already registered.

### CLAUDE.md guidance

- **Prefer structural separation over prose-only enforcement for sequential gates** — directly supports a Python helper + bin shim over inline SKILL.md prose. The bug exists because prose-only enforcement failed; the fix must not re-introduce prose-only enforcement.
- **Design principle: prescribe What and Why, not How** — refine SKILL.md prose should describe the decision and intent, not the procedure.
- **MUST-escalation policy** — default to soft positive-routing phrasing for new authoring under epic #82. Do not introduce new MUST/REQUIRED escalations without artifact evidence + effort=high attempt record.

### Criticality-matrix invariant

- `skills/lifecycle/references/criticality-matrix.md:11`: "The user's criticality setting is always final. No automated process (including future orchestrator additions) may override the user's choice." Anchors backlog frontmatter as authoritative.

## Tradeoffs & Alternatives

### Implementation alternatives

- **Alt A — bin/cortex-emit-lifecycle-start standalone Python shim**: New `uv run --script` Python file at `bin/cortex-emit-lifecycle-start`. Mirrors `cortex-resolve-backlog-item`/`cortex-update-item` ceremony.
  - **Pros**: reads naturally as a fourth call in refine's existing prose pattern; single new file; subprocess-testable.
  - **Cons**: violates the project.md "Skill-helper modules" directive (which prefers `cortex_command/<skill>.py` modules with `[project.scripts]` entries); duplicates frontmatter parsing logic already in `cortex_command/common.py`.

- **Alt B — Inline JSONL append in refine SKILL.md prose**: Model-executed append between Step 3 and Step 4.
  - **Pros**: zero new files; maximally legible at the call site.
  - **Cons**: directly violates CLAUDE.md "Prefer structural separation over prose-only enforcement". Reproduces the exact failure mode that caused bug 227 — prose can be silently skipped, paraphrased, or never executed. **Rejected.**

- **Alt C — Promote to cortex_command/refine.py with subcommand + `[project.scripts]` entry** (recommended by Tradeoffs Agent): New module mirroring `cortex_command/discovery.py`'s emit-* subcommand pattern. Atomic validation+mutation+telemetry. Unit-testable.
  - **Pros**: matches project.md directive verbatim; `cortex_command/discovery.py` is a near-perfect precedent (three emit-* subcommands under one console-script); pytest-testable; future emissions from refine compose under the same module.
  - **Cons (surfaced by adversarial review)**: `[project.scripts]` is CLI-wheel-only — plugin-only installs cannot invoke `cortex-refine` directly. Requires a thin `bin/` shim that wraps `python3 -m cortex_command.refine` (auto-mirrored to `plugins/cortex-core/bin/`).

- **Alt D — Hook-based emission**: A new pre-clarify-critic hook surface.
  - **Pros**: invisible to SKILL.md prose; structurally guaranteed.
  - **Cons**: hook surface doesn't exist for in-SKILL.md emission points; building one is far heavier than the bug warrants. **Out of scope.**

### Recommended approach

**Alt C with the bin/ shim correction**: `cortex_command/refine.py` holds the logic (frontmatter read, idempotency check, JSONL emit, read-after-write verify) and is unit-testable via pytest. A small shell shim at `bin/cortex-refine-emit-lifecycle-start` wraps `python3 -m cortex_command.refine emit-lifecycle-start --backlog-slug ... --lifecycle-slug ...` so the plugin distribution can invoke it. Refine SKILL.md calls the shim, not the `[project.scripts]` entry. The pattern mirrors how `cortex-update-item` is invoked from skill prose today.

## Adversarial Review

### Load-bearing concerns the spec must address

- **Resume-path skip**: Placing the emit in refine SKILL.md Step 3 prologue silently skips it on resume-from-research or resume-from-spec. The emit must be at refine entry (Step 1 or Step 2), unconditional, gated by an events.log content check — not by a phase-prose anchor.
- **Tier propagation gap**: The bug ticket scopes the fix to criticality. But `lifecycle_start` carries `{tier, criticality}` together. Emitting with criticality-only leaves tier=None (or default `simple`) in events.log. `cortex_command/pipeline/metrics.py:222-223` reads `start_events[0]` (first-wins), forbidding a "second lifecycle_start with tier filled in" later. **Two viable choices** — see Open Questions.
- **User-edited backlog drift**: Silent-skip on duplicate violates the criticality-matrix.md "user's setting is always final" guarantee when the user edits backlog `criticality:` between refine invocations. The helper should compare backlog frontmatter to most-recent events.log value and emit a `criticality_override` on drift (not a second `lifecycle_start`).
- **Plugin mirror gap**: `[project.scripts]` entries do not ride the plugin distribution channel. Helper must ship a `bin/` shim that wraps the Python module — `bin/` auto-mirrors to `plugins/cortex-core/bin/`.
- **Regression-test gap**: A pytest unit test of the helper does not verify that refine SKILL.md actually invokes it (the original failure mode). Add a **static wiring test** (grep refine SKILL.md for the canonical call site; fail if absent) alongside the unit test. Pattern precedent: `tests/test_lifecycle_kept_pauses_parity.py`, `bin/cortex-check-prescriptive-prose`.
- **Schema-version**: Add `schema_version: 1` to the new emit. Forward-compatible (readers tolerate absence as v1).
- **Ordering invariant unenforced in code**: `cortex_command/pipeline/metrics.py:222` reads `start_events[0]` (first-wins), but no write-time guard rejects a second emit. The helper's idempotency check ("skip if any `lifecycle_start` already present in events.log") closes this from the producer side.
- **Concurrent-write safety**: Follow `bin/cortex-complexity-escalator`'s bare-append + read-after-write verify pattern. Bare appends are atomic below PIPE_BUF (~4KB on macOS/Linux); verify catches torn writes.

### Adjacent issues found but out of scope

- **`cortex_command/overnight/prompts/orchestrator-round.md:256` criticality_override bug**: That prompt reads `entry.get("criticality")` for both `lifecycle_start` AND `criticality_override`. But `criticality_override` carries `to`/`from`, not `criticality`. So a user-issued criticality override is silently ignored by the orchestrator's planning fan-out. **This is a separate ticket** — the propagation fix in #234 is necessary but not sufficient for "user-final at every downstream gate." Recommend filing a new backlog item.
- **In-flight lifecycle retrofit**: The ticket marks retrofit as "Optional". For "every downstream phase gate" to hold for **existing** in-flight lifecycles (those that already silently demoted), a retrofit pass is required. The retrofit can compare backlog frontmatter to the most-recent lifecycle_start/criticality_override and emit a `criticality_override` to correct the drift. Recommend filing a new backlog item.
- **Refine SKILL.md §5 wording**: Update the "no event emission" framing to say "no phase_transition events" to make the `lifecycle_start` carve-out semantically coherent. Small wording change; can ride this lifecycle.

## Open Questions

All five items below are **Deferred: will be resolved in Spec by asking the user** per refine SKILL.md Step 5 / specify.md §3 structured interview. Each carries a recommended default that the Spec interview will present for confirmation or override.

1. **Tier-scope decision** — Deferred: will be resolved in Spec by asking the user. Should `lifecycle_start` emit both `tier` and `criticality` from backlog frontmatter (`complexity:` field for tier), or only `criticality` (leaving tier emission as a separate post-clarify event)? **Recommended default: emit both from backlog**. Backlog `complexity:` is already written back by clarify §7, so the read pattern is symmetric. Clarify §7 may emit a follow-up `complexity_override` if it rederives differently.

2. **Backlog drift behavior** — Deferred: will be resolved in Spec by asking the user. When refine re-runs on an in-progress lifecycle and the backlog `criticality:` differs from the most-recent events.log value, should the helper (a) silent-skip, (b) emit `criticality_override` reflecting the user's change, or (c) refuse to proceed with a diagnostic? **Recommended default: (b)** — preserves the "user-final" guarantee and reuses existing override schema.

3. **Retrofit for in-flight lifecycles** — Deferred: will be resolved in Spec by asking the user. The ticket marks retrofit as "Optional", but research shows it is load-bearing for the "every downstream phase gate" claim to hold for existing lifecycles. **Recommended default: out of scope; file as separate ticket** to keep this lifecycle scoped to the propagation fix.

4. **Orchestrator-round criticality_override read bug** — Deferred: will be resolved in Spec by asking the user. `cortex_command/overnight/prompts/orchestrator-round.md:256` reads `criticality` instead of `to`. **Recommended default: out of scope; file as separate ticket**. The spec will note the dependency but not block.

5. **Refine entry-point placement of the emit** — Deferred: will be resolved in Spec by asking the user. Should the emit fire at refine Step 1 (after `cortex-resolve-backlog-item` exits 0), Step 2 (after Check State determines resume point), or Step 3 (Clarify dispatch prologue)? **Recommended default: Step 2** — after `Check State` so the helper knows the lifecycle directory exists and which resume path applies.

## Considerations Addressed

(No `research-considerations` argument was passed at dispatch — section omitted by protocol.)
