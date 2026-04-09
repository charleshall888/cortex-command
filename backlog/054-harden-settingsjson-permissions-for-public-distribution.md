---
schema_version: "1"
uuid: a3f1c8e2-7b4d-4e9a-b6c1-d2e3f4a5b6c7
title: "Harden settings.json permissions for public distribution"
status: backlog
priority: high
type: epic
tags: [permissions-audit, security, shareability]
created: 2026-04-09
updated: 2026-04-09
discovery_source: research/permissions-audit/research.md
---

# Harden settings.json permissions for public distribution

## Context

Full audit of `claude/settings.json` permissions surfaced structural security issues: overly broad `Read(~/**)`, interpreter escape hatches (`bash *`, `python3 *`), missing deny patterns, and exfiltration channels via sandbox-excluded commands (`git:*`, `gh:*`, `WebFetch`). The template is deployed as global user settings via `just setup`, affecting all Claude Code projects.

Framing decision: optimize for public safety. Conservative defaults in the shipped template; primary user adds power-user permissions to `settings.local.json`.

## Research

See `research/permissions-audit/research.md` for full findings, 8 decision records, execution context analysis, and critical review feedback.

## Children

- 055: Verify escape hatch bypass mechanism (spike)
- 056: Apply confirmed-safe permission tightening
- 057: Remove interpreter escape hatch commands
- 058: Close exfiltration channels in sandbox-excluded commands
