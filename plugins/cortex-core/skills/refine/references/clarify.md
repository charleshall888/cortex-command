# Clarify Phase

Pre-research intent gate: confirms what's being built and why, aligns with requirements, sets complexity/criticality, and surfaces targeted questions when intent is unclear — runs before Research to aim it correctly.

## Protocol

### 1. Resolve Input

Input is resolved at refine SKILL.md Step 1; this phase reads the backlog item's frontmatter and body.

- **Context A — Backlog item**: input resolved to a `cortex/backlog/NNN-*.md`; use Step 1's JSON fields downstream.
- **Context B — Ad-hoc prompt**: raw text (topic or description), no matching item. Assess directly — intent statement and complexity/criticality still apply; backlog write-backs are skipped. Optionally offer `/cortex-backlog:backlog new`'s disciplined body template; if impractical, note it and proceed.

### 2. Load Requirements Context

Run `cortex-load-requirements --feature {slug}` (shared protocol: `load-requirements.md`); read every listed non-skipped path and inject the printed path list into downstream prompts needing scope, relaying any fallback note. No `cortex/requirements/` → note it and proceed.

### 3. Confidence Assessment

Assess three dimensions:

| Dimension | High confidence | Low confidence |
|-----------|-----------------|----------------|
| **Intent clarity** | one clear, unambiguous outcome | vague, multi-interpretable, or contradictory |
| **Scope boundedness** | in/out explicit | open-ended, unbounded, or conflated with adjacent work |
| **Requirements alignment** | aligns with cortex/requirements/, no conflicts | conflicts with, ignores, or has no connection to requirements |

> A prescriptive ticket body (one suggesting a fix or approach) does NOT make scope more bounded — treat implementation suggestions as unvalidated hypotheses for research, not scope constraints.

Context B (ad-hoc): assess requirements alignment as "no requirements files found" if §2 was skipped.

### 3a. Critic Review

Read the **clarify-critic** sibling at the propagated absolute path (target: `${CLAUDE_SKILL_DIR}/references/clarify-critic.md`) and follow its protocol. After the critic completes, the orchestrator writes the `clarify_critic` event to `cortex/lifecycle/{feature}/events.log` with the post-critic status.

### 4. Question Threshold

**All three dimensions high after §3a AND no critic Ask items** → skip questions entirely, proceed to §5.

<!-- pause: clarify-question-batch question -->
**Any dimension still low after §3a, or critic raised Ask items** → merge into one list, present via AskUserQuestion, cap ≤5. Over 5 → prioritize critic Ask items first, then highest-impact low-confidence questions; drop the rest. Ask only about specific gaps — never for completeness, never re-asking what's already clear. Wait for answers before continuing.

### 5. Produce Clarify Output

Write or present these five outputs — the handoff package for Research:

1. **Clarified intent statement** — one sentence: what's being built and why (from the backlog description in Context A, or the user's answers in Context B). The anchor for research scope.
2. **Complexity** — `simple` or `complex`:
   - simple: 1–3 files, mechanical (rename, reword, add a field), an existing pattern followed exactly, no behavioral effect on callers.
   - complex: 4+ files, OR shared infrastructure/core workflow orchestration, OR cross-cutting effects on other skills/downstream processes, OR design-trade-off judgment calls, OR new patterns.
   When in doubt, prefer `complex`.
3. **Criticality** — `low | medium | high | critical`:
   - low: minimal impact, easily reversed, no meaningful downstream deps (comment fix, typo).
   - medium: affects users or developers but recoverable; isolated tooling change with no downstream consumers.
   - high: significant impact or hard to reverse, OR any change to shared skills / workflow infrastructure / overnight runner / hooks other capabilities depend on — **the appropriate default for most skill and agentic-layer changes**.
   - critical: severe consequences — security, data loss, financial, OR loss of a core capability everything else depends on.
   Default `medium` only for clearly isolated, easily-reverted tooling changes. State both with brief reasoning and proceed without confirming.
4. **Requirements alignment note** — one of: aligned (name `cortex/requirements/{file}` and the relevant constraints/goals), partial (what aligns, what doesn't), no requirements files found (check skipped), or conflict (describe it, resolve with the user before proceeding).
5. **Open questions for research** — bulleted (may be empty): questions needing investigation, not user answers — ambiguities best resolved by reading code.

### 6. Research Sufficiency Criteria

Defined here, applied at Research phase entry (not during Clarify) against an existing `cortex/lifecycle/{slug}/research.md`. **Sufficient if none of these signals are present**:

- (a) research.md's goal differs materially from the clarified intent statement (written for a different feature scope).
- (b) files named in the backlog item's description/acceptance criteria don't appear in research.md's codebase findings.
- (c) research.md's codebase findings are empty or generic — no specific file paths or patterns for this feature.
- (d) requirements context changed significantly since the research was written.

None of (a)–(d) apply → treat existing research as sufficient, skip re-running, proceed to Spec. Any apply → flag the specific signal(s), explain the insufficiency, and rerun research.

### 7. Write-Backs (Context A only)

After producing the complexity and criticality assessments, write them per refine SKILL.md Step 3's canonical write-back routing (Context B skips).

## Constraints

Out of scope for Clarify:

- The deep requirements interview — that happens in Specify, after Research. Different gates.
- Technical feasibility — that is Research's job. Clarify checks only intent, scope, and requirements alignment.
