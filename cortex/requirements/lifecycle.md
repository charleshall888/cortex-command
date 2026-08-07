# Requirements: lifecycle

> Last gathered: 2026-08-07

**Parent doc**: [requirements/project.md](project.md)

## Overview

The lifecycle area covers the per-feature state machine carrying a backlog item from research to a merged PR: the closed, wheel-owned transition table; the served verb class the prose loop consults instead of branching in prose; `events.log` as the only durable state and the authoritative phase source; the kept-pause taxonomy; lifecycle identity and slug resolution; `lifecycle.config.md`; and the phase artifacts and hand-offs between them.

**Boundary — narration.** How a phase is *rendered* to an operator (statusline feature/phase line, dashboard badges and phase progress, the `phase_label` projection they render through) is governed by `cortex/requirements/observability.md`, not here: this area owns the phase values and what moves between them, that one owns their display.

**Boundary — the overnight session machine.** The session-level state machine (`planning → executing → complete`, forward-only, `paused` reachable from any phase) and the runner's per-feature *status* vocabulary (`pending → running → merged`, plus `paused`/`deferred`/`failed`) belong to the pipeline and are governed by `cortex/requirements/pipeline.md`. They are a different machine from the per-feature *phase* states below; the two vocabularies must not be conflated.

**Shared vocabulary.** `tier`, `criticality`, and `short road` are defined in `cortex/requirements/glossary.md`, which loads unconditionally via `project.md`'s `## Global Context`. This doc cites them and does not restate them.

## Functional Requirements

### Phase state machine

- **Description**: The closed set of lifecycle states and edges, owned by `cortex_command/lifecycle/transition_table.py`. "Closed" is structural: consumer config selects enum-validated parameter values and can never add a state, add an edge, or reorder the topology.
- **Inputs**: the reduced `events.log` (current state plus the discriminants guards read); parameter selections from `cortex/lifecycle.config.md`; verdict and cycle at the review gate.
- **Outputs**: the current state, its outgoing edges with advisory guards, pause specs, and each edge's ordered event vocabulary; the CI-diffed render produced by `describe`.
- **Acceptance criteria** — a state machine's requirements are its transition rules and invariants:
  - The state set is closed at nine: `research`, `specify`, `plan`, `implement`, `implement-rework`, `review`, `complete`, `escalated`, `cancelled`. The last three are terminal. Each projects a legacy display phase equal to its own name, except `cancelled`, which the artifact-derived reader has no route for and which projects to `complete`.
  - Identifiers are append-only, reserve-on-deprecate: retired names move to the reserved sets and are never reused. Import-time checks fail loudly on a duplicate or reused-reserved id, an edge naming an unknown state, or an unknown edge/pause kind.
  - A config key naming no parameter has zero effect; a recognized key with an out-of-enum value raises `ClosedTableError` rather than being coerced. The edge topology is invariant across arbitrary consumer configs.
  - Every non-`error` decision arm of the four decision verbs maps to exactly one row keyed by `(owning_verb, decision_state)`, derived from the real verbs rather than a hand-copy.
  - Guards are **advisory** at read time; the authoritative check re-runs inside `advance` at act time.
  - Both forks — spec exit and implement exit — are governed by one predicate, the short road (see glossary), on the same discriminants. A corrupted reduction takes the long road.
  - `implement-rework` has exactly one exit, to `review`, taken unconditionally on the departure state: a rework is always re-reviewed and the fork predicate is not re-run.
  - `escalated` is terminal, reached from `review` on a rejected verdict at any cycle or changes-requested at cycle ≥ 2.
- **Priority**: must-have

### Served verb class

- **Description**: `next` (read-only server), `advance` (the only sanctioned writer of a state move), and `describe` (table renderer) are a bounded, wheel-owned exception to ADR-0019's dumb-arg-actor rule — they read config, resolve identity, evaluate guards, and serve instructions. `enter`, the Step-2 entry composition verb, stays a dumb arg-actor with every discriminant caller-passed.
- **Inputs**: the caller's feature token and optional phase; the main-root-anchored `events.log`; `lifecycle.config.md`; the caller-supplied protocol expectation range.
- **Outputs**: one JSON envelope per verb in the never-crash house style — always exit 0, always `{"state": …}`, never a traceback. `next` serves the state, its legacy display projection, the fragment reference, pause spec, advance contract, a pre-bound `enter` command, path overview, advisory guards, and a derivation trace.
- **Acceptance criteria**:
  - `next` never writes: no log append, no backlog write-back.
  - Every machine verb resolves a feature's `events.log` through the one pinned, worktree-aware resolver. Two callers share a flock domain iff they resolve the same physical log, so resolving it two ways forks both the state and the lock.
  - A protocol expectation outside the served range short-circuits to `protocol-skew` with a copy-pasteable remediation, rather than serving a contract the loop cannot honour.
  - `advance` refuses on a from-state gate mismatch, naming the missing evidence, the typed resume arm when one exists, and the sanctioned override (`cortex-lifecycle-event log`).
  - `advance` is idempotent per emission (parsed-field match, never substring), and an all-present invocation short-circuits as a benign replay before gating.
  - Every verb rejects an unsafe slug **before** any filesystem access.
  - `enter` never self-resolves the backend or re-derives new-vs-resume, and never auto-closes an already-complete backlog item — it returns `needs-decision` with no side effect.
  - Legacy typed transition subcommands stay callable through a coexistence window closed only by an operator-decided protocol-floor bump. → ADR-0024 (**proposed**, so not binding): the served-verb class and coexistence policy.
  - The invocation grammar is owned by a structural parser, not by prose spread across drifting surfaces. → ADR-0018 (**proposed**, so not binding): structural lifecycle invocation grammar with a docs-derived drift guard.
- **Priority**: must-have

### Event emission and events-as-phase authority

- **Description**: `events.log` is the only durable lifecycle state. Every state move appends to it, and the phase a reader reports is events-derived wherever machine rows exist.
- **Inputs**: the emitting arm's decision and discriminant fields; the existing log, read under the advisory lock before appending.
- **Outputs**: canonical `{ts, event, feature, …}` rows appended through the shared flock'd single-append writer; the reduced state every read-path caller consumes.
- **Acceptance criteria**:
  - Emission is append-only and serialized on the lockfile beside the resolved log, canonically serialized so independent readers parse machine- and hand-written rows identically. → ADR-0020 (**proposed**, so not binding): the lifecycle event emission contract and its named hand-written exempt set.
  - "Events first, else artifacts" is decided in exactly one shared resolver. A machine row is a `phase_transition` or a terminal event; `spec_approved`/`plan_approved` are deliberately not machine rows, so an approval-only log correctly falls through to the artifact fallback. → ADR-0025 (**proposed**, so not binding): events as phase authority with legacy fallback.
  - Plan progress and review-cycle count stay artifact-derived read-side facts even when the phase is events-derived, so caller field shapes are unchanged.
  - Phase-moving rows are ordered last in every arm's plan, so a crash between appends on an events-authority log resumes cleanly.
  - Readers stay tolerant of rows written by retired protocols; the corpus is mixed-format, and `project.md` carries the normative reader discipline for it.
- **Priority**: must-have

### Kept-pause taxonomy

- **Description**: The deliberate user-facing pauses are a marked taxonomy with a machine-readable source of truth. `project.md` states the taxonomy and its four kinds; this section records the lifecycle-side behavior consuming it.
- **Inputs**: the `<!-- pause: … -->` markers, the kept-pause data rows, the table's pause specs, and the reduced log for whether a pause is active.
- **Outputs**: the generated inventory; the pause block in `next`'s envelope, which the loop renders as a question surface.
- **Acceptance criteria**:
  - The served subset is exactly the rows naming a served-from state — the pause sites that are event-backed, pause-gated states in the closed table. Three-way set-equality between those rows, the table's pause specs, and the served envelopes is enforced, so no layer drifts.
  - Enforcement is scoped: `advance` refuses to cross an active event-backed pause of an enforcement-bearing kind it did not itself author, and never refuses on a judgment- or config-conditional kind — those are describe-only metadata, never a runtime refusal.
  - A pause's owning arm crosses its own pause; that crossing is the typed resume.
  - The plan gate is a single surface: the branch/dispatch modes *are* the approval options, and the chosen mode rides to implement as a field on the approval event rather than a second prompt. → ADR-0012 (accepted) ratifies the merged plan-approval and dispatch-selection surface, including the deliberate demotion of request-changes and cancel to the free-text escape.
- **Priority**: must-have

### Lifecycle identity and slug resolution

- **Description**: A lifecycle's identity is the backlog item's canonical slug; numbers, uuid prefixes, and filename stems are input normalization. `project.md` carries the normative clause in full, including the defensive coercions that must be retained.
- **Inputs**: the caller's raw feature token; backlog frontmatter; existing lifecycle directory names.
- **Outputs**: the canonical slug threaded into every command the envelope pre-binds, or a refusal.
- **Acceptance criteria**:
  - `enter` is the enforcement point: unsafe-slug, missing-lifecycle, and cross-item-uuid violations exit non-zero on stderr with no side effect.
  - `next` serves the canonical slug in its pre-bound command, never the caller's raw token, so a pasted ticket number cannot turn a valid resume into a refusal.
  - The rule governs the resolver-mediated path only: a hand-typed numeric entry still creates a numeric-keyed directory, so readers must not assume every lifecycle directory is slug-keyed.
- **Priority**: must-have

### Lifecycle configuration

- **Description**: `cortex/lifecycle.config.md` is the consumer surface for selecting lifecycle behavior. Its schema exists as two hand-maintained sources in different distribution channels — the plugin asset plugin-only users read, and the CLI init template `cortex init` drops into a repo.
- **Inputs**: the repo-root config file's frontmatter keys.
- **Outputs**: the resolved parameter selection handed to the table; the suppression signals the config-conditional pause rows consult.
- **Acceptance criteria**:
  - Dormant keys are mapped without being activated: the mapping records where an activated value would land and confines it to an enum member. Activation must be loud and deliberate.
  - The two schema sources reconcile **up** (asset ← template) behind a parity gate that byte-compares the frontmatter region, so a plugin-only user's copy is never missing a section the template gained. → ADR-0017 (accepted) ratifies reconciling and gating the two `lifecycle.config.md` sources, keeping both hand-maintained rather than generating one from the other.
- **Priority**: should-have

### Interactive dispatch and phase artifacts

- **Description**: The implement loop dispatches per-task builders from `plan.md` and checkpoints each task; the surrounding phases produce and hand off the lifecycle artifacts.
- **Inputs**: `plan.md`'s tasks and dependency edges; per-task builder exit reports; the resolver's backlog basename at index creation.
- **Outputs**: per-task git checkpoints, exit reports, artifact registrations on `index.md`, and batch-dispatch rows in `events.log`.
- **Acceptance criteria**:
  - Dispatch prose is mode-agnostic: per-task completion derives exclusively from the git checkpoint, never from the shape in which the runtime returns the report, and nothing branches on synchronous vs background dispatch. The batch barrier stays. → ADR-0030 (accepted) ratifies mode-agnostic interactive dispatch, with dependency pipelining and a per-task completion event both deferred rather than built.
  - Task identity is the composite task id, not the group ordinal, at every identity-bearing site: dependency batching, plan checkoff, exit-report filenames, the idempotency token, and the has-dependents test. → ADR-0010 (accepted) ratifies `task_id` as task identity, with the ordinal demoted to telemetry and the residual silent-merge hazard held by merge-guard tests.
  - `index.md` creation has a backlog-linked shape and an ad-hoc shape. A non-empty backlog basename that does not resolve is a contract violation, never a silent fall-back; an unlinked ad-hoc index is repaired in place once the backlog match becomes known.
  - The refine→research hand-off carries its considerations in a file and passes only the path, coupled to a same-run fresh write so absence stays structural. → ADR-0022 (**proposed**, so not binding): the explicit-path argument for that hand-off.
- **Priority**: must-have

## Non-Functional Requirements

- **Never-crash verbs**: every lifecycle machine verb exits 0 and reports through a `{"state": …}` envelope; a traceback reaching the prose loop is a defect, because the loop cannot route on one.
- **Auditability**: every state move leaves a durable row, so a feature's history is reconstructible from `events.log` alone, without a database.
- **Token economy**: the served envelope replaces prose branching rather than supplementing it — behavior belongs in the verb, prose keeps control flow. This doc loads only on a tag match, so it must not restate what `project.md` and `glossary.md` already load unconditionally.
- **Release-cadence coupling, conceded**: the transition matrix is wheel-owned while the loop body is plugin-shipped, so a gate change needs a wheel release and a skewed pair can disagree. Accepted and mitigated by the protocol handshake, not designed away.

## Architectural Constraints

- The transition table is closed and wheel-owned; topology is never consumer-selectable. Adding an operator-facing discriminant should be a display-phase suffix, not a new route value (`project.md` carries the normative phase/route rule).
- `events.log` is the only durable lifecycle state (→ ADR-0001), and events-first phase authority forfeits a cheap prose-side revert — the standing exit is roll-forward, not revert.
- Exactly one events.log resolver serves the machine verbs, which is what makes one flock domain structural rather than conventional.
- The served-verb class is a named, bounded exception to ADR-0019 and does not reopen it for other helper verbs. A served envelope may name a skill to invoke only when that skill's invocation condition is machine-readable state.
- The review phase's output-shape prescription is a protocol-governed served surface (→ ADR-0035): a brief-shape change moves the protocol version and its expectation pin in the same commit.
- Operational detail — how to run the verbs, which recipe rebuilds mirrors, how to commit — lives in `CLAUDE.md` and `docs/`, not here.

## Dependencies

- **Wheel-internal**: `cortex_command/common.py` (reducers, phase resolution, defaults), `cortex_command/lifecycle_event.py` (the locked append writer), `lifecycle_config.py`, `backlog/resolve_item.py`.
- **Plugin-shipped**: `skills/build/` and `skills/refine/` — the prose loops consuming the served envelopes — and their reference files, including the kept-pause data.
- **Backlog backend**: the spec-approval write-back is backend-gated; see `cortex/requirements/backlog.md` and ADR-0016.
- **Consumers of this area's state**: `cortex/requirements/observability.md` (statusline, dashboard) and `cortex/requirements/pipeline.md`, whose transition-decision writers route through this area's table rather than deciding independently.
- **External**: `git` and `gh` for the complete phase's PR open/merge hand-off.

## Edge Cases

- **A `plan.md` checkbox is hand-edited on a feature that already has machine rows**: the events-derived state wins; the artifact derivation gets no vote.
- **A legacy log carries no state-establishing machine row**: the artifact-presence derivation is the sanctioned fallback.
- **A crash lands between two of an arm's appends**: on an events-authority log the gate still sees the pre-transition state and re-invocation resumes; on a legacy-shaped log it refuses loudly and points at the sanctioned override rather than silently resuming.
- **The session runs inside a git worktree**: machine verbs resolve the main-repo-anchored log, so no second log or lock is forked. The typed subcommands keep their legacy CWD resolution and are a known divergence.
- **The backlog item is already complete at entry**: `enter` returns `needs-decision` before any side effect and the caller resolves close-vs-continue.
- **A lifecycle is created ad-hoc with no backlog file**: its `index.md` gets an empty tag list, so this doc's trigger cannot match and the load silently narrows to `project.md`. The repair carve-out closes this once the backlog match is known; until then, read this doc directly.
- **The plugin loop and the installed wheel disagree on protocol**: `next` short-circuits to `protocol-skew` with a remediation message.
- **A reviewer auto-appends detected drift into this doc**: it succeeds and the doc grows; there is no size brake on `cortex/requirements/` today (see Open Questions).

## Open Questions

- Whether the `## Conditional Loading` trigger matcher should be widened or replaced — today it is ASCII-casefold substring matching against an index's tags, with no word-boundary protection and a measured miss rate. Owned by backlog #472, deliberately out of scope here.
- Whether the review phase's no-area-doc warning should also fire when a listed requirements path is reported absent, not only when nothing matched. Deferred: it is a change to the review skill's warning contract.
- Whether ADR-0018, ADR-0020, and ADR-0022 — all still **proposed**, and so binding on no consumer — get promoted, amended, or retired. Until one is promoted, what each records is described here as the decision under review that it is, not as settled doctrine.
- Whether `cortex/requirements/` should gain a size brake. This doc has no token budget, is not ratcheted, and its validator is wired into no hook or CI; no runaway growth is observed yet, so the brake has not earned its place.
