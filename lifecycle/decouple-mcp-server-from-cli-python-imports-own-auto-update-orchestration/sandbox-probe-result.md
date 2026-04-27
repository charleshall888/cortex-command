# R18 Sandbox Empirical Probe — Result

Spec reference: `lifecycle/decouple-mcp-server-from-cli-python-imports-own-auto-update-orchestration/spec.md` R18.

This artifact records the empirical verdict for whether MCP tool handlers
spawned by Claude Code's MCP-launch path can perform the four operations that
R10–R14 require:

1. Filesystem write to `$cortex_root/.git/.cortex-write-probe`.
2. `fcntl.flock(LOCK_EX)` on `$cortex_root/.git/cortex-update.lock`.
3. `uv tool install -e <cortex_root> --force` and verification that writes
   land at `~/.local/share/uv/tools/cortex-command/lib/` and `~/.local/bin/cortex`.
4. Post-upgrade `cortex --print-root` and `cortex overnight status --format json`
   subprocess invocations.

Verdict semantics (per spec R18):

- **PASS** = all four operations succeed → R10–R14 stay in scope.
- **FAIL** = any of operations 1–4 is blocked by the sandbox / macOS TCC →
  fall through to R19's notice-only fallback.
- **PARTIAL** = mixed outcome → treated as FAIL for R10–R14 scoping; document
  which operations failed.

The probe MUST be run from a real Claude Code MCP session — NOT via the
Claude Code `Bash` tool, which inherits a different sandbox surface and would
not reflect the production R10–R14 execution context.

## How to Run

1. **Register the probe MCP server in your Claude Code session.** Add this
   block to a project-local `.mcp.json` (or your global Claude Code MCP
   config), or use the equivalent `claude mcp add` command:

   ```json
   {
     "mcpServers": {
       "r18-probe": {
         "command": "uv",
         "args": [
           "run",
           "--script",
           "/Users/charlie.hall/Workspaces/cortex-command/lifecycle/decouple-mcp-server-from-cli-python-imports-own-auto-update-orchestration/probe-mcp.py"
         ]
       }
     }
   }
   ```

   The probe is a PEP 723 single-file script (`requires-python = ">=3.12"`,
   `dependencies = ["mcp>=1.27,<2"]`); `uv run --script` resolves the inline
   metadata block and provisions the MCP SDK on first launch.

2. **Restart Claude Code** so the new MCP server registers.

3. **Confirm Task 2 has landed.** This task brief notes that Task 2
   (`cortex --print-root` flag) has landed at commit `441d3b3`, so Op 4 can
   exercise the real flag. If for any reason `cortex --print-root` does not
   exist on the installed CLI, run `cortex --version` (or another stable
   verb) as a substitute and note the substitution under Operation Results.

4. **Invoke the `run_probe` tool** from Claude Code. No arguments are
   required; defaults resolve `cortex_root` from `CORTEX_COMMAND_ROOT` env
   var, falling back to `/Users/charlie.hall/Workspaces/cortex-command`. To
   override, pass a `cortex_root` argument.

5. **Paste the returned JSON** into the Operation Results section below
   (replacing the placeholder text).

6. **Set the verdict line** at the bottom of this file to one of the
   following exact strings on its own line: `PASS`, `FAIL`, or `PARTIAL`.
   The orchestrator and the verification grep look for
   `^(PASS|FAIL|PARTIAL)$` — replace the literal `PENDING` with one of those
   three values.

## Operation Results

### Op 1 — Filesystem write to `.git/`

PENDING — fill in after running probe.

(Expected: `Path("$cortex_root/.git/.cortex-write-probe").touch()` returns
without raising; record `status: "ok"` from the JSON, or paste the captured
exception type and message.)

### Op 2 — `flock(LOCK_EX)` on `cortex-update.lock`

PENDING — fill in after running probe.

(Expected: `os.open` + `fcntl.flock(LOCK_EX)` succeeds on
`$cortex_root/.git/cortex-update.lock`, then releases cleanly.)

### Op 3 — `uv tool install -e <cortex_root> --force`

PENDING — fill in after running probe.

(Expected: `subprocess.run(["uv", "tool", "install", "-e", cortex_root,
"--force"], timeout=60)` returns exit 0, AND
`~/.local/share/uv/tools/cortex-command/lib/` and `~/.local/bin/cortex` both
exist after the call.)

### Op 4 — `cortex --print-root` and `cortex overnight status --format json`

PENDING — fill in after running probe.

(Expected: both subprocesses return exit 0 with parseable JSON on stdout.)

## Verdict

<!--
The orchestrator and the verification grep look for the regex
  ^(PASS|FAIL|PARTIAL)$
on a line by itself. After running the probe, replace the literal `PENDING`
on the line below with exactly one of: PASS, FAIL, or PARTIAL.

If the verdict is FAIL or PARTIAL, also follow up per spec R19:
  - record the rationale and scope-cut diff above (which R10–R14 acceptance
    criteria are dropped), and
  - file a follow-up backlog ticket to investigate `cortex init` allowWrite
    registration of `$cortex_root/.git/` and
    `~/.local/share/uv/tools/cortex-command/` paths.
-->

PENDING
