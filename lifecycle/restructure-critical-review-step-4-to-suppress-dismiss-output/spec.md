# Specification: restructure-critical-review-step-4-to-suppress-dismiss-output

Epic context: [`research/audit-interactive-phase-output-for-decision-signal/research.md`](../../research/audit-interactive-phase-output-for-decision-signal/research.md) (DR-2, DR-4). This spec implements a single-file, single-block edit; epic-wide concerns are out of scope.

## Problem Statement

`/critical-review` Step 4's current compact-summary instruction (line 215 of `skills/critical-review/SKILL.md`) requires three things — "what was changed (one line per fix), what was dismissed and why, and — only if any remain — ask about 'Ask' items." The Dismiss-reporting requirement produces verbose disposition walkthroughs in practice, especially under Claude Opus 4.7's increased instruction literalism. Apply items have already been written into the artifact and need no user action; Dismiss items are internal bookkeeping; only Ask items require user input. The restructured instruction replaces the verbose walkthrough with a one-line Dismiss count (preserving anchor-check live-signal pressure) and specifies direction-oriented Apply bullets with a worked example (defending against Opus 4.7 literalism collapsing bullets to location-only form). Ships independently of sibling ticket #068.

## Requirements

**MoSCoW classification**: All requirements R1–R10 below are Must-have for this ticket. There are no Should-have or Could-have items; the ticket is tightly scoped to the Step 4 restructure. Non-requirements (Dismiss-to-events.log capture, anchor-check tightening, per-call-site conditional logic, sibling ticket coupling) are explicitly Won't-have and listed in the Non-Requirements section below.

**Acceptance-criteria convention**: Unless noted otherwise, grep commands are scoped to the Step 4 block of `skills/critical-review/SKILL.md` using the awk range `awk '/^## Step 4:/,/^## Step [^4]/'`. This scopes checks to content between the Step 4 heading and the next top-level Step heading, preventing false-pass via phrases appearing elsewhere in the file.

1. **R1 — Remove "what was dismissed and why" from `SKILL.md`**: The phrase must no longer appear anywhere in the file.
   - Acceptance: `grep -c "what was dismissed and why" skills/critical-review/SKILL.md` — pass if output is `0`.

2. **R2 — Replace with count-only Dismiss line (with explicit N = 0 omission)**: The Step 4 compact-summary instruction must specify that, when N > 0 objections were dismissed, the compact summary includes a single line reporting the count ("Dismiss: N objections"). When N = 0, no Dismiss line appears.
   - Acceptance: `awk '/^## Step 4:/,/^## Step [^4]/' skills/critical-review/SKILL.md | grep -c "Dismiss: N objections"` — pass if output ≥ `1` (the canonical literal must appear inside the Step 4 block).
   - Acceptance: `awk '/^## Step 4:/,/^## Step [^4]/' skills/critical-review/SKILL.md | grep -cE "[Oo]mit.*Dismiss.*line.*when.*(N = 0|N=0|zero|count is 0)"` — pass if output ≥ `1` (the N = 0 omission semantic must be explicit in the Step 4 block).

3. **R3 — Apply reporting specifies direction-oriented bullets**: The Step 4 compact-summary instruction must include a sentence stating that Apply bullets describe the direction of the change, adjacent to a verb list containing at least strengthened, narrowed, clarified, added, removed, inverted.
   - Acceptance: `awk '/^## Step 4:/,/^## Step [^4]/' skills/critical-review/SKILL.md | grep -cE "Apply bullets.*(direction of the change|describe.*direction)"` — pass if output ≥ `1` (phrase must govern the Apply-bullet spec, not just appear loose in the block).
   - Acceptance: `awk '/^## Step 4:/,/^## Step [^4]/' skills/critical-review/SKILL.md | grep -cE "strengthened.*narrowed.*(clarified|added|removed).*inverted|inverted.*(strengthened|narrowed|clarified|added|removed)"` — pass if output ≥ `1` (the verb list including "inverted" must appear as a single contiguous list).

4. **R4 — Include two-polarity worked examples plus counter-example**: The Step 4 block must contain two compliant worked examples demonstrating different polarities (one tightening/strengthening and one loosening/inversion/narrowing/relaxation) and at least one non-compliant counter-example. Opus 4.7 literalism pattern-matches from a single example; two polarities defend against the one-direction failure mode.
   - Acceptance: `awk '/^## Step 4:/,/^## Step [^4]/' skills/critical-review/SKILL.md | grep -c "strengthened from"` — pass if output ≥ `1` (tightening example).
   - Acceptance: `awk '/^## Step 4:/,/^## Step [^4]/' skills/critical-review/SKILL.md | grep -cE "(inverted|reversed|relaxed|narrowed) from"` — pass if output ≥ `1` (loosening, inversion, or narrowing example).
   - Acceptance: `awk '/^## Step 4:/,/^## Step [^4]/' skills/critical-review/SKILL.md | grep -c "Compliant:"` — pass if output ≥ `2` (at least two Compliant example markers, one per polarity).
   - Acceptance: `awk '/^## Step 4:/,/^## Step [^4]/' skills/critical-review/SKILL.md | grep -c "Non-compliant:"` — pass if output ≥ `1` (counter-example marker).

5. **R5 — Line 205's Dismiss description + Anchor check are preserved verbatim**: The line-205 Anchor check and the line-209 self-resolution Anchor check must both survive, anchored by their specific distinguishing phrases.
   - Acceptance: `grep -c "State the dismissal reason briefly" skills/critical-review/SKILL.md` — pass if output is `1`.
   - Acceptance: `grep -c "if your dismissal reason cannot be pointed" skills/critical-review/SKILL.md` — pass if output ≥ `1` (line-205 Anchor check distinguishing phrase).
   - Acceptance: `grep -c "if your resolution relies" skills/critical-review/SKILL.md` — pass if output ≥ `1` (line-209 self-resolution Anchor check distinguishing phrase).

6. **R6 — Ask items consolidate only when any remain**: The restructured Step 4 compact-summary instruction must explicitly tie Ask items to the consolidated-when-present semantic.
   - Acceptance: `awk '/^## Step 4:/,/^## Step [^4]/' skills/critical-review/SKILL.md | grep -cE "Ask items.*(consolidate|consolidated).*(if|when).*(any remain|present)"` — pass if output ≥ `1` (phrase must appear inside the Step 4 block governing the Ask behavior).

7. **R7 — Only `skills/critical-review/SKILL.md` is modified**: No other files in `skills/` are edited. In particular, `skills/lifecycle/references/specify.md`, `skills/lifecycle/references/plan.md`, and `skills/discovery/references/research.md` (the three call sites) are NOT modified.
   - Acceptance: `git diff --name-only main.. -- skills/` — pass if output is exactly the single line `skills/critical-review/SKILL.md`.

8. **R8 — No events.log emission is added**: The edit must not introduce any new events.log reference in `SKILL.md`.
   - Acceptance: `grep -c "events\.log" skills/critical-review/SKILL.md` — pass if output is `0` (baseline count before edit is 0; must remain 0 after).

9. **R9 — Steps 1, 2, and 3 of `/critical-review` are byte-identical pre- and post-edit**: Only Step 4 is edited. The reviewer-dispatch logic (Step 2c), synthesis logic (Step 2d), and present step (Step 3) are unchanged. The Step 4 heading itself is preserved verbatim so the awk ranges in R2/R3/R4/R6/R10 remain stable.
   - Acceptance: `diff <(git show main:skills/critical-review/SKILL.md | awk '/^# Critical Review$/,/^## Step 4:/ { if (!/^## Step 4:/) print }') <(awk '/^# Critical Review$/,/^## Step 4:/ { if (!/^## Step 4:/) print }' skills/critical-review/SKILL.md)` — pass if the diff output is empty (content from the title through the last line before the Step 4 heading is byte-identical).
   - Acceptance: `grep -c "^## Step 4: Apply Feedback$" skills/critical-review/SKILL.md` — pass if output is `1` (the Step 4 heading is preserved verbatim).

10. **R10 — Restructured compact-summary instruction is a single coherent anchored block**: The new compact-summary format appears as a contiguous passage in the Step 4 block, introduced by a canonical anchor sentence.
    - Acceptance: `awk '/^## Step 4:/,/^## Step [^4]/' skills/critical-review/SKILL.md | grep -c "Present a compact summary in the following format:"` — pass if output ≥ `1` (a canonical introducer sentence anchors the new format block).
    - Acceptance: The canonical introducer and the content governed by R2 (Dismiss count line), R3 (direction sentence + verb list), R4 (worked examples and counter-example), and R6 (Ask consolidation clause) must all appear within 40 consecutive lines of the Step 4 block. Verified by: `awk '/Present a compact summary in the following format:/{s=NR} s && NR-s<=40 && /Non-compliant:/{print "ok"; exit}' skills/critical-review/SKILL.md` — pass if output is `ok` (the anchor sentence and the counter-example marker appear within 40 lines of each other; since R4, R3, R6, R2 all require their literals inside the Step 4 block and R10's first criterion anchors the canonical introducer, this check establishes block contiguity).

## Non-Requirements

- No changes to the Step 4 disposition framework (Apply/Dismiss/Ask definitions at lines 203, 205, 207).
- No changes to the Apply bar section (line 217).
- No changes to the self-resolution block at line 209 (second Anchor check, for Ask classification).
- No changes to any of the three call sites (`specify.md:150`, `plan.md:243`, `discovery/references/research.md:128`).
- No changes to `skills/lifecycle/references/clarify-critic.md` (sibling ticket #068 owns that surface).
- No schema extensions or consumer code added for `critical_review` events.log entries. The existing inconsistent `critical_review` event emission is left as-is.
- No new sub-agent dispatch, no structured-output JSON schema for Step 4 dispositions.
- No per-call-site conditional logic in Step 4. All three invocation sites receive identical output format.
- No monitoring or telemetry instrumentation added as part of this ticket.
- Does not depend on sibling ticket #068 landing first; ships independently.

## Edge Cases

- **All Ask, zero Apply, zero Dismiss**: Step 4 output is the consolidated Ask-items message only. No Apply bullet block, no Dismiss count line.
- **All Apply, zero Dismiss, zero Ask**: Step 4 output is the Apply bullet block only. No Dismiss count line (N=0 → omit), no Ask message.
- **Zero Apply, N Dismiss, zero Ask**: Step 4 output is the single "Dismiss: N objections" count line. No Apply block, no Ask message.
- **High-N Dismiss count (e.g., 15)**: Step 4 output is still one line: "Dismiss: 15 objections". Orchestrator does not volunteer details; user can ask if the count is suspicious.
- **Apply fix is a semantic inversion (MUST→SHOULD, narrowing, polarity reversal)**: Direction verb ("inverted", "reversed", "relaxed", "strengthened") is required — not "updated" or "modified." The worked example in SKILL.md must cover this case.
- **Apply fix adds a new acceptance criterion**: Bullet reads "Added acceptance criterion to R5: [brief description]" — the direction verb is "added" plus the target scope (which requirement). Not "R5 updated."
- **No objections raised at all** (synthesis was clean): Step 4 produces no output. The artifact was unchanged; there is nothing to report.
- **Step 2c total failure fallback was used**: Step 4 runs against the raw fallback-agent findings (no synthesis). The same compact-summary format applies — count-only Dismiss, direction-oriented Apply, Ask consolidated.

## Changes to Existing Behavior

- MODIFIED: `/critical-review` Step 4's compact-summary instruction (line 215 of `skills/critical-review/SKILL.md`). Old: "Present a compact summary: what was changed (one line per fix), what was dismissed and why, and — only if any remain — ask about 'Ask' items in a single consolidated message." New: an instruction specifying direction-oriented Apply bullets (with a worked example), a one-line Dismiss count when N > 0 (omitted when N = 0), and consolidated Ask items only when present. Applies uniformly to all three call sites (specify §3b, plan §3b, discovery research §6b) by inheritance — no call-site edits.

## Technical Constraints

- **Opus 4.7 instruction literalism**: Positive format specification is more reliable than negative prohibition. The edit specifies the new format positively (what Step 4 SHOULD produce), rather than prohibiting the old output. Verified from Anthropic's Claude 4 best-practices guide.
- **DR-4 (mechanism distinction)**: The edit operates at the requirement surface — what the instruction requires — not as a "be briefer" behavioral nudge. Consistent with the epic's research finding.
- **No consumer for `critical_review` events.log entries**: Verified via grep of `claude/overnight/report.py` and `claude/pipeline/metrics.py` — zero consumers. Adding events.log capture in this ticket would produce a write-only log with no audit value; explicitly excluded per R8.
- **Call-site consumption inheritance**: The three call sites (`specify.md:150`, `plan.md:243`, `discovery/references/research.md:128`) all invoke `/critical-review` and surface its Step 4 output to the user. Editing Step 4 alone propagates to all three. Confirmed by codebase agent.
- **Anchor-check live-signal preservation**: The count-only Dismiss line ("Dismiss: N objections") preserves enough user-visible signal that an orchestrator anchoring on memory rather than artifact text can be caught when N is surprising. Full silence would remove this signal; count-only is the minimum.

## Open Decisions

None.
