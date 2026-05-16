# Decomposition: windows-support

## Epic
- **Backlog ID**: 215
- **Title**: Add native Windows host support for the agentic harness

## Work Items

| ID  | Title                                                    | Priority | Size  | Depends On |
|-----|----------------------------------------------------------|----------|-------|------------|
| 216 | Add platform abstraction package for Windows             | medium   | M     | —          |
| 217 | Port overnight scheduler to Windows Task Scheduler       | low      | L     | 216        |
| 218 | Bootstrap Windows install and validate hook execution    | medium   | M-L   | —          |
| 219 | Add Windows posture surface and advisory CI              | medium   | S-M   | 216        |

## Suggested Implementation Order

**Windows v1** (interactive cortex on Windows): 216 → 218 → 219 (216 lands the platform package; 218 delivers the installer and validates hook execution; 219 wraps the posture statement, runtime warning, and advisory CI). After v1, Windows users can run skills, CLI utilities, the dashboard, and hooks.

**Windows v2** (overnight runner support): 217 lands the scheduler port on top of 216's platform package.

## Out of Scope (Documented in Epic 215)

- cortex-ui-extras plugin port — EXPERIMENTAL plugin with heavy Unix-centric assumptions (bash globs, `uv run --script` shebangs, Husky). Deferred to a separate follow-up epic if pursued.
- cortex-pr-review's evidence-ground.sh — single bash script in an optional plugin. Stays bash; documented as requiring Git for Windows on Windows hosts.
- tests/test_*.sh — eight bash test scripts invoked by the justfile test recipe. Require Git for Windows to run on Windows clones. Documented; not rewritten in this epic.
- .githooks/pre-commit — contributor pre-commit hook (~13.6KB bash). Runs under Git for Windows' bundled bash on Windows clones. Documented; not rewritten.

## Created Files

- `cortex/backlog/215-add-native-windows-host-support-for-the-agentic-harness.md` — epic
- `cortex/backlog/216-add-platform-abstraction-package-for-windows.md` — platform abstraction package
- `cortex/backlog/217-port-overnight-scheduler-to-windows-task-scheduler.md` — overnight scheduler port
- `cortex/backlog/218-bootstrap-windows-install-and-validate-hook-execution.md` — installer + hook validation (merged at decompose time)
- `cortex/backlog/219-add-windows-posture-surface-and-advisory-ci.md` — posture surface + advisory CI

## Decomposition Notes

- The research-phase Architecture initially named 7 pieces; the post-Architecture critical review compressed to 5. At decompose time, the user merged the two install-related pieces (former 218 hooks + 219 installer) into one ticket because the empirical hook test requires the installer to have run on the same Windows VM session — bundling keeps the atomic validation work in one ticket.
- A second pass of explore agents surfaced additional touch points (lsof in pipeline/worktree.py stale-lock cleanup; module-level POSIX imports in 5 test files that crash collection on Windows; observability.md spec/implementation mismatch). All folded into 216 and 219 without changing the piece count.
