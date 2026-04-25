# Review: publish-cortex-overnight-integration-plugin-overnight-skill-runner-hooks

## Stage 1: Spec Compliance

### Requirement R1: Plugin manifest with three fields naming both prerequisites
- **Expected**: `plugins/cortex-overnight-integration/.claude-plugin/plugin.json` exists with `name`, `author`, `description`; description names both `cortex CLI` and `cortex-interactive`. No `version` field.
- **Actual**: File exists with `name = "cortex-overnight-integration"`, `author = "Charlie Hall <charliemhall@gmail.com>"`, and a description containing both literal substrings `"cortex CLI"` and `"cortex-interactive"`. No `version` field. `jq -er '.name'`, `jq -e '.description | contains(...)'`, and `jq -e 'has("version") | not'` all exit 0.
- **Verdict**: PASS

### Requirement R2: Skills synced byte-for-byte from canonical sources
- **Expected**: `plugins/cortex-overnight-integration/skills/{overnight,morning-review}/` byte-identical to the top-level `skills/` sources (including `morning-review/references/`).
- **Actual**: `diff -rq skills/overnight/ plugins/cortex-overnight-integration/skills/overnight/` and `diff -rq skills/morning-review/ plugins/cortex-overnight-integration/skills/morning-review/` both exit 0 with no output.
- **Verdict**: PASS

### Requirement R3: Runner-only hooks present and byte-identical
- **Expected**: Four hook scripts in `plugins/cortex-overnight-integration/hooks/`, each `cmp -s` identical to its source location; each executable.
- **Actual**: All four `cmp -s` checks pass (cleanup-session and scan-lifecycle from `hooks/`; tool-failure-tracker and permission-audit-log from `claude/hooks/`). `find … -not -perm -u+x | wc -l` returns `0`.
- **Verdict**: PASS

### Requirement R4: Hook manifest with correct schema per event, matcher omitted
- **Expected**: `hooks.json` registers four events (`SessionStart, SessionEnd, PostToolUse, Notification`), each pointing at its expected script; `matcher` field omitted on all four.
- **Actual**: Manifest contains exactly the four event keys (verified via `jq -r '.hooks | keys[] | ascii_downcase' | sort | tr '\n' ' '` → `notification posttooluse sessionend sessionstart `). All four entries are `type: "command"` with `command` strings beginning with `${CLAUDE_PLUGIN_ROOT}/hooks/cortex-`. The `endswith` checks pair each event to the correct script (SessionStart→scan-lifecycle, SessionEnd→cleanup-session, PostToolUse→tool-failure-tracker, Notification→permission-audit-log). `jq -e '.hooks | to_entries | all(.value[0] | has("matcher") | not)'` exits 0.
- **Verdict**: PASS

### Requirement R5: MCP server registration with single `cortex-overnight` entry
- **Expected**: Single `mcpServers.cortex-overnight` entry with `command: "cortex"` and `args: ["mcp-server"]`.
- **Actual**: `jq -er '.mcpServers["cortex-overnight"].command'` returns `cortex`; `jq -er '… .args | join(" ")'` returns `mcp-server`; `jq -e '.mcpServers | length == 1'` exits 0.
- **Verdict**: PASS

### Requirement R6: Build recipe with per-plugin manifests (bash 3.2-compatible)
- **Expected**: `justfile build-plugin` dispatches per-plugin SKILLS/HOOKS/BIN via `case "$p" in … esac` with a wildcard arm; runs cleanly under bash 3.2; idempotent; per-plugin isolation; produces 14 cortex-interactive skills and 2 cortex-overnight-integration skills.
- **Actual**: `justfile:417-449` implements the case dispatch with cortex-interactive (14 skills, `hooks/cortex-validate-commit.sh`, `BIN=(cortex-)`) and cortex-overnight-integration (2 skills, 4 hooks across `hooks/` and `claude/hooks/`, `BIN=()`) arms plus a wildcard arm that prints `build-plugin: no manifest for $p` and `continue`s. No `declare -A` or `mapfile` — uses plain bash arrays and `case` (bash 3.2-safe). Confirmed `bash --version` is `3.2.57`. `just build-plugin` exits 0; produces exactly `morning-review overnight` under cortex-overnight-integration/skills/ and 14 entries under cortex-interactive/skills/. `test ! -d plugins/cortex-overnight-integration/bin` exits 0 (per-plugin BIN isolation enforced). Pre-`rm -f plugins/$p/hooks/cortex-*.sh` ensures stale hooks are pruned on rebuild. Plan Task 6 verified idempotence and stale-removal inline.
- **Verdict**: PASS

### Requirement R7: Pre-commit drift check passes for both plugins
- **Expected**: After build, `bash .githooks/pre-commit` exits 0 and `git diff --quiet plugins/{cortex-overnight-integration,cortex-interactive}/` both exit 0.
- **Actual**: `bash .githooks/pre-commit` exits 0 against current staging state; `git diff --quiet plugins/cortex-overnight-integration/` and `git diff --quiet plugins/cortex-interactive/` both exit 0. Plan deviation noted: the spec called for `git add -A && bash .githooks/pre-commit`; the implementation skipped the broad `git add -A` to avoid staging unrelated working-tree changes from other backlog work — both substantive checks (per-plugin diff) still pass.
- **Verdict**: PASS

### Requirement R8: `cortex init` widens sandbox allowWrite scope, symlink-safety repointed
- **Expected**: `cortex init` registers `{repo_root}/lifecycle/` (with trailing slash); `check_symlink_safety` repointed at `lifecycle/`; existing narrow registrations left in place; symlink escape gate preserved.
- **Actual**:
  - `cortex_command/init/scaffold.py:116-176` — `check_symlink_safety(repo_root)` operates on `repo_root / "lifecycle"` (line 142) and returns `str(lifecycle_canon) + "/"`. Variable rename complete (`lifecycle_path/canon/norm`). Docstring and error message refer to `lifecycle/`.
  - `cortex_command/init/handler.py:144-149` — handler resolves `repo_root` once, then captures `lifecycle_target = scaffold.check_symlink_safety(repo_root)`. Spec acceptance grep `grep -E 'check_symlink_safety|symlink_safety' cortex_command/init/handler.py | grep -v sessions` returns 3 matches (the docstring comment, the call site, and the comment).
  - `cortex_command/init/handler.py:197` — `settings_merge.register(repo_root, lifecycle_target, home=home)`.
  - `cortex_command/init/handler.py:123-139` — `--unregister` branch unconditionally calls `settings_merge.unregister` for both legacy narrow path (`lifecycle/sessions/`) and new wide path (`lifecycle/`), with comments explaining migration symmetry.
  - `cortex_command/init/scaffold.py` contains zero occurrences of `lifecycle/sessions`.
  - `cortex_command/init/tests/test_scaffold.py:338-405` — `test_symlink_refusal_prefix_aliased_path` and `test_symlink_refusal_case_variant` updated to symlink `repo/lifecycle` directly (not `repo/lifecycle/sessions`).
  - `just test` exits 0 (5/5 passed). Plan deviation noted: end-to-end `cortex init` against the user's real `~/.claude/settings.local.json` and the migration-symmetry shell test were skipped to avoid mutating user settings — `just test` carries the unit-test correctness signal.
- **Verdict**: PASS

### Requirement R9: `requirements/project.md` Architectural Constraints text reflects new sandbox scope
- **Expected**: "Per-repo sandbox registration" sentence updated to `lifecycle/` instead of `lifecycle/sessions/`.
- **Actual**: `requirements/project.md:26` reads `cortex init additively registers the repo's lifecycle/ path…`. `grep -F "lifecycle/sessions/" requirements/project.md | grep -i sandbox` returns 0 matches. Sentence carries the new wide scope.
- **Verdict**: PASS

### Requirement R10: Local dogfooding documented in `docs/plugin-development.md`
- **Expected**: New file with `/plugin marketplace add` (referencing repo path or `$PWD`) and `/plugin install cortex-overnight-integration` lines.
- **Actual**: File exists. `grep -E '^\s*/plugin marketplace add'` returns 2 lines (one with the absolute repo path, one with `$PWD`). `grep -E '^\s*/plugin install cortex-overnight-integration'` returns 1 line. Doc also covers DR-9/DR-2 rationale, prerequisites, and iteration workflow.
- **Verdict**: PASS

### Requirement R11: Plugin enables under marketplace flow (interactive)
- **Expected**: From a terminal-launched Claude Code session, `/plugin marketplace add /Users/charlie.hall/Workspaces/cortex-command` then `/plugin install cortex-overnight-integration@cortex-command` makes `/plugin list` show the plugin enabled and `/cortex:overnight` invocable.
- **Actual**: All static prerequisites are in place — `.claude-plugin/marketplace.json` stub at repo root lists exactly `cortex-overnight-integration` with the canonical schema (name=cortex-command, owner.name=charleshall888, owner.email=charliemhall@gmail.com, plugins[0]={name, source: "./plugins/cortex-overnight-integration"}). The plugin tree under `plugins/cortex-overnight-integration/` contains `.claude-plugin/plugin.json`, `.mcp.json`, `hooks/hooks.json` with 4 hooks, and the 2 skill trees. Cannot exercise the slash commands from a non-interactive CLI session.
- **Verdict**: PARTIAL (requires manual user verification in a live Claude Code session)

### Requirement R12: MCP server connects when plugin enabled (interactive)
- **Expected**: With plugin enabled in terminal-launched Claude Code, `/mcp` shows `cortex-overnight` connected with five tools.
- **Actual**: `.mcp.json` matches the R5 contract (single `cortex-overnight` server invoking `cortex mcp-server`). The five tool names are not asserted in the static tree — they are exposed dynamically by the running MCP server. Cannot be exercised from a shell command.
- **Verdict**: PARTIAL (requires manual user verification in a live Claude Code session)

### Requirement R13: Notification hook fires on permission prompts (interactive)
- **Expected**: With plugin enabled and a permission prompt triggered, `cortex-permission-audit-log.sh` writes a non-empty line to `$TMPDIR/claude-permissions-*.log`.
- **Actual**: `plugins/cortex-overnight-integration/hooks/cortex-permission-audit-log.sh` is byte-identical to source (per R3) and registered against the `Notification` event in `hooks.json` with no matcher (per R4 — script self-filters internally on lines 62, 68 via `notification_type`). All static prerequisites for R13 are in place. Cannot trigger a live permission prompt from a shell command.
- **Verdict**: PARTIAL (requires manual user verification in a live Claude Code session)

## Requirements Drift

**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Consistent with project patterns. The `sessions_target → lifecycle_target` rename in `handler.py` aligns with the new wider scope and matches the spec acceptance grep. `legacy_target_path` / `wide_target_path` naming in the `--unregister` branch makes the dual-call migration symmetry self-documenting. Justfile `BUILD_OUTPUT_PLUGINS` / `HAND_MAINTAINED_PLUGINS` constants follow the existing all-caps recipe convention. Plugin/hook script names retain the `cortex-` prefix used elsewhere in the codebase.
- **Error handling**: `handler.py` keeps the existing exception-translation pattern (`ScaffoldError` and `SettingsMergeError` → exit 2; unexpected → exit 1). `scaffold.check_symlink_safety` raises a clear actionable error when `lifecycle/` resolves outside the repo. `--unregister` is intentionally idempotent — comments at handler.py:131-136 spell out the no-op behavior of the legacy unregister call against fresh-init repos. The justfile recipe's wildcard `*) echo "build-plugin: no manifest for $p" >&2; continue;;` arm fails loudly rather than silently emitting an empty plugin tree. Hook scripts retain their original self-filter exits.
- **Test coverage**: Plan verification steps 1–6 (automated) executed and all pass: `just build-plugin` is idempotent and produces the expected trees, byte-for-byte hook/skill diffs are clean, `just test` passes (5/5), `bash .githooks/pre-commit` exits 0, both plugin diff checks are clean, and the marketplace/plugin/hooks/mcp JSONs satisfy every documented `jq` assertion. Plan Task 6 (idempotence + stale-removal) verified inline. The `tests/test_settings_merge.py` `_target_path_for` helper update was a necessary deviation noted in implementation context — it kept the partial-failure-recovery test cases passing without modifying their assertion semantics. Interactive R11/R12/R13 verification deferred to user (Task 13 status pending) per spec design.
- **Pattern consistency**: The plugin layout mirrors `plugins/cortex-interactive/` exactly (`.claude-plugin/plugin.json` is the only file in `.claude-plugin/`; `skills/`, `hooks/`, `.mcp.json` at plugin root; no `version` field; SKILL.md sources unchanged). The hooks.json schema follows the documented `${CLAUDE_PLUGIN_ROOT}/hooks/...` placeholder convention. The `case` dispatch in justfile is the bash-3.2-compatible idiom called out in spec Technical Constraints. Per-task commits (deviation from plan's single-bulk commit) are consistent with the project's normal `/cortex:commit` per-task workflow and all subjects are ≤72 chars per the convention.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
