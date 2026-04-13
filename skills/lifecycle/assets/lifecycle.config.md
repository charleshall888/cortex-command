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
---

# Lifecycle Configuration

Project-specific overrides for the lifecycle skill. Copy this file to your project root as `lifecycle.config.md` and customize.

## Review Criteria

Add project-specific review criteria beyond default spec compliance + code quality:
<!-- Example: -->
<!-- - Verify all new routes have authentication middleware -->
<!-- - Check that database migrations are reversible -->
