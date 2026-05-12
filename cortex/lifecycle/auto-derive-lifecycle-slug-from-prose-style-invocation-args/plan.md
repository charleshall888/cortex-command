# Plan: auto-derive-lifecycle-slug-from-prose-style-invocation-args

## Overview

Two parallel SKILL.md prose edits, one per file. Both insertions add an explicit prose-handling branch with three properties: (a) detection rule for "input is prose, not a valid slug", (b) derivation prescription (3–6 word kebab-case slug summarizing the prose), and (c) no-confirmation rule (announce, don't ask). Plugin mirrors auto-regenerate via the pre-commit dual-source hook.

## Outline

### Phase 1: Add prose-handling branch to both skill surfaces (tasks: 1, 2)
**Goal**: Both canonical SKILL.md files prescribe prose-to-slug derivation behavior explicitly; agents stop asking and stop varying.
**Checkpoint**: All three spec acceptance criteria (R1, R2, R3) pass; `just test` exits 0.

## Tasks

### Task 1: Augment `skills/lifecycle/SKILL.md` Step 1 with prose-handling branch
- **Files**: `skills/lifecycle/SKILL.md`
- **What**: Modify the parse-rule prose in Step 1 (currently around line 45, beginning "Feature/phase from invocation: $ARGUMENTS. Parse: first word = feature name…") to add an explicit branch: when `$ARGUMENTS` is non-empty AND its first word does not match the valid-slug pattern `^[a-z0-9]+(-[a-z0-9]+)*$`, the agent derives a 3–6 word kebab-case slug summarizing the prose, announces the chosen slug, and uses it as `{feature}` for the rest of Step 1 (resolver lookup) and Step 2. Include the no-confirmation prescription explicitly. Include the brief edge-case note (collisions fall through to existing Step 2 resume path). Soft positive-routing language; no MUST/NEVER/REQUIRED/CRITICAL.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Existing Step 1 prose style is short instructional paragraphs followed by code-fenced bash examples. The new branch fits between the existing "Parse: first word = feature name…" sentence (line 45) and the "Determine the feature name from the invocation" sentence (line 47). The valid-slug regex `^[a-z0-9]+(-[a-z0-9]+)*$` should appear inline as a literal pattern the agent matches against. The phrase "kebab-case slug" already appears at line 47 — re-use the same vocabulary for consistency. Inline correction mechanism (per spec Non-Requirements): re-invocation only; do not mention "rename in place" as a correction option. Phrasing pattern to follow: existing Step 1 uses "When `$ARGUMENTS` is empty, skip the resolver…" (line 65) as a conditional-branch template — mirror that structure for the new prose branch.
- **Verification**: `awk '/^## Step 1:/,/^## Step 2:/' skills/lifecycle/SKILL.md | grep -ci 'derive.*slug\|prose-style\|not a valid.*slug'` returns ≥`1`; `awk '/^## Step 1:/,/^## Step 2:/' skills/lifecycle/SKILL.md | grep -ci 'do not ask\|without.*confirm\|do not.*confirm'` returns ≥`1`; `awk '/^## Step 1:/,/^## Step 2:/' skills/lifecycle/SKILL.md | grep -ciE '\b(MUST|NEVER|REQUIRED|CRITICAL)\b'` against just the new prose lines returns `0`; `wc -l skills/lifecycle/SKILL.md` ≤ `500` (size budget); `just test` exits 0.
- **Status**: [x] completed

### Task 2: Augment `skills/refine/SKILL.md` Step 1 exit-3 branch with prose-handling branch
- **Files**: `skills/refine/SKILL.md`
- **What**: Modify the exit-3 routing prose in Step 1 (currently around line 39, "Exit 3 — no match. Switch to Context B (ad-hoc topic)…") to add a parallel prose-derivation prescription: when the resolver returns exit 3 AND the input is prose (does not match `^[a-z0-9]+(-[a-z0-9]+)*$`), derive a 3–6 word kebab-case slug from the prose before switching to Context B, announce it, and use it as the `{lifecycle-slug}` for refine's downstream phases. Include the no-confirmation prescription. Reference the lifecycle SKILL.md prescription by inline cross-pointer rather than duplicating the full rule. Soft positive-routing language; no MUST/NEVER/REQUIRED/CRITICAL.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Existing exit-3 prose at line 39 is one sentence: "Exit 3 — no match. Switch to Context B (ad-hoc topic) per `../lifecycle/references/clarify.md` §1 and treat the input as the topic name." The new content augments this — likely 2–3 additional sentences within the same exit-3 bullet. Cross-pointer phrasing: "When the input is prose (not a valid kebab-case slug), apply the prose-derivation prescription from `../lifecycle/SKILL.md` Step 1 before treating it as the topic name." This avoids duplicating the rule. Inline correction mechanism: re-invocation only.
- **Verification**: `awk '/Exit 3.*no match/,/Exit 64/' skills/refine/SKILL.md | grep -ci 'derive.*slug\|prose'` returns ≥`1`; `awk '/Exit 3.*no match/,/Exit 64/' skills/refine/SKILL.md | grep -ci 'do not ask\|without.*confirm\|do not.*confirm'` returns ≥`1`; the exit-3 bullet block has zero MUST/NEVER/REQUIRED/CRITICAL terms; `wc -l skills/refine/SKILL.md` ≤ `500` (size budget); `just test` exits 0.
- **Status**: [x] completed

## Risks

- **Plugin mirror drift**: If the pre-commit dual-source hook is not installed locally (`just setup-githooks`), edits to canonical sources won't trigger mirror regeneration and the committed mirrors will be stale. Mitigation: the hook is repo-managed (per CLAUDE.md); the implementer should verify the hook fires by checking `plugins/cortex-core/skills/lifecycle/SKILL.md` and `plugins/cortex-core/skills/refine/SKILL.md` reflect the canonical changes after staging.
- **Tone drift toward directive language**: Adding prescription text strong enough to actually shift behavior may inadvertently produce implicit imperatives ("always derive…") that read as MUST. Mitigation: the verification grep on MUST/NEVER/REQUIRED/CRITICAL catches literal directive vocabulary; the implementer should also re-read for implicit imperatives.
- **Cross-pointer breakage**: Task 2's cross-pointer to `../lifecycle/SKILL.md` Step 1 will break if Step 1's structure changes. Mitigation: anchor on section heading ("Step 1") rather than line numbers; the lifecycle SKILL.md kept-pauses parity test catches structural drift in Step 1's user-facing pauses, providing partial coverage.
