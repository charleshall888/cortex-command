# Plan: docs-audit

## Overview

Eight independent documentation fixes executed in parallel — one task per doc file. Each task reads the relevant source files first, then makes targeted in-place edits. No new files are created; no source code changes. All tasks can run concurrently since they touch separate files.

## Tasks

### Task 1: Fix skills-reference.md (R1, R2, R3)
- **Files**: `docs/skills-reference.md`
- **What**: Remove the non-existent `serena-memory` skill entry, fix the skill count from 30 to 29, and add brief usage guidance explaining the relationship between `/dev`, `/lifecycle`, and `/overnight`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The file opens with a claim of "all 30 skills". Search for `serena-memory` and remove the full row. For usage guidance, read `skills/dev/SKILL.md`, `skills/lifecycle/SKILL.md`, and `skills/overnight/SKILL.md` to understand each skill's trigger phrases and routing. Add a brief section (or inline note near these three entries) that distinguishes: `/dev` is the general entry point for new work (routes automatically); `/lifecycle` is invoked directly when you already know the feature and want lifecycle phases; `/overnight` is invoked to run an existing plan batch. Authoritative count: `ls skills/*/SKILL.md | wc -l`.
- **Verification**: `grep -c "serena-memory" docs/skills-reference.md` returns 0; opening count matches `ls skills/*/SKILL.md | wc -l`; usage guidance section present near the three overlapping skill entries.
- **Status**: [ ] pending

### Task 2: Fix pipeline.md (R4, R5, R6)
- **Files**: `docs/pipeline.md`
- **What**: Add `conflict.py` and `merge_recovery.py` to the module table, explain the two-level plan structure (master-plan.md vs. per-feature plan.md), and correct the `revert_merge()` recovery note to clarify it targets `base_branch` (main by default).
- **Depends on**: none
- **Complexity**: simple
- **Context**: Read `claude/pipeline/conflict.py` header (first 15 lines): handles merge conflict classification and repair agent dispatch; provides `dispatch_repair_agent()`. Read `claude/pipeline/merge_recovery.py` header: post-merge test-failure recovery loop; orchestrates flaky guard + up to two code-repair attempts with model escalation (sonnet → opus). Add these as rows in the module table. For plan structure: `master-plan.md` is the top-level batch plan produced by `/overnight`; it contains all features for the session. Per-feature `plan.md` lives in `lifecycle/{slug}/plan.md` and contains the task breakdown for a single feature. `parser.py` reads both. Add a brief "Plan Structure" subsection. For `revert_merge()`: the function lives in `claude/pipeline/merge.py` at line 335 (not `merge_recovery.py`). Its signature is `revert_merge(feature: str, base_branch: str = "main", repo_path=None)` — it performs `git revert -m 1 HEAD` on `base_branch` (defaults to `main`), not on the integration branch. Add a note clarifying this default. Authoritative count excludes `__init__.py`: `ls claude/pipeline/*.py | grep -v __init__ | wc -l` (currently 10).
- **Verification**: Module table row count matches `ls claude/pipeline/*.py | grep -v __init__ | wc -l`; `conflict.py` and `merge_recovery.py` present in table with descriptions; plan structure explanation present; `revert_merge()` note names `merge.py` as the source file and clarifies default target branch is `main`.
- **Status**: [ ] pending

### Task 3: Fix agentic-layer.md (R7, R8, R9)
- **Files**: `docs/agentic-layer.md`
- **What**: Add a Hooks Architecture section covering event types, JSON permissionDecision output semantics, stdin contracts, ordering, and failure behavior; integrate hooks into the workflow narrative at their trigger points; clarify `/dev` routing logic.
- **Depends on**: none
- **Complexity**: complex
- **Context**: Hooks live in two directories: `hooks/` (user-facing hooks like `validate-commit.sh`, `scan-lifecycle.sh`) and `claude/hooks/` (internal hooks like `setup-github-pat.sh`). Read `claude/settings.json` to find the full list of registered hook events. Confirmed output contract (from `hooks/validate-commit.sh` lines 95–111): hooks write JSON `{"permissionDecision": "allow"|"deny", "permissionDecisionReason": "..."}` to stdout; exit code is always 0. Do NOT document "exit 2 = block" — hooks in this project block via JSON output. Some hooks read stdin (e.g., `claude/hooks/sync-permissions.py`, `claude/hooks/worktree-create.sh`) — document this stdin contract in the section. Place the new Hooks Architecture section after the existing hooks table (not as a top-level section — add it as a subsection under the existing "Hooks" or "System Components" heading to preserve the current heading hierarchy). For workflow narrative integration: find the workflow diagram descriptions and add inline annotations like "(PreToolUse hook: validate-commit fires here)" at the git commit step and "(SessionStart hook: scan-lifecycle fires here)" at session start. For `/dev` routing: read `skills/dev/SKILL.md` — the routing criteria are documented there. Summarize as a decision table or 1 paragraph in `agentic-layer.md`'s existing `/dev` entry in the skill table.
- **Verification**: Hooks Architecture subsection exists under the existing Hooks section; section covers event types, JSON output format (not exit codes), stdin contract, ordering, and failure behavior; workflow narrative has inline hook annotations at commit and session-start steps; `/dev` routing entry explains criteria for routing to lifecycle/discovery/backlog/direct.
- **Status**: [ ] pending

### Task 4: Fix overnight.md (R10, R11, R12, R13)
- **Files**: `docs/overnight.md`
- **What**: Complete the module table to match all 16 non-init .py files; document all scenarios that produce `running` status (not just crash); add a one-sentence rationale for the 3-5 features recommendation; clarify how concurrency interacts with git conflict detection.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Run `ls claude/overnight/*.py | grep -v __init__` to get the full 16-file list. Compare against the existing module table to find missing entries. For `running` status: read `claude/overnight/batch_plan.py` around lines 132 and 169 to understand the non-crash cases — `running` is set when the round ends with features still in `pending` or `executing` state (normal round-end path, not just crash). Enumerate all 3 ways `running` occurs: (1) crash with no graceful shutdown — status is stale; (2) normal round end while feature was still executing — feature was mid-execution when the batch closed; (3) orchestrator prompt reads pending features at round start and marks them running. For 3-5 features rationale: the tradeoff is context budget (too many features overflows a single agent's context window) vs. recovery cost (too few makes sessions inefficient). Add this as one sentence inline. For conflict detection: read `claude/pipeline/conflict.py` — conflicts are detected at merge time (not dispatch time); unresolvable conflicts trigger a pause; `dispatch_repair_agent()` is called for complex cases. Authoritative count: `ls claude/overnight/*.py | grep -v __init__ | wc -l` (currently 16).
- **Verification**: Module table row count matches `ls claude/overnight/*.py | grep -v __init__ | wc -l`; `running` status section covers at least the crash and normal-round-end scenarios; rationale sentence present inline with 3-5 recommendation; concurrency section names merge time as the detection point and distinguishes pause vs. repair-agent dispatch.
- **Status**: [ ] pending

### Task 5: Fix interactive-phases.md (R14, R15, R16)
- **Files**: `docs/interactive-phases.md`
- **What**: Remove references to `skills/refine/references/` and `skills/interview/references/` (non-existent); clarify whether manual tier escalation is persisted to backlog YAML; document the stale artifact limitation in the readiness gate.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Search the file for `skills/refine/references/` and `skills/interview/references/` — remove those references or replace with the correct path if an equivalent exists. For tier escalation persistence: read `skills/lifecycle/SKILL.md` (the Complexity Override section) — manual escalation appends a `complexity_override` event to `events.log` but does NOT update backlog YAML (the backlog `complexity:` field is set only at Clarify time and not updated by mid-lifecycle overrides). Document this explicitly. For stale artifacts: the readiness gate checks file existence only — a spec written months ago passes the gate and goes to overnight. Document as a known limitation with workaround: delete or rename the stale artifact and re-run `/refine` to regenerate it.
- **Verification**: No reference to `skills/refine/references/` or `skills/interview/references/` in the file; tier escalation section explicitly states backlog YAML is NOT updated by mid-lifecycle overrides; stale artifact limitation documented with workaround.
- **Status**: [ ] pending

### Task 6: Fix backlog.md (R17, R18, R19)
- **Files**: `docs/backlog.md`
- **What**: Move the readiness gate "file existence, not quality" callout to the Gate section; enumerate all 7 TERMINAL_STATUSES from `claude/common.py`; add a concrete thin-spec example.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The canonical TERMINAL_STATUSES are in `claude/common.py` as a frozenset: `{"complete", "abandoned", "done", "resolved", "wontfix", "won't-do", "wont-do"}`. The existing doc lists only 5 — update to all 7 and cite `claude/common.py`. Note: `common.py` line 38 has a comment saying `overnight/backlog.py` defines its own 5-value tuple — this comment is stale (backlog.py now imports from `claude.common`); document the canonical 7-value list from `common.py` and do not reproduce the stale comment. For the readiness gate callout: find it in Best Practices and move (or duplicate with a cross-reference) to the Gate section. For the thin-spec example: read `claude/overnight/backlog.py` around the spec-sufficiency logic to understand what triggers a deferral. A thin spec might look like a spec.md with only a one-line problem statement and no Requirements section — show the actual content and explain why overnight defers (the plan agent has no verifiable criteria to check against).
- **Verification**: Readiness gate callout appears in the Gate section; TERMINAL_STATUSES list has all 7 values and cites `claude/common.py`; thin spec example shows actual content (not an abstract description); the stale `common.py` comment is not reproduced in the doc.
- **Status**: [ ] pending

### Task 7: Fix setup.md (R20, R21, R22)
- **Files**: `docs/setup.md`
- **What**: Fix the Windows Terminal section nesting under the macOS heading; clarify that `caffeinate-monitor.sh` is both a symlinked binary AND a launchd service; add a minimal MCP plugin example for `claude/settings.json`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Find the macOS terminal section and the Windows Terminal content nested under it — restructure so each platform has its own heading. For `caffeinate-monitor.sh`: the script lives at `mac/caffeinate-monitor.sh` (confirmed in setup.md lines 128–133). It is both: (1) a symlinked binary at `~/.local/bin/caffeinate-monitor.sh`, and (2) a launchd service registered via `mac/local.caffeinate-monitor.plist` at `~/Library/LaunchAgents/` — it starts automatically at login. The existing setup.md text already covers this (lines 125–133); the task is to make the dual role explicit and unambiguous in the prose explanation. For MCP plugin example: read `claude/settings.json` and find an existing `mcpServers` entry to use as the example. If none exists, use the Claude Code MCP server config format: `"server-name": {"command": "npx", "args": ["-y", "@package/server"]}`.
- **Verification**: Windows Terminal and macOS terminal sections are under separate headings; caffeinate-monitor.sh dual role (symlinked binary + launchd service, auto-starts at login) is explicitly described; MCP plugin example is a concrete JSON snippet.
- **Status**: [ ] pending

### Task 8: Fix dashboard.md (R23, R24, R25)
- **Files**: `docs/dashboard.md`
- **What**: Clarify whether the dashboard is localhost-only or network-accessible; add key field descriptions for `overnight-state.json` and `overnight-events.log`; document the polling intervals.
- **Depends on**: none
- **Complexity**: simple
- **Context**: HTMX polling: all dashboard sections use `hx-trigger="load, every 5s"` (confirmed in `claude/dashboard/templates/base.html`). Backend polling (from `claude/dashboard/poller.py`): state files every 2s, JSONL events every 1s, backlog every 30s. Total state-change latency: up to 7s (2s backend + 5s HTMX). For deployment: read `claude/dashboard/app.py` and find the uvicorn launch command (the `uvicorn.run(...)` call or CLI invocation) — specifically the `host=` argument. Do NOT use the port-availability check socket at line 173 (`127.0.0.1` there is a pre-launch probe, not the server listen address). Document whether the server binds to `0.0.0.0` (network-accessible) or `127.0.0.1` (localhost-only). For state file schemas: read `claude/overnight/state.py` for the overnight-state.json structure. Key fields include: `status`, `features` (list with id/status/phase), `round`, `started_at`. Read `claude/dashboard/data.py` or any sample events file for the NDJSON event log format: each line is `{"ts": "...", "event": "...", "feature": "..."}`.
- **Verification**: Known Limitations section explicitly states whether server is localhost-only or network-accessible (based on actual `app.py` host binding, not the port-check socket); polling intervals documented (5s HTMX, 2s state files, 1s events, 30s backlog, ~7s total latency); state file schema lists key fields; event log NDJSON format documented.
- **Status**: [ ] pending

## Verification Strategy

After all tasks complete: run `just test` (per `lifecycle.config.md`) to confirm no regressions. Cross-doc consistency pass: verify skill count is consistent between `skills-reference.md` and `agentic-layer.md`; verify pipeline.md and overnight.md module table counts match their respective `grep -v __init__ | wc -l` outputs. Spot-check cross-doc navigation links still resolve.
