---
schema_version: "1"
uuid: 906b88bb-880d-4c16-ba42-1133a4c1f875
title: "CLI_PIN drift lint (#146 hygiene)"
status: superseded
priority: medium
type: chore
created: 2026-05-13
updated: 2026-05-13
discovery_source: 210-refresh-install-update-docs-close-mcp-only-auto-update-gaps.md
tags: [mcp, upgrade]
---

## Problem

`plugins/cortex-overnight/server.py:105` hardcodes the cortex-command CLI pin as a tuple literal: `CLI_PIN = ("v0.1.0", "1.0")`. The first element is the git tag the MCP server expects the installed CLI wheel to track; the second is the companion schema floor. Because the tag is wired in as a frozen literal, the pin is decoupled from any source of truth that advances when `main` advances. Once a newer tag lands on `origin/main` and someone bumps the plugin version without remembering to edit this tuple, the pin silently stays at the old tag — the MCP server keeps signaling "the v0.1.0 wheel is fine" even as the project moves forward, and the auto-update mechanism that the pin gates loses its anchor without any loud failure.

## Fix direction

Two viable shapes, either of which removes the silent-drift surface:

- **CI lint** — compare `CLI_PIN[0]` against the latest tag on `origin/main` and fail (or warn) when the literal is behind. Cheap to add, runs on every PR, surfaces drift the next time anyone touches the repo rather than the next time a user hits the auto-update path.
- **Auto-derive at build time** — populate `CLI_PIN` from `pyproject.toml`'s version field plus the current git tag during the plugin build/package step, so the tuple is never edited by hand and cannot drift from the tag it claims to track.

The lint is the smaller patch; the auto-derive removes the failure mode entirely. Refine should pick one.

## Origin

Filed as a #146 follow-up during refine of #210 (item 6 — "CLI_PIN drift lint"). Parent ticket explicitly flagged this as a candidate to break out into its own backlog item rather than fold into the docs/hygiene-scoped #210 work.

## Superseded by #213

Superseded by #213 (close-plugin-cli-auto-update-gaps): the CI lint at T16 realizes #212's lint goal, and the auto-release workflow at T13 closes the root cause by removing hand-edited CLI pin drift entirely.
