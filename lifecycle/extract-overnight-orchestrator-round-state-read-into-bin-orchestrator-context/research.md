# Research: Extract overnight orchestrator-round state read into a `cortex` CLI subcommand (ticket 111)

> **Scope anchor (from Clarify §5)**: Reduce per-orchestrator-round context cost by extracting the 6–8 inline state-file reads in `cortex_command/overnight/prompts/orchestrator-round.md` into a single `cortex` CLI subcommand that emits aggregated round context as JSON. Distribution decision is locked at Clarify time: **Option 1** (cortex CLI subcommand inside `cortex_command/`, NOT a `bin/` script).

## Codebase Analysis

### Files that will change

- `cortex_command/cli.py` (current overnight subparser block at lines 319–511): register a new `orchestrator-context` subparser alongside `start | status | cancel | logs | list-sessions`. Pattern: `overnight_sub.add_parser("orchestrator-context", help=..., description=...)`, register args, set `func=_dispatch_overnight_orchestrator_context` (lazy-import handler).
- `cortex_command/overnight/cli_handler.py`: add `handle_orchestrator_context(args) -> int` following the signature of `handle_status` (lines 231–301). Use `_emit_json(payload)` (lines 43–50) which always prepends `version: _JSON_SCHEMA_VERSION = "1.0"`. Use `session_validation.validate_session_id` + `session_validation.resolve_session_dir` for any session-id input (parity with `handle_status` at lines 329–343).
- `cortex_command/overnight/orchestrator_io.py`: re-export the new aggregator function so the orchestrator prompt's import surface stays single-audit-point. Per `docs/overnight-operations.md:497-498`: *"Any new orchestrator-callable I/O primitive is added here rather than imported directly from `claude.overnight.state` or `claude.overnight.deferral` by the orchestrator."*
- `cortex_command/overnight/prompts/orchestrator-round.md` (lines 22–176): rewrite Step 0/1/1a/2 to invoke the aggregator (either the new in-process function via `orchestrator_io` or the new subprocess CLI) instead of doing inline reads of `escalations.jsonl`, `overnight-state.json`, `overnight-strategy.json`, and the session plan markdown.
- `docs/overnight-operations.md` (owns round-loop and orchestrator behavior per CLAUDE.md): add a section documenting the new aggregator, its JSON schema, and how the orchestrator-round prompt consumes it.
- `docs/pipeline.md` and `docs/sdk.md`: cross-link to the new section in `docs/overnight-operations.md` rather than duplicating.

### Files that will be created

- `cortex_command/overnight/<aggregator-module>.py`: the aggregator module itself. Naming: agents disagreed (`orchestrator_context.py` vs `round_context.py`). Spec to choose. Exports `aggregate_round_context(session_dir: Path, round_number: int) -> dict`.
- `tests/test_<aggregator-module>.py`: unit tests covering the aggregator function. For CLI-handler subprocess + stdout discipline, follow `tests/test_cli_overnight_format_json.py` pattern (not `tests/test_map_results.py`, which is too thin a template per the Adversarial review).

### Existing patterns to follow

#### Subcommand registration (argparse, in `cortex_command/cli.py:319-511`)

```python
overnight = subparsers.add_parser("overnight", help="...", description="...")
overnight_sub = overnight.add_subparsers(dest="overnight_command", required=True, metavar="<subcommand>")
start = overnight_sub.add_parser("start", help="...", description="...")
start.add_argument("--state", type=str, default=None, help="...")
start.set_defaults(func=_dispatch_overnight_start)
```

The new subcommand follows the same shape. Dispatch functions in `cli.py` lazy-import handlers from `cortex_command.overnight.cli_handler` to keep cold-start light.

#### Versioned JSON output (`cortex_command/overnight/cli_handler.py:40-50`)

```python
_JSON_SCHEMA_VERSION = "1.0"

def _emit_json(payload: dict) -> None:
    versioned = {"version": _JSON_SCHEMA_VERSION, **payload}
    print(json.dumps(versioned))
```

Note: `_emit_json` is module-private. The aggregator should not import it cross-module — either keep emission inside `cli_handler.handle_orchestrator_context` (recommended) or factor `_emit_json` into a shared `cortex_command/overnight/json_emit.py` if reuse is needed.

#### Atomic write + unprotected read (`cortex_command/common.py:atomic_write` and `cortex_command/overnight/state.py`)

Writes use `tempfile.mkstemp` + `os.write` + `durable_fsync` (F_FULLFSYNC on macOS) + `os.replace`. Reads are unprotected (`load_state`, `load_strategy` use plain `read_text` / `json.loads`). Per `requirements/pipeline.md:127,134`, this is a permanent architectural constraint; the new aggregator must follow the same convention (no locking).

#### Handler delegates to sibling module (precedent: every existing overnight handler)

`handle_status` calls `status_module.render_status()` (line 297). `handle_logs` calls `logs_module`. `handle_start` calls `runner_module.run`. The handler stays thin; domain logic lives in a sibling module. The new handler should follow this — it should not inline aggregation logic.

### Inline-read inventory in `orchestrator-round.md` (lines 22–176, 200–304)

The aggregator must consolidate these reads. The Adversarial review (see below) corrected several misclaims about the "6–8 inline reads" framing — many "reads" are already structured Python library calls, not raw `Read`-tool invocations.

| Step | Source | Read type | Conditional? | Purpose |
|------|--------|-----------|--------------|---------|
| 0a | `escalations.jsonl` existence check | filesystem | always | gate Step 0 |
| 0b | `escalations.jsonl` (line-by-line JSONL) | Python `read_text` + `json.loads` | only if file exists | unresolved escalations |
| 0d | per-feature `spec.md` and `plan.md` | `Read`-tool invocations on markdown | only when escalations reference a feature, capped at 5 | escalation resolution context |
| 1 | `overnight-state.json` via `load_state` | structured Python (already library call) | always | round/feature state |
| 1a | `overnight-strategy.json` via `load_strategy` | structured Python (already library call) | always | hot files, round notes |
| 2 | session plan markdown | `Read`-tool on markdown | always | batch assignments |
| 2a | per-feature `intra_session_blocked_by` (in state) | dict access on already-loaded state | always | dependency check |
| 3 | per-feature `spec_path` / `plan_path` (in state) | dict access on already-loaded state | always | path lookup |
| 3a–3e | per-feature `spec.md` / `plan.md` for current round | `Read`-tool on markdown, per feature | only for features dispatched this round | feature plan input |
| 4 | overnight-events.log merge_conflict events | `events.read_events()` | always | paused-feature awareness |

**Aggregator scope (recommended)**: only the *unconditional* round-startup snapshot — `escalations.jsonl` (parsed), `overnight-state.json`, `overnight-strategy.json`, session plan markdown, and the merge-conflict event subset of overnight-events.log. Per-feature `spec.md`/`plan.md` reads are excluded because they are conditional and per-feature; folding them in would require either eager-read-all (expensive) or per-call filters (re-introduces coordination cost).

### State file schemas

#### `overnight-state.json` (writer: `cortex_command/overnight/state.py:save_state` lines 404–445; reader: `load_state` line 334)

```python
@dataclass
class OvernightState:
    session_id: str
    plan_ref: str
    plan_hash: Optional[str]
    current_round: int
    phase: str  # planning | executing | complete | paused
    features: dict[str, OvernightFeatureStatus]
    round_history: list[RoundSummary]
    started_at: str
    updated_at: str
    paused_from: Optional[str]
    paused_reason: Optional[str]
    integration_branch: Optional[str]
    integration_branches: dict[str, str]
    worktree_path: Optional[str]
    project_root: Optional[str]
    integration_worktrees: dict[str, str]
    scheduled_start: Optional[str]
    integration_pr_flipped_once: bool
    integration_degraded: bool
    schema_version: int = 1
```

`OvernightFeatureStatus` has `status, round_assigned, started_at, completed_at, error, deferred_questions, spec_path, plan_path, backlog_id, recovery_attempts, recovery_depth, repo_path, intra_session_blocked_by`.

`RoundSummary` has `round_number, features_attempted, features_merged, features_paused, features_deferred, started_at, completed_at`.

#### `overnight-strategy.json` (writer: `cortex_command/overnight/strategy.py:save_strategy` lines 66–102; reader: `load_strategy` line 36)

```python
@dataclass
class OvernightStrategy:
    hot_files: list[str]
    integration_health: str  # healthy | degraded
    recovery_log_summary: str
    round_history_notes: list[str]  # ⚠ unbounded — see Adversarial Review
```

#### `escalations.jsonl` (writer: `cortex_command/overnight/deferral.py:write_escalation` lines 407–440)

Append-only JSONL. Three entry types:
- `{"type": "escalation", "escalation_id", "session_id", "feature", "round", "question", "context", "ts"}`
- `{"type": "resolution", "escalation_id", "feature", "answer", "resolved_by", "ts"}`
- `{"type": "promoted", "escalation_id", "feature", "promoted_by", "ts"}`

Unresolved set = escalations minus those with matching resolution/promoted entries by `escalation_id`.

#### Session plan markdown

Currently unstructured-but-conventional. Read by orchestrator for batch assignments and intra-session dependencies. Aggregator should pass through (or extract) the relevant batch-assignment subsection.

#### `overnight-events.log` (writer: `cortex_command/overnight/events.py:log_event`; reader: `events.read_events()`)

JSONL. The aggregator only needs the `merge_conflict_classified` subset to give the orchestrator paused-feature awareness.

## Web Research

### Prior art for context aggregation in agent loops

- **Manus' compact-vs-full pattern** — keeps a "full" tool result alongside a "compact" file reference; stale results swap to compact while recent stay full. Manus also offloads state to a sandbox filesystem and keeps the function-calling layer under ~20 atomic tools, deferring richer behavior to CLI utilities. Directly analogous to the proposed shape. ([rlancemartin.github.io/2025/10/15/manus](https://rlancemartin.github.io/2025/10/15/manus/))
- **Anthropic's "lightweight identifiers + dynamic load"** — explicitly recommends agents maintain identifiers (paths, queries) and pull data through tool calls rather than inlining file contents. ([anthropic.com/engineering/effective-context-engineering-for-ai-agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents))
- **Iterative retrieval beats upfront stuffing** — letting the agent ask for what it needs in stages reportedly improves accuracy ~10% while reducing context. ([Redis: LLM Token Optimization](https://redis.io/blog/llm-token-optimization-speed-up-apps/))

### CLI-emitted JSON as agent context (relevant conventions)

- **Conventions**: JSON to stdout, prose to stderr; semantic exit codes (0 ok / 1 generic / 2 usage / 3 not-found / 4 perms / 5 conflict); `--no-prompt` / `--quiet` flags; self-documenting `--schema` flag; flat field names that mirror existing model conventions; structured output is a versioned API contract. ([dev.to: CLI tools agents want to use](https://dev.to/uenyioha/writing-cli-tools-that-ai-agents-actually-want-to-use-39no), [InfoQ: AI Agent Driven CLIs](https://www.infoq.com/articles/ai-agent-cli/))
- **Versioning**: include `schema_version`; treat additions as non-breaking, removals/renames as breaking. (InfoQ above.)

### Anti-patterns

- **Schema brittleness** — one malformed JSON kills the whole round vs. one missing file killing one inline read. Pair with JSON-schema fixtures in tests; treat shape changes as breaking. ([promptlayer JSON-Schema](https://blog.promptlayer.com/how-json-schema-works-for-structured-outputs-and-tool-integration/))
- **Context bloat from over-aggregation** — Anthropic warns more tokens compete for attention regardless of relevance; cap the JSON size; prefer file references for anything > ~200 tokens of inner content. ([Anthropic context engineering, above])
- **Loss of per-source attribution** — debugging gets harder. Worth keeping inline reads as fallback. ([Jeremy Daly: Context Engineering for Commercial Agent Systems](https://www.jeremydaly.com/context-engineering-for-commercial-agent-systems/))
- **Prompt-prefix invalidation** — flagged by Web agent but **moot here** per the Adversarial review (each round spawns fresh; no cross-round system-prompt cache).

### Key takeaways

1. The bet is well-supported by prior art directionally (Manus + Anthropic both recommend it).
2. Treat the JSON as a versioned API: `schema_version`, JSON-schema fixture in tests, flat-as-possible per-source field names, cap inner content.
3. Keep an escape hatch — preserve inline-read pseudocode as fallback documentation, or accept the centralized-chokepoint risk explicitly.

Sources: see Web Agent's full reference list (Manus, Anthropic, Tokenoptimize.dev, Fast.io 2026, Redis, dev.to, InfoQ, promptlayer, thoughtbot, Real Python, Typer docs, click-plugins, Don't Break the Cache arxiv, MCP Schema Reference).

## Requirements & Constraints

### From `requirements/project.md`

- **"Complexity must earn its place by solving a real problem that exists now."** (line 19)
- **"File-based state... No database or server."** (line 25) — the new aggregator reads files only, no new persistent state.
- **"Maintainability through simplicity"** (line 32) — the aggregator should be one small module, not a new subsystem.
- **"Context efficiency: Deterministic preprocessing... no token cost for the filtering itself."** (lines 35–36) — directly supports the design intent.
- **"Defense-in-depth for permissions... overnight runner bypasses permissions entirely (`--dangerously-skip-permissions`)... making sandbox configuration the critical security surface for autonomous execution."** (line 34) — the new subcommand runs in skip-permissions mode; it must remain read-only and validate any user-supplied paths.

### From `requirements/pipeline.md`

- **Atomicity**: "All session state writes use tempfile + `os.replace()` — no partial-write corruption" (line 126).
- **Concurrency safety**: "State file reads are not protected by locks; the forward-only phase transition model ensures re-reading a new state is safe" (line 127). Permanent constraint (line 134). The aggregator must not introduce locking.
- **CLI shape**: "The overnight runner ships as a `cortex overnight {start|status|cancel|logs}` Python CLI" (line 28). New subcommand inherits this naming.
- **Stdout cleanliness**: "When `~/.claude/notify.sh` is absent, notifications fall back to stderr with a `NOTIFY:` prefix so stdout remains clean as the orchestrator agent's input channel" (line 28). The new subcommand's JSON goes to stdout; all diagnostics go to stderr.

### From `docs/overnight-operations.md`

- **Orchestrator I/O surface** (lines 491–498): *"`cortex_command/overnight/orchestrator_io.py` is the sanctioned import boundary for orchestrator-callable I/O primitives... Any new orchestrator-callable I/O primitive is added here rather than imported directly from `claude.overnight.state` or `claude.overnight.deferral` by the orchestrator. This keeps the orchestrator's blast radius for internal refactors bounded to one file."* The aggregator must re-export through `orchestrator_io.py`.
- **Per-round agent freshness** (lines 32–33): *"Each round spawns a fresh `claude -p` invocation — the orchestrator reads state files each time rather than carrying memory between rounds."* Confirms there is no in-process cross-round caching to consider.

### From `requirements/observability.md`

- "All three [observability] subsystems are read-only with respect to session state files" (line 93). The new aggregator extends this read-only principle.

### From `CLAUDE.md` (project root)

- "Overnight docs source of truth: `docs/overnight-operations.md` owns the round loop and orchestrator behavior; `docs/pipeline.md` owns pipeline-module internals; `docs/sdk.md` owns SDK model-selection mechanics." Documentation for the new aggregator goes in `docs/overnight-operations.md`.

### Scope boundaries

**In-scope (relevant to this work)**:
- New Python CLI subcommand under `cortex overnight` following the existing argparse pattern
- JSON to stdout, diagnostics to stderr
- Read-only access to session state files
- File-based reads with no locking (per architectural constraint)
- Integration via `orchestrator_io.py` re-export

**Out-of-scope**:
- Publishing as a reusable package or registering with a package manager
- Writing to state files (read-only only)
- Parallel agent spawning (orchestrator owns parallelism)
- Changing the lock-free-reads architectural constraint
- Daytime/interactive workflows (this is overnight-only)
- Plan-gen dispatch (C9, separate ticket)

### Architectural constraints summary

1. JSON to stdout, all else to stderr (orchestrator agent input contract).
2. Read-only with respect to state files.
3. No locking on reads; rely on forward-only state transitions for safety.
4. Re-export through `orchestrator_io.py` per the sanctioned-import-boundary rule.
5. Validate any user-supplied session-id / state-path inputs (parity with `handle_status`).
6. Versioned JSON envelope via `_emit_json` pattern.

## Tradeoffs & Alternatives

### Module organization

| | Description | Pros | Cons |
|---|---|---|---|
| **A. Extend `map_results.py`** (ticket suggestion) | Add `aggregate_round_context()` to the existing module | Lowest LOC delta; `load_state` / `load_strategy` already imported | `map_results.py:1-11`'s docstring scopes it to *post-round write-side* mapping; new function is *pre-round read-side*; conflates two distinct lifecycle phases; argparse harness already serves a different entry-point style |
| **B. New dedicated module** (e.g., `orchestrator_context.py` or `round_context.py`) | New module imports `load_state`/`load_strategy` and reads `escalations.jsonl` directly; CLI handler thin-wraps it | Matches package convention (one-module-per-concern: state, strategy, events, deferral, orchestrator_io); precedent in `orchestrator_io.py` (orchestrator-prompt-facing module); new test file doesn't pollute `test_map_results.py` | One more file to discover (rounding error in 33-file package) |
| **C. Inline in `cli_handler.handle_orchestrator_context`** | No library reuse; handler does the work itself | Smallest diff | Breaks established pattern (every other handler delegates to a sibling module); domain logic untestable without the argparse harness; second consumer (dashboard, MCP) would have to re-implement |
| **D. Lazy-eval / memoization** | Aggregator caches results across calls within a session | Theoretical amortization | No second caller exists in the prompt; orchestrator agent process exits at end-of-round (no in-process repeat); cache invalidation problem (state mutated between rounds); rejected |

**Recommendation**: **B** — new dedicated module. Choose `orchestrator_context.py` if scope is "what the orchestrator prompt consumes," or `round_context.py` if scope is "what describes a round" and there's intent for other consumers. Spec to choose name.

### JSON shape

| | Description | Pros | Cons |
|---|---|---|---|
| **E. Flat JSON** | One top-level dict with all fields | Shortest access expressions (`payload["hot_files"]`); simplest jq | Field-name collisions across sources (e.g., `round_history` in state vs `round_history_notes` in strategy); provenance lost; harder to evolve |
| **F. Nested JSON** | `{version, state: {...}, strategy: {...}, escalations: {unresolved: [...]}, session_plan: {...}}` | Matches `_emit_json` versioned-envelope; matches `handle_status`'s nested payload precedent (`cli_handler.py:286-292`); preserves provenance; new fields can't collide across sources; 1:1 carry-over of orchestrator's existing mental model | Two-level access in prompt pseudocode (marginal token cost) |
| **G. Streaming NDJSON** | Multi-line tool output | Useful for large append-only logs | Wrong tool for snapshot; forces orchestrator to parse multiple lines; adds prompt overhead |

**Recommendation**: **F** — nested per-source sub-objects. Preserves provenance, matches the existing `_emit_json` versioned-envelope and `handle_status` nested-payload precedent, and minimizes prompt-rewrite churn since the orchestrator already consumes these as separate units.

## Adversarial Review

### Failure modes and edge cases

- **The "6–8 inline reads" framing is misleading.** Most state-file reads in `orchestrator-round.md` are already structured Python calls (`load_state`, `load_strategy`, `events.read_events`), not raw `Read`-tool invocations. The truly inline `Read`-tool reads are: `escalations.jsonl` (line-by-line) plus session plan markdown plus per-feature `spec.md`/`plan.md`. The first two are aggregable; the last is conditional and per-feature. Adjust the ROI claim accordingly.
- **Per-feature `spec.md` / `plan.md` reads dominate variable-cost rounds.** When unresolved escalations exist (Step 0d, capped at 5 per round), the orchestrator does up to 5 × 2 = 10 `Read`-tool calls on lifecycle markdown. The proposed aggregator does NOT cover these (per the recommended scope). On rounds *without* escalations the inline-read cost is much smaller than the worst-case ~500–800 tokens cited in the ticket.
- **Centralized failure surface.** Today, malformed `escalations.jsonl` impacts only Step 0 (`orchestrator-round.md:48-50` handles per-line malformed JSON). With the aggregator, *one* unhandled exception or `json.loads` failure produces an error string that the orchestrator must reason about. Combined with `--dangerously-skip-permissions`, a misfire that emits Python tracebacks to stdout corrupts the prompt's expected JSON shape.
- **`round_history_notes` is unbounded** (`strategy.py:33`). After many rounds it can dominate the JSON. The aggregator must cap or truncate; spec must specify the cap.
- **No mid-round resume to break.** Each round spawns a fresh orchestrator agent (`runner.py:1597-1631`). The new aggregator just re-runs at round start each spawn — Resume is not a regression risk. But this also means there's no test infrastructure that would catch a rewritten-prompt divergence at restart.
- **Subprocess vs in-process mismatch.** The orchestrator-round prompt's existing pattern is in-process Python imports from `orchestrator_io.py` (`orchestrator-round.md:36-66`). Adding a `cortex overnight orchestrator-context` *subprocess* invocation introduces a Bash tool-call dependency where the existing flow was all-Python. This is a regression in the "thin orchestrator" contract and adds a new permission-grant requirement Bash needs but Python doesn't (in skip-permissions mode this is moot but it's still an extra dependency).

### Security concerns

- **Path validation parity**: The new handler must use `session_validation.validate_session_id` and `session_validation.resolve_session_dir` (`cli_handler.py:329-343`) for any user-supplied session-id input. Prevents path-traversal in the session directory.
- **Stdout discipline**: The aggregator must guarantee no `print(...)` leaks from `load_state` / `load_strategy` / escalations parsing. `load_strategy` swallows errors silently (`strategy.py:50-63`); other helpers may not. All warnings/errors must route to stderr or the orchestrator will see them mixed with JSON.

### Assumptions that may not hold

- **"Distribution Option 1 (CLI subcommand) is the right shape."** The orchestrator agent is already a Python-running agent that imports library functions. The smallest, most-aligned design may be **"Option 0"**: just add the aggregator function to a module and call it in-process (which is what the orchestrator already does for `load_state` / `load_strategy`). The CLI subcommand adds subprocess overhead, stdout/stderr discipline concerns, and a Bash-tool-call dependency, all to deliver something the in-process path could deliver without those costs. **The CLI shape is required if and only if a non-Python consumer (dashboard, MCP, shell) needs the same data.** This is the most consequential challenge to the locked Distribution decision — see Open Questions.
- **"Schema-versioning is enforced downstream."** `_emit_json` emits a `version` field, but no consumer currently checks it before reading payload fields. Without enforcement (a min-version assert in the orchestrator prompt or in tests), the version field is theater.
- **"Test pattern can mirror `tests/test_map_results.py`."** That file is 66 lines and tests post-round write mappings — wrong template for a CLI handler. Use `tests/test_cli_overnight_format_json.py` for stdout-isolation testing.

### ROI risk

- **Direct API-cost savings are negligible.** 300–500 tokens × 50–100 rounds/year = 15k–50k tokens/year. At cached Sonnet 4.7 rates (~$0.003/1k input), that's $0.045–$0.15/year. At uncached Opus rates, ~$1–$4/year. The bet has to be on **agent-attention quality** (fewer tool calls = better focus), which 104's instrumentation does not directly measure.
- **JSON output token cost may exceed savings.** If the aggregated JSON contains state (10 features × 6 fields ≈ 600 tokens), strategy, session plan markdown (500–1500 tokens), and 5 escalations (~250 tokens), the total is ~1500–2500 tokens — *more* than the inline-read tokens it replaces. Spec must define an explicit JSON-size budget (e.g., 500 tokens max) and validate at test time.
- **Cold-start subprocess overhead**: ~70–200ms per `cortex overnight orchestrator-context` invocation. Negligible absolutely (10–20s/year cumulative) but it's a real cost the in-process path avoids.
- **JSON-shape documentation in the prompt**: the rewritten orchestrator-round.md will need to document the JSON schema for the agent. That schema doc may itself be 200–400 tokens, eating most of the savings.

### Recommended mitigations

1. **Pre-ship 104 measurement.** Honor the ticket's own gating: use 104's aggregator on a recent overnight session to measure actual round-startup token cost *before* merging this work. Decide a numeric savings threshold (e.g., ≥150 tokens average) and ship only if cleared.
2. **Cap and truncate aggressively.** Truncate `round_history_notes` to last 5 entries; truncate or extract-only-batch-assignments from session plan markdown; explicit JSON-size budget asserted in tests.
3. **Re-export through `orchestrator_io.py`.** Mandatory per requirements.
4. **Stdout-discipline test.** Assert: (a) stdout is exactly one line of valid JSON; (b) all warnings/errors route to stderr; (c) malformed input produces `{"version", "error"}` JSON (not a Python traceback) and a non-zero exit code.
5. **Hidden subcommand**: consider `argparse.SUPPRESS` to keep `cortex overnight orchestrator-context` out of user-facing `--help` (it is an agent-internal helper, not an operator verb).
6. **Path validation**: parity with `handle_status`'s validation.
7. **Centralized-chokepoint fallback**: spec must either define a fallback (e.g., the prompt retains inline-read pseudocode behind an `if-CLI-fails` branch) or explicitly accept the chokepoint risk.

## Open Questions

1. **(RESOLVED 2026-04-28)** Aggregator shape: in-process function only, CLI subcommand only, hybrid, or drop the ticket? **User chose Option 0: in-process function only.** Drop the CLI subcommand from scope. Add `aggregate_round_context()` to a new module (`cortex_command/overnight/orchestrator_context.py` or `round_context.py` — see Q2) and re-export through `orchestrator_io.py`. The orchestrator-round prompt imports and calls it directly, same pattern as `load_state` / `load_strategy` today. Backlog item Scope section needs amending to drop the "new CLI `bin/orchestrator-context`" line and reword to "new module function exposed through `orchestrator_io.py`." Sections of this research that reference CLI handlers, `_emit_json`, subcommand registration, stdout-discipline tests, and `--help` visibility are now non-applicable; the corresponding test/handler wrappers are out of scope.
2. **Module naming** (deferred to Spec): `orchestrator_context.py` (orchestrator-prompt-facing) vs `round_context.py` (round-scoped, more general). Default proposal under Option 0: `orchestrator_context.py` since the only consumer is the orchestrator prompt.
3. **Aggregated-dict size budget** (deferred to Spec; reframed from "JSON-size budget" since there is no longer JSON serialization): what is the maximum acceptable in-memory-dict size for the aggregator's return value when the orchestrator prompt receives it? Resolution method: measure existing inline-read cost via 104's aggregator on a real overnight session, then set a budget that is a meaningful improvement.
4. **`round_history_notes` truncation policy** (deferred to Spec): cap at last N entries? Drop entirely and let the orchestrator request it separately if needed? Default proposal: "last 5 entries."
5. **Session plan markdown handling** (deferred to Spec): pass through verbatim (risks bloat), or extract only the batch-assignment subsection (risks losing context the orchestrator needs)? Resolution method: spec to choose after looking at a real session-plan.md.
6. **Schema-version policy** (deferred to Spec; reframed): should the aggregator's returned dict include a `schema_version` key the orchestrator prompt asserts before reading fields? Recommended: yes, with bump-on-breaking-change policy. (No longer about JSON envelope versioning since there is no JSON envelope.)
7. **(MOOT under Option 0)** `--help` visibility was relevant only for the CLI subcommand. With no CLI subcommand, this question dissolves.
8. **Fallback path on aggregator failure** (deferred to Spec): should the orchestrator-round prompt retain inline-read pseudocode behind an `except` branch around the aggregator call, or accept the centralized-chokepoint risk? Under Option 0, exceptions raise in-process and the orchestrator's existing Python error-handling pattern applies (see `orchestrator-round.md:48-50` for the existing per-line malformed-JSON tolerance). Resolution method: spec to choose; if accepted-as-chokepoint, document the failure mode explicitly.
9. **ROI confirmation criterion** (deferred to Spec): what numeric threshold and what session-of-record does post-ship validation require? (Per ticket scope and Clarify open question.) Resolution method: spec to define after Q3 settles the budget.
