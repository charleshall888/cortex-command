# Research: Extract Scripts From Agent Tool-Call Sequences

## Topic

Identify places in the agentic harness (skills, hooks, pipeline prompts, lifecycle flows) where the Claude agent executes sequences of deterministic tool calls that could collapse into a single agent-invokable script. Goal: save tokens, reduce wall-clock latency, and increase determinism where the logic has no model judgment between steps.

## Research Questions

1. **Inventory.** Where does the agent execute ≥3 deterministic tool calls in sequence? → **Answered.** ~10 viable candidates surfaced across skills, hooks, and pipeline prompts. Hot paths: `/commit` preflight reads, `/lifecycle` phase detection (both SessionStart hook and `/lifecycle` Step 2), `/dev` epic-map parse, `/refine` backlog-item resolution, lifecycle daytime polling loop, orchestrator-round state reader. Full list in §Codebase Analysis.

2. **Determinism axis.** Which are MECHANICAL vs JUDGMENT-AT-ENDPOINTS vs JUDGMENT-INTERLEAVED? → **Answered, with narrower scoping than the initial pass.** Classification now annotates the specific sub-range of each skill that is actually mechanical, rather than applying the label to the whole candidate row. Several candidates previously tagged "MECHANICAL" are really "mechanical parse + judgment decision downstream" — extraction replaces only the parse. See §Codebase Analysis.

3. **Cost.** Per-invocation token and latency cost of current sequences vs collapsed call? → **Partially answered.** The pipeline logs per-turn tool calls into `agent-activity.jsonl` (`claude/pipeline/dispatch.py:485-528`) and per-dispatch turn/cost in `pipeline-events.log`. Per-`(model, tier)` aggregates exist (`python3 -m claude.pipeline.metrics --report tier-dispatch`). **Gap**: skill name is not recorded in `dispatch_start` (dispatch.py:445), so per-skill tool-call averages are not computable today. **Parallel-call caveat**: several candidates run tool calls in parallel within one agent turn (e.g., `/commit` preflight). Collapsing N parallel calls into 1 script call saves ~1 turn, not N calls-worth. The Candidate Inventory's "Calls" column is serial-equivalent turns, not raw tool-call count. Precise ROI numbers are estimates, not measurements. Hook-based and SessionStart sequences have no log at all.

4. **Existing scripts as models.** What in `bin/`, `backlog/`, `hooks/` already works well? → **Answered, with adoption caveats.** `bin/` convention is kebab-case single-purpose CLIs with distinct exit codes. `overnight-status`, `overnight-start`, `overnight-schedule`, `git-sync-rebase.sh` are structurally good AND well-adopted (each has ≥1 SKILL.md direct reference). `validate-spec`, `count-tokens`, `audit-doc`, `create-backlog-item` are structurally good but **not adopted** — no SKILL.md invokes them. The structural template is a necessary but not sufficient predictor of adoption. See §Decision Record DR-2.

5. **Discoverability & adoption.** How does an agent find out a script exists? → **Answered, and this is the load-bearing finding.** Adoption is set by SKILL.md references at the point of use and decays as SKILL.md files are re-authored without re-audit. Four deployed-but-unused scripts is direct evidence that one-shot extraction without ongoing enforcement produces script accretion, not adoption. See DR-5.

6. **Transparency trade-off.** When does collapsing hurt? → **Answered.** Collapsing is safe when (a) the sequence is pure data-gathering whose output the agent inspects as a unit anyway, (b) exit codes + short structured output make the agent's next-step decision equivalent, AND (c) the downstream agent work is not a re-read of what the script collapsed (e.g., `/commit` Step 4 composes the message *from the diff content*, so a script that summarizes the diff forces a re-read — negating the saving). It hurts when any of those fail.

7. **Ranked candidates.** → **Answered** in §Feasibility Assessment, with scope narrowed per Q2 and cost framing corrected per Q3.

## Codebase Analysis

### Candidate Inventory

Ranked by (frequency × extractable-surface-size × determinism clarity). Hot = every session. Warm = per-phase/per-feature. Cool = occasional. **Calls column** is serial-equivalent turns within the extractable region — parallel calls in the same turn count once.

| # | Candidate | Heat | Turns | Class | Location | Extractable scope |
|---|-----------|------|-------|-------|----------|-------------------|
| C1 | `/commit` preflight (`git status` + `git diff HEAD` + `git log --oneline -10`) | Hot | 1 (3 parallel calls) | MECHANICAL-PARSE, JUDGMENT-DOWNSTREAM | `skills/commit/SKILL.md:12-14` | Preflight reads only. Steps 3–5 (stage / compose / commit) stay inline — staging is judgment, message composition reads the diff. Saving: 1 turn + prompt-level clarity. |
| C2 | Lifecycle phase detector (SessionStart hook) | Hot | ~7 | MECHANICAL-PARSE + FORMATTING | `hooks/cortex-scan-lifecycle.sh:170-417` | Only the ~20-line reverse-order file-existence ladder is shared with C3. Surrounding logic (tier metric computation, morning-review suppression, session migration, worktree awareness, status-line formatting) is hook-specific and not co-extractable. |
| C3 | `/lifecycle` Step 2 artifact-based phase detection | Hot | 4-7 | MECHANICAL-PARSE + JUDGMENT-DOWNSTREAM | `skills/lifecycle/SKILL.md:41-100` | The reverse-order ladder (shared with C2). The `.dispatching` marker check, worktree-aware phase detection, and criticality/tier-override scan are skill-specific and stay inline. |
| C4 | `/dev` epic-map parse (Step 3a/3b) | Warm | 4-5 | MECHANICAL-PARSE, JUDGMENT-DOWNSTREAM | `skills/dev/SKILL.md:135-166` | Parent-field normalization (quotes / UUID skip / integer match) and the flat-list dedup extract. Step 3c's ~60-line workflow-recommendation decision tree stays inline and may grow because DR-2 requires the script's output schema to be documented at point of use. |
| C5 | `/refine` Step 1 backlog-item resolution | Warm | 3-4 | MECHANICAL-PARSE on happy path | `skills/refine/SKILL.md:22-35` | Happy-path only: unambiguous fuzzy match, three-slug derivation (`backlog-filename-slug`, `item-title`, `lifecycle-slug` — "often different"). Ambiguous-input path bails via exit code; agent redoes disambiguation inline — savings conditional on happy-path rate, which is unestimated. |
| C6 | Lifecycle daytime polling loop | Warm | ~3 × N iterations | MECHANICAL | `skills/lifecycle/references/implement.md:144-155` | Full loop. See Open Question re: ticket #94 obsolescence. |
| C7 | `/backlog pick` index→filter→table | Warm | 3-4 | JUDGMENT-AT-ENDPOINTS | `skills/backlog/SKILL.md:82-94` | Filter + sort + render; selection itself is agent judgment. |
| C8 | Orchestrator-round state read (overnight prompt) | Warm | 6-8 | MECHANICAL | `claude/overnight/prompts/orchestrator-round.md:22-176` | Pure file-read aggregation. **Data-rankable today** — runs inside the pipeline where `agent-activity.jsonl` already exists. |
| C9 | Plan-gen dispatch + result collection | Cool | ~8 | JUDGMENT-AT-ENDPOINTS | `claude/overnight/prompts/orchestrator-round.md:237-294` | Mechanical middle, judgment at endpoints. |
| C10 | Merge-conflict classify + dispatch | Cool | ~8 | JUDGMENT-INTERLEAVED | `claude/overnight/feature_executor.py` | Out of scope. |

**C2+C3 caveat**: beyond the two callers named, a third copy of phase-detection logic lives at `claude.common.detect_lifecycle_phase`, cross-referenced in `hooks/cortex-scan-lifecycle.sh:168` ("Mirrors claude.common.detect_lifecycle_phase — keep in sync if phase model changes"). Any unification must **retire** old implementations, not just add a new shared script — otherwise the count goes 3 → 4, not 3 → 1. See DR-6.

### Existing scripts — adoption audit

| Script | Structural shape | Adopted? | Wired by |
|--------|------------------|----------|----------|
| `bin/overnight-status` | Single-shot state read, human-readable | Yes | morning-review |
| `bin/overnight-start`, `overnight-schedule` | tmux launcher, positional args | Yes | overnight, morning-review |
| `bin/git-sync-rebase.sh` | Distinct exit codes, stderr logs | Yes | morning-review walkthrough |
| `bin/validate-spec` | Defaults to `lifecycle/*/spec.md`, non-zero on error | **No** — no SKILL.md wires it | none |
| `bin/count-tokens` | Simple file scanner + SDK token count | **No** | none |
| `bin/audit-doc` | Token + noise ratio report | **No** | none |
| `backlog/create_item.py` (deployed as `create-backlog-item`) | Atomic frontmatter + sidecar event log | **No** — skill uses Python module indirectly | none (only CLAUDE.md mention) |
| `backlog/update_item.py` (deployed as `update-item`) | Frontmatter update with side-effects | **No direct wire** — mentioned in CLAUDE.md | none |
| `backlog/generate_index.py` (deployed as `generate-backlog-index`) | JSON + md output | Yes (invoked by other scripts and `/dev`) | dev |

Five of nine "good-shape" scripts are under-adopted. The structural template is necessary but not sufficient. See DR-5.

### Observability floor

- Per-turn tool calls: logged in `lifecycle/{feature}/agent-activity.jsonl` by `claude/pipeline/dispatch.py:485-528`.
- Per-dispatch turns + cost: logged in `lifecycle/sessions/{id}/pipeline-events.log`.
- Per-`(model, tier)` aggregates: `python3 -m claude.pipeline.metrics --report tier-dispatch`.
- **Not logged**: which skill initiated the dispatch. Adding skill-name to `dispatch_start` is an S-effort change in `dispatch.py:445`.
- **Not logged at all**: daytime interactive sequences (the `/commit`, `/dev`, `/lifecycle` candidates live here). The agent-activity recorder is pipeline-scoped.

Consequence: the interactive candidates (C1, C3, C4, C5, C7) cannot be ranked by data today without new instrumentation that doesn't exist. C8 (pipeline-prompt) **can** be ranked today using the existing aggregator; C9 could be ranked with skill-name added to `dispatch_start`.

## Web & Documentation Research

Skipped. Internal topic, no external dependencies.

Adjacent internal references:
- Completed ticket #51 (hook-based preprocessing for test/build output) — filter pattern for tool *output*.
- `research/agent-output-efficiency/research.md` — subagent output-format + "1,000-2,000 token condensed return" anchor.

## Domain & Prior Art

- **MCP / tool-calling convention**: prefer single tools with structured output over multi-step protocols. Our agent-invokable scripts are a poor-man's MCP tool — more flexible, less discoverable.
- **Anthropic harness-design**: scaffolding encodes assumptions about what the model can't do. Under Opus 4.7, some in-prompt scaffolding is removable (ticket #88). Script extraction is the orthogonal direction: keep the scaffolding, move it out of the agent's context window.

## Feasibility Assessment

| # | Candidate | Script shape | Effort | Risks | Prerequisites |
|---|-----------|--------------|--------|-------|---------------|
| C1 | `bin/commit-preflight` → `{status, diff, recent_log}` | S | Savings are ~1 turn (3 parallel → 1 serial), not ~3 calls. Diff must be emitted in full — any summary forces the agent to re-read. Staging and message composition stay inline. | DR-5 enforcement committed. |
| C2+C3 | `bin/detect-lifecycle-phase` → `{phase, slug, has_artifacts}`; hook and skill call, keep their divergent surrounding logic inline | **L (not M)** — scope unbounded until prerequisites complete | Only ~20 lines are common between hook and skill. Script becomes a superset of hook needs (tier-override scan) OR subset (re-introducing divergent logic). Third implementation at `claude.common.detect_lifecycle_phase` must be retired in the same change, or count goes 3 → 4. DR-2's "keep schemas flat" is in tension with the multi-field output shape — mitigate by narrowing the script's output to the minimum both callers need; put derived fields (tier, criticality) in whichever caller needs them. | (a) Audit hook output usage + determine whether status-line formatting is still needed (promoted from Open Question to prerequisite). (b) Enumerate all three current implementations and commit to a retirement plan. (c) DR-5 enforcement committed. |
| C4 | `bin/build-epic-map` → `{epic_id: {children, status, refined}}` | S | Parent-field normalization extracts; `/dev` Step 3c workflow-recommendation decision tree stays inline and grows under DR-2's "output format at point of use." Net SKILL.md line count may not decrease. | DR-5 enforcement committed. |
| C5 | `bin/resolve-backlog-item <fuzzy>` — exit codes for unambiguous / ambiguous / no-match | S | Savings only on happy path. Ambiguous rate is unmeasured — if <50%, extraction pays for itself only marginally. Three-slug derivation must match `claude/common.py:slugify()` exactly. | Sample recent `/refine` invocations to estimate ambiguous-input rate. DR-5 enforcement committed. |
| C6 | `bin/poll-daytime-subprocess <feature>` — batch polling, exit-coded checkpoints | M | Changes user-facing UX at iter 30 (offer-to-stop). | **Block on ticket #94 resolution** — subprocess-lifecycle may be restructured; extraction before that is likely wasted. |
| C7 | `bin/backlog-ready` → priority-grouped ready items | S | None material. | DR-5 enforcement committed. |
| C8 | Extend `claude/overnight/map_results.py`; new CLI `bin/orchestrator-context` | M | Orchestrator prompt rewrite + mid-round resume risk. | **Instrument first**: add skill-name to `dispatch_start` + secondary aggregator over `agent-activity.jsonl`, then rank C8/C9 with data before committing. |
| C9 | — | — | Judgment-at-endpoints; revisit after C8 data. | — |
| C10 | — | — | Judgment-interleaved; out of scope. | — |

**Rollup**: 4 S-effort (C1, C4, C5, C7), 1 M (C6, blocked), 1 L (C2+C3, scope unbounded pending prerequisites), 1 M-after-instrumentation (C8). The M-or-lower clean wins are C1, C4, C7. C5 wins iff ambiguous rate is low. C2+C3 should not ship until its prerequisites close.

## Decision Records

### DR-1: Extract-first vs. instrument-first — three-way split

- **Context**: Candidates differ in whether existing observability can rank them.
- **Options**:
  - (a) Instrument everything first (add skill-name to `dispatch_start`, build secondary aggregator, wait for sample), then rank and extract.
  - (b) Extract all by inspection now.
  - (c) **Split**: inspection-ship the interactive candidates where no data is feasible (C1, C3/C4/C5, C7); instrument-first for pipeline-side (C8, C9) where data exists or is one small schema change away.
- **Recommendation**: (c). Interactive candidates' structural determinism + every-session frequency is a sufficient (if noisy) signal. Pipeline candidates must use the aggregator that already exists. The two halves have different data environments and deserve different gates.
- **Trade-offs**: The heuristic for the interactive half is not validated (DR-5 acknowledges this). (c) doesn't fix that — DR-5's standing enforcement does.

### DR-2: Script convention

- **Context**: Shared shape so agent invocation is uniform.
- **Recommendation**:
  - **Location**: `bin/` for cross-skill; `skills/<skill>/bin/` for skill-local.
  - **Naming**: kebab-case verb-noun.
  - **Output**: JSON for multi-field; plain text for single-value. **Narrow**, not fat — include only fields ≥2 callers need. Derived/caller-specific fields stay in the caller.
  - **Exit codes**: 0 = success; distinct non-zero per failure class the agent can branch on.
  - **Flags**: POSIX `--flag value`.
  - **Good-shape examples**: `overnight-status`, `overnight-start`, `overnight-schedule`, `git-sync-rebase.sh`. (Structural template — see DR-5 re: adoption.)
- **Trade-offs**: Schema versioning discipline required; small-and-flat mitigates silent breakage.

### DR-3: Interactive vs pipeline-prompt split into two epics

- **Context**: Interactive candidates' savings accrue to interactive cost + user latency; pipeline candidates' accrue to overnight budget/turn caps.
- **Recommendation**: Two epics. Interactive ships first (no session-resume complications). Pipeline-prompt batches with other 4.7 prompt-simplification work (tickets #88, #92).
- **Trade-offs**: Two review cycles; matches the natural seam.

### DR-4: Per-extraction discoverability hygiene (INSUFFICIENT WITHOUT DR-5)

- **Context**: Script exists + SKILL.md references it = day-one adoption. That's not enough over time.
- **Recommendation**: Every extraction ticket must (a) replace the SKILL.md step with a direct script reference at point of use; (b) run a replayable test case against the prior transcript to confirm the agent invokes the script; (c) audit for stale "do this with tool calls" guidance.
- **Trade-offs**: Point-in-time verification only. Does not detect drift after a future SKILL.md edit. DR-5 handles the drift axis.

### DR-5 (NEW): Standing SKILL.md ↔ bin/ parity enforcement is a prerequisite, not a follow-up

- **Context**: Four of nine good-shape bin/ scripts are deployed but not referenced by any SKILL.md: `validate-spec`, `count-tokens`, `audit-doc`, `create-backlog-item`. Direct evidence that DR-4's per-ticket verification does not hold across subsequent skill edits. Shipping more scripts without a standing signal ensures the under-used pile grows.
- **Options considered**:
  - (a) Ship per-ticket hygiene (DR-4) and hope.
  - (b) Add a lint/CI check that every `bin/` entry is referenced by ≥1 SKILL.md (or an explicit allowlist of scripts intended for user-only / orchestrator-only use).
  - (c) Add agent-invocation telemetry (log every Bash call whose first word matches a `bin/` entry) so post-ship non-adoption is observable.
- **Recommendation**: (b) as a prerequisite to further extraction. (c) is a follow-up — telemetry requires instrumentation infra the interactive surface lacks.
- **Trade-offs**: (b) requires a small linter and an allowlist for intentionally-not-wired scripts. The alternative — "keep shipping, keep accumulating" — has a measured failure rate of 4/9.

### DR-6 (NEW): Unification candidates must include retirement plan for all prior copies

- **Context**: The `/lifecycle` phase-detection logic already exists in three places: `hooks/cortex-scan-lifecycle.sh`, `skills/lifecycle/SKILL.md`, and `claude.common.detect_lifecycle_phase`. A new `bin/detect-lifecycle-phase` that is "consumed by both [hook and skill]" without retirement of the prior copies takes the count from 3 to 4.
- **Recommendation**: Any unification ticket must enumerate all current implementations (not just the two the feature request mentions), specify which get retired in the same change, and specify what the retirement looks like (deleted, reduced to a thin wrapper, kept only for backward-compat with named sunset).
- **Trade-offs**: Larger per-ticket scope, but the alternative has produced the current triad and is not trending better.

## Open Questions

- **C5 ambiguous-input rate**: sample recent `/refine` invocations (events logs or conversation transcripts). If ambiguous rate ≥50%, C5's savings evaporate and it drops below the ship bar.
- **DR-5 allowlist**: which scripts are legitimately user-only / orchestrator-only (never wired from a SKILL.md)? Candidate allowlist: `overnight-start`, `overnight-schedule`, `audit-doc` (if kept as human-only governance), the `just` recipes under Development/Testing.
- **C8 instrumentation**: add skill-name to `dispatch_start` event in `claude/pipeline/dispatch.py:445` + secondary aggregator over `agent-activity.jsonl`. This is a blocker for the pipeline-side epic, not a follow-up.
- **C6 blocking on ticket #94**: check whether daytime subprocess-lifecycle is being restructured before investing in C6.
- **Should `update-item` / `create-item` get thin skill-invoked wrappers** to close their adoption gap alongside new extractions? Probably yes — they're the lowest-risk test case for DR-5's enforcement.
- **Subagent dispatch in `/research`, `/critical-review`, `/discovery` research phase**: mechanical shell around judgment synthesis. Possible future candidate; not in this decomposition.
