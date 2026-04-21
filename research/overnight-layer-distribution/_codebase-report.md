# Codebase Analysis: overnight layer boundaries

*Produced by codebase research agent. Raw findings; not yet synthesized into research.md.*

## 1. What's in the Overnight Bundle?

The overnight bundle — files that must ship together for autonomous execution:

**Core orchestration engine:**
- `claude/overnight/runner.sh` — main orchestrator loop (600+ lines), entry point that spawns orchestrator agents, invokes batch_runner, handles circuit breakers, integrates with git
- `claude/overnight/*.py` (~10K LOC): state.py, events.py, backlog.py, plan.py, strategy.py, batch_runner.py, brain.py, integration_recovery.py, interrupt.py, deferral.py, throttle.py, report.py, status.py, map_results.py
- `claude/overnight/prompts/*.md` (3 prompt files): orchestrator-round.md, batch-brain.md, repair-agent.md

**Pipeline/dispatch subsystem:**
- `claude/pipeline/dispatch.py` — agent spawning, SDK orchestration, tool allowlist enforcement
- `claude/pipeline/*.py` (~5K LOC): merge.py, conflict.py, merge_recovery.py, review_dispatch.py, events.py
- `claude/pipeline/prompts/*.md`: implement.md, review.md

**Shared utilities & state:**
- `claude/common.py` — imported by 15+ modules
- `claude/settings.json` — deployed to `~/.claude/settings.json`
- Python venv (uv.lock, pyproject.toml)

**Supporting tooling in bin/:**
- `bin/overnight-start`, `bin/overnight-schedule`, `bin/overnight-status`
- `backlog/*.py` — backlog scanning/scoring

**State directories written to working repo:**
- `lifecycle/overnight-state.json` — session state, atomic writes
- `lifecycle/sessions/{id}/overnight-events.log`, `overnight-strategy.json`, `batch-{N}-results.json`
- `lifecycle/{feature}/learnings/orchestrator-note.md`
- `lifecycle/escalations.jsonl`
- `lifecycle/morning-report.md`

**Why bundled:** The runner directly imports and calls modules in `claude.overnight` and `claude.pipeline`; the orchestrator prompt has hardcoded references to `overnight-strategy.json` and `escalations.jsonl` paths; batch_runner expects pipeline artifacts to exist in specific locations.

---

## 2. Plugin-Splittable Skills and Hooks

**Skills that can run standalone (no runner dependency):**
- `skills/lifecycle` — feature lifecycle state machine. Safe as optional plugin.
- `skills/commit`, `skills/pr`, `skills/retro`, `skills/dev`, `skills/fresh`, `skills/diagnose`, `skills/evolve`
- `skills/research`, `skills/discovery`, `skills/refine`
- `skills/backlog`, `skills/requirements`

**Skills that CAN'T split (runner requires):**
- `skills/overnight` — invokes runner.sh and orchestrator
- `skills/critical-review`, `skills/morning-review` — directly call `claude.overnight.report` and state modules. Re-invoked by the runner.

**Hooks that must ship with overnight:**
- `hooks/cortex-scan-lifecycle.sh` — SessionStart hook. Injects `LIFECYCLE_SESSION_ID` that runner.sh exports.
- `hooks/cortex-validate-commit.sh` — worker agents dispatch commits; hook validates format.
- `hooks/cortex-tool-failure-tracker.sh` — logs tool failures.
- `hooks/cortex-notify.sh` — desktop notifications for runner events.

**Hooks that can split:**
- `cortex-skill-edit-advisor.sh`, `cortex-permission-audit-log.sh`, `cortex-output-filter.sh`, `cortex-cleanup-session.sh` (optional), `cortex-sync-permissions.py` (optional)

---

## 3. Runtime Dependencies (runner → other components)

The overnight runner directly calls:

1. **Python modules at key gates:**
   - `python3 -m claude.overnight.interrupt` — startup recovery (line ~570)
   - `python3 -m claude.overnight.batch_runner` — feature execution (line ~716)
   - `python3 -m claude.overnight.map_results` — state updates (line ~768)
   - `python3 -m claude.overnight.integration_recovery` — test-gate repair (line ~919)
   - `python3 -m claude.overnight.report` — morning report (line ~512)

2. **Inline Python snippets** (lines 51-296, scattered): state reads, feature counting, prompt filling, auth resolution.

3. **Bash subprocesses:** `claude -p <prompt>`, `git`, `gh`

4. **Hook invocation:** `~/.claude/notify.sh` (lines 522, 675, 750, 800, 1012)

**Which skills the runner's agents invoke:** None. Worker agents (dispatch.py) have `_ALLOWED_TOOLS = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]` — skills never run inside workers.

---

## 4. Shared State Contract

| Path | Ownership | R/W | Notes |
|------|-----------|-----|-------|
| `lifecycle/overnight-state.json` | runner.sh, state.py | RW | Core session state |
| `lifecycle/sessions/{id}/` | runner.sh | W | Per-session dir |
| `lifecycle/{feature}/spec.md` | Lifecycle skill | R | Validation input |
| `lifecycle/{feature}/plan.md` | Lifecycle skill + orchestrator | RW | Plan artifact |
| `lifecycle/{feature}/learnings/orchestrator-note.md` | orchestrator | W | Feedback loop |
| `lifecycle/{feature}/agent-activity.jsonl` | dispatch.py | W | Breadcrumbs |
| `lifecycle/{feature}/events.log` | batch_runner.py | W | Phase transitions |
| `lifecycle/escalations.jsonl` | deferral.py | W | Worker questions |
| `backlog/NNN-slug.md` | User + overnight | RW | Feature metadata |
| `backlog/index.json`, `index.md` | backlog/generate_index.py | W | Regenerated each session |
| `lifecycle/morning-report.md` | report.py | W | Final summary |
| `.git/refs/heads/{integration_branch}` | runner.sh + git | RW | Integration branch |

## 5. Host Touchpoints

| Path | Notes |
|------|-------|
| `~/.claude/settings.json` | Copied, not symlinked; `/setup-merge` merges updates |
| `~/.claude/settings.local.json` | Per-machine overrides |
| `~/.claude/hooks/*` | Symlinked; referenced literally in settings.json |
| `~/.claude/notify.sh` | Symlink to `hooks/cortex-notify.sh` |
| `~/.claude/rules/*` | Symlinks |
| `~/.claude/reference/*` | Symlinks |
| `~/.claude/skills/*` | Directory symlinks (bug: see issue #14836) |
| `~/.local/bin/overnight-{start,schedule,status}` | Symlinks |
| `~/.local/bin/{update-item, create-backlog-item, generate-backlog-index, jcc, ...}` | Symlinks |
| `ANTHROPIC_API_KEY` env var | Exported by runner |
| `REPO_ROOT/.venv/bin/activate` | Must exist before runner starts |
| `CORTEX_COMMAND_ROOT` env var | Points to repo root |

**Hardcoded path assumptions:**
- `runner.sh` reads `$REPO_ROOT/.venv/bin/activate` (line 39)
- `runner.sh` reads `$REPO_ROOT/claude/overnight/prompts/orchestrator-round.md` (line 97)
- `runner.sh` calls `python3 -m claude.overnight.*` — requires `PYTHONPATH=$REPO_ROOT`
- `settings.json` references `~/.claude/notify.sh` literally
- `dispatch.py` loads `.claude/settings.json` to read `apiKeyHelper` (line ~42)
- `skills/overnight/SKILL.md` invokes `$CORTEX_COMMAND_ROOT/.venv/bin/python3 -m claude.overnight.*` (line 46)

---

## 6. Existing Modularity Seams

**Can already run independently:**
1. **Lifecycle skill + state machine** — fully standalone.
2. **Individual skills** (commit, pr, backlog, research, discovery, etc.)
3. **Dashboard** — read-only observer; reads state files on 1-2s cadence. Can run on separate machine.
4. **Backlog system** — generate_index.py, update tools.
5. **Commit message validation** — runs on every commit.

**Cannot split:**
- overnight runner + orchestrator prompt + pipeline dispatch — tightly coupled
- overnight skill + runner — ship together

---

## 7. Packaging Constraints (what would block MCP/CLI packaging)

1. **Hardcoded path expansion** in ~20 inline Python snippets. Runner populates paths from state file fields and uses them in shell subcommands.
2. **Process group management** (lines 644-650, 714-730). `set -m` gives child processes their own PGID for watchdog-kill.
3. **Symlink architecture** — all config points to `~/.claude/` or `~/.local/bin/`. A hosted version would need fake filesystem layer or config-as-data.
4. **Signal handling** (trap cleanup SIGINT SIGTERM SIGHUP, line 526). Graceful shutdown writes state atomically.
5. **Atomic tempfile + os.replace()** used in 15+ places. RPC wrapper must preserve guarantee.
6. **Settings.json deep-merge** in `/setup-merge`. A plugin distribution mechanism would need equivalent logic.
7. **Prompt template substitution** (line 379-393). Runner reads `orchestrator-round.md` and replaces `{state_path}`, `{plan_path}`, etc. with absolute paths. MCP server would need to load prompts from package resources and inject paths before dispatching.

**Result: A packaging effort would not be a simple symlink replacement.** Refactoring needed:
1. Extract core orchestration into a library with explicit in/out contracts
2. Implement RPC boundary (runner-as-service)
3. Move prompts from template files to data / package resources
4. Decouple signal handling from process lifecycle
5. Provide mock `~/.claude/` layer or structure all config as data

---

## Summary

- **Overnight bundle**: 92 files, 5.3M, inseparable.
- **Plugin-safe components**: 12 skills; 5+ hooks — all independent of overnight.
- **Runtime invocations from runner**: all in-tree Python modules, no skill re-invocation during execution.
- **State locations**: `lifecycle/` (user repo), `~/.claude/` (config), `~/.local/bin/` (CLI).
- **Key constraint**: Tight coupling via hardcoded paths, process groups, atomic file ops, prompt substitution, signal handling.
