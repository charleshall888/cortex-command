# Research: Extract Scripts From Agent Tool-Call Sequences

## Topic

Identify places in the agentic harness (skills, hooks, pipeline prompts, lifecycle flows) where the Claude agent executes sequences of deterministic tool calls that could collapse into a single agent-invokable script. Goal: save tokens, reduce wall-clock latency, and increase determinism where the logic has no model judgment between steps.

> **Revision history**:
> - **Round 1**: inventoried C1–C10 across skills / hooks / pipeline prompts.
> - **Critical review 1**: flagged classification looseness, savings inflation, 3-way phase-detection triad. Applied.
> - **Round 2**: deepened on quantification, linter spec, C2+C3 semantic diff, C5 ambiguity sample, missed-candidate sweep (added C11–C15).
> - **Critical review 2**: found that (a) a *fourth* phase-detection implementation lives in `claude/statusline.sh` that can't subprocess to Python; (b) drift is not just hypothetical — commit `5026ee7` deleted `skills/backlog/generate-index.sh` and rewired callers; (c) PR-level enforcement barely exists in this repo (3 PRs ever); (d) runtime-adoption signal is missing and a third failure mode (written-but-unused at runtime) is not addressed; (e) C5's bailout design makes its ship-gate telemetry non-load-bearing. Applied below.

## Research Questions

1. **Inventory.** Where does the agent execute ≥3 deterministic tool calls in sequence? → **Answered.** 15 viable candidates (C1–C15). See §Codebase Analysis.

2. **Determinism axis.** → **Answered, with narrowed sub-range scoping.** C1, C4, C5 are "mechanical parse + judgment downstream."

3. **Cost.** Per-invocation token and latency? → **Partially answered.**
   - **C8 (pipeline-observable)**: ~500–800 tokens saved + ~1 turn per round.
   - **C1 (/commit)**: ~1 turn saved per commit (3 parallel → 1 serial).
   - **C4, C7, C11, C13, C15**: no telemetry. Per-invocation ~0.3–1 turn. Ranked by frequency-heuristic.
   - **Gap**: skill name not logged on `dispatch_start` (addressed by ticket 109, but see Q5 — this only helps pipeline).

4. **Existing scripts as models — adoption failure root cause.** → **Mixed picture, not a clean "day-one only" story.**
   - **Day-one wiring failures** (caught by static lint): `bin/validate-spec`, `bin/count-tokens`, `bin/audit-doc` — never referenced by any SKILL.md.
   - **Hidden behind module abstraction** (not linter-catchable without heuristic): `create-backlog-item`, `update-item` — wired through Python module invocation, not direct CLI reference. Static linter scanning for `bin/foo` or bare `foo` misses these.
   - **Confirmed drift in this repo**: commit `5026ee7` (Apr 7 2026) deleted `skills/backlog/generate-index.sh` (238-line shell); follow-up `8ba65c3` rewired `skills/discovery/references/decompose.md`. Script-reference *replacement* has happened — small example, but evidence that drift is real.
   - **Sample caveat**: N=5 scripts across a 7-day window is not a basis for generalizing. Day-one failures dominate the known sample; drift and module-abstraction substitution are additional failure modes.

5. **Discoverability & runtime adoption.** → **Three failure modes, not one.**
   - (a) Day-one missing reference (static-lint catchable).
   - (b) Drift (reference removed/replaced over time — static lint on every commit mitigates if the linter actually runs on that commit; see DR-5).
   - (c) **Written-but-unused at runtime**: SKILL.md references the script but the surrounding prose makes the agent prefer Read+Grep / Bash / a Python module. Static lint cannot catch this. No runtime signal exists for interactive sessions. See DR-7.

6. **Transparency trade-off.** → **Answered.** Collapsing is safe when (a) output is inspected as a unit, (b) exit codes preserve branching, (c) downstream work doesn't re-read the collapsed data.

7. **Ranked candidates.** → **Answered** in §Feasibility Assessment.

## Codebase Analysis

### Candidate Inventory

Heat: hot = every session; warm = per-phase; cool = occasional. **Turns** = serial-equivalent turns in extractable region.

| # | Candidate | Heat | Turns | Class | Location | Extractable scope |
|---|-----------|------|-------|-------|----------|-------------------|
| C1 | `/commit` preflight | Hot | 1 (3 parallel) | MECHANICAL-PARSE + judgment downstream | `skills/commit/SKILL.md:12-14` | Preflight reads only. |
| C2+C3 | Lifecycle phase detection across hook + skill + `claude.common` + **`claude/statusline.sh`** (4 implementations, not 3) | Hot | 4–7 per caller | MECHANICAL-CORE + inter-component contract | See below | Promote `claude.common` for hook + skill. Statusline stays bash. See DR-6 revision. |
| C4 | `/dev` epic-map parse | Warm | 4-5 | MECHANICAL-PARSE, judgment downstream | `skills/dev/SKILL.md:135-166` | Parent-normalization + dedup. |
| C5 | `/refine` Step 1 resolution | Warm | 3-4 | MECHANICAL-PARSE on happy path | `skills/refine/SKILL.md:22-35` | Ship with bailout exit code — Pareto improvement regardless of ambiguity rate. See Feasibility. |
| C6 | Lifecycle daytime polling loop | Warm | ~3 × N iter | MECHANICAL | `skills/lifecycle/references/implement.md:144-155` | Blocked on ticket #94. |
| C7 | `/backlog pick` index→filter→table | Warm | 3-4 | JUDGMENT-AT-ENDPOINTS | `skills/backlog/SKILL.md:82-94` | Filter + sort + render. |
| C8 | Orchestrator-round state read | Warm | 6-8 | MECHANICAL | `claude/overnight/prompts/orchestrator-round.md:22-176` | Data-rankable today. |
| C9 | Plan-gen dispatch + result collection | Cool | ~8 | JUDGMENT-AT-ENDPOINTS | `claude/overnight/prompts/orchestrator-round.md:237-294` | Revisit after 109 data. |
| C10 | Merge-conflict classify + dispatch | Cool | ~8 | JUDGMENT-INTERLEAVED | `claude/overnight/feature_executor.py` | Out of scope. |
| C11 | Morning-review session completion + state update | Warm | 4 | MECHANICAL | `skills/morning-review/SKILL.md:23-48` | |
| C12 | Morning-review stale worktree GC | Cool | 4+ | MECHANICAL | `skills/morning-review/SKILL.md:50-75` | |
| C13 | Morning-review backlog-closure loop | Warm | 3 × N (parallelizable) | MECHANICAL | `skills/morning-review/SKILL.md:109-128` | |
| C14 | Morning-review git preflight sync | Warm | 3 serial | MECHANICAL | `skills/morning-review/SKILL.md:132-138` | Fold into `git-sync-rebase.sh`. |
| C15 | Backlog-index regeneration fallback chain | Hot | 5-6 | MECHANICAL | `skills/lifecycle/references/complete.md:42-71`, `skills/morning-review/SKILL.md:130-151` | |

### C2+C3 — Four implementations, inter-component contract

| # | Location | Output format | Constraint |
|---|----------|---------------|------------|
| 1 | `hooks/cortex-scan-lifecycle.sh:170-207` | `implement:N/M` / `implement-rework:N` / `complete` | Bash; subprocess-to-Python acceptable |
| 2 | `skills/lifecycle/SKILL.md:41-100` | `implement` / `plan` / etc. | Agent-interpreted pseudo-code |
| 3 | `claude/common.py:detect_lifecycle_phase()` | `"implement"` (discards N/M counts it computes internally at 137-145) | Canonical for Python callers |
| 4 | `claude/statusline.sh:377-402` (**missed by Round 2**) | Re-implements ladder in bash for per-prompt refresh | **Cannot** subprocess to Python (~100ms latency per prompt is too expensive) |

**Inter-component contract**: statusline parses `implement:N/M` at lines 535-546 into a progress bar. So the hook's format is not "wrapping" — it's an API the statusline reads. Canonical `claude.common` is strictly less expressive than consumers 1 and 4 need.

**Consumer audit** (Round 2 + CR2): dashboard and backlog-index call `claude.common` in Python (free). Hook can subprocess if we pay ~cold-start cost per SessionStart (acceptable). Statusline cannot. The statusline's inline copy is structural, not accidental.

**Consequence for ticket 108 effort**: L, not M. See §Feasibility.

### Existing scripts — adoption audit (CR2-corrected)

| Script | Shipped | SKILL.md reference? | Failure mode |
|--------|---------|---------------------|---------------|
| `bin/validate-spec` | 024cb6f, Apr 7 2026 | No | Day-one missing |
| `bin/count-tokens` | 428e54e, Apr 1 2026 | No | Day-one missing |
| `bin/audit-doc` | 428e54e, Apr 1 2026 | No | Day-one missing |
| `create-backlog-item` | 428e54e, Apr 1 2026 | Indirect (Python module) | Hidden behind abstraction; linter heuristic would need to recognize `backlog.create_item` as equivalent |
| `update-item` | 428e54e, Apr 1 2026 | Indirect (Python module) | Same |
| `skills/backlog/generate-index.sh` | (deleted 2026-04-07) | Was referenced, then removed and rewired to `generate-backlog-index` | **Drift — replaced** |

Positive controls (well-wired): `overnight-status`, `overnight-start`, `overnight-schedule`, `git-sync-rebase.sh`, `generate-backlog-index`. All explicitly named in SKILL.md.

**Timing pattern** (CR2): every successful wiring happened within minutes of ship or not at all. Implication: a linter not invoked during the ship session won't catch the omission unless the developer re-runs it against the whole tree (not just staged files). See DR-5 enforcement revision.

### Observability floor (CR2-expanded)

- **Pipeline, per-turn**: `lifecycle/{feature}/agent-activity.jsonl` (`dispatch.py:485-528`).
- **Pipeline, per-dispatch**: `lifecycle/sessions/{id}/pipeline-events.log`.
- **Pipeline aggregates**: `python3 -m cortex_command.pipeline.metrics --report tier-dispatch`.
- **Gap — skill name on dispatch**: `dispatch.py:445` doesn't record which skill triggered the sub-agent dispatch. Addressed by ticket 109 — but this only covers pipeline sub-agent dispatches, NOT tool calls the agent makes inside an interactive SKILL.md flow. 109 is orthogonal to interactive adoption.
- **Gap — interactive tool calls**: daytime Claude Code sessions have no tool-call log. Candidates C1, C3, C4, C5, C7, C11–C15 all live here.
- **Unused infrastructure**: `claude/settings.json:252-267` already wires PreToolUse Bash hooks (`cortex-validate-commit.sh`, `cortex-output-filter.sh`) that receive `{"tool_name": "Bash", "tool_input": {"command": "..."}}`. A third matcher grepping for `bin/*` invocations and appending to a rolling JSONL would produce real interactive-session adoption telemetry at trivial cost. See DR-7.

### Repo workflow reality (CR2)

- **PR activity**: `gh pr list --state all --limit 10` returns 3 PRs ever. Both merged PRs are "Overnight session:" batch landings. The dominant pattern is direct-to-main commits.
- **Implication for DR-5**: "CI check" as enforcement is effectively dead wiring — no PRs to gate. Pre-commit hook is the real enforcement point, with known gaps (`--no-verify`, staged-files-only scope, overnight-runner commits may bypass). See DR-5 enforcement revision.

## Web & Documentation Research

Skipped. Internal topic.

## Domain & Prior Art

- MCP / tool-calling convention, Anthropic harness-design — see prior revision. No change.

## Feasibility Assessment

| # | Candidate | Script shape | Effort | Risks | Prerequisites |
|---|-----------|--------------|--------|-------|---------------|
| C1 | `bin/commit-preflight` → `{status, diff, recent_log}` | S | ~1 turn saved. Diff emitted in full. Stage/compose stay inline. | 102 + 113 (DR-7). |
| C2+C3 | Promote `claude.common.detect_lifecycle_phase()` to canonical + extend to return `{phase, checked, total, cycle}`; expose `python3 -m cortex_command.common detect-phase <dir>` CLI; hook subprocesses to it. **Statusline stays bash** (structural constraint). Retire hook's 38-line ladder; retire skill's 22-line pseudo-ladder. `.dispatching` + worktree overrides in skill stay (they're phase *overrides*, not detection). | **L (reverted from M)** | Statusline keeps bash ladder — document that it is a known second source that cannot be unified under current constraints (DR-6). Net drift: 4→3. `claude.common` return type grows — acknowledge DR-2 tension. | 102 + documented statusline exception in DR-6. |
| C4 | `bin/build-epic-map` → `{epic_id: {children, status, refined}}` | S | Step 3c decision tree stays inline. | 102 + 113. |
| C5 | `bin/resolve-backlog-item` with distinct exit codes for unambiguous / ambiguous / no-match | S | **Ship unconditionally.** Bailout design = Pareto improvement: happy path faster, unhappy path unchanged (agent re-reads SKILL.md Step 1 guidance as today). Telemetry is post-ship validation (see 113), not a ship gate. | 102 + 113. |
| C6 | — | — | Blocked on ticket #94. | — |
| C7 | `bin/backlog-ready` → priority-grouped ready items | S | None material. | 102 + 113. |
| C8 | New CLI `bin/orchestrator-context`; extend `claude/overnight/map_results.py` | M | Orchestrator prompt rewrite + mid-round resume risk. | 109 closed; ROI confirmed with pipeline data. |
| C9 | — | — | Revisit after 109 data. | — |
| C10 | — | — | Out of scope. | — |
| C11 | `bin/morning-review-complete-session` | S | | 102 + 113. |
| C12 | New `bin/worktree-gc` or fold into `git-sync-rebase.sh` | S | Low. | 102 + 113. |
| C13 | `bin/close-completed-features` (parallel `update-item` calls) | S | Closes update-item adoption gap. | 102 + 113. |
| C14 | Fold preflight mode into `bin/git-sync-rebase.sh`; may be SKILL.md edit only | S | Minor. | 102 + 113. |
| C15 | Simplify fallback chain to single call with PATH requirement | S | Existing fallback is defensive against deployment-state unknowns; simplifying requires `just setup` guarantees. | 102 + 113. |

**Rollup**: 9 S-effort, 1 L (C2+C3 reverted), 1 M (C8), 1 blocked (C6), 2 OOS (C9, C10). Remaining scaffolding (override blocks, inter-component contracts, caller-specific wrapping) is NOT free — effort estimates assume only the extractable region is in scope, not the post-extraction cleanup.

## Decision Records

### DR-1: Extract-first vs. instrument-first — three-way split

- Interactive uses inspection; pipeline uses existing aggregator + ticket 109.
- **CR2 correction**: DR-5 (static linter) and ticket 109 (pipeline dispatch tagging) do NOT close the interactive runtime-adoption gap. DR-7 adds the missing runtime signal via PreToolUse hook matcher.

### DR-2: Script convention

- Location: `bin/`. Naming: kebab-case. Output: JSON for multi-field, plain text for single-value. **Narrow** schemas except where an inter-component contract forces wider shape (C2+C3 is the known exception — `claude.common` return type must include N/M for the hook/statusline consumers). Exit codes: 0 success, distinct non-zero per failure class. POSIX `--flag value`.

### DR-3: Interactive vs pipeline-prompt split into two epics

- Interactive ships first. Pipeline batches with 4.7 prompt-simplification work.

### DR-4: Per-extraction discoverability hygiene (INSUFFICIENT WITHOUT DR-5 + DR-7)

- Point-in-time verification at extraction ticket close. Covers (a) SKILL.md script reference, (b) replay test, (c) stale-guidance audit.

### DR-5: Standing SKILL.md ↔ bin/ parity — pre-commit first, with scope caveats

- **Evidence of need**: 3 day-one-missing cases + 2 hidden-behind-abstraction cases + 1 confirmed drift replacement. Multiple failure modes, not one.
- **Enforcement mechanism** (CR2-revised):
  - Tool: `bin/check-parity`. Also installable as `just check-parity` for full-tree scan (not staged-only).
  - **Primary enforcement: `just check-parity` as manual recipe + pre-commit hook on SKILL.md/bin/justfile changes.** Not CI-gated; this repo has ~3 PRs ever.
  - **Known limits**: `--no-verify` bypass is possible. Overnight-runner commits may skip hooks. Staged-files-only scope means an orphaned script checked in without matching SKILL.md edit may never re-trigger. Mitigation: periodic `just check-parity` as part of retro/morning-review protocol (add as a new bullet).
- **Scan scope**: all `skills/**/*.md`, `CLAUDE.md`, `claude/reference/`, `requirements/`.
- **Script inventory** (deploy-path aware): dynamic scan of `bin/` + justfile `deploy-bin` extraction for `backlog/*.py` deployed names **+** enumerate other deploy mechanisms: `hooks/cortex-notify.sh` → `~/.claude/notify.sh`, any other symlink-deploy patterns in justfile or setup scripts.
- **Signal detection**: three categories — literal `bin/foo` mentions, bare `foo` invocations in shell code blocks, path-qualified `~/.local/bin/foo`. **Known gap**: indirect invocation via `just <recipe>` is handled by recognizing `just ` patterns and cross-referencing the recipe's body. Indirect via Python module (e.g., `create-backlog-item` through `backlog.create_item`) requires a heuristic map from deployed-name → module path; this is acknowledged as a linter heuristic edge case that may need manual tuning.
- **Allowlist**: `bin/.parity-exceptions.md` with `{script: {reason, audience: user-only | orchestrator-only | module-shim}}`.
- **Failure modes acknowledged, not all solved**: the linter cannot detect "SKILL.md references the script but agent uses a different tool at runtime" — that's DR-7's scope.

### DR-6: Unification candidates enumerate ALL current implementations (including bash hot-path mirrors)

- **Rule (reinforced)**: any unification ticket must enumerate every current implementation, including those that cannot be unified due to structural constraints (e.g., statusline-style bash hot-path).
- **C2+C3 specific**: `claude.common.detect_lifecycle_phase()` is canonical for Python callers; hook subprocesses to it; skill references it; **statusline continues its bash ladder** as a documented exception. Net drift 4→3, not 4→1. The comment at `hooks/cortex-scan-lifecycle.sh:168` ("Mirrors claude.common.detect_lifecycle_phase — keep in sync") becomes: "Subprocess-delegates to claude.common; statusline is a separate bash-only mirror, see DR-6."

### DR-7 (NEW): Runtime adoption telemetry via PreToolUse Bash hook matcher

- **Context**: DR-5 catches static non-wiring. It does NOT catch the third failure mode — SKILL.md references a script but the agent doesn't invoke it. Interactive sessions have no tool-call log.
- **Mechanism**: add a PreToolUse Bash matcher in `claude/settings.json` (infrastructure already present; pattern proven by `cortex-validate-commit.sh` and `cortex-output-filter.sh`). The matcher greps the command for known `bin/*` names (inventory extracted at runtime from `just deploy-bin`), logs to a rolling JSONL (e.g., `~/.claude/bin-invocations.jsonl`) with timestamp, script name, skill context if available.
- **Usage**: weekly (or on-demand) aggregator reports per-script invocation count. A wired-but-never-invoked script is a DR-7-detectable failure.
- **Ship order**: 113 (DR-7 telemetry) ships alongside 102 (DR-5 static lint). Both S-effort; together they cover day-one + drift + runtime failure modes.
- **Trade-offs**: adds one more hook (mild overhead on every Bash tool call — but hooks already exist for other purposes). Log file hygiene needs a size cap or rotation.

## Open Questions

- **DR-5 allowlist scope**: `audit-doc` — governance-only or retrofit-wired into a doc-review skill?
- **C11–C15 bundling**: single ticket vs several? Same-file overlap in `morning-review/SKILL.md` supports bundling, but C14 touches `bin/git-sync-rebase.sh` (different file) and C15 touches `skills/lifecycle/references/complete.md` (different file). Acceptable consolidation or over-decomposed M?
- **DR-2 narrow-schema exception**: `claude.common.detect_lifecycle_phase()` returning `{phase, checked, total, cycle}` violates "narrow" — document as a known inter-component-contract exception or seek an alternative (e.g., separate `detect-phase-progress` CLI that returns just counts)?
- **DR-7 privacy/log-size**: how aggressive is JSONL rotation? Weekly archive? Auto-purge old entries?
- **DR-5 scope for non-bin deploy paths**: `hooks/cortex-notify.sh` → `~/.claude/notify.sh` is a different deploy mechanism. Should the linter enumerate all such paths or stay scoped to `bin/`?
- **Subagent dispatch in `/research`, `/critical-review`, `/discovery`** — mechanical shell around judgment. Future candidate after first wave lands.
