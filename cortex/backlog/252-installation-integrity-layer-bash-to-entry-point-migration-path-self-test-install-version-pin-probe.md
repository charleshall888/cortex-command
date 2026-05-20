---
schema_version: "1"
uuid: e60729f1-9799-4a4b-ba3f-d004a8840da5
title: "Installation integrity layer: bash-to-entry-point migration, PATH self-test, install-version pin probe"
status: complete
priority: high
type: feature
created: 2026-05-20
updated: 2026-05-20
parent: "251"
tags: [harness, cli, plugin-distribution]
discovery_source: cortex/research/harness-friction-triage/research.md
complexity: complex
criticality: high
spec: cortex/lifecycle/installation-integrity-layer-bash-to-entry/spec.md
areas: [skills,hooks]
session_id: null
---

## Role

Closes the three install-time failure modes that together produce "binary not on PATH" friction across installed-user sessions. The three failure modes are: bash scripts referenced by skill prose that have no corresponding entry point on the installed user's PATH; the plugin-tier bin directory that the SessionStart PATH bootstrap never exposes; and the stale uv-tool venv that lags the repo's declared entry-point set after `pyproject.toml` adds new scripts. The remediation set is bash-to-entry-point promotion (per Decision Record DR4 this explicitly includes the resolver script formerly held back by the install_guard boundary), a SessionStart PATH self-test, and an install-version pin probe that detects venv-vs-repo skew at session start.

## Integration

Consumes the canonical "set of `cortex-*` invocations across skill prose" emitted by the skill-prose contract-lint child as a derived artifact, and uses that enumeration to seed the PATH self-test's top-N binary list. Coordinates with the already-refined ticket 235 (`trigger-cortex-cli-reinstall-at-sessionstart-on-cli-pin-drift`), which owns the SessionStart-hook approach for CLI/version pin drift; this ticket extends or attaches to 235's lifecycle rather than competing with it.

## Edges

- Breaks if the `[project.scripts]` table in `pyproject.toml` stops being the canonical declaration surface for installable CLIs.
- Depends on the `install_guard` boundary semantics that currently keep some bash scripts off the wheel side; Decision Record DR4 closes that boundary for the resolver case by promoting the bash script to a Python entry point.
- Depends on ticket 235 owning the SessionStart-hook surface; this ticket attaches to 235's lifecycle for the pin-probe sub-deliverable rather than introducing a competing hook.
- Behavior change at install time: each promoted bash script will newly appear as an importable module under the `cortex_command` namespace; downstream consumers that source the bash form by absolute path must migrate.

## Touch points

- `bin/` directory — 25 bash scripts to inventory and migrate; one already dual-channel (`cortex-morning-review-complete-session`); the remaining 24 lack `[project.scripts]` entries.
- `pyproject.toml` lines 21-43 — `[project.scripts]` table; this is the canonical declaration surface for new entry points added by the migration.
- `plugins/cortex-core/hooks/cortex-session-start-path-bootstrap.sh:29` — the PATH bootstrap line that currently prepends only `~/.local/bin`; the PATH self-test attaches here.
- `cortex/backlog/235-trigger-cortex-cli-reinstall-at-sessionstart-on-cli-pin-drift.md` — active owner of the pin-probe sub-deliverable; status `refined`.
- `bin/cortex-resolve-backlog-item:32-36` — install_guard boundary that DR4 closes by promoting this script to a Python entry point.
