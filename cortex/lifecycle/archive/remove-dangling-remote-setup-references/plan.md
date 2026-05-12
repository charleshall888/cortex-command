# Plan: Remove dangling remote/SETUP.md references

## Overview

Remove the `remote/SETUP.md` table row and the entire Remote Access section from `docs/setup.md`. Remote access setup is machine-level infrastructure that doesn't belong in this public repo's docs.

## Tasks

### Task 1: Remove remote/SETUP.md row from customization table
- **Files**: `docs/setup.md`
- **What**: Delete the `| remote/SETUP.md | Replace the hostname examples... |` row from the "Customize for Your Machine" table at line 166.
- **Depends on**: none
- **Complexity**: trivial
- **Context**: The table at lines 162-166 has three rows. After this edit, only `shell/zshrc` and `claude/settings.json` rows remain.
- **Verification**: `grep -c 'remote/SETUP' docs/setup.md` — pass if count = 2 (the two remaining references in the Remote Access section, not yet removed)
- **Status**: [x] done

### Task 2: Remove entire Remote Access section
- **Files**: `docs/setup.md`
- **What**: Delete the `## Remote Access (macOS + Android)` section entirely — heading (line 282), body (lines 284-286), and the `---` separator before it (line 280). The section after it (`## OS Compatibility`) follows directly after the previous section's separator.
- **Depends on**: [1]
- **Complexity**: trivial
- **Context**: Lines 278-290: previous section content ends, `---` separator (280), blank line (281), `## Remote Access` heading (282), blank line (283), Customize blockquote (284), blank line (285), paragraph with broken link (286), blank line (287), `---` separator (288), blank line (289), `## OS Compatibility` (290). Remove lines 280-288 so the previous section's content flows directly into the `---` + `## OS Compatibility`.
- **Verification**: `grep -c 'remote/SETUP' docs/setup.md` — pass if count = 0
- **Status**: [x] done

## Verification Strategy

Run `grep -c 'remote/SETUP' docs/setup.md` — pass if count = 0. Confirm no orphaned separators or blank lines around where the section was removed.
