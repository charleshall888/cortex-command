# Clarify Phase

Pre-research ideation gate. Confirms the topic is well-aimed, checks whether it is novel or already covered, and aligns it with project requirements before research begins. Runs before Research — it aims research in the right direction, not after it.

Discovery Clarify is always ad-hoc: there is no backlog item yet. Discovery produces backlog items; it does not consume them.

## Protocol

### 1. Resolve Input

The input is a raw topic name or description. There is no backlog item to resolve — that is what discovery will create.

### 2. Load Requirements Context

Load requirements using the shared tag-based loading protocol — read `../../lifecycle/references/load-requirements.md` and follow it. If no `cortex/requirements/` directory or files exist, note this and skip to §3.

If a concept you need is not yet defined in the glossary, treat the absence as a signal to surface the term in the next requirements interview.

### 3. Check Existing Backlog Coverage

Scan `cortex/backlog/[0-9]*-*.md` titles, tags, and descriptions for overlap with the topic. If a backlog item already covers this topic substantially, surface it to the user and ask whether to proceed with discovery or work from the existing ticket.

### 4. Confidence Assessment

Assess confidence across four ideation-alignment dimensions:

| Dimension | High confidence | Low confidence |
|-----------|----------------|----------------|
| **Topic aim** | The topic has a clear focus — one problem space, one domain | The topic is vague, multi-directional, or conflates distinct problems |
| **Domain** | The domain is identifiable — it belongs clearly to one area of the system | The domain is unclear or spans unrelated areas without a unifying question |
| **Novelty** | No substantial backlog overlap detected | Significant overlap with existing tickets; unclear whether this is truly new |
| **Requirements alignment** | Topic aligns with requirements context; no obvious conflicts | Topic conflicts with requirements, or has no connection to any stated need |

### 5. Question Threshold

**If any dimension is low confidence**: Ask ≤4 targeted questions to resolve the gaps. Focus on what is unclear — do not re-ask what is already obvious from the topic name or context. Wait for answers before continuing.

**If all four dimensions are high confidence**: Skip questions entirely and proceed to §6.

### 6. Produce Clarify Output

Write or present the following outputs — this is the handoff package for Research:

1. **Clarified topic statement**: One sentence describing what this discovery will investigate and why. Example: "Explore options for replacing the pipeline orchestrator with a simpler overnight-backed flow, focused on reducing duplication in the execution layer."

2. **Domain note**: Which area(s) of the project this touches (e.g., "Skills & workflow engine — orchestration layer").

3. **Requirements alignment note**: One of:
   - "Aligned with cortex/requirements/{file}: [brief summary of relevant constraints or goals]"
   - "Partial alignment: [what aligns and what doesn't]"
   - "No requirements files found — alignment check skipped"
   - "Conflict detected: [describe the conflict]" — if conflict, resolve with user before proceeding

4. **Open questions for research**: Bulleted list of questions to carry into Research (may be empty). These are questions best resolved by investigation — not user answers.

5. **Research-sizing complexity**: `simple` or `complex`. This sizes the research fan-out ONLY — it is *not* the implementation-complexity that /cortex-core:refine or /cortex-core:lifecycle assess later when a ticket is ready to build. It feeds the shared fan-out matrix at `../../lifecycle/references/fanout.md` (the tier axis), which discovery's Research phase reads to decide how many parallel agents to dispatch.

   Skew toward `complex` for any topic that is multi-faceted or seeds a whole epic. Discovery sits at the top of an epic and sets its initial direction; an under-sized research pass here risks a shallow, wrong direction that then propagates across every ticket the discovery spawns. Because that divergence is expensive to unwind, prefer the wider investigation when the topic is anything beyond a single, self-contained question. State the assessment with brief reasoning and proceed.

6. **Research-sizing criticality**: `low | medium | high | critical`. Like the complexity output above, this sizes the research fan-out ONLY (it feeds the criticality axis of the same `../../lifecycle/references/fanout.md` matrix) and is distinct from the implementation-criticality assessed later by /refine or /lifecycle.

   Discovery's research-sizing assessment is deliberately biased *upward* relative to how the same topic would rate under refine/lifecycle, because discovery is high-leverage: it sets the direction the whole epic inherits, and a wrong direction is costly to reverse once tickets are spawned. So criticality **floors at `medium`** — never rate a discovery topic `low`. Raise it to `high` or `critical` when the topic seeds a whole epic or sets direction across multiple tickets. Apply judgment to where on that range the topic lands rather than a mechanical lookup. State the assessment with brief reasoning and proceed.

7. **Scope envelope** (optional): The agent decides per topic whether to produce this. When the topic's boundaries are tractable at clarify time, emit in-scope/out-of-scope bullets to constrain what Research investigates:
   - **In scope**: bulleted list of areas/questions Research should pursue
   - **Out of scope**: bulleted list of adjacent concerns explicitly excluded from this discovery
   
   When boundaries cannot be pre-locked (topic is too exploratory, or scope itself is part of what Research must determine), emit "No envelope needed" with a one-line reason. Fire when boundaries are tractable; skip when they are not.

### Persist the research-sizing assessment

Discovery supports independent phase entry — a user can run `/cortex-core:discovery research <topic>` in a fresh session, without Clarify's conversation context. So the two research-sizing values above (outputs 5–6) must be persisted now, while you have them, so Research can read them back across that boundary. Conversation memory alone does not survive a phase-resume.

Persist the assessment by invoking:

```
cortex-discovery emit-research-sizing --topic <topic> --complexity <simple|complex> --criticality <low|medium|high|critical>
```

This records a durable `discovery_research_sizing` entry on the topic's events.log (the helper resolves the correct path — never hardcode it). Research reads it back at entry to size its fan-out.

## Constraints

| Thought | Reality |
|---------|---------|
| "I should assess complexity and criticality" | Discovery Clarify assesses a *research-sizing* complexity/criticality only (§4, outputs 5–6) — its sole job is sizing the research fan-out, biased upward because discovery sets an epic's initial direction. It does not assess *implementation* complexity; that assessment happens in /cortex-core:refine or /cortex-core:lifecycle when a ticket is ready to build. |
| "I should look for a backlog item to match" | Discovery produces backlog items; it does not start from them. The backlog coverage check (§3) looks for overlap to avoid duplicating existing work, not to resolve an input. |
| "I should research feasibility here" | That is Research's job. Clarify only checks aim, domain, novelty, and alignment. |
