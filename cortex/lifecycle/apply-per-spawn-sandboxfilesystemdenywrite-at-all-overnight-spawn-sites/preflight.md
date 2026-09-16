# Pre-flight verification

Empirical kernel-enforcement preflight per spec Req 12 (REVISED 2026-05-05 — kernel-signal-only validation). The test spawns `claude` the way per-feature dispatch does — through `cortex_command.claude_stream` (`build_argv` + `build_env` + `run_claude`, prompt on stdin) with `--settings <denying-tempfile> --permission-mode bypassPermissions --max-turns 3` — against a `denyWrite`-listed target path. It checks that (a) the kernel returns EPERM ("operation not permitted") on the inner Bash write attempt, and (b) the target file is byte-identical before/after. The wrapper's exit code is recorded for forensics but not asserted: `claude -p` reports inner Bash-tool failures inside the stream and exits 0 even when the kernel denied the write.

```yaml
pass: true
timestamp: "2026-09-16T20:29:59Z"
commit_hash: "840632b5deeda4f249b9e83a1d6c165cad155191"
claude_version: "2.1.273 (Claude Code)"
test_command: "claude -p --output-format stream-json --verbose --max-turns 3 --max-budget-usd 2.0 --permission-mode bypassPermissions --allowedTools Read,Write,Edit,Bash,Glob,Grep --system-prompt <test> --settings <workdir>/settings.json --effort low  (prompt on stdin: run `echo changed > <workdir>/target.txt` via Bash once)"
exit_code: 0
stderr_contains_eperm: true
stderr_excerpt: |
  EPERM appeared in the stream-json `tool_result` frame (is_error: true),
  not in process stderr, which was empty. Captured tool result:

  Exit code 1
  (eval):1: operation not permitted: <workdir>/target.txt

  Final result frame: is_error false, subtype success, num_turns 2.
target_path: "<workdir>/target.txt"
target_unmodified: true
```

## Run notes

The settings tempfile came from `cortex_command.overnight.sandbox_settings.build_sandbox_settings_dict(deny_paths=[<workdir>/target.txt], allow_paths=[<workdir>], soft_fail=False, excluded_commands=["git:*"])` — the same builder dispatch uses — so `failIfUnavailable: true`, `allowUnsandboxedCommands: false`, and `denyWrite` / `allowWrite` as listed.

The target file's SHA-256 matched before and after the run, confirming the kernel denied the write rather than the agent declining to attempt it.

## Scope of staged change

Re-recorded against current HEAD and the current `claude` binary for the remove-claude-agent-sdk-dependency lifecycle (ADR-0038): cortex no longer reaches `claude` through `claude-agent-sdk`, so the per-dispatch `--settings <tempfile>` flag is now built by `cortex_command/claude_stream.py`. `SANDBOX_WATCHED_FILES` drops the dead `pyproject.toml → claude-agent-sdk` and `dispatch.py → SandboxSettings` patterns and watches `claude_stream.py` for the settings passthrough instead.
