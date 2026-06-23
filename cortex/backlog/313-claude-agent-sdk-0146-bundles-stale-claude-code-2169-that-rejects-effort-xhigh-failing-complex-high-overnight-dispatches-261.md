---
schema_version: "1"
uuid: 9317e015-9ae6-4d15-845a-4f4bfcf69696
title: "claude_agent_sdk 0.1.46 bundles stale claude-code 2.1.69 that hard-rejects --effort xhigh; SDK prefers the bundled CLI over system claude, failing every complex/high|critical overnight dispatch (#261)"
status: in_progress
priority: high
type: bug
created: 2026-06-23
updated: 2026-06-23
complexity: complex
criticality: high
lifecycle_slug: overnight-dispatch-sends-opus-only-xhigh
lifecycle_phase: research
---
## Summary

Every `complex` + `high|critical` overnight implement/review dispatch fails **instantly** because the Claude Code CLI **bundled inside `claude_agent_sdk 0.1.46` is v2.1.69**, which predates the `xhigh` effort level and **hard-errors** on `--effort xhigh`. cortex correctly resolves `xhigh` for those (Opus) tasks, but the SDK transport prefers its **bundled** CLI over the system `claude` (2.1.186, which accepts `xhigh`), so the dispatch dies at CLI arg-parse with exit 1 before doing any work.

> **Correction (supersedes this ticket's original root cause):** This is NOT a `--tier` model cap nor a "Sonnet + xhigh" mismatch. The dispatch model was correctly `opus`. The failure is the **stale bundled CLI inside the SDK**, confirmed by byte-identical reproduction below.

## Impact

`complex`/`high|critical` features — the highest-value work — cannot run at all: the dispatch exits 1 within ~1-3s and is recorded as `task_failure`. Observed pausing wild-light #261 (thread-worldgen, the flagship batch item). The failure surfaces only as an opaque `ProcessError: exit code 1` in `learnings/progress.txt`, not as a clear "CLI rejected --effort xhigh".

## Reproduction (exact, byte-identical)

```
$ env -u CLAUDECODE <sdk>/claude_agent_sdk/_bundled/claude --effort xhigh --version
error: option '--effort <level>' argument 'xhigh' is invalid. It must be one of: low, medium, high, max
$ env -u CLAUDECODE <sdk>/claude_agent_sdk/_bundled/claude --effort high --version
2.1.69 (Claude Code)
```

For contrast, the system CLI accepts it:
```
$ claude --effort xhigh --version    # /Users/.../.local/bin/claude
2.1.186 (Claude Code)                # exit 0; truly-invalid values only WARN ("Valid values: low, medium, high, xhigh, max")
```

## Observed (wild-light overnight-2026-06-23-0605, feature thread-worldgen-off-the-main-thread / #261)

- `pipeline-events.log` dispatch_start records: complex tasks → `model: opus, effort: xhigh, complexity: complex, criticality: high`; simple tasks → `model: sonnet, effort: high`.
- Every `opus + xhigh` dispatch → `dispatch_error {error_type: task_failure}` within 1-3s (instant arg rejection). The `sonnet + high` tasks ran for minutes and produced multi-minute `dispatch_complete` records — i.e. only the `xhigh` cell failed.
- `learnings/progress.txt`: `Error: task_failure: ProcessError: Command failed with exit code 1`. Feature paused after 2 attempts.

## Root cause (chain)

1. `cortex_command/pipeline/dispatch.py` `_EFFORT_MATRIX[("complex","high")] = _EFFORT_MATRIX[("complex","critical")] = "xhigh"` (Opus-only; correct per Anthropic guidance).
2. `claude_agent_sdk/_internal/transport/subprocess_cli.py` `_find_cli()` calls `_find_bundled_cli()` **first** — returning `<sdk>/_bundled/claude` if present — **before** `shutil.which("claude")`. So the bundled CLI wins over the system one.
3. The bundled CLI in `claude_agent_sdk 0.1.46` is **claude-code 2.1.69** (May 5 2026): its `--effort` vocabulary is `{low, medium, high, max}` and it **hard-errors** on `xhigh`. Newer claude-code (2.1.186) added `xhigh` and only warns on unknown values.
4. cortex passes **no** `ClaudeAgentOptions(cli_path=...)` (grep: none), so nothing redirects the SDK to the system claude.

→ `opus + xhigh` dispatch → SDK spawns bundled 2.1.69 → instant exit-1 reject → `task_failure` → feature paused. (Installed `claude_agent_sdk` is **0.1.46**; latest on PyPI is **0.2.107**.)

## Suggested fixes (any/all)

1. **Upgrade `claude_agent_sdk`** (0.1.46 → current 0.2.x) so the bundled CLI supports `xhigh`. Primary fix.
2. **Pin the CLI**: pass `ClaudeAgentOptions(cli_path=<system claude>)` (or set an env) so dispatch uses the system 2.1.186; prefer the newer of bundled-vs-system rather than always-bundled.
3. **Defense-in-depth (cortex):** probe the effective CLI's supported `--effort` set (or run a one-shot `<cli> --effort xhigh --version` preflight at startup) and clamp `xhigh -> high/max` if unsupported — don't trust `_MODEL_SUPPORTED_EFFORTS` to describe a CLI the SDK actually bundles.
4. Surface the real error: an `--effort` rejection should be reported as such, not as an opaque `ProcessError: exit code 1` (ties to #309 undiagnosable failures).

## References

Same run as #314 (review-gate merge-revert). Origin of the `xhigh` default: #090 (#089 cost study). Related: #309 (undiagnosable empty-output failures), #308, #312. Env: cortex-command 2.28.1, claude_agent_sdk 0.1.46 (bundled claude-code 2.1.69), system claude-code 2.1.186.
