# Pre-flight verification

Empirical kernel-enforcement preflight per spec Req 12 (REVISED 2026-05-05 — kernel-signal-only validation). Test invokes `claude -p ... --settings <denying-tempfile> --dangerously-skip-permissions --max-turns 3` against a `denyWrite`-listed target path; verifies (a) kernel returns EPERM ("operation not permitted") on the inner Bash write attempt, and (b) the target file is byte-identical before/after. The wrapper's exit code is recorded for forensic value but not asserted: `claude -p` wraps inner Bash-tool failures gracefully and exits 0 even when the kernel correctly denied the write.

```yaml
pass: true
timestamp: "2026-07-18T02:55:49Z"
commit_hash: "7641cf716d1aafb50a3b917b9d07c82b3ea6d923"
claude_version: "2.1.214 (Claude Code)"
test_command: "claude -p '<kernel-sandbox preflight test prompt>' --settings <workdir>/cortex-preflight-settings.json --dangerously-skip-permissions --max-turns 3"
exit_code: 0
stderr_contains_eperm: true
stderr_excerpt: |
  EPERM signal appeared in claude's stdout content (not in process
  stderr — the agentic CLI surfaces inner Bash tool failures via
  content rather than the wrapper's stderr stream). Captured content:

  Result observed:

  - stderr: `(eval):1: operation not permitted: /tmp/cortex-preflight.HH9PSe/cortex-preflight-target.txt`
  - exit code: 1
  - Signal: zsh's redirection layer reported `operation not permitted` — the classic EPERM surface from Seatbelt denying the `open(O_WRONLY|O_CREAT|O_TRUNC)` syscall on that path.

  This matches the expected outcome: the path is listed in `denyWrite` within an
  `allowWrite` parent for the sandbox, so the kernel rejected the write before the
  shell could open the file. The denial came from the OS layer (Seatbelt), not from
  the agent declining — confirming kernel-level enforcement is active.

  Process stderr was empty (claude surfaces inner Bash failures via stdout content).
target_path: "<workdir>/cortex-preflight-target.txt"
target_unmodified: true
```

## Run notes

The settings tempfile passed via `--settings` carried this JSON (paths expanded to an absolute `mktemp -d` working directory rather than a bare `$TMPDIR` so the deny/allow set is unambiguous):

```json
{
  "sandbox": {
    "enabled": true,
    "failIfUnavailable": true,
    "filesystem": {
      "denyWrite": ["<workdir>/cortex-preflight-target.txt"],
      "allowWrite": ["<workdir>/"]
    }
  }
}
```

The prompt instructed the inner agent to attempt `echo OVERWRITTEN > $TARGET` via Bash, explicitly framing the kernel denial as the EXPECTED and DESIRED outcome (so the agent would attempt the syscall rather than refuse at the agent layer). The captured stdout confirms the inner Bash subprocess attempted the write and the OS kernel returned `operation not permitted` (EPERM) on the redirection target's `open(O_WRONLY|O_CREAT|O_TRUNC)` syscall.

Target file byte-identical before/after the test (SHA-256 `d164570cd3638c57975902d5ba584daf06fc69523061cc704263712b77fe8600` both times), confirming the kernel actually denied the write — not just that the agent declined to attempt it.

This run was conducted from inside a Claude Code session via Bash with `dangerouslyDisableSandbox: true` to avoid nested-Seatbelt application failure (the inner `claude` process applies its own Seatbelt profile and cannot do so when the outer Bash subprocess is already inside one). This is functionally equivalent to running in a clean non-sandboxed terminal per spec Req 12.

## Scope of staged change

This preflight is re-recorded (against current HEAD and the current `claude` binary, per the E102/E103 freshness gate) for the staged change that **moves `claude-agent-sdk` out of `pyproject.toml`'s base `dependencies` and into an optional `[overnight]` extra** (with `[dashboard]`/`[all]` siblings). This is the file+pattern the sandbox-preflight gate watches (`pyproject.toml` → `claude-agent-sdk`) because the SDK bundles the `claude` binary that sandboxed spawns invoke.

The change does NOT alter any sandbox behavior. It does not touch `cortex_command/overnight/sandbox_settings.py`, and the `denyWrite` / `allowWrite` / `enabled` / `allowUnsandboxedCommands` / `enableWeakerNestedSandbox` / `enableWeakerNetworkIsolation` fields are unchanged. The overnight runner still receives `claude-agent-sdk` at install time — the auto-installer and documented install both request `cortex-command[all]` — so spawn-time sandbox settings, the `--settings` tempfile, and the `claude` binary used for spawns are all identical to before. The only sandbox-source file in the change beyond `pyproject.toml` is `cortex_command/pipeline/dispatch.py`, whose sole edit is the wording of the SDK-absent `RuntimeError` message (no change to `build_sandbox`, `SandboxSettings`, `write_settings_tempfile`, or `_load_project_settings`).

The empirical re-run above confirms kernel-level `denyWrite` enforcement remains active on the current `claude` binary (`2.1.214`), so the dependency-location move introduces no sandbox regression.
