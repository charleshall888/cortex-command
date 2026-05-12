# Research: gpg-signing-claude-code-sandbox

> **Correction (2026-04-13):** This research missed `claude/settings.json` → `sandbox.excludedCommands: ["gh:*", "git:*", "WebFetch", "WebSearch"]`. `git:*` excludes the entire git process tree (including pre-commit hooks and spawned `gpg -bsau`) from the Seatbelt sandbox. Direct `gpg` invocations from Bash are sandboxed; git-spawned gpg is not. Signing has always worked via the host `~/.gnupg/` and standard `S.gpg-agent` socket — the TMPDIR-relative `GNUPGHOME`, the `S.gpg-agent.sandbox` extra socket, and the `cortex-setup-gpg-sandbox-home.sh` hook were all dead code solving a non-problem. Scaffolding was deleted; #081 closed on that basis. Questions and decision records below are preserved for posterity but should not be read as actionable.

## Research Questions

1. What env vars does Claude Code inject into SessionStart hook processes — is TMPDIR the sandbox path or system default? → **Hooks receive `CLAUDE_PROJECT_DIR`, `CLAUDE_ENV_FILE`, and `CLAUDE_CODE_REMOTE`. TMPDIR is NOT set to the sandbox path in hook processes. Hooks run outside the sandbox and see the system TMPDIR (`/var/folders/...` on macOS). Confirmed by diagnostic log.**

2. What fields are in the SessionStart hook JSON input payload? → **`session_id`, `transcript_path`, `cwd`, `hook_event_name`, `source` (startup/resume/clear/compact), `model`, `agent_type` (optional). No TMPDIR field, no sandbox indicator.**

3. Can a hook discover the sandbox TMPDIR before it's used in the session? → **No. There is no documented mechanism. The sandbox TMPDIR is set only for sandboxed Bash tool calls within the session, not for hook processes. `CLAUDE_CODE_TMPDIR` env var (set externally before launching) overrides Claude's internal temp dir, but is separate from the sandboxed Bash TMPDIR and would require user shell config changes.**

4. Does GPG need write access to GNUPGHOME during signing with an Assuan redirect and `no-autostart`? → **Minimal. GPG reads `pubring.kbx`, `S.gpg-agent` (redirect), and `gpg.conf`. All signing delegates to the external agent via socket. Potential writes are `random_seed`, trustdb access locks, and pubring lock files. All three can be eliminated with `no-random-seed-file`, `no-auto-check-trustdb`, and `lock-never` in gpg.conf — but `lock-never` disables all GnuPG locking globally, including keybox locking during `--import`, which is unsafe under concurrent access. See DR-2.**

5. What viable fix approaches exist, and what are their trade-offs? → **Three approaches identified. Approach A (stable path) has unacknowledged concurrent-access and post-reboot failure modes; Approach C (per-session path via CLAUDE_ENV_FILE) avoids both. See updated Feasibility Assessment and Decision Records.**

6. Does any fix require modifying the sandbox write allowlist? → **No, if writes are suppressed via gpg.conf. But write suppression via `lock-never` is unsafe under concurrent overnight dispatch. See DR-2.**

## Codebase Analysis

**Root cause (confirmed):**
- `cortex-setup-gpg-sandbox-home.sh` line 30–32: exits early when `$TMPDIR` does not match `/private/tmp/claude*` or `/tmp/claude*`
- At SessionStart, TMPDIR is the macOS system default (`/var/folders/...`) — confirmed by diagnostic log
- Result: hook body never runs; `$TMPDIR/gnupghome/` is never created
- Commit skill step 5 tests `$TMPDIR/gnupghome/S.gpg-agent` inside a sandboxed Bash call where TMPDIR is `/tmp/claude-503` — always MISSING

**Current gnupghome path:** `$TMPDIR/gnupghome` (set at hook line 43). Never exists because the hook always exits early.

**CLAUDE_ENV_FILE injection:** Hook lines 111–113 write `export GNUPGHOME=<path>` to CLAUDE_ENV_FILE. This code is correct in principle but unreachable due to the early exit. Available since Claude Code v2.1.45+; has known bugs on session resume (issue #24775) and does not work for plugin-installed hooks (#11649).

**Current gpg.conf content:** `no-autostart` only. Does not include write-suppression options.

**Extra socket path:** `$HOME/.local/share/gnupg/S.gpg-agent.sandbox` — already in `sandbox.network.allowUnixSockets`.

**Signing key file:** `$HOME/.local/share/gnupg/signing-key.pgp` — exists, managed by `just setup-gpg-sandbox`.

**Sandbox write allowlist:** Only `~/cortex-command/lifecycle/sessions/` and `~/.cache/uv`. Neither `~/.local/share/gnupg/` nor any claude-gnupghome path is listed.

**Sandbox read restrictions:** Deny list does not include `~/.local/share/gnupg/`. Sandboxed commands can read from there.

**Commit skill (current):** Step 5 is now `test -f "$TMPDIR/gnupghome/S.gpg-agent" && echo "GNUPGHOME=$TMPDIR/gnupghome"` — tests and prints a TMPDIR-relative path.

**Hook fast-path (line 81–83):** `if GNUPGHOME="$GNUPG_HOME" gpg --list-keys "$SIGNING_KEY" >/dev/null 2>&1; then exit 0; fi` — skips rebuild if key already imported. This is an unlocked check-then-act: not a concurrency primitive. It skips keybox rebuild but does NOT re-verify that `S.gpg-agent.sandbox` (the external socket) is live.

**S.gpg-agent file lifetime:** Written once by the hook (line 107); a plain file — not a socket. Persists indefinitely. The socket it redirects to (`S.gpg-agent.sandbox`) is ephemeral — disappears on reboot or gpg-agent exit. Current TMPDIR-based design is self-healing: redirect file vanishes with TMPDIR, hook always recreates it after verifying socket liveness at line 53. Stable-path design breaks this: redirect file outlives the agent.

**Overnight runner concurrency:** Dispatches multiple concurrent Claude Code worktree sessions. Worktrees isolate working trees, not `$HOME`. All parallel agents share the same `$HOME/.local/share/gnupg/` directory. Multiple simultaneous SessionStart hooks and concurrent `git commit -S` calls are expected under overnight parallel dispatch.

## Web & Documentation Research

- **Hook env vars:** SessionStart hooks receive `CLAUDE_PROJECT_DIR`, `CLAUDE_ENV_FILE`, `CLAUDE_CODE_REMOTE`. TMPDIR is NOT set to the sandbox value — hooks are unsandboxed processes. (Claude Code Hooks docs, confirmed post-August-2025)
- **CLAUDE_ENV_FILE:** Documented mechanism for injecting env vars into the Claude session from a hook. Works as of v2.1.45+ (partial fix for issue #15840). Known failure mode: session resume points to wrong env file (#24775).
- **GPG write-suppression options (GnuPG docs):**
  - `no-random-seed-file` — prevents writing `random_seed` after operations
  - `no-auto-check-trustdb` — skips automatic trustdb validation and its associated writes
  - `lock-never` — disables file locking; documented safe **only for single-process access**; disables locking globally including during `gpg --import`, making concurrent import unsafe
- **Assuan socket redirect:** `S.gpg-agent` file containing `%Assuan%\nsocket=<path>` redirects GPG to an external agent. All signing happens in the agent process. When the redirect target socket is absent (agent dead), GPG emits `gpg: can't connect to the agent: IPC connect call failed` — a hard error, not a graceful fallback.
- **No native GPG signing support planned:** Issue #7711 closed as NOT_PLANNED (January 2026). The workaround is the canonical approach.

## Feasibility Assessment

| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|
| **A: Stable shared path + read-only gpg.conf** | S | `lock-never` unsafe under concurrent overnight dispatch (concurrent signing + import tears `pubring.kbx`); hook rebuild is unlocked check-then-act (concurrent hooks can destroy each other's gnupghome); `S.gpg-agent` redirect file outlives the agent (post-reboot: stale redirect → hard IPC error mid-commit, worse than current unsigned-commit fallback); worst-case failure regresses | Overnight parallel dispatch must be excluded or serialized — unverified |
| **B: Move setup into commit skill** | M | Adds gpg commands inside sandbox (needs `Bash(gpg *)` in allow list); first-commit latency per session; more complex skill | Add gpg to allow list |
| **C: Per-session path via CLAUDE_ENV_FILE** | M | CLAUDE_ENV_FILE resume bug (#24775): signing unavailable in resumed sessions; not a regression (current state: signing always unavailable) | Claude Code v2.1.45+ |

**No clear recommendation.** Approach A introduces concurrent-access and post-reboot regressions not present in the current (broken) state. Approach C avoids both but requires CLAUDE_ENV_FILE reliability investigation. The right choice depends on: (1) whether concurrent overnight signing is a real use case or can be serialized; (2) whether CLAUDE_ENV_FILE is reliable enough in the current Claude Code version.

## Decision Records

### DR-1: Stable path vs. TMPDIR-relative path

- **Context:** The hook cannot know the sandbox TMPDIR because it runs in a different process. TMPDIR is set per-session for sandboxed Bash calls, not for hook processes.
- **Options considered:** (1) Stable `$HOME`-relative path; (2) CLAUDE_ENV_FILE to pass a per-session path; (3) CLAUDE_CODE_TMPDIR external env var; (4) Move setup into commit skill
- **Initial recommendation:** Stable `$HOME/.local/share/gnupg/claude-gnupghome/` path.
- **Revised after critical review:** The "persistence is acceptable" judgment was incomplete. Persistence introduces: (a) unlocked concurrent hook rebuild race (`rm -rf` + check-then-act without mutex); (b) stale Assuan redirect after reboot (redirect file persists, socket disappears, fast-path skips liveness check, commit errors hard). A per-session path (Approach C) avoids both. If Approach A is chosen, the hook needs: `flock` around the rebuild section; a liveness check for `S.gpg-agent.sandbox` in the fast-path (not just key import check).
- **Trade-offs (stable path):** Concurrent access requires locking; post-reboot requires liveness re-verification; path must stay in sync between hook and commit skill.
- **Trade-offs (per-session path):** CLAUDE_ENV_FILE resume bug means signing unavailable on `--continue` sessions. Not a regression from current state (signing is currently always unavailable).

### DR-2: Write access to stable gnupghome path

- **Context:** Sandbox write allowlist does not include `~/.local/share/gnupg/`. If GPG writes to GNUPGHOME during signing in the sandbox, it would fail.
- **Options considered:** (1) Add path to allowWrite; (2) Suppress all writes via gpg.conf options
- **Initial recommendation:** Suppress writes with `no-random-seed-file`, `no-auto-check-trustdb`, `lock-never`.
- **Revised after critical review:** `lock-never` disables GnuPG locking globally — including during `gpg --import` in the hook. Under concurrent overnight dispatch, two hooks importing simultaneously can corrupt `pubring.kbx`. The "inherently sequential" safety justification is false for this project. If Approach A is taken, `lock-never` must be accompanied by external mutual exclusion (e.g., `flock`) around all GPG operations on this GNUPGHOME, or the stable path must be abandoned for a per-session path that doesn't require `lock-never` to be safe.
- **Trade-offs:** Write suppression via `lock-never` and concurrency safety are in direct conflict for this project.

### DR-3: Dependency on CLAUDE_ENV_FILE

- **Context:** CLAUDE_ENV_FILE lets hooks inject env vars into the session. CLAUDE_ENV_FILE has a known bug on session resume.
- **Options considered:** (1) Depend on CLAUDE_ENV_FILE entirely; (2) Use it as a bonus, keep commit skill detection path-based
- **Initial recommendation:** Keep `test -f` detection in commit skill, CLAUDE_ENV_FILE as bonus.
- **Revised after critical review:** The `test -f` detection on a stable path has a liveness gap: it returns true whenever the redirect file exists, regardless of whether the underlying agent is running. This produces a hard IPC error on post-reboot commits, worse than the current soft failure. Two mitigations if stable path is used: (a) commit skill step 5 should probe agent liveness (e.g., `gpg-connect-agent /bye 2>/dev/null`) before trusting the redirect; (b) hook fast-path should re-verify socket liveness, not just key import status. Alternatively, using CLAUDE_ENV_FILE as the primary detection mechanism (no path hardcoded in commit skill) avoids the stale-redirect problem entirely: if the env var isn't set (hook didn't run or CLAUDE_ENV_FILE failed), the commit skill falls back to no signing — same soft failure as today.
- **Trade-offs:** Path-based detection is fragile (liveness gap); CLAUDE_ENV_FILE-based detection has a resume blind spot but no liveness gap.

## Open Questions

- **Is concurrent GPG signing actually a use case for the overnight runner?** If overnight agents commit sequentially (each feature finishes before the next starts), `lock-never` concurrency risk is moot and Approach A with `flock` on the hook rebuild is sufficient. If agents commit in parallel (worktree-parallel mode), a per-session GNUPGHOME or external serialization is required.
- **Is CLAUDE_ENV_FILE reliable at current Claude Code version?** The research confirmed v2.1.45+ partially fixes issue #15840. Whether it is reliable enough for Approach C to be the primary mechanism requires a one-session verification test.
- **What is the right failure mode when gpg-agent is not running?** Should the commit skill detect this and skip the GNUPGHOME prefix (soft fallback), or error explicitly? The current design produces a hard error; a liveness probe in step 5 would restore soft-fallback behavior.
