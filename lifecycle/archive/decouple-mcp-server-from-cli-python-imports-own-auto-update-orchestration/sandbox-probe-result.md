# R18 Sandbox Empirical Probe — Result

Spec reference: `lifecycle/archive/decouple-mcp-server-from-cli-python-imports-own-auto-update-orchestration/spec.md` R18.

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

Probe executed 2026-04-27 from a real Claude Code MCP session
(`r18-probe` registered via `claude mcp add`, invoked via the `run_probe`
tool). Cortex root: `/Users/charlie.hall/Workspaces/cortex-command`.

### Op 1 — Filesystem write to `.git/`

**status: ok**

```json
{
  "op": 1,
  "name": "filesystem_write_to_dot_git",
  "status": "ok",
  "path": "/Users/charlie.hall/Workspaces/cortex-command/.git/.cortex-write-probe",
  "error": null
}
```

`Path("$cortex_root/.git/.cortex-write-probe").touch()` returned without
raising. No sandbox / TCC block on writes into `$cortex_root/.git/`.

### Op 2 — `flock(LOCK_EX)` on `cortex-update.lock`

**status: ok**

```json
{
  "op": 2,
  "name": "flock_acquire_release",
  "status": "ok",
  "path": "/Users/charlie.hall/Workspaces/cortex-command/.git/cortex-update.lock",
  "error": null
}
```

`os.open(O_RDWR | O_CREAT)` + `fcntl.flock(LOCK_EX)` succeeded on
`$cortex_root/.git/cortex-update.lock` and released cleanly. No sandbox /
TCC block on advisory locks under `.git/`.

### Op 3 — `uv tool install -e <cortex_root> --force`

**status: ok**

```json
{
  "op": 3,
  "name": "uv_tool_install_force",
  "exit_code": 0,
  "stdout": "",
  "stderr": "Resolved 42 packages in 149ms\nUninstalled 1 package in 2ms\nInstalled 1 package in 4ms\n ~ cortex-command==0.1.0 (from file:///Users/charlie.hall/Workspaces/cortex-command)\nInstalled 2 executables: cortex, cortex-batch-runner\n",
  "lib_exists": true,
  "bin_exists": true,
  "lib_path": "/Users/charlie.hall/.local/share/uv/tools/cortex-command/lib",
  "bin_path": "/Users/charlie.hall/.local/bin/cortex",
  "status": "ok",
  "error": null
}
```

`uv tool install -e <cortex_root> --force` exited 0; both
`~/.local/share/uv/tools/cortex-command/lib/` and `~/.local/bin/cortex`
exist after the call. No sandbox / TCC block on `uv tool install` writes
into `~/.local/share/uv/tools/` or `~/.local/bin/`.

### Op 4 — `cortex --print-root` and `cortex overnight status --format json`

**status: error (op 4b only — invocation-form bug in probe, NOT a sandbox block)**

**Diagnosis after first run:** the probe's Op 4b passed `""` (an empty
string) as a positional argument: `cortex overnight status --format json ""`.
The current CLI's `overnight status` subparser does not accept a positional
session_id (it offers `--session-dir` as the override path; only
`overnight cancel` accepts a positional session_id). The empty string was
parsed as an unknown positional and the main parser exited 2 with
`unrecognized arguments: `. The first stderr line in the captured output —
`cortex: error: argument verb: invalid choice: 'status' (choose from cancel)` —
is a separate cosmetic stderr leak from `cortex_command/install_guard.py`'s
cancel-bypass pre-parse (it builds a narrow argparse parser whose
`add_subparsers(dest="verb")` only registers `cancel`, then calls
`parse_known_args` and catches the `SystemExit` — but argparse's own
`parser.error()` writes to stderr before raising). It does not affect the
exit code; the bypass parser's verdict ("not a cancel --force") is
correct, and control falls through to the real CLI. Independent
verification: running `cortex overnight status --format json` (without the
trailing empty string) from a bare shell returns exit 0 with parseable
JSON on stdout — `cortex overnight status` is registered correctly in the
installed CLI (`cortex_command/cli.py:290–309`).

The probe source has been corrected (`probe-mcp.py`'s `_op4_cortex_subprocess`
now invokes `["cortex", "overnight", "status", "--format", "json"]` with no
trailing empty positional) and the spec interpretation note is preserved
inline. Re-running the probe from MCP-handler context (which requires a
Claude Code restart to pick up the updated script) is expected to return
PASS for all four operations.

```json
{
  "op": 4,
  "name": "cortex_subprocess_post_upgrade",
  "sub_results": {
    "print_root": {
      "exit_code": 0,
      "stdout": "{\"version\": \"1.0\", \"root\": \"/Users/charlie.hall/Workspaces/cortex-command\", \"remote_url\": \"https://github.com/charleshall888/cortex-command.git\", \"head_sha\": \"e9f06721199bbcc926dbb574336f4dddcdde77fb\"}\n",
      "stderr": ""
    },
    "overnight_status": {
      "exit_code": 2,
      "stdout": "",
      "stderr": "usage: cortex {cancel} ...\ncortex: error: argument verb: invalid choice: 'status' (choose from cancel)\nusage: cortex [-h] [--print-root] <command> ...\ncortex: error: unrecognized arguments: \n"
    }
  },
  "status": "error",
  "error": "print_root_exit=0, overnight_status_exit=2"
}
```

- **Op 4a (`cortex --print-root`): PASSED.** Exit 0; stdout is parseable
  JSON containing `version`, `root`, `remote_url`, `head_sha`.
- **Op 4b (`cortex overnight status --format json ""`): FAILED with exit 2.**
  However, the captured stderr shows this is a CLI-argument error, not a
  sandbox block: `argument verb: invalid choice: 'status' (choose from cancel)`.
  The current CLI's `overnight` subparser only registers the `cancel` verb;
  `status` is no longer wired up. The subprocess invocation itself
  succeeded — Python received the child's exit code and captured stdout/stderr
  through normal subprocess plumbing. There is no sandbox / TCC denial here.

**Sandbox-feasibility implication.** R18's purpose is to confirm that the
sandbox in which MCP tool handlers execute does not block the four
operations R10–R14 will perform. None of the four operations were
sandbox-blocked: writes into `.git/`, advisory locks under `.git/`,
`uv tool install` writes into `~/.local/share/uv/tools/` and `~/.local/bin/`,
and subprocess execution from the MCP handler context all succeeded
mechanically. The single non-zero exit code in the probe (op 4b) is a CLI
surface regression that is unrelated to sandboxing and is recorded
separately as a CLI-shape note for the lifecycle.

## Verdict

<!--
The orchestrator and the verification grep look for the regex
  ^(PASS|FAIL|PARTIAL)$
on a line by itself.

Initial run produced a mechanical PARTIAL because op 4b's exit code was
non-zero. Diagnosis (recorded in the Op 4 section above) traced that
non-zero exit to a probe bug (over-literal handling of "empty/unknown
session id"), not a sandbox block. The corrected invocation
(`cortex overnight status --format json` with no trailing empty
positional) was verified to exit 0 with parseable JSON; the probe source
has been updated to match. All four sandbox-sensitive operation classes
(filesystem write to .git/, flock under .git/, uv tool install writes
into ~/.local/, subprocess execution from the MCP-handler context) are
empirically confirmed feasible from MCP-handler context.

User decision (2026-04-27): treat the empirical evidence (3-of-4 PASS
from MCP context plus bare-shell verification of the corrected Op 4b
form) as sufficient for R18's purpose. Verdict flipped to PASS; R10–R14
remain in scope; Task 16 (R19 notice-only fallback) does not fire.
-->

PASS
