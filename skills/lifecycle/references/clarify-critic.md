# Clarify Critic

Post-§3 confidence challenge. A fresh agent reviews the three-dimension confidence assessment and challenges whether each rating is well-supported by the source material, before any Q&A with the user. Always runs — the critic does not gate on confidence level.

## Input Contract

The critic receives two inputs:

1. **Confidence assessment** — the full §3 output including the agent's reasoning for each of the three dimensions (intent clarity, scope boundedness, requirements alignment), plus the high/low verdict for each.
2. **Source material** — the original backlog item body (Context A) or the ad-hoc prompt text (Context B).

The orchestrator provides both inputs in the dispatch prompt. The critic does not read any other files.

## Agent Dispatch

Launch a fresh general-purpose agent. No worktree isolation — the critic is read-only.

```
Agent tool:
  subagent_type: "general-purpose"
  isolation: none (omit the field)
```

The orchestrator (not the critic agent) writes `clarify_critic` to `events.log` after the critic returns.

Pass the critic this prompt verbatim, substituting the bracketed placeholders:

---

You are challenging a confidence assessment. Your job is to find where the ratings are poorly supported — not to be balanced.

## Confidence Assessment

{confidence assessment text, including the agent's reasoning for each dimension}

## Source Material

{backlog item body or ad-hoc prompt text}

## Instructions

1. Read the confidence assessment and the source material carefully.
2. Derive 3–4 challenge angles from the confidence assessment. The three dimensions you should cover are:
   - **Intent clarity** — is the goal unambiguous and complete as stated in the source?
   - **Scope boundedness** — are the boundaries explicit and grounded in the source, or asserted?
   - **Requirements alignment** — is the claim of alignment (or no conflict) actually supported?
   You may also challenge **complexity/criticality calibration** if the assessment's tier or severity rating appears poorly supported by the source material. Focus on angles most likely to reveal poorly supported ratings for this specific assessment: unsupported High ratings, overlooked ambiguity, scope claims not grounded in the source, requirements alignment asserted without evidence.
3. For each angle, challenge whether the cited reasoning actually comes from the source material — or whether the agent is filling gaps with assumptions. Be specific: quote the source material and the assessment where they diverge.
4. Do not accept the agent's reasoning as settled. The agent wrote the assessment — it may have anchored on its own interpretation. Your job is to surface objections the agent would not raise against itself.
5. Return a list of objections only — one per finding, written as prose. Do not classify or categorize them. Do not recommend fixes. Do not reassure.

Format each objection as a labeled item so the orchestrator can parse them consistently:

```
- Finding: [what the assessment claims or assumes]
  Concern: [why this claim is poorly supported by the source material]
```

Each objection must include both the `Finding` and `Concern` fields. The prose style still applies within each field — write full sentences, quote the source material and the assessment where they diverge, and do not collapse an objection into a single label.

End with: "These are the objections. Proceed as you see fit."

Do not be balanced. Do not summarize what the assessment got right.

---

## Disposition Framework

After the critic agent returns its list of objections, the orchestrator (not the critic) classifies each objection with one of three dispositions. (Apply/Dismiss/Ask classification and the self-resolution step below are reproduced from `/critical-review` Step 4 to avoid silent drift. Dismiss-rationale handling diverges by design: clarify-critic routes rationales to `dismissals[].rationale` per the Dispositioning Output Contract below; `/critical-review` Step 4 emits a count-only user-facing line.)

**Apply** — the objection identifies a concrete problem and the correct fix is clear and unambiguous. Examples: a High confidence rating is demonstrably unsupported by the source, the scope claim contradicts explicit text in the backlog item, the requirements alignment is asserted when no requirements file was loaded. Fix these without asking — revise the affected confidence dimension(s) accordingly.

**Dismiss** — the objection is already addressed by the source material, misreads the stated constraints, or rests on an assumption the source material explicitly rules out.

**Ask** — the fix is not for the orchestrator to decide unilaterally. This covers: (a) genuine preference or scope decisions — e.g., whether a vague phrase in the backlog item should be read narrowly or broadly; (b) genuine orchestrator uncertainty about which reading of the source is correct; (c) consequential ambiguity where either interpretation changes what gets built. Hold these for the consolidated Q&A in §4.

**Before classifying as Ask, attempt self-resolution.** For each objection you are considering classifying as Ask, do a brief check — not an exhaustive search. Re-read the source material and confidence assessment, and consult any requirements context loaded in clarify §2. If the answer is supported by verifiable evidence — explicit text in the source material, a requirements constraint, or a documented project convention — resolve it and reclassify: as Apply (revising the affected confidence dimension accordingly) or as Dismiss. Do not resolve based on inferences from general principles or reasoning you already held before investigating. **Anchor check**: if your resolution relies on conclusions from your prior work on this assessment rather than new evidence found during the check, treat it as Ask — that is anchoring, not resolution. Uncertainty still defaults to Ask. Surviving Ask items flow into the Ask-to-Q&A Merge Rule as before.

**Apply bar**: Apply when and only when the fix is unambiguous and confidence is high. Uncertainty is a legitimate reason to Ask — do not guess and apply. For inconsequential tie-breaks, pick one and apply. For consequential tie-breaks, Ask.

### Dispositioning Output Contract

After classifying every objection, the dispositioning step produces one structured artifact and nothing else. That artifact is the `clarify_critic` event itself — a YAML payload matching the schema defined in `## Event Logging` below, including the `dismissals` array.

- The **sole output** of the dispositioning step is the structured YAML artifact. It is not free-form prose.
- The orchestrator writes this YAML **verbatim** to `lifecycle/{feature}/events.log` as the `clarify_critic` event.
- The user-facing response following the dispositioning step is scoped to (a) the §4 Ask-merge invocation (per Ask-to-Q&A Merge Rule below), and (b) silent application of Apply dispositions to the confidence assessment.
- Dismiss rationales appear only in `dismissals[].rationale` inside the event — never in the user-facing response surface. Because the dispositioning step's only output channel is the structured artifact, there is no prose surface in which a Dismiss rationale could appear.

## Ask-to-Q&A Merge Rule

Ask items from the critic are **not** presented as a blocking escalation separate from §4. They are folded into the §4 question list and presented alongside any remaining low-confidence dimensions as a single consolidated Q&A round. The user sees one set of questions — not a critic-escalation followed by a separate Q&A.

If the critic produces no Ask items, proceed to §4 with only the low-confidence dimension questions (or skip §4 entirely if all dimensions are now high confidence after Apply fixes).

## Event Logging

After the critic agent returns and the orchestrator has applied dispositions, write a `clarify_critic` event to `lifecycle/{feature}/events.log`.

Required fields:

```
ts: <ISO 8601 timestamp>
event: clarify_critic
feature: <feature slug>
findings: <array of prose strings — one per critic objection>
dispositions:
  apply: <count>
  dismiss: <count>
  ask: <count>
applied_fixes: <array of strings describing changes made to the confidence assessment>
dismissals: <array of {finding_index, rationale} objects — one per Dismiss disposition>
status: "ok"
```

`applied_fixes` contains descriptions of the changes the orchestrator made to the confidence assessment as a result of Apply dispositions. If no Apply dispositions were made, `applied_fixes` is an empty array.

`dismissals` is the Dismiss-disposition counterpart to `applied_fixes`. Each entry is `{finding_index: <int>, rationale: <prose>}`: `finding_index` is the zero-based position of the dismissed objection in the `findings` array; `rationale` is the orchestrator's reason for dismissing that objection.

If no Dismiss dispositions were made, `dismissals` is an empty array. The invariant `len(dismissals) == dispositions.dismiss` must hold for every success-path event.

Disposition counts reflect post-self-resolution values. If self-resolution reclassifies an Ask item as Apply, the logged `apply` count increases and `ask` count decreases accordingly, and the resulting fix description is appended to `applied_fixes` (the `applied_fixes` array thus carries initial Apply dispositions and Ask→Apply self-resolution reclassifications). If self-resolution reclassifies an Ask item as Dismiss, `ask` decreases and `dismiss` increases; the resolved rationale lands in `dismissals[].rationale` (not in `applied_fixes`) because `dismissals` is the Dismiss-disposition counterpart to `applied_fixes`.

Example (YAML block format, same as other lifecycle events):

```yaml
- ts: 2026-03-23T14:05:00Z
  event: clarify_critic
  feature: my-feature
  findings:
    - "The High rating for intent clarity is not grounded in the backlog item body — the item says 'improve the workflow' with no further elaboration."
    - "Scope boundedness is rated High but the item mentions both the CLI and the web UI without distinguishing them."
    - "Requirements alignment asserts 'no conflicts' but no requirements file was actually loaded."
    - "Complexity rated simple despite four distinct subsystems named in the body."
  dispositions:
    apply: 1
    dismiss: 2
    ask: 1
  applied_fixes:
    - "Revised intent clarity from High to Low — the goal phrase is genuinely ambiguous."
  dismissals:
    - finding_index: 1  # initial Dismiss disposition — source material explicitly distinguishes the two UIs later in the body
      rationale: "The body's second paragraph distinguishes CLI and web UI; the scope claim is grounded, not asserted."
    - finding_index: 3  # Ask→Dismiss self-resolution reclassification — resolved against a documented project convention
      rationale: "Reclassified from Ask to Dismiss during self-resolution: the four subsystems are orchestration layers within one bounded context per project convention in requirements/project.md; the simple rating holds."
  status: ok
```

## Failure Handling

If the critic agent fails, errors, or times out:

1. Write a `clarify_critic` event with `status: "failed"` and empty `findings`, `applied_fixes`, `dismissals`, and zero counts in `dispositions`.
2. Proceed to §4 as if the critic had not run — cover all original low-confidence dimensions in the Q&A. Do not skip questions because the critic was supposed to run.
3. Do not surface the failure as a blocking error. Note it silently in the event log.

## Constraints

| Thought | Reality |
|---------|---------|
| "Skip the critic if all three dimensions are High confidence" | Always runs — the critic's job is to challenge whether those High ratings are deserved, not to rubber-stamp them. |
| "The critic should classify its own objections as Apply/Dismiss/Ask" | The critic returns prose objections only. The orchestrator applies the disposition framework after the agent returns. |
| "Ask items from the critic should be presented separately before §4" | Ask items are folded into the §4 Q&A and presented as a single consolidated question set alongside any low-confidence dimension questions. |
| "The critic should read files or gather additional context" | The critic receives exactly two inputs: the confidence assessment and the source material. It reads nothing else. |
| "The orchestrator should write the event before reading critic output" | The orchestrator writes the `clarify_critic` event after the critic returns and dispositions are applied — not before. |
| "applied_fixes should summarize the critic's suggestions" | `applied_fixes` contains descriptions of changes the orchestrator actually made. If the orchestrator dismissed or asked about an objection, it does not appear in `applied_fixes`. |
| "Surface Dismiss rationales to the user so they can see the critic's work" | Dismiss rationales go to the `dismissals` array in `events.log` only; the user-facing response surface is reserved for §4 Ask merge and silent Apply confidence revisions. |
