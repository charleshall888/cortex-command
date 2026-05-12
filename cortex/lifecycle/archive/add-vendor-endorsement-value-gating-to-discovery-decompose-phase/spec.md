# Specification: Add vendor-endorsement value gating to /discovery decompose phase

> **Epic context**: Scoped from [research/audit-and-improve-discovery-skill-rigor/research.md](../../research/audit-and-improve-discovery-skill-rigor/research.md) (Approach C, DR-1(c)). Companion to #138 (complete) which codified the `[premise-unverified: not-searched]` signal in `skills/discovery/references/research.md`. DR-1(c) selected rule edits (A+C) and rejected mechanical grounding (Approach F) — the residual self-referential failure mode identified in this spec's N5 is an accepted consequence of that choice, not a bug to be fixed within this ticket.

## Problem Statement

The `/discovery` decompose phase lets work items whose Value rests on vendor guidance or external endorsement pass the user-approval step at `skills/discovery/references/decompose.md:29` even when the codebase premise is unverified. Ticket #092 closed `wontfix` because a vendor quote ("endorsed by Anthropic's 4.7 migration guide") was accepted as sufficient Value while the underlying codebase target did not exist. Every existing post-hoc check passed clean. This spec closes the authoring-and-approval path by two paired moves: (1) an authoring-time norm (R1) and (2) a detection-and-ack gate (R2/R3) that fires when the research artifact's basis for a Value claim is thin. The gate is not foolproof — a synthesis agent that fabricates plausible citations still evades it (N5) — but it converts the #092 failure class from "slips silently past a batch-approval step" into "requires either a disciplined agent or a documented fabrication event," which is the strongest move available within DR-1(c)'s rule-edit scope.

### Worked trace: #092 under the revised rule

- #092's Value: "endorsed by Anthropic's 4.7 migration guide."
- **R1 (norm)** instructs the agent that vendor/best-practice endorsement is not sufficient Value alone.
- **R2(a)** asks the agent to produce a `[file:line]` grounding the Value claim in *this* codebase. The #092 target ("After every 3 tool calls, summarize progress" scaffolding) did not exist anywhere in the codebase. A disciplined agent fails to cite and flags per R2(a). An agent that fabricates a plausible-looking citation evades R2(a) — this is the residual N5 path, explicitly accepted per DR-1(c).
- **R2(b)** checks `research/opus-4-7-harness-adaptation/research.md` for either `[premise-unverified: not-searched]` adjacent to the Value claim (absent pre-#138) or absence of `[file:line]` citation within the Value-supporting research section. The original research's locator was projected by inference, but citation-shaped tokens exist in that section — the "absence of citation" branch does not fire reliably. This path is disclosed in TC6 as a lexical-statistic limitation.
- **Net effect**: A disciplined agent flags via R2(a). An undisciplined agent that produces any `[file:line]` token evades, but the R1 norm moves the failure from silent-and-accepted to requires-explicit-fabrication. The user-ack in R3 (on the R2(a)-flag path) adds an explicit per-item pause with item-specific rationale, which the batch-approval-only path lacked.

## Requirements

All R1–R9 are must-have for feature completion — removing any one breaks the spec's stated intent (see Non-Requirements for explicit won't-do boundaries). There are no should-have items in this rule edit.

1. **R1 — Authoring-time norm (M5)** at `skills/discovery/references/decompose.md`: Add a one-line constraint stating vendor guidance, best practices, and industry standards are not sufficient Value on their own — the Value field must state what problem this solves in *this* codebase.
   - Acceptance: `grep -c "not sufficient Value" skills/discovery/references/decompose.md` ≥ 1.

2. **R2 — Flag detection at §2 Value field** (`decompose.md:23` region): For every work item, the agent must attempt both checks below; the item is **flagged** when EITHER check indicates a concern.
   - **R2(a) — Local grounding check**: The agent must produce a `[file:line]` citation in *this* codebase that grounds the Value claim (what problem this solves here). If the agent cannot produce such a citation — because the target does not exist, the agent's search was inconclusive, or the Value rests on a premise that is not codebase-local — the item is flagged.
   - **R2(b) — Research-side premise check**: The agent must consult `research/{topic}/research.md` for the section substantiating this Value claim. The item is flagged when either (i) a `[premise-unverified: not-searched]` marker appears adjacent to the Value-supporting claim (per #138's signal), OR (ii) no `[file:line]` citation appears within the same research section/bullet as the Value-supporting claim. Per TC6, this is a lexical check; it catches citation-absence but not citation-incorrectness.
   - **Surface-pattern helper (non-gating hint)**: As a prompt-level aid, flag items whose Value prose matches vendor/external-endorsement language — named vendors (e.g., "Anthropic says", "CrewAI docs", "vendor X recommends"), industry-authority phrasings (e.g., "industry best practice", "canonical pattern in $framework", "the recommended approach", "current conventions suggest", "standard pattern", "widely adopted", "accepted convention"). This list is non-exhaustive; the agent should treat the pattern family — external authority cited in place of codebase grounding — as a reason to apply R2(a)/R2(b) with extra care. A surface-pattern match alone does **not** flag the item; flagging still requires R2(a) or R2(b) to indicate a concern.
   - Acceptance: `grep -c "\[file:line\]" skills/discovery/references/decompose.md` ≥ 1 AND `grep -c "premise-unverified" skills/discovery/references/decompose.md` ≥ 1 AND `grep -c "canonical pattern\|best practice\|recommended" skills/discovery/references/decompose.md` ≥ 1.

3. **R3 — Per-item acknowledgment with item-specific content** at `decompose.md:29`: When any work items are flagged per R2, modify the user-approval step so flagged items are presented one at a time via `AskUserQuestion`. Each acknowledgment prompt must (a) quote the proposed Value string verbatim, (b) state the specific unverified premise: which branch of R2 flagged the item (R2(a)-no-grounding or R2(b)-research-absent), and for merged items that inherited a flag via R5, quote the originating input's Value + premise so the ack shows the basis of the flag, (c) offer at minimum three choices: "Acknowledge and proceed," "Drop this item," and "Return to research." Unflagged items continue through the existing batch-review flow.
   - Acceptance: `grep -c "AskUserQuestion" skills/discovery/references/decompose.md` ≥ 1; protocol text describes quoting Value + premise in the prompt AND surfacing origin for merged items; three choices enumerated.

4. **R4 — Cap-and-escalate** at the user-approval step: The cap fires when EITHER (i) more than 3 items are flagged in the **pre-consolidation** set, OR (ii) all items are flagged and N ≥ 2. When the cap fires, skip per-item pauses and halt with a single escalation: "{N} of {total} flagged items (pre-consolidation) — recommend re-running research with premise verification." The user may choose "return to research" or "proceed anyway" (which resumes the per-item ack flow). This evaluates on the **pre-consolidation** count so that §3 merges cannot reduce the cap signal; the user's research-quality signal is preserved regardless of how §3 reshapes the item list.
   - Acceptance: `grep -c "pre-consolidation\|before Consolidation" skills/discovery/references/decompose.md` ≥ 1 AND `grep -c "more than 3\|all items are flagged" skills/discovery/references/decompose.md` ≥ 1.

5. **R5 — Flag propagation across §3 Consolidation**: If any input item to a §3 Consolidation merge carried a flag per R2, the merged output item carries the flag, for R3 ack-display purposes only. The R4 cap is evaluated on the **pre-consolidation** flag count (not the post-consolidation count). When an unflagged item is consolidated with a flagged one, the merged item's R3 ack prompt must surface the originating flagged input's Value + premise (per R3(b) above) so the user sees the actual basis of the flag — not a generic warning on an item whose Value may now be partially grounded.
   - Acceptance: `grep -c "merged item carries the flag\|flag propagat" skills/discovery/references/decompose.md` ≥ 1 AND text specifies the ack shows the originating input.

6. **R6 — No disruption to unflagged path**: Work items that are not flagged (the common case, including legitimate vendor-guided work with grounded codebase premise) continue through the existing batch user-approval step at `decompose.md:29` unchanged.
   - Acceptance: the existing batch-review instruction at `decompose.md:29` remains present: `grep -c "Present the proposed work items" skills/discovery/references/decompose.md` ≥ 1.

7. **R7 — Event logging for flag, acknowledgment, and drop events**: When flagging occurs, when the user acknowledges a flagged item, or when the user drops a flagged item, append an event to the active discovery topic's event stream (the same stream used by `orchestrator-review.md:22-30`). Event shapes:
   - `{"ts": "<ISO 8601>", "event": "decompose_flag", "phase": "decompose", "item": "<title>", "reason": "<R2(a)|R2(b)|both>", "details": "<short>"}`
   - `{"ts": "<ISO 8601>", "event": "decompose_ack", "phase": "decompose", "item": "<title>"}`
   - `{"ts": "<ISO 8601>", "event": "decompose_drop", "phase": "decompose", "item": "<title>", "reason": "<R2 basis from flag event>"}`
   If no event stream exists for the topic, skip silently — do not create new infrastructure.
   - Acceptance: `grep -c "decompose_flag" skills/discovery/references/decompose.md` ≥ 1 AND `grep -c "decompose_ack" skills/discovery/references/decompose.md` ≥ 1 AND `grep -c "decompose_drop" skills/discovery/references/decompose.md` ≥ 1. Runtime verification: Interactive/session-dependent.

8. **R8 — Tests**: Update or add a test that exercises the flag/ack rule. Minimum: a protocol-level test that parses the updated `decompose.md` and asserts the rule text for R1–R7 is present (grep assertions on the strings named in each R's acceptance row). Run `just test` and confirm exit 0.
   - Acceptance: `just test` exits 0.

9. **R9 — Dropped-items subsection in §6 Decomposition Record**: Extend `research/{topic}/decomposed.md` schema to include a `## Dropped Items` subsection listing each item the user dropped at R3's ack prompt: title, reason (R2 branch that flagged it), and the originating Value string. If no items were dropped, omit the subsection. This closes the silent-scope-shift gap where a re-run of /discovery on the same topic cannot detect that a premise-failed item was already considered and rejected.
   - Acceptance: `grep -c "Dropped Items\|## Dropped" skills/discovery/references/decompose.md` ≥ 1.

## Non-Requirements

- **N1**: No changes to `/discovery` orchestration (SKILL.md, clarify.md, research.md, orchestrator-review.md, auto-scan.md) beyond reading existing `[premise-unverified: not-searched]` markers from research.md. The companion change in research.md was shipped by #138.
- **N2**: No extension of gating into `/lifecycle`, `/refine`, or the overnight pipeline. Discovery stops at ticket creation.
- **N3**: No new persistent files, backlog frontmatter fields, or durable artifacts beyond the existing `research/{topic}/decomposed.md` schema extension (R9). Ephemeral in-run state (e.g., pre- vs post-consolidation flag counts held in the decompose run's working memory) is permitted per TC1.
- **N4**: No mechanical/automated grounding verifier (Approach F from the epic — deferred by DR-1(c)).
- **N5**: **No fix for the self-referential detection limitation** — an agent that fabricates plausible `[file:line]` citations in R2(a), or that produces citation-shaped tokens in research.md that are lexically present but semantically wrong, still passes the gate. This is the dominant residual risk and is accepted out-of-scope per epic DR-1(c). The R1 authoring-time norm partially shifts the failure mode (from silent-accepted vendor-endorsement to explicit-fabrication), but the synthesis agent that accepted vendor framing in #092 can still evade by generating a plausible-looking citation. Future escalation path is Approach F (mechanical grounding), which is out of scope for this ticket.
- **N6**: No retroactive auditing of existing backlog tickets for premise-weakness (epic Q1 caveat — out of scope for this rule edit).

## Edge Cases

- **E1 — Pre-#138 research.md artifacts** (no `[premise-unverified: not-searched]` markers present): R2(b) falls back to the "absence of `[file:line]` citation within the same research section" branch. **Note the base-rate**: per research-phase grep, the `[premise-unverified]` marker currently appears in ~1 of 26 existing artifacts. This means the absence-of-citation branch is the **primary path** for almost all current /discovery inputs, not a legacy fallback — it will remain so until #138's marker adoption saturates the research corpus.
- **E2 — Research.md with grep-positive but stale or wrong citations**: R2(b)'s second branch only checks citation *presence*, not *correctness* (per TC6). A research.md section with a `[file:line]` citation that points to a deleted or irrelevant file passes R2(b). This is an acknowledged limitation of the lexical approach; R2(a)'s local-grounding requirement at decompose time provides the second layer.
- **E3 — Single-item decomposition with one flagged item**: Per-item ack runs once via AskUserQuestion. R4 cap does not fire (N=1 → all-flagged branch requires N≥2).
- **E4 — All items flagged** (e.g., 3 of 3 or 5 of 5): R4 fires via the all-flagged-and-N≥2 branch; halt and escalate rather than per-item ack.
- **E5 — Flagged item consolidated with unflagged item at §3**: Merged item carries the flag per R5 for ack-display purposes. The R3 ack prompt quotes the originating flagged input's Value + premise so the user sees the actual basis, not a generic warning. The R4 cap evaluates on the pre-consolidation flag count — consolidation cannot launder the research-quality signal.
- **E6 — User chooses "Drop this item" at the ack prompt**: The item is dropped from the decomposition (no backlog ticket created), a `decompose_drop` event is logged per R7, and the item is recorded in §6 Decomposition Record's Dropped Items subsection per R9. Other items (flagged or unflagged) continue.
- **E7 — User chooses "Return to research"**: Halt decomposition (do not proceed to §5 ticket creation). Equivalent to the existing decline-at-decompose.md:29 behavior, but triggered from an ack prompt rather than the batch-approval step.
- **E8 — Ambiguous Value language** (e.g., "aligns with the direction the team is taking"): Does not match a surface-pattern helper hint. R2(a) and R2(b) still apply — if the agent cannot produce a local `[file:line]` or if research.md lacks citation in the relevant section, the item is flagged. The surface-pattern helper is advisory; the gate hinges on R2(a)/R2(b), which are content-agnostic.
- **E9 — No `research/{topic}/research.md` available** (ad-hoc discovery, Context B): R2(b) cannot run; R2 falls back to R2(a) alone (local `[file:line]` grounding requirement). Document this explicitly in the rule.
- **E10 — Consolidation reduces flagged count to zero** (all flagged inputs merged into unflagged items? — not possible per R5): R5 ensures merged items carry any input flag, so consolidation cannot reduce the flagged set. This is the invariant that preserves R3 integrity post-consolidation.

## Changes to Existing Behavior

- **MODIFIED: `decompose.md:23` Value field instruction** → now requires each item's Value to have a locally-written `[file:line]` citation grounding the claim in this codebase; adds the two-check flag detection (R2) and the surface-pattern helper hint.
- **MODIFIED: `decompose.md:29` user-approval step** → flagged items route to per-item `AskUserQuestion` with item-specific content and three choices (Acknowledge/Drop/Return to research); unflagged items keep the existing batch-review behavior.
- **ADDED: cap-and-escalate branch** at the approval step (R4) — fires on pre-consolidation flag count >3 OR all-flagged-and-N≥2.
- **ADDED: flag propagation rule** inside `decompose.md:§3 Consolidation Review` (R5) — propagates for ack-display only; cap evaluates pre-consolidation.
- **ADDED: authoring-time norm** as a bullet in the constraints block near `decompose.md:§ Constraints` (R1).
- **ADDED: event logging** for `decompose_flag` / `decompose_ack` / `decompose_drop` conditional on an existing event stream (R7).
- **ADDED: Dropped Items subsection** in the `research/{topic}/decomposed.md` schema described at `decompose.md:§6` (R9).

## Technical Constraints

- **TC1 — Rule-edit-first scope; ephemeral in-run state permitted**: All durable changes confined to `skills/discovery/references/decompose.md`. No new files, tooling, hooks, backlog frontmatter fields, or persistent artifacts (except the R9 schema extension to the existing `decomposed.md`). **Ephemeral in-run state** — e.g., the pre-consolidation flag count held in the agent's working memory during a single decompose run — is permitted and required for R4's pre-consolidation evaluation. "No persistent state" means no new files on disk between runs; it does not forbid transient tracking within one run.
- **TC2 — Symlink architecture**: Edit the repo copy at `skills/discovery/references/decompose.md`; the `~/.claude/skills/*` symlink propagates.
- **TC3 — File-based state**: The flag is a runtime agent decision, not persisted between runs. Event logs use the existing research-topic event stream.
- **TC4 — Daytime-only**: The per-item ack is interactive; `/discovery` is daytime per project philosophy. Overnight contexts do not run decompose interactively — no overnight-stall risk.
- **TC5 — Prose precedent**: Follow the style of `skills/lifecycle/references/specify.md:38-77` (§2a Research Confidence Check) — the closest precedent for signal-driven per-item gating inside a phase. Bulleted flag list with ≤15-word items; `AskUserQuestion` as the interactive mechanism (per `specify.md:36, 157`).
- **TC6 — Citation density is a lexical statistic** (epic Q6). R2(a)'s local-grounding check and R2(b)'s research-side citation check both rely on lexical presence of `[file:line]` tokens, not on semantic verification that the cited location substantiates the Value claim. The gate catches absence of citation (the #092-class failure where no local target exists) but not citation-incorrectness (a fabricated or stale `[file:line]`). Residual epistemic gap is explicitly deferred to future Approach F work per N5.
- **TC7 — Acceptance test surface**: Grep-based tests on `decompose.md` can verify rule presence (R1–R9 acceptance). Full interactive behavior (flag detection, AskUserQuestion ack flow, pre-vs-post-consolidation cap evaluation) is only verifiable by running `/discovery` end-to-end — accepted as interactive/session-dependent per R7 runtime and R8 scope.

## Open Decisions

None. All previously-deferred decisions from research's `## Open Questions` and all critical-review A-class concerns have been resolved in the body above.

Implementation-level questions (e.g., exact surface-pattern regex, exact grep commands in the R8 test, exact §6 Dropped Items schema formatting) are left to the Plan phase.
