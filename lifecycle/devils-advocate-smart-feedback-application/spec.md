# Specification: devils-advocate-smart-feedback-application

## Problem Statement

`/devils-advocate` today makes a case against the current direction and stops — the user or host agent is left to manually decide which objections are worth acting on, which misread the direction, and which deserve a consolidated question. `/critical-review` has a structured Apply/Dismiss/Ask step that handles this for its heavier fresh-agent dispatch path, but `/devils-advocate` has no equivalent. Users who invoke `/devils-advocate` on a lifecycle artifact currently get a sharp critique with no mechanism for the skill to apply the clear-cut fixes or surface genuine tie-breaks. This spec adds that step — scoped strictly to the lifecycle path where an artifact exists to anchor against, and calibrated for the inline single-context execution model (default to Dismiss, require anchor-to-source for Apply).

## Requirements

<!-- MoSCoW legend: M = Must-have, S = Should-have, W = Won't-do (tracked here for boundary clarity) -->

1. **[M] New Step 3 "Apply Feedback" added to `skills/devils-advocate/SKILL.md`**: Inserted between the existing Step 2 (Make the Case) and the existing Success Criteria section. Structurally parallel to `/critical-review`'s Step 4.
   - **Acceptance**: `grep -c '^## Step 3: Apply Feedback' skills/devils-advocate/SKILL.md` = 1. Section appears between `## Step 2:` and `## Success Criteria` in file order.

2. **[M] Step 3 runs only when a lifecycle artifact was read in Step 1**: When `/devils-advocate` is invoked without an active lifecycle (Step 1's conversation-context fallback path), Step 3 is skipped and the skill behaves exactly as today — the case is made and the skill stops.
   - **Acceptance**: Step 3's opening paragraph explicitly states the lifecycle-artifact gate. `grep -c 'no lifecycle' skills/devils-advocate/SKILL.md` ≥ 1 under Step 3. Interactive/session-dependent: the no-lifecycle skip path requires runtime context (was a lifecycle artifact actually read?) that cannot be captured by file-state grep alone.

3. **[M] Three dispositions defined: Apply / Dismiss / Ask**: Definitions reproduced from `/critical-review` Step 4 (lines 197–217) **with inverted anchor semantics** — the original CR rule anchors Dismiss to artifact text; this version anchors Apply to artifact text. Default disposition is Dismiss.
   - **Acceptance**: `grep -c '^\*\*Apply\*\*' skills/devils-advocate/SKILL.md` = 1, `grep -c '^\*\*Dismiss\*\*' skills/devils-advocate/SKILL.md` = 1, `grep -c '^\*\*Ask\*\*' skills/devils-advocate/SKILL.md` = 1. Interactive/session-dependent: anchor-inversion check verifies the Apply anchor rule states "if your apply reason cannot be pointed to in the artifact text" (or semantic equivalent) — requires reading the section prose.

4. **[M] Unit of classification: one disposition per H3 section in Step 2, excluding Tradeoff Blindspot**: The three remaining sections (Strongest Failure Mode, Unexamined Alternatives, Fragile Assumption) each receive one disposition per `/devils-advocate` run. Tradeoff Blindspot is explicitly exempt from the apply loop (it produces sensibilities, not applyable fixes). If Unexamined Alternatives names multiple alternatives, the agent selects the strongest to classify — matching the skill's existing "strongest case" framing.
   - **Acceptance**: Step 3 prose names the three in-scope sections and explicitly exempts Tradeoff Blindspot with a one-sentence rationale. `grep -c 'Tradeoff Blindspot' skills/devils-advocate/SKILL.md` ≥ 2 (once in Step 2, once in Step 3 exemption).

5. **[M] Self-resolution step reproduced, adapted**: Before classifying an objection as Ask, attempt a brief self-resolution check (re-read relevant artifact sections). If verifiable evidence supports a disposition, reclassify to Apply or Dismiss. Adapted wording from `/critical-review` Step 4's self-resolution paragraph.
   - **Acceptance**: `grep -c 'self-resolution' skills/devils-advocate/SKILL.md` ≥ 1. Interactive/session-dependent: section includes the "uncertainty still defaults to Ask" guard or semantic equivalent — requires reading the section prose.

6. **[M] Apply bar preserved from CR Step 4**: Apply when and only when the fix is unambiguous and confidence is high. Uncertainty is a legitimate reason to Ask. Bias toward Dismiss for ambiguous or speculative objections.
   - **Acceptance**: `grep -c 'Apply bar' skills/devils-advocate/SKILL.md` ≥ 1 (a paragraph under that heading or label). `grep -c 'default.*[Dd]ismiss\|[Dd]ismiss.*default' skills/devils-advocate/SKILL.md` ≥ 1 within Step 3 (confirms the Dismiss bias is named explicitly in the skill text).

7. **[M] Apply mechanics: re-read artifact, apply fixes, present compact summary**: Re-read the artifact before or during classification (re-read timing is left to the agent — before classification when context was lost; during or after otherwise). Apply the Apply-classified fixes to the artifact (preserving everything not touched). Present a compact summary naming what was changed (one line per fix), what was dismissed and why, and any Ask items as a single consolidated message.
   - **Acceptance**: Step 3 prose describes the re-read / apply / summary sequence and allows re-read ordering flexibility. Interactive/session-dependent: the sequence involves runtime artifact state not capturable by grep alone.

8. **[M] Inline framework with explicit inversion callout**: A one-paragraph preamble at the top of Step 3 names the source pattern (CR Step 4) AND the intentional inversion ("INVERTED anchor semantics: CR anchors Dismiss-to-artifact; this step anchors Apply-to-artifact. Changes to CR Step 4 must not be propagated here verbatim."). This warns future editors against silent drift.
   - **Acceptance**: `grep -c 'INVERTED' skills/devils-advocate/SKILL.md` = 1. `grep -c 'not be propagated' skills/devils-advocate/SKILL.md` ≥ 1 or semantic equivalent present.

9. **[M] "Stop after making the case" section preserved verbatim**: The existing "What This Isn't" section (lines 92–94 of the current file) is NOT modified. Step 3 is inserted above Success Criteria, and "What This Isn't" remains at the end of the file with the original text. The final behavioral guard against re-argument stays intact.
   - **Acceptance**: All four load-bearing phrases from the pre-implementation "What This Isn't" section appear unchanged: `grep -c 'Stop after making the case' skills/devils-advocate/SKILL.md` = 1, `grep -c "Don't repeat objections after they've been acknowledged" skills/devils-advocate/SKILL.md` = 1, `grep -c "Don't negotiate or defend your position" skills/devils-advocate/SKILL.md` = 1, `grep -c 'Not a blocker' skills/devils-advocate/SKILL.md` = 1.

10. **[M] Step 3 accommodates Step 2's existing output**: Step 3 does not require Step 2 to emit bulleted objections or change its prose format. Step 2 continues to produce 4 H3 prose sections exactly as it does today; Step 3 reads those sections and classifies them.
    - **Acceptance**: All four Step 2 H3 headers present and unmodified: `grep -c '^### Strongest Failure Mode' skills/devils-advocate/SKILL.md` = 1, `grep -c '^### Unexamined Alternatives' skills/devils-advocate/SKILL.md` = 1, `grep -c '^### Fragile Assumption' skills/devils-advocate/SKILL.md` = 1, `grep -c '^### Tradeoff Blindspot' skills/devils-advocate/SKILL.md` = 1.

11. **[M] Post-change description distinction and apply-loop surfacing**: The frontmatter `description:` field remains clearly distinct from `/critical-review`'s description AND mentions the apply-loop behavior (e.g., "applies clear-cut fixes in lifecycle mode" or semantic equivalent). This is the canonical place for the user-facing capability change to surface — not just the downstream docs.
    - **Acceptance**: `grep 'description:' skills/devils-advocate/SKILL.md` returns a line that (a) includes "inline" (or semantic equivalent naming the single-context execution model), (b) mentions the apply-loop behavior in some form (keywords like "apply", "fix", "dispositions", or equivalent), and (c) does NOT include any phrase that also appears verbatim in `grep 'description:' skills/critical-review/SKILL.md`.

12. **[S] Documentation update**: The `/devils-advocate` entries in `docs/skills-reference.md` and `docs/agentic-layer.md` reflect the new lifecycle-path behavior. A one-line note is sufficient.
    - **Acceptance**: `grep -c 'Apply\|Dismiss\|Ask\|dispositions\|apply loop' docs/skills-reference.md` ≥ 1 within the `/devils-advocate` entry. `grep -c 'Apply\|Dismiss\|Ask\|dispositions\|apply loop' docs/agentic-layer.md` ≥ 1 within the `/devils-advocate` row or entry.

13. **[M] Surgical write semantics, not full-file rewrite**: Apply fixes use surgical text replacement (i.e., the Edit tool's old_string → new_string pattern, or equivalent), NOT full-file Write. This preserves YAML frontmatter, code fences, wikilinks, and plan.md checkbox state byte-exactly outside the specific text being replaced, and avoids mid-write truncation corrupting the lifecycle artifact.
    - **Acceptance**: Step 3 prose explicitly states that Apply fixes use surgical replacement (Edit-tool style) and explicitly forbids full-file rewrite. `grep -c 'surgical\|Edit tool\|old_string' skills/devils-advocate/SKILL.md` ≥ 1 within Step 3. Interactive/session-dependent: the skill prose must name the mechanism; a grep alone cannot verify the semantic claim.

14. **[M] Abort conditions named in Step 3**: Step 3 explicitly states three abort conditions where the apply loop halts and the skill presents the case-as-made only: (a) the artifact has been modified by another session between Step 1 and Step 3's re-read; (b) the artifact cannot be re-read at Step 3 time (deleted, path changed, permission error); (c) the host agent's context no longer contains the Step 1 read and a re-read is required before classification. All three conditions are named in the skill prose, not just in this spec.
    - **Acceptance**: `grep -ci 'abort' skills/devils-advocate/SKILL.md` ≥ 1 within Step 3. Interactive/session-dependent: the three specific conditions are named in prose — verified by reading the section. (Grep count alone cannot confirm all three conditions are enumerated.)
    - **Acceptance**: `grep -c 'Apply\|Dismiss\|Ask\|dispositions' docs/skills-reference.md` ≥ 1 within the `/devils-advocate` entry. `grep -c 'Apply\|Dismiss\|Ask\|dispositions' docs/agentic-layer.md` ≥ 1 within the `/devils-advocate` row or entry.

## Non-Requirements

- **No fresh-agent dispatch, no parallel reviewers, no Opus synthesis**: Devils-advocate remains inline single-context. The apply loop runs in the host agent's context, not a dispatched subagent's.
- **No Project Context loading step analogous to CR §2a**: The inline execution model means the host agent already has whatever project context it needs. Adding a pre-load step duplicates work and bloats the skill.
- **No apply loop in the no-lifecycle (conversation-context) path**: When no lifecycle artifact was read in Step 1, Step 3 is skipped entirely. The no-lifecycle path behaves exactly as today.
- **No revision of "What This Isn't"**: The line "Stop after making the case" is preserved verbatim from the consolidate-devils-advocate-critical-review lifecycle. This spec does not re-open that decision.
- **No restructuring of Step 2**: The 4-section H3 prose output established by the consolidate lifecycle is preserved exactly. Step 2's existing language is not modified.
- **No third shared reference file for the Apply/Dismiss/Ask framework**: The framework is inlined into `skills/devils-advocate/SKILL.md` with an explicit inversion callout. Creating a shared reference would require unifying with `/critical-review` and `clarify-critic.md` — out of scope for this spec and blocked by the inversion anyway.
- **No per-objection classification within a section**: Unexamined Alternatives stays at one disposition even when the section names multiple alternatives. The agent picks the strongest alternative to classify.
- **No auto-trigger in the lifecycle**: `/devils-advocate` remains a manually-invoked skill. This spec does not change when the skill runs.

## Edge Cases

- **Artifact changed between Step 1 and Step 3**: If the host agent notices during the Step 3 re-read that the artifact has been modified since Step 1 (e.g., by another session), it must abort the apply loop and present the case-as-made only. The apply loop assumes a stable target. Operationally: Step 3's re-read compares against its Step 1 read; material changes trigger abort. (Rare case — devils-advocate runs in a single turn, but coverage belongs in Step 3 prose.)
- **All three in-scope sections classify as Dismiss**: Step 3 still produces its compact summary ("dismissed these N: [reasons]"). The artifact is not modified. The user sees which objections were dismissed and why — this is the value of the apply loop even when no Apply fires.
- **All three in-scope sections classify as Ask**: Step 3 produces only the consolidated Ask list. The artifact is not modified. The user receives a single question-bundle.
- **Host agent loses artifact context before Step 3**: If the host agent's context window is under pressure and the original artifact read has been compacted out, Step 3 must re-read the artifact from disk before classifying — the skill cannot trust in-memory state to be current.
- **Artifact not found at Step 3 re-read time**: The artifact existed in Step 1 but cannot be re-read (e.g., file deleted, path changed). Abort the apply loop, present the case-as-made, and surface the read failure as a one-line note.
- **Apply would produce a no-op change**: If the concrete fix proposed by an Apply disposition turns out to already be present in the artifact (the agent initially missed it), reclassify as Dismiss because the artifact already contains the fix. Do not phrase this as "anchoring Dismiss to artifact text" — that would reintroduce the CR-style Dismiss-to-artifact rule. The inversion (Apply-anchors-to-artifact) is preserved; this case is a no-op short-circuit, not an anchor inversion.
- **Conversation-context invocation**: Step 3 is skipped. The skill output is identical to today's behavior (4 H3 sections, stop). No dispositions, no summary.
- **Step 2 produces a section that is entirely speculative** (e.g., Strongest Failure Mode with no concrete anchor): The default-to-Dismiss rule fires — the objection is Dismissed with the dismissal reason naming the absence of concrete anchor text. The artifact is not modified. This is the expected behavior, not a degenerate case.

## Changes to Existing Behavior

- **MODIFIED**: `/devils-advocate` invoked with an active lifecycle now runs a post-case apply loop that may edit the lifecycle artifact. Previously, the skill made the case and stopped regardless of lifecycle presence.
- **ADDED**: Step 3 "Apply Feedback" section in `skills/devils-advocate/SKILL.md`.
- **UNCHANGED**: `/devils-advocate` invoked without an active lifecycle behaves exactly as today.
- **UNCHANGED**: Step 2 (Make the Case) and its 4 H3 sections remain verbatim.
- **UNCHANGED**: "What This Isn't" section remains verbatim. "Stop after making the case" is preserved.

## Technical Constraints

- **Lifecycle artifact anchor is well-defined**: The apply target is the file read in Step 1 (`lifecycle/{feature}/plan.md`, `spec.md`, or `research.md`). The anchor universe is that file's text. Rewrites preserve everything not touched by an Apply fix.
- **The inversion is intentional and load-bearing**: `/critical-review`'s anchor check anchors Dismiss to artifact text because its default is to Apply. Devils-advocate's anchor check anchors Apply to artifact text because its default is Dismiss. The inversion is semantically meaningful — propagating a CR Step 4 change verbatim into Step 3 would break the rule.
- **Single-context anchoring has acknowledged limits**: Research surfaced literature (arXiv 2412.06593, Huang et al. 2310.01798) showing that prompt-level instructions cannot fully mitigate anchoring bias in single-context self-review. The calibration reduces bias but does not eliminate it. Users wanting a structural fresh-agent review should invoke `/critical-review` instead.
- **No dependency on Project Context**: Step 3 does not read `requirements/project.md` or `lifecycle.config.md`. It relies on the host agent's existing context.
- **No new file writes outside the artifact being applied-to**: Step 3 does not create, move, or delete any file. The only writes are surgical text replacements within the lifecycle artifact read in Step 1 (Edit-tool style — see R13). No full-file rewrites.
- **Skill symlink deployment**: Changes to `skills/devils-advocate/SKILL.md` take effect immediately via the `skills/ → ~/.claude/skills/` symlink. No deploy step, no settings update.

## Open Decisions

None. All design decisions have been resolved at spec time based on research findings and the user's scope choice (lifecycle-only apply). The remaining implementation decisions (exact section wording, exact line placements) are implementation-level and resolved during the Plan phase.
