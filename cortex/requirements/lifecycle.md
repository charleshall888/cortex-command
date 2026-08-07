# Requirements: lifecycle

> Last gathered: 2026-08-07

**Parent doc**: [requirements/project.md](project.md)

## Overview

This area owns the per-feature state machine carrying a backlog item from research to a merged PR, and the verbs, log, pauses, config, and phase artifacts that machine runs on.

**Boundary — narration.** This area owns the phase values and what moves between them; how a phase is *rendered* to an operator — statusline feature/phase line, dashboard badges and phase progress, the `phase_label` projection they render through — is governed by `cortex/requirements/observability.md`.

**Boundary — the overnight session machine.** The session-level state machine (`planning → executing → complete`, forward-only, `paused` reachable from any phase) and the runner's per-feature *status* vocabulary (`pending → running → merged`, plus `paused`/`deferred`/`failed`) are governed by `cortex/requirements/pipeline.md` — a different machine from the per-feature *phase* states below; the two vocabularies must not be conflated.

**Shared vocabulary.** `tier`, `criticality`, and `short road` are defined in `cortex/requirements/glossary.md`, which loads unconditionally via `project.md`'s `## Global Context`. This doc cites them and does not restate them.

## Functional Requirements

A state machine's requirements are its transition rules and invariants, so this section records those rather than a capability inventory; where a rule is ADR-backed, the cited ADR carries its rationale.

### Phase state machine

Owned by `cortex_command/lifecycle/transition_table.py`.

- The state set is closed at nine: `research`, `specify`, `plan`, `implement`, `implement-rework`, `review`, `complete`, `escalated`, `cancelled`. The last three are terminal. Each projects a legacy display phase equal to its own name, except `cancelled`, which projects to `complete`.
- Closure is structural: consumer config selects enum-validated parameter values and can never add a state, add an edge, or reorder the topology. An unrecognized key has zero effect; a recognized key with an out-of-enum value raises `ClosedTableError` rather than being coerced.
- Identifiers are append-only, reserve-on-deprecate: retired names move to the reserved sets and are never reused. Import-time checks fail loudly on a violation.
- Every non-`error` decision arm of the four decision verbs maps to exactly one row keyed by `(owning_verb, decision_state)`, derived from the verbs rather than hand-copied.
- Guards are **advisory** at read time; the authoritative check re-runs inside `advance` at act time.
- Both forks — spec exit and implement exit — are governed by one predicate, the short road (see glossary), on the same discriminants. A corrupted reduction takes the long road.
- `implement-rework` has exactly one exit, to `review`, taken unconditionally: a rework is always re-reviewed and the fork predicate is not re-run.
- `escalated` is terminal, reached from `review` on a rejected verdict at any cycle or changes-requested at cycle ≥ 2.
- A lifecycle phase may be multi-step with a user-driven re-invocation point. The Complete phase is the canonical example — it creates a PR, exits with a handoff message, and finalizes only on re-invocation after the PR is merged on GitHub. Merge (not PR-open) is the terminal event for "Done", recorded in the `feature_complete` event with `merge_anchor: "merge"`. → ADR-0004 (accepted): multi-step Complete + interactive-worktree lifecycle.

### Served verb class

- `next` (read-only server), `advance` (the only sanctioned writer of a state move), and `describe` (table renderer) are a bounded, wheel-owned exception to ADR-0019's dumb-arg-actor rule (ADR-0019 is **proposed**, so not binding): they read config, resolve identity, evaluate guards, and serve instructions from the closed transition table. `enter`, the entry composition verb, stays a dumb arg-actor with every discriminant caller-passed.
- Every verb rejects an unsafe slug **before** any filesystem access.
- `next` never writes: no log append, no backlog write-back. It serves the canonical slug in the commands it pre-binds, never the caller's raw token.
- Every machine verb resolves a feature's `events.log` through the one pinned, worktree-aware resolver; two callers share a flock domain iff they resolve the same physical log, which is what makes the single lock domain structural.
- A protocol expectation outside the served range short-circuits to `protocol-skew` with a copy-pasteable remediation, rather than serving a contract the loop cannot honour.
- `advance` refuses on a from-state gate mismatch, naming the missing evidence, the typed resume arm when one exists, and the sanctioned override (`cortex-lifecycle-event log`). It is idempotent per emission (parsed-field match, never substring); an all-present invocation short-circuits as a benign replay before gating.
- `enter` never self-resolves the backend or re-derives new-vs-resume, and never auto-closes an already-complete backlog item — it returns `needs-decision` with no side effect.
- Legacy typed transition subcommands stay callable through a coexistence window closed only by an operator-decided protocol-floor bump. → ADR-0024 (**proposed**, so not binding).
- The invocation grammar is owned by a structural parser, not by prose spread across drifting surfaces. → ADR-0018 (**proposed**, so not binding).

### Event emission and events-as-phase authority

- `events.log` is the only durable lifecycle state: every state move appends canonical `{ts, event, feature, …}` rows through the shared flock'd single-append writer, and the phase a reader reports is events-derived wherever machine rows exist.
- Emission is append-only, serialized on the lockfile beside the resolved log, and canonically serialized so independent readers parse machine- and hand-written rows identically. → ADR-0020 (**proposed**, so not binding), which also names the hand-written exempt set.
- "Events first, else artifacts" is decided in exactly one shared resolver. A machine row is a `phase_transition` or a terminal event; `spec_approved`/`plan_approved` are deliberately not machine rows, so an approval-only log correctly falls through to the artifact fallback. → ADR-0025 (**proposed**, so not binding).
- Plan progress and review-cycle count stay artifact-derived read-side facts even when the phase is events-derived, so caller field shapes are unchanged.
- Phase-moving rows are ordered last in every arm's plan, so a crash between appends resumes cleanly.
- The corpus is mixed-format: readers stay tolerant of rows written by retired protocols, under `project.md`'s normative reader discipline.

### Kept-pause taxonomy

The kept user pauses are a marked taxonomy of the deliberate, in-scope user-facing pauses across the lifecycle and refine skills. Each pause carries a `kind` — `question` (a phase blocks for an interactive answer), `phase-exit-wait` (a phase exits cleanly and waits for the user to re-invoke after an out-of-band action, e.g. merging a PR on GitHub), `config-conditional` (a pause a config key can suppress), or `relayed-consent` (a substantive approval surface whose consent overnight relays pre-authorized) — plus an orthogonal optional `suppressed_by` (a `lifecycle.config.md` key, or `judgment` for model-conditional rendering). The durable source of truth is `skills/build/references/kept-pauses-data.toml` (one row per `<!-- pause: <slug> <kind> -->` marker in skill prose); `cortex-generate-kept-pauses` renders the human-readable `skills/build/references/kept-pauses.md` from it, and `tests/test_lifecycle_kept_pauses_parity.py` is the enforcement pair — asserting marker/data set-equality, inventory freshness, and per-kind semantic anchors.

- The served subset is exactly the rows naming a served-from state: the `next` verb serves each state's pause spec in its envelope and the interactive loop renders it via AskUserQuestion, so the taxonomy is read at runtime and not only by the parity test. Three-way set-equality between those rows, the table's pause specs, and the served envelopes is enforced, so no layer drifts.
- Enforcement is scoped: `advance` refuses to cross an active event-backed pause of an enforcement-bearing kind it did not itself author, and never refuses on a judgment- or config-conditional kind — those are describe-only metadata.
- A pause's owning arm crosses its own pause; that crossing is the typed resume.
- The plan gate is a single surface: the branch/dispatch modes *are* the approval options, and the chosen mode rides to implement as a field on the approval event rather than a second prompt. → ADR-0012 (accepted) ratifies the merged surface, including the demotion of request-changes and cancel to the free-text escape.

### Lifecycle identity and slug resolution

A lifecycle's identity is the backlog item's canonical slug; numbers, uuid prefixes, and filename stems are input normalization. `project.md` carries the normative clause in full, including the defensive coercions it requires be retained.

- `enter` is the enforcement point: unsafe-slug, missing-lifecycle, and cross-item-uuid violations exit non-zero on stderr with no side effect.
- The rule governs the resolver-mediated path only: a hand-typed numeric entry still creates a numeric-keyed directory, so no reader may assume every lifecycle directory is slug-keyed.

### Lifecycle configuration

`cortex/lifecycle.config.md`'s frontmatter is the consumer surface: the parameter selection handed to the table, and the suppression signals the config-conditional pause rows consult.

- Dormant keys are mapped without being activated: the mapping records where an activated value would land and confines it to an enum member. Activation must be loud and deliberate.
- The schema has two hand-maintained sources in different distribution channels — the plugin asset plugin-only users read, and the CLI init template `cortex init` drops into a repo. They reconcile **up** (asset ← template) behind a parity gate that byte-compares the frontmatter region. → ADR-0017 (accepted) keeps both hand-maintained rather than generating one from the other.

### Interactive dispatch and phase artifacts

- Dispatch is mode-agnostic: per-task completion derives exclusively from the git checkpoint, never from the shape in which the runtime returns the report, and nothing branches on synchronous vs background dispatch. The batch barrier stays. → ADR-0030 (accepted), which defers dependency pipelining and a per-task completion event.
- Task identity is the composite task id, not the group ordinal, at every identity-bearing site: dependency batching, plan checkoff, exit-report filenames, the idempotency token, and the has-dependents test. → ADR-0010 (accepted) demotes the ordinal to telemetry; the residual silent-merge hazard is held by merge-guard tests.
- `index.md` creation has a backlog-linked shape and an ad-hoc shape. A non-empty backlog basename that does not resolve is a contract violation, never a silent fall-back; an unlinked ad-hoc index is repaired in place once the backlog match becomes known.
- The refine→research hand-off carries its considerations in a file and passes only the path, coupled to a same-run fresh write so absence stays structural. → ADR-0022 (**proposed**, so not binding).

## Non-Functional Requirements

- **Never-crash verbs**: every machine verb exits 0 with a `{"state": …}` envelope; a traceback reaching the prose loop is a defect, because the loop cannot route on one.
- **Auditability**: a feature's history is reconstructible from `events.log` alone, without a database.
- **Token economy**: the served envelope replaces prose branching rather than supplementing it. This doc loads only on a tag match, so it must not restate what `project.md` and `glossary.md` load unconditionally. Measured on 2026-08-07, when seven lifecycle-only items relocated here behind pointer stubs: `project.md` 29,918 B → 26,387 B, a 3,531 B net shrink every non-lifecycle feature stops paying (29,731 B at the start of the relocation — the routing-row fix had already removed 187 B).
- **Release-cadence coupling, conceded**: the transition matrix is wheel-owned while the loop body is plugin-shipped, so a gate change needs a wheel release and a skewed pair can disagree. Mitigated by the protocol handshake, not designed away.
- **The area-doc load, measured**: a lifecycle-tagged feature loads `project.md` + `glossary.md` + this doc = 45,487 B, against 31,094 B before this doc existed — **+14,393 B**, well above the 33,400–36,400 B projected when the work was specced. Non-lifecycle features pay −3,531 B. The shrink's beneficiary is the non-lifecycle majority; this area pays for its own coverage.

## Architectural Constraints

- **Phase boundaries are session boundaries**: the default workflow splits sessions at lifecycle phase boundaries — a fresh session after refine (spec approval) runs plan+implement, and a plan that consumed heavy context hands implement to another fresh session; phase-keyed `resume` routing is the re-entry path. Rationale: session carry is superlinear in turns (measured 37–61% of orchestrator spend); a fresh session re-caches for ~50k tokens (~0.7% of one long session's cache-read).
- Adding an operator-facing discriminant should be a display-phase suffix, not a new route value (`project.md` carries the normative phase/route rule).
- Events are the authoritative phase source wherever machine rows exist (artifact derivation is the legacy fallback), which forfeits the cheap prose-side revert — so the standing exit is the roll-forward procedure at `docs/rollforward-exit.md`, not a revert. → ADR-0025 (**proposed**, so not binding).
- The served-verb class does not reopen ADR-0019 (**proposed**, so not binding) for other helper verbs. A served envelope may name a skill to invoke only when that skill's invocation condition is machine-readable state.
- **Consumer `EnterWorktree` authorization surface**: `cortex init` writes **no** clause to consumer `CLAUDE.md`; the lifecycle implement phase authorizes `EnterWorktree` via the user's live picker selection at implement time. → ADR-0008 (accepted): picker-selection authorizes `EnterWorktree` (supersedes ADR-0006).
- The review phase's output-shape prescription is a protocol-governed served surface: `cortex-lifecycle-review-brief` emits it for both the interactive prose and the overnight pipeline, so a brief-shape change the prose depends on moves `PROTOCOL_VERSION` and `skills/build/references/protocol-expectation.txt` in the same commit. → ADR-0035 (accepted).
- **Override-reason clause vocabulary**: the closed set an override `reason` may lead with (`reversibility`, `exposure`, `consequence`, `other`) is owned by `cortex_command/refine.py:_ALLOWED_REASON_CLAUSES` and restated for authors in `skills/refine/SKILL.md` Step 4 and `cortex/adr/0036-*.md`; adding a tag edits all three, and the wheel-side change must land before the skill prose that emits it (a consumer on an older wheel fails the reconcile loudly). Both writers of an override row — `lifecycle_event.py` (typed verbs) and `refine.py` (`reconcile-clarify`) — emit the same field order `from, to, reason, gate`, with `reason` omitted rather than nulled. → ADR-0036 (accepted).
- Operational detail — how to run the verbs, which recipe rebuilds mirrors, how to commit — lives in `CLAUDE.md` and `docs/`, not here.

## Dependencies

- **Wheel-internal**: `cortex_command/common.py` (reducers, phase resolution, defaults), `cortex_command/lifecycle_event.py` (the locked append writer), `lifecycle_config.py`, `backlog/resolve_item.py`.
- **Plugin-shipped**: `skills/build/` and `skills/refine/` — the prose loops consuming the served envelopes — and their reference files, including the kept-pause data.
- **Backlog backend**: the spec-approval write-back is backend-gated; see `cortex/requirements/backlog.md` (the primary source) and ADR-0016 (**proposed**, so not binding).
- **Consumers of this area's state**: `cortex/requirements/observability.md` (statusline, dashboard) and `cortex/requirements/pipeline.md`, whose transition-decision writers route through this area's table rather than deciding independently.
- **External**: `git` and `gh` for the complete phase's PR open/merge hand-off.

## Edge Cases

- **A legacy log carries no state-establishing machine row**: the artifact-presence derivation is the sanctioned fallback. On such a log a crash mid-arm refuses loudly and points at the sanctioned override rather than silently resuming.
- **The session runs inside a git worktree**: the typed subcommands keep their legacy CWD resolution and are a known divergence from the machine verbs' main-repo-anchored resolution.
- **A lifecycle is created ad-hoc with no backlog file**: its `index.md` gets an empty tag list, so this doc's trigger cannot match and the load silently narrows to `project.md`. The repair carve-out closes this once the backlog match is known; until then, read this doc directly.

## Open Questions

- Whether the `## Conditional Loading` trigger matcher should be widened or replaced — today it is ASCII-casefold substring matching against an index's tags, with no word-boundary protection and a measured miss rate. Owned by backlog #472, out of scope here.
- Whether the review phase's no-area-doc warning should also fire when a listed requirements path is reported absent, not only when nothing matched. Deferred: it changes the review skill's warning contract.
- Whether ADR-0018, ADR-0020, and ADR-0022 — all still **proposed**, and so binding on no consumer — get promoted, amended, or retired.
- Whether `cortex/requirements/` should gain a size brake. This doc has no token budget, is not ratcheted, and its validator is wired into no hook or CI, so a reviewer's auto-appended drift note grows it unchecked; no runaway growth is observed yet, so the brake has not earned its place.
