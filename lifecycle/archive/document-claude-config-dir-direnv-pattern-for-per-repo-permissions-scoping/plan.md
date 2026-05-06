# Plan: document-claude-config-dir-direnv-pattern-for-per-repo-permissions-scoping

## Overview

Add a single top-level "Per-repo permission scoping" section to `docs/setup.md` (30–80 non-blank lines) documenting the `CLAUDE_CONFIG_DIR` + direnv pattern with a WARM upstream preamble, a `cp -R` symlink-trap warning, and an honest limitations list. Pre-flight gate re-audits DR-7 against structured `gh` JSON fields only and halts deterministically if upstream state has moved.

## Tasks

### Task 1: DR-7 upstream audit re-check (pre-flight gate)
- **Files**: none (read-only GitHub queries + one `plan_halt` event to `lifecycle/.../events.log` on halt)
- **What**: Re-run the DR-7 upstream audit against `anthropics/claude-code#12962` and `#26489` using only **structured** `gh issue view --json` fields. On proceed, continue to Task 2. On halt, append a `plan_halt` event to `events.log`, do NOT modify `docs/setup.md`, and stop the plan — the user will re-invoke `/lifecycle` after deciding how to react (either descope this ticket if upstream landed a fix, or re-run if they want to ship docs anyway).
- **Depends on**: none
- **Complexity**: simple
- **Context**: Run both commands:
  ```bash
  gh issue view 12962 --repo anthropics/claude-code --json state,assignees,labels
  gh issue view 26489 --repo anthropics/claude-code --json state,assignees,labels
  ```
  **Deterministic halt criteria** — halt if ANY of these is true for EITHER issue:
  1. `.state` is not `OPEN`.
  2. `.assignees` is a non-empty array.
  3. `.labels[].name` contains any label matching the case-insensitive regex `roadmap|planned|in-progress|area/config|area/settings`.

  If none fire on either issue, the audit is still WARM and Task 2 proceeds.

  **Intentional narrowing**: the original draft included "linked closing PR" and "sustained Anthropic comment activity in past 30 days" as halt triggers. Both rejected because (a) linked PRs are not in the `--json state,assignees,labels` structured output and comment-body parsing is fragile, (b) "sustained activity" requires identifying Anthropic employees from `author.login` with no ground-truth list. The narrowed criteria are conservative — they will miss some genuine upstream motion (e.g., an Anthropic employee commenting without assigning themselves) but are unambiguous. Cost of the false-negative is one extra day of stale WARM framing, which is tolerable.

  **Halt protocol** (if the plan halts):
  1. Append this event to `lifecycle/archive/document-claude-config-dir-direnv-pattern-for-per-repo-permissions-scoping/events.log`:
     ```
     - ts: <ISO 8601>
       event: plan_halt
       feature: document-claude-config-dir-direnv-pattern-for-per-repo-permissions-scoping
       phase: implement
       task: 1
       reason: "DR-7 audit re-check failed deterministic WARM criteria"
       issue_12962_state: <state>
       issue_12962_assignees: <assignees JSON or []>
       issue_12962_labels: <labels JSON or []>
       issue_26489_state: <state>
       issue_26489_assignees: <assignees JSON or []>
       issue_26489_labels: <labels JSON or []>
       status: halt
     ```
  2. Leave Task 1's `Status: [ ] pending` unchanged — do NOT mark complete or cancelled. Pending + `plan_halt` event = "awaiting user decision."
  3. Do NOT modify `docs/setup.md`. Do NOT run Task 2 or Task 3.
  4. Report to the user: summarize which halt criterion fired, quote the relevant `gh` JSON fields, note that re-invoking `/lifecycle 65` will re-run Task 1.

- **Verification**: Interactive/session-dependent — the task is a conditional branch on external GitHub state against structured JSON fields. On halt, verify with `grep -c 'event: plan_halt' lifecycle/archive/document-claude-config-dir-direnv-pattern-for-per-repo-permissions-scoping/events.log` = 1 and `git status docs/setup.md` clean. On proceed, `grep -c 'event: plan_halt' ...` = 0.
- **Status**: [x] complete

### Task 2: Add "Per-repo permission scoping" section to `docs/setup.md`
- **Files**: `docs/setup.md`
- **What**: Insert a new top-level `## Per-repo permission scoping` section between the existing `## Customization` section and the `## macOS Notifications` section. Use the Edit tool — do not rewrite the file. The section body must be 30–80 non-blank lines and must contain all the content elements listed below.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:

  **Insertion anchor**: locate the insertion point by searching for the literal strings `## Customization` and `## macOS Notifications` in `docs/setup.md`. Do NOT use line numbers — parallel worktrees or intermediate edits may have shifted line positions.

  **Content elements** (mandatory — see Verification for the binary checks):

  1. **Status preamble**: 2–3 sentences explaining this pattern is an interim pattern until one of two upstream issues lands. Link both issues: `https://github.com/anthropics/claude-code/issues/12962` and `https://github.com/anthropics/claude-code/issues/26489`.

  2. **How it works**: 2–4 sentences on `CLAUDE_CONFIG_DIR` — it points Claude Code at an alternate user-scope directory instead of `~/.claude`, read at launch time (so a relaunch is required to pick up a new value). The literal `CLAUDE_CONFIG_DIR` must appear at least 4 times across the section body.

  3. **direnv walkthrough**: step-by-step — create the shadow directory, write `.envrc`, `direnv allow`, relaunch Claude Code. Include a short `.envrc` code example with `export CLAUDE_CONFIG_DIR=...`. The literal `.envrc` must appear at least twice in the section body.

  4. **`cp -R` symlink-trap warning — must appear BEFORE the foot-guns list** (ordering enforced by verification):
     - State that on macOS, four files under `~/.claude/` are symlinks back into the cortex-command repo: `settings.json`, `statusline.sh`, `notify.sh`, and `CLAUDE.md`. Research §4.1 verified this empirically on this machine.
     - Explain that `cp -R` preserves symlinks by default on macOS, so `cp -R ~/.claude ~/.claude-shadow` shares those four files with the host. Mutating the shadow mutates the host.
     - Give the explicit fix: after `cp -R`, `rm` each of the four files (`settings.json`, `statusline.sh`, `notify.sh`, `CLAUDE.md`) in the shadow, then write fresh minimal copies or deliberately re-symlink them. All four filenames must appear literally in the section body (enforced).
     - **MUST NOT recommend `cp -RL` as the workaround.** Spec Technical Constraints forbid it ("creates a frozen snapshot which is the wrong default for an evolving cortex install"). The section body MUST NOT contain the literal string `cp -RL` (enforced by negative grep).

  5. **Cortex-command foot-guns — 5 items, framed as limitations**: bulleted or numbered list. Each foot-gun must (a) include its anchor keyword, (b) explain the failure mode, and (c) give a workaround. **The foot-guns MUST NOT be framed as automatic handling** — the section body MUST NOT contain `handles` within 80 characters of any foot-gun keyword (enforced). Phrases like "cortex-command handles this for you" are prohibited — they contradict spec Technical Constraints and directly cause the criticality=high "silent infrastructure drift" failure mode this ticket documents.
     - **`/setup-merge` hardcodes `~/.claude`** — don't run from a shadowed shell or it silently bypasses the shadow.
     - **`just setup` hardcodes `~/.claude`** — re-run from the shadow shell when the host updates, or use `cp -R --update`.
     - **Notify hook literal path** — `claude/settings.json` hook commands reference `~/.claude/notify.sh` as a string. Under a shadow, notifications fire from the host path or fail. Workaround: keep a working host install alongside the shadow.
     - **Evolve / auto-memory / audit-doc / count-tokens walk from host** — these tools fall back to `~/.claude`. Auto-memory under a shadow writes to the host scope.
     - **Scope-active confusion / concurrent sessions** — users cannot tell from inside a session which scope is active (upstream `/context` bug). Workaround: `echo $CLAUDE_CONFIG_DIR` before launching.

  6. **Upstream partial-support bugs**: short sub-list naming `#36172` literally (enforced — the spec allows a disjunction with `skill.*lookup|partially honored` but the plan tightens to the literal issue number so users can actually look it up). Briefly explain that the skills lookup under `$CLAUDE_CONFIG_DIR/skills/` is not reliably honored in current Claude Code — this undermines the "swap the entire user scope" mental model. Also mention `#38641` (`/context` display), `#42217` (MCP config), `#34800` (IDE lock) for context.

  7. **Background link**: one line referencing `research/user-configurable-setup/research.md` as the full failure-mode inventory.

  **Length discipline**: section body between the new heading and the next top-level `## ` heading must be 30–80 **non-blank** lines inclusive. Non-blank = at least one non-whitespace character on the line.
- **Verification**: Run this block — extracts the section body once and runs all checks against the extracted body, so pre-existing content elsewhere in `docs/setup.md` cannot mask omissions.

  Run as a single `bash` invocation (heredoc). In a sandboxed environment the temp file must live under `$TMPDIR/claude/`, not `/tmp/`, to satisfy sandbox write rules:
  ```bash
  bash <<'VERIFY'
  set -e
  BODY="$TMPDIR/claude/section-body-$$"
  mkdir -p "$(dirname "$BODY")"
  awk '/^## .*[Pp]er-repo permission/{flag=1; next} flag && /^## /{exit} flag' docs/setup.md > "$BODY"
  test -s "$BODY" && echo "section exists"
  len=$(grep -c '[^[:space:]]' "$BODY")
  test "$len" -ge 30 -a "$len" -le 80 && echo "length ok: $len non-blank lines"
  grep -q 'issues/12962' "$BODY" && echo "12962 ok"
  grep -q 'issues/26489' "$BODY" && echo "26489 ok"
  test $(grep -c '\.envrc' "$BODY") -ge 2 && echo "envrc ok"
  test $(grep -c 'CLAUDE_CONFIG_DIR' "$BODY") -ge 4 && echo "var ok"
  test $(grep -cE 'cp -[rR]' "$BODY") -ge 1 && echo "cp ok"
  grep -q 'settings.json' "$BODY" && echo "settings.json ok"
  grep -q 'statusline.sh' "$BODY" && echo "statusline.sh ok"
  grep -q 'notify.sh' "$BODY" && echo "notify.sh ok"
  grep -q 'CLAUDE.md' "$BODY" && echo "CLAUDE.md ok"
  test $(grep -cE 'rm [^[:space:]]+' "$BODY") -ge 4 && echo "rm count ok"
  test $(grep -c 'symlink' "$BODY") -ge 2 && echo "symlink ok"
  # Negative checks use if-then form because bare `! grep` is parsed as history-expansion in some shells
  if grep -q 'cp -RL' "$BODY"; then echo "FAIL: cp -RL present"; exit 1; else echo "cp -RL absent ok"; fi
  if grep -E 'handles.{0,80}(setup-merge|just setup|notify|evolve|auto-memory|audit-doc|count-tokens|concurrent|shadow)' "$BODY" > /dev/null; then echo "FAIL: handles-lie forward"; exit 1; else echo "no-handles-lie ok"; fi
  if grep -E '(setup-merge|just setup|notify|evolve|auto-memory|audit-doc|count-tokens|concurrent|shadow).{0,80}handles' "$BODY" > /dev/null; then echo "FAIL: handles-lie reverse"; exit 1; else echo "no-handles-lie-reverse ok"; fi
  grep -qi 'setup-merge' "$BODY" && echo "setup-merge ok"
  grep -qi 'just setup' "$BODY" && echo "just setup ok"
  grep -qi 'notify' "$BODY" && echo "notify ok"
  grep -qiE 'evolve|auto-memory|audit-doc|count-tokens' "$BODY" && echo "tools ok"
  grep -qiE 'concurrent|multiple sessions|scope confusion|which scope' "$BODY" && echo "scope ok"
  sym_line=$(grep -n 'symlink' "$BODY" | head -1 | cut -d: -f1)
  sm_line=$(grep -in 'setup-merge' "$BODY" | head -1 | cut -d: -f1)
  test -n "$sym_line" -a -n "$sm_line" && test "$sym_line" -lt "$sm_line" && echo "ordering ok"
  grep -q '#36172' "$BODY" && echo "36172 ok"
  grep -q 'research/user-configurable-setup/research.md' "$BODY" && echo "research ok"
  test ! -f docs/per-repo-permissions.md && echo "no new file ok"
  rm -f "$BODY"
  echo "all checks passed"
  VERIFY
  ```
  Pass if `all checks passed` prints and the script did not exit early via `set -e` or an explicit `exit 1` from a negative check.
- **Status**: [x] complete

### Task 3: Commit the docs change
- **Files**: `docs/setup.md` (staged; no new files)
- **What**: Commit the single-file docs change using the `/commit` skill. Before invoking `/commit`, assert a clean-index precondition — only `docs/setup.md` may be staged. If other files are staged from prior session state, unstage them first.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**:

  **Clean-index precondition** (run before invoking `/commit`):
  ```bash
  # Unstage anything that is not docs/setup.md
  git diff --cached --name-only | while read f; do
    if [ "$f" != "docs/setup.md" ]; then
      git restore --staged "$f"
    fi
  done
  # Stage the docs change
  git add docs/setup.md
  # Verify exactly docs/setup.md is staged
  staged=$(git diff --cached --name-only)
  test "$staged" = "docs/setup.md"
  ```
  If the final `test` fails, do NOT invoke `/commit` — investigate why additional files re-appeared in the index and stop the task with a report.

  **Commit invocation**: invoke the `/commit` skill per global rules (never run `git commit` manually). Commit message: imperative, describe the *why* (per-repo permission scoping is unsupported by Claude Code's additive settings merge; this documents the workaround with foot-guns). Mention that infrastructure fixes are deliberately deferred (spec Non-Requirements). Subject max 72 chars.

  **Failure handling**: if `/commit` is rejected by the commit-message validation hook, read the hook output, fix the message, and retry. Hook rejection is a fix-and-retry condition per `skills/commit/SKILL.md`. Do not run `--no-verify` or `--no-gpg-sign`.
- **Verification**:
  ```bash
  # Exactly one commit was created touching only docs/setup.md
  files=$(git log -1 --name-only --pretty=format:)
  test "$(echo "$files" | grep -c .)" -eq 1 && test "$(echo "$files" | tr -d '[:space:]')" = "docs/setup.md" && echo "commit scope ok"
  ```
  Pass if `commit scope ok` prints. Fail if the commit touches anything other than `docs/setup.md` — rollback via `git reset --soft HEAD~1`, re-clean the index, and retry.
- **Status**: [x] complete

## Verification Strategy

End-to-end verification after all 3 tasks complete:

1. **Pre-flight gate honored**: Task 1 either proceeded (WARM confirmed against structured `gh` JSON fields) or halted with a `plan_halt` event logged and no docs modifications. Verify via `git status docs/setup.md` and the `plan_halt` event count in `events.log`.

2. **Section content and length**: re-run Task 2's combined verification block against the final state of `docs/setup.md`. All content presence checks pass, both negative checks pass, section length in [30, 80] non-blank lines.

3. **Scope invariants hold**: `git diff --name-only HEAD~1` shows exactly `docs/setup.md`. No new file at `docs/per-repo-permissions.md`. No edits to `README.md`, `CLAUDE.md`, `justfile`, `merge_settings.py`, `skills/evolve/SKILL.md`, `bin/audit-doc`, `bin/count-tokens`, or `claude/settings.json` — all explicitly scoped out per spec Non-Requirements.
