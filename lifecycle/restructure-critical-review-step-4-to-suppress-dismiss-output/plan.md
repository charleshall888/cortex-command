# Plan: restructure-critical-review-step-4-to-suppress-dismiss-output

## Overview

Single-file edit to `skills/critical-review/SKILL.md` Step 4's compact-summary block. The restructured instruction adds a canonical anchor sentence, a direction-oriented Apply bullet format with a verb list and two-polarity worked examples, a count-only Dismiss line with N = 0 omission, and a reworded Ask consolidation clause. Preserves lines 205/207/209 (disposition framework + self-resolution anchor check), line 217 (Apply bar), and all of Steps 1–3. Decomposed into two tasks — one does the edit and runs the full R1–R10 battery as its own gate; one commits via `/commit` and re-asserts scope against HEAD. Narrow sub-verification witnesses are rejected as under-gating based on adversarial review.

## Tasks

### Task 1: Rewrite Step 4's compact-summary block and verify full R1–R10 battery passes

- **Files**: `skills/critical-review/SKILL.md`
- **What**: (a) Pre-flight — confirm the current target line by searching for the current compact-summary phrase before editing. (b) Replace the numbered-list item currently at or near line 215 (the current compact-summary instruction) with a restructured block containing a canonical anchor sentence, direction-oriented Apply bullet format with verb list, count-only Dismiss line spec with explicit N = 0 omission, reworded Ask consolidation clause, and two-polarity worked examples (one tightening, one loosening/inversion) plus a non-compliant counter-example. (c) Preserve lines 197–214 (Step 4 preamble + disposition framework + anchor checks) and line 217 (Apply bar). Preserve the `## Step 4: Apply Feedback` heading verbatim. (d) Run the full R1–R10 acceptance battery (~17 sub-checks) and confirm each passes before marking the task done.
- **Depends on**: none
- **Complexity**: complex
- **Context**:
  - **Pre-flight**: before editing, run `grep -n "what was changed (one line per fix), what was dismissed and why" skills/critical-review/SKILL.md` to confirm the current compact-summary line still contains the expected phrase. If the output is empty, the target has drifted and the task must halt and surface the drift. If non-empty, record the line number as the current target.
  - **Target block**: the numbered-list item containing the current compact-summary instruction inside Step 4. Current text begins `"Present a compact summary: what was changed (one line per fix), what was dismissed and why, ..."` and ends with the Ask-items clause.
  - **Canonical introducer**: spec R10 fixes the literal sentence `"Present a compact summary in the following format:"`. Include this exact wording; variations fail R10.
  - **Direction-oriented Apply sentence**: spec R3 requires a sentence matching `"Apply bullets describe the direction of the change"` (or the regex-equivalent `"Apply bullets.*describe.*direction"`) as the governing sentence for the Apply bullet format spec.
  - **Canonical verb list ordering**: use exactly this comma-separated list — `strengthened, narrowed, clarified, added, removed, inverted` — on a single contiguous line or sentence. This ordering satisfies R3's regex on the first alternation branch. Do not reorder.
  - **Canonical Dismiss line**: spec R2 requires the literal `"Dismiss: N objections"` inside the Step 4 block. Also include the N=0 omission semantic via a phrase like `"Omit the Dismiss line when N = 0"` (matches R2's second regex).
  - **Ask consolidation clause**: spec R6 requires a sentence matching the regex `"Ask items.*consolidate.*(if|when).*(any remain|present)"`. Example wording: `"Ask items consolidate into a single message when any remain."`.
  - **Worked examples (R4)**: include at least two compliant examples and one non-compliant counter-example, all labeled in the Step 4 block:
    - **Compliant (tightening)**: must match the literal `"strengthened from"` — e.g., `"Compliant: R10 strengthened from SHOULD to MUST."`.
    - **Compliant (loosening/inversion)**: must match the regex `"(inverted|reversed|relaxed|narrowed) from"` — e.g., `"Compliant: R3 narrowed from 'all endpoints' to 'payment endpoints'."` or `"Compliant: R7 inverted from MUST to SHOULD."`.
    - **Non-compliant counter-example**: must be labeled with the literal `"Non-compliant:"` — e.g., `"Non-compliant: R10 updated."`.
  - **Preserve (do NOT edit)**: lines 197–214 (Step 4 preamble + disposition framework + both anchor checks), line 217 (Apply bar), the Step 4 heading `## Step 4: Apply Feedback`, and all content before Step 4 (Steps 1–3 + preamble). R9 verifies this via byte-identity diff.
  - **Inherited callers (do NOT edit)**: `skills/lifecycle/references/specify.md:150`, `skills/lifecycle/references/plan.md:243`, `skills/discovery/references/research.md:128`. They invoke `/critical-review` and inherit Step 4 behavior transparently per spec R7.
  - **Reference artifact**: `lifecycle/restructure-critical-review-step-4-to-suppress-dismiss-output/spec.md` contains the full R1–R10 requirement text and acceptance-criteria convention.
- **Verification**: Full R1–R10 battery. Each of the following must pass; if any fails, revise the edit and re-run before marking the task done.
  - R1: `grep -c "what was dismissed and why" skills/critical-review/SKILL.md` — output is `0`.
  - R2a: `awk '/^## Step 4:/,/^## Step [^4]/' skills/critical-review/SKILL.md | grep -c "Dismiss: N objections"` — output ≥ `1`.
  - R2b: `awk '/^## Step 4:/,/^## Step [^4]/' skills/critical-review/SKILL.md | grep -cE "[Oo]mit.*Dismiss.*line.*when.*(N = 0|N=0|zero|count is 0)"` — output ≥ `1`.
  - R3a: `awk '/^## Step 4:/,/^## Step [^4]/' skills/critical-review/SKILL.md | grep -cE "Apply bullets.*(direction of the change|describe.*direction)"` — output ≥ `1`.
  - R3b: `awk '/^## Step 4:/,/^## Step [^4]/' skills/critical-review/SKILL.md | grep -cE "strengthened.*narrowed.*(clarified|added|removed).*inverted|inverted.*(strengthened|narrowed|clarified|added|removed)"` — output ≥ `1`.
  - R4a: `awk '/^## Step 4:/,/^## Step [^4]/' skills/critical-review/SKILL.md | grep -c "strengthened from"` — output ≥ `1`.
  - R4b: `awk '/^## Step 4:/,/^## Step [^4]/' skills/critical-review/SKILL.md | grep -cE "(inverted|reversed|relaxed|narrowed) from"` — output ≥ `1`.
  - R4c: `awk '/^## Step 4:/,/^## Step [^4]/' skills/critical-review/SKILL.md | grep -c "Compliant:"` — output ≥ `2`.
  - R4d: `awk '/^## Step 4:/,/^## Step [^4]/' skills/critical-review/SKILL.md | grep -c "Non-compliant:"` — output ≥ `1`.
  - R5a: `grep -c "State the dismissal reason briefly" skills/critical-review/SKILL.md` — output is `1`.
  - R5b: `grep -c "if your dismissal reason cannot be pointed" skills/critical-review/SKILL.md` — output ≥ `1`.
  - R5c: `grep -c "if your resolution relies" skills/critical-review/SKILL.md` — output ≥ `1`.
  - R6: `awk '/^## Step 4:/,/^## Step [^4]/' skills/critical-review/SKILL.md | grep -cE "Ask items.*(consolidate|consolidated).*(if|when).*(any remain|present)"` — output ≥ `1`.
  - R7: `git diff --name-only main.. -- skills/` — output is exactly the single line `skills/critical-review/SKILL.md`. (Note: on `integration_branch = main`, the output is empty — see Veto Surface for handling.)
  - R8: `grep -c "events\.log" skills/critical-review/SKILL.md` — output is `0`.
  - R9a: `diff <(git show main:skills/critical-review/SKILL.md | awk '/^# Critical Review$/,/^## Step 4:/ { if (!/^## Step 4:/) print }') <(awk '/^# Critical Review$/,/^## Step 4:/ { if (!/^## Step 4:/) print }' skills/critical-review/SKILL.md)` — output is empty.
  - R9b: `grep -c "^## Step 4: Apply Feedback$" skills/critical-review/SKILL.md` — output is `1`.
  - R10a: `awk '/^## Step 4:/,/^## Step [^4]/' skills/critical-review/SKILL.md | grep -c "Present a compact summary in the following format:"` — output ≥ `1`.
  - R10b: `awk '/Present a compact summary in the following format:/{s=NR} s && NR-s<=40 && /Non-compliant:/{print "ok"; exit}' skills/critical-review/SKILL.md` — output is `ok`.
- **Status**: [x] completed

### Task 2: Commit the Step 4 restructure via /commit and re-assert scope against HEAD

- **Files**: `skills/critical-review/SKILL.md`
- **What**: (a) Invoke the `/commit` skill to stage `skills/critical-review/SKILL.md` and create a single commit; do NOT bundle unrelated working-tree changes. (b) After the commit lands, re-run R1, R7, and R10's second check against the HEAD state to catch any regression between Task 1's working-tree state and the committed state (e.g., `/commit` staging additional files, amend, etc.).
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Global rule: always use `/commit`; never run `git commit` directly.
  - Scope rule: stage only `skills/critical-review/SKILL.md`. Pre-existing unrelated working-tree changes (other skills, backlog items, settings, retros, dashboard code, etc.) are not part of this commit.
  - Commit message style (from recent repo history): imperative subject ≤72 chars; optional multi-bullet body via multiple `-m` flags. Example recent subjects: `"Refine lifecycle 69: spec and plan for specify-phase narration fix"`, `"Refine lifecycle 67: research and spec for critical-review Step 4 restructure"`.
  - Suggested subject: `"Restructure critical-review Step 4: count-only Dismiss, direction-oriented Apply"`.
  - Suggested body bullets: (1) drops verbose Dismiss walkthrough, replaces with one-line count; (2) Apply bullets now describe direction of change with two-polarity worked examples; (3) preserves line 205 anchor check and all of Steps 1–3; (4) uniform behavior at all three call sites (specify §3b, plan §3b, discovery research §6b) via inheritance.
- **Verification**: All three post-commit checks must pass.
  - Commit subject format: `git log -1 --pretty=format:%s` — output matches regex `^Restructure critical-review Step 4.*` (or equivalent phrase containing `critical-review` and `Step 4`).
  - Scope re-assertion (matches spec R7 literal): `git diff --name-only main.. -- skills/` — output is exactly the single line `skills/critical-review/SKILL.md`. (Same caveat as R7: if running on `main`, output is empty; see Veto Surface.)
  - R1 re-assertion against committed tree: `grep -c "what was dismissed and why" skills/critical-review/SKILL.md` — output is `0`.
  - R10a re-assertion against committed tree: `awk '/^## Step 4:/,/^## Step [^4]/' skills/critical-review/SKILL.md | grep -c "Present a compact summary in the following format:"` — output ≥ `1`.
- **Status**: [x] completed

## Verification Strategy

End-to-end verification is Task 1's full R1–R10 battery (working tree) plus Task 2's post-commit re-assertion of R1, R7, R10a (committed tree). If all 17 Task 1 checks pass AND all 4 Task 2 checks pass, the feature is correctly shipped.

Condensed regression-sanity bundle (run once after Task 2 completes to confirm no drift between task boundaries):

```bash
# All must pass; if any fails, inspect full R1-R10 to identify the specific requirement violated.
grep -c "what was dismissed and why" skills/critical-review/SKILL.md                                            # → 0 (R1)
awk '/^## Step 4:/,/^## Step [^4]/' skills/critical-review/SKILL.md | grep -c "Dismiss: N objections"           # → ≥1 (R2a)
awk '/^## Step 4:/,/^## Step [^4]/' skills/critical-review/SKILL.md | grep -c "Present a compact summary in the following format:"  # → ≥1 (R10a)
awk '/^## Step 4:/,/^## Step [^4]/' skills/critical-review/SKILL.md | grep -c "strengthened from"               # → ≥1 (R4a)
awk '/^## Step 4:/,/^## Step [^4]/' skills/critical-review/SKILL.md | grep -cE "(inverted|reversed|relaxed|narrowed) from"  # → ≥1 (R4b)
awk '/^## Step 4:/,/^## Step [^4]/' skills/critical-review/SKILL.md | grep -c "Compliant:"                      # → ≥2 (R4c)
awk '/^## Step 4:/,/^## Step [^4]/' skills/critical-review/SKILL.md | grep -c "Non-compliant:"                  # → ≥1 (R4d)
awk '/Present a compact summary in the following format:/{s=NR} s && NR-s<=40 && /Non-compliant:/{print "ok"; exit}' skills/critical-review/SKILL.md  # → ok (R10b)
grep -c "State the dismissal reason briefly" skills/critical-review/SKILL.md                                    # → 1 (R5a)
grep -c "events\.log" skills/critical-review/SKILL.md                                                            # → 0 (R8)
grep -c "^## Step 4: Apply Feedback$" skills/critical-review/SKILL.md                                            # → 1 (R9b)
git diff --name-only main.. -- skills/                                                                          # → exactly skills/critical-review/SKILL.md (R7)
diff <(git show main:skills/critical-review/SKILL.md | awk '/^# Critical Review$/,/^## Step 4:/ { if (!/^## Step 4:/) print }') <(awk '/^# Critical Review$/,/^## Step 4:/ { if (!/^## Step 4:/) print }' skills/critical-review/SKILL.md)  # → empty (R9a)
```

This is a **regression-sanity** bundle, not a substitute for Task 1's full 17-check battery. Any failure here indicates drift between working-tree state (Task 1 verified) and committed state (Task 2 re-asserts). The full R1–R10 battery remains the authoritative pre-ship gate inside Task 1.

No runtime validation is possible in this session — `/critical-review`'s Step 4 exercises the restructured instruction only when invoked live (e.g., at the next complex-tier feature's spec §3b or plan §3b). Binary-checkable R1–R10 inside Task 1 is the pre-ship gate.

## Veto Surface

- **Canonical introducer wording**: spec R10 commits to the literal `"Present a compact summary in the following format:"`. Minor variations (e.g., `"Present a compact summary using this format:"`) will fail R10a's grep. If the user prefers different wording, the spec's R10a regex needs loosening before implementation.
- **Canonical verb-list ordering**: plan commits to `strengthened, narrowed, clarified, added, removed, inverted`. R3b's regex admits only two orderings — this one, and the reverse (`inverted ...`). Any other permutation fails R3b. If the user wants a different ordering, loosen R3b's regex in the spec.
- **Two-polarity example requirement**: R4 requires two `Compliant:` examples. If the user prefers to consolidate to a single example, R4c fails (`≥ 2`). The two-polarity defense against Opus 4.7 literalism is the design commit; removing it is a material spec change.
- **Task 2 commit-scope vacuity on `main` execution**: `runner.sh:286` supports `integration_branch = main` as a fallback. When executing on `main`, `git diff --name-only main.. -- skills/` produces empty output, which fails Task 2's "exactly the single line" assertion (and fails R7's literal). Two options: (a) explicitly require the executor to run on a feature/worktree branch, not main — this is the assumed execution environment and matches the plan's expectation; (b) extend R7 / Task 2 verification to handle both cases (branch diff OR `HEAD^..HEAD` on main). Recommendation: (a), with a pre-flight guard in Task 2 that checks `git branch --show-current` and halts if output is `main`. Not yet encoded; surface to user at approval.

## Scope Boundaries

Excluded per spec §Non-Requirements:

- No changes to Step 4 disposition framework (lines 203, 205, 207).
- No changes to the Apply bar (line 217) or the self-resolution block (line 209).
- No changes to the three call sites (`specify.md`, `plan.md`, `discovery/references/research.md`).
- No changes to `skills/lifecycle/references/clarify-critic.md` (sibling ticket #068 owns that surface).
- No events.log emission for critical-review Step 4 dispositions; no consumer code; no metrics instrumentation.
- No sub-agent dispatch for Step 4, no structured-output JSON schema.
- No per-call-site conditional logic.
- No dependency on sibling ticket #068 landing first.
