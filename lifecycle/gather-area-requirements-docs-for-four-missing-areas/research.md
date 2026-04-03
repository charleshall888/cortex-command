# Research: Gather area requirements docs for four missing areas

## Epic Reference

Epic research: `research/requirements-audit/research.md` — covers the full requirements audit that identified these four areas as missing, validated the hybrid project.md format, and produced decision records on parent doc structure, "when to load" conventions, and maintenance cadence. Ticket 012 is the execution arm: apply the audit's conclusions by running `/requirements` for each of the four areas.

---

## Codebase Analysis

### Files to create

- `requirements/observability.md` — new
- `requirements/remote-access.md` — new
- `requirements/multi-agent.md` — new
- `requirements/pipeline.md` — new

### Files already correct (no changes needed)

- `requirements/project.md` — already has `## Conditional Loading` with correct trigger phrases pointing to all four files; no updates required after area docs are created.

### Area doc format (from `skills/requirements/references/gather.md`)

```markdown
# Requirements: {area-name}

> Last gathered: {date}

**Parent doc**: [requirements/project.md](project.md)

## Overview
## Functional Requirements
### {Capability}
- Description / Inputs / Outputs / Acceptance criteria / Priority
## Non-Functional Requirements
## Architectural Constraints
## Dependencies
## Edge Cases
## Open Questions
```

Target length: 60–120 lines. Area docs do not include "when to load" triggers — those belong in project.md only.

### Code locations per area

**Observability:**
- `claude/statusline.sh` — bash, 644 LOC, v1.4.0; 3 output modes; color handling uses basic 16-color to avoid ANSI byte overhead
- `claude/dashboard/` — 12-file FastAPI + Jinja2 (~1800 LOC); `app.py`, `data.py`, `poller.py`, `alerts.py`, 9 HTML templates
- `hooks/cortex-notify-remote.sh` — ntfy.sh HTTP API; suppresses subagent sessions (checks `agent_id`); exits silently if `NTFY_TOPIC` or `TMUX` unset

**Remote access:**
- `skills/tmux/SKILL.md` — session creation, auto-numbered naming, `claude --resume`, Ghostty window creation
- `hooks/cortex-notify-remote.sh` — Android push via ntfy.sh; requires Tailscale mesh
- `docs/setup.md` references non-existent `remote/SETUP.md` — broken reference ticket 012 resolves by creating the area doc

**Multi-agent:**
- `claude/pipeline/worktree.py` — worktree isolation; branches named `pipeline/{feature}`; cleanup post-merge
- `claude/pipeline/dispatch.py` — MODEL_ESCALATION_LADDER (Haiku → Sonnet → Opus); ERROR_RECOVERY table; task complexity × phase × criticality matrix
- `claude/reference/parallel-agents.md` — pattern for 3+ independent tasks

**Pipeline:**
- `claude/overnight/batch_runner.py` — main overnight orchestrator
- `claude/overnight/state.py` — OvernightState/OvernightFeatureStatus; phases: planning → executing → complete; states: pending/running/merged/paused/failed/deferred
- `claude/pipeline/conflict.py` — conflict classification and repair-agent dispatch
- `claude/pipeline/merge_recovery.py` — post-merge test failure recovery; model escalation (Sonnet → Opus)
- `claude/overnight/deferral.py` — writes open questions for human triage; tracks question ID, feature, timestamp, rationale
- `claude/pipeline/metrics.py` — parses `lifecycle/*/events.log`; cost, timing, phase durations
- `claude/overnight/smoke_test.py` — post-merge verification gate
- `docs/pipeline.md` — implementation reference (176 lines); source material for pipeline area doc derivation

---

## Web Research

### Machine-readable requirements best practices

- **Stable prefix + dynamic content + attention anchors**: Structure documents in three zones — stable project metadata (never changes between sessions, enables KV-cache), dynamic requirements with acceptance criteria, and attention anchors (restate executive summary at both top and bottom to counteract "lost-in-the-middle" failure mode).
- **Under 300 lines** for any always-loaded document; area docs (loaded on demand) can be up to ~120 lines without degrading agent effectiveness. Monolithic context is an anti-pattern.
- **Lead with executable information**: exact file paths, verifiable criteria, runnable commands. Narrative prose should be minimal.
- **`file:line` references over inline code blocks**: code blocks go stale; file references stay fresh. (Relevant: area docs should reference source file paths, not embed code.)
- **Timing beats completeness**: context injected at the moment an agent opens a file produces better results than a perfect document loaded at session start and then compacted away.

### Area-level organization patterns

- **`agent_docs/` progressive disclosure** (HumanLayer): main context file lists area docs with brief descriptions; agent decides which are relevant and fetches them. Mirrors requirements/project.md → requirements/area.md pattern.
- **Subdirectory CLAUDE.md loading** (Claude Code): loads on demand when working in that directory — the closest analogue to area-level requirements.
- **Recommended sections** for agentic context: primary objectives, decision-making frameworks, available tools + data access, safety constraints, error/recovery procedures, escalation protocols.

### Observability documentation patterns

- Organize around **four golden signals**: request rate, error rate, latency (p95/p99), saturation. For each signal: calculation method, normal baselines, alert thresholds.
- "**One page = one decision**": if a dashboard can't answer a single on-call question quickly, the requirements are under-specified.
- For developer-facing statuslines: surface health summaries before drill-down; specify which state each zone displays and under what conditions it changes.
- For push notifications: document trigger events, delivery latency SLOs, fallback behavior on failure, and session reattachment protocol.

### Multi-agent requirements patterns

- **Parallel dispatch go/no-go criteria** (Claude Code): all three must be met — (1) 3+ unrelated tasks, (2) no shared state, (3) clear file boundaries.
- **Worktree lifecycle requirements**: create, destroy, branch naming, merge gate, conflict resolution ownership.
- **Model selection matrix**: route planning to cheaper models, implementation to premium models, review to security-focused variants. Requirements doc should include explicit routing table by task type and criticality.
- Orchestration patterns to document: sequential (linear dependencies), concurrent (fan-out/fan-in), handoff (context transfer protocol).

---

## Requirements & Constraints

### From `requirements/project.md`

- Conditional Loading section already references all four area doc paths — no post-creation updates needed.
- **File-based state only**: area docs must not recommend database or server solutions.
- **Graceful partial failure**: pipeline requirements must preserve the "retry and fail gracefully while completing the rest" invariant.
- **Simplicity constraint**: complex solutions must earn their place; requirements docs should not encode implementation preferences.

### From `skills/requirements/SKILL.md` and `references/gather.md`

- Area docs include a parent backlink to `requirements/project.md`. No "when to load" guidance inside the area doc.
- Interview protocol: mine code first (what's already decided), then ask about intent, unwritten rules, and planned changes — not re-state visible capabilities.
- Content principle: capture WHAT and architectural constraints, not HOW. `os.replace()` is HOW; "state writes must never corrupt on power loss" is WHAT.
- Area docs must not duplicate operational content from CLAUDE.md; reference it instead.

### From `docs/pipeline.md` (pipeline derivation source)

- State transitions are forward-only: planning → executing → merging → integration-review → complete.
- Feature statuses: pending, executing, reviewing, merging, merged, paused, failed.
- Writes are atomic (tempfile + `os.replace()`).
- Integration branch naming: `overnight/{session_id}`; feature branches: `pipeline/{feature}`.
- Dashboard has explicit known limitations section (no authentication, localhost-only): should be captured as **architectural constraints**, not requirements — they represent intentional scope decisions.

---

## Tradeoffs & Alternatives

### Sequential vs. parallel gathering

**Sequential** (one area at a time): zero collision risk, maximum context focus per area, but 60–120 minutes total and misses cross-area dependency discovery.

**Full parallel** (all 4 simultaneously): fastest time-to-delivery, surfaces cross-area dependencies naturally. Collision risk is low with distinct draft filenames during gathering. ✓ *User-preferred approach.*

**Hybrid batch** (observability + multi-agent first, then pipeline + remote-access): balanced but adds a phase boundary with no strong justification given the areas are largely independent for the gathering step itself.

**Recommended**: parallel dispatch for all four, with targeted Q&A for gaps. Each agent writes to `requirements/{area}.md` directly (areas have distinct paths; no collision). Per-area approval is independent (rework is surgical).

### Pipeline doc: fresh interview vs. derive-from-existing vs. hybrid

**Fresh interview**: captures intent and evolution but re-derives what `docs/pipeline.md` already documents — redundant for a stable, implementation-complete reference.

**Pure derivation**: fast but risks encoding implementation-oriented "how" constraints as requirements and missing strategic intent (evolution plans, known limitations intended to change).

**Hybrid (derive + focused validation interview)**: extract structural requirements from `docs/pipeline.md` (module roles, state schema, recovery patterns), then run a focused 10–15 minute interview targeting evolution intent and undocumented constraints. ✓ *User-preferred approach.* Key interview questions: "What about this will change?", "Which limitations in docs/pipeline.md are intentional constraints vs. shortcuts?", "What does pipeline guarantee under failure?"

### Single observability doc vs. split by subsystem

**Single `requirements/observability.md`**: statusline, dashboard, and notifications are architecturally coupled (all monitor session state; dashboard depends on statusline data sources; notifications integrate with both). One doc keeps cross-subsystem constraints coherent and the project.md trigger table concise. ✓ *Recommended.*

**Three separate docs**: cleaner per-subsystem scope but adds coordination overhead for cross-subsystem constraints and lengthens the project.md Conditional Loading table.

### Single agent vs. sub-agents per area for pipeline

**Single agent**: pipeline modules are tightly coupled (state consumed by dispatch, merge, retry; all feed metrics). One agent holds cross-module context; avoids sub-agent sync. Trade a potentially longer interview (20–30 min) for coherence. ✓ *Recommended.*

**Multi-agent per component**: cleaner per-component focus but requires cross-agent interface coordination and risks inconsistent cross-cutting constraints.

---

## Open Questions

- `docs/pipeline.md` has a "limitations" section (dashboard has no authentication, localhost-only). Are these permanent architectural constraints to enshrine in requirements, or temporary shortcuts expected to change? *Deferred: will be resolved in Spec by asking the user.*
- The tmux skill creates sessions via Ghostty (`open -na Ghostty --args`) which is macOS-specific. Is Windows/Linux support for remote access in scope for `requirements/remote-access.md`, or macOS-only? *Deferred: will be resolved in Spec by asking the user.*
