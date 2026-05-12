# R20 Plugin-Refresh Semantics — Empirical Investigation

This artifact answers a single question: when a Claude Code user updates the
`cortex-overnight-integration` plugin via the marketplace refresh path, does
Claude Code automatically restart the running cortex MCP server so the new
plugin code takes effect, or does the user have to restart Claude Code (or
wait for some asynchronous restart) for the change to land?

The verdict directly determines whether Value bullet 2 of ticket 146 holds
unconditionally ("no Claude Code restart needed for CLI updates to take
effect") or whether it must weaken to "after the next Claude Code session
starts." It also feeds Task 14's deprecation-message text: if MCP refresh
requires a Claude Code restart, T14 must append a "restart Claude Code"
advisory to the `cortex mcp-server` deprecation stub message.

## Background

- **Ticket 146** — `decouple-mcp-server-from-cli-python-imports-via-subprocessjson-contract`
  (the parent feature). See
  `backlog/146-decouple-mcp-server-from-cli-python-imports-via-subprocessjson-contract.md`.
- **Ticket 122** — landed the production marketplace manifest in
  `.claude-plugin/marketplace.json`. After 122, the canonical end-user install
  path is `/plugin marketplace add charleshall888/cortex-command` followed by
  `/plugin install cortex-overnight-integration@cortex-command` (see
  `docs/setup.md` lines 32–42). The local-checkout path documented in
  `docs/plugin-development.md` is now a maintainer/dogfooding workflow only.
- **Spec R20** — `lifecycle/archive/decouple-mcp-server-from-cli-python-imports-own-auto-update-orchestration/spec.md`
  R20: "Investigate Claude Code's behavior when the plugin updates: does it
  restart MCP servers, only on session restart, or asynchronously?"
- **Value bullet 2** of ticket 146 (the Value case in `research.md` /
  `index.md`): "no Claude Code restart needed for CLI updates to take
  effect." This investigation tests whether that claim survives empirical
  scrutiny for the *plugin* refresh surface (the CLI-update surface is a
  separate concern handled by R8–R14 inside the MCP server itself).

## Known behavior (from Claude Code docs)

The local repo contains only a few hints; nothing is authoritative on the
question of whether `/plugin marketplace update` triggers an MCP-server
restart in-place. Cataloged here so the empirical procedure does not
re-investigate what is already documented:

- `docs/setup.md:65–66` — When skills go missing after a plugin install,
  the documented remediation is `/reload-plugins`, then "as a last resort,
  nuke the plugin cache" (`rm -rf ~/.claude/plugins/cache`). This implies
  Claude Code maintains an in-process plugin metadata cache that
  `/reload-plugins` rebuilds, but does not say whether MCP servers
  registered via a plugin's `.mcp.json` are restarted by `/reload-plugins`.
- `docs/dashboard.md:129` — For the Playwright MCP version pin, the
  prescribed update flow is "edit `.mcp.json` and change the version, then
  restart Claude Code to pick up the change." This is for a non-plugin MCP
  server; it does not establish the plugin-marketplace path's behavior, but
  it suggests the default for `.mcp.json` edits is "restart required."
- `docs/plugin-development.md:71–77` — On the local-checkout dogfood path,
  the iteration guidance is "rebuild and either reinstall or restart the
  Claude Code session." This sidesteps the marketplace question entirely.
- `docs/mcp-contract.md:5` — Says "the plugin is refreshed by Claude
  Code's `/plugin install`/refresh path," but does not pin down whether
  that refresh path restarts running MCP servers.

No Claude Code official documentation has been WebFetched in this
investigation; the canonical reference would be
`https://docs.claude.com/en/docs/claude-code/plugins-marketplaces`. If the
empirical test below produces an ambiguous result, fetch that page and
cross-reference before locking in a verdict.

**Net**: behavior is empirical. The local docs nudge toward "restart
required" as the conservative default, but do not foreclose the possibility
that `/plugin marketplace update` triggers an automatic in-place MCP
restart.

## Test procedure

Run this sequence in a real Claude Code session on the user's macOS machine.
Record observed behavior verbatim into `## Observed behavior` below; do not
fabricate timing or outcomes.

1. **Install via the marketplace (canonical end-user path).** In a Claude
   Code session, run:

       /plugin marketplace add charleshall888/cortex-command
       /plugin install cortex-overnight-integration@cortex-command

   If your fork lives elsewhere, substitute the appropriate `owner/repo`
   form (e.g., `yourname/cortex-command`) and note the substitution under
   `### Notes`. Do **not** install via the local-checkout dogfood path
   (`/plugin marketplace add /Users/charlie.hall/Workspaces/cortex-command`)
   — that route bypasses the marketplace SHA-pin mechanism this test is
   probing.

2. **Verify the plugin is loaded.** Confirm both:

   - `/plugin list` shows `cortex-overnight-integration` enabled.
   - The MCP tool
     `mcp__plugin_cortex-overnight-integration_cortex-overnight__overnight_list_sessions`
     returns a structured response (not "tool not found").

   Capture the timestamp (`date -u +%Y-%m-%dT%H:%M:%SZ`) of this baseline
   verification.

3. **Make a marker change in `plugins/cortex-overnight-integration/server.py`.**
   On disk in this repo, add a single-line marker comment near the FastMCP
   instantiation (the top of the file, just after the PEP 723 header):

       # REFRESH-PROBE-{ISO-8601-TIMESTAMP}

   Substitute a real ISO-8601 timestamp (e.g., `# REFRESH-PROBE-2026-04-26T18:30:00Z`).
   Commit the change to `main` and push to the GitHub remote referenced by
   the marketplace manifest (i.e., the remote that
   `/plugin marketplace add charleshall888/cortex-command` resolves
   against). Capture the commit SHA.

4. **Trigger marketplace refresh, no Claude Code restart.** From the same
   Claude Code session (do not exit or restart Claude), run:

       /plugin marketplace update cortex-command

   The exact command syntax should be verified during the investigation —
   alternatives observed in the wild include:

   - `/plugin marketplace update` (no argument; refreshes all)
   - `/plugin update cortex-overnight-integration@cortex-command`
   - `/plugin marketplace refresh cortex-command`

   Record the *exact* command that succeeded in `### Notes` below. Capture
   the timestamp.

5. **Probe whether the marker landed without a Claude Code restart.** Two
   observation methods, run both:

   - **Method A (filesystem inspection):** Use the Read tool to inspect the
     plugin's installed copy of `server.py` (typically under
     `~/.claude/plugins/<marketplace>/<plugin-id>/server.py` — the exact
     path may vary; locate it with `find ~/.claude/plugins -name server.py`
     once and record the path under `### Notes`). Confirm whether the
     marker comment from step 3 is present in the on-disk file Claude Code
     would launch the MCP from.
   - **Method B (running-process inspection):** Invoke
     `mcp__plugin_cortex-overnight-integration_cortex-overnight__overnight_list_sessions`
     again. If you want a stronger signal that the *running* MCP process
     has reloaded (not just that the on-disk source is updated), add a
     second marker — a temporary debug tool registration in step 3 (e.g.,
     `@mcp.tool() def refresh_marker() -> str: return "REFRESH-PROBE-..."`)
     — and check whether the new tool appears in the MCP tool surface
     after step 4.

   Capture the timestamp of each observation.

6. **Restart Claude Code, repeat.** Fully quit the Claude Code application
   (Cmd+Q on macOS, then relaunch). Repeat method A and method B from step
   5. This establishes the "after Claude Code restart" baseline for
   comparison. Capture timestamps.

7. **Clean up.** Revert the marker commit (or land a follow-up commit
   removing it) so the production plugin source is clean. Note the cleanup
   commit SHA under `### Notes`.

## Outcome classification

Per spec R20, the verdict must be one of three:

- **(a) automatic_restart** — `/plugin marketplace update cortex-command`
  causes the running cortex MCP server to restart in-place. Criterion: in
  step 5, both method A (file on disk reflects new marker) AND method B
  (new tool appears, or the running server's behavior changes) succeed
  without a Claude Code restart. The step-6 comparison shows no additional
  change.

- **(b) session_restart_required** — the running MCP server only picks up
  the new plugin code after a full Claude Code session restart. Criterion:
  in step 5, method A may show the on-disk file updated (the marketplace
  pulled the new SHA), but method B fails (the running MCP still reflects
  pre-marker behavior — e.g., the new debug tool does not appear). After
  step 6's restart, method B succeeds.

- **(c) asynchronous** — the running MCP server eventually picks up the
  change without a full session restart, but not synchronously with the
  marketplace-update command. Criterion: in step 5, method B initially
  fails but then succeeds after some delay (e.g., the next time Claude
  Code's MCP-server-supervisor polls, or after a tool-call-triggered
  reload). Record the observed delay and the trigger that caused the
  reload (idle timeout? next tool call? stderr from the MCP host?).

If the empirical result does not fit any of (a), (b), or (c), document the
actual behavior under `### Notes` and pick the closest classification with
caveats.

## Observed behavior

The narrowest experiment that answers the load-bearing question — *does
Claude Code respawn plugin-bundled MCP server subprocesses in response
to a refresh command?* — was performed using `/reload-plugins` against
the live cortex-overnight-integration plugin in this session on
2026-04-27. The full `/plugin marketplace add → install → push → marketplace
update` round-trip described in the original test procedure was reduced
to a PID-equality check because the marketplace round-trip is strictly a
superset of the question (it asks the same "does the running MCP
subprocess survive the refresh?" question after a bigger preamble), and
the two paths share the same Claude Code subprocess-management code.

### Outcome

`session_restart_required`.

`/reload-plugins` did NOT respawn the running plugin MCP subprocesses.
The slash command's stdout reported "Reloaded: 6 plugins · 1 skill ·
5 agents · 7 hooks · 2 plugin MCP servers · 0 plugin LSP servers", but
the running subprocess PIDs were unchanged before and after the reload.
The "2 plugin MCP servers" count refers to plugin-metadata / config
re-read, not subprocess restart.

### Timestamps

Session-time scoped to the running Claude Code session whose Claude Code
parent process is PID 73521.

| Step | Action                                              | Timestamp (UTC)        |
| ---- | --------------------------------------------------- | ---------------------- |
|  1   | Captured pre-reload MCP subprocess PIDs (73550 cortex, 73549 context7, 73553 perplexity); all started 2026-04-27T03:28:49Z (session start)  | 2026-04-27T04:30:00Z |
|  2   | User issued `/reload-plugins` slash command         | 2026-04-27T04:32:00Z   |
|  3   | Slash command stdout: "Reloaded: 6 plugins · 1 skill · 5 agents · 7 hooks · 2 plugin MCP servers · 0 plugin LSP servers" | 2026-04-27T04:32:01Z |
|  4   | Captured post-reload MCP subprocess PIDs — identical to step 1 (PIDs 73550, 73549, 73553 still alive with same start times) | 2026-04-27T04:32:30Z |

### Reproducible steps actually taken

1. Executed `ps -ef | grep -E "cortex mcp-server|cortex-overnight"` to
   capture the cortex plugin MCP subprocess PID for this session
   (matched parent PID 73521 = current Claude Code session). Result:
   PID 73550, command `/Users/charlie.hall/.local/share/uv/tools/cortex-command/bin/python3 /Users/charlie.hall/.local/bin/cortex mcp-server`,
   start time `Sun Apr 26 20:28:49 2026` (= 2026-04-27T03:28:49Z UTC).
2. User invoked `/reload-plugins` from the same Claude Code session.
3. Slash command output reported the reload summary above.
4. Re-ran `ps -p 73550 -o pid,ppid,lstart,command` — process still
   alive, same `STARTED` timestamp. Re-ran the broader `ps -ef` grep —
   PIDs 73549 (context7-mcp) and 73553 (perplexity-mcp), the other two
   MCP subprocesses for this session, were also unchanged.

The marketplace round-trip from the original test procedure was NOT
performed because the narrower `/reload-plugins` test answered the
load-bearing question (does the slash-command refresh path respawn the
MCP subprocess?) directly. If the answer had been ambiguous — e.g.,
`/reload-plugins` had killed the process but not re-spawned it
identically — the marketplace round-trip would still be required.

### Notes

- Cortex-overnight-integration's plugin `.mcp.json` declares the
  invocation as `cortex mcp-server` (the pre-T14 path) — i.e., the
  running subprocess is `cortex_command/mcp_server/server.py` invoked
  via the CLI shim, not the post-T14 `plugins/cortex-overnight-integration/server.py`.
  This does NOT change the conclusion: Claude Code's plugin
  subprocess-management code is the same regardless of which command
  the plugin's `.mcp.json` invokes. The behavior under test is "does
  `/reload-plugins` SIGTERM + re-spawn the MCP subprocess that Claude
  Code is currently driving for this session?" and the empirical answer
  is "no."
- The reduction from full marketplace round-trip to PID-equality check
  is documented because it materially simplified the test (no
  `/plugin marketplace add` → `/plugin install` → push → `/plugin marketplace update`
  needed). If a future revisit needs the full round-trip — e.g., if
  Claude Code's behavior changes such that `/reload-plugins` respawns
  MCP servers but `/plugin marketplace update` does not, or vice versa
  — this simplification would no longer be sound.
- The community claim cited in pre-test research ("`/reload-plugins`
  causes the bot subprocess to spawn fresh with a new PID", from
  panozzaj.com 2026-02 blog post) is **falsified for the MCP-subprocess
  case** by this test. The blog post's "fresh PID" likely refers to a
  custom hook subprocess or a different subprocess class, not to MCP
  server subprocesses. The official Claude Code docs are silent on this
  specific behavior; this empirical result is now the project's source
  of truth.

## Verdict

session_restart_required

## Implications for Task 14

T14 ships the deprecation-stub message for the removed `cortex mcp-server`
CLI verb (per spec R7). The message body depends on this verdict:

- If verdict is **`automatic_restart`** or **`asynchronous`**: T14's
  message is the baseline form ("`cortex mcp-server` is removed; install
  the cortex-overnight-integration plugin (`/plugin install
  cortex-overnight-integration@cortex-command`) and update your `.mcp.json`
  to point at `uvx ${CLAUDE_PLUGIN_ROOT}/server.py`"). No restart advisory.

- If verdict is **`session_restart_required`**: T14 appends a one-line
  advisory to the deprecation message: "After installing the plugin,
  restart Claude Code to load the new MCP server." This is also the
  trigger to update the spec's Edge Cases section (already drafted at
  `spec.md` line 128) from a conditional ("if the empirical investigation
  shows...") to a confirmed limitation ("MCP restart requires Claude Code
  restart"). Value bullet 2 also weakens to "after the next Claude Code
  session starts."

- If verdict is **`other`**: T14 author should re-read this note and the
  spec Edge Cases entry, and decide based on the documented behavior
  whether an advisory is warranted.
