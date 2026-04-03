# Debug Session: /refine produces spec.md without research.md
Date: 2026-04-02
Status: Resolved

## Phase 2 Findings

- **Root cause confirmed** via path tracing through lifecycle → discovery bootstrap → refine delegation chain (see below)
- **Exact bug location**: `skills/lifecycle/SKILL.md:225` — ambiguous summary of `/refine` Step 2, drops the `lifecycle/{lifecycle-slug}/` path prefix
- **Supporting evidence**:
  - `skills/lifecycle/SKILL.md:178-191` — Discovery Bootstrap sets `epic_research_path = research/{topic}/research.md` and loads it into agent context
  - `skills/lifecycle/SKILL.md:220-223` — Epic context injection: "read the epic research file at `{epic_research_path}` as background context" — agent now holds `research/{topic}/research.md` as an active mental model
  - `skills/lifecycle/SKILL.md:225` — THEN says: "detect the resume point (Clarify if **no research.md**, Spec if **research.md exists**)" — NO path qualifier
  - `skills/refine/SKILL.md:40-48` — the actual `/refine` Step 2 says `lifecycle/{lifecycle-slug}/research.md` explicitly, but the LIFECYCLE's step 3 summary omits the path
  - `skills/research/SKILL.md:37-39` — `/research` only writes `lifecycle/{slug}/research.md` when `lifecycle-slug` is passed; if agent skips calling it, no file is written

## Phase 1 Findings

- **Observed behavior**: A user ran `/refine` on multiple tickets; overnight failed because `lifecycle/{slug}/research.md` is missing while `spec.md` exists. Example: `lifecycle/design-api-contract-pydantic-schemas-openapi/spec.md` exists, `research.md` does not.

- **Evidence gathered**:
  - `claude/overnight/backlog.py:487` — the overnight selector checks `research.md` BEFORE `spec.md`; if research.md is absent, the item is rejected regardless of spec.md
  - `skills/refine/SKILL.md:40-48` — `/refine` Step 2 checks: if `spec.md` exists → "offer to re-run or exit." Does NOT check whether `research.md` also exists before offering the exit
  - `skills/lifecycle/SKILL.md:214` — lifecycle's `/refine` delegation guard: "If `spec.md` already exists: skip delegation, proceed to Plan." Also no check for `research.md`
  - `/refine` Step 5 produces `spec.md` only after Step 4 produces `research.md` — so these two files should always co-exist IF `/refine` ran the full flow

- **Dead-ends**:
  - Slug mismatch ruled out: the selector finds `spec.md` in the correct directory, so `lifecycle_slug` is resolving to the right path for both artifacts
  - Silent `/research` failure ruled out: `/refine` Step 4 explicitly says "verify research.md exists and is non-empty; if absent, surface the error and halt — do not proceed to Research Exit Gate"

## Current State

**Root cause identified**: The lifecycle skill's `/refine` Delegation Step 3 summarizes `/refine`'s Step 2 check as "Clarify if no research.md, Spec if research.md exists" — omitting the `lifecycle/{lifecycle-slug}/` path prefix. In context where Discovery Bootstrap has just loaded `research/{topic}/research.md` as epic background, the agent evaluates this ambiguous check against the discovery artifact path and concludes "research.md exists → resume = Spec." It skips calling `/research`, so `lifecycle/{slug}/research.md` is never written, but spec.md is written correctly.

**Prior Phase 1 hypotheses** (now superseded):

Two separate paths can produce `spec.md` without `research.md`:

1. **`/lifecycle feature specify` direct invocation** — user or agent invokes the specify phase explicitly, bypassing the `/refine` delegation guard (which only fires when `spec.md` does NOT exist). This writes `spec.md` directly without research.

2. **`/refine` Step 2 early exit on incomplete state** — if `spec.md` exists from a prior direct `/lifecycle specify` run, `/refine` Step 2 sees `spec.md` and offers "spec is already complete — re-run or exit." If the user exits, the backlog item is left in a `spec-without-research` state. Neither `/refine` nor the lifecycle delegation check guards against this.

The **structural gap**: both the `/refine` Step 2 completion check and the lifecycle delegation guard treat `spec.md` existence as the sole signal that the early phases are complete. Neither verifies that `research.md` also exists. Since overnight requires both, any path that creates `spec.md` without `research.md` will silently pass through all pre-overnight gates and only fail at overnight selection.

**Fix location**: `skills/refine/SKILL.md` Step 2 Check State — add a guard: when `spec.md` exists, also check for `research.md`. If `research.md` is missing, do not offer the "exit" path; instead, warn and proceed directly to the Research phase.

## Phase 3–4 Findings

- **Hypothesis**: lifecycle SKILL.md:225 summarizes `/refine` Step 2 as "Clarify if no research.md, Spec if research.md exists" — dropping the `lifecycle/{lifecycle-slug}/` path prefix — in a context where the discovery research path is already loaded. Agent evaluates the discovery artifact and takes the Spec branch.
- **Fix applied**:
  - `skills/lifecycle/SKILL.md:225` — reworded to explicitly name `lifecycle/{lifecycle-slug}/research.md`, with an inline disqualifier: "The discovery/epic research at `{epic_research_path}` does NOT satisfy this check."
  - `skills/refine/SKILL.md` Step 4 Sufficiency Check — added **Path guard** note: discovery research at `research/{topic}/research.md` does not satisfy the check; only `lifecycle/{lifecycle-slug}/research.md` does.

## Prior Attempts
(none — first investigation)
