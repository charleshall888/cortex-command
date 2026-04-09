# Plan: Close exfiltration channels in sandbox-excluded commands

## Overview

Edit `claude/settings.json` to narrow the allow list for sandbox-excluded commands and add targeted deny rules. All changes are in a single file with two logical operations: (1) replace overly broad allow entries with specific read-only patterns, (2) add deny rules for exfiltration vectors.

## Tasks

### Task 1: Narrow the allow list
- **Files**: `claude/settings.json`
- **What**: Remove `WebFetch` from the allow array, replace `Bash(gh *)` with 7 read-only gh subcommand patterns, and replace `Bash(git remote *)` with 2 read-only git remote patterns.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Current `"WebFetch"` entry is at approximately line 15 in `permissions.allow`
  - Current `"Bash(gh *)"` entry is at approximately line 128 in `permissions.allow`
  - Current `"Bash(git remote *)"` entry is at approximately line 26 in `permissions.allow` — note `"Bash(git remote)"` (no wildcard, line 27) must be kept
  - Replacement gh patterns: `Bash(gh pr view *)`, `Bash(gh pr list *)`, `Bash(gh pr diff *)`, `Bash(gh pr checks *)`, `Bash(gh repo view *)`, `Bash(gh run list *)`, `Bash(gh run view *)`
  - Replacement git remote patterns: `Bash(git remote -v)`, `Bash(git remote get-url *)`
- **Verification**: `python3 -c "import json; d=json.load(open('claude/settings.json')); a=d['permissions']['allow']; gh=['Bash(gh pr view *)','Bash(gh pr list *)','Bash(gh pr diff *)','Bash(gh pr checks *)','Bash(gh repo view *)','Bash(gh run list *)','Bash(gh run view *)']; remote=['Bash(git remote -v)','Bash(git remote get-url *)']; checks=['WebFetch' not in a, 'Bash(gh *)' not in a, 'Bash(git remote *)' not in a, 'Bash(git remote)' in a]+[p in a for p in gh]+[p in a for p in remote]; print(all(checks), f'{sum(checks)}/{len(checks)}')"` — pass if output starts with `True`.
- **Status**: [ ] pending

### Task 2: Add deny rules for exfiltration vectors
- **Files**: `claude/settings.json`
- **What**: Add 9 deny rules to `permissions.deny`: gh gist create/edit, git remote add/set-url/remove, and git push inline URL patterns (4 variants covering both argument positions).
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Deny rules go in the `permissions.deny` array, after the existing entries
  - Group new entries logically: gh gist rules together, git remote rules together, git push URL rules together
  - Exact entries to add:
    - `Bash(gh gist create *)`
    - `Bash(gh gist edit *)`
    - `Bash(git remote add *)`
    - `Bash(git remote set-url *)`
    - `Bash(git remote remove *)`
    - `Bash(git push https://*)`
    - `Bash(git push http://*)`
    - `Bash(git push * https://*)`
    - `Bash(git push * http://*)`
  - Follow existing deny list conventions: strings in double quotes, comma-separated, grouped by tool (no trailing comma after the last entry in the array)
- **Verification**: `python3 -c "import json; d=json.load(open('claude/settings.json')); deny=d['permissions']['deny']; expected=['Bash(gh gist create *)','Bash(gh gist edit *)','Bash(git remote add *)','Bash(git remote set-url *)','Bash(git remote remove *)','Bash(git push https://*)','Bash(git push http://*)','Bash(git push * https://*)','Bash(git push * http://*)']; missing=[e for e in expected if e not in deny]; print(len(missing)==0, f'missing: {missing}' if missing else 'all present')"` — pass if output starts with `True`.
- **Status**: [ ] pending

### Task 3: Validate final settings.json
- **Files**: (none — read-only validation)
- **What**: Run all spec acceptance criteria to confirm the final file is valid JSON with all changes correctly applied. This task is read-only — if validation fails, report the failures for manual resolution.
- **Depends on**: [1, 2]
- **Complexity**: trivial
- **Context**:
  - Run `python3 -c "import json; json.load(open('claude/settings.json'))"` to verify valid JSON (exit 0 = pass)
  - Run each spec acceptance criterion from Requirements 1-6
  - Verify no unintended changes: `git diff claude/settings.json` should show only the expected modifications (allow removals/additions, deny additions)
- **Verification**: Run all 7 Verification Strategy commands below. Pass if all output `True` or exit 0.
- **Status**: [ ] pending

## Verification Strategy

After all tasks, run the full acceptance criteria suite from the spec:

1. `python3 -c "import json; d=json.load(open('claude/settings.json')); print('WebFetch' not in d['permissions']['allow'])"` = True
2. `python3 -c "import json; d=json.load(open('claude/settings.json')); a=d['permissions']['allow']; gh=['Bash(gh pr view *)','Bash(gh pr list *)','Bash(gh pr diff *)','Bash(gh pr checks *)','Bash(gh repo view *)','Bash(gh run list *)','Bash(gh run view *)']; print('Bash(gh *)' not in a and all(p in a for p in gh))"` = True
3. `python3 -c "import json; d=json.load(open('claude/settings.json')); d_list=d['permissions']['deny']; print('Bash(gh gist create *)' in d_list and 'Bash(gh gist edit *)' in d_list)"` = True
4. `python3 -c "import json; d=json.load(open('claude/settings.json')); a=d['permissions']['allow']; print('Bash(git remote *)' not in a and 'Bash(git remote -v)' in a and 'Bash(git remote get-url *)' in a)"` = True
5. `python3 -c "import json; d=json.load(open('claude/settings.json')); d_list=d['permissions']['deny']; print(all(x in d_list for x in ['Bash(git remote add *)', 'Bash(git remote set-url *)', 'Bash(git remote remove *)']))"` = True
6. `python3 -c "import json; d=json.load(open('claude/settings.json')); d_list=d['permissions']['deny']; print(all(x in d_list for x in ['Bash(git push https://*)', 'Bash(git push http://*)', 'Bash(git push * https://*)', 'Bash(git push * http://*)']))"` = True
7. `python3 -c "import json; json.load(open('claude/settings.json'))"` exits 0
