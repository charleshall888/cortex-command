# Plan: Add vendor-endorsement value gating to /discovery decompose phase

## Overview

Single-file prose edit to `skills/discovery/references/decompose.md` implementing spec R1–R9, plus one new protocol-level pytest test that validates **both** rule presence and correct section placement (not just string presence). Verification is multi-layered: per-task grep gates at edit time, section-aware pytest assertions that exclude HTML comments, a final-state re-verification task that catches cross-task overwrites, and a narrow-scope test gate that isolates rule correctness from repo-wide test flakes.

Edit tasks (1–6) are localized to distinct sections of decompose.md with explicit ordering where boundaries overlap. Task 7 writes the pytest module; Task 8 runs the narrow-scope test as the authoritative rule gate; Task 9 re-runs all per-task greps in the final state; Task 10 runs the full `just test` suite as the repo-health gate.

## Tasks

### Task 1: Add R1 authoring-time norm to Constraints block
- **Files**: `skills/discovery/references/decompose.md`
- **What**: Insert a new bullet in the final Constraints section stating vendor guidance, best practices, and industry standards are not sufficient Value alone; the Value field must describe the codebase-local problem this work solves.
- **Depends on**: none
- **Complexity**: simple
- **Context**: decompose.md's Constraints section is at lines 113–117 (end of file). Current bullets: "No implementation planning", "One epic max", "Respect backlog conventions". Insert the new bullet above "No implementation planning" so it anchors the Value-field discipline. Bullet format: `- **Codebase-grounded Value**: Vendor guidance, best practices, and industry standards are not sufficient Value on their own — the Value field must state what problem this solves in *this* codebase.` Spec anchor: R1.
- **Verification**: `grep -c "not sufficient Value" skills/discovery/references/decompose.md` ≥ 1. String must appear within the Constraints block (not in an HTML comment or stale section) — Task 7's section-aware test enforces this.
- **Status**: [x] completed

### Task 2: Add R2 two-check flag detection to §2 Value field
- **Files**: `skills/discovery/references/decompose.md`
- **What**: Replace the Value-field bullet at §2 line 23 with an expanded block covering: (a) require a locally-written `[file:line]` citation grounding the Value in *this* codebase; (b) cross-check `research/{topic}/research.md` for either `[premise-unverified: not-searched]` adjacent to the Value-supporting claim OR absence of `[file:line]` within that claim's research section (explicitly describe BOTH branches as primary paths, noting that citation-absence is the dominant path for current corpus per E1); (c) non-gating surface-pattern helper hint listing vendor/authority phrasings; (d) **E9 ad-hoc fallback**: when no `research/{topic}/research.md` exists (ad-hoc discovery), R2(b) is skipped and R2(a) alone governs flagging — name this condition explicitly in the rule prose. Item is flagged when (a) fails OR (b) indicates an unverified premise.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Current text at line 23: `- **Value**: What problem this solves and why it's worth the effort. One sentence. If the value case is weak relative to size, say so — this is the moment to flag it before tickets are created.` Replace with the R2 block matching spec §R2 and E1/E9. #138's signal shape (`[premise-unverified: not-searched]`) is codified at `skills/discovery/references/research.md:148-154`. Surface-pattern examples to enumerate: `"vendor X recommends"`, `"Anthropic says"`, `"CrewAI docs"`, `"industry best practice"`, `"canonical pattern in $framework"`, `"recommended approach"`, `"current conventions suggest"`, `"standard pattern"`, `"widely adopted"`, `"accepted convention"`. List is non-exhaustive; say so explicitly. Spec anchors: R2 + E1 + E9 + TC6.
- **Verification**: All five must hold: `grep -c "\[file:line\]" skills/discovery/references/decompose.md` ≥ 1 AND `grep -c "premise-unverified" skills/discovery/references/decompose.md` ≥ 1 AND `grep -c "canonical pattern" skills/discovery/references/decompose.md` ≥ 1 AND `grep -c "absence of\|no citation" skills/discovery/references/decompose.md` ≥ 1 (E1 branch anchor) AND `grep -c "ad-hoc\|no research\.md\|R2(b)" skills/discovery/references/decompose.md` ≥ 1 (E9 fallback anchor).
- **Status**: [x] completed

### Task 3: Replace user-approval step at §2 line 29 with flagged-item routing (R3 + R4 + R6) + inline R7 event logging
- **Files**: `skills/discovery/references/decompose.md`
- **What**: Replace/extend §2 line 29 with a structured flow: (i) if any items flagged per R2, check the R4 cap (more than 3 flagged in the pre-consolidation set OR all items flagged with N ≥ 2); if cap fires, halt and escalate with the R4 message; (ii) otherwise, present flagged items one at a time via `AskUserQuestion`, each prompt quoting the Value string verbatim, stating which R2 branch flagged it, and offering three choices: "Acknowledge and proceed", "Drop this item", "Return to research"; (iii) unflagged items continue through the existing batch-review at `decompose.md:29` (preserve the original sentence for R6); (iv) **inline event logging**: within this §2 flow block, document the event shapes `decompose_flag`, `decompose_ack`, `decompose_drop` appended to the existing research-topic event stream (same stream as `orchestrator-review.md:22-30`), with skip-silent invariant if no stream exists. Place the event documentation at the end of the §2 flow so events are documented where they fire.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: AskUserQuestion precedent: `skills/lifecycle/references/specify.md:36` and `:157`. Signal-driven per-item gating precedent: `specify.md:38-77` (§2a Research Confidence Check). Event-documentation precedent: `orchestrator-review.md:22-30` documents events inside the section that emits them (flat numbering — no §Na subsection letter introduced). Following that precedent: event block lives at end of §2, not §3a. This also eliminates cross-skill §3a naming collision with `specify.md:143` and `plan.md:235` (both §3a Orchestrator Review). R4 uses **pre-consolidation** flag count explicitly. Three-choice prompt must quote Value + R2 branch (R2(a)-no-grounding OR R2(b)-research-absent). Event JSON shapes (spec R7 verbatim): `{"ts": "<ISO 8601>", "event": "decompose_flag", "phase": "decompose", "item": "<title>", "reason": "<R2(a)|R2(b)|both>", "details": "<short>"}`, `{"ts": "<ISO 8601>", "event": "decompose_ack", "phase": "decompose", "item": "<title>"}`, `{"ts": "<ISO 8601>", "event": "decompose_drop", "phase": "decompose", "item": "<title>", "reason": "<R2 basis from flag event>"}`. Spec anchors: R3, R4, R6, R7, E3, E4, E6, E7.
- **Verification**: All must hold: `grep -c "AskUserQuestion" skills/discovery/references/decompose.md` ≥ 1; `grep -c "pre-consolidation\|before Consolidation" skills/discovery/references/decompose.md` ≥ 1; `grep -c "more than 3" skills/discovery/references/decompose.md` ≥ 1 (E4 branch — split from alternation); `grep -c "all items are flagged\|all items flagged" skills/discovery/references/decompose.md` ≥ 1 (E3 branch); `grep -c "Return to research" skills/discovery/references/decompose.md` ≥ 1 (E7 halt); `grep -c "Present the proposed work items" skills/discovery/references/decompose.md` ≥ 1 (R6 preservation — the original batch-review sentence must still exist in the unflagged-path branch of the new flow, not be deleted); `grep -c "flagged item" skills/discovery/references/decompose.md` ≥ 1 (new-flow presence — ensures the replace-in-place edit actually introduced flagged-item routing prose); `grep -c "decompose_flag" skills/discovery/references/decompose.md` ≥ 1 AND `grep -c "decompose_ack" skills/discovery/references/decompose.md` ≥ 1 AND `grep -c "decompose_drop" skills/discovery/references/decompose.md` ≥ 1 (R7 event schemas).
- **Status**: [x] completed

### Task 4: Add R5 flag propagation to §3 Consolidation Review
- **Files**: `skills/discovery/references/decompose.md`
- **What**: Append a paragraph at the end of §3 stating: (i) if any input item to a consolidation merge carried a flag per R2, the merged output item carries the flag for R3 ack-display purposes; (ii) R4 cap evaluates on pre-consolidation count (not post-consolidation); (iii) the R3 ack prompt for a merged flagged item must surface the originating flagged input's Value + premise so the user sees the actual basis of the flag (E5); (iv) E10 invariant: consolidation cannot reduce the flagged set to zero — propagation ensures any input flag survives merging.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: §3 Consolidation Review is at decompose.md lines 31–45. Current final paragraph: `When items are combined, document the consolidation decision and rationale in the Key Design Decisions section of research/{topic}/decomposed.md (written in §6).` Insert the R5 paragraph after that line. Task 6 (former §3a Event Logging) has been merged into Task 3's §2 flow — no longer inserts at §3a, so Tasks 4 and 6 no longer share the §3 boundary. Spec anchors: R5, E5, E10.
- **Verification**: All must hold: `grep -c "merged item carries the flag\|flag propagat\|consolidated item inherits\|merged items retain" skills/discovery/references/decompose.md` ≥ 1 (R5 propagation, broadened for paraphrase); `grep -c "originating\|originally flagged" skills/discovery/references/decompose.md` ≥ 1 (E5 originating-input surfacing); `grep -c "cannot reduce\|invariant\|any input flag survives" skills/discovery/references/decompose.md` ≥ 1 (E10 invariant statement).
- **Status**: [x] completed

### Task 5: Extend §6 Decomposition Record template with Dropped Items subsection (R9)
- **Files**: `skills/discovery/references/decompose.md`
- **What**: Add a `## Dropped Items` subsection to the decomposed.md template at §6 (lines 75–95), with a table header `| Title | Reason (R2 branch) | Originating Value |` and a one-line note: "Include this subsection only when items were dropped at R3's ack prompt; omit when no drops occurred."
- **Depends on**: [4]
- **Complexity**: simple
- **Context**: §6 currently shows the decomposed.md markdown template with sections `## Epic`, `## Work Items`, `## Suggested Implementation Order`, `## Created Files`. Insert `## Dropped Items` between `## Work Items` and `## Suggested Implementation Order`. "Reason" values are the R2 branches named in R3 (R2(a)-no-grounding, R2(b)-research-absent). Spec anchor: R9 + E6.
- **Verification**: `grep -c "Dropped Items\|## Dropped" skills/discovery/references/decompose.md` ≥ 1.
- **Status**: [x] completed

### Task 6: REMOVED — merged into Task 3 (R7 event logging now inline at §2 where events fire)
- **What**: The original Task 6 added a separate §3a Event Logging block. Critical review surfaced that §3a is a named role across `skills/lifecycle/references/*` (Orchestrator Review), not a generic next-subsection slot, and that decompose.md has no subsection-letter precedent (§1–§9 are flat). The R7 event schema is now co-located with the flow that emits the events (Task 3's §2 block), following `orchestrator-review.md:22-30`'s precedent of documenting events inside the section that fires them. Task 3's Verification row includes the three R7 event-name greps. This task remains in the task list as a formal NOOP/removed marker so downstream references to Task numbers in retrospectives and events remain stable.
- **Files**: none
- **Depends on**: [3]
- **Complexity**: trivial
- **Status**: [x] merged into Task 3 — no separate work unit

### Task 7: Add section-aware pytest test for R1–R7 rule presence AND placement (R8)
- **Files**: `tests/test_decompose_rules.py` (new)
- **What**: Write a pytest module that:
  - Opens `skills/discovery/references/decompose.md` and strips HTML-comment blocks (`<!-- ... -->`) before assertions — rule text stranded in comments must not satisfy the gate.
  - Parses the file into sections by `### ` headers and extracts each section's body.
  - Asserts each rule string appears **within its expected section**, not merely anywhere in the file:
    - R1 norm string ("not sufficient Value") in the Constraints section.
    - R2 strings (`[file:line]`, `premise-unverified`, `canonical pattern`, absence-of-citation anchor, ad-hoc fallback anchor) in §2 (Identify Work Items).
    - R3/R4/R6 strings (`AskUserQuestion`, `pre-consolidation`, `more than 3`, `all items are flagged`, `Return to research`, `Present the proposed work items`, `flagged item`) in §2.
    - R7 event names (`decompose_flag`, `decompose_ack`, `decompose_drop`) in §2 (co-located with fire site per Task 3).
    - R5 strings (propagation anchor, `originating`, `cannot reduce`) in §3 (Consolidation Review).
    - R9 `## Dropped Items` as a subsection heading within §6 (Write Decomposition Record).
  - Each assertion is a discrete `def test_<rule>_placement()` function so a failure names the specific rule and expected section.
- **Depends on**: [1, 2, 3, 4, 5]
- **Complexity**: simple
- **Context**: Existing test pattern: `tests/test_skill_contracts.py` — `REPO_ROOT = Path(__file__).parent.parent`, simple pytest structure. Section parsing: split on `^### ` with a regex, group lines under each header. HTML comment stripping: `re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)` before section parsing. `just test` runs `.venv/bin/pytest tests/ -q` (justfile lines 882–908) so auto-discovery picks up the new `test_*.py` module without registration. This addresses the critical-review concern that a grep-only check passes when rule text is stranded in comments, deprecated examples, or wrong sections.
- **Verification**: Run `pytest tests/test_decompose_rules.py -v` — pass if exit 0 and every per-rule placement test passes.
- **Status**: [x] completed

### Task 8: Run narrow-scope pytest test as the authoritative rule gate
- **Files**: none (verification only)
- **What**: Run `pytest tests/test_decompose_rules.py -v` in isolation. This is the authoritative gate for R1–R9 correctness — its signal is independent of unrelated test flakes in the wider suite.
- **Depends on**: [7]
- **Complexity**: simple
- **Context**: Narrow invocation bypasses any flaky or slow sibling tests in `tests/`. Rule-edit correctness does not depend on pipeline, overnight, or dashboard tests passing.
- **Verification**: Run `pytest tests/test_decompose_rules.py -v` — pass if exit 0.
- **Status**: [x] completed

### Task 9: Final-state re-verification (per-task grep gates)
- **Files**: none (verification only)
- **What**: After all edit tasks (1–5) complete, re-run every per-task grep verification against the current on-disk state of `decompose.md`. This catches cross-task overwrites where Task N's inserted string was unintentionally removed by Task N+1 (e.g., Tasks 2 and 3 both edit §2 — if Task 3's replace-in-place accidentally nukes Task 2's R2 anchor strings, Task 2's already-passed gate never re-runs). **Failure-recovery guidance**: if a specific grep fails in this re-check, re-run the owning task's edit targeting only the missing prose; do not re-run the earlier already-complete tasks from scratch.
- **Depends on**: [1, 2, 3, 4, 5]
- **Complexity**: simple
- **Context**: Re-run the grep pipelines from Tasks 1, 2, 3, 4, 5 in sequence on the final file state. This is a discrete verification task so that a cross-task regression surfaces before Task 7's pytest runs — faster feedback on a broken final state.
- **Verification**: All per-task grep gates (from Tasks 1–5's Verification rows) pass against the final `decompose.md` — same commands, now run post-all-edits.
- **Status**: [x] completed

### Task 10: Run full `just test` as repo-health gate
- **Files**: none (verification only)
- **What**: Run `just test` and confirm exit 0. This confirms no regressions were introduced in sibling tests. If `just test` fails due to an unrelated flake, the rule correctness is already confirmed by Task 8 (narrow pytest) and Task 9 (per-task greps) — investigate the flake separately; do not gate feature completion on unrelated test health.
- **Depends on**: [8, 9]
- **Complexity**: simple
- **Context**: `just test` runs `.venv/bin/pytest tests/ -q` plus other test recipes via an internal runner (justfile `test:` recipe). Per `lifecycle.config.md:test-command`, it is the project's authoritative full-suite invocation.
- **Verification**: Run `just test` — pass if exit 0. On failure unrelated to R1–R9, file a separate issue and proceed (Tasks 7/8/9 are the rule-correctness gates).
- **Status**: [x] completed

## Verification Strategy

End-to-end verification has four layers:

1. **Per-task grep gates** (Tasks 1–5): each edit task verifies its own rule strings appear post-edit. These catch the common "did I write the rule?" case.

2. **Final-state re-verification** (Task 9): re-runs all per-task greps against the final on-disk state to catch cross-task overwrites where a later task's edit accidentally removed an earlier task's inserted prose. Critical for Tasks 2/3 which both edit §2.

3. **Section-aware pytest** (Tasks 7 + 8): protocol-presence test asserts each rule string appears **within its expected section header's range**, with HTML-comment blocks stripped before assertion. Rules stranded in comments or wrong sections fail the gate. This is the authoritative rule-correctness signal and is run in isolation (Task 8) so that unrelated test flakes in the wider suite do not block feature completion.

4. **Full-suite health** (Task 10): `just test` confirms no regressions were introduced outside the target file. On failure unrelated to R1–R9, file a separate issue rather than blocking the feature.

Interactive behavior (flag detection runtime, AskUserQuestion ack flow, pre-vs-post-consolidation cap evaluation, event-log writes to topic stream) cannot be unit-tested without running `/discovery` end-to-end and is accepted as interactive/session-dependent per spec TC7. The four-layer automated gate provides strong evidence that the protocol text is present, correctly placed, not stranded in comments or stale sections, and not contradicted by overlapping edits — which is the tightest automated guarantee achievable without running the live skill.

## Veto Surface

- **Surface-pattern list enumeration** (Task 2): 10 example patterns ("vendor X recommends", "Anthropic says", "CrewAI docs", "industry best practice", "canonical pattern in $framework", "recommended approach", "current conventions suggest", "standard pattern", "widely adopted", "accepted convention"). If the user prefers a shorter list or different enumeration, change it here.
- **Three-choice ack prompt** (Task 3): "Acknowledge and proceed" / "Drop this item" / "Return to research". If two choices are preferred (halt handled another way), trim here.
- **R4 cap phrasing** (Task 3): "more than 3 OR all items flagged with N ≥ 2". If proportional threshold (>50%) or different absolute number is preferred, change here and update Task 3's grep anchors accordingly.
- **Task 6 merger into Task 3**: R7 event logging is now inline at end of §2 rather than a separate §3a block. If the user prefers a separate section (even flat §10 Event Logging at file end), this is the moment to redirect.

## Scope Boundaries

Maps to spec Non-Requirements (N1–N6):

- **No /discovery orchestration changes** (N1): plan only edits `skills/discovery/references/decompose.md` and adds `tests/test_decompose_rules.py`. No changes to SKILL.md, clarify.md, research.md, orchestrator-review.md, or auto-scan.md.
- **No gate extension beyond /discovery** (N2): no changes to `/lifecycle`, `/refine`, or the overnight pipeline.
- **No new persistent infrastructure** (N3): the only new file is `tests/test_decompose_rules.py`. No new backlog frontmatter fields, no new hook scripts, no new config files. Ephemeral in-run state (pre- vs post-consolidation flag counts) is agent working memory only.
- **No mechanical grounding verifier** (N4): Approach F deferred per DR-1(c). R2 checks are prose instructions to the agent, not automated validators.
- **No fix for self-referential fabrication** (N5): the residual failure mode where an undisciplined agent fabricates a plausible `[file:line]` to satisfy R2(a) is accepted out-of-scope.
- **No retroactive backlog audit** (N6): existing discovery-sourced tickets are not re-evaluated.
