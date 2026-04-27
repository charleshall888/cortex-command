---
type: other
test-command: just test
skip-specify: false
skip-review: false
commit-artifacts: true
demo-commands:
  - label: "Dashboard"
    command: "just dashboard"
---

# Lifecycle Configuration

Project-specific overrides for the lifecycle skill.

## Review Criteria

- Settings JSON files must remain valid JSON after any changes
- New hook/notification scripts must be executable (`chmod +x`)
- New config files ship via the relevant plugin tree (cortex-interactive, cortex-overnight-integration) — never as host-level symlinks
- New skills must have `name` and `description` frontmatter
