# Specification: Agent-driven demoability assessment and validation setup at morning review

> Background context: this ticket sits inside a larger discovery thread at [`research/morning-review-demo-setup/research.md`](../../research/morning-review-demo-setup/research.md). The discovery research evaluated multiple approaches to reducing morning-review demo-launch friction and concluded that morning-review is the only viable hook point. The research and adversarial passes for this lifecycle (`lifecycle/{this-feature}/research.md`) reframed the original ticket significantly: the "smart demoability assessment" framing has been dropped, and the feature is scoped down to a fire-and-forget worktree-creation step inside the morning-review walkthrough that prints commands for the user to run in their own shell. See research.md for the full reasoning.

## Problem Statement

When the overnight runner produces a session that includes interactively-validatable work (a Godot scene change, a FastAPI dashboard tweak, a gameplay system that "feels" different), the morning-review walkthrough has no on-ramp to seeing it actually run. The user either retypes a long `git worktree add` command from memory and looks up the launch command, or skips validation entirely and merges blind. This feature gives morning-review a single yes/no offer that prepares a fresh worktree from the overnight branch and displays the user-configured launch command, removing the friction without taking on any of the agent-process-management complexity that the original ticket framing implied.

## Requirements

> **Priority classification**: All requirements R1–R14 are **Must-have** for v1. The feature is intentionally scoped to the minimum surface that delivers value without taking on the security, lifecycle, or process-management complexity that the original ticket framing implied. Should-have / Could-have items are absent because every requirement here is load-bearing for either correctness (R1, R2, R7, R8), graceful degradation (R3, R4, R5), security (R10), the auto-advance contract (R9), the cleanup contract (R11, R12), the user-facing offer (R6), or the index of where the new behavior lives (R13, R14). Won't-have items are enumerated explicitly under Non-Requirements below.

> **Acceptance-criteria phrasing**: Most ACs use `grep -c "<literal phrase>"` checks against pinned phrases. This is intentional — the spec uses verifiable substrings as its mechanical contract. The implementer should use the pinned phrases verbatim in the skill text. If alternative wording is preferred during implementation, the spec AC must be updated in the same change set so the verification stays accurate. A few ACs are marked "Manual reviewer check" where mechanical greppability is impractical (e.g., counting characters within a section body extracted by heading boundaries) — these are explicitly annotated with rationale.

### R1 — `demo-command` field added to `lifecycle.config.md` template
Add an optional, commented-by-default `demo-command` field to `skills/lifecycle/assets/lifecycle.config.md`, placed alongside `test-command` (currently line 3). The field follows the existing schema-comment convention: `# demo-command:           # e.g., godot res://main.tscn, uv run fastapi run src/main.py`. The example text MUST use `godot res://main.tscn` (positional scene argument), NOT `godot --play res://main.tscn` — the `--play` flag is not a documented Godot 4 CLI option and the original ticket / discovery research example was incorrect.
**Acceptance**: `grep -c '^# demo-command:' skills/lifecycle/assets/lifecycle.config.md` = 1 AND `grep -c -- '--play' skills/lifecycle/assets/lifecycle.config.md` = 0.

### R2 — New `## Section 2a — Demo Setup` in walkthrough.md
Insert a new section heading `## Section 2a — Demo Setup` between the existing `## Section 2 — Completed Features` (currently ending at line 79) and `## Section 2b — Lifecycle Advancement` (currently starting at line 82). The section's first line must be a "Skip this section entirely if …" guard clause matching the established convention used by Sections 2b, 2c, and 6a.

The insertion is NOT purely additive — two adjacent clauses currently assume immediate adjacency between Section 2 and Section 2b and must be edited as part of the same change set:
- **walkthrough.md line 76** currently reads "Record verified/skipped status per feature, then proceed immediately to Section 2b. Verified/skipped statuses are for reporting context only — they do not gate lifecycle advancement." This must be updated to reference Section 2a as the next section, with the clarification that Section 2a is conditional and may be skipped (in which case Section 2b runs immediately).
- **walkthrough.md line 84** currently reads "Run immediately after the batch verification response. No additional user input is needed." This must be updated to reference Section 2a (which may have run between the batch verification and Section 2b) — for example: "Run immediately after Section 2a (or after the batch verification response if Section 2a was skipped)."

**Acceptance** (all four checks):
- `grep -c '^## Section 2a — Demo Setup$' skills/morning-review/references/walkthrough.md` = 1
- `grep -c 'proceed immediately to Section 2a' skills/morning-review/references/walkthrough.md` ≥ 1 (line 76 update)
- `grep -c 'Run immediately after Section 2a' skills/morning-review/references/walkthrough.md` ≥ 1 (line 84 update)
- **Manual reviewer check**: in the file, the line containing `## Section 2a` falls between the line containing `## Section 2 —` and the line containing `## Section 2b —`. (Mechanical: pipeline `awk '/^## Section 2 / {a=NR} /^## Section 2a / {b=NR} /^## Section 2b / {c=NR} END {exit !(a<b && b<c)}'` returns exit 0.)

### R3 — Section 2a guard: skip when `demo-command` is not configured
Section 2a must be skipped entirely (no offer presented, no worktree created, no output displayed beyond the section being absent from the walkthrough flow) when ANY of the following hold:
- `lifecycle.config.md` does not exist at the project root
- `lifecycle.config.md` exists but does not contain a non-commented `demo-command:` line
- `demo-command:` exists but its value is empty (whitespace-only)
- `demo-command:` value contains any byte with code < 0x20 except `\t` (control characters / ANSI escapes — see R10 and the security framing in TC9; values that contain control characters are treated as malformed and the section is skipped silently)

The parsing rules are pinned to avoid skill-prose ambiguity. The skill instructions in Section 2a must specify them in this exact form (paraphrasing acceptable, semantics MUST match):
1. Read the file. For each non-blank line, strip leading whitespace.
2. If the stripped line begins with `#`, ignore it (comment line).
3. If the stripped line begins with `demo-command:`, extract everything after the first `:` character. Strip leading and trailing whitespace from the extracted value.
4. Reject the value if it contains any control character (byte < 0x20 except `\t`). Treat as if the field were unset.
5. If no matching line was found, or the extracted value is empty, treat the field as unset.
6. Do NOT strip inline `#` comments from the value. Shell commands may legitimately contain `#`, and there is no shell-parser available at this layer to determine when `#` is a comment vs literal. The user is responsible for keeping `demo-command` values free of trailing comments.

**Parser implementation note** (for the implementer, NOT user-facing): the spec's example value `godot res://main.tscn` (R1) contains a `:` in the value itself. A naive `awk -F:` split breaks here — it would return `//` as the value. The implementer MUST use a parser form that splits on the FIRST colon only and keeps the rest verbatim. Acceptable forms include:
- `sed -n 's/^[[:space:]]*demo-command:[[:space:]]*//p'` (strips the field name + leading whitespace; what remains is the verbatim value)
- `awk -F': *' '{sub(/^[^:]+: */, ""); print}'` (manually trims the first field)
- Reading the line and using string manipulation that explicitly takes "everything after the first `:`"
- NOT acceptable: `awk -F: '{print $2}'` — this discards `://main.tscn`.

**Acceptance** (all six greps must pass for the parsing rules to be considered pinned, and the four guard conditions must each appear in the section text):
- `grep -c 'comment line' skills/morning-review/references/walkthrough.md` ≥ 1 (parsing rule 2 — comment lines are ignored)
- `grep -c 'after the first' skills/morning-review/references/walkthrough.md` ≥ 1 (parsing rule 3 — extract value after the first colon)
- `grep -c 'leading and trailing whitespace' skills/morning-review/references/walkthrough.md` ≥ 1 (parsing rule 3 — strip whitespace)
- `grep -c 'control character' skills/morning-review/references/walkthrough.md` ≥ 1 (parsing rule 4 — reject control characters)
- `grep -c 'treat the field as unset' skills/morning-review/references/walkthrough.md` ≥ 1 (parsing rule 5 — empty value treated as unset)
- `grep -c 'inline.*comments' skills/morning-review/references/walkthrough.md` ≥ 1 (parsing rule 6 — do not strip inline `#`)
- `grep -c 'lifecycle.config.md.*missing' skills/morning-review/references/walkthrough.md` ≥ 1 (guard 1 — file missing)
- `grep -c 'demo-command.*absent' skills/morning-review/references/walkthrough.md` ≥ 1 (guard 2 — field absent or commented)
- `grep -c 'value.*empty' skills/morning-review/references/walkthrough.md` ≥ 1 (guard 3 — empty value)
- `grep -c 'control character' skills/morning-review/references/walkthrough.md` ≥ 1 (guard 4 — control characters)

### R4 — Section 2a guard: skip on remote sessions
Section 2a must be skipped entirely when the morning-review session is running over SSH or mosh, because the user has no realistic path to opening a separate local terminal to paste the demo command. The detection signal is: `$SSH_CONNECTION` is set and non-empty. (Mosh sessions inherit `$SSH_CONNECTION` from the underlying SSH handshake, so a single check covers both.)

**Acceptance**: walkthrough.md Section 2a contains a guard clause referencing `$SSH_CONNECTION` (verifiable by `grep -c 'SSH_CONNECTION' skills/morning-review/references/walkthrough.md` ≥ 1).

### R5 — Section 2a guard: skip when overnight branch is missing
Section 2a must be skipped entirely when `git rev-parse --verify {integration_branch}` exits non-zero, where `{integration_branch}` is read from `lifecycle/sessions/latest-overnight/overnight-state.json` using the same pattern Section 6 step 1 uses today (jq read with fallback). If `overnight-state.json` is missing or `integration_branch` is absent, also skip Section 2a.
**Acceptance**: walkthrough.md Section 2a contains a guard clause naming `git rev-parse --verify` and `integration_branch` (verifiable by `grep -c 'rev-parse --verify' skills/morning-review/references/walkthrough.md` ≥ 1).

### R6 — Section 2a presents exactly one yes/no offer when guards pass
When all guards in R3, R4, R5 pass, Section 2a must present exactly one yes/no question to the user. The question text must include the integration branch name and a one-line preview of what acceptance will do. Suggested form (paraphrasing acceptable; substance must match):

> Spin up a demo worktree of `{integration_branch}` at `$TMPDIR/demo-{session_id}-{timestamp}` and print the launch command? [y / n]

The section must NOT ask any follow-up questions. On any answer (y / n / unparseable), Section 2a immediately advances to Section 2b — see R9.

**Acceptance** (Manual reviewer check, with mechanical smoke test): the implementer asserts that Section 2a's user-facing prose contains exactly one yes/no prompt and no follow-up questions or pauses. Mechanically extracting "the section body" by heading boundaries is not robust enough for a grep-based AC (it requires awk range expressions plus locale-sensitive matching of em-dashes); the trade-off is annotated here per the AC-phrasing header note. **Smoke test**: `awk '/^## Section 2a — Demo Setup$/,/^## Section 2b/' skills/morning-review/references/walkthrough.md | grep -c '?'` ≤ 2. (The cap of 2 allows for one user-prompt sentence ending in `?` plus at most one rhetorical aside; > 2 indicates the section has grown follow-up questions and must be tightened.)

### R7 — Section 2a worktree creation on accept
On user `y` (or `yes`, case-insensitive), the morning-review agent must:
1. Resolve `$TMPDIR` to its canonical absolute form (the symlink chain on macOS is `/var/folders/...` → `/private/var/folders/...`). Resolution method: `realpath "$TMPDIR"`. Both BSD `realpath` (macOS) and GNU `realpath` (Linux) support this form. (Earlier drafts of this spec listed alternatives like `cd && pwd -P` and `readlink -f`; both were dropped — the former is a compound command forbidden by TC2, and the latter does not exist on older macOS BSD by default.)
2. Build a target path of the form `{resolved-tmpdir}/demo-{session_id}-{timestamp}` where `{timestamp}` is `$(date -u +%Y%m%dT%H%M%SZ)` (UTC ISO-8601 compact form, second-precision).
3. Run exactly ONE git command (no shell chaining): `git -c core.hooksPath=/dev/null worktree add "{target-path}" "{integration_branch}"`. The `git -c core.hooksPath=/dev/null` prefix neutralizes any tracked `post-checkout` hook the overnight branch may have added (e.g., via husky / lefthook / pre-commit-framework, which redirect `core.hooksPath` to a tracked directory) — see TC9 for the security rationale. The skill MUST NOT use `--force`. The skill MUST NOT use `git -C` (per `claude/rules/sandbox-behaviors.md`); note that `git -c` (lowercase, config override) is distinct from `git -C` (uppercase, change-directory) and is allowed.
4. On non-zero exit: print the captured stderr, advance to Section 2b. Do not retry. Do not invoke any cleanup.

**Acceptance** (all four greps):
- `grep -c 'realpath' skills/morning-review/references/walkthrough.md` ≥ 1 (R7 step 1)
- `grep -c 'core.hooksPath=/dev/null' skills/morning-review/references/walkthrough.md` ≥ 1 (R7 step 3 hook neutralization)
- `grep -c 'git worktree add' skills/morning-review/references/walkthrough.md` ≥ 1 (R7 step 3 worktree command)
- `grep -c 'NOT use --force' skills/morning-review/references/walkthrough.md` ≥ 1 (R7 step 3 prohibition)

### R8 — Section 2a prints the launch command on success
After `git worktree add` succeeds, the agent must print a literal block to the user containing:
1. The resolved absolute path of the new worktree
2. The verbatim `demo-command` value from `lifecycle.config.md`
3. The cleanup command for when the user is done

Suggested form:
```
Demo worktree created at: {resolved-target-path}

To start the demo, run this in a separate terminal or shell:
    {demo-command}

When you're done, close the demo and remove the worktree:
    git worktree remove {resolved-target-path}
```

The path MUST be the resolved (absolute, symlink-chain-resolved) form, not the literal `$TMPDIR/...` template.
**Acceptance**: walkthrough.md Section 2a contains a "Demo worktree created at:" template AND a "git worktree remove" cleanup line (verifiable by `grep -c 'Demo worktree created at:' skills/morning-review/references/walkthrough.md` = 1 AND `grep -c 'git worktree remove' skills/morning-review/references/walkthrough.md` ≥ 2 — once in Section 2a, once in the existing Section 6 worktree-removal logic).

### R9 — Section 2a immediate auto-advance
After all branches of Section 2a (skipped, declined, accepted-and-succeeded, accepted-and-failed), the walkthrough proceeds to Section 2b WITHOUT waiting for any user input or "demo done" confirmation. This preserves the auto-advance contract codified at walkthrough.md:84 ("Run immediately after the batch verification response. No additional user input is needed.") and aligned with the user's saved preference (`feedback_lifecycle_auto_proceed.md`).
**Acceptance**: walkthrough.md Section 2a contains text matching: "After this section completes (skipped, declined, or accepted), proceed immediately to Section 2b. Do not wait for the user to report demo completion." (verifiable by `grep -c 'Do not wait' skills/morning-review/references/walkthrough.md` ≥ 1).

### R10 — Section 2a does NOT execute the `demo-command` itself
The morning-review agent MUST NOT execute `demo-command` via the Bash tool, a subprocess invocation, or any other mechanism. The command is printed for the user to manually run in their own shell. This is a security boundary: `lifecycle.config.md` is a checked-in file that travels with branches; any contributor opening a PR could write arbitrary shell into `demo-command`. By requiring the user to manually paste-and-run the command, acceptance is gated on an explicit human action that displays the verbatim command first.

The walkthrough.md Section 2a text MUST contain an explicit prohibition matching: "The agent MUST NOT execute the demo-command itself; it is printed for the user to run manually in a separate terminal."
**Acceptance**: `grep -c 'MUST NOT execute the demo-command' skills/morning-review/references/walkthrough.md` ≥ 1.

### R11 — Section 6 step 5 cleanup reminder
The existing Section 6 step 5 success path (PR merge succeeded → worktree-remove of integration worktree) must be extended with one additional unconditional reminder line, printed AFTER the existing worktree-removal report:

> If you spun up a demo earlier in this review, close the demo and remove its worktree using the `git worktree remove` command printed at the time.

The reminder is unconditional — it does not check whether Section 2a was actually accepted. The cost of an unnecessary reminder when no demo was created (one extra line of output) is far cheaper than the cost of forgetting to remind someone who did create one. The reminder also does not attempt to detect "still running" — see Non-Requirement NR3.
**Acceptance**: walkthrough.md Section 6 step 5 success path contains the literal phrase "If you spun up a demo earlier" (verifiable by `grep -c 'If you spun up a demo earlier' skills/morning-review/references/walkthrough.md` = 1).

### R12 — Step 0 garbage sweep for stale demo worktrees
The existing morning-review SKILL.md Step 0 (mark overnight session complete) must be extended with a garbage-sweep sub-step that removes demo worktrees from prior sessions. Logic:

1. Read the current session ID (already resolved by Step 0 from `overnight-state.json`).
2. Resolve `$TMPDIR` to its canonical absolute form using `realpath "$TMPDIR"` (same method as R7 step 1).
3. Run `git worktree list --porcelain`. For each line beginning with `worktree `, extract the path.
4. For each path matching the regex `^{resolved-tmpdir}/demo-overnight-[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{4}-[0-9]{8}T[0-9]{6}Z$` (the canonical Section-2a-created form: `demo-{session_id}-{timestamp}`): if the path does NOT begin with `{resolved-tmpdir}/demo-{current_session_id}-`, run `git worktree remove "{path}"` (no `--force`). On success, print one-line confirmation. On failure (e.g., dirty worktree with unsaved user edits), print the captured stderr and continue — do not retry, do not force, and do not abort the morning-review walkthrough.
5. After all per-worktree removals (successful or not), run `git worktree prune` once to clean any orphaned admin metadata under `$(git rev-parse --git-dir)/worktrees/` whose target directories were already removed manually by the user. Errors are non-fatal.

**Path-filter rationale**: Step 4's regex is intentionally narrow — it matches only paths created by Section 2a's R7 step 2 path-construction template. A loose `$TMPDIR/demo-*` filter would collide with unrelated user worktrees on Linux dev machines where `$TMPDIR` defaults to `/tmp` and `demo-*` is a common scratch-name prefix. The strict regex restricts the sweep to paths that are unambiguously this feature's output.

**`--force` removed**: earlier drafts of this spec used `git worktree remove --force` for the sweep, with the rationale that checking cleanliness via `git status` would require `git -C` (forbidden). The critical-review pass flagged that the user could have unsaved edits in a stale demo worktree from a 2am debugging session. Force-removing those edits silently is unacceptable. The new contract is "remove what's clean, fail loudly on dirty." Failed removals leave the worktree in place; it will be retried on the next morning-review (and if the user genuinely needs to keep the edits, they'll move them out before the next sweep).

**Acceptance** (all six greps must pass):
- `grep -c 'Garbage sweep' skills/morning-review/SKILL.md` ≥ 1 (sub-step heading present)
- `grep -c 'git worktree list --porcelain' skills/morning-review/SKILL.md` ≥ 1 (worktree enumeration command named)
- `grep -c 'demo-overnight-' skills/morning-review/SKILL.md` ≥ 1 (path-filter regex prefix named)
- `grep -c 'git worktree remove' skills/morning-review/SKILL.md` ≥ 1 (removal command named)
- `grep -c 'no .--force' skills/morning-review/SKILL.md` ≥ 1 (sub-step explicitly says no `--force`; the `.` is regex-friendly for the leading hyphen-or-backtick character)
- `grep -c 'git worktree prune' skills/morning-review/SKILL.md` ≥ 1 (admin metadata cleanup)

### R13 — SKILL.md Step 3 outline mentions Demo Setup
The existing morning-review SKILL.md Step 3 numbered list (currently 4 items: Completed Features → Lifecycle Advancement → Deferred Questions → Failed Features) must be extended with a 5th item describing Demo Setup, inserted between item 1 (Completed Features) and item 2 (Lifecycle Advancement). Suggested form: `2. **Demo Setup** — if `demo-command` is configured and the session is local, offer to spin up a demo worktree`.
**Acceptance**: `grep -c 'Demo Setup' skills/morning-review/SKILL.md` ≥ 1 AND the "Demo Setup" line appears between the "Completed Features" line and the "Lifecycle Advancement" line in Step 3.

### R14 — Edge cases table updated with new failure-mode rows
The existing Edge Cases table in walkthrough.md (currently lines 418–457) must gain new rows for each Section 2a guard and failure path. At minimum:

| Situation | Action |
|-----------|--------|
| `lifecycle.config.md` missing at project root | Skip Section 2a entirely |
| `lifecycle.config.md` present but `demo-command` absent or commented out | Skip Section 2a entirely |
| `lifecycle.config.md` present but `demo-command` value is empty | Skip Section 2a entirely |
| `demo-command` value contains control characters / ANSI escapes | Skip Section 2a entirely; treat as malformed |
| `$SSH_CONNECTION` set (running over SSH or mosh) | Skip Section 2a entirely |
| `git rev-parse --verify {integration_branch}` exits non-zero (branch missing or pruned) | Skip Section 2a entirely |
| Overnight branch already checked out by another worktree | `git worktree add` fails with "already checked out" error; print stderr; advance to Section 2b |
| User declines the demo offer | Print no further output; advance to Section 2b |
| `git worktree add` fails on accept (any other reason — disk full, locked, etc.) | Print git's stderr; advance to Section 2b without retry |
| Agent crashes between worktree creation and command print | Worktree exists on disk with no record for the user; next morning-review's Step 0 sweep will retry removal (and fail if dirty) |
| Stale demo worktree from prior session in `$TMPDIR` | Removed by Step 0 garbage sweep on next morning-review (if clean) |
| Stale demo worktree from prior session contains user edits | Sweep's `git worktree remove` (no `--force`) fails; stderr printed; user can investigate and rescue edits manually |
| Demo worktree created but user closes session before Section 6 reminder | No cleanup until next morning-review's Step 0 garbage sweep |
| User abandons the repo entirely (no future morning-review for it) | Stale worktrees and `.git/worktrees/` admin entries persist indefinitely until manual cleanup or OS reboot — accepted limitation, see Non-Requirement NR13 |

**Acceptance** (each row must be greppable by a unique substring; all 14 greps must return ≥ 1):
- `grep -c 'lifecycle.config.md missing at project root' skills/morning-review/references/walkthrough.md` ≥ 1
- `grep -c 'demo-command.* absent or commented' skills/morning-review/references/walkthrough.md` ≥ 1
- `grep -c 'demo-command.* value is empty' skills/morning-review/references/walkthrough.md` ≥ 1
- `grep -c 'control characters' skills/morning-review/references/walkthrough.md` ≥ 1
- `grep -c 'SSH_CONNECTION.* set' skills/morning-review/references/walkthrough.md` ≥ 1
- `grep -c 'rev-parse --verify' skills/morning-review/references/walkthrough.md` ≥ 1
- `grep -c 'already checked out' skills/morning-review/references/walkthrough.md` ≥ 1
- `grep -c 'declines the demo offer' skills/morning-review/references/walkthrough.md` ≥ 1
- `grep -c 'git worktree add.* fails' skills/morning-review/references/walkthrough.md` ≥ 1
- `grep -c 'crashes between worktree creation' skills/morning-review/references/walkthrough.md` ≥ 1
- `grep -c 'Stale demo worktree from prior session' skills/morning-review/references/walkthrough.md` ≥ 2
- `grep -c 'closes session before' skills/morning-review/references/walkthrough.md` ≥ 1
- `grep -c 'abandons the repo' skills/morning-review/references/walkthrough.md` ≥ 1

## Non-Requirements

- **NR1**: No "smart demoability assessment" layer. The agent does not read the diff, does not read per-feature spec.md, and does not classify which features are "demoable." Section 2a is triggered solely by `demo-command` being configured + branch existing + non-remote session. The original ticket's framing of "the agent reasons about whether features warrant validation" is explicitly discarded as untestable false-precision.
- **NR2**: No agent-managed demo process. The agent does not run `demo-command`, does not track its PID, does not background it via `nohup`/`disown`/`setsid`/`Popen`, and does not detect whether the demo is still running. The user runs the demo in their own shell and is responsible for its lifecycle.
- **NR3**: No "still running" detection at Section 6. The Section 6 reminder is unconditional. The agent does not attempt to detect via port scan, PID lookup, process listing, or directory inspection whether the user's demo is still active.
- **NR4**: No support for multiple demoable surfaces per repo (no map-of-commands schema). The schema is a single scalar `demo-command` field. Repos with multiple surfaces (e.g., a dashboard and a CLI) must pick one or wait for v2.
- **NR5**: No per-feature `demo-command` override. `demo-command` is repo-level only.
- **NR6**: No standalone `/demo` slash command. The feature lives entirely inside morning-review. If usage signal later shows a need for outside-morning-review invocation, extracting this logic into a `/demo` skill is mechanical and can be done as a follow-up.
- **NR7**: No conditional offer based on diff content (e.g., "skip if only docs changed"). The offer fires whenever `demo-command` is set and guards pass. A user with a docs-only session pays a one-keystroke decline cost; this is cheaper than the spec-ambiguity of "what counts as docs-only."
- **NR8**: No automatic worktree cleanup at Section 6. Cleanup happens at Step 0 of the NEXT morning-review (R12). The Section 6 reminder is text-only.
- **NR9**: No changes to `claude/overnight/runner.sh`, `claude/overnight/parser.py`, `claude/overnight/state.py`, or any other overnight-pipeline component. The feature is purely morning-review-side; the runner is not aware of `demo-command`.
- **NR10**: No new shared YAML parser module. The `lifecycle.config.md` field is read inline by the morning-review skill using the parsing rules pinned in R3. The four existing private `_parse_frontmatter` copies in the codebase are not consolidated as part of this feature.
- **NR11**: No backward-compatibility shims for old morning-review walkthroughs without Section 2a. The new section is additive; no users have a "section between 2 and 2b" today, so there is nothing to migrate from.
- **NR12**: No support for `demo-command` values that contain inline `#` comments. The parsing rule (R3) treats the entire post-colon string as the value. Users with `#` in their commands (not as a comment) work correctly; users who want to comment a portion of the line out must use a separate fully-commented variant.
- **NR13**: No "abandoned repo" cleanup. If the user accepts a demo offer in repo A, then never runs `/morning-review` for repo A again (switches workflows, repo dies, etc.), the stale worktree at `$TMPDIR/demo-overnight-{...}-{...}` and its `.git/worktrees/demo-...` admin entry persist until macOS reboots `/var/folders` or until the user manually runs `git worktree prune` from repo A. This is an accepted limitation; the realistic alternative (cross-repo, OS-level cleanup) is disproportionately complex for the upside.
- **NR14**: No printed dependency-execution warning. The user opting into the demo (typing `y`) is the consent surface; running `npm install` / `uv sync` / Godot asset import / `cargo run` from the worktree may execute code from the overnight branch (post-install hooks, build scripts, `@tool` scripts), but this is the same trust boundary that already exists when the user merges the PR — the demo step is just running it earlier. The spec deliberately does NOT print a warning to avoid habituating the user to a "yes, I have read the warning" reflex that empties the warning of value.

## Edge Cases

- **`lifecycle.config.md` missing at project root**: Skip Section 2a entirely. No prompt, no error, no message printed.
- **`demo-command` field absent from a present `lifecycle.config.md`**: Same as missing file. Skip silently.
- **`demo-command:` line is fully commented (`# demo-command: foo`)**: Parsing rule (R3 step 2) ignores comment lines. Skip silently.
- **`demo-command:` value is whitespace-only**: Parsing rule (R3 step 4) treats empty as unset. Skip silently.
- **`demo-command:` value contains inline `#`**: Treated as part of the command (R3 step 5). User responsibility per NR12.
- **`$SSH_CONNECTION` is set**: Section 2a skipped entirely. No fallback "print only" mode for SSH/mosh in v1 — the simplest version. If usage demands it later, add a config option.
- **`integration_branch` field absent from `overnight-state.json`**: Skip Section 2a (R5). Same fallback as Section 6 step 1's "no integration branch" path.
- **`overnight/{session_id}` branch deleted between session end and morning-review**: `git rev-parse --verify` returns non-zero. Skip Section 2a (R5). Print no error.
- **User accepts the demo offer**: Worktree is created, path and command are printed, walkthrough advances to Section 2b immediately.
- **User declines (n)**: No worktree creation, no output beyond moving on. Walkthrough advances to Section 2b immediately.
- **User responds with unparseable input** (e.g., empty string, "maybe"): Treat as decline. Advance to Section 2b. Do not re-prompt.
- **`git worktree add` fails because the target path already exists**: Captured stderr is printed. Walkthrough advances to Section 2b. Note: timestamp salt in R7 makes same-session collisions effectively impossible (timestamps are second-precision in UTC), but cross-session collisions are caught by the Step 0 garbage sweep.
- **`git worktree add` fails because of a stale worktree registration**: Same as above. The garbage sweep at Step 0 handles stale registrations on the NEXT morning-review invocation; the current invocation does not retry or self-heal.
- **`git worktree add` fails for any other reason** (disk full, permission denied, locked branch): Captured stderr printed; walkthrough advances. Do not retry.
- **`$TMPDIR` is unset or empty**: Treat as `/tmp`. (Standard shell convention; macOS always sets `$TMPDIR` so this is a Linux/dev-container fallback.)
- **`$TMPDIR` is a symlink chain**: Resolved per R7 step 1. The printed path is canonical; commands the user pastes resolve correctly.
- **Two morning-review sessions running concurrently for two different repos**: Each has its own `$TMPDIR/demo-{their-session-id}-{ts}` path, so the worktree directories themselves do not collide. The Step 0 garbage sweep is safe across concurrent repos because `git worktree list --porcelain` is repo-scoped: it only enumerates worktrees registered in the CURRENT repo's `$(git rev-parse --git-dir)/worktrees/`. Worktrees created by another repo's `/morning-review` invocation are registered in that repo's git dir, not this one, so they are not visible to this sweep and cannot be removed by it. **Important**: this safety property depends on `git worktree list` being repo-scoped — it does NOT depend on the session-ID exclusion filter alone. A future "optimization" that reads the worktree directory listing directly (e.g., `ls $TMPDIR/demo-*` without going through git) would break this property and is forbidden.
- **User reruns `/morning-review` for the same overnight session**: Step 0 garbage sweep does NOT remove the current-session demo worktree (the current session ID is excluded from the sweep filter, R12). Section 2a creates a new worktree with a fresh timestamp. Both worktrees coexist until the NEXT morning-review (when they'll both be stale).
- **User runs `/morning-review` against an overnight session that is several days old**: Step 0 garbage sweep removes any demo worktrees from earlier sessions; Section 2a guards check `git rev-parse --verify` for the current session's overnight branch (which may have been pruned). Both edge cases are handled.
- **`gh pr merge` succeeds in Section 6 but the user still has the demo running**: The Section 6 reminder fires unconditionally. The user closes the demo and removes the worktree manually using the printed cleanup command. Next morning-review's Step 0 garbage sweep is the safety net for "user forgot to clean up."
- **`git worktree remove --force` fails during garbage sweep at Step 0**: Each removal is wrapped in non-fatal error handling per R12. Print and continue. The next sweep retries.

## Changes to Existing Behavior

- **MODIFIED**: `skills/lifecycle/assets/lifecycle.config.md` schema gains an optional `demo-command:` field. Repos with no project-root `lifecycle.config.md` or no `demo-command` field are unaffected (the new field is opt-in).
- **MODIFIED**: `skills/morning-review/SKILL.md` Step 0 gains a garbage-sweep sub-step (R12). Sessions with no stale `$TMPDIR/demo-*` worktrees see no change in behavior beyond a no-op `git worktree list` invocation.
- **MODIFIED**: `skills/morning-review/SKILL.md` Step 3 outline gains a 5th item ("Demo Setup") inserted between Completed Features and Lifecycle Advancement.
- **MODIFIED**: `skills/morning-review/references/walkthrough.md` gains a new conditional sub-section `## Section 2a — Demo Setup` between Section 2 and Section 2b.
- **MODIFIED**: `skills/morning-review/references/walkthrough.md` Section 6 step 5 success path gains an unconditional cleanup reminder line.
- **MODIFIED**: `skills/morning-review/references/walkthrough.md` Edge Cases table gains 9 new rows (R14).
- **ADDED**: A new agentic-layer convention: skills that read `lifecycle.config.md` field values where the value is a shell command (not a single token or boolean) follow the parsing rules pinned in R3. Future fields of similar shape can reference these rules.

## Technical Constraints

- **TC1 — `git -C <path>` is forbidden**: per `claude/rules/sandbox-behaviors.md`, `git -C` does not match permission allow rules. All git invocations must run from the project root with positional path arguments. R7 (`git worktree add`) and R12 (`git worktree list --porcelain` and `git worktree remove`) are the only git commands introduced; all use this pattern.
- **TC2 — No compound commands**: per `claude/rules/sandbox-behaviors.md`, commands chained with `&&`, `;`, or `|` evaluate as a single string for permission matching. All new git invocations must be issued as separate commands. The R7 `git worktree add` is one command. R12's "list, then remove" requires multiple invocations issued sequentially.
- **TC3 — No HEREDOC for any commit messages**: `claude/rules/sandbox-behaviors.md`. Implementation commits go through the `/commit` skill, which handles formatting.
- **TC4 — Symlinked files**: `skills/lifecycle/assets/lifecycle.config.md`, `skills/morning-review/SKILL.md`, and `skills/morning-review/references/walkthrough.md` are symlinked from the repo into `~/.claude/skills/`. Edits MUST be made to the repo copies; do not edit the destination paths.
- **TC5 — Auto-advance contract preserved**: walkthrough.md:84 codifies "Run immediately after the batch verification response. No additional user input is needed." User memory `feedback_lifecycle_auto_proceed.md` reinforces this. Section 2a violates this contract if it waits for any user input beyond the single y/n offer in R6. Spec R9 makes auto-advance explicit.
- **TC6 — Sandbox `$TMPDIR` allowlist**: the project's sandbox config (`claude/settings.json`) allows writes under `$TMPDIR`. The chosen worktree location is consistent with the existing overnight-runner pattern that uses `$TMPDIR/overnight-worktrees/`.
- **TC7 — Permission allow rules for `git worktree`**: confirmed at spec time. `claude/settings.json:95` already contains `"Bash(git worktree *)"`, which authorizes `git worktree add`, `git worktree list`, `git worktree remove`, and `git worktree prune` without prompting. The `git -c core.hooksPath=/dev/null worktree add ...` form (R7 step 3) is also covered because the wildcard matches the suffix. No global-allow expansion is needed.
- **TC8 — `realpath` portability**: macOS `realpath` (BSD) differs slightly from GNU `realpath` but both support the canonical-path resolution form needed here. Alternative implementations (`python3 -c`, `cd && pwd -P`) are documented in R7 as acceptable substitutes.
- **TC9 — Security boundary on `demo-command` execution and worktree creation**: R10 + NR2 establish that the agent never executes `demo-command` directly. R3's control-character rejection (parsing rule 4) prevents ANSI escape sequences from hiding the printed value from the user. R7 step 3's `git -c core.hooksPath=/dev/null` prefix neutralizes any tracked `post-checkout` hook the overnight branch might use to escape the trust boundary during `git worktree add` (relevant for repos using husky / lefthook / pre-commit-framework). The remaining trust boundary — the user manually running `demo-command` from a worktree containing the overnight branch, which may trigger `npm install` / `uv sync` / asset-import code execution from that branch — is accepted as natural consent: the user opting into the demo is opting into running overnight-branch code, the same code they'd run after PR merge. NR14 documents this stance and explains why no printed warning is shown.
- **TC10 — Strategic-review framing tension**: project.md states "Morning is strategic review — not debugging sessions." Adding an interactive demo offer to morning-review introduces tension with this framing. The mitigation is that Section 2a never blocks the walkthrough, never holds state, and never executes anything itself — it is a one-line offer that the user can decline with a single keystroke. The walkthrough returns to its strategic-review character immediately.
- **TC11 — Pipeline branch persistence**: this feature is a new, unstated consumer of `requirements/pipeline.md`'s "Integration branch persistence" architectural constraint (which is stated for "manual PR creation and review" only). Section 2a's behavior is graceful when the branch is missing (R5), so the constraint is not strengthened — the feature degrades cleanly when the branch's lifecycle differs from what is expected.
- **TC12 — Discovery research correction**: the discovery research at `research/morning-review-demo-setup/research.md:19` and the backlog item at `backlog/071-auto-launch-demo-at-morning-review.md:43` both contain the incorrect Godot example `godot --play res://main.tscn`. Implementation should correct these at the source as part of the same change set, not because they are functional dependencies but because the wrong example would otherwise propagate to readers of those documents.

## Open Decisions

None. All decisions previously open at the end of research were resolved during the user-facing scope conversation:
- Top-level shape: morning-review subsection (Approach H), not standalone `/demo`.
- Smart-assessment layer: dropped (NR1).
- Per-repo single field: yes (NR4, NR5).
- Cleanup contract: garbage sweep at next Step 0 (R12); reminder at Section 6 (R11); no still-running detection (NR3).
- Worktree path: `{resolved-$TMPDIR}/demo-{session_id}-{timestamp}` with timestamp salt.
- Branch-deleted fallback: skip silently (R5).
- Insertion point: between Section 2 and Section 2b (R2).
- Parser precision: pinned inline in R3.
- Security framing: agent never executes `demo-command` (R10, NR2, TC9).
- Remote-session incompatibility: skip silently (R4).
- Wrong Godot example: corrected at source (R1, TC12).
- Strategic-review framing: tension acknowledged (TC10), mitigated by section being non-blocking and non-stateful.
