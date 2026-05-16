---
id: 218
title: "Bootstrap Windows install and validate hook execution"
type: feature
status: not-started
priority: medium
parent: 215
tags: [windows-support, install, hooks, validation, bootstrap]
created: 2026-05-15
updated: 2026-05-15
discovery_source: cortex/research/windows-support/research.md
---

# Bootstrap Windows install and validate hook execution

## Role

Deliver the Windows install path and establish how cortex-shipped hooks fire on the same Windows host, as one coupled deliverable. The empirical hook test (does a Python entry point's `.exe` shim work as Claude Code's exec-form `command:` on Windows?) requires the installer to have run on the same Windows VM session so cortex-* entry points are on PATH; bundling install and hook validation keeps the atomic empirical work in one ticket.

The install half mirrors the three steps of the macOS bash installer: install uv if missing, run uv tool install against the cortex repo at the current tag, print next-steps. A Windows-troubleshooting subsection in setup docs covers the five known uv-on-Windows gotchas (PATH propagation requiring uv tool update-shell, antivirus false positives, multi-shim write contention, Git Credential Manager auth quirks, symlink admin requirement). Empirical verification that cortex init runs cleanly is part of the same VM session.

The hook half then runs the empirical exec-form-command test. If shims work, cortex-shipped hooks that already shell out to Python entry points become direct entry-point invocations and the wrapper scripts are deleted from the canonical hooks tree. If shims do not work, PowerShell siblings are authored following the statusline precedent (a `.ps1` next to each `.sh`). Hook test scripts under tests/ and the contributor pre-commit hook under .githooks/ remain bash and are documented as requiring Git for Windows — out of scope for this piece.

## Integration

Lands a new top-level installer script as a sibling to the existing bash installer. Modifies setup documentation to add a Windows quickstart and troubleshooting section. The installer's three steps depend on uv being installed (the installer installs it if absent) and Git for Windows being installed (uv shells out to system git for git-source installs). After install validation, the empirical hook test interfaces with Claude Code's hook resolver: cortex authors `command:` strings in its plugin's hook configurations, and Claude Code's resolver routes them to Git Bash, PowerShell, or direct executable invocation per documented rules. The choice between exec-form entry points and shell-routed scripts shapes what files get shipped under the canonical hooks tree and propagated to the plugin mirror by the dual-source pre-commit drift enforcer.

## Edges

- Breaks if uv changes the URL or shape of its official Windows installer or its `uv tool install` console-script semantics.
- Breaks if Claude Code's hook resolver changes its handling of exec-form vs shell-form `command:` strings on Windows.
- Depends on Git for Windows being present on the host — uv has no embedded git binary.
- Depends on the cortex pyproject scripts table producing `.exe` shims in the standard Windows tool-install location; the empirical exec-form test consumes these shims.
- The dual-source drift enforcer syncs hook files from the canonical roots to the plugin mirror; deletions of canonical `.sh` files must propagate.
- The `.ps1`-sibling pattern (a PowerShell counterpart adjacent to each `.sh`) is the documented fallback when exec-form shims fail.
- The cortex-init first-run behavior on Windows is shaped by the posture surface piece, which adds the transitional sandbox warning that fires during init.

## Touch points

- `install.sh` (existing macOS installer to mirror; three-step structure)
- `docs/setup.md` (Quickstart and Dependencies sections; Windows troubleshooting subsection to add)
- `pyproject.toml` (`[project.scripts]` entries that uv installs as Windows `.exe` shims; consumed by the hook empirical test)
- `cortex_command/init/handler.py` (cortex-init flow; smoke-test target for the Windows-VM install validation)
- `hooks/cortex-validate-commit.sh` (primary validation candidate; today shells out to a Python entry point)
- `hooks/cortex-scan-lifecycle.sh`
- `hooks/cortex-cleanup-session.sh`
- `claude/hooks/cortex-tool-failure-tracker.sh`
- `claude/hooks/cortex-skill-edit-advisor.sh`
- `claude/hooks/cortex-permission-audit-log.sh`
- `claude/hooks/cortex-worktree-create.sh`
- `claude/hooks/cortex-worktree-remove.sh`
- `claude/statusline.sh` and `claude/statusline.ps1` (existing dual-artifact pattern reference for the fallback path)
- `plugins/cortex-core/hooks/` (auto-regenerated mirror tree; deletions or additions must propagate)
