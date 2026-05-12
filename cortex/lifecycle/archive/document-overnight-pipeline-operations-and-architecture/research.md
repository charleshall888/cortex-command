# Research: Document overnight pipeline operations and architecture

Backlog ticket 073. Deliverable is `docs/overnight-operations.md` covering all 13 listed content gaps, plus relocation of architecture/debug content from `docs/overnight.md` into the new file. Tier: complex. Criticality: high.

## Codebase Analysis

### The 13 gaps — where they actually live

1. **Post-merge review** — `claude/pipeline/review_dispatch.py` (614 lines). Entry: `dispatch_review()`. Prompt: `claude/pipeline/prompts/review.md` via `_load_review_prompt()`. Called from `batch_runner.py:1690-1757`, gated by `requires_review(tier, criticality)` in `claude/common.py:245` — gating: `tier == "complex" or criticality in ("high", "critical")`. Verdict parsed from a ```` ```json ```` block in `review.md` via `parse_verdict()`. Rework cycle: CHANGES_REQUESTED cycle 1 → feedback appended to `lifecycle/{feature}/learnings/orchestrator-note.md` → HEAD SHA captured → fix agent dispatched → SHA circuit breaker → re-merge with `ci_check=False` → cycle 2 review. REJECTED or cycle-2 non-APPROVED → `_write_review_deferral()` writes a blocking `DeferralQuestion`. `batch_runner` owns all `events.log` writes (`phase_transition`, `review_verdict`, `feature_complete`); the review agent writes only `review.md`.

2. **Per-task agent capability constraints** — `claude/pipeline/dispatch.py:188`: `_ALLOWED_TOOLS = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]`. Enforced by omission — `Agent`, `Task`, `AskUserQuestion`, `WebFetch`, `WebSearch` are absent. No deny list. Passed as `allowed_tools=_ALLOWED_TOOLS` to `ClaudeAgentOptions` at line 434. Dispatch also clears `CLAUDECODE` env (line 401) so subprocess does not trip the nested-session guard. `claude/overnight/prompts/repair-agent.md:36` reinforces in prose.

3. **`claude/pipeline/prompts/` vs. `claude/overnight/prompts/`** —
   - *pipeline*: per-task/per-feature prompts dispatched into worktrees. Contains `implement.md`, `review.md`.
   - *overnight*: orchestrator/session-level prompts loaded by `runner.sh` and overnight subsystems. Contains `orchestrator-round.md`, `batch-brain.md`, `repair-agent.md`.

4. **Escalation system (`lifecycle/escalations.jsonl`)** — schema + writers in `claude/overnight/deferral.py:344-441`: `EscalationEntry` dataclass, `write_escalation()`, `_next_escalation_n()`. Records are JSONL with a `type` field: `"escalation"`, `"resolution"`, `"promoted"`. Each carries `escalation_id = {feature}-{round}-q{N}`, `feature`, `round`, `question`, `context`, `ts`. Writers: `write_escalation()` (re-exported via `claude/overnight/orchestrator_io.py`) and inline writes from `orchestrator-round.md` Step 0d. Readers: `orchestrator-round.md` Steps 0a–0d (cycle detection); `batch_runner.py:_next_escalation_n()` for q-numbering. `_next_escalation_n()` has an acknowledged TOCTOU race, safe under current per-feature single-coroutine dispatch.

5. **Strategy file (`overnight-strategy.json`)** — `claude/overnight/strategy.py` (103 lines). `OvernightStrategy` dataclass: `hot_files: list[str]`, `integration_health: "healthy"|"degraded"`, `recovery_log_summary: str`, `round_history_notes: list[str]`. `save_strategy()` is atomic (tempfile + os.replace). Written at end-of-round by orchestrator (per `orchestrator-round.md:212`) and on integration-recovery failure by `runner.sh:934`. Read by orchestrator prompt (Step 1a) and `batch_runner.py:712-721` for `hot_files` lookup in conflict-recovery decisions. Path: `{session_dir}/overnight-strategy.json`.

6. **Conflict recovery policy** — prompt at `claude/overnight/prompts/orchestrator-round.md:200-213` (declarative); code at `batch_runner.py:679-770` in `execute_feature()`. Decision: trivial-eligible iff `len(conflicted_files) <= 3 and not any(f in hot_files for f in conflicted_files)`. Trivial path: `resolve_trivial_conflict()` at `claude/pipeline/conflict.py:509`. Repair fallback: `dispatch_repair_agent` with `repair-agent.md`. Per-feature budget: `recovery_depth < 1`.

7. **Escalation cycle-breaking** — `orchestrator-round.md:87-103` (Step 0d). **Prompt-implemented, not Python.** If ≥1 `"type": "resolution"` entry exists for the same `feature` in `escalations.jsonl` and the worker re-asks, orchestrator deletes `lifecycle/{feature}/learnings/orchestrator-note.md`, appends `promoted` entry, writes a deferral via `write_deferral()`, and does not re-queue the feature.

8. **Test gate + integration health** — `runner.sh:908-959` runs `TEST_COMMAND` in `WORKTREE_PATH` after merges; on non-zero exit invokes `python3 -m cortex_command.overnight.integration_recovery`. Recovery module `claude/overnight/integration_recovery.py` (275 lines): flaky-guard re-run → HEAD SHA capture → `INTEGRATION_REPAIR_PROMPT_TEMPLATE` dispatched at complexity=complex → SHA circuit breaker → re-test. Events: `INTEGRATION_RECOVERY_START/SUCCESS/FAILED` from `events.py:66-68`. On recovery failure (`runner.sh:926`): sets `INTEGRATION_DEGRADED=true`, mutates `overnight-strategy.json` to `integration_health="degraded"`, and writes `INTEGRATION_WARNING_FILE` content prepended to PR body.

9. **`--tier` concurrency** — `batch_runner.py:2169-2173` (CLI), `--tier` (max_5 | max_100 | max_200), default None. Wired via `BatchConfig.throttle_tier` → `load_throttle_config()` → `ConcurrencyManager(throttle_config)`. Tier defaults in `claude/overnight/throttle.py:33-37`: MAX_5={runners:1,workers:1}, MAX_100={2,2}, MAX_200={3,3}. Default (None/unrecognized) = MAX_100. Adaptive: `report_rate_limit()` prunes a 300s sliding window; after 3 rate-limit events drops effective concurrency by 1 (min 1); `report_success()` restores after 10 consecutive successes.

10. **`brain.py` — post-retry triage** — `claude/overnight/brain.py` (268 lines). **Not a repair agent.** Entry: `request_brain_decision()` calls `dispatch_task` directly (NOT throttled — caller holds semaphore). `BrainAction` enum: `SKIP`, `DEFER`, `PAUSE`. No RETRY by design (runs post-retry-exhaustion). Prompt: `claude/overnight/prompts/batch-brain.md` (109 lines), rendered with `{feature, task_description, retry_count, learnings, spec_excerpt, has_dependents, last_attempt_output}`. `_parse_brain_response()` extracts JSON, validates `action ∈ {skip,defer,pause}` and `reasoning` required. DEFER additionally requires `question` and `severity`. Fallback `_default_decision()` returns PAUSE with confidence 0.3.

11. **`lifecycle.config.md`** — **no centralized Python loader**. Template at `skills/lifecycle/assets/lifecycle.config.md`; project copy at `lifecycle.config.md`. Runner does not parse — `test-command` is passed via CLI `--test-command` to `runner.sh`/`batch_runner.py`. Readers: skill prompts only (`skills/lifecycle/SKILL.md:29`, `references/specify.md:9`, `references/plan.md:12`, `references/complete.md:9-13`; `skills/critical-review/SKILL.md:21-22`; `skills/morning-review/references/walkthrough.md`). Absence behavior per consumer: morning-review skips Section 2a; lifecycle complete skips test step with note; critical-review omits `## Project Context`. Fields: `type`, `test-command`, `demo-command`/`demo-commands`, `default-tier`, `default-criticality`, `skip-specify`, `skip-review`, `commit-artifacts`.

12. **Env var fallback order (`runner.sh:42-87`)** —
    1. `ANTHROPIC_API_KEY` in env → use it (short-circuit).
    2. `apiKeyHelper` from `~/.claude/settings.json` or `settings.local.json` → execute, export stdout as `ANTHROPIC_API_KEY`.
    3. No helper AND no `CLAUDE_CODE_OAUTH_TOKEN` → try `~/.claude/personal-oauth-token`; if non-empty, export as `CLAUDE_CODE_OAUTH_TOKEN`.
    4. Fall back to keychain auth (warning printed).
    Propagation: `dispatch.py:401-405` re-exports both vars into SDK subprocesses. `CLAUDE_CODE_OAUTH_TOKEN` works only for `claude -p`/SDK; standalone tools need `ANTHROPIC_API_KEY`.

13. **`orchestrator_io`** — `claude/overnight/orchestrator_io.py` (17 lines, no logic). Re-exports `load_state`, `save_state`, `update_feature_status` from `claude.overnight.state`; `write_escalation` from `claude.overnight.deferral`. Consumed by `orchestrator-round.md:37`. Convention: any new orchestrator-callable I/O primitive is added here rather than imported directly from internal modules.

### Sections to move from `docs/overnight.md` → `docs/overnight-operations.md`

| Section | Lines | Disposition |
|---------|-------|-------------|
| Authentication | 98-156 | Move (operations) |
| Advanced / Operator Reference divider | 253-257 | Move (header only) |
| The Execution Phase — Architecture (ASCII flow) | 259-297 | Move |
| The Round Loop | 299-316 | Move |
| Circuit Breakers | 318-329 | Move |
| Signal Handling | 331-339 | Move |
| Module Reference | 341-362 | Move |
| State Files and Artifacts | 390-425 | Move |
| Best Practices → Conflict avoidance and resource protection | 470-503 | **Contested** — adversarial flagged; see Open Questions |
| Recovery: corrupt or inconsistent state | 524-565 | **Contested** — split: architecture explanation to ops doc, user-facing diagnosis stays |
| Recovery: merge conflict on integration branch | 567-585 | **Contested** — same split pattern |

Stays in `docs/overnight.md`: Quick-Start, Per-repo Overnight, Prerequisites, The Planning Phase, The Deferral System (user-facing table), The Morning Review, Command Reference, and other Best Practices (session size, prep, morning workflow, mid-session).

Cross-links that need updating: `overnight.md:15` jump-nav anchors; `overnight.md:263` SDK pointer; `overnight.md:297` and `overnight.md:444` pointers to Recovery/Advanced sections; `pipeline.md:9,13` link paths; `agentic-layer.md:~290` reference-docs list; `README.md:54` `lifecycle.config.md` pointer.

### Relevant existing patterns in `docs/`

- Breadcrumb `[← Back to ...](source.md)` at line 1 of every doc.
- Audience header: `**For:** ... **Assumes:** ...`.
- Jump-to blockquote nav: `> **Jump to:** ... | ... | ...`.
- Module/file inventory tables: `| Module | Role |` two-column.
- State schema docs: fenced ```` ```json ```` blocks.
- Recovery subsections: H3 with **Diagnosis** and **Recovery** bolded run-in heads.
- Cross-links: relative paths inside `docs/` (`[text](sdk.md)`); anchors `[text](file.md#slug)`.
- "Keeping This Document Current" footer (pipeline.md:170, agentic-layer.md:349).

### Conventions to follow

- ATX headings; H1 only at top. H1→H2→H3; avoid H4.
- Code fences: ` ```bash `, ` ```json `, ` ```python ` (no language for ASCII trees).
- Em-dashes (—), not `--`.
- `**Files**`, `**Inputs**`, `**Returns**`, `**Diagnosis:**`, `**Recovery:**` bolded run-in heads.
- Inline backticks for paths, filenames, function names, env vars, branch names.
- File paths in prose are project-root-relative; absolute only in code blocks.

## Web Research

### Prior art on runbook structure
- **Emmer — Incident Runbook Template**: 5-section per-symptom skeleton (Summary → Triage → Mitigate → Validate → Remediate). Emphasizes "actionable, accessible, accurate, authoritative, adaptable."
- **Skelton-Thatcher run-book template** — canonical ops-manual skeleton: system overview, runtime checks, procedures, dependencies.
- **Google SRE Workbook — On-Call**: every alert has a corresponding playbook entry; templates enforce completeness + quick scanning.
- **Alex Moss — Developer-Friendly Runbooks**: accessibility, independence, maintainability; use markdown+git so updates are frictionless; include log locations and verbosity options.
- **Braintree/runbook framework**: Books/Sections/Steps + Statements — useful nesting vocabulary.
- **ContainerSolutions/runbooks**: symptom → check → fix layout, one file per problem class.
- **AWS Prescriptive Guidance — Saga Orchestration**: document both the forward path and the compensating action per step.
- **Mindra — Multi-Agent Design Patterns**: blackboard pattern (structured shared document represents workflow state).
- **Agent Patterns — Allowlist vs Blocklist**: document each allow with a *reason*; reviewed periodically.

### Documentation shape takeaways
- **State machines + file state**: per transition, document *trigger + guard + action + on-failure compensator*. Name the on-disk artifact per state.
- **"Debug a stuck feature" docs**: symptom-first indexing (reader arrives with a symptom → likely state → check → action).
- **Tool-allowlist docs**: document by *intent/reason* plus review cadence; centralize source-of-truth; avoid wildcards. (See Adversarial — this recommendation has a caveat for enforce-by-omission policies.)
- **Cron/round orchestrators**: make the *checkpoint artifact* a first-class documented object (what it contains, how to read, how to edit manually, what "clean" vs. "mid-flight" vs. "poisoned" look like).

### Anti-patterns from the web
- Pasting commands without mental-model scaffolding.
- Line numbers that rot on every refactor.
- Wildcard allowlists documented as-is (become default-allow silently).
- Staleness is P1 — a single inaccuracy destroys trust in all procedures.
- Runbook-as-substitute-for-automation — long procedures signal missing code.

### Recommendation from web agent
**Emmer 5-section skeleton applied per-symptom at the debugging layer, nested inside a Skelton-Thatcher-style operations manual at the top.** Three parts: (1) Mental model/architecture as state-machine transition tables, (2) Tuning reference as tables-with-reasons, (3) Observability & debugging as symptom-first Emmer procedures.

## Requirements & Constraints

### Must be documented accurately (exact-phrase constraints)
- Forward-only phase transitions: `planning → executing → complete`; any phase → `paused` (pipeline.md:19).
- Atomic state writes: tempfile + `os.replace()` (pipeline.md:21).
- Integration branches persist after completion — not auto-deleted (pipeline.md:22, 133).
- Artifact commits travel on the integration branch, not local main (pipeline.md:23).
- Morning report commit is the only runner commit that stays on local main (pipeline.md:24).
- State file reads are not lock-protected by design; forward-only transitions make this safe — permanent architectural constraint (pipeline.md:131).
- Repair attempt cap: max 2 attempts for test failures (Sonnet + Opus); single Sonnet→Opus escalation for merge conflicts — fixed architectural constraint (pipeline.md:132). **Two different codepaths, two different numbers — do not unify.**
- Dashboard binds `0.0.0.0`, unauthenticated, by design (pipeline.md:134, observability.md:91).
- Dashboard is read-only (observability.md:92).
- Orchestrator owns parallelism — agents never spawn peer agents (multi-agent.md:72).
- Tier concurrency limit 1-3 is hard, not runtime-overridable by agents (multi-agent.md:73).
- Escalation ladder haiku → sonnet → opus, no downgrade (multi-agent.md:75).
- `--dangerously-skip-permissions` makes sandbox config the critical security surface (project.md:32).
- PR `--merge` strategy is load-bearing for `--theirs` rebase semantics (pipeline.md:118).
- `pipeline-events.log` is append-only JSONL (pipeline.md:126).
- Orchestrator `rationale` field convention exists but enforcement requires prompt changes (pipeline.md:127).

### Scope boundaries the doc must respect
- **Out of scope (do NOT document as current)**: dotfiles/machine config; application code in other repos; published packages; setup automation for new machines.
- **Deferred (do NOT document as current)**: migration from file-based state; cross-repo work in one overnight session (cross-repo *worktree placement* exists, but orchestrating cross-repo *work* is deferred).
- **`should-have`, not `must-have`** — do not frame as load-bearing: sandbox socket access (observability.md:79); some metrics behavior; remote reattachment; mobile push alerting.

### Gaps to acknowledge (not paper over)
- `remote/SETUP.md` is referenced but missing (remote-access.md:80).
- Notification/session failures are silent; no log mechanism exists (remote-access.md:52).
- Orchestrator `rationale` field: convention documented, enforcement requires prompt changes (pipeline.md:127).

### Documentation-shape conventions observed in `requirements/`
- "Last gathered" date header.
- Priority labels (must-have / should-have).
- Section ordering: overview → functional requirements → non-functional → architectural constraints → dependencies → edge cases → open questions.

## Tradeoffs & Alternatives

### Structural alternatives
- **A — Single monolithic `docs/overnight-operations.md`**. Pros: one URL, Cmd-F works across the whole doc, matches `overnight.md` one-long-doc pattern, simplest to keep in sync. Cons: 13+ gaps + Architecture/Tuning/Observability → likely 1500+ lines; scroll fatigue; hard to diff section-by-section.
- **B — Three linked docs** (`overnight-architecture.md`, `overnight-tuning.md`, `overnight-observability.md`). Pros: 1:1 map to ticket's three sections; smaller, more focused files; jump-to-one-doc-by-symptom. Cons: three files to keep in sync; cross-refs between them will rot; bucks repo convention (one-doc-per-subject); relies on a `docs/` index that doesn't exist today.
- **C — One primary doc + small appendices** (appendices for orchestrator_io API reference, config schema reference). Pros: narrative main stays readable; deep reference has a home; preserves one-primary-doc convention. Cons: judgment call on what belongs where; appendices are the most code-proximate content (highest rot risk). **Tradeoffs agent's recommendation — but Adversarial flags appendix rot (see mitigation).**
- **D — Merge into existing `docs/pipeline.md`**. Pros: consolidation; pipeline.md already contains similar reference material. Cons: conflates pipeline (per-feature) with overnight (multi-feature orchestration); contradicts the ticket's explicit call to relocate *out of* overnight.md *into* a new file; high blast radius for existing cross-links.

### Content-depth alternatives
- **X — Narrative-first**: mental-model-per-subsystem prose, code pointers after. Pros: builds intuition fast; survives small refactors; context-friendly for agents. Cons: slower for reference lookup; prose drifts silently.
- **Y — Reference-first**: table/schema per subsystem with exact names and pointers. Pros: fast lookup at 2am; validatable (a script can assert doc rows equal code constants). Cons: loses "why"; reverse-engineering intent from tables.

### Cross-link strategy alternatives
- **P — Direct code refs (`file.py:123`)**. Pros: precise. Cons: line numbers rot on every refactor; inconsistent with existing docs which use filenames + function names only.
- **Q — Concept/heading refs only (no line numbers)**. Pros: maximally stable. Cons: readers must grep.
- **R — Hybrid** (filenames inline + "state at commit {SHA}" footer with line numbers). Pros: best of both. Cons: SHA footer is aspirational — rots unless actively refreshed.

### Recommended approach

**Structure C (single primary doc + targeted appendices as pointers) + blended depth (brief Mental Model narrative preamble per subsystem, then reference-first tables) + cross-links Q (filenames + function names, no line numbers or prompt line numbers). Appendices are pointers with invariants, NOT enumerations (see Open Questions — appendix rot).**

Rationale: Respects repo convention (one primary doc per subject with anchored jump-nav), matches project philosophy of maintainability through simplicity. Reference-first is faster than narrative-first at 2am for both Architecture and Observability (see Adversarial point 8). Module+function-name cross-links match existing `overnight.md` and `pipeline.md` patterns, avoiding line-number rot.

## Adversarial Review

### Failure modes and edge cases
- **Appendix rot on `orchestrator_io` and `lifecycle.config.md`**: any appendix that enumerates symbols/fields becomes stale the moment a symbol is added. `orchestrator_io.py` is 17 lines today and will grow. `lifecycle.config.md` already has 6+ consumers with no centralized loader; an appendix becomes a 7th. *Mitigation*: replace enumerations with pointers + invariants (e.g., "fields are whatever is in `skills/lifecycle/assets/lifecycle.config.md` — template is source of truth"); only write a table if a `just`/pytest check can diff against the source.

- **Extraction miscategorizations**: "Conflict avoidance and resource protection" (overnight.md:470-503) is a *planning/Best-Practices* concern (what to batch together), not a debugging concern — moving it to operations leaves a hole in user-facing overnight.md. "Recovery: corrupt or inconsistent state" (524-565) enumerates three causes of `running`, two of which are architectural (round-end, orchestrator-interrupted) and one of which is user-facing (crash/SIGKILL) — splitting loses the enumeration; merging forces user to bounce to operations doc at the worst moment. *Mitigation*: keep user-facing Recovery procedures in `overnight.md`; move only the *architectural explanation of why these three states exist* into operations. Emmer pattern: symptom (in user doc) → remediation pointer → architectural context (in operations doc).

- **"Document tool allowlist by intent" fails here**: the `_ALLOWED_TOOLS` list in `dispatch.py:188` is enforced by *omission*, not by a named policy. If a future edit adds `WebFetch` to the list, intent-prose ("file-editing and shell tools") silently still covers the change and a security auditor can't tell. *Mitigation*: document the list **literally**, note "if this diverges from `dispatch.py`, code wins," and add a pytest asserting the doc snippet equals `dispatch._ALLOWED_TOOLS` as a set.

- **Brittle claims that will go stale as misleading-at-2am**:
  - "brain.py has no RETRY by design" (true today, hazardous if RETRY is added).
  - "Repair cap: single Sonnet→Opus for conflicts; max 2 attempts for test failures" (two different codepaths — `conflict.py` vs. `merge_recovery.py`; narrative will tempt unification).
  - "Zero-progress circuit breaker fires after 2 consecutive rounds" (will go stale if made configurable).
  - Any reference to "orchestrator-round.md lines 87-103" — prompts are edited for clarity routinely.
  *Mitigation*: replace numeric claims with pointer + *why* the number is what it is (the "why" outlives the number). Never quote prompt line numbers; use prompt filenames + section headings only.

- **Gaps the 13-gap list itself misses** (docs audit was pipeline-flavored): dashboard's state-file reads and poll-vs-atomic-replace behavior; `agent-activity.jsonl` schema; `.runner.lock` PID mechanics and stale-lock recovery; SessionEnd/SessionStart and notification hooks (silent failure mode); morning-report generation logic (`report.py` is 1555 lines); scheduled-launch subsystem; `interrupt.py` startup-recovery semantics; relationship between `events.log`, `pipeline-events.log`, `agent-activity.jsonl` (which to grep for which symptom).

- **Cross-doc conflict with `pipeline.md`**: `pipeline.md` already documents `merge_recovery.py` and post-merge review mechanics. Two true-but-differently-framed descriptions WILL drift. *Mitigation*: establish a **source-of-truth rule**: operations doc owns the round loop and orchestrator behavior; `pipeline.md` owns pipeline-module internals; `sdk.md` owns SDK mechanics. No behavioral claims about pipeline modules in operations doc — only pointers. Write the rule into `CLAUDE.md`.

- **`docs/sdk.md` already owns model-selection matrix**: both `overnight.md:263` and `pipeline.md:13` already delegate SDK-specific content to `sdk.md`. Documenting model selection in operations doc risks a three-way source-of-truth conflict. *Mitigation*: operations doc covers tier × criticality → role dispatch; detailed SDK model configuration stays in `sdk.md`; operations links across.

### Security concerns / anti-patterns
- **`--dangerously-skip-permissions` and `0.0.0.0` framing**: narrative prose softens these routinely. *Mitigation*: dedicated "Security and Trust Boundaries" section (not scattered), each boundary enumerated once with a single-sentence threat model. Follow `dashboard.md:131` precision ("Do not expose"; clarify `127.0.0.1` probe is unrelated).
- **Allowlist ≠ permission model**: readers will conflate `_ALLOWED_TOOLS` with `--dangerously-skip-permissions`. They are orthogonal: the former is an SDK-level tool bound; the latter disables Claude Code's permission prompts entirely.
- **"Local network" ≠ "home network"**: a reader checking the dashboard from hotel Wi-Fi is on a shared network — the doc must state this explicitly.
- **Keychain prompt blocking subprocess spawn**: the "runs while you sleep" premise breaks if a macOS keychain prompt fires mid-session. Document as a failure mode.

### Assumptions that may not hold
- That the 13-gap list is complete (audit was pipeline-flavored — see missed gaps above).
- That the tradeoffs-agent's "narrative for Architecture, reference for Observability" is right — Adversarial argues reference-first for both (operators at 2am want symptom → answer in both sections).
- That `retros/` contains no additional debug pain-points worth mining. Five recent lifecycle retros exist — grep for "2am," "couldn't find," "unclear," "surprising" before finalizing scope.

### Recommended mitigations (full list)
1. Appendices: pointers + `__all__`/template-diff invariants, not enumerations.
2. Keep user-facing Recovery in `overnight.md`; move only *architectural explanation* to operations.
3. Document tool allowlist literally; back with a pytest.
4. Ban prompt line numbers; replace numeric claims with pointer + rationale.
5. Expand gap list before writing — include dashboard, hooks, locks, logs, morning-report generation, `report.py`.
6. Establish single-source-of-truth rule in `CLAUDE.md`: operations owns round loop; pipeline.md owns pipeline internals; sdk.md owns SDK mechanics.
7. Dedicated "Security and Trust Boundaries" section.
8. Disambiguation-first prose for `brain.py` and any other hazardously-named component.
9. Mine `retros/` for overnight debugging pain-points before finalizing scope.
10. Reference-first format for both Architecture and Observability; short narrative only as Mental Model preamble per subsystem.

## Open Questions

Deferred to the Specify phase — these are design/preference questions best resolved with the user during the structured interview, not by further investigation.

- **Gap-list expansion**: adversarial surfaced ~8 additional gaps the audit missed (dashboard polling semantics, `agent-activity.jsonl`, `.runner.lock`, hooks, morning-report generation, scheduled-launch, `interrupt.py`, log-file disambiguation). Deferred: which of these expand the doc vs. deliberately stay out-of-scope.
- **Extraction split for contested sections** (`overnight.md` lines 470-503 "Conflict avoidance"; 524-565 "Recovery: corrupt state"; 567-585 "Recovery: merge conflict"): full-move vs. adversarial-recommended symptom-stays/architecture-moves split. Deferred: which split pattern the doc adopts.
- **Source-of-truth rule in `CLAUDE.md`**: adversarial recommended codifying the operations/pipeline/sdk doc ownership boundary. Deferred: whether this ticket's scope includes a `CLAUDE.md` edit, or if that is a separate backlog item.
- **Literal tool-allowlist + pytest check**: adversarial recommended a pytest asserting doc-snippet equals `dispatch._ALLOWED_TOOLS`. Deferred: whether this ticket's scope includes the pytest, or docs-only.
- **Appendix structure**: tradeoffs agent recommended appendices; adversarial recommended pointers-plus-invariants instead. Deferred: concrete appendix list and invariant mechanism for each.
- **`retros/` mining**: adversarial recommended greppping retros for 2am pain-points. Deferred: whether this is a scope-expanding input or a style check.
- **`docs/pipeline.md` disposition**: retain as-is with cross-links, trim duplicated recovery content, or deprecate in favor of operations doc. Deferred: refactor scope.
