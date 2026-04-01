# Specification: Security & Share-Readiness Audit

## Problem Statement

The cortex-command repo will be shared publicly for others to clone and use as a turnkey AI workflow framework. Before release, it needs: (1) security hardening of code execution paths in hooks, scripts, and the overnight runner, and (2) share-readiness fixes so `just setup` works from a fresh clone with minimal friction. The threat model for security fixes is accidental injection (trusted operator, malformed inputs) — not malicious operator defense.

## Requirements

1. **Fix shell variable injection in scan-lifecycle.sh:10**: Quote SESSION_ID in the export statement to prevent shell metacharacter expansion when the env file is sourced. SESSION_ID is a UUID from Claude Code's session framework, so simple single-quote wrapping is sufficient.
   - Acceptance: `echo "export LIFECYCLE_SESSION_ID='$SESSION_ID'"` or equivalent safe quoting.

2. **Harden test command execution in runner.sh and merge.py**: Shell interpretation is unavoidable for test commands (they legitimately contain `&&`, pipes, subshells). The fix is input validation and safe quoting, not eliminating shell execution. Replace `eval "$TEST_COMMAND"` in runner.sh with `bash -c "$TEST_COMMAND"` (removes eval's additional expansion pass) and add basic validation (reject empty commands, log the command being executed). For merge.py, replace `subprocess.run(test_command, shell=True)` with `subprocess.run(["sh", "-c", test_command])` for consistency.
   - Acceptance: Test commands with `&&`, pipes, and subshells still work. `eval` is no longer used. Commands are logged before execution.

3. **Systematically fix shell variable interpolation in python3 -c calls**: runner.sh has ~50 `python3 -c` invocations that interpolate shell variables (`$STATE_PATH`, `$SESSION_ID`, `$REPO_PATH`, `$PR_URL`, `$EVENTS_PATH`, etc.) directly into Python string literals. Any variable containing a single quote breaks the Python code. Fix all instances by passing values via environment variables (`os.environ['VAR']`) or command-line arguments (`sys.argv`). Also fix sed template substitutions (e.g., `fill_prompt` at ~line 357) where file-path variables could contain sed metacharacters.
   - Acceptance: No `python3 -c` call embeds shell variables directly in Python string literals. No `sed` substitution uses path variables that could contain the delimiter character. A grep for the pattern `python3 -c ".*\$` in runner.sh returns zero matches.

4. **Auto-detect clone path in `just setup`**: Detect the repo's location and update the sandbox `allowWrite` path. Since `claude/settings.json` is symlinked and git-tracked, do not modify the repo copy directly (that dirties git status). Instead, write the path to `claude/settings.local.json` or use the existing `.claude/settings.local.json` override mechanism.
   - Acceptance: After `just setup`, the sandbox allows writes to the correct lifecycle/sessions path regardless of clone location. `git status` is not dirtied by setup. Re-running setup is idempotent.

5. **Print CORTEX_COMMAND_ROOT export line**: `just setup` prints a ready-to-copy `export CORTEX_COMMAND_ROOT="..."` line with the correct path pre-filled. Do not auto-append to shell config — this conflicts with the sandbox deny rules on .zshrc/.bashrc and the non-requirement about not auto-installing.
   - Acceptance: User sees the exact export line to add to their shell config. Path is correct for their clone location.

6. **Add `just verify-setup` recipe**: Extends `just check-symlinks` with additional checks. Specific checks: (a) all symlinks valid (existing check-symlinks logic), (b) `python3 --version` ≥ 3.12, (c) `uv` available, (d) `claude` CLI available, (e) `CORTEX_COMMAND_ROOT` is set and points to this repo, (f) `just test` passes.
   - Acceptance: `just verify-setup` exits 0 on a healthy install. Each failing check prints a specific, actionable error message. Succeeding checks are silent or minimal.

7. **README stays macOS-primary**: Add a brief note near the top linking to `docs/setup.md` for Linux/Windows users. Do not restructure the README for multi-platform.
   - Acceptance: Non-macOS users can find their setup path within the first few paragraphs.

## Non-Requirements

- Defending against malicious operators — the threat model is accidental injection only.
- Eliminating shell interpretation for test commands — complex test commands require it.
- Multi-platform parity in the README — macOS is primary, other OSes get a docs link.
- Auto-installing dependencies (just, uv, Python) — document them, don't install them.
- Auto-appending to shell config files — conflicts with sandbox deny rules.
- Fixing the `terminal-notifier` silent failure — it's optional and documented in docs/setup.md.
- Fixing the notify-remote.sh unquoted variable — low-impact logging concern.
- Rewriting the symlink architecture — it works, just needs the path auto-detection.

## Edge Cases

- **Clone path contains spaces**: Auto-detect must handle paths with spaces (e.g., `/Users/Jane Doe/cortex-command`). Quote all path references.
- **Clone path not under $HOME**: Some users may clone to `/opt/` or `/srv/`. Auto-detect should work with any absolute path.
- **settings.local.json already exists**: The path write must merge, not overwrite. Preserve existing local overrides.
- **SESSION_ID format**: Claude Code session IDs are UUIDs (alphanumeric + hyphens). Simple single-quote wrapping is sufficient. The edge case of single quotes in SESSION_ID is theoretical but defended against by the quoting approach.
- **Test command is empty or "none"**: merge.py already handles this (returns passing TestResult). The fix must preserve this behavior.
- **Re-running setup**: `just setup` should be idempotent — running it twice should not corrupt settings or create duplicates.
- **python3 -c variables with single quotes**: Paths like `/Users/Jane's Mac/project` would break Python string literals. The env var approach handles this correctly.
- **sed delimiter collision**: Paths containing `|` (common sed delimiter in fill_prompt) would corrupt template substitution. Use a delimiter not found in file paths, or use python for template filling.

## Technical Constraints

- settings.json must remain valid JSON after path rewriting (no shell variable expansion in JSON — must be a literal path).
- Test command execution must still support complex commands (e.g., `cd subdir && python -m pytest`).
- All fixes must work within the existing sandbox configuration.
- Do not change shebangs or introduce dependencies on shells not already used by each script.
- Python fixes must maintain compatibility with Python 3.12+.
- settings.local.json (if used for path override) must follow Claude Code's settings merge semantics.
