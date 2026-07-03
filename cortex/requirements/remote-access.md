# Requirements: remote-access

> Last gathered: 2026-04-03

**Parent doc**: [requirements/project.md](project.md)

## Overview

The remote-access area covers the capabilities that allow development work to continue from a remote location — specifically, persistent terminal sessions that survive network interruptions and remote session reattachment. The current implementation uses tmux for session persistence, but the requirement is defined at the capability level: the specific tool providing persistence is subject to change.

## Functional Requirements

### Session Persistence

- **Description**: Terminal sessions hosting Claude Code must persist independently of the client connection, surviving network interruptions, terminal closures, and device switches.
- **Acceptance criteria**:
  - A Claude Code session can be detached from its client window without interrupting the active conversation
  - The session can be reattached from a different terminal window or device
  - Session identity (conversation history, context) is preserved across detach/reattach cycles
  - Sessions can be enumerated (list available sessions by name or ID)
  - Sessions are addressable by explicit name or auto-assigned numeric ID
- **Priority**: must-have

### Remote Session Reattachment

- **Description**: A developer working remotely (via Tailscale mesh VPN + mosh) can reattach to a running Claude Code session from a mobile device or remote machine.
- **Acceptance criteria**:
  - mosh connection survives IP address changes and roaming between networks
  - After reconnect, the persistent session state is unchanged
  - The Tailscale VPN provides the secure channel; no port forwarding required
- **Priority**: should-have

## Non-Functional Requirements

- **Failure transparency**: Session management failures are silent by default; no mechanism currently surfaces failures to a log. This is acceptable for personal use.
- **Platform**: macOS is the primary and only supported platform for session persistence (Ghostty dependency). Linux/Windows are not supported.

## Architectural Constraints

- Platform/terminal constraint: see Non-Functional Requirements → Platform (macOS + Ghostty dependency).

## Dependencies

- **Session persistence**: tmux; Ghostty terminal — see Overview for the tool-agnostic framing and Non-Functional Requirements → Platform for the macOS/Ghostty constraint
- **Remote connection**: Tailscale (mesh VPN), mosh (resilient mobile shell)
- **Local notifications**: `terminal-notifier`, Ghostty (click-to-activate) — see `cortex/requirements/observability.md` (Notifications) for the canonical listing

## Edge Cases

- **Required tool missing** (Ghostty, Tailscale, or mosh): the corresponding capability — session persistence or remote connection — fails at that layer; per Non-Functional Requirements → Failure transparency, this is not guaranteed to surface an error message.

## Open Questions

- The tool currently providing session persistence (tmux skill) is under review — see Overview for the capability-level framing that must be preserved regardless of which tool provides it.
