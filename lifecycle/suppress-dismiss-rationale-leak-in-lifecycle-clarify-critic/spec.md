# Specification: Suppress Dismiss-rationale leak in lifecycle clarify critic

> **Epic reference**: Broader context in [research/audit-interactive-phase-output-for-decision-signal/research.md](../../research/audit-interactive-phase-output-for-decision-signal/research.md). This spec covers the clarify-critic Dismiss-routing fix (#068). Sibling #067 covers `/critical-review` Step 4 separately (currently at research phase only — this spec is designed to land cleanly whether #067 ships before, after, or never).

## Problem Statement

The lifecycle clarify critic's Dismiss disposition definition in `skills/lifecycle/references/clarify-critic.md:73` instructs: "State the dismissal reason briefly." No target audience is specified. Orchestrators surface these rationales to the user as inline conversation commentary, even though Dismiss items are internal bookkeeping — resolved by the orchestrator, not requiring user input. The leak obscures decision-relevant signal (questions, approvals, synthesis) with internal work product. Every lifecycle clarify invocation pays this cost. The fix replaces the current free-form Dismiss-rationale output with a structured disposition output — the orchestrator's dispositioning step produces a single YAML artifact matching the `clarify_critic` events.log schema as its sole output, which is written verbatim to events.log. The user-facing response covers only §4 Ask merging and Apply confidence revisions; Dismiss rationales have no user-facing surface because the dispositioning step produces only structured output, not because an instruction forbids narration.

## Design Principle

This spec adopts a **structural output contract** over a **negative instruction** per epic DR-4 and Anthropic's harness-design guidance ("structural enforcement... outperforms prompt-only approaches"; "assume the reviewer will leak... unless the harness prevents it"). The dispositioning step's output contract is tightened so that Dismiss rationales have nowhere to live except in the structured `dismissals` field of the events.log entry. The orchestrator's user-facing response is scoped to specific classes of content (§4 Ask merge, Apply confidence revisions) — Dismiss rationales are structurally absent from the response surface.

## Requirements

**MoSCoW**: All 9 requirements below are **Must-have**. The spec has no Should-have or Could-have items. Scope is narrow: any requirement unresolved would leave the disposition output contract incoherent.

1. **Extend the `clarify_critic` event schema with a `dismissals` field.** `clarify-critic.md`'s Event Logging section (lines 91–104) gains a required field between `applied_fixes` and `status`. Field shape: `dismissals: [{finding_index: <int>, rationale: <prose>}]` — array of objects, each with a `finding_index` pointing into the `findings` array and a `rationale` string.
   - **Acceptance**: The schema block (between ````` and ````` under "Required fields:") contains a `dismissals:` line AND the `dismissals` field is documented in the prose paragraph immediately after the schema block. Check: `awk '/^Required fields:/,/^```$/' skills/lifecycle/references/clarify-critic.md | grep -c "^dismissals:"` = 1 AND `awk '/^```$/,/^## Failure Handling/' skills/lifecycle/references/clarify-critic.md | grep -c "dismissals"` ≥ 2. Pass if both hold.

2. **Rewrite the dispositioning step's output contract to produce a single structured artifact.** Replace the Dismiss disposition definition's trailing sentence ("State the dismissal reason briefly.") and add a new "Dispositioning Output Contract" subsection to the Disposition Framework. The subsection must specify:
   - The dispositioning step's **sole output** is a YAML artifact matching the `clarify_critic` events.log schema (including `dismissals`).
   - The orchestrator writes this YAML verbatim to `lifecycle/{feature}/events.log` as the `clarify_critic` event.
   - The orchestrator's user-facing response following the dispositioning step is scoped to: (a) the §4 Ask-merge invocation (unchanged Ask-to-Q&A Merge Rule), and (b) silent application of Apply dispositions to the confidence assessment.
   - Dismiss rationales appear only in the YAML's `dismissals[].rationale` field; they are not part of the user-facing response surface.
   - **Acceptance (replacement)**: `grep -c "State the dismissal reason briefly" skills/lifecycle/references/clarify-critic.md` = 0. Pass if count = 0.
   - **Acceptance (structural contract present)**: The Disposition Framework section (between `## Disposition Framework` and the next `^## ` heading) contains a subsection heading named "Dispositioning Output Contract" (or equivalent — the prose must match the four bullets above). Check: `awk '/^## Disposition Framework/,/^## [^D]/' skills/lifecycle/references/clarify-critic.md | grep -cE "^### (Dispositioning Output Contract|Output Contract)"` = 1. Pass if count = 1.
   - **Acceptance (user-facing scope)**: The same subsection contains prose that restricts the user-facing response to Ask merging and Apply confidence revisions. Check: `awk '/^### (Dispositioning Output Contract|Output Contract)/,/^### |^## /' skills/lifecycle/references/clarify-critic.md | grep -cE "user-facing|user response|§4 Ask"` ≥ 1. Pass if count ≥ 1.

3. **Preserve the Ask-to-§4 merge path verbatim**. The Ask disposition paragraph (currently line 75) and the Ask-to-Q&A Merge Rule section (currently lines 81–85) must remain textually identical to their pre-change form.
   - **Acceptance**: The sentence "Ask items from the critic are **not** presented as a blocking escalation separate from §4. They are folded into the §4 question list and presented alongside any remaining low-confidence dimensions as a single consolidated Q&A round." appears verbatim in the file. Check: `grep -F "Ask items from the critic are **not** presented as a blocking escalation separate from §4. They are folded into the §4 question list" skills/lifecycle/references/clarify-critic.md | wc -l` = 1. Pass if count = 1.
   - **Acceptance (Ask disposition paragraph preserved)**: The sentence "Ask — the fix is not for the orchestrator to decide unilaterally." appears verbatim (allowing for the bold `**Ask**` markdown). Check: `grep -cF "the fix is not for the orchestrator to decide unilaterally" skills/lifecycle/references/clarify-critic.md` = 1. Pass if count = 1.

4. **Narrow the existing `applied_fixes` semantics paragraph to exclude Ask→Dismiss reclassifications.** Current line 108 says: "Disposition counts reflect post-self-resolution values. If self-resolution reclassifies an Ask item as Apply, the logged `apply` count increases and `ask` count decreases accordingly. The `applied_fixes` array includes fixes from both initial Apply dispositions and self-resolution reclassifications." The unqualified "self-resolution reclassifications" clause must be narrowed to cover only Ask→Apply. Additionally, a parallel sentence must be added covering Ask→Dismiss: the rationale lands in `dismissals[].rationale`, not `applied_fixes`; `dispositions.ask` decreases and `dispositions.dismiss` increases.
   - **Acceptance (old unqualified clause removed)**: `grep -cF "fixes from both initial Apply dispositions and self-resolution reclassifications" skills/lifecycle/references/clarify-critic.md` = 0. This catches the exact pre-existing unqualified sentence; any replacement that retains the unqualified "both Apply and reclassification" framing fails. Pass if count = 0.
   - **Acceptance (Ask→Apply path explicitly scoped)**: `grep -cE "self-resolution reclassif.*Ask.*Apply|Ask.*Apply.*self-resolution" skills/lifecycle/references/clarify-critic.md` ≥ 1. Pass if count ≥ 1.
   - **Acceptance (Ask→Dismiss path documented)**: `grep -cE "Ask.*Dismiss.*rationale.*dismissals|dismissals.*Ask.*Dismiss.*rationale" skills/lifecycle/references/clarify-critic.md` ≥ 1. Pass if count ≥ 1.
   - **Acceptance (new `dismissals` documentation distinct from `applied_fixes`)**: A sentence exists describing `dismissals` as the Dismiss-disposition equivalent of `applied_fixes`. Check: `grep -cE "dismissals.*Apply|Apply.*dismissals" skills/lifecycle/references/clarify-critic.md` has at least one match explicitly contrasting the two fields. Minimum check: `grep -cE "dismissals.*Dismiss disposition|Dismiss disposition.*dismissals" skills/lifecycle/references/clarify-critic.md` ≥ 1. Pass if count ≥ 1.

5. **Extend the YAML example (lines 112–126) to demonstrate both initial Dismiss and Ask→Dismiss reclassification cases.** The current example has `dispositions.dismiss: 0` and no `dismissals` entries. Update the example so:
   - `dispositions` counts are consistent: `dismiss` equals `len(dismissals)`.
   - `dismissals` contains at least 2 entries: one representing an initial Dismiss disposition and one representing an Ask→Dismiss self-resolution reclassification, with a brief comment in the YAML distinguishing them.
   - **Acceptance (key exists in example)**: `awk '/^```yaml/,/^```$/' skills/lifecycle/references/clarify-critic.md | grep -cE "^[[:space:]]+dismissals:"` ≥ 1. Pass if count ≥ 1.
   - **Acceptance (non-empty array with at least 2 entries)**: `awk '/^```yaml/,/^```$/' skills/lifecycle/references/clarify-critic.md | grep -cE "finding_index:"` ≥ 2. Pass if count ≥ 2.
   - **Acceptance (count consistency)**: Mechanical check that `dismiss:` integer in the YAML equals 2 (matching 2 `finding_index` entries). Check: `awk '/^```yaml/,/^```$/' skills/lifecycle/references/clarify-critic.md | grep -E "^[[:space:]]+dismiss: 2"` matches. Pass if the grep matches.

6. **Extend the Failure Handling list (line 132) to include `dismissals: []` on failure.** The failure-path event payload must include `dismissals: []`, consistent with existing `findings: []` and `applied_fixes: []` empty-array conventions.
   - **Acceptance**: Within the Failure Handling section (between `## Failure Handling` and the next `^## ` heading), `dismissals` appears in the context of the empty-payload description. Check: `awk '/^## Failure Handling/,/^## [^F]/' skills/lifecycle/references/clarify-critic.md | grep -cE "dismissals.*\[\]|empty.*dismissals\\b|\\bdismissals\\b.*and empty" ` ≥ 1. Pass if count ≥ 1.

7. **Add a Constraints-table row governing the Dismiss-rationale output location.** The Constraints table (starting at line 137) gains one new row in `| Thought | Reality |` format. The "Reality" cell must name both `dismissals` and `events.log`.
   - **Acceptance (row is in table format)**: The Constraints-section line count for rows matching `| "[^|]*dismiss[^|]*" | "[^|]*dismissals[^|]*events\.log[^|]*" |` format ≥ 1 — this enforces a true table row with both `dismissals` and `events.log` substrings in the Reality cell. Mechanical check: `awk '/^## Constraints/,0' skills/lifecycle/references/clarify-critic.md | grep -cE '^\|.*(dismissal|Dismiss).*\|.*dismissals.*events\.log' ` ≥ 1. Pass if count ≥ 1.

8. **Downstream consumer audit is broader than previously specified.** Confirm no file across the repo parses `clarify_critic` events in a way that breaks when the new `dismissals` field appears. Coverage must include: `bin/`, `retros/`, `hooks/`, `claude/`, `skills/`, `docs/`, `tests/` and all extensions `.py`, `.sh`, `.md`, `.json`, `.yaml`, `.yml`, `.toml`, `.js`, `.ts`.
   - **Acceptance**: `grep -rn "clarify_critic" bin/ retros/ hooks/ claude/ skills/ docs/ tests/ --include='*.py' --include='*.sh' --include='*.md' --include='*.json' --include='*.yaml' --include='*.yml' --include='*.toml' --include='*.js' --include='*.ts' 2>/dev/null | grep -vE "skills/lifecycle/references/clarify(-critic)?\.md|lifecycle/[^/]+/(events\.log|research\.md|spec\.md|plan\.md|review\.md|implementation\.md)$|research/audit-interactive-phase-output-for-decision-signal/" | wc -l` = 0. Pass if count = 0.
   - **Note**: The filter explicitly excludes this ticket's own lifecycle directory and the epic research directory — those contain `clarify_critic` references as documentation about the feature, not as consumers of the event schema.

9. **No structural change to `clarify.md`.** `clarify.md` §3a (lines 47–49) remains pure delegation — no defensive reinforcement added. The single schema-destination edit in `clarify-critic.md` carries the behavioral constraint; reinforcing in §3a would be defense-in-depth without marginal benefit.
   - **Acceptance**: `diff <(git show HEAD:skills/lifecycle/references/clarify.md | sed -n '45,55p') <(sed -n '45,55p' skills/lifecycle/references/clarify.md)` is empty. Pass if the diff produces no output.

## Non-Requirements

- **Does NOT modify the drift-avoidance parenthetical at `clarify-critic.md:69`**. Sibling #067 is currently at research phase only (no spec). Touching the line-69 parenthetical from this ticket would encode assumptions about #067's outcome that #067 has not committed to. When #067's spec lands, the parenthetical update belongs in whichever ticket ships second. This is a scope boundary decision: this ticket ships the schema change and disposition contract; #067 (when specced) handles the parenthetical coordination.
- **Does NOT modify `skills/critical-review/SKILL.md`**. Any `/critical-review` Step 4 edits belong to sibling #067.
- **Does NOT add a JSONL schema validator**. The invariant `len(dismissals) == dispositions.dismiss` remains textual in the spec. A future ticket may add a programmatic validator; research.md:119 flagged this as a residual risk. Not in scope for #068.
- **Does NOT introduce a user-facing "expand dispositions" command**. Users who want to audit dismissal rationales read `events.log` directly.
- **Does NOT rewrite the three-disposition framework**. Apply/Dismiss/Ask vocabulary is preserved.
- **Does NOT backfill past `events.log` entries**. Existing `clarify_critic` events in `lifecycle/*/events.log` have no `dismissals` field; the schema extension is forward-only.
- **Does NOT move dispositioning to a separate subagent**. The full Option-2 redesign (dispositioning as its own subagent with structured return) is a larger change than this ticket's scope. The structural enforcement in this spec is achieved via output-format contract on the orchestrator's dispositioning step, not by introducing an agent boundary.

## Edge Cases

- **Zero Dismiss dispositions**: When `dispositions.dismiss = 0`, the YAML emits `dismissals: []` for shape consistency (matches how `findings: []` and `applied_fixes: []` are emitted when empty).
- **Critic agent failure**: Per Requirement 6, the failure-path event carries `dismissals: []` alongside empty `findings: []` and `applied_fixes: []`.
- **Self-resolution Ask→Dismiss reclassification**: Per Requirement 4, the reclassified item's rationale lands in `dismissals[].rationale` (not `applied_fixes`). Count accounting: `dispositions.ask` decreases by 1, `dispositions.dismiss` increases by 1, `len(dismissals)` increases by 1, `len(applied_fixes)` unchanged.
- **Self-resolution Ask→Apply reclassification**: Unchanged — rationale description lands in `applied_fixes`; `dismissals` unaffected.
- **`finding_index` out of bounds**: If `finding_index` points outside the `findings` array, the event is malformed. No validator catches this today; the textual invariant (`0 ≤ finding_index < len(findings)`) is asserted in the spec, enforcement deferred to a future validator.
- **Invariant violation (`len(dismissals) != dispositions.dismiss`)**: Textual invariant only; no write-time validator. If drift appears in practice, a follow-up ticket may add a JSONL validator.
- **Orchestrator emits a pre-spec legacy event (no `dismissals` field, non-zero `dispositions.dismiss`)**: Treated as a pre-change entry. No consumer parses the field today (verified by Requirement 8's audit), so no downstream consumer breaks. Forward-facing orchestrators following the updated spec always emit `dismissals` (including `dismissals: []` when dismiss count is zero).
- **Orchestrator attempts to narrate a Dismiss rationale in the user-facing response**: The Dispositioning Output Contract (Requirement 2) scopes the user-facing response to §4 Ask merging and Apply confidence revisions. A response containing Dismiss-rationale narration violates the contract; reviewers and future critical-review runs should flag this. No runtime enforcement in this ticket.

## Changes to Existing Behavior

- **MODIFIED**: `clarify-critic.md:73` Dismiss disposition definition — removes the "State the dismissal reason briefly" sentence; the Dismiss definition now stands alone as a classification rule, with the output handling governed by the new Dispositioning Output Contract subsection.
- **ADDED**: `clarify-critic.md` gains a "Dispositioning Output Contract" subsection under `## Disposition Framework` (exact location between the existing Apply/Dismiss/Ask definitions and the Ask-to-Q&A Merge Rule, or as a distinct `###` subsection).
- **MODIFIED**: `clarify-critic.md:93–104` schema block — adds the `dismissals` field.
- **MODIFIED**: `clarify-critic.md:106–108` paragraphs — narrows the `applied_fixes` Ask→Apply reclassification clause, adds parallel Ask→Dismiss handling.
- **MODIFIED**: `clarify-critic.md:112–126` YAML example — demonstrates both initial-Dismiss and Ask→Dismiss reclassification cases.
- **MODIFIED**: `clarify-critic.md:132` Failure Handling — adds `dismissals: []` to the empty-payload list.
- **ADDED**: One row in the `clarify-critic.md` Constraints table governing Dismiss-rationale routing.
- **UNCHANGED**: `clarify-critic.md:69` drift-avoidance parenthetical (gated on #067 having a spec — not in this ticket's scope).
- **UNCHANGED**: Apply disposition (line 71), Ask disposition (line 75), self-resolution Anchor check (line 77), Apply bar (line 79), Ask-to-Q&A Merge Rule (lines 81–85), orchestrator write-ownership of the event (clarify.md §3a).

## Technical Constraints

- **`events.log` is append-only JSONL** (`requirements/pipeline.md:126`). The schema extension is additive; existing entries remain valid.
- **Orchestrator write-ownership unchanged**: Per `requirements/pipeline.md:62`, the orchestrator (not the critic subagent) writes the `clarify_critic` event. The Dispositioning Output Contract tightens the orchestrator's output shape but does not change write-ownership.
- **Structural enforcement per epic DR-4 and Anthropic harness-design guidance**: The primary lever is the positive output-format contract on the dispositioning step, not a negative "do not narrate" instruction. This is the higher-reliability lever available within the bounded scope of this ticket. Residual risk: the orchestrator could technically produce additional user-facing prose after the structured output step; the Dispositioning Output Contract requires explicitly that the user-facing response be scoped to §4 Ask merge and Apply confidence revisions only. Full structural containment (dispositioning as a separate subagent) is out of scope — deferred as a potential future ticket if the residual risk manifests.
- **Schema field naming**: `dismissals` (plural, consistent with `findings` and `applied_fixes`). Element shape `{finding_index: <int>, rationale: <prose>}`. `finding_index` is preferred over `finding: <prose>` (duplicated text) because it preserves the linkage to `findings[i]` without duplication.
- **Invariant**: `len(dismissals) == dispositions.dismiss` must hold for every success-path event. `len(applied_fixes) ≤ dispositions.apply` (at most one `applied_fixes` entry per Apply disposition; Apply dispositions may combine). Textual assertions only; no programmatic validator in this ticket.
- **#067 coupling**: This spec is designed to ship cleanly regardless of #067's status. The line-69 parenthetical is explicitly Non-Requirements (see above). If #067 lands after #068, #067 updates the parenthetical; if before, this ticket leaves it alone.

## Open Decisions

None. All consequential decisions have been resolved:

- **Alt B' (structural output contract)** over Alt B (schema + negative instruction), over subagent redesign (Option 2 full), over Alt D (eliminate): chosen per adversarial review + Anthropic harness-design guidance + research DR-4. Preserves audit trail (satisfies `pipeline.md:127`), replaces negative instruction with positive output-format contract (DR-4 high-reliability lever), stays scope-bounded (no new agent boundary).
- **#067 coupling**: dropped from this ticket — the parenthetical update belongs to whichever ticket ships second.
- **Invariant enforcement**: textual only; validator deferred as potential follow-up.

Residual acknowledged risks (noted for awareness, not blockers):
- Future consumer cannot distinguish pre-spec legacy `clarify_critic` events from post-spec bugs without a schema-version marker. A future ticket may introduce schema versioning if strict parsers emerge (dashboard, metrics work).
- Invariant drift (`len(dismissals) != dispositions.dismiss`) cannot be caught at write time. Mitigation deferred.
- The Dispositioning Output Contract still operates within the orchestrator's context; a fully structural fix would move dispositioning to a separate subagent. That redesign is out of scope here.
