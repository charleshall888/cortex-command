# Research: gpg-signing-claude-code-sandbox

## Research Questions

1. What env vars does Claude Code inject into SessionStart hook processes — is TMPDIR the sandbox path or system default? → **Hooks receive `CLAUDE_PROJECT_DIR`, `CLAUDE_ENV_FILE`, and `CLAUDE_CODE_REMOTE`. TMPDIR is NOT set to the sandbox path in hook processes. Hooks run outside the sandbox and see the system TMPDIR (`/var/folders/...` on macOS). Confirmed by diagnostic log.**

2. What fields are in the SessionStart hook JSON input payload? → **`session_id`, `transcript_path`, `cwd`, `hook_event_name`, `source` (startup/resume/clear/compact), `model`, `agent_type` (optional). No TMPDIR field, no sandbox indicator.**

3. Can a hook discover the sandbox TMPDIR before it's used in the session? → **No. There is no documented mechanism. The sandbox TMPDIR is set only for sandboxed Bash tool calls within the session, not for hook processes. `CLAUDE_CODE_TMPDIR` env var (set externally before launching) overrides Claude's internal temp dir, but is separate from the sandboxed Bash TMPDIR and would require user shell config changes.**

4. Does GPG need write access to GNUPGHOME during signing with an Assuan redirect and `no-autostart`? → **Minimal. GPG reads `pubring.kbx`, `S.gpg-agent` (redirect), and `gpg.conf`. All signing delegates to the external agent via socket. Potential writes are `random_seed`, trustdb access locks, and pubring lock files. All three can be eliminated with `no-random-seed-file`, `no-auto-check-trustdb`, and `lock-never` in gpg.conf, making GNUPGHOME fully read-only during signing.**

5. What viable fix approaches exist, and what are their trade-offs? → **Three approaches identified; Approach A recommended. See Feasibility Assessment.**

6. Does any fix require modifying the sandbox write allowlist? → **No, if Approach A is taken. GPG options in gpg.conf eliminate all writes to GNUPGHOME, so a path outside the allowlist works.**

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

## Web & Documentation Research

- **Hook env vars:** SessionStart hooks receive `CLAUDE_PROJECT_DIR`, `CLAUDE_ENV_FILE`, `CLAUDE_CODE_REMOTE`. TMPDIR is NOT set to the sandbox value — hooks are unsandboxed processes. (Claude Code Hooks docs, confirmed post-August-2025)
- **CLAUDE_ENV_FILE:** Documented mechanism for injecting env vars into the Claude session from a hook. Works as of v2.1.45+ (partial fix for issue #15840). Known failure mode: session resume points to wrong env file (#24775).
- **GPG write-suppression options (GnuPG docs):**
  - `no-random-seed-file` — prevents writing `random_seed` after operations
  - `no-auto-check-trustdb` — skips automatic trustdb validation and its associated writes
  - `lock-never` — disables file locking; documented safe for single-process access
- **Assuan socket redirect:** `S.gpg-agent` file containing `%Assuan%\nsocket=<path>` redirects GPG to an external agent. All signing happens in the agent process; GPG itself makes no writes to GNUPGHOME beyond the suppressed ones above.
- **No native GPG signing support planned:** Issue #7711 closed as NOT_PLANNED (January 2026). The workaround is the canonical approach.

## Feasibility Assessment

| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|
| **A: Stable path + read-only gpg.conf** | S | `lock-never` safe only for single-process access (met by this use case); CLAUDE_ENV_FILE bug on resume (mitigated by not depending on it) | None — uses existing infrastructure |
| **B: Move setup into commit skill** | M | Adds gpg commands inside sandbox (needs `Bash(gpg *)` in allow list); first-commit latency per session; more complex skill | Add gpg to allow list |
| **C: Session-ID-based path via CLAUDE_ENV_FILE** | M | CLAUDE_ENV_FILE resume bug means signing fails on resumed sessions unless fallback detection is added | Claude Code v2.1.45+ |

**Recommended: Approach A.**

Changes required:
1. **Hook:** Remove TMPDIR sandbox detection (lines 28–32). Change `GNUPG_HOME` to `$HOME/.local/share/gnupg/claude-gnupghome`. Add `no-random-seed-file`, `no-auto-check-trustdb`, `lock-never` to gpg.conf (line 91). CLAUDE_ENV_FILE injection (lines 111–113) now reachable — keep it as a bonus.
2. **Commit skill step 5:** Change test path from `$TMPDIR/gnupghome/S.gpg-agent` to `$HOME/.local/share/gnupg/claude-gnupghome/S.gpg-agent`.
3. **Remove diagnostic logging** added to hook during investigation.

## Decision Records

### DR-1: Stable path vs. TMPDIR-relative path

- **Context:** The hook cannot know the sandbox TMPDIR because it runs in a different process. TMPDIR is set per-session for sandboxed Bash calls, not for hook processes.
- **Options considered:** (1) Stable `$HOME`-relative path; (2) CLAUDE_ENV_FILE to pass TMPDIR from hook to session; (3) CLAUDE_CODE_TMPDIR external env var; (4) Move setup into commit skill
- **Recommendation:** Stable `$HOME/.local/share/gnupg/claude-gnupghome/` path. Both the hook (outside sandbox) and sandboxed git commit can access it: the hook has full filesystem access; `~/.local/share/gnupg/` is not in the sandbox read deny list.
- **Trade-offs:** Gnupghome persists across sessions (not cleaned up per-session). Acceptable — the hook has a fast-path that skips rebuild if the key is already imported.

### DR-2: Write access to stable gnupghome path

- **Context:** Sandbox write allowlist does not include `~/.local/share/gnupg/`. If GPG needs to write to GNUPGHOME during signing, it would fail in the sandbox.
- **Options considered:** (1) Add path to allowWrite; (2) Suppress all writes via gpg.conf options
- **Recommendation:** Suppress writes with `no-random-seed-file`, `no-auto-check-trustdb`, `lock-never`. Avoids expanding the write allowlist (per the project's "minimal global allows" principle) and addresses the root write behavior rather than widening permissions.
- **Trade-offs:** `lock-never` is safe only when GNUPGHOME is accessed by a single process at a time. Git commit signing is inherently sequential, so this holds.

### DR-3: Dependency on CLAUDE_ENV_FILE

- **Context:** CLAUDE_ENV_FILE lets hooks inject env vars into the session. If used, the commit skill can read `$GNUPGHOME` directly without path detection. But CLAUDE_ENV_FILE has a known bug on session resume.
- **Options considered:** (1) Depend on CLAUDE_ENV_FILE entirely; (2) Use it as a bonus, keep commit skill detection path-based
- **Recommendation:** Keep the `test -f` detection in the commit skill, pointing at the stable path. Retain CLAUDE_ENV_FILE write as a bonus — it helps in interactive sessions but the skill doesn't fail if it's absent or broken.
- **Trade-offs:** Commit skill still needs the stable path hardcoded. Slightly more surface area to keep in sync if the path ever changes.

## Open Questions

- None. All questions answerable through research and codebase analysis. Approach A can be implemented without user input.
