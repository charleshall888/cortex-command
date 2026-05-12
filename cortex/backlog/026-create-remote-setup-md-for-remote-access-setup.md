---
schema_version: "1"
uuid: 60388986-7df9-4e38-b274-b4736d4a906b
title: "Remove dangling remote/SETUP.md references from docs/setup.md"
status: complete
priority: low
type: chore
tags: [docs, remote-access, cleanup]
areas: [docs]
created: 2026-04-03
updated: 2026-04-06
blocks: []
blocked-by: []
session_id: null
lifecycle_phase: research
lifecycle_slug: remove-dangling-remote-setup-references
complexity: simple
criticality: low
spec: cortex/lifecycle/archive/remove-dangling-remote-setup-references/spec.md
---

# Remove dangling remote/SETUP.md references from docs/setup.md

## Problem

`docs/setup.md` references `remote/SETUP.md` in three places (lines 166, 284, 286), but the file was never created in this repo. Remote access setup (Tailscale, mosh, ntfy) is machine-specific infrastructure that belongs in machine-config, not cortex-command.

## Scope

- Remove all `remote/SETUP.md` references from `docs/setup.md`
- Clean up the Remote Access section (lines 282–286) — either remove it entirely or replace with a brief note that remote access config lives in machine-config
- Remove the `remote/SETUP.md` row from the customization table (line 166)
- No behavioral changes — documentation cleanup only
