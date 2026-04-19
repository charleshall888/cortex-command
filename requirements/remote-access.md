# Requirements: remote-access

> Last gathered: 2026-04-03

**Parent doc**: [requirements/project.md](project.md)

## Overview

The remote-access area covers the capabilities that allow development work to continue from a remote location — specifically, persistent terminal sessions that survive network interruptions and remote session reattachment. The current implementation uses tmux for session persistence, but the requirement is defined at the capability level: the specific tool providing persistence is subject to change.

## Functional Requirements

### Session Persistence

- **Description**: Terminal sessions hosting Claude Code must persist independently of the client connection, surviving network interruptions, terminal closures, and device switches.
- **Inputs**: Active Claude Code session; developer initiates session move or reconnection
- **Outputs**: New terminal window with session running inside a persistent container; original session continues unaffected
- **Acceptance criteria**:
  - A Claude Code session can be detached from its client window without interrupting the active conversation
  - The session can be reattached from a different terminal window or device
  - Session identity (conversation history, context) is preserved across detach/reattach cycles
  - Sessions can be enumerated (list available sessions by name or ID)
  - Sessions are addressable by explicit name or auto-assigned numeric ID
- **Priority**: must-have

### Remote Session Reattachment

- **Description**: A developer working remotely (via Tailscale mesh VPN + mosh) can reattach to a running Claude Code session from a mobile device or remote machine.
- **Inputs**: Remote connection to the host machine (Tailscale + mosh); active persistent session
- **Outputs**: Mobile shell connected to the persistent session; full terminal state visible
- **Acceptance criteria**:
  - mosh connection survives IP address changes and roaming between networks
  - After reconnect, the persistent session state is unchanged
  - The Tailscale VPN provides the secure channel; no port forwarding required
- **Priority**: should-have

## Non-Functional Requirements

- **Failure transparency**: Session management failures are silent by default; no mechanism currently surfaces failures to a log. This is acceptable for personal use.
- **Timeout**: Session reattachment depends on network latency
- **Platform**: macOS is the primary and only supported platform for session persistence (Ghostty dependency). Linux/Windows are not supported.

## Architectural Constraints

- Session persistence depends on a macOS terminal that supports persistent container processes (currently Ghostty).

## Dependencies

- **Session persistence**: tmux (current implementation, subject to change); Ghostty terminal (macOS)
- **Remote connection**: Tailscale (mesh VPN), mosh (resilient mobile shell)
- **Local notifications**: `terminal-notifier` (macOS), Ghostty (for click-to-activate)

## Edge Cases

- **Ghostty not installed**: Session persistence mechanism fails at window creation; error message suggests installation
- **Tailscale/mosh not installed**: Remote connection fails at the client; Claude session on host continues unaffected

## Open Questions

- `docs/setup.md` references `remote/SETUP.md` (line 286) as "Full step-by-step instructions," but that file does not exist in the repository. Users following the setup guide encounter a broken link. This documentation gap should be addressed as a separate task.
- The tool currently providing session persistence (tmux skill) is under review. The requirements above describe the capability that must be preserved regardless of which tool provides it.
