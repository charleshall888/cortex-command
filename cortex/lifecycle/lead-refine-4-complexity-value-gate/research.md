# Research: Lead refine §4 complexity-value gate with recommended option + rationale

> Clarified intent: Amend `skills/refine/SKILL.md` §4 so that when the complexity/value gate fires, the orchestrator picks a per-feature recommended alternative, states a one-sentence rationale, and presents it first with a `(Recommended)` label suffix — using soft positive-routing phrasing.

## 1. Current §4 prose (canonical)

File: `skills/refine/SKILL.md` — single-line bullet at line 162 inside the Step 5 adaptations list. Verbatim (one logical line, wrapped here for readability):

```
- **§4 (User Approval) — Complexity/value gate**: After the spec is written, before showing the approval surface, check whether complexity is proportional to the value case. Fire this check if the spec has any of: 3+ distinct new state surfaces, a new persistent data format or config section the user must maintain, or a subsystem requiring ongoing per-feature upkeep. This check fires regardless of whether critical-review ran. If the check fires, do NOT proceed to the approval question in the same turn — instead present: (1) a one-sentence value case for the primary outcome, (2) a one-sentence complexity cost, and (3) 2–3 concrete alternatives. Where they naturally exist for this ticket, offer: "drop entirely" (value is achievable another way or too weak), "bugs-only" (strip the feature, keep only latent fix work the spec uncovered), "minimum viable" (identify one concrete scope cut). If an alternative doesn't naturally apply, say so. Wait for the user's response before showing the approval surface.
```

The spec author rewrites this single bullet. No other §4 surfaces in `skills/refine/` reference the gate.

Cross-reference caveat: line 164 (`**Hard Gate**` row) cites "refine's existing **§4 (User Approval) — Complexity/value gate** adaptation above" — the heading "Complexity/value gate" must remain searchable. The rewrite keeps the same bullet boundary.

## 2. Decision rule for the recommendation

Memory entries cited in `CLAUDE.md`/`MEMORY.md` are not present as standalone files in this checkout (`/Users/charlie.hall/.claude/projects/-Users-charlie-hall-Workspaces-cortex-command/memory/` contains only `MEMORY.md` plus a "prefer fixing the underlying skill over saving memories" note). The trigger-prompt text is the authoritative paraphrase:
- `feedback_scope_recommendations`: "for multi-option scope/complexity-value questions, always lead with the recommended option and one-sentence rationale; place `(Recommended)` on the lead option."
- `user_defaults_full_scope`: "when offered full-scope vs. downsized alternatives, the user almost always accepts full scope" — but "*when presenting alternatives*, lead with the most-likely-accepted option" (NOT "every feature should be maximally scoped").

Proposed decision-rule prose for §4 (one concrete sentence + one calibrator):

> Decide which alternative is the recommended option for this specific spec. Default to "Confirm current scope" (full scope) unless the spec's introduced complexity materially exceeds the value case — in which case recommend the smallest downsize that preserves the primary outcome. Either way, cite the specific spec surface(s) driving the choice in a one-sentence rationale.

The "cite the specific surface(s)" clause prevents content-free recommendations and keeps the rationale auditable.

## 3. Worked example placement

`skills/refine/SKILL.md` is currently 212 lines; the size budget cap is 500 lines (`tests/test_skill_size_budget.py`:59 `CAP = 500`). Adding a ~12–20 line inline worked example (the orchestrator's announcement + the rendered options array) leaves >250 lines of margin — well past the >50-line comfort threshold.

Recommendation: **inline worked example** under the §4 bullet. A `references/` extract would add a redirect-and-resolve indirection cost that the line budget does not justify.

Worked-example shape: 3–5 lines of the orchestrator's pre-question announcement ("I recommend Confirm current scope because the persistence cost is one config line and the value case is X. Confirm or downsize?"), then 3–4 lines showing the rendered options array with the `(Recommended)` suffix on the lead option.

## 4. AskUserQuestion rendering

The canonical analog is `skills/lifecycle/references/implement.md`:18, which uses a lowercase `(recommended)` suffix on the first label:

```
- **Implement on current branch** (recommended) — trunk-based workflow, ...
```

And `implement.md`:22 confirms the suffix-strip convention: "strip the `(recommended)` suffix from that option's label if present."

The trigger prompt's memory paraphrase capitalizes it as `(Recommended)`. The ticket body (line 28 of #209) writes `(Recommended)`. To match the user-facing memory wording, the spec should standardize on **`(Recommended)` (capital R)** for the refine gate. Note this differs in case from `implement.md`'s `(recommended)` — flagged as Open Question §4 below.

Prose instruction the spec author needs to encode in §4:
- The lead option's `label` ends with the literal suffix ` (Recommended)` (with the leading space).
- The lead option's `description` opens with the rationale (one sentence).
- The question prompt opens with "I recommend X because Y. Confirm or downsize?" — not a neutral "Which scope do you want?".
- Subsequent options retain neutral descriptions (no demotion text required — they are alternatives the user is already opting into by selecting them).

## 5. Test surface

No `tests/test_refine_skill.py` exists today (`ls tests/ | grep -i refine` → empty). Closest existing surfaces:
- `tests/test_lifecycle_kept_pauses_parity.py` — scans `skills/refine/` for `AskUserQuestion` mentions and requires an inventory entry in `skills/lifecycle/SKILL.md` "Kept user pauses". **Coupling**: introducing `AskUserQuestion` into refine §4 prose (Section 4 above) creates a new call-site reference; the spec must add an inventory line at `skills/lifecycle/SKILL.md:189–200` matching the refine SKILL.md line where the new `AskUserQuestion` mention lands (±35-line tolerance per `LINE_TOLERANCE` at `tests/test_lifecycle_kept_pauses_parity.py`:27).
- `tests/test_check_prescriptive_prose.py` — exercises `bin/cortex-check-prescriptive-prose`, scoped to forbidden Role/Integration/Edges sections. Not a fit for §4 prose assertions.

Recommendation: **create a new `tests/test_refine_skill.py`** rather than overloading kept-pauses or prescriptive-prose tests. The new file has a single, scoped concern (refine §4 prose shape) and matches existing one-concern-per-file convention (`test_skill_callgraph.py`, `test_skill_contracts.py`, etc.).

Concrete regex assertions the new test should make (against `skills/refine/SKILL.md`):

1. The literal substring `\(Recommended\)` appears within 25 lines after the heading anchor `Complexity/value gate` (proves the suffix instruction is colocated with the gate prose, not stranded elsewhere).
2. The substring `I recommend` (or equivalent soft positive-routing trigger) appears within the §4 bullet block — assert the bullet contains the phrase.
3. The substring `rationale` (or `because`) appears between the `Complexity/value gate` anchor and the `(Recommended)` literal, proving rationale-first ordering rather than recommendation-as-afterthought.
4. (Negative) The substring `MUST decide` or `MUST decide which` does NOT appear in the §4 bullet — guards against accidental MUST escalation regression (per Section 7 below).

## 6. Plugin mirror

The `build-plugin` recipe at `justfile`:519–551 rsyncs `skills/refine/` → `plugins/cortex-core/skills/refine/` for every skill in the cortex-core `SKILLS` list (line 527 includes `refine`). The pre-commit hook at `.githooks/pre-commit`:71–92 invokes `just build-plugin` and runs a drift loop (lines 261–286) that fails the commit if `plugins/$p/` differs from the regenerated tree. The plugin mirror at `plugins/cortex-core/skills/refine/SKILL.md` exists and is auto-regenerated; authors edit only `skills/refine/SKILL.md`.

## 7. MUST-policy compliance

`CLAUDE.md`:72–84 governs MUST-escalation: "Default to soft positive-routing phrasing for new authoring under epic #82's post-4.7 harness adaptation… To add a new MUST/CRITICAL/REQUIRED escalation, you must include in the commit body OR PR description a link to one evidence artifact: (a) `cortex/lifecycle/<feature>/events.log` path + line of an F-row showing Claude skipped the soft form, OR (b) a commit-linked transcript URL or quoted excerpt."

Ticket #209's "Proposed change" #1 uses "MUST decide which of the alternatives is the recommended option." No effort=high failure artifact accompanies the ticket. The amendment written into `skills/refine/SKILL.md` therefore uses soft positive-routing phrasing:

- Soft form: "Decide which alternative is the recommended option for this specific spec and state it explicitly with a one-sentence rationale before listing the alternatives."
- The orchestrator-side decision verb is "Decide" (declarative), not "MUST decide" (escalated).
- The rationale presentation verb is "state" (declarative), not "MUST state".

The clarified intent at the top of this research artifact already encodes the soft-form choice.

## 8. Existing analogous patterns

Lead-with-recommendation surfaces already in the codebase:

- `skills/lifecycle/references/implement.md`:18 — branch selection prompt uses lowercase `(recommended)` suffix on the first option (`Implement on current branch`). Line 22 confirms the suffix is a label convention that can be stripped under fault conditions. **Closest analog**; the refine gate should mirror its shape but use capital-R `(Recommended)` per memory wording (open question §4 below).
- Multiple lifecycle research artifacts use `(Recommended)` in approach tables — e.g. `cortex/lifecycle/.../research.md` files with `### Approach A: ... (Recommended)`. These are author-facing, not user-facing prompts, but confirm the capital-R convention for "recommended option marker in a multi-option presentation".
- `skills/lifecycle/references/plan.md`:277 — plan approval surface uses an `AskUserQuestion` with `Approve | Request changes | Cancel` options; **not a recommendation-lead pattern** (all three options are neutral), but confirms the canonical AskUserQuestion shape (overview + task list + options enumerated).

No existing surface uses the "I recommend X because Y. Confirm or downsize?" phrasing — this is genuinely new authoring, not a propagation of an existing pattern.

## Open Questions

- **Resolved (decision rule)**: Default to "Confirm current scope" unless complexity materially exceeds value; cite the surfaces driving the choice. See §2.
- **Resolved (worked example placement)**: Inline. Line budget margin is >250 lines. See §3.
- **Resolved (test surface)**: New `tests/test_refine_skill.py` with the four regex assertions in §5.
- **Resolved (MUST policy)**: Soft-form phrasing per `CLAUDE.md`:72–84; no MUST in the amended bullet. See §7.
- **Deferred to Spec — `(Recommended)` capitalization**: `implement.md` uses lowercase `(recommended)`; the ticket body and memory paraphrase use capital `(Recommended)`. Spec must decide: (a) standardize refine on capital-R to match user-facing memory wording and accept a one-time stylistic divergence from `implement.md`, or (b) align with `implement.md`'s lowercase convention and update the ticket's expected suffix. Recommend (a) — the memory wording is the user's stated preference and capital-R is the more visually distinct suffix.
- **Deferred to Spec — kept-pauses inventory coupling**: If the amended §4 prose introduces a literal `AskUserQuestion` mention into `skills/refine/SKILL.md`, the spec must include a paired update to `skills/lifecycle/SKILL.md` "Kept user pauses" inventory (§5 coupling note). The spec author decides whether to use `AskUserQuestion` verbatim (triggers inventory update) or paraphrase as "ask the user via the structured-question surface" (no inventory update). Recommend the verbatim `AskUserQuestion` mention plus the inventory line — the parity test is the user-facing affordance protecting this pause from accidental removal.
- **Deferred to Spec — downsize-option labels and counts**: §4 currently enumerates "drop entirely / bugs-only / minimum viable" as the canonical downsize candidates. The spec must decide whether the new wording carries those literal labels through or generalizes to "the spec-author picks 1–2 downsize alternatives appropriate for this feature". Recommend carrying the labels through to preserve the existing template while adding "Confirm current scope (Recommended)" as the lead option.
