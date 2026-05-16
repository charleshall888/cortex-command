# Review: adopt-one-at-a-time-grilling (cycle 1)

## Stage 1: Spec Compliance

### R1 — One-at-a-time cadence prose in requirements-gather: PASS
`awk '/^## Decision criteria/,/^## Output shape/' skills/requirements-gather/SKILL.md | grep -ci "one at a time"` returns 2 (≥ 1 required). Cadence prose lands in a new H3 subsection `### Ask one at a time` at line 31 of `skills/requirements-gather/SKILL.md`, positioned between `### Recommend before asking` and `### Lazy artifact creation` as planned.

### R2 — Cross-reference pointer in requirements-gather: PASS
`awk '/^## Decision criteria/,/^## Output shape/' skills/requirements-gather/SKILL.md | grep -c "specify.md"` returns 1 (≥ 1 required). The pointer reads "Mirrored in `skills/lifecycle/references/specify.md` §2 — when editing this rule, update the other surface too." and is anchored inside the `Ask one at a time` H3 block.

### R3 — Grounded file-path citation rule in requirements-gather: PASS
`grep -ci "derived from code\|grounded in code" skills/requirements-gather/SKILL.md` returns 1 (≥ 1 required). The guidance lands at line 65 below the Output shape block and preserves the "omit otherwise" semantics for intent-only questions.

### R4 — One-at-a-time cadence prose in specify §2: PASS
`awk '/^### 2\. Structured Interview/,/^### 2a/' skills/lifecycle/references/specify.md | grep -ci "one at a time"` returns 1 (≥ 1 required). Cadence prose lands as a `**Cadence**:` paragraph at line 38, immediately after the existing "Ask probing questions…" paragraph.

### R5 — Cross-reference pointer in specify §2: PASS
`awk '/^### 2\. Structured Interview/,/^### 2a/' skills/lifecycle/references/specify.md | grep -c "requirements-gather"` returns 1 (≥ 1 required). Pointer is anchored to the cadence paragraph as required.

### R6 — Grounded file-path citation rule in specify §2: PASS
`awk '/^### 2\. Structured Interview/,/^### 2a/' skills/lifecycle/references/specify.md | grep -ci "file path\|file-path"` returns 2 (≥ 1 required). Lands as a `**File-path citation**:` paragraph at line 40.

### R7 — Soft mid-interview verification guideline in specify §2: PASS
Current count of `\bverify\b`-bearing lines in the §2 awk window = 1; pre-change baseline (commit `a810e905^`) = 0. Delta = 1 (≥ 1 required). The spec's literal AC references `git show main:` for baseline; because the implementation is already merged to main, that literal form produces a misleading current==baseline reading. The intent of the AC — that R7 added ≥ 1 newly-`verify`-bearing line over the pre-implementation baseline — is satisfied. New prose at line 42 reads "**Verification posture**: When citing a file path or a function-behavior claim during the interview, verify it against the actual code…". The §2b end-of-interview Verification check sub-block is preserved separately (R9).

### R8 — Judgmental edge-case invention prose in specify §2: PASS
`awk '/^### 2\. Structured Interview/,/^### 2a/' skills/lifecycle/references/specify.md | grep -ci "under-specified"` returns 1 (≥ 1 required). The prose at line 44 explicitly applies "judgmentally" and reinforces that categorical per-requirement invention is not prescribed.

### R9 — §2b Verification check stays end-of-interview: PASS
`awk '/^### 2b/,/^### 3/' skills/lifecycle/references/specify.md | grep -c "Verification check"` returns 1 (≥ 1 required). §2b structural position unchanged.

### R10 — Kept-user-pauses tolerance prose matches code constant: PASS
`grep -c "±35-line tolerance" skills/lifecycle/SKILL.md` returns 1; `grep -c "±20-line tolerance" skills/lifecycle/SKILL.md` returns 0. Line 191 prose updated.

### R11 — Q&A block schema preserved verbatim: PASS
`grep -cE '^\s*-\s+\*\*(Q|Recommended answer|User answer|Code evidence):\*\*\s+\{' skills/requirements-gather/SKILL.md` returns exactly 4. Schema bullets at lines 54–57 unchanged.

### R12 — Soft-positive routing only — no new MUST/CRITICAL/REQUIRED tokens: PASS
Per-file counts: `requirements-gather/SKILL.md` = 0, `specify.md` = 0; sum = 0; AC awk exits 0.

### R13 — Test suite passes: PASS (with caveat)
Under default sandbox, `just test` returns 6 spurious failures in `tests/test_clarify_critic_alignment_integration.py` and `tests/test_load_parent_epic.py`. These are an environment artifact — the sandbox `**/*.pem` deny rule blocks `tiktoken`'s certifi cert-bundle read inside `bin/cortex-load-parent-epic` when its tiktoken cache is cold, unrelated to the prose-only edits in this work. Sandbox-bypass run yields 6/6 suites pass (per plan T6 verification record).

### R14 — SKILL.md size cap respected: PASS
`requirements-gather/SKILL.md` = 78, `specify.md` = 199, `lifecycle/SKILL.md` = 225 — all well below the 500-line cap.

## Stage 2: Code Quality

- **Naming conventions**: The new H3 in requirements-gather (`### Ask one at a time`) matches the imperative-but-soft form of sibling H3s in `## Decision criteria` (`### Codebase trumps interview`, `### Recommend before asking`, `### Lazy artifact creation`). The four bolded `**Cadence**:` / `**File-path citation**:` / `**Verification posture**:` / `**Edge-case invention**:` paragraphs in specify §2 follow the existing §2 convention of bolded inline labels (`**Problem statement**:`, `**Requirements**:`, etc.).
- **Error handling / soft-positive routing**: R12 confirms zero MUST/CRITICAL/REQUIRED tokens in the final state of both edited skill files. Cadence prose uses soft-positive form ("Ask interview questions one at a time, waiting for…") and frames the anti-pattern as guidance ("Avoid batching…"). Verification posture and edge-case invention prose both encode the decision rule and intent (what + why) without procedural narration, honoring CLAUDE.md's "Prescribe What and Why, not How" principle.
- **Test coverage**: Plan T6 verification record documents all five global gates as passing. R13's sandbox-bypass execution was performed; no test regressions are attributable to the prose edits.
- **Pattern consistency — cadence-block substantive parity**: The cadence prose in both surfaces is substantively equivalent. Both share the same opening sentence ("Ask interview questions one at a time, waiting for the user's response before posing the next"), the same gating concept ("The previous answer is the gate to the next question, so each question can be shaped by what just landed"), the same anti-batching rationale ("batched questions invite partial answers, hide decision-tree branches that should resolve sequentially, and create respondent fatigue"), and reciprocal pointer notes back to the other surface. The pointer-note hybrid mitigation chosen to balance Approach A vs B is faithfully reflected — both surfaces explicitly invite the editor to update the other when changing the rule.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Verdict
```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": "none"
}
```
