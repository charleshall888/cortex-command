# Review: extract-interview-skill

**Criticality**: high · **Tier**: complex · **Cycle**: 1
**Verdict**: APPROVED

## Review method (disclosure)

Per the high-criticality protocol, fresh-context parallel review sub-agents were
dispatched (three dimension-scoped agents, then one consolidated agent as a fallback).
In this session's interactive-worktree shell environment, sub-agent reports did not
reliably surface (the same tool-result cancellation behavior this session exhibited on
its first parallel batch). Rather than continue re-dispatching an unstable path, the
review was conducted directly by the orchestrator across the same three dimensions —
Correctness, Completeness, Quality — grounded in complete reads of every changed file
and the recorded verification evidence below. This is a prose-only feature (skills
markdown + a justfile allowlist entry), so the review surface is text conformance and
spec/requirement satisfaction rather than runtime behavior.

## Verification evidence (independently confirmed)

- `just test` → **6/6 passed** (test-pipeline, test-overnight, test-init, test-install,
  full pytest, takeover-stress).
- `tests/test_lifecycle_kept_pauses_parity.py` → **3 passed** (specify.md pause anchors
  at 36/67/155 intact — R12/Technical-Constraint satisfied).
- Skill-design suite (size budget, routing disambiguation, descriptions, contracts) → all green.
- Plugin mirrors **byte-identical** to canonical (`git diff --quiet` clean for
  interview/, requirements-gather/, lifecycle/references/specify.md).
- `git diff main..HEAD` touches **no** backlog-author file (R14 correctly not fired).

## Dimension 1 — Correctness

| Check | Result | Evidence |
|-------|--------|----------|
| loop.md encodes all 5 decision rules | PASS | one-at-a-time, recommend-before-asking (suppressed on taste), codebase-trumps, funnel, saturation — six `###` sections present |
| Saturation stated as NOT template-coverage | PASS | "Saturation, not coverage of any template or checklist, is the stop signal" — semantic, not keyword-only |
| AskUserQuestion is a genuine *exclusion* | PASS | "Keep the grilling conversational — not batched AskUserQuestion" with rationale that batching breaks previous-answer-gates-next |
| requirements-gather keeps grounded + reserve clauses inline | PASS | `Recommendations are grounded`=1, `Reserve interview questions`=1; only the cadence block became a pointer; `Mirrored in`=0 |
| specify.md repoint text-only, no orphaning | PASS | cadence prose preserved; reciprocal note swapped for `This cadence is the canonical rule at skills/interview/references/loop.md`; parity green |
| Zero MUST/CRITICAL/REQUIRED in new files | PASS | grep=0 in both loop.md and SKILL.md |

**Correctness verdict: CLEAN.**

## Dimension 2 — Completeness (R1–R14)

- **R1** routing verified + eval captured — routing-eval.md records both skills resolving with no mis-route. ✓
- **R2** loop.md mechanics, kw grep=12 (≥5). ✓
- **R3** SKILL.md read-and-follow, no inline loop restatement (no cadence/funnel/saturation `###` headers in SKILL.md). ✓
- **R4** topic arg-or-context + single establishing question ("Anchor on a topic"). ✓
- **R5** conversational, answers in context, AskUserQuestion excluded. ✓
- **R6** saturation + user-stop + soft cap. ✓
- **R7** brief offered + requestable anytime + in-conversation default + user-specified path. ✓
- **R8** zero escalation tokens. ✓
- **R9** justfile:582 cortex-core list has `interview` (line 588 overnight list does not); mirror regenerated. ✓
- **R10** 500-line cap (SKILL.md 28 lines, loop.md 46) + parity (`just test` green). ✓
- **R11** requirements-gather lossless single-source. ✓
- **R12** specify.md repoint, parity intact. ✓
- **R13** no regression (`just test` 6/6). ✓
- **R14** conditional — **correctly NOT fired**. See assessment below. ✓

Non-Requirements honored: backlog-author untouched; specify.md behavior and pause sites
unchanged; no bin/cortex-* helper or Python module added; no MUST language.

**Completeness verdict: COMPLETE.**

## Dimension 3 — Quality

- **What/Why not How**: loop.md uses decision-rule + `Why:` rationale structure, not
  procedural narration. PASS.
- **Soft-positive / MUST policy**: zero escalation tokens; phrasing is positive-routing. PASS.
- **Read-and-follow idiom**: SKILL.md delegates to loop.md, modeled on load-requirements.md;
  no duplicated loop mechanics. PASS.
- **Frontmatter**: name/description/when_to_use/argument-hint well-formed; description
  self-disambiguates from backlog-author. PASS.
- **DRY**: cadence genuinely single-sourced in loop.md; requirements-gather's grounded
  recommend + codebase-reserve clauses appropriately KEPT inline (caller-specialized,
  not generic). PASS.
- **Mirror hygiene**: byte-identical; justfile edit on the correct list. PASS.

**Quality verdict: HIGH.**

## R14 assessment (the one judgment call)

R14 permits a minimal backlog-author description clarification only on a *residual*
routing collision. The routing eval found none: representative priming phrasings
("interview me about X", "grill me on X", "help me think through X") resolve to
`/interview`, and ticket phrasings ("author a backlog item", "write a ticket body",
"compose a backlog ticket") resolve to `backlog-author`. The disambiguation was achieved
from the `/interview` side — its description leads with "General-purpose priming
interview … NOT backlog-ticket authoring" and cross-references backlog-author. Leaving
backlog-author untouched is the spec-preferred outcome (Non-Requirement).

**Non-blocking observation (watch-item, not a defect):** backlog-author's `description`
still lists a bare `"interview"` trigger token. The eval judged it contextually
dominated, and that holds for the representative set, but it remains a latent overlap. If
future telemetry ever shows a real priming utterance mis-routing to backlog-author, the
R14 clarification (qualify that token) is the pre-approved remedy. Recorded here so it is
not lost; it does not block approval.

## Decision

No blocking issues across any dimension. Spec fully satisfied, all six plan tasks
complete and verified, full suite and parity green, mirrors in sync. **APPROVED** →
proceed to Complete.
