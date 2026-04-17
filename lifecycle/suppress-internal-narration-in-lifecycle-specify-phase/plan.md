# Plan: suppress-internal-narration-in-lifecycle-specify-phase

## Overview

Edit two lifecycle skill-reference files (`skills/lifecycle/references/specify.md` and `skills/lifecycle/references/orchestrator-review.md`) across five surface-specific tasks plus one end-to-end verification sweep. Tasks T1–T3 hit specify.md; T4–T5 hit orchestrator-review.md. All edits target disjoint, heading-anchored regions, so the `Edit` tool (which matches on `old_string`, not line numbers) makes concurrent edits mechanically safe. The `Depends on` chain (T2 [1], T3 [2], T5 [4]) is a **defensive serialization** against the implement-phase pipeline's dispatch semantics — not a data dependency — because two concurrent Edit calls on the same file could race if the pipeline dispatches tasks without a per-file mutex. The `Depends on` field is the only available lever to express "don't run these concurrently on the same file," so it does double duty here. Verifications use the spec's grep/awk acceptance commands directly. Per P7's operational test, these greps are benign self-checks: each edit task's primary deliverable is the edit, and the grep asserts the edit's structural shape (not a side-channel audit artifact).

## Tasks

### Task 1: Edit §2a clean-pass directive (R1)

- **Files**: `skills/lifecycle/references/specify.md`
- **What**: Amend the clean-pass directive at line 55 so the pass path is structurally silent by directive, not emergent. Append a "Do not emit" clause after the existing "No event is logged" sentence.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Current line 55: `**If all three signals pass**: proceed to §3. No event is logged.`
  - Invariant the edit must establish (the grep is the binding constraint): the file must match the regex `proceed to §3\. No event is logged\. Do not (emit|announce|surface)` at least once. Any phrasing that satisfies this regex is acceptable.
  - Example phrasing (illustrative only): `**If all three signals pass**: proceed to §3. No event is logged. Do not emit any acknowledgment to the user.`
  - No `confidence_check` pass event is added (preserves invariant; cycle counting at line 57 unchanged).
  - Editing tool: `Edit` with `old_string`/`new_string` for precise replacement.
- **Verification**: `grep -cE 'proceed to §3\. No event is logged\. Do not (emit|announce|surface)' skills/lifecycle/references/specify.md` — pass if count ≥ 1.
- **Status**: [x] complete

### Task 2: Edit §2a failure-path (cycle-1 and cycle≥2) (R2 + R3)

- **Files**: `skills/lifecycle/references/specify.md`
- **What**: Rewrite the cycle-1 failure-path announcement step (currently line 61) and the cycle≥2 "Present the flagged signals" step (line 70) so both use a bulleted signal list with ≤15 words per bullet and structural-anchor phrasing ("signals flagged in §2a's Research Confidence Check"). Cycle-1 must additionally include an inline example of acceptable terseness.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Cycle-1 block is under the heading `**If any signal is flagged AND current_cycle = 1**:` (lines 59–66); cycle≥2 block is under `**If any signal is flagged AND current_cycle ≥ 2**:` (lines 68–76).
  - Invariants each block must satisfy:
    - **Per-bullet ≤15-word cap** (the substring `≤15 words` must appear in the block)
    - **Structural-anchor phrasing** (the substring `signals flagged in §2a` must appear in the block)
    - **Cycle-1 only**: an inline example matching `Example:` or `e.g.,` demonstrating acceptable terseness
  - Do NOT hardcode a closed list of `C1:` / `C2:` / `C3:` label mappings — bind by reference only. A signal identifier in the cycle-1 example bullet is acceptable because it illustrates shape, not enumerates the set.
  - Editing tool: `Edit` on each heading-bounded block.
- **Verification** (each grep tagged with the R it serves):
  - (R2.1) `awk '/current_cycle = 1/,/current_cycle ≥ 2/' skills/lifecycle/references/specify.md | grep -c '≤15 words'` ≥ 1
  - (R2.2) `awk '/current_cycle = 1/,/current_cycle ≥ 2/' skills/lifecycle/references/specify.md | grep -c 'signals flagged in §2a'` ≥ 1
  - (R2.3) `awk '/current_cycle = 1/,/current_cycle ≥ 2/' skills/lifecycle/references/specify.md | grep -cE '(Example:|e\.g\.,)'` ≥ 1
  - (R3.1) `awk '/current_cycle ≥ 2/,/### 2b\. Pre-Write Checks/' skills/lifecycle/references/specify.md | grep -c '≤15 words'` ≥ 1
  - (R3.2) `awk '/current_cycle ≥ 2/,/### 2b\. Pre-Write Checks/' skills/lifecycle/references/specify.md | grep -c 'signals flagged in §2a'` ≥ 1
- **Status**: [x] complete

### Task 3: Restructure §2b Pre-Write Checks (R4)

- **Files**: `skills/lifecycle/references/specify.md`
- **What**: Restructure §2b (lines 78–97) so verification and cross-check work produces no user-visible output on pass. On failure, surface only the specific failing claim or unresolved item. Preserve the substance of all four sub-checks — the change is output surface, not verification work. Ensure no surviving instruction in §2b asks the orchestrator to summarize, announce, or confirm passing checks (R4's conjunctive second clause).
- **Depends on**: [2]
- **Complexity**: simple
- **Context**:
  - Existing §2b structure to preserve:
    - **Verification check** (lines 82–86): four code-fact sub-checks (git semantics, function behavior, file paths, state ownership)
    - **Research cross-check** (line 88): re-read research.md; silent-omission guard
    - **Open Decision Resolution** (lines 90–96): three-step resolution order; one-sentence reason for any deferred item
  - Invariants the edit must establish:
    - **Positive directive**: at least one occurrence of `continue to §3 with no output`, `proceed to §3 with no output`, or `no output on pass` somewhere in §2b.
    - **No pass-narration instruction**: the §2b block must NOT contain the words `summarize`, `announce`, or `confirm` in any instruction that asks the orchestrator to narrate on pass. (The grep below checks by `awk`-scoping to §2b.)
  - Do NOT add an instruction to summarize, announce, or confirm passing checks anywhere in §2b after edit.
  - Do NOT add a new `pre_write_check` event (explicitly Non-Requirement).
  - Editing tool: `Edit` over the §2b section (from `### 2b. Pre-Write Checks` through the end of the Open Decision Resolution bullets, bounded above by `### 3\. Write Specification Artifact`).
- **Verification**:
  - (R4.1) `grep -cE '(continue to §3 with no output|proceed to §3 with no output|no output on pass)' skills/lifecycle/references/specify.md` ≥ 1
  - (R4.2, closes the silent-gap from critical-review): `awk '/### 2b\. Pre-Write Checks/,/### 3\. Write Specification Artifact/' skills/lifecycle/references/specify.md | grep -cEi '(summarize|announce|confirm) passing'` = 0. The `awk` bounds §2b exactly; the grep catches any residual phrasing that asks the orchestrator to narrate on pass.
- **Status**: [x] complete

### Task 4: Rewrite Fix Agent Prompt Template envelope (R5)

- **Files**: `skills/lifecycle/references/orchestrator-review.md`
- **What**: Replace the free-form `Report: what you changed and why. Format: changed [file path] — [one-sentence rationale].` line (currently line 98 inside the Fix Agent Prompt Template code block) with a YAML-like envelope specification requiring three fields. Preserve all other lines of the Fix Agent Prompt Template (94–102) verbatim except line 98.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Current line 98 (inside a fenced code block at lines 81–102): `5. Report: what you changed and why. Format: changed [file path] — [one-sentence rationale].`
  - **Invariants the envelope specification must establish** (the four grep targets are the binding constraint — any text that satisfies all four is acceptable):
    - **verdict field**: required; line matching the regex `^\s*verdict:\s*revised \| failed` must appear exactly **once** in the file (count = 1). The pipe `|` is the union separator (YAML-style).
    - **files_changed field**: required; at least one occurrence of the substring `files_changed` in the file.
    - **rationale field**: required; at least one occurrence of the substring `rationale` in the file.
    - **Legacy phrase removed**: the substring `Report: what you changed and why` must no longer appear in the file (count = 0).
    - **Numbered-list prefix**: preserve the `5.` prefix that starts the Fix Agent Prompt Template's fifth instruction, so instruction numbering within the template stays intact.
  - Example phrasing (illustrative only; the implementer writes whatever hits the grep):
    - Something of the shape "End your return with a YAML-style envelope using the fields `verdict: revised | failed`, `files_changed: [<path>, ...]`, and `rationale: <≤15 words>`. Emit no prose before or after the envelope."
  - Scope: the phrase `Report: what you changed and why` also appears in `skills/discovery/references/orchestrator-review.md` — **do NOT edit the discovery file; the scope of this task is the lifecycle file only.** The R5 grep targets `skills/lifecycle/references/orchestrator-review.md` specifically.
  - Editing tool: `Edit` on line 98 (use a unique `old_string` that includes context to avoid ambiguity).
- **Verification**:
  - (R5.1) `grep -cE '^\s*verdict:\s*revised \| failed' skills/lifecycle/references/orchestrator-review.md` = 1
  - (R5.2) `grep -c 'files_changed' skills/lifecycle/references/orchestrator-review.md` ≥ 1
  - (R5.3) `grep -c 'rationale' skills/lifecycle/references/orchestrator-review.md` ≥ 1
  - (R5.4) `grep -c 'Report: what you changed and why' skills/lifecycle/references/orchestrator-review.md` = 0
- **Status**: [x] complete

### Task 5: Add Step 5 orchestrator disposition instruction (R6 + R7)

- **Files**: `skills/lifecycle/references/orchestrator-review.md`
- **What**: Add an explicit disposition instruction inside Step 5 (Fix Dispatch, lines 59–102) stating that after the fix-agent returns its envelope, the orchestrator (a) reads the envelope, (b) does NOT relay it to the user, (c) writes the per-cycle `orchestrator_review` event (preserving cycle-cap logic at lines 161–168), and (d) surfaces only the pass/fail verdict from the re-review. The new disposition MUST be placed inside the Step 5 block bounded by `### 5. Fix Dispatch` and `### 6.`.
- **Depends on**: [4]
- **Complexity**: simple
- **Context**:
  - Step 5 already contains at line 77: "After all fixes complete, return to step 2 (Execute Review) and increment the cycle counter." The new disposition paragraph should be placed immediately before or after line 77, or as a new sub-paragraph between line 77 and the Fix Agent Prompt Template heading at line 79.
  - **Invariants the edit must establish** (the awk-bounded greps are the binding constraint):
    - Step 5 must contain at least one of the substrings `do not relay`, `never relay`, or `not surfaced to the user`.
    - Step 5 must contain the substring `orchestrator_review` at least once.
  - **R7 semantic guard** (flagged by plan critical-review): Step 5 does NOT currently contain the string `orchestrator_review` (the current reference is in Step 3 at line 39). The R7 grep's intent is that the NEW disposition text mentions the event explicitly, not that a coincidental adjacent reference satisfies it. Implementer guidance: the `orchestrator_review` mention MUST appear inside the newly added disposition paragraph — not as a bare reference attached to existing text. The grep's current form is permissive; satisfying the semantic intent (the disposition explicitly wires the silent re-run to the event write) is the implementer's responsibility.
  - Example phrasing (illustrative only; any wording satisfying both invariants is acceptable):
    > After the fix-agent returns its envelope, the orchestrator reads the envelope and does not relay it to the user. The orchestrator proceeds to step 2 (Execute Review) and writes the per-cycle `orchestrator_review` event per step 3 as part of the re-review. Only the pass/fail verdict from the re-review surfaces to the user; the fix-agent envelope itself is never relayed.
  - Scope: this directive applies only to the §3a fix-agent re-run loop in the lifecycle phases (research, specify, plan). It is NOT a general convention for sibling skills (`/critical-review` Step 4, `clarify-critic.md`) — spec's Technical Constraints documents this scope limit; no cross-skill edits are required in this task.
  - Editing tool: `Edit` on the Step 5 body (insert a new paragraph; use a unique `old_string` spanning line 77 and the line after).
- **Verification**:
  - (R6) `awk '/^### 5\. Fix Dispatch$/,/^### 6\./' skills/lifecycle/references/orchestrator-review.md | grep -c -E '(do not relay|never relay|not surfaced to the user)'` ≥ 1
  - (R7) `awk '/^### 5\. Fix Dispatch$/,/^### 6\./' skills/lifecycle/references/orchestrator-review.md | grep -c 'orchestrator_review'` ≥ 1
- **Status**: [x] complete

### Task 6: Full acceptance-sweep verification

- **Files**: `skills/lifecycle/references/specify.md` (read-only), `skills/lifecycle/references/orchestrator-review.md` (read-only)
- **What**: Re-run every acceptance command from the spec (R1–R7) against the final state of both edited files in a single sweep. Confirms nothing regressed during the serialized edit path and that all acceptance criteria hold simultaneously. This is the end-to-end gate before commit.
- **Depends on**: [1, 2, 3, 4, 5]
- **Complexity**: simple
- **Context**:
  - The 14 acceptance assertions to re-run (enumerated here rather than deferred to spec — if spec tightens later, this list must be refreshed):
    - **R1.1**: `grep -cE 'proceed to §3\. No event is logged\. Do not (emit|announce|surface)' skills/lifecycle/references/specify.md` ≥ 1
    - **R2.1**: `awk '/current_cycle = 1/,/current_cycle ≥ 2/' skills/lifecycle/references/specify.md | grep -c '≤15 words'` ≥ 1
    - **R2.2**: `awk '/current_cycle = 1/,/current_cycle ≥ 2/' skills/lifecycle/references/specify.md | grep -c 'signals flagged in §2a'` ≥ 1
    - **R2.3**: `awk '/current_cycle = 1/,/current_cycle ≥ 2/' skills/lifecycle/references/specify.md | grep -cE '(Example:|e\.g\.,)'` ≥ 1
    - **R3.1**: `awk '/current_cycle ≥ 2/,/### 2b\. Pre-Write Checks/' skills/lifecycle/references/specify.md | grep -c '≤15 words'` ≥ 1
    - **R3.2**: `awk '/current_cycle ≥ 2/,/### 2b\. Pre-Write Checks/' skills/lifecycle/references/specify.md | grep -c 'signals flagged in §2a'` ≥ 1
    - **R4.1**: `grep -cE '(continue to §3 with no output|proceed to §3 with no output|no output on pass)' skills/lifecycle/references/specify.md` ≥ 1
    - **R4.2**: `awk '/### 2b\. Pre-Write Checks/,/### 3\. Write Specification Artifact/' skills/lifecycle/references/specify.md | grep -cEi '(summarize|announce|confirm) passing'` = 0
    - **R5.1**: `grep -cE '^\s*verdict:\s*revised \| failed' skills/lifecycle/references/orchestrator-review.md` = 1
    - **R5.2**: `grep -c 'files_changed' skills/lifecycle/references/orchestrator-review.md` ≥ 1
    - **R5.3**: `grep -c 'rationale' skills/lifecycle/references/orchestrator-review.md` ≥ 1
    - **R5.4**: `grep -c 'Report: what you changed and why' skills/lifecycle/references/orchestrator-review.md` = 0
    - **R6.1**: `awk '/^### 5\. Fix Dispatch$/,/^### 6\./' skills/lifecycle/references/orchestrator-review.md | grep -c -E '(do not relay|never relay|not surfaced to the user)'` ≥ 1
    - **R7.1**: `awk '/^### 5\. Fix Dispatch$/,/^### 6\./' skills/lifecycle/references/orchestrator-review.md | grep -c 'orchestrator_review'` ≥ 1
  - Report one line per assertion with the observed count and pass/fail result. Any single failure halts the task and surfaces the specific failing assertion for rework.
  - This task does NOT modify any file. Both files in the Files list are read-only dependencies (P6 clause 1 satisfied; clause 2 trivially satisfied because nothing is modified).
- **Verification**: Every assertion above returns the required count; task passes only when all 14 assertions hold. If any assertion fails, the task is flagged with the failing assertion name (e.g., "R5.4 failed: 'Report: what you changed and why' count = 1, expected 0"). Pass criterion: zero failing assertions across the R1–R7 set.
- **Status**: [x] complete

## Verification Strategy

The feature is verified by the union of the 14 R1–R7 acceptance assertions enumerated in Task 6, executed after all edit tasks complete. Because all assertions are grep/awk commands against two static files, Task 6 is fully deterministic and re-runnable.

**P7 self-seal carve-out (explicit)**: Every edit task's Verification field asserts the structural shape of that task's own primary deliverable (the edit). Per P7's operational test in `skills/lifecycle/references/orchestrator-review.md` line 159 — "if the task's stated purpose is to create that artifact (it is the primary deliverable), the self-check is benign" — these greps are benign self-checks, not self-sealing audit side-channels. Task 6's sweep re-asserts the same invariants across both files to catch regressions introduced during the serialized edit path.

**What is NOT verified by this ticket** (explicitly out of scope per spec Non-Requirements): whether real fix-agent runs actually emit parseable envelopes at runtime; whether the orchestrator actually suppresses them from the user; whether malformed envelopes are detected without a parser; whether on-disk artifact integrity post-fix matches the orchestrator's in-context understanding. These rely on runtime behavior this ticket knowingly does not test.

## Veto Surface

- **B2 envelope mechanism over B1 behavioral instruction (R5)** — selected during spec interview; user may revisit before implement if a simpler B1 is preferred in retrospect. Changing back to B1 would collapse Task 4 into a minor edit and simplify Task 5 slightly.
- **Structural-anchor phrasing "signals flagged in §2a's Research Confidence Check"** — picked over alternatives like "signals flagged in the checks above." Changing it would require rewriting R2/R3 acceptance commands and Task 2's Context.
- **Defensive serialization via `Depends on` chain** — keeps same-file tasks sequential to avoid pipeline races. If the implement pipeline guarantees per-file mutex or single-task-at-a-time dispatch, the chain could be dropped and T1/T2/T3 could run with `Depends on: none`, T5 with `none`. Revisit if pipeline semantics are confirmed to serialize per-file.
- **No runtime test / no re-read guard** — accepted silent-failure surfaces from the spec (malformed rewrite, wrong-path write, events-log asymmetry). A lightweight runtime smoke test (e.g., a hook asserting the envelope parses in events.log) is out of scope.

## Scope Boundaries

- **Not in scope**: `orchestrator-review.md §4` one-line pass assessment, `clarify.md`, `plan.md`, `/critical-review`, `clarify-critic.md`, `skills/discovery/references/orchestrator-review.md`. Sibling tickets in epic 66 own the clarify/critical-review/plan narration surfaces; discovery's orchestrator-review uses the same prose Fix Agent Report pattern but is explicitly out of scope (its grep target is NOT asserted).
- **Not in scope**: runtime tests of narration suppression, re-read+validity guards before silent re-run, new audit events (`pre_write_check`, `confidence_check: pass`), any pattern extension beyond the §3a fix-agent re-run loop.
- **Not in scope**: changes to event schemas (`orchestrator_review`, `orchestrator_dispatch_fix`), cycle-cap logic (orchestrator-review.md lines 161–168), cycle counting (specify.md line 57).
