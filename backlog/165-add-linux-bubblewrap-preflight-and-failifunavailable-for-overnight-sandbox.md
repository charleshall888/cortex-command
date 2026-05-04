---
schema_version: "1"
uuid: 59de6f26-d6ad-4d2c-aceb-73d446bee723
title: "Add Linux bubblewrap preflight and failIfUnavailable for overnight sandbox"
status: ready
priority: low
type: feature
parent: 162
tags: [overnight-runner, sandbox, cross-platform, linux]
areas: [overnight-runner]
created: 2026-05-04
updated: 2026-05-04
lifecycle_slug: null
lifecycle_phase: null
session_id: null
blocks: []
blocked-by: [163]
discovery_source: research/sandbox-overnight-child-agents/research.md
---

# Add Linux bubblewrap preflight and failIfUnavailable for overnight sandbox

## Context from discovery

Per https://code.claude.com/docs/en/sandboxing, on Linux/WSL2 Claude Code uses bubblewrap (`bwrap`) + `socat` for sandbox enforcement. If these packages are missing, "Claude Code shows a warning and runs commands without sandboxing" — fails open silently. On macOS, Seatbelt is built-in and reliable.

After #163 lands, V1's per-spawn `sandbox.filesystem.denyWrite` enforcement on Linux silently no-ops if `bwrap` is missing — the entire V1 work becomes unprotected on Linux unless this ticket ships. Setting `sandbox.failIfUnavailable: true` (already proposed for V1's settings JSON) flips the silent fall-open to a hard error, but does not fire any earlier than spawn time; a runner-startup preflight catches the error at session-launch instead of mid-session.

## Findings from discovery

- `sandbox.failIfUnavailable: true` is documented (https://code.claude.com/docs/en/sandboxing): "To make this a hard failure instead, set `sandbox.failIfUnavailable` to `true`. This is intended for managed deployments that require sandboxing as a security gate."
- Linux install line: `sudo apt-get install bubblewrap socat` (Ubuntu/Debian) or `sudo dnf install bubblewrap socat` (Fedora).
- Windows is not supported; WSL2 works via bubblewrap; WSL1 errors with `Sandboxing requires WSL2`.

## Value

V1 (#163) silently fails open on Linux/WSL2 if `bwrap`/`socat` are missing — without this ticket, V1 provides macOS-only enforcement. Citation: `docs/setup.md` (no Linux sandbox prereq currently documented), corroborated by Anthropic sandbox docs documenting the silent-fail-open behavior.

## Acceptance criteria (high-level)

- The runner adds a startup preflight check that detects Linux/WSL2 platform and verifies `bwrap` and `socat` are on PATH. Missing dependencies produce a clear error (or warning, per spec-phase decision) before any overnight session launches.
- `sandbox.failIfUnavailable: true` is included in the per-spawn settings JSON written by #163.
- `docs/setup.md` is updated with a Linux/WSL2 prerequisites section listing the `apt-get`/`dnf` install commands.

## Research context

Full research at `research/sandbox-overnight-child-agents/research.md`. Particularly relevant: RQ5 (cross-platform), DR-4 (cross-platform handling).
