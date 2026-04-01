---
type: other
test-command: just test
skip-specify: false
skip-review: false
commit-artifacts: true
---

# Lifecycle Configuration

Project-specific overrides for the lifecycle skill.

## Review Criteria

- Settings JSON files must remain valid JSON after any changes
- New hook/notification scripts must be executable (`chmod +x`)
- New config files must follow the symlink pattern (source in repo, symlinked to system location)
- New skills must have `name` and `description` frontmatter
