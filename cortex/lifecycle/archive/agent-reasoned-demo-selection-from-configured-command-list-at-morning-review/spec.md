# Specification: Agent-reasoned demo selection from configured command list at morning review

## Problem Statement

`#071` shipped a single `demo-command:` string in `lifecycle.config.md` that Section 2a always offers when guards pass. With one command, the unconditional offer is fine — it fires or it doesn't. With a list of commands (e.g., Godot gameplay, FastAPI dashboard, CLI), the same unconditional logic would offer *all* entries every session, which defeats the purpose of having a list. The user wants the morning-review agent to scan the features that completed overnight, reason about which demo command is most contextually relevant to those changes, and offer exactly that one — or offer nothing if nothing is relevant. The selection input is the "Key files changed" data the agent already has in context from Section 2, so no additional git commands or file reads are required.

> **Design rationale — superseding NR1 and NR7**: #071's Non-Requirements NR1 ("smart demoability assessment is untestable false-precision") and NR7 ("no conditional offer based on diff content") were correct for the single-command case — the one-keystroke decline cost was lower than the spec-ambiguity of "what counts as relevant." For a list, that tradeoff reverses: the value proposition only exists if the agent filters, and the structural contract (one offer or none, from a finite configured list, always auto-advancing) remains testable even if selection quality is not. NR1 and NR7 remain in effect for the existing `demo-command:` single-string path, which is unchanged.

## Requirements

> **Priority classification**: All requirements R1–R9 are **Must-have**. The feature is intentionally scoped to the minimum surface that delivers the list-based agent-selection value without taking on path-hint config, fallback complexity, or git-command overhead. There are no Should-have requirements — every item here is load-bearing for either the config schema (R1), the guard routing (R2, R3), the selection logic (R4), the offer/print contract (R5, R6), the security boundary (R7), or documentation consistency (R8, R9).

### R1 — `demo-commands:` YAML list added to lifecycle.config.md template

Add an optional, commented-by-default `demo-commands:` block list to `skills/lifecycle/assets/lifecycle.config.md`, placed immediately after the existing `# demo-command:` line. The template must include a commented example with at least two entries to demonstrate the block list format. Each entry has exactly two sub-keys: `label:` (human-readable name) and `command:` (shell command to print). Example (must appear verbatim as a comment block in the template):

```
# demo-commands:
#   - label: "Godot gameplay"
#     command: "godot res://main.tscn"
#   - label: "FastAPI dashboard"
#     command: "uv run fastapi run src/main.py"
```

**Acceptance**:
- `grep -c '^# demo-commands:' skills/lifecycle/assets/lifecycle.config.md` = 1
- `grep -c 'label:' skills/lifecycle/assets/lifecycle.config.md` ≥ 2
- `grep -c 'command:' skills/lifecycle/assets/lifecycle.config.md` ≥ 2

### R2 — Guard 1 updated: routes between demo-commands: list and demo-command: single-string

Section 2a Guard 1 is extended. It now checks for `demo-commands:` first, falling back to the existing `demo-command:` path if no list is configured. The updated guard behavior:

- If `lifecycle.config.md` is missing → skip Section 2a silently
- If `lifecycle.config.md` exists:
  - If a non-commented `demo-commands:` block is present and contains at least one valid entry → enter the **new agent-reasoning flow** (R3–R6)
  - Else if a non-commented `demo-command:` line is present and valid → enter the **existing #071 single-command flow** (unchanged)
  - Else → skip Section 2a silently

**`demo-commands:` parsing rules** (apply in order — adapted from R3 in #071 spec):

1. Read the file. Scan for the first non-commented line that exactly matches `demo-commands:` (after stripping leading whitespace).
2. Collect subsequent indented lines of the form `- label: "..."` and `command: "..."` as list entries, stopping at the first non-indented, non-blank line.
3. For each entry, extract `label:` value and `command:` value using the same first-colon extraction rule from R3 of the #071 spec: extract everything after the first `:` character and strip leading/trailing whitespace.
4. Reject any entry whose `command:` value contains a control character (byte < 0x20 except `\t`). Silently discard that entry.
5. Reject any entry whose `command:` value is empty after trimming. Silently discard that entry.
6. If no valid entries remain after filtering, treat `demo-commands:` as absent (fall through to `demo-command:` check).
7. Do NOT strip inline `#` comments from `command:` values. Shell commands may legitimately contain `#`.

**Acceptance**:
- `grep -c 'demo-commands:' skills/morning-review/references/walkthrough.md` ≥ 1 (Guard 1 routing logic present)
- `grep -c 'first.*colon\|after the first' skills/morning-review/references/walkthrough.md` ≥ 1 (parsing rule 3 — first-colon extraction)
- `grep -c 'control character' skills/morning-review/references/walkthrough.md` ≥ 1 (parsing rule 4 — carried over from #071)
- `grep -c 'inline.*comments\|inline.*#' skills/morning-review/references/walkthrough.md` ≥ 1 (parsing rule 7 — do not strip `#`)
- `grep -c 'non-indented\|indented.*entries\|stop.*non-indented' skills/morning-review/references/walkthrough.md` ≥ 1 (parsing rule 2 — block boundary: collect indented lines, stop at first non-indented non-blank line)
- `grep -c 'empty.*command\|command.*empty\|whitespace-only' skills/morning-review/references/walkthrough.md` ≥ 1 (parsing rule 5 — empty command value → discard entry)
- `grep -c 'no valid entries\|fall.*through.*demo-command\|fall.*back.*demo-command' skills/morning-review/references/walkthrough.md` ≥ 1 (parsing rule 6 — fallthrough to demo-command: when no valid entries remain)

### R3 — Guard 3 extended: skip when zero features merged (demo-commands: path only)

Guard 3 already reads `lifecycle/sessions/latest-overnight/overnight-state.json` for `integration_branch`. When the `demo-commands:` list path is active (Guard 1 selected the new reasoning flow), extend Guard 3 with an additional skip condition: if the `features` map in `overnight-state.json` contains zero entries with `"status": "merged"`, skip Section 2a silently. This prevents a spurious demo offer for sessions where nothing demoable was produced.

This extension applies **only to the `demo-commands:` path**. The `demo-command:` single-string path uses Guard 3's existing two-condition check unchanged (missing state file / branch does not exist).

Order of checks within Guard 3 for the `demo-commands:` path:
1. `overnight-state.json` missing or `integration_branch` absent → skip
2. `git rev-parse --verify {integration_branch}` exits non-zero → skip
3. No features with `"status": "merged"` in `overnight-state.json` → skip (demo-commands: path only)

**Acceptance**:
- `grep -c '"status".*merged\|status.*merged' skills/morning-review/references/walkthrough.md` ≥ 1
- `grep -c 'zero.*features\|no.*merged\|no completed features' skills/morning-review/references/walkthrough.md` ≥ 1

### R4 — Agent reasons from Section 2 context to select one entry (or none)

After all guards pass (R2, Guard 2 SSH check, Guard 3 as extended by R3), and the `demo-commands:` list path is active, Section 2a must:

1. **Not** run any additional git commands or file reads. The input for selection reasoning is the completed-features list already in context from Section 2: specifically, feature names and their "Key files changed" bullets as displayed during Section 2.
2. Reason: given the features that completed overnight and the files they changed, which `demo-commands:` entry (by label) is most contextually relevant? The label is the primary matching signal.
3. If a clear winner exists → proceed to R5 (demo offer for that entry).
4. If no entry is clearly relevant to the overnight work → skip Section 2a silently. No offer is presented, no worktree is created.

**Acceptance**: Interactive/session-dependent — the selection criterion is intentionally agent-reasoned; no mechanical command can verify selection quality. The structural contract (at most one offer from the configured list, always auto-advancing) is verified by R5 and R6 below.

The walkthrough must contain language specifying that the agent uses "completed features" and their "Key files changed" data as selection context, without running additional git commands:
- `grep -c 'Key files changed\|key files changed' skills/morning-review/references/walkthrough.md` ≥ 2 (at least one reference in Section 2 and one in Section 2a)
- `grep -c 'no additional git\|already in context\|already processed' skills/morning-review/references/walkthrough.md` ≥ 1

### R5 — Demo offer shows selected entry's label and command

When R4 selects an entry, Section 2a presents exactly one yes/no offer. The offer text must include the selected entry's label and command. Suggested form (paraphrasing acceptable; substance must match):

> Run `{selected-label}` demo (`{selected-command}`) from `{integration_branch}` in a fresh worktree? [y / n]

On `n` or any unparseable input: advance to Section 2b (unchanged from #071). On `y`: proceed to worktree creation (unchanged from #071, R7 in #071 spec). Section 2a must not ask any follow-up questions.

**Acceptance**:
- `grep -c '{selected-label}' skills/morning-review/references/walkthrough.md` ≥ 1
- `grep -c '{selected-command}' skills/morning-review/references/walkthrough.md` ≥ 1

### R6 — Print template uses selected entry's label and command

The print template after a successful worktree add must reference `{selected-label}` and `{selected-command}` (replacing the legacy `{demo-command}` placeholder on the `demo-commands:` path). The template for the `demo-commands:` path:

```
Demo worktree created at: {resolved-target-path}

To start the demo ({selected-label}), run this in a separate terminal or shell:
    {selected-command}

When you're done, close the demo and remove the worktree:
    git worktree remove {resolved-target-path}
```

The legacy `{demo-command}` placeholder remains in the print template for the `demo-command:` single-string path (unchanged).

**Acceptance**:
- `grep -c 'To start the demo ({selected-label})' skills/morning-review/references/walkthrough.md` ≥ 1
- `grep -c '{selected-command}' skills/morning-review/references/walkthrough.md` ≥ 1

### R7 — Security boundary language updated

The security boundary note in Section 2a must be updated to explicitly cover the `demo-commands:` list case. The updated phrasing must read:

> The agent MUST NOT execute the selected command (or the `demo-command:` value) itself; it is printed for the user to run manually in a separate terminal session.

**Acceptance**:
- `grep -c 'selected command\|selected.*demo' skills/morning-review/references/walkthrough.md` ≥ 1

### R8 — SKILL.md Step 3 item 2 updated

`skills/morning-review/SKILL.md` Step 3 item 2 currently reads: "**Demo Setup** — if `demo-command` is configured and the session is local, offer to spin up a demo worktree from the overnight branch." Update to reference `demo-commands:` list and agent-reasoned selection.

**Acceptance**:
- `grep -c 'demo-commands\|demo-command' skills/morning-review/SKILL.md` ≥ 1 (updated reference present)

### R9 — docs/overnight.md updated

`docs/overnight.md` lines documenting `demo-command` must be updated to document the `demo-commands:` list schema and selection behavior.

**Acceptance**: Interactive/session-dependent — the doc change is narrative and not greppable to a specific substring, but the word `demo-commands:` must appear:
- `grep -c 'demo-commands:' docs/overnight.md` ≥ 1

---

## Non-Requirements

- **NR1 (updated)**: No agent reasoning about diff content is the rule for the **`demo-command:` single-string path** — that path is unchanged from #071 NR1. For the `demo-commands:` list path, agent reasoning from Section 2 context IS the mechanism. This NR only applies to the legacy single-string path.
- **NR2**: No per-entry `areas:`, `paths:`, or `tags:` hints. Agent judgment from completed-feature context is the filter — no supplemental matching config to maintain.
- **NR3**: No fallback from `demo-commands:` "none selected" to `demo-command:`. When the list path is active and agent selects nothing, Section 2a skips silently. The `demo-command:` fallback is only reached when `demo-commands:` is entirely absent/invalid.
- **NR4**: No changes to `runner.sh`, `parser.py`, `batch_runner.py`, or any overnight pipeline component. The feature is purely morning-review-side.
- **NR5**: No new shared YAML parser module. Parsing is inline skill text, consistent with #071 NR10.
- **NR6**: No additional git commands in Section 2a. Selection reasoning uses the morning report's "Key files changed" data already in context — not a fresh `git diff`.
- **NR7 (updated)**: No conditional offer based on diff content is the rule for the **`demo-command:` single-string path** — that path still fires unconditionally when guards pass. For the `demo-commands:` list path, conditional selection IS the defined behavior.

---

## Edge Cases

- **`demo-commands:` list is present but all entries have control characters in `command:`**: After filtering (R2 rule 4), no valid entries remain. Fall through to `demo-command:` single-string check (or skip if that's also absent).
- **`demo-commands:` and `demo-command:` are both configured**: `demo-commands:` takes precedence. The `demo-command:` field is ignored on sessions where `demo-commands:` is non-empty and valid.
- **Single entry in `demo-commands:`**: Agent may still reason "none relevant" and skip silently, even with only one entry. Having one entry does not guarantee an offer.
- **Zero features merged in `overnight-state.json`**: Guard 3 fires, Section 2a skips silently. No offer regardless of `demo-commands:` content.
- **`overnight-state.json` missing `features` key** (older state format): Treat as zero merged features — skip Section 2a silently.
- **Section 2 showed features but agent has poor context on what they changed**: Agent selects "none relevant" and skips silently. This is the correct graceful degradation — the user experiences one extra silent skip, not a wrong offer.
- **Label contains a colon** (e.g., `"Godot: gameplay"`): Parsing rule 3 (first-colon extraction) applies to `label:` value too — extract everything after the first `:` then trim. A label of `"Godot: gameplay"` parses correctly to `Godot: gameplay`.

---

## Changes to Existing Behavior

- **MODIFIED: Guard 1** — previously checked only for `demo-command:` single string. Now checks for `demo-commands:` list first, routes to agent-reasoning flow if list is present and valid, falls back to existing single-string path if not.
- **MODIFIED: Demo offer** — on the `demo-commands:` path, the offer shows the selected entry's `{selected-label}` and `{selected-command}` instead of a generic yes/no for a single command.
- **MODIFIED: Print template** — on the `demo-commands:` path, prints `{selected-label}` and `{selected-command}` instead of generic `{demo-command}`.
- **MODIFIED: Guard 3** — extended with a zero-merged-features check when the `demo-commands:` path is active; `demo-command:` single-string path continues to use Guard 3's existing two-condition check unchanged.
- **ADDED: Agent selection step** — when `demo-commands:` list is active and all guards pass, Section 2a now includes an agent-reasoning step before the offer (uses Section 2 context, no additional file reads).
- **UNCHANGED: `demo-command:` single-string path** — all #071 behavior (NR1, NR7, parsing rules, offer, worktree creation, print template) is preserved exactly. Projects using `demo-command:` require no migration.

---

## Technical Constraints

- `lifecycle.config.md` is not read by the overnight runner — only the morning-review skill reads it. Adding `demo-commands:` requires no changes to `runner.sh`, `parser.py`, or `batch_runner.py` (confirmed: runner receives `test-command` as a CLI arg, not from the config file).
- YAML list parsing is inline skill text (not a shared module) — consistent with #071 NR10. The spec's parsing rules must be pinned as greppable phrases in walkthrough.md so they serve as mechanical ACs.
- The `git -c core.hooksPath=/dev/null worktree add` prefix is mandatory on the `demo-commands:` path (same as #071 R7 step 3) — neutralizes `post-checkout` hooks.
- `{placeholder}` braces are LITERAL in skill text — agents substitute at runtime. `{selected-label}` and `{selected-command}` follow this convention.
- The `demo-commands:` path shares Guards 2 and 3 with the existing single-string path — no duplication of SSH and branch-existence checks.

---

## Open Decisions

None. All design decisions were resolved during the user interview or are derivable from research findings.
