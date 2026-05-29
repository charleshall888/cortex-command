# Specification: extract-interview-skill

## Problem Statement

Cortex has a one-at-a-time interview "grilling" loop embedded inside `requirements-gather`, with its cadence rule verbatim-duplicated into the lifecycle Spec interview (`specify.md:42`) and hand-synced via reciprocal "Mirrored in … update both" notes. There is no way to invoke that grilling on its own to prime a working session. This feature (a) creates a standalone, user-invocable `/interview` skill that interviews the user one question at a time — accumulating answers in conversation context so the user can then proceed with a well-primed prompt — and (b) single-sources the **verbatim-duplicated one-at-a-time cadence rule** so `requirements-gather` points at a canonical copy instead of hand-syncing, and `specify.md`'s note is repointed at the same canonical copy. The pattern mirrors Matt Pocock's chain: standalone `/interview` ≈ grill-me (context priming); `requirements-gather` ≈ grill-with-docs (interview, then synthesize an artifact). It benefits the user (a reusable priming tool) and maintainers (the verbatim cadence dup is killed). The DRY scope is deliberately narrow: only the cadence rule is single-sourced; grounding-entangled rules (recommend-before-asking, codebase-trumps) stay caller-owned because they differ in substance per caller.

## Phases

- **Phase 1: Standalone `/interview` skill** — Create a first-class, user-invocable grilling skill and the canonical interview-loop reference it follows. Independently shippable; satisfies the core ask.
- **Phase 2: Single-source the cadence rule** — Repoint `requirements-gather`'s verbatim cadence block at the canonical loop, and repoint `specify.md`'s cross-reference note at it too (text-only). Pure refactor; no interview-behavior change.

## Requirements

1. **Standalone skill exists with verified routing disambiguation**: Create `skills/interview/SKILL.md` as a top-level, user-invocable skill with required `name: interview`, a `description:` scoped as a *general-purpose priming interview* (clearly distinct from `backlog-author`'s ticket-authoring `interview` subcommand), optional `when_to_use:` / `argument-hint:`. Routing disambiguation is **verified**, not asserted: using the `/skill-creator:skill-creator` eval harness (in scope per Technical Constraints), confirm representative "interview me about X" phrasings route to `/interview` and ticket-authoring phrasings still route to `backlog-author`. Acceptance: `grep -c '^name: interview' skills/interview/SKILL.md` = 1 AND a skill-creator routing eval run shows both skills resolve correctly for their representative phrasings (eval output captured in the implementation notes; pass = no mis-route in the representative set). If the eval shows a residual collision, R14 fires. **Phase**: Phase 1: Standalone `/interview` skill

2. **Canonical interview-loop reference**: Create `skills/interview/references/loop.md` holding the interview-loop mechanics `/interview` follows: (a) one-at-a-time cadence (previous answer gates the next; this is the rule single-sourced in Phase 2); (b) recommend-before-asking, with recommendations suppressed on taste/preference questions; (c) codebase-trumps-interview (explore code before asking when recoverable, then confirm); (d) funnel ordering (broad/open first, narrow/closed last); (e) saturation-based stopping (stop when new answers stop changing the picture) with early-exit allowed and a soft cap against over-interrogation. `loop.md` is both `/interview`'s loop spec and the canonical source for the cadence rule (a) that Phase 2 repoints other surfaces at. Acceptance: file exists and `grep -ciE 'one at a time|recommend|codebase|funnel|saturation|cap' skills/interview/references/loop.md` ≥ 5. **Phase**: Phase 1: Standalone `/interview` skill

3. **`/interview` follows the canonical loop via read-and-follow**: `skills/interview/SKILL.md` directs reading and following `skills/interview/references/loop.md` (the `load-requirements.md` idiom) rather than restating the loop inline. Acceptance: `grep -c 'references/loop.md' skills/interview/SKILL.md` ≥ 1. **Phase**: Phase 1: Standalone `/interview` skill

4. **Topic anchor — arg or context**: `/interview` accepts an optional topic argument and falls back to the pending goal in conversation context when omitted; when neither is present, it asks one question to establish the topic rather than guessing. Acceptance: `argument-hint:` present in frontmatter; SKILL.md prose describes both paths. Interactive/session-dependent for runtime behavior: rationale — the topic-resolution branch only manifests at invocation. **Phase**: Phase 1: Standalone `/interview` skill

5. **Conversational one-at-a-time grilling, answers in context, not AskUserQuestion**: `/interview` conducts the loop as plain-text conversational Q&A (one question, await reply, next question shaped by the answer) and explicitly does NOT route the grilling through batched `AskUserQuestion` calls; `loop.md` states this with its rationale (batching breaks the previous-answer-gates-next-question cadence, and the grilling is conversational priming, not a structured pick-menu). Answers accumulate in conversation context for the user to proceed from. Acceptance: `grep -ciE 'AskUserQuestion' skills/interview/references/loop.md skills/interview/SKILL.md` ≥ 1 in a sentence that excludes it from the grilling cadence (interactive confirmation). Interactive/session-dependent for runtime cadence: rationale — questioning cadence is observable only during a live session; a conversational cadence cannot be structurally gated, so it is prose-specified with rationale per the medium. **Phase**: Phase 1: Standalone `/interview` skill

6. **Stop control = saturation + user-stop + soft cap (no template-coverage assumption)**: Because a standalone interview has no template/section-list to "cover," the stop criterion is **saturation** — stop when the user's answers stop changing the picture (new questions add nothing new) — NOT template-coverage. The user can stop early at any time, and a soft cap surfaces a "we've covered a lot — keep going or wrap up?" check to prevent over-interrogation. Acceptance: `loop.md` prose defines the stop as saturation (not coverage-of-a-template) and names user early-stop and the soft cap. **Phase**: Phase 1: Standalone `/interview` skill

7. **Brief offered, requestable at any point**: `/interview` offers a concise brief of the accumulated Q&A at conclusion; the user may also request the brief at any point mid-interview (partial mitigation for `/clear`/compaction loss). Default is an in-conversation summary; on request it writes the brief to a user-specified path (no hardcoded output location). The brief is offered, never forced. Acceptance: SKILL.md prose describes the offered brief, the request-anytime affordance, the in-conversation default, and the user-specified-path write option. **Phase**: Phase 1: Standalone `/interview` skill

8. **Soft-positive authoring**: `skills/interview/SKILL.md` and `skills/interview/references/loop.md` use soft positive-routing phrasing with zero new MUST/CRITICAL/REQUIRED escalation tokens (per the `CLAUDE.md` MUST-escalation policy; no evidence artifact is being supplied). Acceptance: `grep -cE '\b(MUST|CRITICAL|REQUIRED)\b' skills/interview/SKILL.md skills/interview/references/loop.md` = 0. **Phase**: Phase 1: Standalone `/interview` skill

9. **Plugin distribution wiring**: Add `interview` to the cortex-core `SKILLS=(...)` allowlist at `justfile:582` and regenerate the plugin mirror so `plugins/cortex-core/skills/interview/` is byte-identical to canonical. Acceptance: `sed -n '582p' justfile | grep -c '\binterview\b'` ≥ 1 (the cortex-core list, not the overnight list at :588); `just build-plugin` leaves the tree clean (pre-commit drift hook passes). **Phase**: Phase 1: Standalone `/interview` skill

10. **Size and parity hygiene (Phase 1)**: `skills/interview/SKILL.md` stays within the 500-line cap and trips no SKILL.md-to-bin parity rule (prose-only, no `bin/cortex-*` helper). Acceptance: `just test` exits 0 (covers `tests/test_skill_size_budget.py` and parity). **Phase**: Phase 1: Standalone `/interview` skill

11. **`requirements-gather` single-sources only the cadence rule (lossless)**: Replace ONLY `requirements-gather`'s verbatim-duplicated one-at-a-time cadence block (`### Ask one at a time` :31-33, the block carrying the "Mirrored in specify.md" note) with a read-and-follow pointer to the cadence rule in `skills/interview/references/loop.md`, and remove the now-obsolete mirror note. Its grounded `### Recommend before asking` (:27-29, with "Recommendations are grounded — derived from explored code, the existing target doc, the parent requirements … none — open question" fallback) and `### Codebase trumps interview` (:23-25, with "Reserve interview questions for intent, priorities, scope boundaries, and non-functional bars …") stay INLINE — they are requirements-specialized and are NOT extracted. Acceptance: `grep -c 'references/loop.md' skills/requirements-gather/SKILL.md` ≥ 1; `grep -c 'Mirrored in' skills/requirements-gather/SKILL.md` = 0; AND lossless-extraction check — `grep -c 'Recommendations are grounded' skills/requirements-gather/SKILL.md` ≥ 1 AND `grep -c 'Reserve interview questions' skills/requirements-gather/SKILL.md` ≥ 1 (the grounding and scope-reservation clauses still present). **Phase**: Phase 2: Single-source the cadence rule

12. **`specify.md` cross-reference repointed at canonical (text-only, no orphaning)**: Repoint `skills/lifecycle/references/specify.md:42`'s `**Cadence**` mirror note at `skills/interview/references/loop.md` as the canonical cadence source (e.g. "This cadence is the canonical rule at `skills/interview/references/loop.md`"). Do NOT take the "drop the note" branch — that would orphan specify.md's inline cadence with zero cross-reference and make drift more likely. This is a text-only edit to the `**Cadence**` bullet; it does not alter specify.md's interview behavior and does not move the kept-pause `AskUserQuestion` sites. Acceptance: `grep -c 'interview/references/loop.md' skills/lifecycle/references/specify.md` ≥ 1 (canonical reference present); `grep -c 'Mirrored in .*requirements-gather' skills/lifecycle/references/specify.md` = 0 (stale reciprocal claim gone); `python3 -m pytest tests/test_lifecycle_kept_pauses_parity.py` exits 0. **Phase**: Phase 2: Single-source the cadence rule

13. **No functional regression**: `requirements-gather`'s externally-observable behavior (one-at-a-time interview, grounded recommend-before-asking, codebase-first, glossary writes, Q&A block, orchestrator handoff) is preserved after the repoint; the full suite passes. Acceptance: `just test` exits 0. **Phase**: Phase 2: Single-source the cadence rule

14. **Conditional `backlog-author` description clarification (eval-gated)**: This requirement fires ONLY if R1's routing eval shows a residual `/interview` ↔ `backlog-author` collision. If it fires: make a minimal text-only clarification to `backlog-author`'s `description`/`when_to_use` so its `interview` trigger reads unambiguously as backlog-ticket authoring (e.g. qualify the bare "interview" token). This does NOT change `backlog-author`'s `interview` subcommand or its behavior. Acceptance: if fired, the routing eval re-run shows both skills resolve correctly AND `backlog-author`'s subcommand surface is unchanged (`grep -c 'interview|compose' skills/backlog-author/SKILL.md` unchanged for the subcommand declaration); if not fired, N/A (R1's eval passed without it). **Phase**: Phase 1: Standalone `/interview` skill

## Non-Requirements

- Does NOT converge `specify.md`'s interview *behavior* — only a text-only cross-reference repoint (R12). specify.md keeps its own inline cadence prose and all its pauses.
- Does NOT change `backlog-author`'s `interview` subcommand or its interview behavior. A minimal description-text clarification is permitted only if R14's eval gate fires.
- Does NOT extract `requirements-gather`'s grounded recommend-before-asking or codebase-trumps clauses — only the verbatim-duplicated cadence rule is single-sourced.
- Does NOT do full convergence across all interview surfaces (`backlog-author`'s cadence near-copy is out of scope — different domain logic).
- Does NOT force a brief/artifact — the brief is offered, and standalone working mode is context accumulation.
- Standalone `/interview` does NOT synthesize requirements docs or specs — answer disposition is the caller's job.
- Does NOT add a `bin/cortex-*` helper, a Python module, or any state/event emission — prose-only skill.
- Does NOT move `specify.md`'s kept-pause `AskUserQuestion` sites (lines 36/67/155) or alter the kept-pauses inventory.
- Does NOT add MUST/CRITICAL/REQUIRED escalation language.

## Edge Cases

- **User stops immediately / answers nothing**: the interview exits gracefully; no brief is forced and no error.
- **No topic arg and no clear context goal**: `/interview` asks a single question to establish the topic rather than fabricating one.
- **Saturation never reached / user keeps answering**: the soft cap surfaces a "keep going or wrap up?" check rather than interrogating indefinitely. (For a standalone topic, saturation and the soft cap may converge into one operative stop — acknowledged.)
- **`/clear` or context compaction mid-interview**: in-progress priming is lost (documented limitation); mitigations are the at-conclusion offered brief AND the request-anytime brief affordance (R7), but a user who never requests it before `/clear` still loses in-progress priming.
- **Recommend-before-asking on a taste/preference question**: the recommendation is suppressed and the question is posed open, to avoid anchoring the user's genuine preference (no synthesis firewall exists in context-only mode).
- **`requirements-gather` after repoint**: its grounded recommend-before-asking and the "reserve questions for intent/priorities/scope" clause stay inline (R11) — pointing at `loop.md` for the cadence must not drop the grounding or scope-reservation.
- **Routing "interview me about X"**: resolves to the top-level `/interview` skill, verified by the R1 routing eval (not assumed); `backlog-author`'s ticket-authoring `interview` must still route to it.

## Changes to Existing Behavior

- ADDED: a new top-level `/interview` skill — extends the available-commands surface.
- MODIFIED: `requirements-gather`'s verbatim cadence block → a read-and-follow pointer to `skills/interview/references/loop.md` (grounded recommend + codebase clauses kept inline; behavior preserved).
- MODIFIED: `skills/lifecycle/references/specify.md:42` cadence note repointed at the canonical `loop.md` (text-only; no behavior change).
- CONDITIONALLY MODIFIED: `backlog-author`'s description text, only if R14's routing-eval gate fires.
- ADDED: `interview` entry in the `justfile:582` cortex-core build-plugin allowlist (+ generated plugin mirror).

## Technical Constraints

- **Dual-source mirror**: edit canonical `skills/` only; regenerate `plugins/cortex-core/skills/` via `just build-plugin`; `.githooks/pre-commit` enforces drift. Requires the skill name in the `justfile:582` allowlist.
- **Kept-pauses parity**: the `specify.md` edit must not move the pause anchors at 36/67/155 (a same-line-count text replacement preserves them; ±35-line tolerance); `tests/test_lifecycle_kept_pauses_parity.py` must stay green.
- **MUST-escalation policy**: soft positive-routing only; no new escalation tokens absent an evidence artifact.
- **Prescribe What and Why, not How**: author `loop.md` and the SKILL.md as decision rules + intent, not procedural narration. Note (per critical-review): a conversational interview cadence is intrinsically a live-session property and cannot be structurally gated; it is prose-specified with rationale, accepting that no automated test catches a runtime revert — this is a deliberate limitation of a conversational prose skill, not an oversight.
- **SKILL.md 500-line cap** (`tests/test_skill_size_budget.py`); **bare-Python skill-invocation prohibition L201** (no `cortex_command` imports in skill markdown).
- **Distribution**: skills ship via plugins, not the wheel (ADR-0002).
- **Authoring + verification tool**: build the new skill via `/skill-creator:skill-creator` (user-directed) and use its eval harness for the R1 routing verification; commit via `/cortex-core:commit`.

## Open Decisions

None blocking. One scope nuance is surfaced at approval rather than deferred: R14 permits a minimal `backlog-author` description-text clarification *if* the routing eval shows the collision persists — this nudges the earlier "don't touch backlog-author" boundary and is flagged for operator confirmation at the approval surface.

## Proposed ADR

None considered.
<!-- A standalone-skill addition consuming a shared reference is reversible (re-inline the cadence) and unsurprising given the existing load-requirements.md sharing idiom; it does not meet the three-criteria ADR gate. The prior adopt-one-at-a-time-grilling lifecycle likewise added/edited these surfaces without an ADR. -->
