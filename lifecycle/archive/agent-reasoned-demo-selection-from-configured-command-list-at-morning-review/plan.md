# Plan: agent-reasoned-demo-selection-from-configured-command-list-at-morning-review

## Overview

Add a `demo-commands:` list schema to the lifecycle.config.md template and restructure
Section 2a of the morning-review walkthrough to route between the new list-based
agent-reasoning path and the existing single-string `demo-command:` path. Six targeted
edits across four files; no runner, parser, or lifecycle-phase code touched.

## Tasks

### Task 1: Add `demo-commands:` block to lifecycle.config.md template

- **Files**: `skills/lifecycle/assets/lifecycle.config.md`
- **What**: Insert a commented `demo-commands:` block immediately after the existing `# demo-command:` line (line 4). The block must include the commented header and a two-entry example showing `label:` + `command:` keys in YAML block-list format. This satisfies R1 and provides the schema reference implementers need.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Current file has `# demo-command:` at line 4. Insert the following 5-line block after it (all lines remain commented-out):
  ```
  # demo-commands:
  #   - label: "Godot gameplay"
  #     command: "godot res://main.tscn"
  #   - label: "FastAPI dashboard"
  #     command: "uv run fastapi run src/main.py"
  ```
  The YAML block-list format is intentional: inline-array style (`[{...}]`) was explicitly rejected in the spec in favor of multi-line block notation for readability.
- **Verification**:
  - `grep -c '^# demo-commands:' skills/lifecycle/assets/lifecycle.config.md` = 1
  - `grep -c 'label:' skills/lifecycle/assets/lifecycle.config.md` ≥ 2
  - `grep -c 'command:' skills/lifecycle/assets/lifecycle.config.md` ≥ 2
- **Status**: [x] complete

---

### Task 2: Rewrite Section 2a Guard 1 to route between `demo-commands:` list and `demo-command:` single-string paths

- **Files**: `skills/morning-review/references/walkthrough.md`
- **What**: Replace the current `### Guard 1 — \`demo-command\` is not configured` section (lines 86–104) with a new routing guard that checks `demo-commands:` first, falls back to `demo-command:` if absent/invalid, and skips Section 2a silently if neither is configured. All 7 parsing rules from R2 must be present in the new text as greppable phrases. Guard 2 (SSH check) must remain a shared gate between Guard 1 routing and Guard 3 — it is not inside either path branch.
- **Depends on**: none
- **Complexity**: complex
- **Context**:

  **Resulting Section 2a document structure**: After this task and Task 3 complete, Section 2a must have the following heading outline. Conditional framing prose (`If on the \`demo-commands:\` list path:`, or `**demo-commands: list path:**`, or a subheading like `#### demo-commands: list path`) is required before every path-conditional block — walkthrough.md has no runtime; a morning-review agent reads it linearly and must be told explicitly which blocks to skip. An implementation that puts two variants adjacently without framing prose produces a broken document that an agent will attempt to execute both of.

  ```
  ## Section 2a — Demo Setup

  ### Guard 1 — Route between demo-commands: list and demo-command: single-string paths
  [routing logic + parsing rules; determines which path is active]

  ### Guard 2 — remote session                       [shared; unchanged; between Guard 1 and Guard 3]
  [SSH check — applies to both paths]

  ### Guard 3 — overnight branch check               [shared; extended for demo-commands: path only]
  [check 1: overnight-state.json present + integration_branch set]
  [check 2: git rev-parse --verify {integration_branch} exits 0]
  [check 3: demo-commands: path only — zero merged features guard]

  [conditional framing] Agent Reasoning             [demo-commands: list path only]
  [conditional framing] Demo offer (list path)      [demo-commands: list path only]
  [conditional framing] Demo offer (single-string)  [demo-command: single-string path only]

  ### Worktree creation                              [shared; unchanged]
  [same git -c core.hooksPath=/dev/null worktree add command for both paths]

  [conditional framing] Print template (list path)        [demo-commands: list path, after worktree creation]
  [conditional framing] Print template (single-string)    [demo-command: single-string path, after worktree creation]

  ### Auto-advance                                   [unchanged]
  ### Security boundary                              [updated R7]
  ```

  **Guard 1 routing logic**:
  1. Read `lifecycle.config.md`. Scan for the first non-commented line that exactly matches `demo-commands:` (after stripping leading whitespace). If found, collect subsequent **indented lines** of the form `- label: "..."` / `command: "..."` as list entries, **stopping at the first non-indented, non-blank line** (parsing rule 2; this phrase must appear verbatim — it is an AC grep target).
  2. For each entry, extract `label:` and `command:` values using **first-colon extraction** (everything after the first `:` character, then trim; this phrase or "after the first" must appear — AC grep target). This phrase must appear for the `demo-commands:` path specifically (not only as legacy text from the `demo-command:` parser).
  3. Reject any entry whose `command:` contains a **control character** (byte < 0x20 except `\t`); silently discard (AC grep target; must appear for both paths in the new Guard 1).
  4. Reject any entry whose `command:` is empty/whitespace-only after trimming; silently discard. The phrase **"empty"** + **"command"** or **"whitespace-only"** must appear for both paths in the new Guard 1 (AC grep target).
  5. If **no valid entries** remain, fall through to `demo-command:` check. The phrase "no valid entries" or "fall.*through.*demo-command" must appear (AC grep target).
  6. Do NOT strip **inline `#` comments** from `command:` values (AC grep target; must appear for both paths in the new Guard 1).
  7. If at least one valid entry exists → active path is `demo-commands:` list. Proceed to Guard 2 then Guard 3, then the demo-commands: flow.

  **Guard 1 fallback** (demo-command: single-string): if `demo-commands:` was absent or had no valid entries, apply the existing 6-rule parser for `demo-command:`. If a non-empty value is found → active path is `demo-command:` single-string. Proceed to Guard 2, then Guard 3, then the existing single-string flow. If neither path is active, skip Section 2a silently.

  **Guard 2 preservation**: Guard 2 (`### Guard 2 — remote session`) currently at lines 106–108 must remain as a shared guard between Guard 1 routing and Guard 3. Do NOT move Guard 2 into either path branch. It applies to both paths unconditionally. Guard 2's text is unchanged.

  Preserve the existing implementer note about `sed` and `awk -F:` in the `demo-command:` path parsing rules — it is still load-bearing for the single-string path.

- **Verification**:
  - `grep -c 'demo-commands:' skills/morning-review/references/walkthrough.md` ≥ 1
  - `grep -Pc 'first.*colon|after the first' skills/morning-review/references/walkthrough.md` ≥ 2 (Task 2 replaces lines 86–104, removing the pre-existing match at line 99; new Guard 1 must have this phrase for both paths)
  - `grep -c 'control character' skills/morning-review/references/walkthrough.md` ≥ 4 (Task 2 replaces lines 86–104, removing old matches at lines 93 and 100; 2 outside-Guard-1 matches survive; new Guard 1 must add 2 new mentions for both paths to reach ≥ 4)
  - `grep -Pc 'inline.*comments|inline.*#' skills/morning-review/references/walkthrough.md` ≥ 2 (Task 2 replaces line 102; new Guard 1 must have this phrase for both paths)
  - `grep -Pc 'non-indented|indented.*entries|stop.*non-indented' skills/morning-review/references/walkthrough.md` ≥ 1
  - `grep -Pc 'empty.*command|command.*empty|whitespace-only' skills/morning-review/references/walkthrough.md` ≥ 2 (Task 2 replaces line 92; new Guard 1 must have this phrase for both paths)
  - `grep -Pc 'no valid entries|fall.*through.*demo-command|fall.*back.*demo-command' skills/morning-review/references/walkthrough.md` ≥ 1
- **Status**: [x] complete

---

### Task 3: Add `demo-commands:` path behavior to Section 2a — Guard 3 extension, agent reasoning, demo offer, print template, and security boundary

- **Files**: `skills/morning-review/references/walkthrough.md`
- **What**: Extend Guard 3 with a zero-merged-features check (R3), insert a new Agent Reasoning subsection (R4), restructure the Demo offer section into two path-conditional variants (R5), add a `demo-commands:`-path print template after worktree creation (R6), and update the security boundary language (R7). All path-conditional sections require explicit conditional framing prose per the Section 2a structure defined in Task 2's Context.
- **Depends on**: [2]
- **Complexity**: complex
- **Context**:
  - **Guard 3 extension (R3)**: Guard 3 (find it by its heading after Task 2 rewrites Guard 1) checks overnight branch existence. Guard 3 has exactly two existing conditions: (1) `overnight-state.json` missing or `integration_branch` absent → skip; (2) `git rev-parse --verify {integration_branch}` exits non-zero → skip. When the `demo-commands:` list path is active, add a **third check after these existing two within Guard 3**: read the `features` map from `lifecycle/sessions/latest-overnight/overnight-state.json`; if no entries have `"status": "merged"` (zero merged features), skip Section 2a silently. The phrase `"status".*merged` or `status.*merged` must appear in the text (AC grep target), as must `zero.*features`, `no.*merged`, or `no completed features` (AC grep target). If `overnight-state.json` is missing the `features` key, treat as zero merged features. Clearly frame this third check as applying **only to the `demo-commands:` list path**.

  - **Agent Reasoning section (R4)**: Add an Agent Reasoning block, clearly framed with conditional prose such as "**If on the `demo-commands:` list path and all guards pass:**". Place it after Guard 3 and before the Demo offer section. The block must specify: (1) no additional git commands are run — the input is the completed-features list with **Key files changed** data already in context from Section 2 (the phrase "Key files changed" must appear here — it already appears in Section 2, making the total count ≥ 2 across the file for the AC); (2) reason about which `demo-commands:` entry label is most contextually relevant; (3) if a clear winner exists, proceed to the demo offer for the `demo-commands:` path; (4) if none is clearly relevant, **skip Section 2a silently** — this suppression is absolute and applies even if `demo-command:` is also configured in the same `lifecycle.config.md`; the fallback to `demo-command:` does NOT fire when the `demo-commands:` list path is active. The phrase "no additional git" or "already in context" or "already processed" must appear (AC grep target).

  - **Demo offer restructure (R5)**: The current `### Demo offer` section (find it by heading) has one generic offer blockquote. Restructure it into **two path-conditional variants**, both under the same `### Demo offer` heading (or replace it with two labeled sub-blocks). Each variant must have explicit conditional framing that tells a linear-reading agent which one to use:
    - `demo-commands:` list path variant (conditional framing required): if Agent Reasoning selected an entry, offer `Run \`{selected-label}\` demo (\`{selected-command}\`) from \`{integration_branch}\` in a fresh worktree? [y / n]`. Paraphrasing is acceptable; `{selected-label}` and `{selected-command}` must appear verbatim (AC grep targets).
    - `demo-command:` single-string path variant (conditional framing required): existing offer text is **preserved unchanged** ("Spin up a demo worktree of `{integration_branch}`…").
    - For both variants: on `n` or unparseable input, advance to Section 2b; on `y`, proceed to worktree creation (shared, unchanged).

  - **Print template (R6)**: The current `### Print template` section (find it by heading) uses `{demo-command}`. Add a `demo-commands:` path variant. **Both the new variant and the existing variant must come after the Worktree creation section** — print templates reference `{resolved-target-path}` which is produced by worktree creation. Place the `demo-commands:` variant with explicit conditional framing **after** the existing `{demo-command}` template, or structure both as labeled sub-blocks within the same section. The `demo-commands:` variant must contain the exact phrase `To start the demo ({selected-label})` and reference `{selected-command}` (both are AC grep targets). Template structure per spec R6:
    ```
    Demo worktree created at: {resolved-target-path}

    To start the demo ({selected-label}), run this in a separate terminal or shell:
        {selected-command}

    When you're done, close the demo and remove the worktree:
        git worktree remove {resolved-target-path}
    ```
    The `demo-command:` single-string path print template (`{demo-command}`) is preserved unchanged.

  - **Security boundary (R7)**: Update the `### Security boundary` section (find it by heading). Current text: "The agent MUST NOT execute the demo-command itself; it is printed for the user to run manually in a separate terminal session." New text must read: "The agent MUST NOT execute the **selected command** (or the `demo-command:` value) itself; it is printed for the user to run manually in a separate terminal session." The phrase `selected command` or `selected.*demo` must appear (AC grep target).

- **Verification**:
  - `grep -Pc '"status".*merged|status.*merged' skills/morning-review/references/walkthrough.md` ≥ 1
  - `grep -Pc 'zero.*features|no.*merged|no completed features' skills/morning-review/references/walkthrough.md` ≥ 1
  - `grep -c 'Key files changed' skills/morning-review/references/walkthrough.md` ≥ 2
  - `grep -Pc 'no additional git|already in context|already processed' skills/morning-review/references/walkthrough.md` ≥ 1
  - `grep -c '{selected-label}' skills/morning-review/references/walkthrough.md` ≥ 1
  - `grep -c '{selected-command}' skills/morning-review/references/walkthrough.md` ≥ 1
  - `grep -c 'To start the demo ({selected-label})' skills/morning-review/references/walkthrough.md` ≥ 1
  - `grep -Pc 'selected command|selected.*demo' skills/morning-review/references/walkthrough.md` ≥ 1
- **Status**: [x] complete

---

### Task 4: Add `demo-commands:` edge case rows to the Edge Cases table

- **Files**: `skills/morning-review/references/walkthrough.md`
- **What**: Append six new rows to the Edge Cases table (find it by the `## Edge Cases` heading) covering `demo-commands:` scenarios from the spec's Edge Cases section. This ensures agents handling edge conditions have explicit guidance, matching the existing table style.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: Append these rows to the Edge Cases table (pipe-delimited, two columns: Situation | Action):
  - `demo-commands:` present but all entries rejected (control chars / empty command) → fall through to `demo-command:` single-string check
  - `demo-commands:` and `demo-command:` both configured → `demo-commands:` takes precedence; `demo-command:` is ignored on this path
  - Single entry in `demo-commands:` → agent may still reason "none relevant" and skip silently; one entry does not guarantee an offer
  - Zero features with `"status": "merged"` in `overnight-state.json` → Guard 3 zero-merged check fires; skip Section 2a silently
  - `overnight-state.json` missing `features` key (older state format) → treat as zero merged features; skip Section 2a silently
  - Section 2 context showed features but agent has poor context on what they changed → agent selects "none relevant" and skips silently; correct graceful degradation
- **Verification**:
  - `grep -c 'demo-commands' skills/morning-review/references/walkthrough.md` ≥ 5 (table rows + Guard 1 + Agent Reasoning = several occurrences)
  - `grep -c 'none relevant' skills/morning-review/references/walkthrough.md` ≥ 1
- **Status**: [x] complete

---

### Task 5: Update SKILL.md Step 3 item 2 to reference `demo-commands:` list and agent-reasoned selection

- **Files**: `skills/morning-review/SKILL.md`
- **What**: Update the "Demo Setup" bullet in Step 3 (line 102) to reference `demo-commands:` list and agent-reasoned selection, replacing the current reference to `demo-command` only. The existing `demo-command` reference must be replaced or supplemented.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Current text (line 102): `2. **Demo Setup** — if \`demo-command\` is configured and the session is local, offer to spin up a demo worktree from the overnight branch.`
  New text must reference `demo-commands:` list and agent-reasoned selection. Example: `2. **Demo Setup** — if \`demo-commands:\` (list) or \`demo-command:\` (single string) is configured and the session is local, offer to spin up a demo worktree from the overnight branch; for \`demo-commands:\`, the agent reasons from Section 2 context to select the most relevant entry (or skips if none is relevant).`
  The exact phrasing is flexible — the AC only requires at least one mention of `demo-commands` in the file.
- **Verification**:
  - `grep -c 'demo-commands' skills/morning-review/SKILL.md` ≥ 1
- **Status**: [x] complete

---

### Task 6: Update docs/overnight.md to document `demo-commands:` list schema

- **Files**: `docs/overnight.md`
- **What**: Update lines 52 and 65 of `docs/overnight.md` to document the `demo-commands:` list schema alongside the existing `demo-command:` string field. The YAML example block and the "Other fields" prose both need updating.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Line 52 (YAML example): Add a commented `demo-commands:` block below `# demo-command:`. Match the same comment style and example format added to `skills/lifecycle/assets/lifecycle.config.md` in Task 1.
  - Line 65 (prose description): The `demo-command` bullet must be updated to also document `demo-commands:` list behavior. The updated bullet should explain: when `demo-commands:` is configured with a list of `label:` / `command:` entries, the morning-review agent reasons from the completed-feature context (Section 2 "Key files changed") to select the most relevant entry and offer it; if none is relevant, the section is skipped silently. The `demo-command:` single-string behavior is unchanged. The phrase `demo-commands:` must appear in the file after the edit (AC grep target).
- **Verification**:
  - `grep -c 'demo-commands:' docs/overnight.md` ≥ 1
- **Status**: [x] complete

---

## Verification Strategy

After all tasks complete, run the full spec AC battery in order. All `grep -c` checks must return ≥ the stated threshold:

```bash
# R1
grep -c '^# demo-commands:' skills/lifecycle/assets/lifecycle.config.md
grep -c 'label:' skills/lifecycle/assets/lifecycle.config.md
grep -c 'command:' skills/lifecycle/assets/lifecycle.config.md

# R2
grep -c 'demo-commands:' skills/morning-review/references/walkthrough.md
grep -Pc 'first.*colon|after the first' skills/morning-review/references/walkthrough.md  # ≥ 2
grep -c 'control character' skills/morning-review/references/walkthrough.md              # ≥ 4
grep -Pc 'inline.*comments|inline.*#' skills/morning-review/references/walkthrough.md   # ≥ 2
grep -Pc 'non-indented|indented.*entries|stop.*non-indented' skills/morning-review/references/walkthrough.md
grep -Pc 'empty.*command|command.*empty|whitespace-only' skills/morning-review/references/walkthrough.md  # ≥ 2
grep -Pc 'no valid entries|fall.*through.*demo-command|fall.*back.*demo-command' skills/morning-review/references/walkthrough.md

# R3
grep -Pc '"status".*merged|status.*merged' skills/morning-review/references/walkthrough.md
grep -Pc 'zero.*features|no.*merged|no completed features' skills/morning-review/references/walkthrough.md

# R4
grep -c 'Key files changed' skills/morning-review/references/walkthrough.md  # ≥ 2
grep -Pc 'no additional git|already in context|already processed' skills/morning-review/references/walkthrough.md

# R5
grep -c '{selected-label}' skills/morning-review/references/walkthrough.md
grep -c '{selected-command}' skills/morning-review/references/walkthrough.md

# R6
grep -c 'To start the demo ({selected-label})' skills/morning-review/references/walkthrough.md
grep -c '{selected-command}' skills/morning-review/references/walkthrough.md

# R7
grep -Pc 'selected command|selected.*demo' skills/morning-review/references/walkthrough.md

# R8
grep -c 'demo-commands' skills/morning-review/SKILL.md

# R9
grep -c 'demo-commands:' docs/overnight.md
```

End-to-end behavioral verification is interactive/session-dependent (R4 selection quality is untestable mechanically — confirmed in spec). The structural contract — at most one offer from the configured list, from a session where merged features exist, auto-advancing — is verified by the grep battery above.

## Veto Surface

- **Walkthrough restructuring approach**: Tasks 2 and 3 rewrite Section 2a in two sequential passes. An alternative would be one large task rewriting the whole section atomically. Splitting is chosen to keep each task bounded; the dependency chain (Task 3 reads Task 2's output) prevents conflicts.
- **Demo offer as two labeled sub-blocks (not two separate sections)**: Task 3 restructures the existing Demo offer section into two path-conditional variants rather than adding a separate `### Demo offer (demo-commands: path)` heading. This keeps the section count stable and avoids heading proliferation; path framing is enforced via conditional prose or labeled sub-blocks within the existing section.
- **Guard 3 extension placement**: The zero-merged-features check is added as a third condition within the existing Guard 3 block rather than as a separate Guard 3b. This keeps the guard count stable and aligns with spec language ("extend Guard 3").

## Scope Boundaries

Per spec Non-Requirements:
- **NR4**: No changes to `runner.sh`, `parser.py`, `batch_runner.py`, or any overnight pipeline component
- **NR5**: No new shared YAML parser module — parsing is inline skill text
- **NR6**: No additional `git diff` or file reads in Section 2a — selection uses Section 2 context only
- **NR2**: No per-entry `areas:`, `paths:`, or `tags:` hints added to the config schema
- **NR3**: No fallback from `demo-commands:` "none selected" to `demo-command:` — when the list path is active and agent reasoning skips, Section 2a skips silently even if `demo-command:` is also configured
