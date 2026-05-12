# Specification: Remove dangling remote/SETUP.md references

## Problem Statement

`docs/setup.md` references `remote/SETUP.md` in three places (lines 166, 284, 286), but the file and directory were never created in this repo. Remote access setup (Tailscale, mosh, ntfy installation and configuration) is machine-specific infrastructure that belongs in the machine-config repo, not cortex-command. Users following the setup guide encounter broken links.

## Requirements

1. **Remove customization table row**: Delete the `remote/SETUP.md` row from the "Customize for Your Machine" table at line 166. Acceptance: the table contains only `shell/zshrc` and `claude/settings.json` rows.

2. **Replace Remote Access section body**: Replace the content of the `## Remote Access (macOS + Android)` section (lines 282–286) with a brief note stating that remote access setup lives in the machine-config repo. Acceptance: section heading is retained, body is a single short note, no dangling links remain.

3. **Zero dangling references**: After edits, `grep -r 'remote/SETUP' docs/setup.md` returns no results. Acceptance: confirmed by grep.

## Non-Requirements

- Creating `remote/SETUP.md` in this repo (belongs in machine-config)
- Updating other files that mention the broken reference (backlog items, lifecycle artifacts, requirements docs — these are historical context documenting the problem, not user-facing links)
- Changing any remote-access behavior or integration (hooks, notifications, session management)

## Edge Cases

- **Users with bookmarks to the Remote Access section**: The `## Remote Access` heading is retained, so anchor links (`#remote-access-macos--android`) continue to work.

## Technical Constraints

- Retain `---` horizontal rule separators between sections (consistent with rest of file)
- Do not add a link to machine-config (it may be a private repo; the repo name is sufficient as a pointer)
