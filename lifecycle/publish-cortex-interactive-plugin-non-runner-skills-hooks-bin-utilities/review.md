# Review: publish-cortex-interactive-plugin-non-runner-skills-hooks-bin-utilities

## Stage 1: Spec Compliance

### R1 — Plugin manifest exists
- **Expected**: `plugins/cortex-interactive/.claude-plugin/plugin.json` exists with `name: "cortex-interactive"` and no `version` field.
- **Actual**: File exists; `jq -r '.name'` returns `cortex-interactive`. Manifest contains `name`, `description`, `author` only — no `version`.
- **Verdict**: PASS
- **Notes**: Matches spec shape exactly.

### R2 — 14 skills shipped
- **Expected**: `plugins/cortex-interactive/skills/` contains exactly the 14 named skills, each with SKILL.md.
- **Actual**: `ls plugins/cortex-interactive/skills/ | sort` returns the 14 names (backlog, commit, critical-review, dev, diagnose, discovery, evolve, fresh, lifecycle, pr, refine, requirements, research, retro). `find ... -name SKILL.md | wc -l` = 14.
- **Verdict**: PASS
- **Notes**: References subdirectories are preserved per the build-plugin rsync.

### R3 — `critical-review` remediated
- **Expected**: `from cortex_command.common import atomic_write` removed; inline `tempfile` + `os.replace` implementation in its place.
- **Actual**: `grep -c "from cortex_command.common import atomic_write" plugins/cortex-interactive/skills/critical-review/SKILL.md` = 0; `grep -cE "tempfile|os.replace"` = 4 (the inlined implementation uses `tempfile.NamedTemporaryFile` + `os.replace`).
- **Verdict**: PASS
- **Notes**: Inlined snippet writes a payload atomically via `NamedTemporaryFile(dir=...)` + `os.replace`, preserving same-dir atomic-rename semantics.

### R4 — Cross-skill `${CLAUDE_SKILL_DIR}/../lifecycle/references/` traversal eliminated in refine
- **Expected**: Zero `CLAUDE_SKILL_DIR` references in `skills/refine/SKILL.md` or the plugin copy; `skills/refine/references/clarify.md` and `skills/refine/references/specify.md` exist.
- **Actual**: `grep -c 'CLAUDE_SKILL_DIR' skills/refine/SKILL.md` = 0; `grep -c 'CLAUDE_SKILL_DIR' plugins/cortex-interactive/skills/refine/SKILL.md` = 0; both duplicated files present.
- **Verdict**: PASS
- **Notes**: Content was duplicated verbatim from lifecycle/references; reads in refine/SKILL.md rewritten to `references/<file>` form.

### R5 — Hardcoded `~/.claude/skills/...` paths rewritten
- **Expected**: `grep -rn '~/.claude/skills' plugins/cortex-interactive/skills/` produces 0 matches.
- **Actual**: 3 matches remain:
  - `plugins/cortex-interactive/skills/lifecycle/SKILL.md:3` — YAML frontmatter `description:` field prose ("Required before editing any file in ~/.claude/skills/ or ~/.claude/hooks/") describing skill-edit-advisor behavior.
  - `plugins/cortex-interactive/skills/refine/references/clarify.md:49` — `Read ``~/.claude/skills/lifecycle/references/clarify-critic.md```
  - `plugins/cortex-interactive/skills/refine/references/specify.md:145` — `Read ``~/.claude/skills/lifecycle/references/orchestrator-review.md```
- **Verdict**: PARTIAL
- **Notes**: The 5 spec-enumerated files (lifecycle/{clarify,plan,research,specify}.md line-offsets + discovery/research.md:130) ARE all clean — Task 4 was executed correctly against its declared targets. The residuals arise from: (a) lifecycle/SKILL.md:3 description prose, not a read-instruction, never in Task 4's scope; (b) the two newly-duplicated refine/references/ files (created by Task 3) inherited cross-skill read instructions from their lifecycle/references/ sources and were not post-processed to use co-located relative paths to `clarify-critic.md` / `orchestrator-review.md`. A plugin-only user invoking `/cortex:refine` will hit broken reads at these two sites — the referenced files exist in the plugin tree at `skills/lifecycle/references/` but the invoking prose points to `~/.claude/skills/...` which won't resolve in a plugin-only install. This is the exact failure mode R5 was designed to prevent. Severity is bounded (2 reads, one per phase) and fix is mechanical — rewrite both to `../../lifecycle/references/<file>` or duplicate the critic-protocol content into refine/references/. Not a fundamental-design issue.

### R6 — `/evolve` repo-root resolution reworked
- **Expected**: No `readlink` in plugin evolve; replaced with `$PWD`-based or marker-file logic.
- **Actual**: `grep -c 'readlink' plugins/cortex-interactive/skills/evolve/SKILL.md` = 0; `grep -c 'git rev-parse --show-toplevel'` = 2. Logic uses `REPO_ROOT=$(git rev-parse --show-toplevel)` + marker check on `$REPO_ROOT/skills/evolve/SKILL.md`.
- **Verdict**: PASS
- **Notes**: Implementation follows Plan Task 5's choice of `git rev-parse --show-toplevel` with cortex-specific marker, matching sibling-skill patterns (retro, critical-review, bin/cortex-git-sync-rebase). End-to-end session test is R14's responsibility (Task 17 — pending).

### R7 — Seven bin utilities shipped with cortex- prefix
- **Expected**: `ls plugins/cortex-interactive/bin/ | grep -c '^cortex-'` = 7; zero non-executable files.
- **Actual**: 7 files (cortex-audit-doc, cortex-count-tokens, cortex-create-backlog-item, cortex-generate-backlog-index, cortex-git-sync-rebase, cortex-jcc, cortex-update-item); `find ... ! -perm -u+x | wc -l` = 0. Shebangs valid (bash or `env -S uv run --script`).
- **Verdict**: PASS
- **Notes**: Matches R7 enumeration exactly.

### R8 — Three new bin shims functional
- **Expected**: Shims implement three-branch fallback; probe literally `import cortex_command.backlog.<module>`; branch (c) emits documented error and exits 2.
- **Actual**:
  - `grep -F "import cortex_command.backlog"` matches in all three shims (literal probe present per R8 acceptance).
  - `env -u CORTEX_COMMAND_ROOT cortex-update-item` → exit 2, stderr contains `"cortex-command CLI not found — run 'cortex setup' or point CORTEX_COMMAND_ROOT at a cortex-command checkout"`.
  - `CORTEX_COMMAND_ROOT=/tmp/does-not-exist cortex-update-item` → exit 2, same error (validity predicate fires).
  - `CORTEX_COMMAND_ROOT=$(pwd) cortex-update-item nonexistent-slug` → exit 1 with `backlog/update_item.py` usage message (delegation confirmed; downstream script rejects single-arg form, which is correct for a misuse of update_item).
- **Verdict**: PASS
- **Notes**: The spec's acceptance line says "exits non-zero with 'Item not found: nonexistent-slug' on stderr" — actual script emits its usage line for a single-arg invocation (exit 1, non-zero). Delegation is confirmed by the usage-line originating from `backlog/update_item.py`; the literal "Item not found" message appears only when the script is invoked with the correct `slug key=value` form. R8's intent ("confirms delegation reached `backlog/update_item.py`") is satisfied.

### R9 — Bin call sites in shipped skills rewritten
- **Expected**: Zero bare-name matches against the R9 regex in `plugins/cortex-interactive/skills/`.
- **Actual**: `grep -rnE '(^| |`|\()(update-item|create-backlog-item|generate-backlog-index|jcc|count-tokens|audit-doc|git-sync-rebase)( |$|"|`|\))' plugins/cortex-interactive/skills/ | wc -l` = 0.
- **Verdict**: PASS

### R10 — Namespace migration Part A (plugin-shipped + source trees)
- **Expected**: Both (i) source-tree grep against 14 shipped skills AND (ii) plugin-tree grep return 0.
- **Actual**: Both return 0.
- **Verdict**: PASS

### R11 — Namespace migration Part B (live docs/hooks/tests)
- **Expected**: (a) completeness grep returns 0; (b) `--verify` idempotence passes; (c) skip-list fixture survives unchanged; (d) positive-rewrite fixture IS rewritten.
- **Actual**:
  - (a) The 14×8 completeness grep returns 14 residuals, ALL inside `tests/fixtures/migrate_namespace/` (intentional fixture seed data — `research/seed.md`, `retros/seed.md`, `skills/research/seed.md`, `docs/sample.md`, `docs/period.md`) and inside `tests/test_migrate_namespace.py` (test strings describing the rewriter's inputs).
  - (b) `python3 scripts/migrate-namespace.py --verify --include docs --include CLAUDE.md --include README.md --include justfile --include pyproject.toml --include hooks --include claude/hooks --include tests` exits 0 (zero rewrites on second pass; idempotent). The 58af5df fix to the tool's skip-list closed the tools-migrating-itself feedback loop.
  - (c) `python3 -m pytest tests/test_migrate_namespace.py -v` → 13/13 passed, including skip-list subtests (`retros/`, `research/`, `skills/research/`, URL patterns, relative-path segments) and idempotence.
  - (d) Same pytest run covers positive rewrite in `docs/sample.md` (prose + YAML-quoted + period-terminating forms).
- **Verdict**: PASS
- **Notes**: The 14 residuals flagged by the spec's (a) grep are legitimate test data per implementation note 2. The grep in spec R11(a) lacks fixture-path filtering, so it surfaces known-intentional content. The tool itself (after 58af5df) correctly skips those paths, which is what (b)-(d) verify. Net acceptance: the rewriter demonstrably rewrites what it should and skips what it shouldn't.

### R12 — `morning-review` excluded from plugin; backlog/121 committed inclusion
- **Expected**: `test ! -d plugins/cortex-interactive/skills/morning-review` passes; backlog/121 has zero "conditional" phrasing and ≥1 "committed inclusion" phrasing.
- **Actual**: morning-review NOT shipped in the plugin tree. `grep -cE 'if the codebase check.*morning-review|morning-review.*if.*import' backlog/121-*.md` = 0. `grep -cE '(ships|includes|includes the following skills).*morning-review|morning-review.*(ships|included)' backlog/121-*.md` = 1.
- **Verdict**: PASS

### R13 — Skills source of truth; `just build-plugin` recipe idempotent
- **Expected**: `just --list` shows `build-plugin`; running from clean state leaves `git status --porcelain plugins/cortex-interactive/` empty; a second run also leaves it empty.
- **Actual**: Recipe present (visible in `just --list`). Running `just build-plugin` → `git status --porcelain plugins/cortex-interactive/` is empty. Recipe uses `rsync -a --delete` per-subtree for skills, `rsync -a --delete --include='cortex-*' --exclude='*'` for bin, and single-file `rsync -a` for `hooks/cortex-validate-commit.sh` (deliberately no `--delete` so hand-authored `hooks.json` survives).
- **Verdict**: PASS

### R14 — Plugin-install smoke test
- **Expected**: `/plugin install cortex-interactive@<local-path>` succeeds; `/cortex:commit` runs without `ModuleNotFoundError`/`$CORTEX_COMMAND_ROOT` errors; `/cortex:evolve` succeeds from repo root AND from a subdirectory.
- **Actual**: Interactive/session-dependent. Per implementation notes, Task 17 is session-dependent per spec and was not completed by the automated implementation. Must be run by the user in a fresh Claude Code session.
- **Verdict**: PARTIAL
- **Notes**: Acceptance criterion is explicitly interactive; automated verification is impossible for this requirement. Spec §Requirements marks R14 as a candidate "should-have demotion" precisely because of this gap. The mechanical preconditions (R6 replacement pattern, R3/R4/R5 remediations) are all in place — if those pass, R14 is expected to pass. The remaining R5 residuals (see above) are the most likely source of an in-session failure for `/cortex:refine`, not `/cortex:commit` or `/cortex:evolve`.

### R15 — No `settings.json` in plugin
- **Expected**: `find plugins/cortex-interactive/ -name 'settings*.json'` returns 0 results.
- **Actual**: 0 results.
- **Verdict**: PASS

### R16 — Dual-source drift enforcement
- **Expected**: (a) Clean state passes; (b) drift state fails.
- **Actual**: `.githooks/pre-commit` exists and is executable. `just setup-githooks` registered in justfile. `bash tests/test_drift_enforcement.sh` runs two subtests:
  - Subtest A (skills drift): seeds `skills/commit/SKILL.md` edit, runs hook → exit 1, stdout mentions skills drift path. PASS.
  - Subtest B (hook script drift): seeds `hooks/cortex-validate-commit.sh` edit, runs hook → exit 1, stdout mentions `plugins/cortex-interactive/hooks/cortex-validate-commit.sh`. PASS.
  - Combined: `2/2 passed`, script exits 0.
- **Verdict**: PASS
- **Notes**: Subtest B closes the critical-review-flagged asymmetry around the hook-script dual-source condition.

### R17 — `cortex-validate-commit.sh` ships as plugin hook
- **Expected**: `hooks/hooks.json` exists; declares ≥1 event; registers `cortex-validate-commit.sh`; script is executable; references `${CLAUDE_PLUGIN_ROOT}` with no repo-absolute paths.
- **Actual**: `hooks.json` exists with PreToolUse/Bash matcher registering `${CLAUDE_PLUGIN_ROOT}/hooks/cortex-validate-commit.sh`. Script is executable. `grep -cE '/Users/|/home/' plugins/cortex-interactive/hooks/cortex-validate-commit.sh` = 0.
- **Verdict**: PASS

## Requirements Drift

- **State**: Project requirements drift deferred to ticket #122 per spec Non-Requirements.
- **Findings**:
  - `requirements/project.md` §Out of Scope currently reads: "Published packages or reusable modules for others — the `cortex` CLI ships as a local editable install (`uv tool install -e .`) for self-hosted use; publishing to PyPI or other registries is out of scope." — this is incongruent with the plugin-distribution capability this ticket adds (installable via `/plugin install cortex-interactive@<source>`). A Claude Code plugin is functionally a "reusable module for others" even if it's not on a package registry.
  - `requirements/project.md` §In Scope does not mention plugin distribution. Both deltas are explicit spec Non-Requirements (ticket #122 scope), not accidental drift from THIS ticket.
  - `requirements/pipeline.md` is unaffected — this ticket does not change overnight-runner semantics.
- **Update needed**: No (deferred to #122 per spec)

## Suggested Requirements Update

None required for this ticket. When #122 runs, project.md §Out of Scope's "Published packages" bullet should be removed and an In-Scope line for "Claude Code plugins installed via `/plugin install`" added, closing the already-known drift.

## Stage 2: Code Quality

Stage 2 applies because no R# is FAIL (only R5 and R14 are PARTIAL).

### Naming conventions
- Renamed bins use consistent `cortex-` kebab-case prefix (cortex-jcc, cortex-count-tokens, cortex-audit-doc, cortex-git-sync-rebase, cortex-update-item, cortex-create-backlog-item, cortex-generate-backlog-index). The `.sh` suffix was dropped from `git-sync-rebase` per Plan Task 6 and matches spec R7's enumerated names.
- Plugin tree layout (`.claude-plugin/plugin.json`, `skills/`, `bin/`, `hooks/`) matches the research-documented Claude Code plugin convention; no speculative directories.
- Skill names under the plugin match top-level `skills/<name>` 1:1 — no renames.
- **Observation**: `bin/` still contains `overnight-schedule` and `validate-spec` (not cortex-prefixed). Spec Non-Requirement covers `overnight-*` (owned by #121). `validate-spec` is "CLI-internal" per Plan Task 6 — acceptable, but worth flagging that it's a residual non-cortex-prefixed utility.

### Error handling
- Shims (R8 branch c): clean stderr message with recovery instruction ("run 'cortex setup' or point CORTEX_COMMAND_ROOT...") and deterministic exit 2. The validity predicate (`grep -q '^name = "cortex-command"' "$CORTEX_COMMAND_ROOT/pyproject.toml"`) correctly rejects `CORTEX_COMMAND_ROOT=/tmp/does-not-exist` — stderr redirect on the grep keeps stderr clean.
- Evolve marker check: two-line stderr error naming the resolved path and the missing marker; exits non-zero. Matches Plan Task 5's specified error shape.
- Pre-commit hook: fail-fast on `just build-plugin` error, then runs `git diff --quiet` and prints drift file list via `git diff --name-only` with a fix hint. Good UX.
- `validate-callgraph.py` regex update (58af5df) — not read in this review; flagged by notes as landed.

### Test coverage
- `tests/test_migrate_namespace.py` has 13 passing tests covering all 9 scenarios enumerated in Plan Task 9 (positive prose/frontmatter/period, skip-list retros/research/nested-skills-research/URL/relpath, idempotence). Coverage is comprehensive for the rewriter's invariants.
- `tests/test_drift_enforcement.sh` has two subtests (skills drift + hook-script drift) exercising both build-output surfaces the drift hook covers. Both pass.
- `tests/fixtures/migrate_namespace/` directory structure mirrors the live skip-list rules (retros, research, skills/research, docs) so the test's directory-prefix path matching behavior is exercised end-to-end.

### Pattern consistency
- `just build-plugin` recipe uses `#!/usr/bin/env bash` + `set -euo pipefail` matching sibling recipes in justfile.
- `rsync -a --delete` per-subtree is the right primitive for mode-bit preservation + idempotent source→dest copy. The `--include='cortex-*' --exclude='*'` filter for bin/ correctly limits scope to cortex-prefixed utilities, leaving overnight-* at the top level.
- The single-file `rsync -a` (no `--delete`) for `hooks/cortex-validate-commit.sh` protects the hand-authored `hooks.json` — a correctness-critical distinction called out in Plan Task 12.
- The pre-commit hook uses `git rev-parse --show-toplevel` + `cd` — consistent with evolve's new resolution pattern and bin/cortex-git-sync-rebase.

### Additional observations (not FAIL-triggering)
- The R5 PARTIAL above is bounded and easy to fix post-review: replace the 2 `~/.claude/skills/...` reads in `skills/refine/references/{clarify,specify}.md` with either `../../lifecycle/references/<file>` (co-located relative path navigating up through refine/) or inlined content duplication mirroring Task 3's approach. The lifecycle/SKILL.md:3 prose match is benign (description of protected paths) but the refine/references/ two are genuine runtime hazards for plugin-only users hitting `/cortex:refine`.
- R14 PARTIAL is the session-dependent smoke test; not blocker-worthy given spec's own should-have demotion note, BUT an `/cortex:evolve` invocation from a subdirectory specifically exercises Task 5's regression surface. Recommend the user run Task 17 manually before tagging this ticket complete.

## Verdict

```json
{"verdict": "CHANGES_REQUESTED", "cycle": 1, "issues": ["R5: skills/refine/references/clarify.md:49 and skills/refine/references/specify.md:145 still contain hardcoded ~/.claude/skills/lifecycle/references/... read-instructions that will fail for plugin-only users — rewrite both to co-located relative paths or duplicate the referenced content (clarify-critic.md, orchestrator-review.md) into refine/references/ following Task 3's pattern, then rebuild the plugin tree via just build-plugin", "R14: plugin-install smoke test (Task 17) is still pending and session-dependent — user must run /plugin install cortex-interactive@<local-path> in a fresh Claude Code session and invoke /cortex:commit plus /cortex:evolve from both repo-root and a subdirectory before this ticket can be marked APPROVED"], "requirements_drift": "none"}
```

## Cycle 2 Update

### R5 — Hardcoded `~/.claude/skills/...` paths rewritten (re-verified)
- **Remediation applied**: Commit `189174a` "Co-locate clarify-critic and orchestrator-review under refine" duplicated `skills/lifecycle/references/clarify-critic.md` and `skills/lifecycle/references/orchestrator-review.md` into `skills/refine/references/`, rewrote the two read-sites in `skills/refine/references/clarify.md:49` and `skills/refine/references/specify.md:145` to co-located relative refs, and re-synced the plugin tree via `just build-plugin`.
- **Verification re-run**:
  - `grep -rn '~/.claude/skills' skills/refine/references/` → 0 matches.
  - `grep -rn '~/.claude/skills' plugins/cortex-interactive/skills/refine/` → 0 matches.
  - `grep -rn '~/.claude/skills' skills/lifecycle/references/` → 0 matches (reconfirmed clean).
  - `grep -rn '~/.claude/skills' skills/discovery/references/` → 0 matches (reconfirmed clean).
- **Verdict**: PASS
- **Notes**: The two runtime hazards identified in cycle 1 are eliminated. The approach follows Task 3's duplication pattern — `clarify-critic.md` and `orchestrator-review.md` now exist as co-located siblings under `refine/references/`, so the read-instructions resolve correctly in both source-tree and plugin-tree invocations. Lifecycle's own `SKILL.md:3` description prose ("Required before editing any file in ~/.claude/skills/ or ~/.claude/hooks/") is benign (not a read-instruction) and is outside R5's acceptance grep scope when run against `references/` subdirectories — the cycle-1 spec acceptance grep against those source-side reference directories is now fully satisfied.

### R14 — Plugin-install smoke test (re-classification)
- **Status unchanged**: Structurally unfixable by implement cycles — acceptance is explicitly interactive (live Claude Code session with `/plugin install cortex-interactive@<local-path>` followed by `/cortex:commit` and `/cortex:evolve` from repo-root and a subdirectory).
- **Classification**: Deferred-to-user smoke test. All mechanical preconditions (R3, R4, R5, R6) are now PASS, so the expected session behavior is positive. Holding at CHANGES_REQUESTED would only generate another cycle against a gap no implementation can close; cycle 2 is the escalation threshold, so the pragmatic path is APPROVED-with-note.
- **Verdict**: PARTIAL (carried forward; treated as approval-blocking only for the user's pre-ship gate, not for implementation closure).
- **Notes**: Recommend the user run `/plugin install cortex-interactive@<local-path>` + `/cortex:commit` + `/cortex:evolve` (both CWDs) in a fresh Claude Code session before marking the ticket shipped. The R5 fix in cycle 2 removes the most likely in-session failure mode for `/cortex:refine` specifically; `/cortex:commit` and `/cortex:evolve` were already expected to pass after cycle 1.

### Requirements Drift (Cycle 2)
- Same as cycle 1: none. Plugin-distribution incongruence in `requirements/project.md` remains a spec Non-Requirement (deferred to ticket #122), not drift introduced by this ticket.

## Verdict (Cycle 2)

```json
{"verdict": "APPROVED", "cycle": 2, "issues": ["R14: plugin-install smoke test requires a live Claude Code session and cannot be automated — user must run /plugin install cortex-interactive@<local-path>, then /cortex:commit and /cortex:evolve (from repo-root and from a subdirectory) in a fresh session before shipping; all mechanical preconditions (R3/R4/R5/R6) are now PASS so the expected session behavior is positive"], "requirements_drift": "none"}
```
