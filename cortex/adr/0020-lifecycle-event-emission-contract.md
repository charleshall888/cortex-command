---
status: proposed
---

# Lifecycle event emission contract

## Context

Epic #336 routes deterministic lifecycle event emission through `cortex-lifecycle-event`, but supplies no explicit field-ordering/typing/serialization contract — so #330 (its foundation ticket) sets the de-facto one that #331/#332/#329 inherit.

## Decision

The verb emits a uniform `{ts, event, feature, <ordered --set/--set-json fields>}` row in canonical form (spaced `json.dumps` defaults, `%Y-%m-%dT%H:%M:%SZ` timestamps, append via flock + `O_APPEND`); `schema_version`/`worktree_path` are ordinary optional fields, not privileged keys; events whose canonical shape places `schema_version` *before* `feature` (the nested judgment events `plan_comparison`, `clarify_critic`, and #331's `pr_opened`) are exempt and stay hand-written rather than forcing positionable base-key machinery into the verb (this hand-written/exempt set is reopened from three to five by the 374 Amendment below, which adds the claim/commit pair `advance_started`/`advance_committed` for a distinct reason). The events-registry scanner recognizes `--event <name>` so gate coverage and typo-catching survive the migration.

## Trade-off / rejected alternatives

A uniform, low-machinery verb (no per-event schema registry) at the cost of a documented hand-written exception for schema_version-first/nested events, and a canonical-format definition that is byte-faithful to a *newly-defined* canonical (not to the already-format-mixed on-disk corpus). Chosen over a fully-general positionable verb (higher complexity, marginal offload for the exempt events). Hard to reverse (siblings build on the contract), surprising without context (why some events stay inline), and a real trade-off (uniformity vs. completeness) — meeting the three-criteria ADR gate.

## Amendment (374 — served advance verb, 2026-07-11)

The 374 served next/advance loop adds a **write-side `advance` verb** that executes a lifecycle transition under a two-phase **claim/commit** lock (spec R3/R12/R14). This amends — does not supersede — the contract above; it is an evolution of the *same* emission decision, recorded in-file per [`cortex/adr/README.md`](README.md)'s no-content-duplication discipline rather than minted as a new ADR. (The served-verb *class* and its coexistence policy are a distinct decision, recorded in [ADR-0024](0024-served-lifecycle-verb-class-and-coexistence.md).)

**Claim/commit two-row shape.** A transition through the primitive appends two rows instead of one:

- `advance_started` (the **claim**) — appended inside a single flock critical section spanning reduce → from-state gate-check → append. A second claimant that sees an unresolved `advance_started` for the same `(feature, from_state)` is refused with "in-flight transition".
- `advance_committed` (the **commit**) — appended in a *second* flock acquisition after side effects run. Side effects, including `gh` network calls, execute **outside** the lock — the two-acquisition split exists precisely so network never runs under flock. The commit re-acquires the lock, re-reduces, asserts no state-moving row landed since the claim, then appends; on interleaving it refuses with "state moved since claim" and names the interleaved row. A concurrency race yields exactly one `advance_committed` and one explicit refusal.

Both rows keep the canonical `{ts, event, feature, …}` serialization (`json.dumps(row)+"\n"`, default spacing) so they parse identically to the typed-subcommand rows.

**`invocation_id` semantics.** Both rows carry a deterministic `invocation_id` (business-derived, generated once, reused across retries) that links the claim to its commit. It lets a crash-recovery retry detect an orphaned `advance_started` and resume via per-side-effect existence probes rather than triggering a global halt (R12). The `advance` verb also stamps the same `invocation_id` **field-additively** onto the dual-emitted legacy-vocabulary transition rows it appends (`phase_transition`/`review_verdict`/`spec_approved`/`plan_approved`/`feature_complete`), where it distinguishes an advance-authored transition from an independent legacy emission during the dual-emission coexistence window; independent typed-subcommand emitters omit it (see the `advance-emitted invocation_id` field-additive note in `bin/.events-registry.md`).

**Exception set reopened → closed at five.** The Decision's hand-written/exempt set — the events that stay hand-written rather than routing through the uniform `--set`/`--set-json` verb — reopens from three (`plan_comparison`, `clarify_critic`, `pr_opened`, all exempt for schema_version-before-feature ordering) to **five**, adding `advance_started` and `advance_committed`. These two are exempt for a *distinct* reason: they are emitted by the claim/commit locking primitive (`cortex_command/lifecycle_event.py`), which holds the flock across read → validate → append — a hold-lock read-validate-append shape the append-only generic verb cannot express — not because of base-key ordering.

**ADR-0004 back-pointer.** The claim/commit primitive's flock discipline extends the file-based, no-database durability substrate of [ADR-0001](0001-file-based-state-no-database.md) and the multi-step / interactive-worktree lifecycle locking precedent of [ADR-0004](0004-multi-step-complete-and-interactive-worktree-lifecycle.md); `events.log` remains the only durable state and all emission stays additive-only under the contract above.

## Amendment (#397 — claim/commit protocol retired, 2026-07-17)

The 374 Amendment above is **superseded**: the claim/commit primitive, the `advance_started`/`advance_committed` machine-row pair, and the deterministic `invocation_id` were deleted from `cortex_command/lifecycle_event.py` and `cortex_command/lifecycle/advance.py`. Recorded in-file rather than as a new ADR per this directory's README — it reverses one amendment of this contract, not the contract itself.

**Evidence.** Measured across every `events.log` under `cortex/lifecycle/` and its archive — 332 files, 10,694 event rows — the protocol opened 11 claims in its entire life, every one of which committed cleanly: **zero** orphaned claims, zero in-flight collisions, zero refusals of a real collision. The requirements' deletion bias puts the burden of proof on keeping; a concurrency guard that has never once done the thing it exists to do does not meet it. The measured 11 claims also resolve the "silently serializing writers" counter-argument: the interactive loop is single-writer by construction, the overnight surfaces (`cortex-morning-review-advance-lifecycle`, the pipeline review dispatch) each advance a feature sequentially, and the interactive lock already excludes interactive/overnight concurrency on one feature — the corpus never ran two writers at once because the architecture never produces two.

**What replaced it.** `advance` keeps the events-first from-state gate (ADR-0025) inline, keeps per-emission parsed-field idempotency probes, and adds an all-emissions-present replay short-circuit; every row goes through the plain flock'd single-append writer (`log_event`/`log_event_at`), which is load-bearing and survives. The `cortex-lifecycle-event log` escape hatch survives unchanged (operator req 7). The trade accepted: a crash *between* two appends on a legacy-shaped log (no `phase_transition` row yet, artifact-fallback detection) can no longer silently resume — it refuses loudly at the gate with the sanctioned override. On the served loop's normal events-authority logs, phase-moving rows are ordered last, so the crash-resume property holds without the machine rows.

**Exception set closes back at three.** The Decision's hand-written/exempt set returns to `plan_comparison`, `clarify_critic`, `pr_opened`.

**Historical rows stay valid.** Logs written during the protocol's window carry the machine rows and `invocation_id` fields; every reader remains tolerant of them (pinned by `tests/test_lifecycle_reverse_golden.py`), and the events-registry rows are marked `deprecated-pending-removal` rather than dropped.
