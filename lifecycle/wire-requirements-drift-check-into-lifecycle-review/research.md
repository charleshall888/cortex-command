# Research: Wire requirements drift check into lifecycle review

## Epic Reference

Epic research at [`research/requirements-audit/research.md`](../../../research/requirements-audit/research.md). That research covered the full requirements management audit (project.md accuracy, missing area docs, skill path bug, process gaps). This ticket is scoped specifically to the lifecycle review phase integration — making drift detection mandatory rather than absent or advisory.

---

## Codebase Analysis

### Files that will change

**Primary:**
- `skills/lifecycle/references/review.md` — the sole authoritative file for the review phase protocol and artifact format. All substantive changes land here: add a mandatory `## Requirements Drift` section, update the reviewer prompt to include explicit drift detection instructions, and update the constraints table.

**Secondary:**
- `claude/overnight/report.py` — add a `_read_requirements_drift(feature)` helper (following the `_read_verification_strategy()` pattern) and call it from `render_completed_features()`. Must also cover features where review.md exists but the feature has not yet reached `merged` status (for interrupted overnight sessions).

**No changes required:**
- `skills/lifecycle/SKILL.md` — state detection reads `"verdict"` from the review artifact JSON block; new sections alongside it don't affect parsing, unless we add a drift field to the verdict JSON (see Open Questions).
- `requirements/project.md` — read-only input during review; not modified by this feature.

### Existing patterns

**Review artifact format (current `review.md` reference):**
- `## Stage 1: Spec Compliance` — per-requirement PASS/FAIL/PARTIAL verdict table; required
- `## Requirements Compliance` — conditional ("Only present if project/area requirements were loaded"); checks the implementation doesn't violate existing requirements
- `## Stage 2: Code Quality` — required if Stage 1 has no FAIL
- `## Verdict` — required; machine-parsed JSON block: `{"verdict": "APPROVED", "cycle": 1, "issues": []}`

The state machine in `SKILL.md` Step 2 parses `"verdict"` from this JSON by exact field name and exact string values. Adding a field to this block is additive and safe. Adding fields outside the block (as new sections) does not affect state detection.

**Morning report pattern (`_read_verification_strategy()`):** A standalone helper reads from a lifecycle artifact by section heading, returns a string, and is called from `render_completed_features()`. Returns `""` when the artifact is absent. The `_read_requirements_drift()` helper should follow this exact pattern.

**Event log (`review_verdict` event):** `{"ts": ..., "event": "review_verdict", "feature": ..., "verdict": ..., "cycle": ...}`. A `"requirements_drift": "none" | "detected"` key can be added to this event additively without breaking existing consumers.

### Overlap with existing `## Requirements Compliance` section

The current `## Requirements Compliance` section and the proposed `## Requirements Drift` section cover overlapping ground. Both check alignment between implementation and requirements docs. The distinction (compliance = implementation violates existing requirements; drift = requirements are outdated/incomplete relative to implementation) is valid but subtle, and a reviewer will likely confuse or duplicate them.

**Resolution**: Remove the existing `## Requirements Compliance` section entirely and replace it with a mandatory `## Requirements Drift` section. Define it broadly: both directions (implementation violates requirements AND implementation introduces behavior not reflected in requirements). One section, one format, one clear job.

### Area doc availability caveat

As of 2026-04-03, `requirements/` contains only `project.md`. The four area docs (`observability.md`, `pipeline.md`, `remote-access.md`, `multi-agent.md`) are the subject of separate backlog work. The drift check will degrade to project.md-only for most features until area docs exist. This is acceptable — a drift check against project.md is better than no drift check.

---

## Web Research

### Industry convergence: log-only drift detection

All credible implementations (Drift/Fiberplane, spec-kit-sync, AGET, Kiro) follow the same pattern: detect and flag in the review artifact; require explicit human action to update the requirements source. Autonomous spec rewriting by AI agents is an anti-pattern — agents lack the business judgment to distinguish implementation compromise from intent change, and can silently overwrite compliance constraints.

### Prior art for the field structure

- **RUP Iteration Assessment** — "Results Relative to Evaluation Criteria": documents what was delivered vs. stated acceptance criteria. The closest structural analog to `requirements_drift`. A required field in the phase assessment artifact.
- **spec-kit-sync** — three-bucket classification: `Aligned / Drifted / Unverifiable`. Enforces three-phase separation: analyze (detect only) → propose (suggest) → apply (human approval required).
- **AGET** — mandatory conformance check field; presence-and-population required before phase progression.

### Relevance scoping

The spec-kit/living-spec community converges on: "relevant requirements are those with trace links to the feature being reviewed" — i.e., requirements referenced in the spec's acceptance criteria. This bounds the check to claimed scope, not all requirements files. This is more tractable than full requirements coverage and avoids the "false no-drift" failure mode.

---

## Requirements & Constraints

**From `requirements/project.md`:**
- File-based state: all artifacts are plain files. No new databases or event streams.
- Overnight/graceful partial failure: "Surface all failures in the morning report. Keep working on other tasks. Stop only if the failure blocks all remaining work." Drift detection must not stall overnight sessions.
- Complexity discipline: "Must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct."

**From `skills/lifecycle/references/review.md`:**
- Reviewer sub-task is read-only. Cannot update requirements files.
- Verdict JSON block fields (`verdict`, `cycle`, `issues`) are machine-parsed by the state machine. Cannot be removed or renamed; can be extended additively.
- CHANGES_REQUESTED cycle 2 → escalate to user. Drift findings must not trigger this path.
- Review phase is "forced regardless of tier" at high criticality (this feature is `high`).

**From `skills/lifecycle/SKILL.md` Step 2:**
- State detection parses `"verdict"` from review.md's JSON block. Review.md present + verdict parsed = review phase complete. No other field in review.md is checked.

---

## Tradeoffs & Alternatives

### Approach A (recommended): Inline `## Requirements Drift` section in review.md

Add a mandatory `## Requirements Drift` section to the review artifact format and to the reviewer prompt. Three-state structured format. Morning report reads and surfaces it as a subsection.

**Pros:** Minimal surface area (one file changed); consistent with existing artifact convention; state detection unaffected; enforceability via verdict JSON extension is possible.

**Cons:** Drift findings and pass/fail verdict co-located in one file (different audience concerns). Bloat risk when drift is extensive.

### Approach B: Separate `drift.md` artifact

**Rejected.** A reviewer sub-task that must produce two required outputs (review.md + drift.md) will silently drop one on context overflow or timeout. State detection does not check drift.md — it becomes advisory immediately.

### Approach C: Events.log entry

**Rejected.** The reviewer sub-task cannot log to events.log (the orchestrator owns that). Adding a two-step handoff (sub-task passes findings back to orchestrator for logging) is fragile. Events.log is not designed for human-readable multi-line content.

### Approach D: Checklist item in Stage 1

**Rejected.** Structurally too compressed for a list-of-changes. The checklist pattern (PASS/FAIL/PARTIAL) cannot hold "list of drifted requirements with pointers to files that need updating." Collapses two distinct questions (spec compliance and requirements currency) into one item.

### Recommended approach

**Approach A**, with these specific design choices:

1. **Replace** `## Requirements Compliance` with `## Requirements Drift` (unified, mandatory, both directions)
2. **Three-state format** enforced via fill-in template in reviewer prompt:
   ```
   ## Requirements Drift

   **State**: none | detected-pending | detected-done
   **Findings**:
   - (one bullet per drifted item, or "None" if state is none)
   **Update needed**: (path to requirements file that needs updating, or "None")
   ```
3. **Area doc loading**: The orchestrator (not the reviewer sub-task) determines which area docs are relevant before dispatching the reviewer. Heuristic: read `lifecycle/{slug}/index.md` tags; map tags to area doc paths using project.md's Conditional Loading phrases; inject concrete file list into reviewer prompt. Fall back to project.md only if no tags match.
4. **Drift must not influence verdict**: Explicit instruction in reviewer prompt — drift findings are observations; the verdict (APPROVED/CHANGES_REQUESTED/REJECTED) reflects spec compliance and code quality only.
5. **Morning report**: `_read_requirements_drift()` surfaces findings for all features where review.md exists, not just merged features.

---

## Adversarial Review

### Conditional Loading table is not machine-parseable

project.md's Conditional Loading table uses natural-language trigger phrases. The reviewer sub-task (or the orchestrator mapping tags to docs) must semantically match feature tags against these phrases — a task where LLMs hallucinate. Additionally, the area docs don't yet exist. **Mitigation** (applied in recommended approach): the orchestrator — not the reviewer sub-task — determines area doc paths, and injects a concrete list into the reviewer prompt. The orchestrator failing to find matching docs is explicit ("loading project.md only"); the reviewer doesn't guess.

### Mandatory section with no enforcement mechanism

The state machine accepts any review.md with a valid verdict JSON block. A context-overflowed reviewer will write Stage 1 + verdict and stop; the missing drift section is undetected. **Mitigation**: either (a) add `"requirements_drift": "none"|"detected"` to the verdict JSON block — state machine can then refuse to accept a review.md missing this field — or (b) add a pre-event validation pass in the orchestrator before logging `review_verdict`. Option (a) is cleaner (reuses machine-parsed infrastructure); option (b) adds logic outside the artifact (see Open Questions).

### Three-state format is unenforced without a template

Free prose in `## Requirements Drift` breaks the morning report renderer. **Mitigation**: strict fill-in template in the reviewer prompt (see recommended approach above). The renderer keys on `**State**:` to extract classification and `**Findings**:` for the bullet list.

### Drift finding creates ambiguous verdict mapping

A reviewer that interprets detected drift as a compliance failure will issue CHANGES_REQUESTED. The implementer cannot fix drift in requirements docs — they would re-submit with the same drift, triggering CHANGES_REQUESTED again and potentially escalating to the user on cycle 2 without progress. **Mitigation**: reviewer prompt must explicitly state "requirements drift is an observation only; it does not influence the verdict."

### Morning report timing for interrupted sessions

If a session is interrupted after review.md is written but before the orchestrator processes the verdict, the feature remains in review phase. The morning report must surface drift findings for these features too, not just completed ones.

### `## Requirements Compliance` and `## Requirements Drift` overlap

Leaving both sections creates structural ambiguity for reviewers about where to put a finding. **Mitigation** (applied in recommended approach): remove `## Requirements Compliance` entirely and replace it with `## Requirements Drift`, defined to cover both directions.

---

## Open Questions

- **Verdict JSON extension vs. pre-event validation**: Should `"requirements_drift": "none"|"detected"` be added to the verdict JSON block (enforceable by state machine) or should the orchestrator validate the drift section exists before logging `review_verdict`? — **Resolved**: extend the verdict JSON. It reuses existing machine-parsed infrastructure, is additive (existing parsers that don't read the new field continue to work), and makes the enforcement explicit and auditable. Pre-event validation adds orchestrator complexity for the same enforcement benefit.

- **Area doc loading timing**: Area docs (`requirements/pipeline.md`, etc.) don't yet exist. Should the implementation include a `# TODO` comment noting that tag-to-doc mapping degrades gracefully to project.md-only, or should a stub tag-to-doc mapping be hardcoded from day one? — **Deferred**: the drift check against project.md alone is the minimum useful behavior; area doc support can be added later when area docs exist. Spec should note this as a known limitation.
