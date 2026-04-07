---
name: retro
description: Write a dated problem-only log for the current session. Accepts an optional context tag (e.g. `/retro lifecycle-work`). Use when user says "/retro", "write a retro", "session retrospective", or wants to log what went wrong in this session. Captures user corrections, mistakes made, things missed, and wrong approaches — each with its consequence. Does NOT capture what worked or accomplishments.
argument-hint: "[tag]"
inputs:
  - "tag: string (optional) — context label appended to the retro filename; sanitized to lowercase-kebab-case; max length 50 chars after sanitization"
outputs:
  - "retros/YYYY-MM-DD-HHmm.md or retros/YYYY-MM-DD-HHmm-<tag>.md — dated problem log"
  - "retro file contains markdown with Problems section and optional User-Taught Lessons section"
preconditions:
  - "Run from project root (skill resolves repo root via git rev-parse)"
  - "Write permission required for retros/ directory and .session-lessons.md read permission if it exists"
  - "System datetime available for YYYY-MM-DD HHmm timestamp"
---

# Retro

Tag: $ARGUMENTS (empty = no tag)

Write a session problem log to `retros/YYYY-MM-DD-HHmm.md` (or `retros/YYYY-MM-DD-HHmm-{{tag}}.md` when a `{{tag}}` is provided) using the local timestamp.

## Success Criteria

A successful retro execution meets ALL of the following:

- ✓ Retro file is created at the correct path: `$REPO_ROOT/retros/YYYY-MM-DD-HHmm.md` or `$REPO_ROOT/retros/YYYY-MM-DD-HHmm-<tag>.md`
- ✓ File contains a `# Session Retro: YYYY-MM-DD HH:mm` header with correct timestamp
- ✓ File contains a `## Problems` section with 0 or more problem entries (each in format: `**Problem**: <description>. **Consequence**: <impact>.`) or the exact text `No problems recorded.`
- ✓ If `.session-lessons.md` existed, a `## User-Taught Lessons` section is present with its content; otherwise this section is omitted
- ✓ `.session-lessons.md` is deleted after successful retro write
- ✓ If retro is unprocessed and count ≥ 10, evolve nudge message is appended to response (unless `CLAUDE_AUTOMATED_SESSION=1`)
- ✓ File permissions allow future reads by the same user/process

## Input Validation

The optional `tag` argument must be validated before use:

- **Non-empty after sanitization**: If tag is provided but becomes empty after sanitization (e.g. `"/retro ---"`), treat as if no tag was provided
- **Character set**: Only `[a-z0-9-]` allowed after sanitization. Reject or strip disallowed characters (including spaces, underscores, dots, slashes, etc.)
- **Length limit**: After sanitization, tag must not exceed 50 characters. If longer, truncate or reject with error message
- **Hyphens**: Collapse consecutive hyphens to single hyphen; trim leading/trailing hyphens
- **Examples of valid tags**: `lifecycle-work`, `bug-fix`, `feature-exploration`, `api-changes`
- **Examples of invalid/rejected tags**: `Lifecycle_Work` (has uppercase and underscore) → sanitizes to `lifecycle-work` (OK); `/retro !!!` → sanitizes to empty (use default filename)

## Output Format Examples

### Example 1: Session with problems, no tag, no lessons

**Input**: `/retro` (invoked after a session with user corrections)

**Output filename**: `retros/2026-03-05-1430.md`

**Output content**:
```markdown
# Session Retro: 2026-03-05 14:30

## Problems

**Problem**: Misunderstood requirement for API pagination — assumed limit parameter was max items returned, but it was page number. **Consequence**: Built wrong endpoint signature; required rewrite.

**Problem**: Forgot to check if database migration was needed before running integration tests. **Consequence**: Tests failed with schema mismatch; lost 20 minutes debugging.

**Problem**: Switched implementation approach mid-task without documenting the prior attempt. **Consequence**: Cannot learn from why the first approach failed.
```

### Example 2: Session with no problems, with tag, with lessons

**Input**: `/retro feature-auth` (invoked after a clean session that included user-taught lessons)

**Output filename**: `retros/2026-03-05-1515-feature-auth.md`

**Output content**:
```markdown
# Session Retro: 2026-03-05 15:15

## Problems

No problems recorded.

```

## What to capture

Problems only — no "what worked", no prescriptions, no positive framing:

- **User corrections**: moments the user had to redirect or correct an approach
- **Mistakes**: wrong decisions or incorrect implementations during the session
- **Things missed**: requirements, edge cases, or constraints overlooked
- **Wrong approaches**: paths that had to be abandoned mid-implementation

Each entry format: `**Problem**: <what went wrong>. **Consequence**: <what happened because of it>.`

If nothing went wrong and no corrections were made: write `No problems recorded.`

## Steps

1. Resolve the main repo root: run `git rev-parse --git-common-dir` in the current directory. If the result is non-empty and not absolute (does not start with `/`), prepend the current directory path to make it absolute. Set `REPO_ROOT` to the `dirname` of that result. If git is unavailable or returns empty, fall back to the current working directory. Use `REPO_ROOT` as the base path for all subsequent file operations in this skill (retros directory, retro file path, `.session-lessons.md` read, and any written files).
2. Check for `$REPO_ROOT/retros/.session-lessons.md` — read it if it exists
3. Reflect on this session: scan for user corrections, mistakes, missed items, wrong approaches
4. Create `$REPO_ROOT/retros/` if it does not exist
5. Determine the filename:
   - If a tag argument was provided (any text after `/retro` on the command line), sanitize it:
     - Lowercase the entire string
     - Replace spaces with hyphens
     - Strip any character outside `[a-z0-9-]`
     - Collapse consecutive hyphens into a single hyphen
     - Trim leading and trailing hyphens
   - If the sanitized result is non-empty, use `$REPO_ROOT/retros/YYYY-MM-DD-HHmm-<tag>.md` (e.g. `/retro lifecycle-work` → `$REPO_ROOT/retros/2026-02-26-1430-lifecycle-work.md`)
   - If no tag was provided, or the sanitized result is empty, use `$REPO_ROOT/retros/YYYY-MM-DD-HHmm.md` (e.g. `$REPO_ROOT/retros/2026-02-26-1430.md`)
6. Write the retro file at the filename determined in step 5
7. Delete `$REPO_ROOT/retros/.session-lessons.md` if it existed
8. Evolve nudge (skip entirely if `CLAUDE_AUTOMATED_SESSION` is set):
   - Run `[ "${CLAUDE_AUTOMATED_SESSION:-0}" = "1" ]` — if this exits 0 (i.e. the var is set to "1"), skip the rest of this step.
   - Determine `last_processed`: if `$REPO_ROOT/retros/.evolve-state.json` exists, extract the value of the `last_processed` key from it (plain string, no JSON library required — a grep/sed on `"last_processed"` is sufficient); otherwise `last_processed` is empty.
   - Count unprocessed retros: list all `.md` files in `$REPO_ROOT/retros/` whose basenames do not start with `.` (i.e. exclude dot-files). If `last_processed` is non-empty, keep only those whose basename is lexicographically greater than `last_processed`. The resulting count is the number of unprocessed retros.
   - If count ≥ 10, append to the response: `"$count retros unprocessed — consider running /evolve."` (substituting the actual count). If count < 10, output nothing.

## Error Handling

The skill must handle the following failure modes gracefully:

### Failure: Git repo root cannot be determined

**Detection**: `git rev-parse --git-common-dir` fails, returns empty, or is not in path

**Action**:
- Fall back to current working directory as `REPO_ROOT`
- Log message to user: `"Git repository not found; using current directory for retro storage."`
- Continue with retro creation at `./retros/YYYY-MM-DD-HHmm.md`
- **Success criterion**: Retro file is still written, user is informed of fallback

### Failure: retros/ directory does not exist

**Detection**: `test -d $REPO_ROOT/retros` returns false

**Action**:
- Create directory: `mkdir -p $REPO_ROOT/retros`
- If mkdir fails (e.g., permission denied), stop and output: `"Error: Cannot create retros/ directory at $REPO_ROOT/retros. Check permissions."`
- **Success criterion**: Either retros/ is created or user receives clear error

### Failure: Cannot write retro file

**Detection**: File write operation fails (permission denied, disk full, path too long, etc.)

**Action**:
- Output error message: `"Error: Cannot write retro to $RETRO_PATH. Details: [system error message]. Retro was not saved."`
- Do NOT delete `.session-lessons.md` (preserve it for next attempt)
- Do NOT proceed to evolve nudge step
- Exit with failure status
- **Success criterion**: File write failure is reported clearly, no silent data loss

### Failure: Invalid tag argument (exceeds length or becomes empty after sanitization)

**Detection**: Tag length > 50 chars after sanitization, or tag becomes empty after sanitization

**Action**:
- If tag becomes empty: silently use default filename without tag (no error; this is acceptable)
- If tag exceeds 50 chars: either truncate to 50 chars OR output warning `"Tag too long (>50 chars); using truncated version: <truncated>"` and continue
- **Success criterion**: Retro file is created with valid filename, no corruption

### Failure: .session-lessons.md exists but cannot be read

**Detection**: File is readable but read fails (permissions, encoding, corruption), or file exists but is not readable

**Action**:
- Output warning: `"Warning: Could not read .session-lessons.md; skipping User-Taught Lessons section."`
- Continue retro creation without the lessons section
- Attempt to delete the file anyway (if deletion fails, output warning but do not stop)
- **Success criterion**: Retro is still written, lessons are skipped gracefully

### Failure: Cannot delete .session-lessons.md

**Detection**: unlink/rm fails on `.session-lessons.md` (e.g., permission denied)

**Action**:
- Output warning: `"Warning: Could not delete .session-lessons.md; you may want to clean it up manually."`
- Continue; do not stop execution
- **Success criterion**: Retro is still written, user is informed of cleanup issue

### Failure: Timestamp generation fails (system clock unavailable)

**Detection**: `date +%Y-%m-%d-%H%M` fails or returns empty

**Action**:
- Output error: `"Error: Cannot determine system timestamp. Retro file cannot be created."`
- Exit with failure status
- **Success criterion**: User is informed of the root cause

## File format

```
# Session Retro: YYYY-MM-DD HH:mm

## Problems

**Problem**: <description>. **Consequence**: <what happened because of it>.

[one entry per problem]
```

Do NOT include "Key Accomplishments", "What Worked", "Next Time", "Patterns to Carry Forward", or any prescriptive/positive sections.
