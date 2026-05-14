---
name: commit
description: Create git commits with consistent, well-formatted messages. Use when user says "commit", "/cortex-core:commit", "make a commit", "commit these changes", or asks to save/checkpoint their work as a git commit.
---

# Commit

Create a single git commit from the current working tree changes.

## Workflow

1. Run `cortex-commit-preflight` to get status, working-tree diff, and last 10 commits as a single JSON document.
2. Stage relevant files with `git add` (specific files, not `-A`)
3. Compose the commit message following the format below
4. Run `git commit -m "..."` with the composed message

Do not push. Do not create branches. Do not output conversational text — only tool calls.

## Commit Message Format

```
<subject line>

<optional body>
```

**Subject line:**
- Imperative mood, start with capital letter ("Add", "Fix", "Remove")
- No trailing period
- Keep concise (~72 chars)
- Summarize the *why*, not the *what*

**Body (when changes need explanation):**
- Blank line after subject
- Wrap at 72 characters
- Use `- ` bullet points for multiple items
- Explain motivation, not mechanics

**Skip the body** for single-purpose, self-evident changes.

## Commit Command

```bash
git commit -m "Subject line here"
```

```bash
git commit -m "Subject line here" -m "- Body bullet one
- Body bullet two"
```

Never use HEREDOC (`<<EOF`) or command substitution (`$(cat ...)`) — these create temp files that fail in sandboxed environments. Never use `dangerouslyDisableSandbox: true` for `git commit`.

## Validation

A PreToolUse hook validates commit messages before execution. If your commit is rejected, read the reason and fix the message — do not bypass.

## Release-type markers

The auto-release workflow runs on every push to `main` and invokes `bin/cortex-auto-bump-version` to determine the next semver tag. The default is a **patch** bump. To override, include a positionally-anchored marker token in the commit message body:

- `[release-type: major]` — bump major version (breaking change).
- `[release-type: minor]` — bump minor version (new feature, backward-compatible).
- `[release-type: skip]` — suppress release for this push (no tag created).

**Positional anchor**: the marker MUST appear as the entire content of its own line, modulo surrounding whitespace. The auto-bump helper matches:

```
(?im)^\s*\[release-type:\s*(major|minor|skip)\s*\]\s*$
```

A marker embedded mid-line or inside prose is ignored. Place the marker on its own line in the body.

**Precedence** when multiple commits since the last tag carry markers: `skip` > `major` > `minor` > `patch`.

**`BREAKING:` fallback**: if no `[release-type: …]` marker is present anywhere in the commit range AND any commit body contains a standalone-line `BREAKING:` or `BREAKING CHANGE:` token (case-insensitive, matching `(?im)^\s*BREAKING(?:\s+CHANGE)?:`), the helper treats the range as a major-bump. This is defense-in-depth for schema-breaking commits authored without explicit markers — prefer the explicit marker; rely on `BREAKING:` only as a backstop.

**Pre-merge verification**: before merging a PR, run `bin/cortex-auto-bump-version --dry-run` locally against the PR branch to confirm the tag the auto-release workflow will produce. The flag performs the same parsing with no filesystem mutations and exits 0 even on `no-bump`.

### Examples

Major bump:

```
Migrate envelope schema to v2.0

The state file format is now incompatible with v1.x consumers.

[release-type: major]
```

Minor bump:

```
Add --dry-run flag to cortex-auto-bump-version

Read-only mode for pre-merge verification of the next tag.

[release-type: minor]
```

Skip release:

```
Fix typo in skills/commit/SKILL.md

[release-type: skip]
```
