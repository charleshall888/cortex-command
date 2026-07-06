---
# type: other            # web-app | cli-tool | library | game | other
# test-command:           # e.g., npm test, pytest, go test ./...
# demo-command:           # e.g., godot res://main.tscn, uv run fastapi run src/main.py
# demo-commands:
#   - label: "Godot gameplay"
#     command: "godot res://main.tscn"
#   - label: "FastAPI dashboard"
#     command: "uv run fastapi run src/main.py"
# default-tier:           # simple | complex (override auto-assessment)
# default-criticality:    # low | medium | high | critical
skip-specify: false
skip-review: false
commit-artifacts: true
# Gate for the overnight critical-tier dual-plan synthesizer dispatch path.
# Default false (fail-closed) until the operator validates the path and flips to true.
synthesizer_overnight_enabled: false
# Branch-selection default for the lifecycle implement phase. Default prompt =
# the picker fires every time, byte-identical to leaving this field absent.
# Values + carve-outs: see docs/overnight-operations.md (branch-mode note).
branch-mode: prompt
# Which ticketing backend cortex uses. Default cortex-backlog = the local
# cortex/backlog/ files; behavior is byte-identical to today when this block
# is absent or set to cortex-backlog.
backlog:
  backend: cortex-backlog
  # backend: github-issues   # external tracker (best-effort, see below)
  # backend: jira            # external tracker (best-effort, see below)
  # backend: none            # opt out of all cortex ticket management
  # Freeform prose hint the LLM reads to drive an EXTERNAL tracker best-effort.
  # External backends are best-effort now and harden in #318. Example:
  # instructions: "Use the `gh` CLI; label cortex issues `cortex`; epics are milestones"
---

# Lifecycle Configuration

Project-specific overrides for the lifecycle skill. Copy to `cortex/lifecycle.config.md` at your project root and customize.

## Review Criteria

Project-specific review criteria beyond default spec compliance + code quality, e.g.:
<!-- - Verify all new routes have authentication middleware -->
<!-- - Check that database migrations are reversible -->
