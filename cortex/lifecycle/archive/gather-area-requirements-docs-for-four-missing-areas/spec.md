# Specification: Gather area requirements docs for four missing areas

## Problem Statement

Four areas — observability, remote-access, multi-agent, and pipeline — have substantial codebase footprints but no requirements docs. Without them, agents working in these areas must reverse-engineer intent from implementation, risking drift between what was built and what should be built. This ticket executes the requirements gathering identified in the audit (ticket 011): gather all four area docs in a live session, producing four area docs that give lifecycle, discovery, and review agents a structured starting point.

## Requirements

1. **Execution flow**: The session runs in four sequential phases:
   - **Phase 1 — Parallel reconnaissance**: All four areas run codebase analysis simultaneously. No docs are written yet.
   - **Phase 2 — Consolidated Q&A**: Aggregate all questions from all four areas into one round (≤8 questions total). The user answers once. No per-area approval gates at this stage.
   - **Phase 3 — Write all four docs**: Write all four area docs based on codebase findings + Q&A answers.
   - **Phase 4 — Per-area approval and commit**: Present all four drafts. Approve each area independently. Commit all approved docs via `/commit`.

2. **Area doc format**: Each doc follows the `gather.md` template — Overview, Functional Requirements (with description / acceptance criteria / priority per capability), Non-Functional Requirements, Architectural Constraints, Dependencies, Edge Cases, Open Questions. Parent backlink to `requirements/project.md` required. No "when to load" guidance inside area docs.

3. **Observability doc structure**: Three functional requirement sections — Statusline, Dashboard, Notifications. One `requirements/observability.md` file (not split by subsystem).

4. **Pipeline doc derivation**: 
   - *Authorized input*: `docs/pipeline.md` AND the pipeline/overnight source files (state.py, conflict.py, merge_recovery.py, deferral.py, metrics.py, batch_runner.py).
   - *Derive means*: read all authorized sources, draft requirements from what is determinable (translate implementation descriptions into requirements language), then formulate questions only for gaps that require user judgment.
   - *Bounded Q&A categories for pipeline* (ask only within these categories, not open-ended discovery): (a) which current limitations are permanent constraints vs. temporary shortcuts; (b) intended evolution direction for specific subsystems; (c) any requirements implied by the source files that contradict or extend docs/pipeline.md.
   - The dashboard's no-authentication and localhost-only properties are **permanent architectural constraints** — do not ask about them.

5. **Remote-access doc scoping**: Write `requirements/remote-access.md` at the **capability level** — session persistence, remote mobile alerting, remote session reattachment — not tied to any specific implementation tool. The tmux skill's long-term place in the architecture is under review; the requirements doc must not encode it as a permanent requirement.

6. **No project.md updates needed**: The `## Conditional Loading` section already references all four file paths correctly. After area docs are created, no updates to `requirements/project.md` are required.

## Non-Requirements

- Not rebuilding or modifying any of the systems being documented
- Not creating `requirements/project.md` (done in ticket 011)
- Not adding "when to load" triggers inside area docs
- Not fixing the broken `remote/SETUP.md` reference in `docs/setup.md` (separate ticket)
- Not deciding whether to keep or remove the tmux skill
- Not converting `docs/pipeline.md` into a requirements doc — area doc is a new file; `docs/pipeline.md` remains as-is

## Edge Cases

- **Q&A follow-ups**: If a user's answer generates a new question, the agent may ask up to 2 targeted follow-up questions per area before proceeding with the best available information. Remaining gaps are noted in the doc's Open Questions section.
- **Per-area revision**: If a draft doc needs significant revision at approval time, only that area re-runs (surgical rework, not all four).
- **project.md contradictions**: If gathering reveals information that contradicts `requirements/project.md`, note it as an open question in the area doc — do not silently update project.md.
- **Cross-area contradictions**: If parallel gathering produces conflicting answers across areas (e.g., a constraint in multi-agent that pipeline doesn't honor), surface the contradiction explicitly in the relevant area doc's Open Questions section.

## Technical Constraints

- Files: `requirements/observability.md`, `requirements/remote-access.md`, `requirements/multi-agent.md`, `requirements/pipeline.md` — lowercase-kebab-case, plain markdown
- No CLAUDE.md operational content duplication; reference it instead
- No inline code style guides in any area doc
- **"Self-contained" definition**: A doc is self-contained if it contains no open questions that block an agent from starting implementation work in this area today. Open questions about future evolution (e.g., whether to keep or remove the tmux skill) are acceptable as long as they don't prevent the agent from knowing what to build given the current system. The remote-access doc written at capability level satisfies this — tmux uncertainty does not block describing current capabilities.
- Commit via `/commit` skill only

## Open Decisions

- Whether to keep, simplify, or remove the tmux skill — does not block this ticket; the remote-access doc is written at capability level regardless of outcome.
