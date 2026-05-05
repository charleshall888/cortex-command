---
type: other
test-command: just test
skip-specify: false
skip-review: false
commit-artifacts: true
# Gate for the overnight critical-tier dual-plan synthesizer dispatch path.
# Default false (fail-closed) until the operator validates the path and flips to true.
synthesizer_overnight_enabled: false
demo-commands:
  - label: "Dashboard"
    command: "just dashboard"
---

# Lifecycle Configuration

Project-specific overrides for the lifecycle skill.

## Review Criteria

- Settings JSON files must remain valid JSON after any changes
- New hook/notification scripts must be executable (`chmod +x`)
- New config files ship via the relevant plugin tree (cortex-core, cortex-overnight) — never as host-level symlinks
- New skills must have `name` and `description` frontmatter
