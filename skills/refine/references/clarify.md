# Clarify Phase

Pre-research intent gate: confirms what's being built and why, aligns with project requirements, sets complexity and criticality, and surfaces targeted questions when intent is unclear. Runs before Research — it aims research in the right direction, not after it.

## Protocol

### 1. Resolve Input

Input is resolved at refine SKILL.md Step 1 (`cortex-resolve-backlog-item` + its unambiguous / ambiguous / no-match / error branching); this phase consumes the result. On an unambiguous match, use the exit-0 JSON fields (`filename`, `backlog_filename_slug`, `title`, `lifecycle_slug`) directly (don't re-derive slugs) and read the backlog item's frontmatter and body.

- **Context A — Backlog item**: input resolved to a `cortex/backlog/NNN-*.md`; use the JSON fields downstream.
- **Context B — Ad-hoc prompt**: raw text (topic or description) with no matching item. Assess it directly — the intent statement and complexity/criticality still apply; backlog write-backs are skipped. Optionally offer `/cortex-backlog:backlog new` with the disciplined body template; if impractical, note it and proceed.

**Title-phrase predicate**: title-phrase input matches when `slugify(input)` is a substring of `slugify(title)`.

### 2. Load Requirements Context

Run `cortex-load-requirements --feature {slug}` (the shared protocol, `load-requirements.md`). Read every listed non-skipped path and inject the printed path list into any downstream prompt that needs scope, relaying any fallback note. No `cortex/requirements/` files → note it and proceed.

### 3. Confidence Assessment

Assess three dimensions:

| Dimension | High confidence | Low confidence |
|-----------|-----------------|----------------|
| **Intent clarity** | one clear, unambiguous outcome | vague, multi-interpretable, or contradictory |
| **Scope boundedness** | in/out explicit | open-ended, unbounded, or conflated with adjacent work |
| **Requirements alignment** | aligns with cortex/requirements/, no conflicts | conflicts with, ignores, or has no connection to requirements |

> A prescriptive ticket body (one suggesting a fix or approach) does NOT make scope more bounded — treat implementation suggestions as unvalidated hypotheses for research, not scope constraints. A detailed suggestion should not raise the scope-boundedness rating.

Context B (ad-hoc): assess requirements alignment as "no requirements files found" if §2 was skipped.

### 3a. Critic Review

Read the **clarify-critic** sibling at the propagated absolute path (target: `${CLAUDE_SKILL_DIR}/references/clarify-critic.md`) and follow its protocol. After the critic completes, the orchestrator writes the `clarify_critic` event to `cortex/lifecycle/{feature}/events.log` with the post-critic status.

### 4. Question Threshold

**All three dimensions high after §3a AND no critic Ask items** → skip questions entirely, proceed to §5.

**Any dimension still low after §3a, or critic raised Ask items** → merge all questions into one list and present via AskUserQuestion, cap ≤5. Over 5 → prioritize critic Ask items first (independent challenge), then the highest-impact low-confidence dimension questions; drop lower-priority ones to stay under the cap. Ask only about specific gaps — never for completeness, and never re-ask what's already clear from the backlog item or prior context. Wait for answers before continuing.

### 5. Produce Clarify Output

Write or present these five outputs — the handoff package for Research:

1. **Clarified intent statement** — one sentence: what's being built and why (from the backlog description in Context A, or the user's answers in Context B). The anchor for research scope.
2. **Complexity** — `simple` or `complex`:
   - simple: 1–3 files, mechanical (rename, reword, add a field), follows an existing pattern exactly, one obvious approach, no behavioral effect on callers.
   - complex: 4+ files, OR modifies shared infrastructure / core workflow orchestration, OR cross-cutting behavioral effects on other skills or downstream processes, OR requires design-trade-off judgment calls, OR introduces new patterns.
   When in doubt, prefer `complex`.
3. **Criticality** — `low | medium | high | critical`:
   - low: minimal impact, easily reversed, no meaningful downstream deps (comment fix, typo).
   - medium: affects users or developers but recoverable; isolated tooling change with no downstream consumers.
   - high: significant impact or hard to reverse, OR any change to shared skills / workflow infrastructure / overnight runner / hooks other capabilities depend on — **the appropriate default for most skill and agentic-layer changes**.
   - critical: severe consequences — security, data loss, financial, OR loss of a core capability everything else depends on.
   Default to `medium` only for clearly isolated, easily-reverted tooling changes. State both assessments with brief reasoning and proceed — do not ask the user to confirm.
4. **Requirements alignment note** — one of: aligned (name the `cortex/requirements/{file}` and the relevant constraints/goals), partial (what aligns and what doesn't), no requirements files found (check skipped), or conflict (describe it). Resolve a detected conflict with the user before proceeding.
5. **Open questions for research** — bulleted (may be empty): questions needing investigation, not user answers — ambiguities best resolved by reading code.

### 6. Research Sufficiency Criteria

Defined here but applied at Research phase entry (not during Clarify): when Research entry evaluates an existing `cortex/lifecycle/{slug}/research.md`, use these signals. **Research is sufficient if none are present**:

- (a) research.md was clearly written for a different feature scope — its goal differs materially from the clarified intent statement.
- (b) files named in the backlog item's description or acceptance criteria don't appear in research.md's codebase findings (wherever the codebase-angle content sits).
- (c) research.md's codebase findings are empty or generic — no specific file paths or patterns for this feature.
- (d) requirements context changed significantly since the research was written (compare the research content against current requirements files).

None of (a)–(d) apply → treat existing research as sufficient, skip re-running, proceed to Spec. Any apply → flag the specific signal(s), explain the insufficiency, and rerun research.

### 7. Write-Backs (Context A only)

After producing the complexity and criticality assessments, write them per refine SKILL.md Step 3's canonical write-back block — backend resolution (`cortex-read-backlog-backend`), the `cortex-update-item --complexity --criticality` call on `cortex-backlog`, the `none` and external-backend arms, failure handling, and the Context B skip.

## Constraints

Out of scope for Clarify:

- The deep requirements interview — that happens in Specify, after Research. Different gates.
- Technical feasibility — that is Research's job. Clarify checks only intent, scope, and requirements alignment.
