---
name: commit
description: Create git commits with consistent, well-formatted messages. Use when user says "commit", "/commit", "make a commit", "commit these changes", or asks to save/checkpoint their work as a git commit.
---

# Commit

Create a single git commit from the current working tree changes.

## Workflow

1. Run `git status` and `git diff HEAD` in parallel to see all changes
2. Run `git log --oneline -10` to match the repo's existing message style
3. Stage relevant files with `git add` (specific files, not `-A`)
4. Compose the commit message following the format below
5. Run the signing check (required — see below)
6. Commit using the output of step 5

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

## Commit Command Format

### Step 5: Signing check

Run this command before every commit. It prints the `GNUPGHOME=` prefix to use, or nothing:

```bash
bash -c 'if [ -f "$TMPDIR/gnupghome/S.gpg-agent" ]; then echo "GNUPGHOME=$TMPDIR/gnupghome"; fi'
```

### Step 6: Commit

Prepend the step 5 output (if any) to `git commit`. Use the literal path printed — not a shell variable.

**If step 5 printed `GNUPGHOME=/tmp/claude/gnupghome`** (or similar path):

```bash
GNUPGHOME=/tmp/claude/gnupghome git commit -m "Subject line here"
```

```bash
GNUPGHOME=/tmp/claude/gnupghome git commit -m "Subject line here" -m "- Body bullet one
- Body bullet two"
```

**If step 5 printed nothing** (non-sandboxed session):

```bash
git commit -m "Subject line here"
```

Never use HEREDOC (`<<EOF`) or command substitution (`$(cat ...)`) — these create temp files that fail in sandboxed environments. Never use `dangerouslyDisableSandbox: true` for `git commit`.

## Validation

A PreToolUse hook validates commit messages before execution. If your commit is rejected, read the reason and fix the message — do not bypass.
