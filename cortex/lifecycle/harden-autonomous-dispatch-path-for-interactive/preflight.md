# Preflight: harden-autonomous-dispatch-path-for-interactive

This is the R22 preflight artifact for backlog 208. It records the file inventory this lifecycle modifies, the commit hash at preflight-run time, and the active Claude Code version.

## Scope note

The sandbox preflight gate at `bin/cortex-check-parity` validates a YAML schema whose `pass`/`stderr_contains_eperm`/`target_unmodified` fields are produced by an interactive kernel-level sandbox-enforcement test on the operator's machine. **This lifecycle did not stage changes to the patterns the gate watches** (`_spawn_orchestrator` / `--settings` / `sandbox` regions of `runner.py`; `_load_project_settings`/`SandboxSettings`/`build_sandbox`/`write_settings_tempfile` regions of `pipeline/dispatch.py`; `sandbox_settings.py`; `claude-agent-sdk` line in `pyproject.toml`), so the gate does not fire on this lifecycle's commits.

The file inventory below is therefore the operative record: a file-list-superset artifact per R22 acceptance, not a kernel-test-result artifact. Running the canonical sandbox preflight test (against `cortex_command/pipeline/dispatch.py` per the existing apply-per-spawn lifecycle's contract) remains the operator's responsibility if a future change in this area re-touches the gate-watched patterns.

```yaml
pass: false  # not a kernel-test artifact; gate did not fire on this lifecycle
timestamp: "2026-05-13T01:42:00Z"
commit_hash: "4c239fe32144118036a2ba4cc588e11e1e237a91"
claude_version: "2.1.140"
test_command: "bin/cortex-check-parity --staged"
exit_code: 0
stderr_contains_eperm: false
stderr_excerpt: ""
target_path: "cortex_command/pipeline/dispatch.py"
target_unmodified: true
```

## File inventory (union of files modified by Tasks 1–19)

This list is the operative superset per R22 acceptance ("file list in preflight.md is a superset of (or equal to) the union of files modified by R1–R21").

### Source files

- `cortex_command/overnight/auth.py` (R1, R2, R3, R5)
- `cortex_command/overnight/daytime_pipeline.py` (R3, R9, R18)
- `cortex_command/overnight/runner.py` (R3)
- `cortex_command/overnight/readiness.py` (R18) — new
- `cortex_command/pipeline/worktree.py` (R6, R8, R9)
- `cortex_command/init/handler.py` (R7)
- `cortex_command/common.py` (R13) — `main()` wrapper added
- `cortex_command/overnight/daytime_result_reader.py` (R13) — `main()` wrapper added
- `cortex_command/overnight/report.py` (R13) — `main()` wrapper added

### Tests

- `cortex_command/overnight/tests/test_auth.py` (R1, R2)
- `cortex_command/overnight/tests/test_daytime_auth.py` (R3)
- `cortex_command/overnight/tests/test_daytime_pipeline.py` (R18 follow-up)
- `cortex_command/overnight/tests/test_dispatch_readiness.py` (R18) — new
- `cortex_command/overnight/tests/test_synthesizer_circuit_breaker.py` (Task 3 follow-up)
- `tests/test_runner_auth.py` (R3) — new
- `tests/test_worktree.py` (R6, R9)
- `tests/test_worktree_probe.py` (R8) — new
- `tests/test_init_worktree_registration.py` (R7) — new
- `tests/test_dispatch_parity.py` (R19, R21) — new

### Skill / hook / doc / config

- `pyproject.toml` (R13) — 14 new `[project.scripts]` entries
- `bin/.events-registry.md` (R4) — `auth_probe` event registered
- `bin/.parity-exceptions.md` (R13) — temporary R13 allowlist (3 remaining rows; 11 removed once R14 wiring landed)
- `bin/.audit-bare-python-m-allowlist.md` (R12d) — new
- `bin/cortex-check-parity` (R12c) — `--audit-bare-python-m-callsites` mode added
- `justfile` (R12e, R20) — `check-bare-python-callsites` + `test-dispatch-parity-launchd-real` recipes added
- `hooks/cortex-scan-lifecycle.sh` (R14)
- `skills/lifecycle/SKILL.md` (R14)
- `skills/lifecycle/references/implement.md` (R10, R14)
- `skills/critical-review/SKILL.md` (R14)
- `skills/critical-review/references/verification-gates.md` (R14)
- `skills/morning-review/SKILL.md` (R14)
- `skills/morning-review/references/walkthrough.md` (R14)
- `skills/discovery/SKILL.md` (R14)
- `skills/overnight/references/new-session-flow.md` (R16)
- `docs/overnight-operations.md` (R11, R14)
- `cortex/requirements/pipeline.md` (R11) — vscode/idea edge case cross-link
- `cortex/requirements/project.md` (R15) — skill-helper-modules clause
- `CHANGELOG.md` (R17)

### Lifecycle artifacts (per `commit-artifacts: true` config)

- `cortex/lifecycle/harden-autonomous-dispatch-path-for-interactive/research.md`
- `cortex/lifecycle/harden-autonomous-dispatch-path-for-interactive/spec.md`
- `cortex/lifecycle/harden-autonomous-dispatch-path-for-interactive/plan.md`
- `cortex/lifecycle/harden-autonomous-dispatch-path-for-interactive/index.md`
- `cortex/lifecycle/harden-autonomous-dispatch-path-for-interactive/events.log`
- `cortex/lifecycle/harden-autonomous-dispatch-path-for-interactive/audit-callsites.md`
- `cortex/lifecycle/harden-autonomous-dispatch-path-for-interactive/preflight.md` (this file)

### Auto-regenerated plugin mirrors

The dual-source pre-commit hook automatically regenerates the following mirrors when their canonical source under `skills/`, `hooks/`, or `bin/` changes:

- `plugins/cortex-core/skills/...` (lifecycle, critical-review, discovery)
- `plugins/cortex-core/bin/cortex-check-parity`
- `plugins/cortex-overnight/skills/overnight/...` (new-session-flow.md)
- `plugins/cortex-overnight/skills/morning-review/...`
- `plugins/cortex-overnight/hooks/cortex-scan-lifecycle.sh`
