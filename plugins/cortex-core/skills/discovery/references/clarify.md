# Clarify Phase

Pre-research ideation gate. Confirms the topic is well-aimed, novel, and aligned with project requirements before Research begins.

Discovery Clarify is always ad-hoc: there is no backlog item yet. Discovery produces backlog items; it does not consume them.

## Protocol

### 1. Resolve Input

The input is a raw topic name or description. There is no backlog item to resolve — that is what discovery will create.

### 2. Load Requirements Context

Run `cortex-load-requirements` (omit `--feature`; discovery has no lifecycle index, so it falls back to project.md + Global Context) per the shared tag-based protocol (`load-requirements.md`). Read every listed non-skipped path into context and inject the printed path list into downstream prompts (relay any fallback note). No `cortex/requirements/` directory or files → note this and skip to §3.

### 3. Check Existing Backlog Coverage

Resolve the active backlog backend once with `cortex-read-backlog-backend` (argless, prints the backend, exits 0); route:

- **`cortex-backlog`** (default) → scan `cortex/backlog/[0-9]*-*.md` titles, tags, and descriptions for overlap. If a backlog item already covers this topic substantially, surface it and ask whether to proceed with discovery or work from the existing ticket.
- **any other value** (`none` or external) → skip the scan with a one-line advisory that backlog coverage checking is disabled for this repo; novelty defaults to "no overlap detected" (the safe, non-blocking direction).

Two arms, not decompose §5's three — a read path has no external-tracker query to fall to.

### 4. Confidence Assessment

Assess confidence across four ideation-alignment dimensions:

| Dimension | High confidence | Low confidence |
|-----------|----------------|----------------|
| **Topic aim** | Clear focus — one problem space, one domain | Vague, multi-directional, or conflates distinct problems |
| **Domain** | Identifiable — belongs clearly to one area of the system | Unclear or spans unrelated areas without a unifying question |
| **Novelty** | No substantial backlog overlap detected | Significant overlap with existing tickets; unclear if truly new |
| **Requirements alignment** | Aligns with requirements context; no obvious conflicts | Conflicts with requirements, or no connection to any stated need |

### 5. Question Threshold

**Any dimension low confidence**: Ask ≤4 targeted questions to resolve the gaps — only what's unclear, not what the topic name or context already answers. Wait for answers before continuing.

**All four high confidence**: Skip questions and proceed to §6.

### 6. Produce Clarify Output

Write or present the handoff package for Research:

1. **Clarified topic statement**: One sentence describing what this discovery will investigate and why.

2. **Domain note**: Which area(s) of the project this touches (e.g., "Skills & workflow engine — orchestration layer").

3. **Requirements alignment note**: One of:
   - "Aligned with cortex/requirements/{file}: [brief summary of relevant constraints or goals]"
   - "Partial alignment: [what aligns and what doesn't]"
   - "No requirements files found — alignment check skipped"
   - "Conflict detected: [describe the conflict]" — if conflict, resolve with user before proceeding

4. **Open questions for research**: Bulleted list carried into Research (may be empty) — questions investigation should resolve, not the user.

5. **Research-sizing complexity**: `simple` or `complex`. Sizes the research fan-out only — not the implementation-complexity /cortex-core:refine or /cortex-core:lifecycle assess later. Feeds the tier axis of the shared **fanout** reference (`${CLAUDE_SKILL_DIR}/../research/references/fanout.md`, propagated in SKILL.md Step 3), which Research reads to size its parallel-agent dispatch.

   Skew toward `complex` for any multi-faceted topic or one that seeds a whole epic — an under-sized pass here risks a shallow, wrong direction propagating across every ticket the epic spawns. Prefer the wider investigation whenever the topic is more than a single, self-contained question. State the assessment with brief reasoning.

6. **Research-sizing criticality**: `low | medium | high | critical` — the criticality axis of the same **fanout** reference, sizing the research fan-out only (not implementation-criticality).

   Biased upward for the same reason as output 5: criticality **floors at `medium`** — never `low`. Raise to `high` or `critical` when the topic seeds a whole epic or sets direction across multiple tickets. State the assessment with brief reasoning.

7. **Scope envelope** (optional): When the topic's boundaries are tractable at clarify time, emit in-scope/out-of-scope bullets to constrain Research. When they can't be pre-locked (too exploratory, or scope is itself what Research must determine), emit "No envelope needed" with a one-line reason.

### Persist the Research-Sizing Assessment

Discovery supports independent phase entry — a user can run `/cortex-core:discovery research <topic>` in a fresh session, without Clarify's conversation context. Persist outputs 5–6 now so Research can read them back across that boundary; conversation memory doesn't survive a phase-resume.

```
cortex-discovery emit-research-sizing --topic <topic> --complexity <simple|complex> --criticality <low|medium|high|critical>
```

Records a durable `discovery_research_sizing` entry on the topic's events.log (helper resolves the path — never hardcode it). Research reads it back at entry.
