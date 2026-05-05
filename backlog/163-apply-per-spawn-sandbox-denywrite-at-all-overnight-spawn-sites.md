---
schema_version: "1"
uuid: 759eb26e-55fd-4cc6-9528-f7c84845e8e2
title: "Apply per-spawn sandbox.filesystem.denyWrite at all overnight spawn sites"
status: ready
priority: critical
type: feature
parent: 162
tags: [overnight-runner, sandbox, os-enforcement, orchestrator-worktree-escape, pipeline, cross-repo, docs]
areas: [overnight-runner, pipeline]
created: 2026-05-04
updated: 2026-05-04
lifecycle_slug: null
lifecycle_phase: null
session_id: null
blocks: []
blocked-by: []
discovery_source: research/sandbox-overnight-child-agents/research.md
---

# Apply per-spawn sandbox.filesystem.denyWrite at all overnight spawn sites

## Context from discovery

This ticket is the **load-bearing** sandbox-enforcement change. It applies the documented `sandbox.filesystem.denyWrite` shape at both overnight spawn sites and fixes two compounded silent-no-op bugs in the existing per-feature dispatch path. Replaces the reverted ticket-128 git-pre-commit-hook approach for the Bash-tool-routed subset of its threat-model coverage.

### Problem 1 — orchestrator spawn has no per-spawn sandbox

The overnight orchestrator is spawned at `cortex_command/overnight/runner.py:905-922` via direct `subprocess.Popen([claude_path, "-p", filled_prompt, "--dangerously-skip-permissions", "--max-turns", N, "--output-format=json"], env={**os.environ, "CORTEX_RUNNER_CHILD": "1"})`. The spawn passes **no `--settings`**, no `--add-dir`, no `cwd` override — it runs from the runner's CWD (the home repo). Inherited sandbox config is the user-global `~/.claude/settings.json`'s `sandbox.filesystem.allowWrite` (`~/cortex-command/lifecycle/sessions/`, `~/.cache/uv`), which provides no protection for the home repo's `.git/`. This is the spawn that exhibited session-1708's `cd $REPO_ROOT && git commit` escape.

### Problem 2 — per-feature dispatch granular shape is a silent no-op

`cortex_command/pipeline/dispatch.py:546` writes `{"sandbox": {"write": {"allowOnly": _write_allowlist}}}` — the granular shape. Per documentary verification of the open-source [`@anthropic-ai/sandbox-runtime`](https://github.com/anthropic-experimental/sandbox-runtime), the package consumes ONLY the simplified shape `filesystem.{allowRead, denyRead, allowWrite, denyWrite}`. The granular `write.allowOnly` shape is the runtime's internal IR after merging permissions rules, NOT a recognized settings input. Existing `tests/test_dispatch.py:306-637` only verifies the JSON is *written*, not that enforcement *applies*. **Conclusion**: per-feature sandbox narrowing is structurally a silent no-op today.

### Problem 3 — cross-repo allowlist inversion

`cortex_command/overnight/feature_executor.py:603` passes `integration_base_path=Path.cwd()` to `dispatch_task`. For a cross-repo feature, `Path.cwd()` is the home repo (the runner runs from home-repo cwd). `dispatch.py:540-549` unconditionally appends `integration_base_path` to `_write_allowlist`. **Net effect**: a cross-repo dispatch's write allowlist includes the home repo, granting cross-repo agents write access to the home repo's working tree — the inverse of multi-repo isolation intent.

## Findings from discovery

- **Schema is the documented simplified shape** `sandbox.filesystem.denyWrite` / `allowWrite` (DR-1 revision 3). Granular `write.{allowOnly,denyWithinAllow}` is the runtime's internal IR only, not a settings input.
- **Distribution layer is per-spawn `--settings <tempfile>`** (DR-2). Plugin-shipped settings cannot carry sandbox config (plugin manifest only accepts `agent`/`subagentStatusLine` keys); managed-settings is too heavyweight.
- **No `--sandbox` CLI flag exists** in v2.1.126 — activation is `sandbox.enabled: true` in the JSON.
- **denyWrite > allowWrite precedence** is documented; the per-spawn deny correctly overrides cortex-init's user-scope allowWrite across the merge.
- **Cross-repo enumeration in scope** (DR-3, R4-B from critical review). V1 enumerates `state.features.values()`, filters by non-None `repo_path`, resolves each cross-repo's default branch via `git symbolic-ref refs/remotes/origin/HEAD` (or fallback to reading `.git/HEAD`), caches in state.

## Value

Catches the session-1708 escape vector documented in `lifecycle/install-pre-commit-hook-rejecting-main-commits-during-overnight-sessions/spec.md:5` — orchestrator's `cd $REPO_ROOT && git commit` from Bash tool — at the OS sandbox layer, replacing ticket-128's reverted git-pre-commit-hook approach for the Bash-tool-routed subset of its threat-model coverage. Simultaneously fixes two latent bugs in the per-feature dispatch path (silent-no-op shape; cross-repo allowlist inversion) so per-feature spawns receive real kernel-level write isolation. Citations: `cortex_command/overnight/runner.py:905-922` (no per-spawn sandbox today), `cortex_command/pipeline/dispatch.py:546` (silent-no-op shape), `cortex_command/overnight/feature_executor.py:603` (cross-repo allowlist inversion).

## Threat-model boundary (explicit, per critical-review R2-C)

This ticket covers **Bash-tool-routed escapes only**. Out of scope:
- Write-tool calls to home-repo paths including `.git/refs/heads/*`
- Edit-tool calls to tracked working-tree files
- MCP-server-routed subprocess writes
- Plumbing-level ref mutation routed via Write tool

Within that boundary, this ticket directly addresses session-1708's vector + per-cross-repo main mutations + per-feature spawns' real (vs illusory) sandbox narrowing.

## Acceptance criteria (high-level — refined in spec phase)

- **Orchestrator spawn**: A per-spawn settings.json file is constructed containing `sandbox.enabled: true`, `sandbox.filesystem.denyWrite` for `<home_repo>/.git/refs/heads/main`, `<home_repo>/.git/HEAD`, `<home_repo>/.git/packed-refs`, plus per-cross-repo entries enumerated from `state.features[*].repo_path`. Passed as `--settings <tempfile>` to the orchestrator subprocess at `runner.py:905`. Tempfile lifecycle handled.
- **Per-feature dispatch shape conversion**: `dispatch.py:546` converted from `{"sandbox": {"write": {"allowOnly": ...}}}` to documented `{"sandbox": {"enabled": true, "filesystem": {"allowWrite": ...}}}`.
- **Cross-repo allowlist fix**: `feature_executor.py:603` uses `integration_worktrees[repo_path_str]` (cross-repo's integration worktree) when `repo_path` is non-None; falls back to `Path.cwd()` only for same-repo features.
- **failIfUnavailable**: per-spawn JSON includes `sandbox.failIfUnavailable: true`.
- **Empirical acceptance tests**: kernel-layer EPERM verification for both spawn sites — orchestrator's Bash tool attempting to write to a denied path, and a per-feature dispatch's write to a path outside its allowlist. Tests run under `just test`.
- **Test scaffolding**: `tests/test_dispatch.py` and a new `tests/test_runner_sandbox.py` (or equivalent) cover both shape correctness AND enforcement (not just JSON-write verification).
- **Docs**: `docs/overnight-operations.md` updated with per-spawn sandbox enforcement section, explicit threat-model boundary (Bash-only; Write/Edit/MCP bypass per [#29048]), operational story when commits fail under sandbox denial. `docs/pipeline.md` updated to document the simplified `sandbox.filesystem.{allowWrite,denyWrite}` shape used at `dispatch.py` post-conversion. Cross-references between docs per CLAUDE.md guidance ("update the owning doc and link from the others rather than duplicating content").
- **Pre-flight (recommended, non-blocking)**: a human runs the empirical test in a clean (non-sandboxed) terminal before implementation begins, to bound mechanism-flip risk early. Documented in spec phase.

## Research context

Full research at `research/sandbox-overnight-child-agents/research.md`. Particularly relevant: DR-1 (schema), DR-2 (distribution), DR-3 (V1 scope including cross-repo), DR-6 (per-feature audit + two compounded bugs), DR-7 (acceptance test), critical review R1-A1 + R4-B + R2-C.
