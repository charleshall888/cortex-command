---
status: proposed
---

# Served lifecycle verb class and coexistence

## Context

The 374 served next/advance loop moves the lifecycle's phase-routing brain out of skill prose and into three wheel-owned verbs: `next` (read-only — reduces `events.log`, resolves identity, evaluates guards, and *serves* a well-formed instruction envelope for the current state), `advance` (write-side — executes the served transition under the claim/commit lock), and `describe` (renders a state's contract). The interactive loop body (`skills/lifecycle/SKILL.md`) shrinks to a thin consumer of the served envelope.

This collides with two existing boundaries that need explicit reconciliation:

1. **[ADR-0019](0019-skill-helper-verb-backend-structural-guard.md)'s dumb-arg-actor rule.** ADR-0019 sanctioned a `cortex-*` skill-helper verb acting on a *caller-passed* `--backend` value "purely as a structural guard, provided it does not resolve the backend itself and contains no external-tracker adapter logic" — a deliberately bounded concession that keeps helper verbs dumb arg-actors. `next`/`advance` categorically exceed that bound: they read config themselves (`lifecycle_config.py`), resolve feature identity, evaluate transition guards, and serve instructions. Sanctioning them *silently* under ADR-0019 would be exactly the scope creep ADR-0019's "hard-to-reverse is the precedent, not the code" clause warns against — the next contributor would cite the served verbs to justify arbitrary backend logic in any helper verb.

2. **A new skill-invocation directive class.** The served envelope may *name a skill for the loop to invoke* (e.g. a pause rendered via AskUserQuestion, or a phase skill). That is a new capability — a wheel verb directing which skill runs — and it needs a stated bound so it does not become an open-ended dispatch mechanism.

The served model also couples correctness to the wheel↔plugin version boundary that [ADR-0009](0009-skill-path-resolution-for-plugin-distributed-skills.md) mapped as a skew surface: the gate/transition matrix is wheel-owned, but the loop body ships in the plugin, so a skewed pair can disagree.

## Decision

Record a **served-lifecycle-verb class** as a bounded, sanctioned exception to ADR-0019 rather than an unmarked extension of it.

- **Served-verb bound.** `next`/`advance`/`describe` are sanctioned to read config, resolve identity, evaluate guards, and serve instructions — the capabilities ADR-0019 withholds from dumb-arg-actor helper verbs. The bound: they are the *only* verbs granted this; they own the closed, wheel-owned transition table (config selects parameters only — it can never introduce a state or edge); and they keep the never-crash exit-0 `{"state": …}` house envelope style. This does not reopen ADR-0019 for other helper verbs; it carves one named class out from under it.
- **Skill-invocation directive bound.** A served envelope may name a skill to invoke **only when that skill's invocation condition is machine-readable state** (a reduced `events.log` predicate). It may not encode judgment-conditional or free-prose dispatch. This keeps the directive a projection of durable state, not a general dispatcher.
- **Release-cadence cost, conceded.** Because the gate/transition matrix is wheel-owned while the loop body is plugin-shipped, a gate-matrix change requires a wheel release to take effect, and a skewed plugin↔wheel pair can disagree. This coupling cost is accepted (mitigated by the per-verb protocol handshake and the SessionStart background-install healer, ADR-0026), not designed away.

## Coexistence policy

The absorbed/typed transition subcommands (`phase-transition`, and the B1 verbs' transition modes) are **not retired** by this build. They:

- stay **callable** for out-of-repo / stale-plugin consumers until a later **protocol-floor bump** decided by the operator (telemetry-informed, not calendar-driven). Retirement, when it comes, runs through the standard `bin/.events-registry.md` `deprecated-pending-removal` template with a **named owner** (the #377 lesson) — but on a *different trigger* than a calendar grace window: a protocol-floor bump, not a 30-day clock;
- lose their **in-repo prose invocations** at Phase 5 (R17): all shipped skill/prompt prose stops commanding them, which narrows the coexistence window to out-of-repo/stale-plugin callers only. The verbs remain callable; no shipped prose commands them.

During the dual-emission window the `advance` verb emits the exact legacy event vocabulary as primary rows (so old readers parse them) plus additive machine rows, and stamps an optional `invocation_id` onto the legacy-vocabulary rows so an advance-authored transition is distinguishable from an independent legacy emission of the same event (see [ADR-0020](0020-lifecycle-event-emission-contract.md)'s 374 amendment and the `bin/.events-registry.md` field-additive note).

## Trade-off / rejected alternatives

- **Extend ADR-0019 silently (rejected).** Let `next`/`advance` ride under ADR-0019's existing concession without a new record. Rejected: it erases the dumb-arg-actor bound ADR-0019 drew and hands the next contributor a precedent for arbitrary helper-verb logic — the precise hard-to-reverse failure ADR-0019 records.
- **Retire the legacy verbs immediately (rejected).** Cut the typed subcommands in the same build. Rejected: out-of-repo and stale-plugin consumers still call them; a coexistence window closed by a telemetry-gated protocol-floor bump is safer than a hard cut and is the reversible path.
- **Prose-only served loop (rejected).** Keep routing in skill prose and skip the wheel verbs. Rejected on the [ADR-0018](0018-structural-lifecycle-invocation-grammar.md) precedent: prose-only lifecycle routing has already drifted (the shipped-broken `complete <slug>` parse), so the routing brain belongs in a unit-tested wheel verb, not model-remembered prose.

## Three-criteria gate clearance

- **Hard to reverse.** The served-verb class becomes the routing substrate the loop body, the transition table, and every migrated caller depend on; unwinding it means re-prosifying routing across all of them and re-litigating the ADR-0019 boundary — a coordinated multi-call-site change, not a one-file edit. `events.log` remains the only durable state ([ADR-0001](0001-file-based-state-no-database.md)), and the claim/commit lock extends the interactive-worktree lifecycle locking precedent of [ADR-0004](0004-multi-step-complete-and-interactive-worktree-lifecycle.md).
- **Surprising without context.** A contributor meeting `next`/`advance` would reasonably read them as ordinary helper verbs and propose folding them back under ADR-0019, unaware that the served-verb class is a *deliberately* bounded exception and that the legacy verbs are kept callable on purpose during coexistence.
- **Real trade-off.** A bounded, wheel-owned served-verb class (with a conceded release-cadence coupling cost and a coexistence window) was chosen over both a silent ADR-0019 extension and an immediate hard cut, each rejected for stated reasons above.
