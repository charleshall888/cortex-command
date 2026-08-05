# Research: Cut /cortex-core:critical-review from 4-5 dispatched agents to 1-2

Clarified intent: narrow reviewer width to 1–2 angles and delete the synthesizer
subagent, with the orchestrator judging raw findings — as leaner prose, no new
machinery.

Tier `moderate`, criticality `high`. Fan-out 3: Codebase, Requirements &
Constraints, Adversarial (last, over a summary of the first two).

> Provenance note: the Codebase angle's dispatched agent went idle twice without
> returning a report; those findings were produced by the orchestrator directly.

## Codebase

### Touch-point inventory

| Path | What changes |
|---|---|
| `skills/critical-review/SKILL.md:3` | `description` — "then synthesizes their findings" becomes false |
| `skills/critical-review/SKILL.md:10` | Intro — "dispatched in parallel … then a synthesis pass" |
| `skills/critical-review/SKILL.md:18` | The width rule itself |
| `skills/critical-review/SKILL.md:34` | Partial-coverage branch; fallback still says "3–4 angles"; "skip synthesis" goes vacuous |
| `skills/critical-review/SKILL.md:38` | Step 5 — deleted |
| `skills/critical-review/SKILL.md:48` | `synthesis_status` prose contract |
| `skills/critical-review/SKILL.md:52` | Step 7's "Output the synthesis directly. Do not soften or editorialize" |
| `skills/critical-review/references/synthesizer-prompt.md` | Deleted (2412 B) |
| `skills/critical-review/references/size-pin.txt` | 4702 → 2290, via `just ratchet-refs` |
| `plugins/cortex-core/skills/critical-review/` | Mirror; pre-commit rebuilds from staged blobs, mirror `size-pin.txt` hand-staged |
| `skills/refine/references/clarify-critic.md:61` | **Explicit "keep the two in sync" contract citing Step 7 by number** — breaks on renumbering |
| `skills/refine/references/specify.md:88` | "presenting the synthesis before approval" |
| `docs/skills-reference.md:110` | Documents both the width rule and "A synthesis agent merges the parallel findings" |
| `docs/internals/sdk.md:144` | "Reviewer count … is what criticality buys" — a dated, retained ruling |
| `cortex/requirements/project.md:38,39` | Ratified constraints |

### Disposition of `synthesizer-prompt.md`'s logic

- **(a) Evidence-quote re-validation against a fresh Read** — partly duplicated by Step 7 ("Dismissals must point at artifact text, not memory"), but Step 7's version runs *after* class assignment. Load-bearing; see Adversarial §5.
- **(b) A→B downgrade rules** (4 triggers + `straddle_rationale` exception) — **has a live consumer.** Step 6 writes only B-class findings to the residue the morning report renders, so class assignment persists to a file. Must be absorbed if the synthesizer goes.
- **(c) Same-class through-line detection** — vacuous at width 1, marginal at 2. Safely droppable.
- **(d) Zero-A-class "no fix-invalidating objections" rule** — keep as one line; prevents a no-findings run reading as a clean verdict.
- **(e) No-balanced-sections prohibition** (no "What Went Well" / "Strengths" / "Recommendation") — keep; matters *more* when the artifact's own author synthesizes.

### `synthesis_status`

`cortex_command/critical_review/write_residue_cli.py:145-146` does **no schema
validation** — `json.loads` on stdin, written verbatim. Sole consumer is
`cortex_command/overnight/report.py:1375-1384`, which renders
`> ⚠ degraded: synthesis failed` whenever the field != `"ok"`, missing included.
`tests/test_report.py::test_missing_required_fields_default_unknown` deliberately
pins that behavior. 9 of 91 existing residues lack the field and therefore already
render the false annotation.

Three options: (i) keep emitting `"ok"` — vestigial; (ii) **redefine the field to
mean "the orchestrator's inline synthesis completed"** — zero code and zero test
change, field stays meaningful; (iii) drop the field, fix `report.py`'s
missing-default, rewrite test (vii) — also fixes the pre-existing 9/91 misfire.
Option (ii) is minimum-change; (iii) is separable and independently justified.

### Tests in play

`tests/test_reference_size_ratchet.py` (pin; enumerates the **working tree**,
canonical-first with content-hash mirror dedupe), `tests/test_l1_surface_ratchet.py:57`
(budget 795, currently 652 — reduction is free, no re-cap needed),
`tests/test_dual_source_reference_parity.py:57`, `tests/test_skill_routing_disambiguation.py`
(must_contain: "critical review", "pressure test", "adversarial review",
"challenge from multiple angles" — all four survive rewording),
`tests/test_skill_size_budget.py` (500-line cap; file is 59 lines),
`tests/test_report.py` (only under option (iii)).

### Byte arithmetic

References `4702 → 2290 = −2412 B (−51%)`. SKILL.md loses Step 5 and the
escalation clause, gains ~4–6 lines absorbing (b)/(d)/(e); net roughly flat.
Overall strongly net-negative — meets the leaner-than-it-replaces constraint.

## Requirements & Constraints

**No ADR needed.** Fails criterion 1 of `cortex/adr/README.md`'s three-criteria
gate (trivially reversible — two prose files). Both predecessor decisions landed
as plain `project.md` edits: the #383 supersession and #403's rewording of `:39`.

**`project.md:38`** — replace with width `1–2`, orchestrator judges envelopes
directly, no synthesizer. Drop the dead "routed to Sonnet with an Opus synthesizer"
clause in the same edit: ADR-0032 (accepted) superseded it, and
`cortex/adr/README.md:51-55` forbids other docs restating a superseded decision body.

**`project.md:39`** — its cited "median 3–7 turns, max 16" is a **blend** of
synthesizer (3/5, n=43) and clarify-critic (7/16, n=52) per #403. Removing the
synthesizer means re-deriving the sentence, not striking a word. The general rule —
mandate shape, not agent identity, governs whether a cap applies — survives with
clarify-critic as its remaining example.

**L1 truthfulness.** Two claims become false: "synthesizes their findings"
(always) and "parallel" / "dispatches parallel sub-agents" (at width 1). The
surviving boundary against `devils-advocate` is dispatch vs. no-dispatch, which
holds at width 1.

**Not implicated:** kept-pauses (no `<!-- pause: -->` markers in this skill),
MUST-escalation policy, `multi-agent.md`. ADR-0028 is `proposed`/orphaned;
ADR-0023 superseded by ADR-0032.

## Adversarial

### 1. This reverses a decision the user already made, on the same surface

`cortex/lifecycle/archive/critical-review-orchestrator-pushback-on-findings/`
investigated **exactly this surface** in April, triggered by the user's own report
of over-applying a 6-finding A-class synthesis ("I rolled over").

- `research.md:205` — "User pivoted from Combination to **upstream-only**. The
  orchestrator-side intervention (d) is dropped from scope."
- `spec.md:41` — "**No Step 4 changes.** No orchestrator-side pushback discipline.
  No new disposition. No anchor check on A→B reclassification. The pivot to
  upstream-only intentionally excludes this surface."
- Stated rationale, quoting Anthropic's harness-design guidance: *"tuning a
  standalone evaluator to be skeptical turns out to be far more tractable than
  making a generator critical of its own work."*

The shipped fix was `fix_invalidation_argument` (`reviewer-prompt.md:25`) plus the
synthesizer-side downgrade rubric (`synthesizer-prompt.md:18`) — i.e. **a fresh,
un-anchored second agent between the reviewers and the artifact's author.** That
mechanism is still live; the old `a-to-b-downgrade-rubric.md` was folded into these
two files, not deleted in substance.

Deleting Step 5 is not a neutral simplification — it *is* option (d), the
orchestrator-side intervention that lifecycle considered and rejected. In refine,
the orchestrator that would now judge the findings is the same agent that just
wrote the spec being challenged, and `SKILL.md:52`'s "do not soften or editorialize"
was written for an agent that had read nothing but the artifact.

### 2. Width-1 leaves contradictory prose behind

At width 1 the Step 4 partial-coverage branch ("Some reviewers failing → synthesize
from the rest … N of M reviewer angles completed") is **provably unreachable** — 0
completed is indistinguishable from all-failing, 1 is full coverage. The
total-failure fallback still dispatches an agent to derive **3–4 angles**, sitting
directly below a primary path capped at 1–2, and its closing "skip synthesis"
becomes vacuous once Step 5 is gone.

### 3. `docs/internals/sdk.md:144` — a dated, explicitly retained ruling

> "**Reviewer count, not reviewer model, is what criticality buys.** Escalating
> criticality raises the number of reviewer angles and triggers the adversarial
> wave; it was never a per-reviewer model upgrade **(requirements ruling
> 2026-07-16, retained)**."

A flat 1–2 with no criticality linkage reverses a ruling deliberately re-affirmed
three weeks ago. Same doc, `:143`, also states judgment dispatches — naming
"critical-review's reviewers **and synthesizer**" — "exist to catch what the cheap
pass missed. Cheaping them out is a false economy."

### 4. The escape-hatch theory has a second life

No independent prose numerically pushes width up (`fanout.md` governs
`/cortex-core:research`, not this skill). But Step 2's distinctness rule
(`SKILL.md:20`) creates the same pressure under another name: an artifact with 3–4
genuinely distinct, evidence-backed weaknesses — which the rule instructs the
orchestrator to look for — has nowhere to go but an over-stuffed angle description
or a quiet re-reading of "1–2" as "1–2 unless."

### 5. B-class residue integrity degrades

The A→B rubric is materially harder to comply with than "Default 2" — 4 triggers,
a straddle exception, per-finding reclassification with rationale, and a *mandated
fresh Read* as the evidence source. Asking the orchestrator to execute it inline,
against its own artifact, from memory, is asking a harder instruction to bind where
a simpler one scored 0-for-82. If the fresh-Read discipline slips, `evidence_quote`
validation degrades to "checked against the orchestrator's memory" — the exact
anchoring failure `SKILL.md:10` exists to prevent, at the one step that persists to
a file the morning report renders unfiltered.

## Open Questions

1. **Does the 2026-04-25 upstream-only pivot still hold?** — **Resolved by the user
   (2026-08-04): yes, it holds.** The synthesizer is kept; only reviewer width is
   cut. Adversarial §1 and §5 are thereby answered rather than accepted as risks:
   the fresh-context filter between reviewers and the artifact's author stays, and
   the A→B rubric stays with an un-anchored agent. Deciding factor: the synthesizer
   is the cheapest agent measured (median 3 / max 5 turns), so deleting it bought
   the least savings at the highest integrity cost.
2. **Does `docs/internals/sdk.md:144`'s retained ruling get amended or honored?** —
   **Resolved by the user (2026-08-04): honored.** Width stays a 1–2 judgment call
   with a single clause weighting toward 2 at `high`/`critical`, preserving
   "criticality buys reviewer count" without a lookup matrix. `sdk.md:144` needs no
   edit.
3. **`synthesis_status` disposition** — **Moot.** The synthesizer survives, so the
   field keeps its current meaning and `write_residue_cli.py` / `report.py` /
   `tests/test_report.py` are untouched. The pre-existing 9-of-91 false-degraded
   misfire (residues missing the field) is unrelated to this change and remains a
   separable follow-up.
4. **Step-number renumbering breaks `clarify-critic.md:61`'s sync contract** —
   **Moot.** No step is deleted, so Step 7 keeps its number and the contract holds.
5. **Should the total-failure fallback stay at 3–4 angles?** — **Open, spec-level.**
   `SKILL.md:34`'s fallback still derives "3–4 angles" and would sit below a primary
   path capped at 1–2. Must be reconciled explicitly; keeping it wider is defensible
   (rarer path, single-shot absorbs more scope) but must read as a decision, not
   residue.
6. **Adversarial §4's distinctness pressure** — **Open, spec-level.** Step 2's rule
   that no two angles may re-phrase the same concern creates upward pressure under a
   different name. The spec should say what the orchestrator does when it finds 3+
   genuinely distinct weaknesses and may dispatch at most 2.

### Descoped by the 2026-08-04 decisions

Adversarial §2 (width-1 unreachable partial-coverage branch) survives and is in
scope — width 1 is still reachable. Everything else predicated on deleting Step 5 —
`synthesizer-prompt.md` deletion, the 4702→2290 size-pin move, `project.md:39`'s
re-derivation, the L1 "synthesizes their findings" falsehood, and the
`specify.md:88` edit — is **out of scope**. Remaining L1 concern is narrower: only
"parallel" / "dispatches parallel sub-agents", still false at width 1.
