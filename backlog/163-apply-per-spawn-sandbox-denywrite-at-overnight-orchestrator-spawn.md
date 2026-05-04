---
schema_version: "1"
uuid: 759eb26e-55fd-4cc6-9528-f7c84845e8e2
title: "Apply per-spawn sandbox.filesystem.denyWrite at overnight orchestrator spawn"
status: ready
priority: critical
type: feature
parent: 162
tags: [overnight-runner, sandbox, os-enforcement, orchestrator-worktree-escape]
areas: [overnight-runner]
created: 2026-05-04
updated: 2026-05-04
lifecycle_slug: null
lifecycle_phase: null
session_id: null
blocks: []
blocked-by: []
discovery_source: research/sandbox-overnight-child-agents/research.md
---

# Apply per-spawn sandbox.filesystem.denyWrite at overnight orchestrator spawn

## Context from discovery

The overnight orchestrator is spawned at `cortex_command/overnight/runner.py:905-922` via direct `subprocess.Popen([claude_path, "-p", filled_prompt, "--dangerously-skip-permissions", "--max-turns", N, "--output-format=json"], env={**os.environ, "CORTEX_RUNNER_CHILD": "1"})`. The spawn passes **no `--settings`**, no `--add-dir`, no `--sandbox`, and no `cwd` override — it runs from the runner's CWD (the home repo). Inherited sandbox config is the user-global `~/.claude/settings.json`'s `sandbox.filesystem.allowWrite` (`~/cortex-command/lifecycle/sessions/`, `~/.cache/uv`), which provides no protection for the home repo's `.git/`.

This is the spawn that exhibited session-1708's `cd $REPO_ROOT && git commit` escape. Per ticket #128's revert rationale, OS-level per-spawn sandbox is the chosen replacement enforcement mechanism.

## Findings from discovery

- **Schema is the documented simplified shape** `sandbox.filesystem.denyWrite` (DR-1 revision 3). Granular `write.denyWithinAllow` is the runtime's internal IR, not a settings input — confirmed by [@anthropic-ai/sandbox-runtime](https://github.com/anthropic-experimental/sandbox-runtime).
- **Distribution layer is per-spawn `--settings <tempfile>`** (DR-2). Plugin-shipped settings cannot carry sandbox config (plugin manifest only accepts `agent`/`subagentStatusLine` keys); managed-settings is too heavyweight.
- **No `--sandbox` CLI flag exists** in v2.1.126 — activation is `sandbox.enabled: true` in the JSON.
- **denyWrite > allowWrite precedence** is documented; the per-spawn deny correctly overrides cortex-init's user-scope allowWrite across the merge.
- **Cross-repo enumeration in scope** (DR-3, R4-B from critical review). V1 enumerates `state.features.values()`, filters by non-None `repo_path`, resolves each cross-repo's default branch via `git symbolic-ref refs/remotes/origin/HEAD` (or fallback to reading `.git/HEAD`), caches in state.

## Value

Catches the session-1708 escape vector documented in `lifecycle/install-pre-commit-hook-rejecting-main-commits-during-overnight-sessions/spec.md:5` — orchestrator's `cd $REPO_ROOT && git commit` from Bash tool — at the OS sandbox layer, replacing ticket-128's reverted git-pre-commit-hook approach for the Bash-tool-routed subset of its threat-model coverage. Citation: `cortex_command/overnight/runner.py:905-922` (the spawn site that lacks per-spawn sandbox today).

## Threat-model boundary (explicit, per critical-review R2-C)

This ticket covers **Bash-tool-routed escapes only**. Out of scope:
- Write-tool calls to home-repo paths including `.git/refs/heads/*`
- Edit-tool calls to tracked working-tree files
- MCP-server-routed subprocess writes
- Plumbing-level ref mutation routed via Write tool

Within that boundary, this ticket directly addresses session-1708's vector + per-cross-repo main mutations.

## Acceptance criteria (high-level — refined in spec phase)

- A per-spawn settings.json file is constructed containing `sandbox.enabled: true`, `sandbox.filesystem.denyWrite` for `<home_repo>/.git/refs/heads/main`, `<home_repo>/.git/HEAD`, `<home_repo>/.git/packed-refs`, plus per-cross-repo entries enumerated from `state.features[*].repo_path`. The file is passed as `--settings <tempfile>` to the orchestrator subprocess at `runner.py:905`.
- The settings.json includes `sandbox.failIfUnavailable: true`.
- Tempfile lifecycle is handled (created before spawn, cleaned up after spawn exits or on runner exit).
- An empirical acceptance test verifies a `claude -p ... --settings <denyWrite-json> --dangerously-skip-permissions` spawn returns EPERM at the kernel layer when its Bash tool attempts to write to a denied path. Test runs under `just test`.
- Pre-flight recommendation (non-blocking): a human runs the empirical test in a clean (non-sandboxed) terminal before V1 implementation begins, to bound mechanism-flip risk early. Documented in spec phase.

## Research context

Full research at `research/sandbox-overnight-child-agents/research.md`. Particularly relevant: DR-1 (schema), DR-2 (distribution), DR-3 (V1 scope including cross-repo), DR-7 (acceptance test).
