# Plan: apply-confirmed-safe-permission-tightening

## Overview

Sequential edits to `claude/settings.json`: first remove 14 entries from the allow list (R1 + R2 removal + R5), then add entries to ask/deny and remove a top-level setting (R2 addition + R3 + R4), then validate. Backlog 047 archival runs independently.

## Tasks

### Task 1: Remove entries from allow list

- **Files**: `claude/settings.json`
- **What**: Remove 14 entries from `permissions.allow`: `Read(~/**)`, `Bash(* --version)`, `Bash(* --help *)`, `Bash(open -na *)`, `Bash(pbcopy *)`, `Bash(pbcopy)`, `Bash(env *)`, `Bash(env)`, `Bash(printenv *)`, `Bash(printenv)`, `Bash(git restore *)`, `mcp__perplexity__*`, `mcp__jetbrains__*`, `mcp__atlassian__*`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `claude/settings.json` `permissions.allow` array (lines 12-148). Entries are at: line 16 (`Read(~/**)`), line 96 (`Bash(* --version)`), line 97 (`Bash(* --help *)`), line 142 (`Bash(open -na *)`), line 143 (`Bash(pbcopy *)`), line 144 (`Bash(pbcopy)`), line 92 (`Bash(env *)`), line 93 (`Bash(env)`), line 94 (`Bash(printenv *)`), line 95 (`Bash(printenv)`), line 110 (`Bash(git restore *)`), lines 145-147 (MCP entries — last three items in the array). After removing MCP entries, the new last item will be `Bash(tmux *)` (currently line 141) — ensure no trailing comma after it. Check for duplicate entries before removing.
- **Verification**: `python3 -c "import json; d=json.load(open('claude/settings.json')); a=d['permissions']['allow']; removed=['Read(~/**)', 'Bash(* --version)', 'Bash(* --help *)', 'Bash(open -na *)', 'Bash(pbcopy *)', 'Bash(pbcopy)', 'Bash(env *)', 'Bash(env)', 'Bash(printenv *)', 'Bash(printenv)', 'Bash(git restore *)', 'mcp__perplexity__*', 'mcp__jetbrains__*', 'mcp__atlassian__*']; assert all(e not in a for e in removed), f'Still present: {[e for e in removed if e in a]}'"` — pass if exit 0.
- **Status**: [x] done

### Task 2: Add ask/deny entries and remove setting

- **Files**: `claude/settings.json`
- **What**: Add `Bash(git restore *)` to `permissions.ask`. Add 9 entries to `permissions.deny`. Remove `skipDangerousModePermissionPrompt` top-level key.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: `claude/settings.json` structure post-Task 1. Find `permissions.ask` by searching for `"ask": []` — it is the empty array in the `permissions` object. Find `permissions.deny` by searching for the `"deny": [` key — add new entries after the existing `WebFetch(domain:127.0.0.1)` entry (maintaining grouping: credential reads together, then loopback deny, then command denials). `skipDangerousModePermissionPrompt` is a top-level key (the last key in the JSON object) — search for it by name. After removal, `effortLevel` becomes the last key; ensure no trailing comma. New deny entries to add: `Read(~/.config/gh/hosts.yml)`, `Read(**/*.p12)`, `WebFetch(domain:0.0.0.0)`, `Bash(crontab *)`, `Bash(eval *)`, `Bash(xargs *rm*)`, `Bash(find * -delete*)`, `Bash(find * -exec rm*)`, `Bash(find * -exec shred*)`.
- **Verification**: `python3 -c "import json; d=json.load(open('claude/settings.json')); assert 'Bash(git restore *)' in d['permissions']['ask']; deny=d['permissions']['deny']; expected=['Read(~/.config/gh/hosts.yml)','Read(**/*.p12)','WebFetch(domain:0.0.0.0)','Bash(crontab *)','Bash(eval *)','Bash(xargs *rm*)','Bash(find * -delete*)','Bash(find * -exec rm*)','Bash(find * -exec shred*)']; assert all(e in deny for e in expected), f'Missing: {[e for e in expected if e not in deny]}'; assert 'skipDangerousModePermissionPrompt' not in d"` — pass if exit 0.
- **Status**: [x] complete

### Task 3: Validate all changes

- **Files**: `claude/settings.json`
- **What**: Run JSON validation and all acceptance criteria from the spec to confirm correctness of Tasks 1-2.
- **Depends on**: [1, 2]
- **Complexity**: trivial
- **Context**: Run each acceptance criterion from the spec sequentially. No file modifications — read-only validation.
- **Verification**: `python3 -c "import json; d=json.load(open('claude/settings.json')); a=d['permissions']['allow']; k=d['permissions']['ask']; y=d['permissions']['deny']; gone=['Read(~/**)', 'Bash(* --version)', 'Bash(* --help *)', 'Bash(open -na *)', 'Bash(pbcopy *)', 'Bash(pbcopy)', 'Bash(env *)', 'Bash(env)', 'Bash(printenv *)', 'Bash(printenv)', 'Bash(git restore *)', 'mcp__perplexity__*', 'mcp__jetbrains__*', 'mcp__atlassian__*']; assert all(e not in a for e in gone), f'R1/R5 fail: {[e for e in gone if e in a]}'; assert 'Bash(git restore *)' in k, 'R2 fail: git restore not in ask'; added=['Read(~/.config/gh/hosts.yml)','Read(**/*.p12)','WebFetch(domain:0.0.0.0)','Bash(crontab *)','Bash(eval *)','Bash(xargs *rm*)','Bash(find * -delete*)','Bash(find * -exec rm*)','Bash(find * -exec shred*)']; assert all(e in y for e in added), f'R4 fail: {[e for e in added if e not in y]}'; assert 'skipDangerousModePermissionPrompt' not in d, 'R3 fail'"` — pass if exit 0.
- **Status**: [x] complete

### Task 4: Archive backlog 047

- **Files**: `backlog/047-investigate-gaps-in-settingsjson-deny-list.md`
- **What**: Mark backlog 047 as complete with a note that it was subsumed by #056.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Run `update-item 047-investigate-gaps-in-settingsjson-deny-list status=complete`. The `update-item` CLI tool updates YAML frontmatter fields in backlog files. After updating status, add a note to the body indicating subsumption: append a line like `> Subsumed by #056 (apply-confirmed-safe-permission-tightening).` after the existing body content.
- **Verification**: `python3 -c "import yaml; f=open('backlog/047-investigate-gaps-in-settingsjson-deny-list.md').read(); fm=f.split('---')[1]; d=yaml.safe_load(fm); assert d['status']=='complete'"` — pass if exit 0.
- **Status**: [x] complete

## Verification Strategy

After all tasks complete, run the full acceptance suite from Task 3 as an end-to-end check. Additionally verify `just setup` still works by running `just check-symlinks` (a non-destructive subset of setup that validates the symlink architecture without overwriting files).
