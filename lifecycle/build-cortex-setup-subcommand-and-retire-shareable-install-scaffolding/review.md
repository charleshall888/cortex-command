# Review: build-cortex-setup-subcommand-and-retire-shareable-install-scaffolding

## Stage 1: Spec Compliance

### Requirement 1: Delete `/setup-merge` skill and its merge helper
- **Expected**: `.claude/skills/setup-merge/` fully removed; no code references to `setup-merge` or `merge_settings` outside archive/lifecycle/research/retros/backlog archive.
- **Actual**: Directory deleted (`test -e .claude/skills/setup-merge` returns `1`). Grep for `setup-merge|merge_settings` returns only backlog items (all `status: complete` plus one `debug/` log — both historical per Technical Constraint #8 scoping; debug/ is a session log, not a live reference).
- **Verdict**: PASS
- **Notes**: Spec R1's "exclude-dir" list doesn't include `debug/`, but the debug log is a historical session postmortem (dated 2026-04-08) — not a live reference. Intent met.

### Requirement 2: Delete `just setup`, `just setup-force`, `just deploy-*`, `just check-symlinks`, `just verify-setup` recipes
- **Expected**: All 9 recipes removed; `just --list` clean; `grep -E "^(setup|setup-force|deploy-(bin|reference|skills|hooks|config)|check-symlinks|verify-setup):" justfile` returns no matches.
- **Actual**: All 9 recipes gone. Additionally, the orphan `verify-setup-full` recipe (which called `just verify-setup`) was also removed via a fix-up commit. `setup-tmux-socket` prose updated per Task 9. `just --list` confirms none of the retired recipes survive.
- **Verdict**: PASS

### Requirement 3: Delete `claude/Agents.md`
- **Expected**: File deleted; no `Agents.md` references across repo (excluding lifecycle/research/retros/.claude/backlog/archive).
- **Actual**: File deleted. Strict grep surfaces 5 backlog items (005, 006, 046, 085 = `status: complete`; 086 = `status: blocked`). Spec Technical Constraint #8 classifies backlog audit as advisory.
- **Verdict**: PASS
- **Notes**: Letter-of-grep would include backlog/ in scope, but spec's Technical Constraint #8 and Veto Surface #6 resolve backlog items as each author's responsibility. Intent (deploy-source retired) met.

### Requirement 4: Delete `claude/rules/`
- **Expected**: Directory removed.
- **Actual**: `test -d claude/rules` returns `1`. Both `global-agent-rules.md` and `sandbox-behaviors.md` deleted from git.
- **Verdict**: PASS

### Requirement 5: Delete `claude/reference/`
- **Expected**: Directory removed (all 4 files).
- **Actual**: `test -d claude/reference` returns `1`. All four reference docs (parallel-agents, context-file-authoring, claude-skills, output-floors) deleted from git.
- **Verdict**: PASS

### Requirement 6: Delete `claude/settings.json`
- **Expected**: File removed.
- **Actual**: `test -f claude/settings.json` returns `1`.
- **Verdict**: PASS

### Requirement 7: Delete `hooks/cortex-notify.sh`
- **Expected**: Deploy-source file removed; no residual references in repo source.
- **Actual**: Deploy source deleted (`test -f hooks/cortex-notify.sh` returns `1`). Strict grep still hits 17 `~/.claude/notify.sh` runtime callers in `cortex_command/pipeline/report.py:117,124`, `cortex_command/overnight/report.py:1449`, `cortex_command/overnight/runner.sh` (13 sites), plus test fixtures and `claude/hooks/cortex-worktree-remove.sh` that look up the notifier at the machine-config-provided path.
- **Verdict**: PASS
- **Notes**: Spec R7's intent is deploy-source retirement — cortex-command no longer ships the notify helper from `hooks/`. Runtime code correctly calls the machine-config-provided `~/.claude/notify.sh` (per spec Non-Requirements: "no deployment to `~/.claude/`" covers cortex-command not shipping the target, not forbidding runtime code from invoking a machine-config target). Runner.sh's 13 sites are explicitly ticket 115's scope (per 115's backlog frontmatter). Intent met.

### Requirement 8: Remove `setup` subparser from `cortex_command/cli.py`
- **Expected**: `cortex --help` no longer lists `setup`; programmatic subparser check returns no `setup` key.
- **Actual**: `python3 -c "from cortex_command.cli import _build_parser; ..." ` confirms choices are `['overnight', 'mcp-server', 'init', 'upgrade']`. Parser description updated ("orchestrates overnight runs and the MCP server."). EPILOG note retained without setup-specific text.
- **Verdict**: PASS

### Requirement 9: Preserve `claude/statusline.sh` at its current path
- **Expected**: File preserved.
- **Actual**: `test -f claude/statusline.sh` returns `0`.
- **Verdict**: PASS

### Requirement 10: Preserve `skills/`, `hooks/`, `claude/hooks/`, `bin/` directories
- **Expected**: All four directories preserved.
- **Actual**: All four exist (verified via `test -d`).
- **Verdict**: PASS

### Requirement 11: Documentation updated across repo and active backlog items
- **Expected**: R11 grep (`just setup|just deploy-|/setup-merge|setup-merge|cortex setup|~/.claude/rules|~/.claude/reference`) returns zero hits for any non-complete file in `README.md`, `docs/`, `CLAUDE.md`, `skills/`, `backlog/`.
- **Actual**: Clean for README/docs/CLAUDE.md/skills. In `backlog/`, 14 active items retain these strings (Task 7 deferred per Veto Surface #3). `backlog/118-bootstrap-installer-curl-sh-pipeline.md` was updated as the worked example. `backlog/index.{json,md}` regenerated.
- **Verdict**: PASS
- **Notes**: Per Technical Constraint #8 ("backlog audit is advisory, not mandatory") and Veto Surface #6 (load-bearing cross-ticket prose stays with the sibling author), the 14 deferred backlog items are an acceptable outcome. Non-backlog surfaces (README/docs/CLAUDE.md/skills) are clean.

### Requirement 12: Update CLAUDE.md symlink-architecture and deploy-bin sections
- **Expected**: `grep -E "Key symlinks|deploy-bin pattern|~/\.claude/hooks|~/\.claude/skills|just setup" CLAUDE.md` returns zero matches.
- **Actual**: Exact-spec grep returns zero matches. New "Distribution" section accurately describes the CLI-plus-plugins model.
- **Verdict**: PARTIAL
- **Notes**: Literal R12 grep passes, but CLAUDE.md still carries two stale command references outside the specific grep: line 18 still reads ``- `bin/` - Global CLI utilities (deployed to `~/.local/bin/`)``; line 30 still lists ``- Check symlinks: `just check-symlinks` `` which points at a recipe deleted by R2; line 49's `jcc` bullet still mentions `jcc deploy-bin` as an example. None of these violate R12's literal grep (which doesn't include `check-symlinks`, bare `deploy-bin`, or `~/.local/bin/`), but they're internally inconsistent with R2 and R10's stance on bin deployment. Call it PARTIAL rather than FAIL because the spec's acceptance grep is binary and passes.

### Requirement 13: No test coverage added in this ticket
- **Expected**: `just test` exits 0; no test regressions from deletions.
- **Actual**: `just test` reports "Test suite: 3/3 passed". `cortex_command/dashboard/tests/test_alerts.py` runs 14 tests (all pass) after the subprocess path was removed from `alerts.py`.
- **Verdict**: PASS
- **Notes**: Plan's Task 11 edited `test_alerts.py` to drop the subprocess-specific assertions (not net-new tests; existing tests continue to guard dedup contract). Spec R13's "existing tests that exercise deleted recipes are also removed" applies cleanly.

## Requirements Drift

**State**: none
**Findings**:
- None — this ticket is pure retirement, and the retired surface (cortex-command deploying files into `~/.claude/`) was not itself captured as a requirements-level behavior in `requirements/project.md` or `requirements/pipeline.md`. The post-retirement reality (cortex-command writes nothing under `~/.claude/`; machine-config owns notify.sh/settings.json; plugins own hooks/skills deployment) is consistent with `requirements/project.md` Out-of-Scope boundaries (machine config belongs in machine-config) and Quality Attributes (defense-in-depth permissions remains meaningful because it characterizes the settings template — the template just now lives in machine-config). The project-scope `.claude/settings.json` introduced by Task 14 preserves commit-validation behavior in-repo, which aligns with the existing "shared hook validates commit messages automatically" convention in `CLAUDE.md`.
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Consistent — `.claude/settings.json` uses the documented `$CLAUDE_PROJECT_DIR` pattern (matches Anthropic's Claude Code configuration-scopes guidance); the EPILOG text in `cli.py` is accurate and free of the deleted `setup` reference; the parser description ("orchestrates overnight runs and the MCP server.") correctly mirrors the remaining four subcommands.
- **Error handling**: `fire_notifications()` in `alerts.py` now uses `logger.info("alert: %s", message)` in place of the subprocess call. Dedup contract (`notified` flag) is preserved; no silent swallowing. The inline docstring explicitly notes the shell channel was retired and machine-config is now responsible — future reader won't be confused by the missing subprocess path.
- **Test coverage**: `test_alerts.py` covers all four alert conditions plus dedup and idempotency on `fire_notifications()`. The docstring update at line 170-175 documents the rationale for the removed subprocess assertions. 14/14 pass in 0.06s. `just test` aggregate: 3/3 suites green.
- **Pattern consistency**: The new project-scope `.claude/settings.json` matches the Claude Code documented env-var pattern (`"$CLAUDE_PROJECT_DIR"/hooks/cortex-validate-commit.sh`) rather than the retired absolute-path form (`~/.claude/hooks/cortex-validate-commit.sh`). Single-hook file with no permission/sandbox/statusline noise — exactly as Task 14 specified. The file layers on top of `.claude/settings.local.json` as intended by Claude Code's configuration scopes.

## Verdict

The implementation fully retires the shareable-install scaffolding per R1–R13. All structural deletions are verified, `just test` passes, `cortex --help` shows the correct four subcommands, and R12's literal acceptance grep on CLAUDE.md returns zero matches. Two minor partial gaps in CLAUDE.md (lines 18, 30, 49) carry stale pointers to retired recipes (`just check-symlinks`, `jcc deploy-bin`) and to the pre-117 `bin/` deployment model — these don't violate the spec's literal R12 grep but are internally inconsistent. They are fix-on-touch clean-ups, not blockers. Given the spec's binary acceptance criterion passes and the implementation matches spec intent across all 13 requirements, recommend APPROVED with an advisory note to tidy the three lines in a follow-up.

```json
{"verdict": "APPROVED", "cycle": 1, "issues": ["CLAUDE.md line 18 still describes `bin/` as 'deployed to `~/.local/bin/`' — inconsistent with R10's bin-stays-in-place-until-120 stance and the retired `deploy-bin` recipe", "CLAUDE.md line 30 lists `just check-symlinks` as a Key command — recipe was deleted by R2", "CLAUDE.md line 49 uses `jcc deploy-bin` as an example — `deploy-bin` recipe retired"], "requirements_drift": "none"}
```
