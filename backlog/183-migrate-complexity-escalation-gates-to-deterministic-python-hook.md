---
schema_version: "1"
uuid: 4b8690e5-7efd-431b-bec5-b45ef64dcc66
title: "Migrate both complexity-escalation gates to deterministic Python hook (`cortex-complexity-escalator`); no deletions"
type: feature
status: complete
priority: medium
parent: 172
blocked-by: []
tags: [lifecycle, hooks, complexity-escalation, token-efficiency, deterministic-execution, vertical-planning]
created: 2026-05-06
updated: 2026-05-11
discovery_source: cortex/research/vertical-planning/research.md
complexity: complex
criticality: high
spec: cortex/lifecycle/migrate-gate-1-researchspecify-open-questions-escalation-to-python-hook-remove-gate-2-entirely/spec.md
areas: [lifecycle]
session_id: null
lifecycle_phase: complete
---

# Migrate both complexity-escalation gates to deterministic Python hook (`cortex-complexity-escalator`); no deletions

Per the audit's Hold-1 resolution (`research/vertical-planning/audit.md:400`, "**Resolution: keep both gates**" + "**move both gates to a deterministic Python hook (`cortex-complexity-escalator`) on research→specify and specify→plan transitions**"), and per the post-refine-research re-scoping (2026-05-11) that reverted an earlier inversion of the audit prescription: **migrate BOTH gates to a uniform Python hook**. Gate 1 (Research → Specify, ≥2 `## Open Questions` bullets in `research.md`) AND Gate 2 (Specify → Plan, ≥3 `## Open Decisions` bullets in `spec.md`) both move to `bin/cortex-complexity-escalator` invoked by a one-line SKILL.md protocol step at each transition. **No deletions** — both gates' prose collapses to one-line pointers; both gates' behavior is preserved by the new mechanism.

## Why the scope reverted to symmetric

A prior decomposition (DR-2) re-scoped this ticket to asymmetric treatment ("migrate Gate 1; remove Gate 2 entirely") on the basis that Gate 2 had "0 fires across 153 lifecycles." Adversarial review during the 2026-05-11 refine pass surfaced:

1. **The "0 fires" empirical claim is unverifiable** — no events.log payload encodes gate provenance. Eleven historical specs (mostly archived) have ≥3 `## Open Decisions` bullets and would have been Gate-2-eligible by the prose-stated rule; whether the gate fired or was bypassed is unattributable from the corpus.
2. **Selection-effect alternative interpretation** — the active-corpus low Gate-2-eligibility could be evidence the gate **works as a forcing function** (model avoids parking ≥3 things in Open Decisions), not that it's unused.
3. **Audit-resolution divergence** — the audit explicitly says "keep both gates," explicitly couples Gate 2 to #180 D4 blocking, and prescribes Tier 3 hook migration for both gates symmetrically.

Reverting to symmetric scope restores audit alignment, doesn't bet on the unverifiable empirical premise, and lets future tickets data-drive any deletion decisions using the new `gate` provenance field that this ticket adds.

## Context (preserved from prior framing)

Trade-offs that motivate the migration (apply to both gates symmetrically):
- **Model tokens at gate-evaluation time**: drop to ~zero (hook runs in Python, not in model context)
- **Algorithmic specifiability**: the bullet-counting algorithm becomes pytest-testable rather than model-discretionary
- **Infrastructure cost**: adds one new utility to deploy/test/maintain
- **Precedent**: cortex already has hooks for similar deterministic work (`bin/cortex-update-item`, `bin/cortex-resolve-backlog-item`)

**Honest framing (per refine adversarial review FM-6)**: the migration is **prose compression with algorithmic side-pin**, not a true "determinism migration" — the trigger remains the model executing one SKILL.md line. The win is at the evaluation layer (algorithm becomes specifiable, prose tokens drop, event shape becomes uniform), not at the trigger layer.

Audit § *"Tier 3 — Move execution out of the model entirely"* (note: "Tier 3" is cortex-internal vocabulary; not in Anthropic skill-authoring docs).

## What to land

### 1. `bin/cortex-complexity-escalator` (single utility, both gates)

A Python script at `bin/cortex-complexity-escalator` (no `.py` suffix — cortex `bin/cortex-*` convention) that takes the lifecycle feature slug and a `--gate` parameter (`research_open_questions` or `specify_open_decisions`) and:

- Reads `lifecycle/{feature}/events.log` to detect current tier; skips if already `complex`. Recognizes all three existing `complexity_override` payload shapes (standard `{from, to}`, YAML-style, and test-fixture `{tier}`).
- For `--gate research_open_questions`: reads `lifecycle/{feature}/research.md`, counts bullets under `## Open Questions` (algorithm specified in spec; Refine-aligned bare-unannotated semantic per `skills/refine/SKILL.md:149` to avoid over-escalation on explicitly-deferred items), escalates if ≥2.
- For `--gate specify_open_decisions`: reads `lifecycle/{feature}/spec.md`, counts bullets under `## Open Decisions` (analogous semantic; algorithm to be specified in spec phase), escalates if ≥3.
- Appends `complexity_override` event to events.log on escalation, with new **`gate` field** containing the gate identifier for future event-source attribution (closes the FM-1 attribution gap; data-drives future Gate-1-vs-Gate-2 retention decisions).
- Verifies the write via read-after-write before announcing (defends against silent sandbox denial in overnight contexts; see refine adversarial SEC-1).
- Path-traversal hardening: feature-slug regex `^[a-zA-Z0-9._-]+$` + realpath containment under `lifecycle/`.
- Emits announcement on stdout (consumed by the model in the protocol step's output).
- Graceful no-op when research.md/spec.md is missing, the named section is absent, tier is already complex, or events.log is unwritable.

Schema source-of-truth correction: canonical per-feature events.log writer is `cortex_command/pipeline/state.py:288 log_event` (plain atomic append, no schema validation) — NOT `cortex_command/overnight/events.py` as the original ticket cited. The new `gate` field is purely additive at the writer level.

### 2. SKILL.md gate-prose collapse (symmetric, both gates)

In `skills/lifecycle/SKILL.md`:
- **Gate 1 site (lines 259–268)**: collapse to one line — *"At the Research → Specify transition, run `cortex-complexity-escalator <feature> --gate research_open_questions`. The hook handles tier detection, bullet-counting, escalation, and event emission deterministically."*
- **Gate 2 site (lines 270–274)**: collapse to one line — *"After spec approval, before the Specify → Plan transition, run `cortex-complexity-escalator <feature> --gate specify_open_decisions`. Same hook, different gate."*
- Strip the Gate-2 cross-reference at line 268.

In `skills/refine/SKILL.md`: line 161 (§3b tier detection) is already source-agnostic; no edit needed.

### 3. Hook tests (cover both gates)

Add tests for:
- Hook reads events.log correctly and identifies current tier across all three payload shapes
- Hook counts bullets correctly per the algorithm spec — including named edge cases: numbered lists (excluded? counted as bullets?), `- Deferred:` and `- Resolved:` prefix handling (Refine-aligned), fenced code blocks (excluded), blockquoted bullets (excluded), sub-bullets (top-level only), horizontal rules
- Hook skips silently when tier is already complex
- Hook emits well-formed `complexity_override` event with `gate` field
- Hook handles missing files / missing sections gracefully
- Read-after-write verification fires when sandbox denies write
- Path-traversal rejection (feature slug regex + realpath containment)
- Both gates' invocations work end-to-end against representative fixtures

### 4. Rollback signal definition (for future-self)

Define in spec: if either gate's empirical fire rate (now attributable via `gate` field) shows a class of features that should have escalated but did not (or vice versa), define the watch-list, review cadence, and restoration path. This is not work for this ticket — it's the data-collection-enabling artifact that this ticket's `gate` field unlocks.

## Risks

- **Trigger-mechanism choice (Approach B per refine research)**: explicit invocation from a one-line SKILL.md protocol step. Honest framing: the model still triggers the hook. Determinism is at the evaluation layer, not the trigger layer. FileChanged hooks exist per Anthropic docs (since Claude Code 2.1.83) but cortex has zero precedent; first-adoption risk + known bugs (GH #44925, #14281) make this not the right ticket for first FileChanged use. PostToolUse alternative was rejected for trigger-vs-transition semantic mismatch (multi-fire during iterative authoring).
- **Bullet-counting algorithm semantic alignment** — Refine's existing gate definition (`skills/refine/SKILL.md:149`) distinguishes resolved/deferred/bare-unannotated; the hook's algorithm MUST align with this or it over-escalates. Spec must specify the exact algorithm with pytest fixtures for each named edge case.
- **Idempotency** — hook must guard against re-firing on the same feature (existing-event check). Monotonic-upward semantic (escalation only; no auto-downgrade) is documented explicitly.
- **Sandbox / permissions** — cortex-init already registers `lifecycle/` in `sandbox.filesystem.allowWrite`. Read-after-write verification protects against silent denial in `--dangerously-skip-permissions` overnight contexts.
- **Backwards compatibility** — existing in-flight features with `complexity_override` events written in pre-v2 shape must continue to read correctly. Hook's "already escalated" guard recognizes all three production payload shapes.

## Touch points

- `bin/cortex-complexity-escalator` (NEW; Python, no extension)
- `skills/lifecycle/SKILL.md` (both gate-prose sites collapse to one-line pointers)
- `tests/test_complexity_escalator.py` (NEW; covers both gates' invocations)
- `plugins/cortex-core/bin/cortex-complexity-escalator` (auto-mirrored by `justfile:521` rsync)
- `plugins/cortex-core/skills/lifecycle/SKILL.md` (auto-mirrored by `justfile:499`)

## Verification

- A fresh research → specify transition with `lifecycle/{feature}/research.md` containing ≥2 bare-unannotated `## Open Questions` bullets fires the hook, escalates to Complex tier, appends `complexity_override` event with `gate: "research_open_questions"`, and emits the announcement
- A fresh specify → plan transition with `lifecycle/{feature}/spec.md` containing ≥3 bare-unannotated `## Open Decisions` bullets fires the hook, escalates to Complex tier, appends `complexity_override` event with `gate: "specify_open_decisions"`, and emits the announcement
- A transition where active tier is already `complex` skips the hook silently (no event emitted) at both gates
- A transition where the relevant section is absent skips the hook silently (no event emitted)
- Bullets that match the Refine-defined "deferred" or "resolved" prefix forms are NOT counted (no over-escalation)
- Read-after-write verification rejects the escalation if the appended event does not appear on re-read
- Path-traversal feature-slug rejection works (`../foo` returns non-zero exit)
- `wc -l skills/lifecycle/SKILL.md` shows the prose collapse (target: drop ~14 lines net, both gates combined)
- All hook tests pass
- Pre-commit dual-source drift hook passes after `just build-plugin`
