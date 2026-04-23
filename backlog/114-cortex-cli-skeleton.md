---
schema_version: "1"
uuid: 9b5c4931-763b-4112-b261-a111119cb99f
title: "Build cortex CLI skeleton with uv tool install entry point"
status: refined
priority: high
type: feature
parent: 113
tags: [distribution, cli, overnight-layer-distribution]
areas: [install]
created: 2026-04-21
updated: 2026-04-23
lifecycle_slug: null
lifecycle_phase: null
session_id: null
blocks: []
blocked-by: []
discovery_source: research/overnight-layer-distribution/research.md
spec: lifecycle/build-cortex-cli-skeleton-with-uv-tool-install-entry-point/spec.md
---

# Build cortex CLI skeleton with uv tool install entry point

## Context from discovery

Every other ticket in this epic depends on the `cortex` CLI existing — it owns the runner, dashboard, MCP server, setup subcommand, and scaffolder. This ticket is the foundational wiring: a Python package declaring a console entry point for `cortex`, installable via `uv tool install -e .`, with subcommand scaffolding (probably `click` or `typer`, `argparse` is the floor). aider's Jan 2025 move to `uv tool install` is the reference precedent.

## Scope

- Add `[build-system]` to `pyproject.toml` (hatchling or setuptools) so `uv tool install -e .` works reliably — `uv sync` has regression-removed editable installs when this is missing (uv#9518)
- Declare the `cortex` entry point
- Subcommand scaffolding with placeholder implementations (`overnight`, `mcp-server`, `setup`, `init`, `upgrade`) that return "not yet implemented" until their respective tickets land
- Verify `uv tool install -e /path/to/cortex-command` produces a working `cortex --help` on PATH
- Document the "cortex's internal `uv run` calls operate on the user's project, not on the tool's own venv" constraint so users don't `uv tool uninstall uv`

## Out of scope

- Actual overnight/mcp-server/setup/init implementations (their own tickets)
- `cortex upgrade` logic (will be added when the bootstrap ships — ticket 118)

## Research

See `research/overnight-layer-distribution/research.md` DR-4 (`uv tool install` rationale), DR-5 (separation of install from deployment), and the CLI packaging report (`_cli-packaging-report.md`). Sharp edges including uv#9518 and the `uv tool update-shell` PATH setup are documented in the Sharp edges section.
