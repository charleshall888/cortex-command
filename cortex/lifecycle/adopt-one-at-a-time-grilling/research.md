# Research: Adopt one-at-a-time grilling cadence in requirements interview

## Epic Reference

Parent epic: `cortex/backlog/221-adopt-grill-with-docs-progressive-disclosure-system.md`. Epic discovery research: `cortex/research/grill-me-with-docs-learnings/research.md`. The epic carves three Tier-1 pieces (cadence refresh, glossary, ADR mechanism) from Matt Pocock's grill-with-docs progressive-disclosure system; this child ticket lands the cadence refresh piece only. Glossary and ADR are sibling children; their inline-write postures do not propagate to this child (see Considerations Addressed and Open Questions below).

## Codebase Analysis

### Files that will change

- `skills/requirements-gather/SKILL.md` (72 lines total)
  - §"Decision criteria" lines 22–33: tighten with one-at-a-time cadence prose. Recommend-before-asking (lines 27–29) is already canonical — this work tightens cadence around it, not the recommendation logic itself.
  - §"Output shape" lines 42–57: file-path citation lands in the existing `**Code evidence:**` field (line 53) — semantic scope to be decided in spec (universal vs grounded-only; see Open Questions).
  - File has 428 lines of headroom under the 500-line SKILL.md size cap.

- `skills/lifecycle/references/specify.md` (191 lines total)
  - §2 "Structured Interview" (lines 11–36): cadence prose, during-interview verification posture, per-requirement edge-case invention before acceptance criteria (categorical vs judgmental TBD — see Open Questions).
  - §2b "Pre-Write Checks" (lines 72–90): only the **Verification check** sub-block is in scope per Clarify-phase scoping decision. Research cross-check (lines 82) and Open Decision Resolution (lines 84–90) stay end-of-interview — they require the complete candidate claim-set and cannot run mid-interview.
  - §2b reposition is itself contested by the adversarial pass — see Open Questions.

- `skills/lifecycle/SKILL.md` lines 189–200 (Kept user pauses inventory): one or more new entries required if specify.md §2 grows new `AskUserQuestion` call sites. Current single entry at `specify.md:36` only covers one site under ±35-line tolerance.

- `tests/test_lifecycle_kept_pauses_parity.py`: parity test uses `LINE_TOLERANCE = 35` but the SKILL.md prose at line 191 says "±20-line tolerance" — pre-existing drift. Address in this patch alongside inventory updates.

### Relevant existing patterns

- **Recommend-before-asking** is already canonical at `skills/requirements-gather/SKILL.md:27–29`. The Integration section of ticket 222 explicitly acknowledges this — this work tightens cadence on top of an existing recommendation pattern, not adding recommend-before-asking from scratch.
- **Codebase-trumps-interview** decision gate at `skills/requirements-gather/SKILL.md:23–25` is the natural anchor for file-path citation (cite paths when the recommendation is grounded in code).
- **Q&A block schema** at `skills/requirements-gather/SKILL.md:44–57`: `**Q:** / **Recommended answer:** / **User answer:** / **Code evidence:**` — file-path citation fits in `Code evidence`, edge-case invention fits in `Q` or `Recommended answer` prose. Per Clarify Q3 decision, no schema additions.
- **AskUserQuestion call sites** elsewhere in the lifecycle are terminal gates (one user decision per call), with one explicit batching exception at `clarify.md:57` (caps at 5 questions). The batching there is intentional, not an oversight — the post-§3a critic-merge step prioritizes within the cap.

### Integration points and dependencies

- `/cortex-core:refine` Step 5 delegates Specify to `skills/lifecycle/references/specify.md`. The cadence prose in §2 fires inside every refine invocation.
- `/requirements-gather` → `/requirements-write` Q&A block contract preservation requires zero schema change; new behaviors land as prose within existing fields.
- `tests/test_lifecycle_kept_pauses_parity.py` enforces the inventory ↔ call-site invariant; any change to specify.md §2's AskUserQuestion sites requires a corresponding inventory edit.

### Conventions to follow

- Kebab-case slugs for lifecycle directory names.
- Soft-positive routing prose only (per CLAUDE.md MUST-escalation policy); no new MUST/REQUIRED/CRITICAL without effort=high dispatch evidence + events.log F-row.
- Prose-within-existing-fields schema preservation; do not add new Q&A block keys.
- Prescribe What and Why, not How (CLAUDE.md): describe the cadence as a decision rule, not as procedural narration.

## Web Research

### Pocock prior art

- **`grill-me`** (productivity/grill-me/SKILL.md): minimal interview body — "Ask the questions one at a time. For each question, provide your recommended answer. If a question can be answered by exploring the codebase, explore the codebase instead." Recommend-before-asking encoded in ~10 words.
- **`grill-with-docs`** (engineering/grill-with-docs/SKILL.md): tightens cadence to "Ask the questions one at a time, **waiting for feedback on each question before continuing**." Adds challenging the glossary, sharpening fuzzy language, inventing concrete scenarios that probe edge cases, cross-referencing with code, and updating `CONTEXT.md` inline.
- **`setup-matt-pocock-skills`**: cleanest soft-positive cadence exemplar — "walk the user through the three decisions **one at a time** — present a section, get the user's answer, then move to the next. Don't dump all three at once."
- **`to-prd`**: synthesis-only counterpart — "Do NOT interview the user — just synthesize what you already know." Structurally validates a gather/write split.

### Escalation language

Targeted grep over `grill-with-docs/SKILL.md` for `MUST|REQUIRED|CRITICAL|NEVER|ALWAYS` returned **zero matches**. Pocock encodes cadence, recommend-before-asking, edge-case invention, and inline verification entirely in soft positive routing. No prose escalation appears anywhere near these skills. This means the cortex-command cadence uplift can be encoded in soft-positive prose without tripping CLAUDE.md MUST-escalation policy.

### Verification placement

`grill-with-docs` positions terminology/ADR verification inline mid-interview ("Update CONTEXT.md inline. When a term is resolved, update CONTEXT.md right there. Don't batch these up — capture them as they happen."). Cross-referencing with code is also mid-interview as a continuous passive activity. This supports repositioning specify.md §2b Verification from end-of-interview to during-interview *in principle* — but the adversarial pass surfaced concrete reasons this may not transfer (see Open Questions).

### Anti-patterns one-at-a-time prevents

- Batch-questioning fatigue (cognitive-load evidence: 77% vs 83% accuracy under high load).
- Partial answers (respondents skip later questions in a batch; the interviewer can't distinguish silence from agreement).
- Decision-tree branch drift (Q1's answer should reshape Q2, but Q2 was already asked).

### Key takeaway URLs

- `https://raw.githubusercontent.com/mattpocock/skills/main/skills/productivity/grill-me/SKILL.md`
- `https://raw.githubusercontent.com/mattpocock/skills/main/skills/engineering/grill-with-docs/SKILL.md`
- `https://raw.githubusercontent.com/mattpocock/skills/main/skills/engineering/setup-matt-pocock-skills/SKILL.md`
- `https://raw.githubusercontent.com/mattpocock/skills/main/skills/engineering/to-prd/SKILL.md`

## Requirements & Constraints

### From `cortex/requirements/project.md`

- **Philosophy of Work — Daytime work**: "Research before asking; don't fill unknowns with assumptions." Cadence tightening aligns.
- **Philosophy of Work — Complexity**: "Must earn its place by solving a real problem now. When in doubt, simpler wins." Bears directly on whether per-requirement edge-case invention earns its complexity (see Open Questions).
- **Philosophy of Work — Solution horizon**: A scoped phase of a multi-phase lifecycle is not a stop-gap. Cadence refresh as one of three Tier-1 epic pieces qualifies as a scoped phase.
- **Architectural Constraints — SKILL.md size cap**: 500 lines. Both target files have ample headroom.

### From `CLAUDE.md`

- **Design principle "Prescribe What and Why, not How"**: describe the cadence as a decision rule and intent, not procedural narration of how to enforce gating.
- **MUST-escalation policy (post-Opus 4.7)**: default soft-positive routing; new MUST/CRITICAL/REQUIRED requires effort=high dispatch evidence + events.log F-row OR transcript URL. Cadence behaviors translate to soft-positive routing per epic discovery DR-5.
- **Skill/phase authoring guidelines**: "Prefer structural separation over prose-only enforcement for sequential gates. Prose-only enforcement is appropriate only for guidelines where the cost of occasional deviation is low." This is the central dispute in the alternatives analysis (see Tradeoffs and Open Questions).

### From parent epic `cortex/backlog/221`

- Out of scope (held pending effort=high evidence): interrupt-driven behaviors (challenge-against-glossary mid-sentence, fuzzy-language sharpening, real-time code contradiction surfacing).
- Out of scope: maintained per-area indices, cortex-init glossary bootstrap.
- "Maintenance follows Pocock's producer-consumer posture: the cadence-uplifted interview surfaces write inline" — this is the contested inline-write inheritance question (see Considerations Addressed).

### From this ticket `cortex/backlog/222` Edges

- **Soft-positive-routing prose only.** No new MUST/REQUIRED escalations without effort=high evidence.
- **Behaviors limited to passive-precondition encoding.** Interrupt-driven mid-turn injections explicitly out of scope.
- **Must not break the existing Q&A block contract** between `/requirements-gather` and `/requirements-write`.

### Scope boundaries

- **In scope**: cadence tightening + file-path citation in `requirements-gather`; cadence + during-interview Verification + per-requirement edge-case invention in `specify.md` §2; reposition `specify.md` §2b Verification check sub-block only (NOT Research cross-check or Open Decision Resolution).
- **Out of scope**: interrupt-driven behaviors; glossary at `cortex/requirements/glossary.md` (sibling child); ADR mechanism at `docs/adr/` (sibling child); new standalone `/grill` skill; maintained per-area indices.

## Tradeoffs & Alternatives

Four candidate approaches were evaluated. Approach A is the ticket's proposal; B, C, D are alternatives explored per the complex/high alternative-exploration rule.

- **Approach A — in-place prose edits (ticket's proposal)**: Two file edits, no new contracts. Minimal complexity. Q&A schema preserved. Risk: prose duplication between the two surfaces; future drift if one updated without the other. Aligns with Pocock's pattern of inline prose-in-skill encoding.

- **Approach B — shared reference file** at `skills/lifecycle/references/interview-cadence.md`, pointed at from both surfaces. Eliminates drift risk. Adds one new file (the ticket says "no new files"). Centralizes the rule for any future third interview surface. Adversarial pass argues this is the correct durable form per CLAUDE.md Solution horizon — two named surfaces already meets the plural threshold.

- **Approach C — AskUserQuestion control-flow gating** (one question per call). Initially appealing on CLAUDE.md "structural over prose-only" grounds. Adversarial pass argued this is *not* genuine structural enforcement — AskUserQuestion call shape is itself a prose-level constraint about how to invoke a tool; the harness does not block multi-question call bodies. Plus inverts the existing `clarify.md:57` batching contract without justified asymmetry. Provides no real enforcement gain over Approach A.

- **Approach D — Pocock-faithful inline-write** (cadence-uplifted surfaces write artifacts mid-interview). Aligns with parent epic posture for grill-with-docs-like surfaces. But cortex-command's surfaces follow the grill-me/to-prd Q&A-then-synthesize split (per `requirements-gather/SKILL.md:33` "This sub-skill never touches the filesystem"). Inline writes would break the `/requirements-gather` "never touches filesystem" invariant and bundle glossary scope into this ticket. Out of scope for this child.

### Recommendation

Tradeoffs agent proposed Hybrid A+C. Adversarial pass rejected C as wishful structural labeling and argued B has stronger CLAUDE.md grounding than the tradeoffs agent acknowledged. **Recommended for spec phase to decide**: Approach A in pure form (drop C), or Approach B (shared reference file) if the Solution horizon plural-threshold reading holds. Decision criteria framed as Open Question O1 below.

## Adversarial Review

The adversarial agent challenged each preceding finding and surfaced eight failure modes / assumptions that may not hold. Highest-impact findings:

- **§2b Verification check repositioning may be a category error.** The check operates on the candidate claim-set, which only exists at end-of-interview. Mid-interview, the agent is *eliciting* claims, not yet making spec assertions. Repositioning forces either re-verification on every new answer (more cognitive load, not less) or a vague soft "be careful with paths as you go" with no concrete trigger.

- **Approach C provides no genuine structural enforcement.** AskUserQuestion call shape is itself a prose-level constraint; the harness does not prevent packing multiple questions into a single call body. Labeling this "structural" is wishful.

- **Per-requirement edge-case invention may compound latency.** Two user-blocking turns per requirement × N requirements + non-requirements + technical constraints — simple-tier interviews become structurally longer than today's batched interview. The cadence prevents fatigue from batching; categorical edge-case invention re-creates fatigue from sequencing.

- **Categorical edge-case invention may amplify hallucination.** Pocock applies edge-case invention judgmentally (when a claim looks under-specified), not categorically (for every claim). Categorical application encourages inventing plausible-but-ungrounded edge cases.

- **Universal file-path citation conflicts with the existing `Code evidence: omit otherwise` semantics.** For genuinely-intent questions with no codebase grounding, the agent must either fabricate a citation, violate the rule, or write `N/A — intent question` that defeats the field's diagnostic value.

- **Verification-as-passive-precondition cannot fail loudly.** Today §2b surfaces failures as a terse bullet ≤15 words — visible, blocking, self-correcting. A passive precondition has no failure surface defined; moving from synchronous loud-failure to asynchronous silent-precondition is an observability downgrade.

- **Approach B's Solution-horizon dismissal may be a misread.** CLAUDE.md says "the same patch would apply in multiple known places you can name." Two named places is plural and meets the trigger. The tradeoffs agent's "≥3 surfaces" reading is not what the policy text says.

- **Kept-user-pauses inventory parity test will need real updates** — multiple new AskUserQuestion sites in specify §2 likely require multiple new inventory entries. The ±35-line tolerance does not give "headroom" for site sprawl; it's symmetric around each anchor. Plus there's pre-existing drift between SKILL.md prose ("±20-line tolerance" at line 191) and test code (`LINE_TOLERANCE = 35`).

## Open Questions

Deferred: will be resolved in Spec by asking the user. The adversarial pass surfaced concrete decisions the Spec phase must resolve with the user. Each is a binary or near-binary choice with named alternatives; deferring to the Spec interview rather than guessing.

- **O1 — Encoding form for cadence**: Approach A (pure prose in both files) OR Approach B (shared reference file `skills/lifecycle/references/interview-cadence.md`)? The tradeoffs agent recommended A; the adversarial pass argued B has stronger CLAUDE.md Solution-horizon grounding. Approach C (AskUserQuestion control-flow) is rejected by both as not genuinely structural and not worth the call-site asymmetry with `clarify.md:57`. Spec phase asks the user.

- **O2 — §2b Verification check reposition**: Reposition the Verification sub-block from end-of-interview to during-interview as a passive precondition, OR keep it end-of-interview and add a separate lightweight "verify file paths as you cite them" guideline to §2? The adversarial pass argues repositioning is a category error and an observability downgrade. Spec phase asks the user.

- **O3 — File-path citation scope**: Universal ("name the file path for every requirement"), OR grounded-only ("when the Recommended answer is derived from code, the Code evidence field must name the file path that grounds it")? Universal conflicts with `Code evidence: omit otherwise` semantics; grounded-only preserves the existing semantics and avoids the prompt-injection-via-codebase incentive the adversarial pass flagged. Spec phase asks the user.

- **O4 — Edge-case invention scope**: Categorical ("per-requirement edge-case invention before locking acceptance criteria"), OR judgmental ("when a requirement's acceptance criteria look under-specified, invent edge-case scenarios that force the user to be precise")? Categorical is Pocock-faithful in name but not in usage; categorical risks both hallucination amplification and turn-count compounding. Spec phase asks the user.

- **O5 — Kept-user-pauses inventory churn budget**: How many new AskUserQuestion sites will land in specify §2 under the chosen cadence encoding? Each new site requires a corresponding inventory entry at `skills/lifecycle/SKILL.md:189–200`. Also: should this patch address the pre-existing drift between SKILL.md prose claim (±20 lines) and code constant (`LINE_TOLERANCE = 35` at `tests/test_lifecycle_kept_pauses_parity.py:27`)? Spec phase finalizes the inventory plan; in scope or punted to a follow-up.

## Considerations Addressed

- **Whether Pocock grill-with-docs encodes one-at-a-time gating as soft positive routing or as MUST language so this cadence can be encoded in soft-positive prose without tripping CLAUDE.md MUST-escalation policy.** Addressed: grep over Pocock's grill-with-docs SKILL.md for MUST/REQUIRED/CRITICAL/NEVER/ALWAYS returned zero matches. Pocock encodes cadence purely in soft-positive prose. Transfer to cortex-command is soft-positive-routing compatible. Adversarial caveat #11 noted that categorical instructions phrased soft-positively may still be MUST-equivalent in force; this is folded into Open Question O3 (file-path citation scope) and O4 (edge-case invention scope).

- **Whether this child inherits the parent epic 221 stated inline-write posture for cadence-uplifted interview surfaces or whether inline-write is scoped to a sibling child such as glossary or ADR.** Addressed: Pocock's inline-write applies to grill-with-docs (writes terminology and ADR artifacts inline) but not to grill-me or to-prd. cortex-command's requirements-gather and specify §2 surfaces follow the grill-me/to-prd Q&A-then-synthesize split — `/requirements-gather` explicitly disclaims filesystem writes (`requirements-gather/SKILL.md:33`). Inline-write does NOT propagate to this child; it's scoped to sibling glossary and ADR children under parent epic 221. Adversarial caveat #13 noted no Pocock skill exactly matches requirements-gather's shape, so the comparator is approximate but the structural mismatch with grill-with-docs's writing posture is clear.

- **Whether during-interview file-path citation is genuinely a passive precondition or requires active mid-turn injection that effort=high evidence could not satisfy.** Addressed in part: web evidence supports passive-precondition framing (Pocock treats citation as a byproduct of codebase exploration). Adversarial M3 surfaced the unresolved scoping problem: a universal "cite file path for every requirement" rule is categorical in force and conflicts with existing `Code evidence: omit otherwise` semantics. Grounded-only scoping ("when the Recommended answer is derived from code") preserves the passive-precondition framing. Folded into Open Question O3 for spec-phase resolution.
