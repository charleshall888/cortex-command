<!-- Generic rules: safe to inject globally for any Claude Code user, regardless of cortex-command install state -->

## Git Commit Format

- For single-line commits: `git commit -m "Subject line here"`
- For multi-line commits, use multiple `-m` flags -- git inserts a blank line between each:
  ```
  git commit -m "Subject line" -m "- Bullet one
  - Bullet two"
  ```
