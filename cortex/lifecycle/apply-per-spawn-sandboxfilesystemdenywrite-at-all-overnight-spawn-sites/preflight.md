# Pre-flight verification

Empirical kernel-enforcement preflight per spec Req 12 (REVISED 2026-05-05 — kernel-signal-only validation). Test invokes `claude -p ... --settings <denying-tempfile> --dangerously-skip-permissions --max-turns 3` against a `denyWrite`-listed target path; verifies (a) kernel returns EPERM ("operation not permitted") on the inner Bash write attempt, and (b) the target file is byte-identical before/after. The wrapper's exit code is recorded for forensic value but not asserted: `claude -p` wraps inner Bash-tool failures gracefully and exits 0 even when the kernel correctly denied the write.

```yaml
pass: true
timestamp: "2026-09-16T19:02:11Z"
commit_hash: "c41a4434e397cd8f0e526f46f08e35b265a76939"
claude_version: "2.1.273 (Claude Code)"
test_command: "claude -p '<kernel-sandbox preflight test prompt>' --settings <workdir>/cortex-preflight-settings.json --dangerously-skip-permissions --max-turns 3"
exit_code: 0
stderr_contains_eperm: true
stderr_excerpt: |
  EPERM signal appeared in claude's stdout content (not in process
  stderr — the agentic CLI surfaces inner Bash tool failures via
  content rather than the wrapper's stderr stream). Captured content:

  Raw output:

  ```
  (eval):1: operation not permitted: /private/tmp/cortex-preflight.WbeuiU/cortex-preflight-target.txt
  ```

  - exit code (inner Bash): 1
  - The file did not change, and the agent neither retried nor disabled
    the sandbox.

  Process stderr carried only an unrelated stdin-timeout warning
  ("no stdin data received in 3s, proceeding without it").
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

This preflight is re-recorded (against current HEAD and the current `claude` binary, per the E102/E103 freshness gate) for the staged change that **widens the `claude-agent-sdk` pin from the exact `>=0.1.46,<0.1.47` to the range `>=0.2.153,<0.3`** in `pyproject.toml`'s `[overnight]` extra, plus the matching `uv.lock` refresh. The publisher yanked 0.1.46 to free PyPI storage and will delete it on or after 2026-09-19, and both uv and pip refuse a yanked release unless it is pinned with `==`, so every install of every cortex release currently fails. That dependency line is the file+pattern the sandbox-preflight gate watches (`pyproject.toml` → `claude-agent-sdk`), because the SDK bundles a `claude` binary that sandboxed spawns could otherwise invoke.

The change does NOT alter any sandbox behavior. No sandbox-source file is touched: `cortex_command/overnight/sandbox_settings.py`, `cortex_command/pipeline/dispatch.py`, and `cortex_command/overnight/runner.py` are all unchanged, and the `denyWrite` / `allowWrite` / `enabled` / `failIfUnavailable` / `allowUnsandboxedCommands` / `enableWeakerNestedSandbox` / `enableWeakerNetworkIsolation` fields are identical. The per-spawn `--settings <tempfile>` mechanism is a CLI flag and is version-independent; `resolve_claude_cli()` continues to prefer the operator's system `claude` (2.1.273) over any bundled binary (ADR-0014), so the binary that applies the sandbox profile is the same before and after.

Verification run alongside this preflight: the pipeline and overnight suites pass on SDK 0.2.153 (1,061 tests), and a real `dispatch_task` drove the new SDK end to end — spawn, message parsing, `ResultMessage.stop_reason`, and error classification all intact.

The empirical re-run above confirms kernel-level `denyWrite` enforcement remains active on the current `claude` binary (`2.1.273`), so the pin widen introduces no sandbox regression.
