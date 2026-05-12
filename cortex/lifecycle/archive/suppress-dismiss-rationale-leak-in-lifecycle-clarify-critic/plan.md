# Plan: suppress-dismiss-rationale-leak-in-lifecycle-clarify-critic

## Overview

All edits land in a single file: `skills/lifecycle/references/clarify-critic.md`. Tasks are serialized via `Depends on` chains because every edit touches the same file. Task ordering places schema edits first (so later tasks can reference the schema field that's now present), then the output-contract subsection, then prose narrowing, then the YAML example, then failure handling, then the constraints row, then a final integration-verification gate.

**All tasks run from the repo root** (`/Users/charlie.hall/Workspaces/cortex-command`). Every `grep`/`awk`/`diff`/`sed` command assumes CWD = repo root.

**Locate edits by content anchor, not line number.** Line numbers cited in task Context reflect the file's state at plan-write time; subsequent tasks shift those numbers. Implementers should use string matching (the quoted existing text) to locate edit sites.

**Verification precedence**: If a verification grep in this plan diverges from the matching spec acceptance, the plan's grep is authoritative — the plan corrects several regex defects inherited from the spec (awk range boundaries, escape handling, order sensitivity).

## Tasks

### Task 1: Extend `clarify_critic` event schema with `dismissals` field [x]

- **Files**: `skills/lifecycle/references/clarify-critic.md`
- **What**: Satisfies spec R1. Adds one line (`dismissals: <array of {finding_index, rationale} objects — one per Dismiss disposition>`) to the schema fenced block under "Required fields:", and documents the new field in the prose paragraph immediately following the schema block.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Anchor: find the line beginning with `applied_fixes:` inside the fenced block under "Required fields:" (currently around line 102). Insert `dismissals: <array of {finding_index, rationale} objects — one per Dismiss disposition>` on the following line, before `status: "ok"`.
  - Match existing schema-descriptor style: `findings: <array of prose strings — one per critic objection>` / `applied_fixes: <array of strings describing changes made to the confidence assessment>`.
  - Prose paragraph to extend: the sentence immediately following the schema block's closing fence currently reads: ``` `applied_fixes` contains descriptions of the changes the orchestrator made to the confidence assessment as a result of Apply dispositions. If no Apply dispositions were made, `applied_fixes` is an empty array. ```
  - Add a parallel sentence documenting `dismissals`: each entry is `{finding_index: <int>, rationale: <prose>}`; `finding_index` points into the `findings` array; when zero Dismiss dispositions occur, `dismissals` is an empty array.
- **Verification**:
  - Schema block contains `dismissals:` at column 0 within the block (not in any other block):
    `grep -A 15 "^Required fields:$" skills/lifecycle/references/clarify-critic.md | grep -c "^dismissals:"` = 1. Pass if count = 1.
  - Prose paragraph after the schema block (and before the YAML example) documents `dismissals`:
    `grep -A 30 "^Required fields:$" skills/lifecycle/references/clarify-critic.md | grep -c "dismissals"` ≥ 3 (one in schema line, at least two in prose references). Pass if count ≥ 3.
- **Status**: [x] complete

### Task 2: Add "Dispositioning Output Contract" subsection to Disposition Framework; remove Dismiss-line trailing sentence [x]

- **Files**: `skills/lifecycle/references/clarify-critic.md`
- **What**: Satisfies spec R2. Removes the sentence "State the dismissal reason briefly." from the Dismiss disposition body (currently line 73 area) and adds a new `### Dispositioning Output Contract` subsection before the `## Ask-to-Q&A Merge Rule` heading.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Anchor for removal: find the line containing `**Dismiss**` in the Disposition Framework section. Remove only the final sentence " State the dismissal reason briefly." — keep the rest of the Dismiss definition intact.
  - Anchor for insertion: insert a new `### Dispositioning Output Contract` subsection immediately before the heading `## Ask-to-Q&A Merge Rule`. The subsection body must contain **four distinct bullet points** (not paragraph prose) covering:
    1. "Sole output" clause: the dispositioning step's sole output is a YAML artifact matching the `clarify_critic` events.log schema (including the `dismissals` field added in Task 1).
    2. "Verbatim write" clause: the orchestrator writes this YAML verbatim to `lifecycle/{feature}/events.log` as the `clarify_critic` event.
    3. "User-facing scope" clause: the user-facing response following the dispositioning step is scoped to (a) the §4 Ask-merge invocation (per Ask-to-Q&A Merge Rule), and (b) silent application of Apply dispositions to the confidence assessment.
    4. "Dismiss-rationale placement" clause: Dismiss rationales appear only in the YAML's `dismissals[].rationale` field — not in the user-facing response surface.
  - Target length: 6–12 lines total (bullets + any brief intro). Keep positive, direct prose; avoid "do not X" phrasings.
- **Verification**:
  - Dismiss trailing sentence is gone:
    `grep -c "State the dismissal reason briefly" skills/lifecycle/references/clarify-critic.md` = 0. Pass if count = 0.
  - Subsection heading is present inside Disposition Framework:
    `awk '/^## Disposition Framework/,/^## Ask-to-Q\&A Merge Rule/' skills/lifecycle/references/clarify-critic.md | grep -cE "^### Dispositioning Output Contract"` = 1. Pass if count = 1.
  - Four bullets each present (4 separate `grep -F` checks — order-independent; each passes independently):
    - `grep -cF "sole output" skills/lifecycle/references/clarify-critic.md` ≥ 1. Pass if count ≥ 1.
    - `grep -cF "verbatim" skills/lifecycle/references/clarify-critic.md` ≥ 1. Pass if count ≥ 1.
    - `grep -cE "§4 Ask|Ask-merge|Ask.{0,20}merge" skills/lifecycle/references/clarify-critic.md` ≥ 1. Pass if count ≥ 1.
    - `grep -cF "dismissals[].rationale" skills/lifecycle/references/clarify-critic.md` ≥ 1. Pass if count ≥ 1.
- **Status**: [x] complete

### Task 3: Narrow `applied_fixes` semantics; add Ask→Dismiss reclassification handling

- **Files**: `skills/lifecycle/references/clarify-critic.md`
- **What**: Satisfies spec R4. Deletes the unqualified phrase "fixes from both initial Apply dispositions and self-resolution reclassifications"; replaces it with (a) a sentence scoped to Ask→Apply reclassification landing in `applied_fixes`, and (b) a parallel sentence for Ask→Dismiss reclassification landing in `dismissals[].rationale`.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Anchor (removal): find the sentence beginning with "The `applied_fixes` array includes fixes from both initial Apply dispositions" (currently line 108 area). The specific phrase "fixes from both initial Apply dispositions and self-resolution reclassifications" must be absent from the file after the edit.
  - Anchor (retention): the preceding sentence "Disposition counts reflect post-self-resolution values." stays unchanged.
  - Anchor (Ask→Apply scoping): the existing sentence "If self-resolution reclassifies an Ask item as Apply, the logged `apply` count increases and `ask` count decreases accordingly." stays unchanged.
  - Required new content (Ask→Apply continuation): a sentence stating that `applied_fixes` is populated by both initial Apply dispositions and Ask→Apply reclassifications specifically (narrowing — not generic reclassifications).
  - Required new content (Ask→Dismiss parallel): a sentence stating that when self-resolution reclassifies an Ask item as Dismiss, the rationale lands in `dismissals[].rationale` (not `applied_fixes`); `dispositions.ask` decreases and `dispositions.dismiss` increases accordingly.
  - Required new content (field contrast — spec R4 acceptance #4): a sentence contrasting `dismissals` with `applied_fixes`, e.g. "The `dismissals` array is the Dismiss-disposition counterpart to `applied_fixes`."
- **Verification**:
  - Old unqualified phrase removed (literal):
    `grep -cF "fixes from both initial Apply dispositions and self-resolution reclassifications" skills/lifecycle/references/clarify-critic.md` = 0. Pass if count = 0.
  - Ask→Apply path explicitly scoped (two fixed substrings must both be present):
    `grep -cF "Ask" skills/lifecycle/references/clarify-critic.md` ≥ 1 AND `grep -cF "Apply" skills/lifecycle/references/clarify-critic.md` ≥ 1 AND `grep -cE "Ask.{0,80}Apply.{0,80}applied_fixes|applied_fixes.{0,80}Ask.{0,80}Apply" skills/lifecycle/references/clarify-critic.md` ≥ 1. Pass if all three hold.
  - Ask→Dismiss rationale routing documented (two alternative phrasings accepted):
    `grep -cE "dismissals\\[\\]\\.rationale|dismissals\\[\\]\\.rationale" skills/lifecycle/references/clarify-critic.md` ≥ 1 AND `grep -cE "Ask.{0,80}Dismiss|Dismiss.{0,80}Ask" skills/lifecycle/references/clarify-critic.md` ≥ 1. Pass if both hold. (This pair is order-independent — either direction between Ask and Dismiss in the sentence passes, as long as `dismissals[].rationale` appears somewhere in the file.)
  - Field contrast documented (spec R4 #4):
    `grep -cE "dismissals.{0,60}applied_fixes|applied_fixes.{0,60}dismissals" skills/lifecycle/references/clarify-critic.md` ≥ 1. Pass if count ≥ 1.
- **Status**: [x] complete

### Task 4: Update YAML example — demonstrate initial Dismiss + Ask→Dismiss reclassification

- **Files**: `skills/lifecycle/references/clarify-critic.md`
- **What**: Satisfies spec R5. Rewrites the existing `` ```yaml `` fenced example block (currently line 112 area) so that `dispositions.dismiss` equals 2, `dismissals:` contains 2 entries (one initial-Dismiss, one Ask→Dismiss reclassification, distinguished by YAML comments), and counts are internally consistent.
- **Depends on**: [1, 3]
- **Complexity**: simple
- **Context**:
  - Anchor: the `` ```yaml `` fence line (currently line 112 area). The existing block has `dispositions.dismiss: 0` and no `dismissals` entries — both change.
  - Required changes inside the block (keep 2-space indent, existing top-level keys `ts/event/feature/findings/dispositions/applied_fixes/dismissals/status`):
    - `findings`: add at least 2 findings (enough to be referenced by `finding_index`).
    - `dispositions.dismiss`: exactly 2.
    - `dismissals`: exactly 2 entries, each `{finding_index: <int>, rationale: <prose>}`.
    - YAML comments on the two dismissals entries distinguishing them — e.g. `# initial Dismiss disposition` and `# Ask→Dismiss self-resolution reclassification`. Comment wording is flexible; the verification checks for the presence of both substrings "initial" and "reclassif" somewhere inside the YAML block.
    - Other counts (`apply`, `ask`) and `applied_fixes` may be set to any consistent scenario.
- **Verification**:
  - `dismissals:` key appears inside the YAML block:
    `awk '/^```yaml/,/^```$/' skills/lifecycle/references/clarify-critic.md | grep -cE "^[[:space:]]+dismissals:"` ≥ 1. Pass if count ≥ 1.
  - At least 2 `finding_index:` entries inside the YAML block:
    `awk '/^```yaml/,/^```$/' skills/lifecycle/references/clarify-critic.md | grep -cE "^[[:space:]]+- finding_index:|^[[:space:]]+finding_index:"` ≥ 2. Pass if count ≥ 2.
  - `dismiss: 2` matches inside the YAML block (matches the spec's "Pass if the grep matches" criterion):
    `awk '/^```yaml/,/^```$/' skills/lifecycle/references/clarify-critic.md | grep -cE "^[[:space:]]+dismiss: 2"` ≥ 1. Pass if count ≥ 1.
  - Both "initial" and "reclassif" substrings appear as YAML comments or prose within the block (enforces the distinguishing-comment requirement):
    `awk '/^```yaml/,/^```$/' skills/lifecycle/references/clarify-critic.md | grep -cF "initial"` ≥ 1 AND `awk '/^```yaml/,/^```$/' skills/lifecycle/references/clarify-critic.md | grep -cF "reclassif"` ≥ 1. Pass if both hold.
- **Status**: [x] complete

### Task 5: Extend Failure Handling with `dismissals` in empty-payload list

- **Files**: `skills/lifecycle/references/clarify-critic.md`
- **What**: Satisfies spec R6. Adds `dismissals` to the empty-list enumeration in the Failure Handling section so the failure-path event payload shape remains consistent with the success-path shape.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Anchor: the sentence in `## Failure Handling` that currently enumerates `findings`, `applied_fixes`, and `dispositions` on the failure path (currently line 132 area). Exact current text: ``` Write a `clarify_critic` event with `status: "failed"` and empty `findings`, `applied_fixes`, and zero counts in `dispositions`. ```
  - Required edit: extend the empty-enumeration to include `dismissals`. Natural phrasing: ``` Write a `clarify_critic` event with `status: "failed"` and empty `findings`, `applied_fixes`, `dismissals`, and zero counts in `dispositions`. ```
- **Verification**:
  - `dismissals` appears within the Failure Handling section in an empty-context phrasing:
    `awk '/^## Failure Handling/,/^## [^F]/' skills/lifecycle/references/clarify-critic.md | grep -cE "empty.{0,80}dismissals|dismissals.{0,80}empty|dismissals:[[:space:]]*\\[\\]"` ≥ 1. Pass if count ≥ 1. (Order-insensitive around "empty" and "dismissals" to accept any natural phrasing.)
- **Status**: [x] complete

### Task 6: Add Constraints-table row governing Dismiss-rationale routing

- **Files**: `skills/lifecycle/references/clarify-critic.md`
- **What**: Satisfies spec R7. Adds one row to the Constraints table (at the end of the file, starting line 137 area) in `| Thought | Reality |` format. The Reality cell must contain both `dismissals` and `events.log`.
- **Depends on**: [5]
- **Complexity**: simple
- **Context**:
  - Anchor: the Constraints table (pipe-delimited markdown table under `## Constraints`). Append a new row after the existing rows (before end-of-file if no trailing content).
  - Row shape: `| <Thought cell describing the misconception> | <Reality cell naming dismissals and events.log> |`
  - Example (wording flexible but must satisfy the grep): `| "Surface Dismiss rationales to the user so they can see the critic's work" | Dismiss rationales go to the `dismissals` array in `events.log` only; user-facing response is reserved for Ask merge + Apply confidence revisions. |`
  - Important: both `dismissals` and `events.log` must appear in the Reality cell (right of the second `|`), and `dismissals` must appear before `events.log` within that cell. If the natural wording places `events.log` first, restructure the sentence to put `dismissals` first (e.g., "The `dismissals` array in `events.log` …").
- **Verification**:
  - Table-row format with both substrings in the Reality cell, `dismissals` before `events.log`:
    `awk '/^## Constraints/,0' skills/lifecycle/references/clarify-critic.md | grep -cE '^\|.*[Dd]ismiss.*\|.*dismissals.*events\.log'` ≥ 1. Pass if count ≥ 1.
  - Corrected vs spec: spec uses `(dismissal\|Dismiss)` with escaped pipe which makes alternation fail; this plan uses `[Dd]ismiss` which captures both cases without escape issues.
- **Status**: [x] complete

### Task 7: Integration verification — preserved Ask paths, untouched `clarify.md`, downstream audit

- **Files**: (read-only verification; no writes)
  - `skills/lifecycle/references/clarify-critic.md` (read)
  - `skills/lifecycle/references/clarify.md` (read; compared to branch-base commit)
  - `bin/`, `retros/`, `hooks/`, `claude/`, `skills/`, `docs/`, `tests/`, `requirements/`, `lifecycle/` (grep audit)
- **What**: Satisfies spec R3 (Ask-path preservation verbatim), R8 (downstream-consumer audit), R9 (`clarify.md` untouched). Final integration gate.
- **Depends on**: [1, 2, 3, 4, 5, 6]
- **Complexity**: simple
- **Context**:
  - R3: confirm specific sentences survived the earlier edits verbatim.
  - R8: scan for any consumer of the `clarify_critic` event schema that the earlier audit might have missed. The audit includes `requirements/` and `lifecycle/` top-level (extensions: `.py`, `.sh`, `.md`, `.json`, `.yaml`, `.yml`, `.toml`, `.js`, `.ts`). Exclusions via grep-vE: `skills/lifecycle/references/clarify(-critic)?\.md` (the files we edited), this ticket's own lifecycle directory (`lifecycle/archive/suppress-dismiss-rationale-leak-in-lifecycle-clarify-critic/`), the epic research directory (`research/audit-interactive-phase-output-for-decision-signal/`), and any other lifecycle directory's artifact files (`lifecycle/*/(events.log|research.md|spec.md|plan.md|review.md|implementation.md)`).
  - R9: diff `clarify.md` against the branch base (the commit **before** the first Task 1–6 commit), not `HEAD`. Because by T7's execution, HEAD already includes Task 1–6 commits. Use `git merge-base HEAD main` to find the branch base.
  - **CWD**: all commands assume repo root as CWD.
- **Verification**:
  - R3 Ask-to-Q&A Merge Rule sentence preserved verbatim:
    `grep -cF "Ask items from the critic are **not** presented as a blocking escalation separate from §4" skills/lifecycle/references/clarify-critic.md` ≥ 1. Pass if count ≥ 1.
  - R3 Ask disposition sentence preserved verbatim:
    `grep -cF "the fix is not for the orchestrator to decide unilaterally" skills/lifecycle/references/clarify-critic.md` = 1. Pass if count = 1.
  - R8 downstream audit (explicit CWD assumption: repo root):
    `cd "$(git rev-parse --show-toplevel)" && grep -rn "clarify_critic" bin/ retros/ hooks/ claude/ skills/ docs/ tests/ requirements/ lifecycle/ --include='*.py' --include='*.sh' --include='*.md' --include='*.json' --include='*.yaml' --include='*.yml' --include='*.toml' --include='*.js' --include='*.ts' 2>/dev/null | grep -vE "skills/lifecycle/references/clarify(-critic)?\\.md:|lifecycle/[^/]+/(events\\.log|research\\.md|spec\\.md|plan\\.md|review\\.md|implementation\\.md):|research/audit-interactive-phase-output-for-decision-signal/|lifecycle/archive/suppress-dismiss-rationale-leak-in-lifecycle-clarify-critic/" | wc -l` = 0. Pass if count = 0.
    (Note: `:` after the filename in the exclusion anchors matches the grep -rn output format `path:lineno:match`, so the exclusion fires correctly regardless of match content.)
  - R9 `clarify.md` unchanged vs. branch base (not HEAD — HEAD includes Task 1–6 commits by this point):
    `BASE=$(git merge-base HEAD main) && diff <(git show $BASE:skills/lifecycle/references/clarify.md) skills/lifecycle/references/clarify.md` produces no output. Pass if diff is empty.
- **Status**: [x] complete

## Verification Strategy

End-to-end verification after all 7 tasks complete:

1. **All per-task verifications pass**: run every task's Verification block; all return their expected pass counts.
2. **Spec-level end-to-end re-run**: run the full acceptance-grep chain from `spec.md` (with the plan's corrected greps where they differ — see note under Overview). All pass = feature correctly implemented.
3. **Behavioral sanity**: manually invoke `/lifecycle` against any small backlog item. Inspect the resulting `clarify_critic` event in `lifecycle/*/events.log`; confirm `dismissals` array is present (`[]` on zero dispositions, populated with `{finding_index, rationale}` entries otherwise). Confirm no Dismiss-rationale prose appears in the user-facing conversation response.
4. **Regression sweep**: over the next few lifecycle features, watch for user-visible Dismiss-rationale leaks; if any appear, the structural output-contract approach may need the full Option-2 (subagent-boundary) redesign.

## Veto Surface

- **Design principle (Alt B')**: scope-bounded structural output contract over Alt B (schema + negative instruction), full Option 2 (subagent boundary), or Alt D (eliminate entirely). Revisit if the leak persists — subagent-boundary redesign is the next structural step.
- **#067 coupling**: line-69 parenthetical carve-out is explicitly dropped from this ticket and deferred to whichever of #067/#068 ships second.
- **Invariant enforcement**: `len(dismissals) == dispositions.dismiss` and the `finding_index` bounds are textual only. A future JSONL validator is a potential follow-up.
- **Schema versioning**: not introduced. May become necessary if strict parsers emerge (dashboard, metrics).
- **Spec-plan grep divergences**: the plan corrects several regex defects inherited from the spec (awk range boundaries, escape handling, order sensitivity). The plan's grep is authoritative during implementation. If this causes confusion later, a follow-up could re-synchronize the spec's acceptance text.

## Scope Boundaries

Mirrors spec Non-Requirements:

- No modification to `skills/lifecycle/references/clarify.md` (pure delegation preserved; R9 enforces)
- No modification to `skills/critical-review/SKILL.md` (sibling #067's scope)
- No JSONL schema validator (potential follow-up)
- No user-facing "expand dispositions" command
- No rewrite of the three-disposition framework (Apply/Dismiss/Ask preserved)
- No backfill of past events.log entries (additive, forward-only)
- No dispositioning subagent boundary (Option 2 full redesign out of scope)
- No update to `clarify-critic.md:69` drift-avoidance parenthetical (coupled to #067)
