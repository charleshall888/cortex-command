# Plan: build-setup-merge-local-skill

## Overview

Build a local project skill at `.claude/skills/setup-merge/` with a Python helper script (`merge_settings.py`) operating in two modes: `detect` (reads repo directories + both settings.json files, outputs complete diffs and hook specs as JSON to a tempfile) and `merge` (reads the tempfile + approved categories, performs atomic write). SKILL.md orchestrates the interactive UX by invoking the helper at key points and executing approved symlink commands directly. Data passes between detect and merge via tempfile to avoid shell argument size limits and quoting issues.

## Tasks

### Task 1: Create directory structure and SKILL.md stub

- **Files**: `.claude/skills/setup-merge/SKILL.md`, `.claude/skills/setup-merge/scripts/.gitkeep`
- **What**: Creates the project-local skill directory, a minimal SKILL.md with correct frontmatter, and the scripts subdirectory. The SKILL.md body will be filled in Tasks 6-8.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Location: `.claude/skills/setup-merge/` — project-local (Priority 3), never symlinked globally
  - Frontmatter required fields: `name: setup-merge`, `description: <trigger phrases>`, `disable-model-invocation: true` (prevents auto-triggering — this is a destructive interactive skill)
  - `${CLAUDE_SKILL_DIR}` is the variable to reference bundled scripts from SKILL.md at invocation time
  - The `scripts/` directory must exist before Tasks 2-5 add the Python helper
  - Pattern: follow `skills/lifecycle/SKILL.md` for stub structure; `disable-model-invocation: true` is critical
- **Verification**: Confirm `.claude/skills/setup-merge/SKILL.md` exists with valid frontmatter and `disable-model-invocation: true`. Confirm `scripts/` directory exists.
- **Status**: [x] complete

---

### Task 2: merge_settings.py — detect mode: symlink inventory

- **Files**: `.claude/skills/setup-merge/scripts/merge_settings.py`
- **What**: Creates the Python helper with a `detect` subcommand that reads the repo's directories at runtime, classifies each symlink target as new/update/conflict-*, and writes JSON output to a tempfile.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Repo root: `subprocess.run(["git", "rev-parse", "--show-toplevel"])` — do not use `os.getcwd()`
  - Tempfile path: `$TMPDIR/setup-merge-detect.json` (write here; SKILL.md reads path from stdout or a known location)
  - Runtime discovery sources (read at invocation, not hardcoded):
    - `bin/` → `~/.local/bin/<filename>` (all files; `ln -sf`)
    - `claude/reference/*.md` → `~/.claude/reference/<filename>` (`ln -sf`)
    - `skills/<name>/` → `~/.claude/skills/<name>` (all subdirs; `ln -sfn`)
    - `hooks/cortex-*` → `~/.claude/hooks/<filename>` (all files matching `cortex-*`, any extension; `ln -sf`)
    - `claude/rules/*.md` → `~/.claude/rules/<filename>` (`ln -sf`)
    - Two hardcoded: `hooks/cortex-notify.sh` → `~/.claude/notify.sh` (`ln -sf`); `claude/statusline.sh` → `~/.claude/statusline.sh` (`ln -sf`)
  - Classification logic per target path:
    - `not exists and not is_symlink` → `new`
    - `is_symlink and resolved == source_resolved` → `update`
    - `is_symlink and not exists` → `conflict-broken`
    - `is_symlink and resolved != source_resolved` → `conflict-wrong-target`
    - `is_file` → `conflict-file`
  - Output shape (partial — settings fields added in Task 3):
    ```
    {"symlinks": [{"source": "/abs/repo/path", "target": "/abs/target", "ln_flag": "-sf|-sfn", "status": "<class>"}]}
    ```
  - Write to tempfile; print tempfile path to stdout for SKILL.md to capture
  - Use `pathlib.Path` throughout; expand `~` with `Path.expanduser()`
- **Verification**: From repo root, run `python3 .claude/skills/setup-merge/scripts/merge_settings.py detect --repo-root .` and confirm it prints a tempfile path. Read the tempfile and confirm valid JSON with `symlinks` array. Verify `status` values are correct for a mix of installed/missing targets.
- **Status**: [x] complete

---

### Task 3: merge_settings.py — detect mode: settings.json diff and hook specs

- **Files**: `.claude/skills/setup-merge/scripts/merge_settings.py`
- **What**: Extends detect mode to read both the user's `~/.claude/settings.json` and the repo's `claude/settings.json`, capture mtime, compute per-category deltas, and embed full hook command objects (not just names) in the absent hook lists.
- **Depends on**: [2]
- **Complexity**: complex
- **Context**:
  - Read repo's `claude/settings.json` via `{repo_root}/claude/settings.json` — this is the canonical source of hook command strings
  - Capture mtime immediately after reading user's settings.json: `mtime = os.stat(user_settings_path).st_mtime`
  - Read `~/.claude/settings.local.json` as well (for apiKeyHelper presence check only — read-only)
  - Required hooks list (9 hooks): for each hook, identify it in the repo's `claude/settings.json` by searching for the script filename in command strings; record the full entry `{event_type, matcher, command, timeout?}`
  - Hook presence detection in user's settings.json: (event-type, matcher, command-substring) triple where command-substring = script filename appearing anywhere in command string; matcher for WorktreeCreate/WorktreeRemove is empty string
  - Absent hook output: full hook objects (not just names):
    ```
    "hooks_required": {
      "present": ["cortex-cleanup-session.sh"],
      "absent": [
        {"event_type": "SessionStart", "matcher": "", "command": "~/.claude/hooks/cortex-scan-lifecycle.sh"}
      ]
    }
    ```
  - Per-category deltas (string lists of what's missing):
    - `allow`: set difference between repo's `permissions.allow` and user's list
    - `deny`: set difference between repo's `permissions.deny` and user's list
    - `sandbox`: compare allowedDomains, allowUnixSockets, excludedCommands arrays; autoAllowBashIfSandboxed scalar
    - `statusLine`: compare command field; report full cortex statusLine object if absent/different
    - `plugins`: check `context7@claude-plugins-official` and `claude-md-management@claude-plugins-official` keys individually
    - `apiKeyHelper`: check both settings.json and settings.local.json
  - Output written to same tempfile (extend the JSON); final tempfile includes `mtime` and full `settings` block
  - Follow `claude/hooks/cortex-sync-permissions.py` pattern for JSON read style
- **Verification**: Run detect mode and read the tempfile. Confirm: mtime present; absent hooks contain full objects with event_type, matcher, command fields (not just names); allow/deny diffs reflect actual differences; apiKeyHelper checks both files.
- **Status**: [x] complete

---

### Task 4: merge_settings.py — merge mode: hook insertion function

- **Files**: `.claude/skills/setup-merge/scripts/merge_settings.py`
- **What**: Implements the `merge` subcommand's hook insertion function. Reads the detect tempfile (for hook specs and mtime), applies the insertion algorithm for each hook to add, returns the modified settings dict.
- **Depends on**: [3]
- **Complexity**: complex
- **Context**:
  - Function interface: `apply_hooks(settings: dict, hooks_to_add: list[dict]) -> dict`
    - `hooks_to_add`: list of objects from detect output absent lists (each has `event_type`, `matcher`, `command`, optional `timeout`)
    - Returns the modified settings dict (mutates in place, also returns for chaining)
  - Insertion algorithm for each hook spec:
    1. `event_arr = settings.setdefault("hooks", {}).setdefault(spec["event_type"], [])`
    2. Find first entry where `entry.get("matcher", "") == spec["matcher"]`
    3. If found: append `{type: "command", command: spec["command"]}` (plus timeout if present) to `entry["hooks"]`
    4. If not found: append `{matcher: spec["matcher"], hooks: [{type: "command", command: spec["command"]}]}` to `event_arr`; omit `matcher` key if empty string
  - merge subcommand entry point: `run_merge(detect_file_path, approved_optional_hooks, approvals_dict)`
    - Reads detect tempfile for: mtime, user settings, full hook specs
    - Calls `apply_hooks()` with required hooks (always) + approved optional hooks from detect absent list
    - Returns settings dict after hook insertion (non-hook categories applied in Task 5)
  - merge mode CLI: `merge_settings.py merge --detect-file <path> --optional-hooks '[...]' --approve-allow <bool> ...`
  - Command strings come from detect output (Task 3) — no separate settings.json read in merge mode
- **Verification**: Call `apply_hooks()` directly with a test settings dict and a list of hook specs; confirm: hook appended to existing matcher group if one exists; new group created if none; no duplicates after calling twice with same spec. This can be verified without running the full merge pipeline.
- **Status**: [x] complete

---

### Task 5: merge_settings.py — merge mode: non-hook categories, contradiction detection, atomic write

- **Files**: `.claude/skills/setup-merge/scripts/merge_settings.py`
- **What**: Completes the `run_merge()` function: applies non-hook category merges, runs bidirectional contradiction detection, and performs the atomic write with mtime guard.
- **Depends on**: [4]
- **Complexity**: simple
- **Context**:
  - `run_merge()` (from Task 4) extended to apply after `apply_hooks()`:
    - `permissions.allow`: extend list with absent entries from detect output (if approved)
    - `permissions.deny`: extend with absent entries (if approved); run reverse contradiction check first
    - `sandbox.network.allowedDomains`, `allowUnixSockets`, `excludedCommands`: extend arrays
    - `sandbox.autoAllowBashIfSandboxed`: set `true` if absent
    - `statusLine`: set full cortex object if absent/different (if approved)
    - `enabledPlugins.<key>`: add individual keys only; do NOT overwrite existing keys or `enableAllProjectMcpServers`
    - `apiKeyHelper`: set string value if absent from both files (if approved)
  - Contradiction detection — `extract_cmd(rule)` strips `Bash(` prefix and `)` suffix:
    - Forward (before writing allow entry): `fnmatch.fnmatch(extract_cmd(allow_entry), extract_cmd(deny_pattern))` for each existing deny
    - Reverse (before writing deny entry): `fnmatch.fnmatch(extract_cmd(existing_allow), extract_cmd(deny_entry))` for each existing allow
    - Literal entries only (no `*`); return contradictions list, skip contradicted entries
  - Personal scalars never touched: model, effortLevel, alwaysThinkingEnabled, skipDangerousModePermissionPrompt, cleanupPeriodDays, attribution, env, $schema, sandbox.enabled, sandbox.filesystem.*, enableAllProjectMcpServers
  - Atomic write:
    1. `current_mtime = os.stat(user_settings_path).st_mtime`; if `current_mtime != mtime_from_detect`, return `{"error": "mtime_changed"}`
    2. `json_str = json.dumps(settings, indent=2) + "\n"`
    3. `json.loads(json_str)` — validate before touching disk
    4. `tmp = tempfile.mkstemp(dir=settings_dir, suffix='.tmp')`; write + fsync
    5. `os.replace(tmp_path, user_settings_path)`
  - Return `{"ok": true, "contradictions": [...], "merged": [...]}` or `{"error": "mtime_changed"|"json_invalid"}`
- **Verification**: Run full merge cycle with a mix of approved/declined categories. Confirm: mtime check fires if file manually modified between detect and merge calls; contradictions appear in output and not written; personal scalars unchanged; run detect+merge twice (idempotency — second merge shows no changes).
- **Status**: [x] complete

---

### Task 6: SKILL.md — startup and safety guards

- **Files**: `.claude/skills/setup-merge/SKILL.md`
- **What**: Writes the first section of SKILL.md: safety guard checks, invocation of detect mode, and display of the summary table.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**:
  - Safety guards (run first, before any other action):
    - Symlink guard: `python3 -c "import pathlib; exit(0 if pathlib.Path('~/.claude/settings.json').expanduser().is_symlink() else 1)"` → if exits 0, halt with message from spec req 4
    - Worktree guard: compare `git rev-parse --git-dir` vs `git rev-parse --git-common-dir` → if different, halt with message from spec req 5
    - Sandbox warning: check `$TMPDIR` starts with `/private/tmp/claude` or `/tmp/claude` → if true, display warning from spec req 6 before proceeding
  - Detect invocation: `DETECT_FILE=$(python3 ${CLAUDE_SKILL_DIR}/scripts/merge_settings.py detect --repo-root $(git rev-parse --show-toplevel) --settings ~/.claude/settings.json)` → DETECT_FILE holds the tempfile path
  - Read the tempfile JSON to present the summary table (one row per symlink conflict count by type; one row per settings category)
  - Store DETECT_FILE path for use in Tasks 7 and 8
- **Verification**: Note — skill discovery is session-scoped; SKILL.md changes are not available until a new Claude session is started in the cortex-command directory. To verify Task 6, start a new session and run `/setup-merge`. Test each guard condition in isolation: symlink guard by temporarily symlinking `~/.claude/settings.json`; worktree guard from a git worktree. Confirm detect output is displayed as a summary table.
- **Status**: [x] complete

---

### Task 7: SKILL.md — symlink conflict resolution flow

- **Files**: `.claude/skills/setup-merge/SKILL.md`
- **What**: Writes the symlink conflict resolution section of SKILL.md. For each conflict in the detect output, presents appropriate information per conflict type and prompts Y/n. Executes approved ln commands.
- **Depends on**: [6]
- **Complexity**: simple
- **Context**:
  - Read symlinks from detect tempfile JSON; iterate conflicts where status ∈ {conflict-broken, conflict-wrong-target, conflict-file}
  - Per conflict type display:
    - `conflict-broken`: "Broken symlink at `{target}` (points to nothing). Replace with cortex-command symlink to `{source}`? [Y/n]"
    - `conflict-wrong-target`: "Symlink at `{target}` currently points to `{current_target}`. Repoint to `{source}`? [Y/n]"
    - `conflict-file`: run `diff {target} {source}` if available (fall back to inode/size info); warn "This file will be replaced by a symlink. This is destructive — the original file will be lost. Replace? [Y/n]"
  - On Y: `ln {ln_flag} {source} {target}` (using ln_flag from detect JSON — `-sf` or `-sfn`)
  - New/update targets: silently execute without prompting; count for summary
  - Order: process all symlink conflicts before presenting settings categories
- **Verification**: Note — requires a new Claude session after SKILL.md changes (session-scoped skill discovery). Start a new session, then create a test conflict: `touch ~/.local/bin/test-conflict-file` and run `/setup-merge`. Confirm correct conflict type detected, Y installs symlink, N skips. After verification, `rm ~/.local/bin/test-conflict-file`. Confirm `ln -sfn` used for skill directories, `ln -sf` for files.
- **Status**: [x] complete

---

### Task 8: SKILL.md — settings.json interactive flow and merge invocation

- **Files**: `.claude/skills/setup-merge/SKILL.md`
- **What**: Writes the settings.json interactive section of SKILL.md: required hooks section, optional hooks Y/n, per-category settings Y/n, merge invocation, and final summary report.
- **Depends on**: [5, 7]
- **Complexity**: complex
- **Context**:
  - Required hooks: display list of absent required hooks from detect tempfile; state they will be merged unconditionally; no Y/n
  - Optional hooks Y/n (3 hooks): display each with description from spec req 17; collect Y/N per hook name
  - Per-category settings Y/n (6 categories): for each with non-empty absent list, show delta + current value + advisory; collect Y/n
  - `apiKeyHelper`: also check that `~/.claude/get-api-key.sh` exists before offering; skip with note if stub not deployed
  - Merge invocation (using tempfile — no ARG_MAX risk, no quoting issue):
    ```
    python3 ${CLAUDE_SKILL_DIR}/scripts/merge_settings.py merge \
      --detect-file "$DETECT_FILE" \
      --optional-hooks '[<approved hook names as JSON array>]' \
      --approve-allow <true|false> \
      --approve-deny <true|false> \
      --approve-sandbox <true|false> \
      --approve-statusline <true|false> \
      --approve-plugins <true|false> \
      --approve-apikey <true|false>
    ```
  - Parse merge output JSON:
    - `{"ok": true}`: display contradictions if any; proceed to summary
    - `{"error": "mtime_changed"}`: "settings.json was modified during this session — re-run /setup-merge"
    - `{"error": "json_invalid"}`: display and halt
  - Summary report (spec req 28): symlinks installed/skipped, categories merged/skipped, all contradictions both directions, skipped regular-file conflicts
- **Verification**: Note — requires a new Claude session after SKILL.md changes. Start a new session, run full `/setup-merge` flow using a copy of settings.json with a subset of cortex-command entries pre-installed. Confirm: required hooks merged silently, optional hooks prompted, categories with no delta show "✓ already installed", approved categories written atomically, contradictions surface in both directions, summary counts accurate. Run again without changes to confirm idempotency.
- **Status**: [x] complete

---

## Verification Strategy

1. **Unit verification** (after Task 5): run `merge_settings.py detect` against the live system; read tempfile, validate JSON schema; call `apply_hooks()` directly in a Python REPL with test inputs; run `merge_settings.py merge` with all categories approved; inspect result.
2. **Guard verification** (after Task 6): start fresh Claude session, test each safety guard condition in isolation.
3. **End-to-end** (after Task 8): start fresh Claude session in cortex-command repo, run `/setup-merge` against a test copy of settings.json. Verify conflict detection, UX accuracy, atomic write, idempotency.
4. **Project config check**: confirm output settings.json remains valid JSON: `python3 -c "import json; json.load(open('~/.claude/settings.json'))"`.
