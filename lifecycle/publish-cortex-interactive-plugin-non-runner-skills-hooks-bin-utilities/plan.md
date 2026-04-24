# Plan: publish-cortex-interactive-plugin-non-runner-skills-hooks-bin-utilities

## Overview

Ship the `cortex-interactive` Claude Code plugin by (a) remediating source-tree couplings that break a plugin-only install (critical-review import, refine cross-skill traversal, hardcoded `~/.claude/skills/...` paths, evolve's `readlink` self-path — replaced with `git rev-parse --show-toplevel` to preserve subdirectory-safe invocation), (b) renaming four bin utilities with a `cortex-` prefix and adding three new backlog-script shims, (c) migrating every bare `/skill-name` slash reference to `/cortex:skill-name` via a scoped Python rewrite tool (separate Part A pass over the 14 shipped skill source trees, Part B pass over live docs/hooks/tests; the rewrite regex covers YAML frontmatter quoted forms and sentence-terminating periods, and path-skip rules use directory-prefix matching to avoid false positives on `skills/research/`), (d) building `plugins/cortex-interactive/` from top-level sources via a new `just build-plugin` recipe that treats BOTH `skills/`, `bin/`, AND the plugin-shipped hook script as build-output (eliminating the dual-source condition for `cortex-validate-commit.sh`), (e) hand-authoring only the plugin manifest and `hooks.json` (genuinely low-change artifacts), and (f) enforcing dual-source drift with a `.githooks/pre-commit` that runs the build recipe and fails on diff across the full plugin tree. Top-level `skills/`, `bin/`, and `hooks/cortex-validate-commit.sh` remain the single sources of truth; the committed `plugins/cortex-interactive/` tree is build-output (modulo the two hand-authored metadata files).

## Tasks

### Task 1: Create plugin manifest skeleton
- **Files**: `plugins/cortex-interactive/.claude-plugin/plugin.json`
- **What**: Create the plugin manifest with required metadata. No `version` field (git-SHA versioning per research).
- **Depends on**: none
- **Complexity**: simple
- **Context**: JSON shape per research: `{"name": "cortex-interactive", "description": "...", "author": "..."}`. Name is kebab-case and drives the `/cortex:` slash prefix. Directory `plugins/cortex-interactive/.claude-plugin/` is new. Only `plugin.json` belongs under `.claude-plugin/` — all other components live at sibling paths (`hooks/`, `skills/`, `bin/`) per spec Technical Constraints and research anti-patterns.
- **Verification**: `jq -r '.name' plugins/cortex-interactive/.claude-plugin/plugin.json` — pass if output is exactly `cortex-interactive` and exit 0 (matches R1 acceptance).
- **Status**: [x] completed

### Task 2: Inline atomic_write in critical-review
- **Files**: `skills/critical-review/SKILL.md`
- **What**: Replace the `from cortex_command.common import atomic_write` import at line 255 with an inline ~6-line implementation inside the same `python3 -c` snippet so critical-review runs without the CLI tier on disk.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The import sits inside a heredoc-style `python3 -c "..."` block that writes B-class residue for lifecycle sessions. Inline implementation uses `tempfile.NamedTemporaryFile(dir=<target_dir>, delete=False)` + `os.replace(tmp, final)` to preserve atomic-write semantics (write to temp in the same directory, then atomic rename). Follow the existing call pattern — the snippet already constructs the target path and payload; only the import line and the single `atomic_write(...)` call site are replaced. Keep `sys.path.insert(...)` removed along with the import to avoid dead code.
- **Verification**: `grep -c "from cortex_command.common import atomic_write" skills/critical-review/SKILL.md` — pass if count = 0 AND `grep -cE "tempfile\\.|os\\.replace" skills/critical-review/SKILL.md` ≥ 1 (matches R3 acceptance after build).
- **Status**: [x] completed

### Task 3: Relocate cross-skill content referenced by refine
- **Files**: `skills/refine/references/clarify.md` (new), `skills/refine/references/specify.md` (new), `skills/refine/SKILL.md` (edit lines 26, 60, 81, 130)
- **What**: Duplicate the sections of `skills/lifecycle/references/clarify.md` and `skills/lifecycle/references/specify.md` that `refine/SKILL.md` reads (§1, §2–§7, §6 of clarify.md; §1–§4 of specify.md) into co-located copies under `skills/refine/references/`. Rewrite the four `${CLAUDE_SKILL_DIR}/../lifecycle/references/<file>` read-sites in `refine/SKILL.md` to reference `references/<file>` (co-located relative paths).
- **Depends on**: none
- **Complexity**: complex
- **Context**: Source file `skills/lifecycle/references/clarify.md` has numbered sections §1–§7; copy all sections referenced by refine (confirmed at refine/SKILL.md:26 §1, :60 §2–§7, :81 §6). Source `skills/lifecycle/references/specify.md` has sections §1–§4, all of which refine/SKILL.md:130 pulls in. Produce verbatim copies, not paraphrased summaries. Rewrite pattern example: `Read \`${CLAUDE_SKILL_DIR}/../lifecycle/references/clarify.md\` §1` → `Read \`references/clarify.md\` §1`. Retain section-anchor identifiers so downstream reads still work.
- **Verification**: `grep -c 'CLAUDE_SKILL_DIR' skills/refine/SKILL.md` — pass if count = 0 AND `test -f skills/refine/references/clarify.md && test -f skills/refine/references/specify.md` — pass if exit 0 (matches R4 source-side acceptance).
- **Status**: [x] completed

### Task 4: Rewrite hardcoded ~/.claude/skills paths in lifecycle and discovery references
- **Files**: `skills/lifecycle/references/clarify.md`, `skills/lifecycle/references/plan.md`, `skills/lifecycle/references/research.md`, `skills/lifecycle/references/specify.md`, `skills/discovery/references/research.md`
- **What**: Replace each `~/.claude/skills/<skill>/references/<file>` absolute path with a co-located relative reference (`references/<file>`) for prose read-instructions where upstream issue #9354 makes `${CLAUDE_PLUGIN_ROOT}` substitution unreliable in SKILL.md bodies.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Known line offsets from spec R5: clarify.md:49, plan.md:237, research.md:187, specify.md:145, discovery/references/research.md:130. Each is a single-line read-instruction of the form `Read \`~/.claude/skills/.../references/<file>.md\``. Target rewrite: `Read \`references/<file>.md\`` when the reader is already inside the same skill's tree (lifecycle references reading siblings), or `Read \`<path relative to reader>\`` otherwise. For hook/MCP JSON contexts (if any remain after audit), prefer `${CLAUDE_PLUGIN_ROOT}/skills/<skill>/references/<file>` because JSON substitution is reliable per research.
- **Verification**: `grep -rn '~/.claude/skills' skills/lifecycle/references/ skills/discovery/references/` — pass if 0 matches (matches R5 source-side acceptance).
- **Status**: [x] completed

### Task 5: Replace readlink-based repo-root resolution in evolve
- **Files**: `skills/evolve/SKILL.md`
- **What**: Replace the `readlink`-on-SKILL.md-path logic at lines 54–58 with `git rev-parse --show-toplevel` — the repo's canonical repo-root resolver — validated by a cortex-command-specific marker check at the resolved root (presence of `skills/evolve/SKILL.md` at `<repo-root>/skills/evolve/SKILL.md`). This preserves subdirectory-safe invocation (matching sibling skills: `retro` uses `git rev-parse --git-common-dir`; `critical-review` and `bin/cortex-git-sync-rebase` use `git rev-parse --show-toplevel`). On marker failure emit a two-line error to stderr: line 1 `/cortex:evolve must be invoked from inside a cortex-command checkout (git rev-parse --show-toplevel resolved to "<resolved-path>" but skills/evolve/SKILL.md not found there)`; line 2 `Fix: cd into a cortex-command clone and re-invoke.` Then exit non-zero.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Current pattern (readlink on SKILL.md path → derive repo root) breaks in plugin layouts because the plugin cache is not a symlink into the user's repo. Replacement strategy uses `REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)` (matching the pattern already in `bin/git-sync-rebase.sh:14`, `cortex_command/pipeline/worktree.py`, `pipeline/merge.py`, `pipeline/smoke_test.py`, `skills/critical-review/SKILL.md`), then checks for `skills/evolve/SKILL.md` at the resolved root as the cortex-command-specific marker. Rationale for the marker choice: (a) `.git/ alone` matches any git repo; (b) `backlog/ alone` matches any project with a backlog directory (not uncommon); (c) `skills/evolve/SKILL.md` is load-bearing — it's the file evolve itself is running from and is unique to cortex-command. Preserves the capability the prior readlink pattern provided (subdirectory-safe invocation) while adding robustness against plugin-cache layout and cross-repo invocation.
- **Verification**: `grep -c 'readlink' skills/evolve/SKILL.md` — pass if count = 0 (matches R6 source-side acceptance) AND `grep -c 'git rev-parse --show-toplevel' skills/evolve/SKILL.md` ≥ 1 (confirms replacement pattern is in place). Interactive/session-dependent: end-to-end manual test of `/cortex:evolve` from both repo-root AND a subdirectory (e.g., `skills/evolve/`) is Task 17.
- **Status**: [x] completed

### Task 6: Rename existing bin utilities with cortex- prefix
- **Files**: `bin/jcc` → `bin/cortex-jcc`, `bin/count-tokens` → `bin/cortex-count-tokens`, `bin/audit-doc` → `bin/cortex-audit-doc`, `bin/git-sync-rebase.sh` → `bin/cortex-git-sync-rebase`. Also inspect the renamed `cortex-git-sync-rebase` for internal references to `cortex_command/overnight/sync-allowlist.conf` (confirmed in research as repo-relative) — no rewrite required unless the path has drifted.
- **What**: `git mv` each source file to its `cortex-` prefixed name (dropping the `.sh` extension from `git-sync-rebase.sh`, matching spec R7's enumerated filenames). Preserve `chmod +x` mode bits through the rename. Do not alter shebangs or script bodies.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Current `bin/` contents: `audit-doc`, `count-tokens`, `git-sync-rebase.sh`, `jcc`, `overnight-schedule`, `overnight-start`, `overnight-status`, `validate-spec`. Only the four named in spec R7 are renamed; the `overnight-*` and `validate-spec` scripts remain untouched (they do not ship in `cortex-interactive` — `overnight-*` is #121 territory, `validate-spec` is CLI-internal). `bin/jcc` is installed as `~/.local/bin/jcc` via an external step — accept the rename as a hard cut per spec "Changes to Existing Behavior" (no compatibility alias).
- **Verification**: `ls bin/ | grep -cE '^cortex-(jcc|count-tokens|audit-doc|git-sync-rebase)$'` — pass if count = 4 AND `find bin/ -maxdepth 1 -name 'cortex-*' -type f ! -perm -u+x | wc -l` — pass if count = 0.
- **Status**: [x] completed

### Task 7: Create three cortex-prefixed bin shims for backlog Python utilities
- **Files**: `bin/cortex-update-item` (new), `bin/cortex-create-backlog-item` (new), `bin/cortex-generate-backlog-index` (new)
- **What**: Bash shims implementing spec R8's three-branch fallback to resolve the backlog Python sources. Each shim has identical structure; only the module name differs per script.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
    - Module map: `cortex-update-item` → `update_item`, `cortex-create-backlog-item` → `create_item`, `cortex-generate-backlog-index` → `generate_index`.
    - Shim skeleton (each script follows this structure — no function bodies reproduced; implementer writes concrete bash):
      - Shebang: `#!/bin/bash`, followed by `set -euo pipefail`.
      - Branch (a): probe `python3 -c "import cortex_command.backlog.<module>" 2>/dev/null`; on exit 0, `exec python3 -m cortex_command.backlog.<module> "$@"`. Probe MUST be literal `import cortex_command.backlog.<module>` (spec R8 acceptance uses a grep on this exact string).
      - Branch (b): if `CORTEX_COMMAND_ROOT` is set and non-empty AND `grep -q '^name = "cortex-command"' "$CORTEX_COMMAND_ROOT/pyproject.toml" 2>/dev/null`, then `exec python3 "$CORTEX_COMMAND_ROOT/backlog/<module>.py" "$@"`.
      - Branch (c): print `cortex-command CLI not found — run 'cortex setup' or point CORTEX_COMMAND_ROOT at a cortex-command checkout` to stderr; `exit 2`.
    - All three scripts `chmod +x`. No third-party deps (pure bash + python3 on PATH).
    - Branch (a) deliberately tests the packaged form `cortex_command.backlog.<module>` (not the PEP 420 ambient form `backlog.<module>`) to avoid shadow-imports from the repo's top-level `backlog/` user-data directory. Spec R8 is explicit on this point.
- **Verification** (all must pass):
    - `grep -F "import cortex_command.backlog" bin/cortex-update-item | wc -l` ≥ 1 (literal probe present; R8 acceptance).
    - `grep -F "import cortex_command.backlog" bin/cortex-create-backlog-item | wc -l` ≥ 1.
    - `grep -F "import cortex_command.backlog" bin/cortex-generate-backlog-index | wc -l` ≥ 1.
    - `find bin/ -maxdepth 1 -name 'cortex-update-item' -o -name 'cortex-create-backlog-item' -o -name 'cortex-generate-backlog-index' | while read f; do test -x "$f" || echo NOT_EXEC; done | wc -l` — pass if count = 0.
    - `env -u CORTEX_COMMAND_ROOT ./bin/cortex-update-item 2>&1 | grep -c 'cortex-command CLI not found'` — pass if count ≥ 1 (branch (c) triggers without env + no packaged module).
- **Status**: [x] completed

### Task 8: Rewrite bin call sites in top-level skills
- **Files**:
  - `skills/backlog/SKILL.md`
  - `skills/dev/SKILL.md`
  - `skills/discovery/references/decompose.md`
  - `skills/lifecycle/SKILL.md`
  - `skills/lifecycle/references/clarify.md`
  - `skills/lifecycle/references/complete.md`
  - `skills/morning-review/SKILL.md`
  - `skills/morning-review/references/walkthrough.md`
  - `skills/overnight/SKILL.md`
  - `skills/refine/SKILL.md`
- **What**: Rewrite every bare invocation to the `cortex-` prefixed form. Use the same word-boundary regex the spec uses for verification so the transform is self-auditable.
- **Depends on**: [6, 7]
- **Complexity**: complex
- **Context**: Task touches 10 files, exceeding the 5-file soft cap; kept as one task because the change is a mechanical batch-rewrite of the same regex across all call-sites — splitting creates arbitrary seams with no independent verification boundary. Word-boundary regex from spec R9: `(^| |\`|\()(update-item|create-backlog-item|generate-backlog-index|jcc|count-tokens|audit-doc|git-sync-rebase)( |$|"|\`|\))`. Replacement: prepend `cortex-` to the captured utility name, preserving the surrounding delimiter characters. Edit in-place with `sed -i` (BSD sed on macOS requires `sed -i ''`) per hit OR via a small Python helper invoked manually — exact mechanism is implementer's choice, subject to the verification grep returning 0. Do NOT use the scoped namespace rewrite tool (Task 9) for this — that tool targets `/slash:command` boundaries, not bin-name boundaries. Note: `morning-review` and `overnight` are non-shipped skills but their call-sites must still be rewritten because the top-level `bin/` files are being renamed at the source — these skills would break locally if their callers were not updated.
- **Verification**: `grep -rnE '(^| |\`|\()(update-item|create-backlog-item|generate-backlog-index|jcc|count-tokens|audit-doc|git-sync-rebase)( |$|"|\`|\))' skills/ | wc -l` — pass if count = 0.
- **Status**: [x] completed

### Task 9: Build scoped namespace rewrite tool and fixture tests
- **Files**: `scripts/migrate-namespace.py` (new), `tests/test_migrate_namespace.py` (new), `tests/fixtures/migrate_namespace/` (new directory — seeded fixtures for tests)
- **What**: Python script that takes an explicit include-list of paths (files or directories), walks them, and rewrites every bare `/<skill-name>` reference to `/cortex:<skill-name>` for an allowlist of 14 skills, subject to a built-in skip list and word-boundary regex. Tests cover positive rewrite (including YAML frontmatter quoted forms and sentence-terminating periods), skip-list enforcement with directory-prefix matching (not substring), and idempotence.
- **Depends on**: none
- **Complexity**: complex
- **Context**:
    - CLI signature: `scripts/migrate-namespace.py --include <path> [--include <path>...] [--mode dry-run|apply] [--verify]`.
    - Skill allowlist (hardcoded): `commit, pr, lifecycle, backlog, requirements, research, discovery, refine, retro, dev, fresh, diagnose, evolve, critical-review`.
    - Regex pattern: `(^| |\x60|\(|\[|,|;|:|")/(<skill-name>)( |$|"|\x60|\)|\]|,|;|:|\.)` — left-delimiters add `"` (covers YAML frontmatter `"commit", "/commit"` forms in every skill's `description:` field — confirmed live at `skills/commit/SKILL.md:3`, `skills/pr/SKILL.md:3`, `skills/backlog/SKILL.md:3`, `skills/fresh/SKILL.md:3`, `skills/discovery/SKILL.md:3`, `skills/lifecycle/SKILL.md:356`, `skills/research/SKILL.md:4`, `skills/retro/SKILL.md:38`). Right-delimiters add `\.` (covers sentence-terminating bare refs like `/commit.`).
    - Replacement: prefix `/` replaced by `/cortex:` while preserving surrounding delimiters.
    - Built-in skip rules (any one skips a file or a match). Path-skip rules MUST use directory-prefix matching via `pathlib.Path` semantics (`path.parts[0] == 'research'` for top-level anchor, OR `'research' in path.parts` for any-component match) — NOT naive `substring in str(path)` which would wrongly exclude `skills/research/` (collision with the shipped `research` skill):
        1. Path has a component equal to (not substring of) any of: `retros`, `.claude/worktrees`, `research`, OR path matches glob `lifecycle/sessions/**`, OR path matches glob `lifecycle/*/events.log`, OR path is under `backlog/` (historical tickets). Explicit exception: paths under `skills/research/` are NOT skipped — the `research` component match applies to top-level `research/` (epic research artifacts), not `skills/research/` (the shipped skill). Implement via `parts[0] == 'research'` for top-level anchor.
        2. Match substring contains any of: `://`, `github.com/`, `gitlab.com/`, `bitbucket.org/`.
        3. Match is a relative-path segment (line contains a `/` character *before* the `/<skill>` token without an intervening space or word boundary — e.g., `./commit/hook.sh`, `src/pr/util.py`).
        4. File extension not in {`.md`, `.sh`, `.py`, `.json`, `.yaml`, `.yml`, no-extension-files}.
    - `--verify` mode: run the rewrite in-memory; exit 0 if NO changes would be written (idempotence proof); exit 1 if changes would occur.
    - Output: one line per rewrite `{file}:{lineno}: /{skill} → /cortex:{skill}` to stdout; summary `Rewrote N references across M files` at end.
    - Test cases in `tests/test_migrate_namespace.py`:
        1. Positive (prose): fixture file under `tests/fixtures/migrate_namespace/docs/sample.md` containing bare `/commit` and `/lifecycle` references — after `--mode apply`, both are rewritten to `/cortex:*` form.
        2. Positive (YAML frontmatter quoted): fixture containing `Use when user says "commit", "/commit", "make a commit"` — after apply, `"/commit"` rewrites to `"/cortex:commit"` (verifies double-quote left-delimiter).
        3. Positive (sentence-terminating period): fixture containing `Use /commit. Then proceed.` — after apply, rewrites to `/cortex:commit.` (verifies period right-delimiter).
        4. Skip-list (top-level research/): fixture under `tests/fixtures/migrate_namespace/research/seed.md` — content bytes IDENTICAL after apply.
        5. Skip-list (nested skills/research/): fixture under `tests/fixtures/migrate_namespace/skills/research/seed.md` — DOES get rewritten (confirms directory-component anchor does not false-match via substring).
        6. Skip-list (retros): fixture under `tests/fixtures/migrate_namespace/retros/seed.md` with a bare `/commit` — content bytes IDENTICAL after apply.
        7. Skip-list (url): fixture containing `https://github.com/foo/commit/abc123` — URL untouched.
        8. Skip-list (relative path segment): fixture containing `./commit/hook.sh` — path untouched.
        9. Idempotence: run `--mode apply` twice on fixture dir; second run produces zero changes (`--verify` exits 0).
    - Framework: use Python `unittest` or plain assertions per `tests/` convention; pick up with `just test` (existing recipe).
- **Verification**: `python3 scripts/migrate-namespace.py --help` — exit 0 AND `just test 2>&1 | grep -c 'FAILED\|error'` — pass if count = 0 AND fixture tests execute (evidence: test file count increases by 1 in `just test` output).
- **Status**: [x] completed

### Task 10: Execute namespace migration Part A across 14 shipped skill trees
- **Files**: `skills/commit/**`, `skills/pr/**`, `skills/lifecycle/**`, `skills/backlog/**`, `skills/requirements/**`, `skills/research/**`, `skills/discovery/**`, `skills/refine/**`, `skills/retro/**`, `skills/dev/**`, `skills/fresh/**`, `skills/diagnose/**`, `skills/evolve/**`, `skills/critical-review/**` (all files under each subtree walked by Task 9's tool)
- **What**: Invoke the Task-9 rewrite tool with `--include` flags for each of the 14 skill directories and `--mode apply`. Review the resulting diff; commit.
- **Depends on**: [2, 3, 4, 5, 8, 9]
- **Complexity**: simple
- **Context**: Invocation: `python3 scripts/migrate-namespace.py --mode apply --include skills/commit --include skills/pr --include skills/lifecycle --include skills/backlog --include skills/requirements --include skills/research --include skills/discovery --include skills/refine --include skills/retro --include skills/dev --include skills/fresh --include skills/diagnose --include skills/evolve --include skills/critical-review`. Depends on Tasks 2–5 and 8 so the source trees already reflect all other remediation before the namespace sweep — prevents double-edit churn and regex false-positives on temporarily-in-flux content. Task 9's skip rules use directory-prefix matching (not substring) so `skills/research/` is NOT inadvertently skipped by the top-level `research/` skip rule.
- **Verification**: `grep -rnE '(^| |\x60|\(|\[|,|;|:|")(/commit|/pr|/lifecycle|/backlog|/requirements|/research|/discovery|/refine|/retro|/dev|/fresh|/diagnose|/evolve|/critical-review)( |$|"|\x60|\)|\]|,|;|:|\.)' skills/commit/ skills/pr/ skills/lifecycle/ skills/backlog/ skills/requirements/ skills/research/ skills/discovery/ skills/refine/ skills/retro/ skills/dev/ skills/fresh/ skills/diagnose/ skills/evolve/ skills/critical-review/ | wc -l` — pass if count = 0. Delimiter set matches Task 9's full regex (left: `^`, space, backtick, `(`, `[`, `,`, `;`, `:`, `"`; right: space, `$`, `"`, backtick, `)`, `]`, `,`, `;`, `:`, `.`) so the verification is not strictly narrower than the rewrite surface. Task 9 skip rules (URL patterns, relative-path segments) may produce legitimate residuals that this grep flags — in those cases the residual is a correctly-unrewritten string like a URL or relative path, and must be manually confirmed to be a skip-rule match. If genuine residuals remain that SHOULD be rewritten, fix by re-running the tool (likely a Task 9 bug) rather than grep-narrowing here.
- **Status**: [x] completed

### Task 11: Execute namespace migration Part B across live documentation, hooks, and tests
- **Files**: `docs/**`, `CLAUDE.md`, `README.md`, `justfile`, `pyproject.toml`, `hooks/**`, `claude/hooks/**`, `tests/**` (walked by Task 9's tool with skip-list applied)
- **What**: Invoke the Task-9 rewrite tool with `--include` flags for each target path and `--mode apply`. Confirm idempotence by immediately re-running with `--verify` (or re-running `--mode apply` and asserting `git diff --quiet`). Skip-list enforcement is validated by Task 9's fixture tests, which must pass before Part B executes.
- **Depends on**: [9]
- **Complexity**: simple
- **Context**: Invocation: `python3 scripts/migrate-namespace.py --mode apply --include docs --include CLAUDE.md --include README.md --include justfile --include pyproject.toml --include hooks --include claude/hooks --include tests`. Then `python3 scripts/migrate-namespace.py --verify --include docs --include CLAUDE.md --include README.md --include justfile --include pyproject.toml --include hooks --include claude/hooks --include tests` — must exit 0 for idempotence.
- **Verification** (all must pass):
    - Completeness: `for skill in commit pr lifecycle backlog requirements research discovery refine retro dev fresh diagnose evolve critical-review; do grep -rnE "(^| |\`|\(|\[|,|;|:)/$skill( |\$|\"|\`|\)|\]|,|;|:)" docs/ CLAUDE.md README.md justfile pyproject.toml hooks/ claude/hooks/ tests/ 2>/dev/null; done | wc -l` — pass if count = 0 (matches R11(a)).
    - Idempotence: `python3 scripts/migrate-namespace.py --verify --include docs --include CLAUDE.md --include README.md --include justfile --include pyproject.toml --include hooks --include claude/hooks --include tests` — pass if exit 0 (matches R11(b)).
- **Status**: [x] completed

### Task 12: Implement `just build-plugin` recipe
- **Files**: `justfile` (append `build-plugin` recipe)
- **What**: Add a `build-plugin` recipe that regenerates `plugins/cortex-interactive/skills/`, `plugins/cortex-interactive/bin/`, AND the plugin-shipped hook script `plugins/cortex-interactive/hooks/cortex-validate-commit.sh` from top-level sources, preserving file-mode bits. Does not touch `.claude-plugin/plugin.json` or `plugins/cortex-interactive/hooks/hooks.json` (manifest is hand-authored).
- **Depends on**: [1, 6, 7]
- **Complexity**: simple
- **Context**:
    - Skills to copy (hardcoded Bash array inside the recipe): `commit pr lifecycle backlog requirements research discovery refine retro dev fresh diagnose evolve critical-review`. Explicitly excludes `morning-review`, `overnight`, `skill-creator` — those are not in this plugin.
    - Bin to copy: glob `bin/cortex-*` (only cortex-prefixed binaries; excludes `overnight-*` and `validate-spec` which stay at top-level for CLI use).
    - Hook script to copy: `hooks/cortex-validate-commit.sh` — copied to `plugins/cortex-interactive/hooks/cortex-validate-commit.sh`. This treats the hook script as build-output (single source of truth at top-level `hooks/`), eliminating the dual-source condition that would otherwise exist between the project-scope and plugin-scope copies. Rationale: the file's own git history shows it's an actively-maintained script (40-line rewrite in one recent commit, rename in another), so hand-authoring a second copy would silently drift. Critical-review feedback loop surfaced this; the fix here closes the gap before it opens.
    - `hooks.json` manifest remains hand-authored (Task 13) — it's a small JSON declaration that changes only when hook registration changes, genuinely meeting the "changes rarely" bar that the script itself does not.
    - Strategy: use `rsync -a --delete` per-subtree to preserve file-mode bits AND idempotently remove stale content if a skill is removed from the allowlist. For each skill `$s`: `rsync -a --delete skills/$s/ plugins/cortex-interactive/skills/$s/`. For bin: `rsync -a --delete --include='cortex-*' --exclude='*' bin/ plugins/cortex-interactive/bin/`. For hook script: `rsync -a hooks/cortex-validate-commit.sh plugins/cortex-interactive/hooks/cortex-validate-commit.sh` (no `--delete` — other hand-authored files like `hooks.json` must survive).
    - Recipe shape: standard justfile recipe with `#!/usr/bin/env bash` and `set -euo pipefail` (matches existing recipes in the justfile).
    - Idempotence: `rsync -a --delete` produces zero diff when source and destination are already identical, by design. The single-file `rsync -a` for the hook script is also idempotent.
- **Verification** (all must pass):
    - `just --list | grep -c 'build-plugin'` ≥ 1 (recipe registered).
    - After running `just build-plugin` twice in succession with no source edits between runs: `git status --porcelain plugins/cortex-interactive/` — pass if output is empty (matches R13 idempotence). This verification runs after Task 14 seeds the plugin directory; Task 12 alone is checked only for recipe presence via the `just --list` probe.
    - `plugins/cortex-interactive/hooks/cortex-validate-commit.sh` is treated as build-output: after an edit to top-level `hooks/cortex-validate-commit.sh`, running `just build-plugin` propagates the edit into the plugin tree (verified during Task 15's drift test).
- **Status**: [x] completed

### Task 13: Hand-author plugin hooks manifest
- **Files**: `plugins/cortex-interactive/hooks/hooks.json` (new)
- **What**: Hand-author `hooks.json` registering `cortex-validate-commit.sh` as a plugin-scope `PreToolUse` hook. The actual script file at `plugins/cortex-interactive/hooks/cortex-validate-commit.sh` is produced by Task 12's `build-plugin` recipe from the top-level `hooks/cortex-validate-commit.sh` source — NOT hand-authored here.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
    - `hooks.json` shape: `{"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/cortex-validate-commit.sh"}]}]}}`. Event name `PreToolUse` is case-sensitive per research. Matcher `Bash` aligns with the script's own `[[ "$TOOL" == "Bash" ]]` guard.
    - Script body responsibility: the script is sourced from top-level `hooks/cortex-validate-commit.sh` by `build-plugin` (Task 12), preserving a single source of truth. Audit the top-level script once as part of this task: if any repo-absolute paths (`/Users/...`, `/home/...`) exist, fix them at the top-level source (not in the plugin copy) so the fix survives rebuilds. Historically the script has no repo-absolute paths; confirm via `grep -cE '/Users/|/home/' hooks/cortex-validate-commit.sh` = 0 before proceeding.
    - Hand-authored vs. build-output split within `plugins/cortex-interactive/hooks/`: `hooks.json` is hand-authored (genuinely changes rarely — only when hook registration itself changes). `cortex-validate-commit.sh` is build-output copied from `hooks/` (already evolves with validation rules). Task 12's recipe uses `rsync -a` (without `--delete`) for the hook script specifically so `hooks.json` survives rebuilds.
- **Verification** (all must pass):
    - `test -f plugins/cortex-interactive/hooks/hooks.json` — exit 0.
    - `jq -r '.hooks | keys[]' plugins/cortex-interactive/hooks/hooks.json | wc -l` ≥ 1 (at least one event declared).
    - `jq -r '.hooks | values[] | .[] | .hooks[] | .command' plugins/cortex-interactive/hooks/hooks.json | grep -c 'cortex-validate-commit.sh'` ≥ 1.
    - `grep -cE '/Users/|/home/' hooks/cortex-validate-commit.sh` — pass if count = 0 (no repo-absolute paths at the source).
    - `test -x plugins/cortex-interactive/hooks/cortex-validate-commit.sh` — pass if exit 0 (the script is produced by Task 12's build and this verification runs after Task 14).
- **Status**: [x] completed

### Task 14: Run build and commit plugin artifacts
- **Files**: `plugins/cortex-interactive/skills/**` (generated — 14 skill subtrees), `plugins/cortex-interactive/bin/**` (generated — 7 cortex-prefixed utilities)
- **What**: Run `just build-plugin`. Verify the produced directory layout matches R2, R7, R9, R10(ii), R15. Commit the generated plugin tree.
- **Depends on**: [1, 2, 3, 4, 5, 8, 10, 12, 13]
- **Complexity**: simple
- **Context**: Standard build+verify+commit. The first run is a net-new write; subsequent runs (Task 12 idempotence verification and Task 15 drift-hook seeding) must produce no diff.
- **Verification** (all must pass):
    - R2: `ls plugins/cortex-interactive/skills/ | sort | tr '\n' ' '` — pass if exactly `backlog commit critical-review dev diagnose discovery evolve fresh lifecycle pr refine requirements research retro ` AND `find plugins/cortex-interactive/skills -maxdepth 2 -name SKILL.md | wc -l` = 14.
    - R7: `ls plugins/cortex-interactive/bin/ | grep -c '^cortex-'` — pass if count = 7 AND `find plugins/cortex-interactive/bin/ -type f ! -perm -u+x | wc -l` = 0.
    - R9: `grep -rnE '(^| |\`|\()(update-item|create-backlog-item|generate-backlog-index|jcc|count-tokens|audit-doc|git-sync-rebase)( |$|"|\`|\))' plugins/cortex-interactive/skills/ | wc -l` = 0.
    - R10(ii) and R11(a) equivalent against the build output: `grep -rnE '(^| |\`|\()(/commit|/pr|/lifecycle|/backlog|/requirements|/research|/discovery|/refine|/retro|/dev|/fresh|/diagnose|/evolve|/critical-review)( |$|"|\`|\))' plugins/cortex-interactive/skills/ | wc -l` = 0.
    - R12: `test ! -d plugins/cortex-interactive/skills/morning-review` — exit 0.
    - R15: `find plugins/cortex-interactive/ -name 'settings*.json' | wc -l` = 0.
    - R13 idempotence: immediately after commit, run `just build-plugin` again; `git status --porcelain plugins/cortex-interactive/` — pass if output empty.
- **Status**: [x] completed

### Task 15: Add dual-source drift enforcement via pre-commit hook
- **Files**: `.githooks/pre-commit` (new, executable), `justfile` (append `setup-githooks` recipe), `tests/test_drift_enforcement.sh` (new test), `CLAUDE.md` (add one-line pointer to `just setup-githooks` in the Conventions section)
- **What**: Pre-commit hook that runs `just build-plugin` and exits non-zero if `git diff --quiet plugins/cortex-interactive/` detects drift; message lists drifted files via `git diff --name-only plugins/cortex-interactive/`. Provide `just setup-githooks` recipe that runs `git config core.hooksPath .githooks`. Add a test that seeds drift in BOTH a build-output subdir AND the hook-script subdir, invokes the hook, asserts failure on both, and cleans up.
- **Depends on**: [12, 14]
- **Complexity**: simple
- **Context**:
    - Hook script logic: run `just build-plugin` (fail fast on error) → run `git diff --quiet plugins/cortex-interactive/` → on non-zero diff exit, print error with `git diff --name-only plugins/cortex-interactive/` output and exit 1; otherwise exit 0. Shebang `#!/bin/bash`, `set -euo pipefail`. Scope of diff covers the entire `plugins/cortex-interactive/` tree (skills, bin, AND hooks) because Task 12 now treats `cortex-validate-commit.sh` as build-output — so an edit to top-level `hooks/cortex-validate-commit.sh` propagates into `plugins/cortex-interactive/hooks/cortex-validate-commit.sh` after `just build-plugin`, and `git diff --quiet plugins/cortex-interactive/` surfaces the previously-invisible dual-source drift.
    - `setup-githooks` recipe: one-liner `git config core.hooksPath .githooks` with a confirmation echo.
    - Test script `tests/test_drift_enforcement.sh` has TWO seed-and-restore subtests:
      - **Subtest A — skills drift**: (1) seed drift by editing `skills/commit/SKILL.md` with a no-op marker comment, (2) run `.githooks/pre-commit` directly, (3) assert exit code ≠ 0 and stdout mentions `skills/commit/SKILL.md`, (4) `git restore skills/commit/SKILL.md` to undo the seed AND `just build-plugin` to re-sync the plugin tree.
      - **Subtest B — hook script drift** (closes the asymmetry the critical review flagged): (1) seed drift by editing `hooks/cortex-validate-commit.sh` with a no-op marker comment, (2) run `.githooks/pre-commit` directly, (3) assert exit code ≠ 0 and stdout mentions `plugins/cortex-interactive/hooks/cortex-validate-commit.sh`, (4) `git restore hooks/cortex-validate-commit.sh` AND `just build-plugin` to re-sync.
      - Both subtests exit 0 on success, non-zero on failure. Hooked into `just test` by convention.
    - CLAUDE.md pointer: one sentence in Conventions section — "Run `just setup-githooks` after clone to enable the dual-source drift pre-commit hook."
    - Chosen pre-commit over CI: simpler local-first enforcement, no CI wiring required for this ticket. CI can be added later without blocking.
- **Verification** (all must pass):
    - `.githooks/pre-commit` exists and is executable: `test -x .githooks/pre-commit` — exit 0.
    - `just --list | grep -c 'setup-githooks'` ≥ 1.
    - R16(a) (clean state pass): after `just setup-githooks && just build-plugin`, run `.githooks/pre-commit` → exit 0.
    - R16(b) (drift state fail): `bash tests/test_drift_enforcement.sh` — exit 0 (both subtests pass iff the hook detects drift in both skills/ and hooks/ surfaces; test restores repo afterward).
- **Status**: [x] completed

### Task 16: Rewrite backlog/121 to commit morning-review inclusion and de-conditional critical-review
- **Files**: `backlog/121-cortex-overnight-integration-plugin.md`, `backlog/index.md`
- **What**: Replace the conditional phrasing ("`critical-review` and `morning-review` land here if the codebase check in ticket 120 finds they import `claude.overnight.*` at module load; otherwise they stay in `cortex-interactive`") with committed statements: (a) `critical-review` ships in `cortex-interactive` (per ticket 120, after remediation — this ticket's Task 2), (b) `morning-review` ships in `cortex-overnight-integration` (this plugin).
- **Depends on**: none
- **Complexity**: simple
- **Context**: Target line is in the `## Scope` bullet list of `backlog/121-*.md`. Rewrite to two bullets: "Skills included (renamed to `/cortex:*`): `overnight` (the user-facing entry point), `morning-review` (ships in this plugin — requires `$CORTEX_COMMAND_ROOT` and runner state)" and a neighboring clarifying note "`critical-review` ships in `cortex-interactive` (ticket 120) — remediated to run standalone". This also updates the backlog/index.md generated summary via the standard backlog-index workflow; run `just backlog-index` after editing.
- **Verification** (all must pass):
    - `grep -cE 'if the codebase check.*morning-review|morning-review.*if.*import' backlog/121-cortex-overnight-integration-plugin.md` — pass if count = 0 (matches R12 acceptance).
    - `grep -cE '(ships|includes|includes the following skills).*morning-review|morning-review.*(ships|included)' backlog/121-cortex-overnight-integration-plugin.md` — pass if count ≥ 1 (matches R12 acceptance).
- **Status**: [x] completed

### Task 17: Plugin-install smoke test (interactive)
- **Files**: none (operational check against the committed plugin tree)
- **What**: In a fresh Claude Code session against a clone of cortex-command, run `/plugin install cortex-interactive@<local-path>` pointing at `plugins/cortex-interactive/` in this repo. Invoke `/cortex:commit` (low-side-effect smoke) and invoke `/cortex:evolve` TWICE — once from the repo root AND once from a subdirectory like `skills/evolve/` — to exercise Task 5's `git rev-parse --show-toplevel`-based resolution. Observe that neither surfaces `ModuleNotFoundError`, `$CORTEX_COMMAND_ROOT unset`, nor plugin-cache-path crashes; AND that `/cortex:evolve` succeeds from the subdirectory invocation (i.e., Task 5's replacement preserves subdirectory-safe resolution that the prior readlink pattern also provided). Record the verification outcome in the lifecycle's Review phase.
- **Depends on**: [14]
- **Complexity**: simple
- **Context**: Per spec R6 (evolve) and R14 (install smoke), this verification is session-dependent: `/plugin install` and slash-command dispatch require a live Claude Code session — neither has a headless equivalent. The smoke test is the operational gate for install-time safety of plugin-only users; any crash here becomes a `CHANGES_REQUESTED` in the review phase and triggers implement-phase rework. The two-location evolve invocation specifically exercises Task 5's regression surface — a smoke from repo root alone would pass even if the marker logic had a subtle bug in the subdirectory path. Do not conflate "passes automated acceptance greps" (R1–R13, R15–R17) with "plugin works under real install" (R14, R6 end-to-end).
- **Verification**: Interactive/session-dependent: `/plugin install` and slash-command dispatch execute inside a live Claude Code session and cannot be scripted as a headless command (matches R14 and R6 acceptance).
- **Status**: [ ] pending

## Verification Strategy

End-to-end verification layers, in order:

1. **Source-tree integrity** (post-Task 11): every source-side acceptance grep from spec R3–R6 returns 0 residual hits; Task-9 tests pass; bin call-sites have no bare forms (R9 source equivalent); `/skill-name` references are gone from shipped skill trees (R10 source) and live documentation (R11 completeness + idempotence).
2. **Build-output integrity** (post-Task 14): R2, R7, R9, R10(ii), R12, R13, R15 greps run against `plugins/cortex-interactive/` and all return expected values; second `just build-plugin` run produces empty `git status --porcelain plugins/cortex-interactive/`.
3. **Plugin-contract integrity** (post-Task 13, 14): `jq` probes on `hooks.json` confirm structural validity (R17); manifest file matches R1.
4. **Drift enforcement live-check** (post-Task 15): pre-commit hook blocks a seeded-drift commit and lets a clean-build commit through.
5. **Install-time functional check** (Task 17): manual plugin install in a fresh session; `/cortex:commit` and `/cortex:evolve` run to completion without coupling errors — satisfies R6 end-to-end and R14.

If any layer fails, the review phase records `CHANGES_REQUESTED` and the lifecycle re-enters Implement with a targeted task list for the failing layer only.

## Veto Surface

Design choices below may warrant user review before implementation begins:

- **Pre-commit hook chosen over CI job (Task 15).** R16 explicitly delegates this choice to Plan phase. Pre-commit is simpler and doesn't require CI wiring, but requires every contributor to run `just setup-githooks` once. CI would enforce the invariant centrally but adds GitHub Actions setup. If the user wants CI instead (or both), Task 15 scope shifts.
- **Evolve repo-root resolution via `git rev-parse --show-toplevel` + cortex-specific marker (Task 5).** Chosen over two alternatives surfaced during critical review: (i) the original plan of `$PWD` + `.git/ AND backlog/` (rejected — forbids subdirectory invocation that every sibling skill permits, and the `backlog/` marker is not unique to cortex-command); (ii) `.git/` alone or `backlog/` alone (rejected for non-specificity). The canonical `git rev-parse --show-toplevel` pattern is already used in five codebase locations (`bin/git-sync-rebase.sh`, `cortex_command/pipeline/{worktree,merge,smoke_test}.py`, `critical-review/SKILL.md`), so this aligns with repo conventions. The `skills/evolve/SKILL.md`-at-resolved-root marker is uniquely identifying because it's the file evolve is already running from. If the user later wants a different marker (e.g., presence of `justfile` + `pyproject.toml`), Task 5's marker check is a single-line change.
- **Bin-rename is a hard cut — no compatibility alias for `jcc` (Task 6).** Spec "Changes to Existing Behavior" lists the bin renames as breaking. Users with `~/.local/bin/jcc` from the pre-117 install need to re-install at the new name. An alias (`ln -s cortex-jcc ~/.local/bin/jcc`) would soften the break; rejected here because it reintroduces the collision risk the `cortex-` prefix is meant to eliminate.
- **`just build-plugin` copies the hook SCRIPT but not the hook MANIFEST (Task 12 + Task 13).** After critical-review feedback, the previous "hooks/ is fully hand-authored" stance was revised: `cortex-validate-commit.sh` is treated as build-output (single source of truth at top-level `hooks/`) because its git history shows active evolution; `hooks.json` remains hand-authored because it's a small JSON declaration that changes only when hook registration itself changes. This split eliminates the dual-source condition the drift-enforcement mechanism would otherwise be blind to.
- **Namespace migration Part A uses the same tool as Part B (Task 10).** Alternative: hand-edit the 14 skill trees because the scope is more constrained. Rejected because ~3,387 references is too many for hand-edits and hand-edits diverge from the tool's guarantees. If the user wants per-skill commits for review clarity, Task 10 can split into 14 sub-invocations of the tool, one `--include skills/<name>` per invocation.

## Scope Boundaries

Explicitly excluded from this feature (maps to spec Non-Requirements):

- **Marketplace manifest** (`.claude-plugin/marketplace.json` at repo root) — ticket #122.
- **`requirements/project.md` DR-8 update** — ticket #122.
- **Migration guide/script for existing symlinked users** — ticket #124.
- **Lifecycle autonomous-worktree graceful-degrade** (hiding worktree option when runner CLI is absent) — ticket #123.
- **`cortex-overnight-integration` plugin** (overnight skill, morning-review, runner-only hooks, `cortex-notify.sh`) — ticket #121.
- **Namespace migration of non-shipped skills (`skills/morning-review/`, `skills/overnight/`)** — deferred to ticket #121. These skills remain at bare `/commit`, `/lifecycle`, `/refine`, `/backlog`, `/pr` forms after ticket 120 lands. Acceptable short-term because bare forms still resolve via project-scope skills in the cortex-command repo itself. Ticket #121 MUST run `scripts/migrate-namespace.py` against `skills/morning-review/` and `skills/overnight/` before packaging those skills into `cortex-overnight-integration`, or else ship plugin skills with bare slash references that won't resolve under plugin-namespaced form. Confirmed outstanding references: 3 in `morning-review/SKILL.md` (lines 137, 138, 143), 4 in `morning-review/references/walkthrough.md` (lines 435, 440, 500, 603), 8 in `overnight/SKILL.md` (lines 73, 77, 79, 178, 180, 200, 389, 393). The drift-enforcement hook (Task 15) does not cover these directories because `build-plugin` does not emit them — inconsistency within those trees is not detectable by this ticket's automation.
- **Cleanup or retention decision for `skills/skill-creator/`** — orphaned empty directory (contains only an empty `scripts/` subdirectory; no `SKILL.md`). Surfaced during critical review; neither retained-and-documented nor removed by this ticket. Future work should either add a `SKILL.md` (making it a real skill), remove the directory, or document its placeholder status in `requirements/`. Ticket #120 only references it in the `build-plugin` exclusion list alongside `morning-review`/`overnight`.
- **`cortex-output-filter.sh` hook in this plugin** — stays in machine-config (cross-project productivity, not cortex-scoped).
- **`cortex-skill-edit-advisor.sh` hook in this plugin** — stays project-scope (meaningful only inside cortex-command).
- **`${CLAUDE_PLUGIN_DATA}` declaration in plugin.json** — no utility needs persistent per-update state today.
- **`cortex doctor` preflight for bin PATH collision detection** — future optional ticket.
- **Full Python repackaging of `backlog/*.py` into `cortex_command.backlog.*`** — deferred; shim fallback in Task 7 is forward-compatible.
- **Bin collision opt-out mechanism** — upstream Claude Code does not offer one; `cortex-` prefix is the only available mitigation.
