---
schema_version: "1"
uuid: 60388986-7df9-4e38-b274-b4736d4a906b
title: "Create remote/SETUP.md for remote access setup"
status: backlog
priority: low
type: chore
tags: [docs, remote-access]
areas: [docs]
created: 2026-04-03
updated: 2026-04-03
blocks: []
blocked-by: []
---

# Create remote/SETUP.md for remote access setup

## Problem

`docs/setup.md` references `remote/SETUP.md` in three places (lines 166, 284, 286), but the file and its parent directory have never been created. The Remote Access section of `docs/setup.md` is essentially empty — it just says "full step-by-step instructions are in `remote/SETUP.md`" with nothing to fall back on. Anyone following the setup guide hits a broken link.

## Scope

- Create `remote/SETUP.md` with step-by-step instructions for: Tailscale install and mesh VPN config, mosh install, ntfy.sh topic setup, `NTFY_TOPIC` env var configuration, and testing that push notifications arrive on Android
- Include hostname customization callout (the existing `docs/setup.md` callout refers to a specific Tailscale machine name that needs to be replaced)
- Update `docs/setup.md` line 166 to fix or remove the table entry referencing `remote/SETUP.md` if it becomes a standalone file rather than a customization target
- No behavioral changes — documentation only
