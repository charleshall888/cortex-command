# Clarify Phase

Pre-research intent gate. Confirms what is being built and why, aligns with project requirements, determines complexity and criticality, and surfaces targeted questions when intent is unclear. Runs before Research — it aims research in the right direction, not after it.

## Protocol

### 1. Resolve Input

Run:

```bash
cortex-resolve-backlog-item <input>
```

Branch on the exit code:

- **Exit 0** — unambiguous match (**Context A**). Parse stdout JSON; the object contains exactly four fields: `filename`, `backlog_filename_slug`, `title`, `lifecycle_slug`. Use these directly in subsequent phases. Do not re-derive slugs from scratch. Read the backlog item's frontmatter (`title`, `description`, `status`) and body.
- **Exit 2** — ambiguous match. Read the `<filename>\t<title>` candidate lines from stderr. Present them to the user and ask them to select one. Re-invoke `cortex-resolve-backlog-item` with the chosen filename slug, or treat the user's selection directly as the resolved item (Context A).
- **Exit 3** — no match. Switch to **Context B** (ad-hoc topic) and treat the input as the topic name. Offer to invoke `/cortex-backlog:backlog new` to create a backlog item with the disciplined body template before continuing — if this seems impractical, note it and proceed without.
- **Exit 64** (usage error) / **Exit 70** (internal error) — halt and surface the stderr diagnostic; do not fall through to disambiguation.

**Context A — Backlog item**: Input resolved to a `cortex/backlog/NNN-*.md` file; use the exit-0 JSON fields downstream.

**Context B — Ad-hoc prompt**: Input is raw text (a topic name or description) with no matching backlog item. Assess the prompt directly. The output intent statement and complexity/criticality assessments still apply; backlog write-backs are skipped.

**Title-phrase predicate**: title-phrase input matches when `slugify(input)` is a substring of `slugify(title)`.

### 2. Load Requirements Context

Load requirements using the shared tag-based loading protocol — read the protocol at the propagated absolute path (target: `${CLAUDE_SKILL_DIR}/references/load-requirements.md`) and follow it. If no `cortex/requirements/` directory or files exist, note this and proceed.

### 3. Confidence Assessment

Assess confidence across three dimensions:

| Dimension | High confidence | Low confidence |
|-----------|----------------|----------------|
| **Intent clarity** | Goal is unambiguous — one clear outcome | Goal is vague, multi-interpretable, or contradictory |
| **Scope boundedness** | Boundaries are explicit — what is in and out is clear | Scope is open-ended, unbounded, or conflated with adjacent work |
| **Requirements alignment** | Request aligns with cortex/requirements/ context; no conflicts detected | Request conflicts with, ignores, or has no connection to requirements context |

> **Note:** A prescriptive ticket body — one that suggests a specific fix or approach — does not make scope "more bounded." Treat implementation suggestions as unvalidated hypotheses for the research phase, not constraints on scope; a detailed suggestion in the body should not raise the scope-boundedness rating.

For Context B (ad-hoc), assess requirements alignment as "no requirements files found" if §2 was skipped.

### 3a. Critic Review

Read the **clarify-critic** sibling reference at the propagated absolute path (target: `${CLAUDE_SKILL_DIR}/../refine/references/clarify-critic.md`) and follow its protocol. After the critic completes, the orchestrator writes the `clarify_critic` event to `cortex/lifecycle/{feature}/events.log` with the post-critic status.

### 4. Question Threshold

**If all three dimensions are high confidence after §3a AND the critic raised no Ask items**: Skip questions entirely and proceed to §5.

**If any dimension is still low confidence after §3a, or if the critic raised Ask items**: Merge all questions into a single list. Present via AskUserQuestion with a cap of ≤5 questions. If the merged list exceeds 5, prioritize critic Ask items first (they came from independent challenge), then the highest-impact low-confidence dimension questions — drop lower-priority questions to stay within the cap.

Ask only about specific gaps — never for completeness, and do not re-ask what is already clear from the backlog item or prior context. Wait for user answers before continuing.

### 5. Produce Clarify Output

Write or present the following five outputs — this is the handoff package for Research:

1. **Clarified intent statement**: One sentence describing what is being built and why. Derived from the backlog item description (Context A) or the user's answers (Context B). This is the anchor for research scope.

2. **Complexity assessment**: `simple` or `complex`, using the lifecycle complexity dimensions:
   - Simple: 1–3 files, mechanical change (rename, reword, add a field), follows existing pattern exactly, 1 obvious approach, no behavioral effects on callers
   - Complex: 4+ files, OR modifies shared infrastructure / core workflow orchestration, OR has cross-cutting behavioral effects on other skills or downstream processes, OR requires judgment calls about design trade-offs, OR introduces new patterns
   When in doubt, prefer `complex`.

3. **Criticality assessment**: `low | medium | high | critical`, using the lifecycle criticality levels:
   - low: minimal impact, easily reversed, no meaningful downstream dependencies (e.g., a comment fix, a typo correction)
   - medium: affects users or developers but recoverable; isolated tooling change with no downstream consumers
   - high: significant impact or hard to reverse, OR any change to shared skills / workflow infrastructure / overnight runner / hooks that other capabilities depend on — **this is the appropriate default for most skill and agentic layer changes**
   - critical: severe consequences — security, data loss, financial, OR loss of a core capability everything else depends on
   Default to `medium` only for clearly isolated, easily-reverted tooling changes (e.g., a standalone UI tweak with no shared dependencies).
   State both assessments with brief reasoning and proceed — do not ask the user to confirm.

4. **Requirements alignment note**: One of:
   - "Aligned with cortex/requirements/{file}: [brief summary of relevant constraints or goals]"
   - "Partial alignment: [what aligns and what doesn't]"
   - "No requirements files found — requirements alignment check skipped"
   - "Conflict detected: [describe the conflict]" — if conflict, resolve with user before proceeding

5. **Open questions for research**: Bulleted list of questions to carry into the research phase (may be empty). These are questions that need investigation (not user answers) — ambiguities best resolved by reading code, not asking.

### 6. Research Sufficiency Criteria

These criteria are defined here but applied at Research phase entry, not during Clarify: when Research phase entry evaluates an existing `cortex/lifecycle/{slug}/research.md`, apply them to determine whether it is sufficient or must be rerun.

**Research is sufficient if none of the following signals are present:**

- (a) The research.md was clearly written for a different feature scope — the goal described in the research differs materially from the clarified intent statement.
- (b) Files named in the backlog item's description or acceptance criteria do not appear in research.md's codebase findings (the codebase-angle content, wherever it appears in the artifact).
- (c) research.md's codebase findings are empty or generic — no specific file paths or patterns for this feature are mentioned.
- (d) Requirements context has changed significantly since the research was written — judge by comparing the research content against the current requirements files.

**If none of (a)–(d) apply**: treat existing research as sufficient; skip re-running research and proceed directly to Spec.

**If any of (a)–(d) apply**: flag the specific signal(s), explain why the research is insufficient, and rerun research.

### 7. Write-Backs (Context A only)

After producing the complexity and criticality assessments, write them to the backlog item — gated on the active backend, resolved once via `` `cortex-read-backlog-backend` `` (argless; it prints the resolved backend and exits 0). On `cortex-backlog` (the default arm), run:

```bash
cortex-update-item {backlog-filename-slug} --complexity {value} --criticality {value}
```

Use `backlog_filename_slug` from §1 as `{backlog-filename-slug}`.

On `none`, skip this write-back with a one-line advisory that backlog write-back is disabled for this repo. On any other (external) backend, make the equivalent complexity/criticality update best-effort on the configured tracker per `backlog.instructions`, surfacing the composed values if it cannot be completed. The lifecycle `events.log` remains the authoritative tier/criticality feed regardless of backend, so the critical-review gate stays correctly fed.

If `cortex-update-item` fails, surface the error and ask the user to resolve it before proceeding. Do not silently skip write-backs. On exit 2, apply the canonical ambiguous-slug handling in backlog-writeback.md (loaded at lifecycle Step 2).

For Context B (ad-hoc), skip this step — there is no backlog item to update.

## Constraints

Out of scope for Clarify:

- The deep requirements interview — that happens in Specify, after Research. These are different gates.
- Technical feasibility — that is Research's job. Clarify only checks intent, scope, and requirements alignment.
