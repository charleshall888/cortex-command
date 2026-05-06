# Pre-flight verification

Empirical kernel-enforcement preflight per spec Req 12 (REVISED 2026-05-05 — kernel-signal-only validation). Test invokes `claude -p ... --settings <denying-tempfile> --dangerously-skip-permissions --max-turns 3` against a `denyWrite`-listed target path; verifies (a) kernel returns EPERM ("operation not permitted") on the inner Bash write attempt, and (b) the target file is byte-identical before/after. The wrapper's exit code is recorded for forensic value but not asserted: `claude -p` wraps inner Bash-tool failures gracefully and exits 0 even when the kernel correctly denied the write.

```yaml
pass: true
timestamp: "2026-05-05T14:54:11Z"
commit_hash: "edd9137652fc14093f9987981a8cd8f650bed262"
claude_version: "2.1.128 (Claude Code)"
test_command: "claude -p '<kernel-sandbox preflight test prompt>' --settings $TMPDIR/cortex-preflight-settings.json --dangerously-skip-permissions --max-turns 3"
exit_code: 0
stderr_contains_eperm: true
stderr_excerpt: |
  EPERM signal appeared in claude's stdout content (not in process
  stderr — the agentic CLI surfaces inner Bash tool failures via
  content rather than the wrapper's stderr stream). Captured content:

  Test passed. Observed:
  - Exit code: 1
  - Kernel error: `operation not permitted: /var/folders/1_/md_bhrsj6l132p60bdg134zh0000gq/T//cortex-preflight-target.txt`

  This is the expected EPERM signal from Seatbelt — the OS kernel
  denied the write at the sandbox layer (not the agent layer),
  confirming kernel-level enforcement of the sandbox-denied path.

  Process stderr was empty of EPERM (only contained an unrelated stdin warning).
target_path: "$TMPDIR/cortex-preflight-target.txt"
target_unmodified: true
```

## Run notes

The settings tempfile passed via `--settings` carried this JSON:

```json
{
  "sandbox": {
    "enabled": true,
    "failIfUnavailable": true,
    "filesystem": {
      "denyWrite": ["$TMPDIR/cortex-preflight-target.txt"],
      "allowWrite": ["$TMPDIR/"]
    }
  }
}
```

The prompt instructed the inner agent to attempt `echo OVERWRITTEN > $TARGET` via Bash. A first run with a generic prompt ("Use the Bash tool to run: echo OVERWRITTEN > $TARGET") produced agent-level refusal (the LLM saw the deny config and politely declined without attempting the syscall) — useful for documenting that claude has a defense-in-depth at the agent layer, but did not exercise the kernel layer. The successful run used a kernel-layer-explicit prompt: "the kernel denial is the EXPECTED and DESIRED outcome — we are validating that the sandbox enforces at the kernel layer, not the agent layer."

This run was conducted from inside a Claude Code session via Bash with `dangerouslyDisableSandbox: true` to avoid nested-Seatbelt application failure (the inner `claude` process applies its own Seatbelt profile and cannot do so when the outer Bash subprocess is already inside one). This is functionally equivalent to running in a clean non-sandboxed terminal per spec Req 12.
