# Research: Add vendor-endorsement value gating to /discovery decompose phase

## Epic Reference

Scoped from [research/audit-and-improve-discovery-skill-rigor/research.md](../../research/audit-and-improve-discovery-skill-rigor/research.md) (Approach C, DR-1(c), and H4-revised). The epic audited /discovery rigor after #092 closed wontfix on an empty-corpus premise; this ticket implements the decomposition-time value gate (companion to #138, which codified the `premise-unverified` signal in research.md and is already complete).

## Codebase Analysis

### Files that will change

- `skills/discovery/references/decompose.md:23` — Value field instruction: extend to require explicit flagging when the Value rests on external endorsement AND the codebase premise is unverified.
- `skills/discovery/references/decompose.md:29` — User-approval step: change from single batch-approve to flagged-item per-item acknowledgment, with unflagged items still batch-approvable.
- `skills/discovery/references/decompose.md:§3 (31-45)` — Must specify flag propagation across Consolidation Review (two flagged inputs → merged item carries the flag).

### Exact anchor text (decompose.md, current state)

- Line 9: `Read research/{topic}/research.md for findings, feasibility assessment, and decision records.` — decompose already has research.md in context; no new plumbing needed for signal consumption.
- Line 23: `- **Value**: What problem this solves and why it's worth the effort. One sentence. If the value case is weak relative to size, say so — this is the moment to flag it before tickets are created.`
- Line 29: `Present the proposed work items to the user for review before creating tickets.`

### #138's `premise-unverified` signal (current shape)

- **Marker**: `[premise-unverified: not-searched]` (literal string).
- **Location**: `skills/discovery/references/research.md:148-154` (Signal formats subsection). Per-claim inline, not a structured field.
- **Usage example in spec**: near `research.md:96` — `"Vendor blog endorses approach Y as 'the canonical pattern in $framework'; [premise-unverified: not-searched] — no codebase scan attempted..."`.
- **Completion**: shipped via `a7692f2`, `58f0985`; #138 marked complete at `d7f41c3`.

### Existing flag/gate precedents

- **`skills/lifecycle/references/specify.md:38-77`** (§2a Research Confidence Check) — closest precedent: presents flagged signals as a bulleted list, then uses `AskUserQuestion` to force a decision per the flagged set (binary batch decision, not per-item iteration).
- **`skills/lifecycle/references/specify.md:157`** — AskUserQuestion is the canonical mechanism for gated user decisions inside a phase.
- **`skills/lifecycle/references/specify.md:155-163`** — Spec User Approval surface explicitly includes "flag weak value cases" in its approval summary; related but not per-item gating.
- **`skills/discovery/references/auto-scan.md`** — uses AskUserQuestion for candidate topic selection.
- **`skills/backlog/SKILL.md:40,87-91`** — uses AskUserQuestion for 2–4 simultaneous options.

### NOT_FOUND

- **Per-item AskUserQuestion iteration across a work-item list** — no existing skill does this shape. `query=grep -r "AskUserQuestion" skills/ | grep -i "each\|per-item\|iterate"` → empty.

### Orchestration context

- Flow: Clarify → Research → Decompose → (user approval inside decompose) → Create Tickets. Discovery stops at ticket creation per `skills/discovery/SKILL.md`.
- `skills/discovery/references/orchestrator-review.md` R1–R5 run on `research.md`, not on decomposition. There is no existing checklist item covering `premise-unverified` marker *emission* by the research agent.
- Decompose's §3 Consolidation Review currently scopes to "combine items" (same-file overlap, no-standalone-value prerequisite) — adding a value-premise check there would expand §3's charter.

### Conventions to follow

- Imperative tone; file:line citations; inline signal markers (same style as #138 established in research.md:148-154).
- Section numbering `§N` with inline anchors matching existing decompose.md style.

## Web Research

### Prior art — human-in-the-loop gating

- **LangGraph `interrupt()`**: graph pauses at a node, state checkpointed, batched interrupt with **ordered per-item decisions** before resume. Direct analog for "pause once, collect N acknowledgments, proceed." ([LangGraph HITL docs](https://docs.langchain.com/oss/python/deepagents/human-in-the-loop))
- **CrewAI `human_input=True`**: per-task boolean gate; supports guardrail-style flagging ("if agent reasoning contains X, flag for human review"). Exact shape of "flag items matching predicate, gate only those." ([CrewAI Tasks](https://docs.crewai.com/en/concepts/tasks))
- **Microsoft Copilot Studio multistage approvals**: conditional-rule routing — auto-approve, reject, or escalate to human with reasoning attached. Canonical "flag-and-gate vs pass-through" pattern. ([Copilot Studio blog](https://www.microsoft.com/en-us/microsoft-copilot/blog/copilot-studio/automate-decision-making-with-ai-approvals-in-microsoft-copilot-studio/))
- **GitHub CODEOWNERS**: predicate-based approval — per-path approvals required, non-matched paths unaffected. Precedent for "gate only what matches the predicate."

### Key takeaways

- **Escalation with inline reasoning**: flagging without showing *why* flagged produces rubber-stamp behavior. Surface the rationale at the ack prompt.
- **Claim-evidence explicit surfacing** (PaperTrail): annotate missing evidence at the item, not in a footer.
- **Multi-category confidence** (SemanticCite: Supported / Partial / Unsupported / Uncertain) — suggests the flag may not need to be binary; an "Uncertain" bucket could reduce false positives. (Out-of-scope for a rule edit; noted for future.)

### Named anti-pattern relevant to the failure mode

- **Cargo Cult Programming** (McConnell, Wikipedia): ritual adoption of practices from prestigious sources without understanding local conditions. Closest established name for "vendor-endorsement + unverified codebase premise." No need to coin a new term — reference the existing one in rule prose if needed.

## Requirements & Constraints

- **`requirements/project.md`** (Philosophy of Work):
  - *Complexity must earn its place* — "When in doubt, the simpler solution is correct." Mitigations added beyond the minimal rule edit must justify themselves.
  - *Day/night split* — /discovery is a daytime skill; overnight does not run decompose interactively. A pause-for-ack step introduces **no overnight-stall risk**.
  - *Quality bar / ROI* — rule evaluated by whether it prevents wasted tickets, not by mechanism elegance.
- **`requirements/project.md`** (Architectural Constraints): file-based state only; any "flagged / acknowledged" marker must be markdown/YAML expressible.
- **`CLAUDE.md`**: skill rules live in `skills/discovery/references/*.md`; edit repo copy (symlinked to `~/.claude/skills/*`).
- **Defense-in-depth** is for sandbox/permissions, not workflow quality. Do not overbuild this gate as a defense layer.
- **Skipped area docs** (not relevant): remote-access, observability.
- **In-scope boundary**: modify decompose user-approval behavior and its reference file. **Out-of-scope**: extending gating into /lifecycle, /refine, or overnight phases; changing how /lifecycle consumes `discovery_source`.

## Tradeoffs & Alternatives

| Approach | Complexity | Maintainability | Friction | Alignment | Satisfies ticket |
|----------|-----------|-----------------|----------|-----------|------------------|
| **A. Ticket baseline** — flag at :23 + pause at :29 with unspecified mechanism | S | H | M | strong | partially — mechanism undefined |
| **B. Flag only, no pause change** | S | H | L | partial | ✗ — fails ticket criterion 2 |
| **C. Move gate to §3 Consolidation** | S | M | M | weak | ✗ — moves away from :29 anchor |
| **D. Flagged-first surfacing, batch approve** | S | H | L | partial | ✗ — no per-item ack event |
| **E. Orchestrator-review R6** | S | H | L | strong (structural) / weak (empirical) | ✗ — DR-1 of epic rejected as post-hoc human check |
| **F. A + explicit AskUserQuestion mechanism (recommended)** | S | H | M | strong | ✓ |

**Recommended: Approach F** — transpose the shape of `specify.md:38-77` (§2a Research Confidence Check) onto decompose. Paired edits at `decompose.md:23` (flag) and `:29` (AskUserQuestion per flagged item, with inline rationale). Precedent-aligned, satisfies both ticket success criteria, names a concrete interactive tool rather than leaving "pause" undefined.

**Why not B/D/E**: #092's chain passed every post-hoc human check (orchestrator-review R1–R5 clean cycle 1; critical-review 4/4 objections applied; user gate approved). One more flag in a batch list (B, D) or one more checklist item on the research phase (E) is the same kind of check that already failed. The AskUserQuestion per-item ack is categorically different: it forces a per-item user event that the batch/checklist approaches cannot produce.

## Adversarial Review

Surfaced load-bearing concerns that shape the spec's open decisions — not all dismissable:

### Confirmed concerns

- **C1. `premise-unverified` signal sparsity**: grep of `research/**` shows the marker exists in **1 of 26 existing research artifacts**. The primary trigger is aspirational on current corpus. The gate's effective behavior on pre-#138 artifacts is determined by the OR-fallback ("absent citations"), not the principled signal.
- **C2. "Absent citations" is lexical, not epistemic** (epic Q6 recurrence): a research.md that contains `[file:line]` strings passes a grep-for-citations check regardless of whether the citation is accurate. This is the same failure shape epic Q6 flagged and DR-1(c) chose not to fully solve.
- **C3. Self-referential detection**: the agent that generated `endorsed by Anthropic's 4.7 migration guide` as sufficient Value must now label its own output as external-endorsement-with-unverified-premise. The detector and fault share a synthesis layer.
- **C4. Ack fatigue**: if discovery produces 5–15 items and several flag, rapid-fire AskUserQuestion sequences train rubber-stamping. The ceremony risks reproducing #092's failure at a new surface.
- **C5. Consolidation flag-propagation is undefined**: §3 can merge two flagged items into one; the proposal does not specify whether the merged item carries the flag. Path to accidental laundering.
- **C6. No orchestrator-review coverage for marker emission**: R1–R5 run on research.md but nothing asserts the agent emitted `premise-unverified` where it should have. The signal flow assumes discipline that the empirical base rate (1/26) already refutes.
- **C7. Ack event evaporation**: user acknowledges a flagged item → ticket gets `discovery_source` pointer → /lifecycle sees a normal ticket with no carry-through of the ack. Point-in-time protection only.

### Assumptions that may not hold

- "Per-item gating is more protective than batch-approval" — asserted, not tested. Mitigated only if the ack prompt includes item-specific rationale.
- "Legitimate vendor-guided work with grounded premise remains unaffected" — only true if the OR-fallback is high-precision, which is doubtful given citation density.

### Lightweight mitigations (rule-edit scope only)

- **M1**: `decompose.md:23` should require the agent to produce a `[file:line]` *it wrote itself* grounding the Value claim; if unable, flag. Moves detection from surface-pattern matching to grounding-capacity.
- **M2**: One sentence in §3 Consolidation: "If any consolidated input item was flagged per §2, the merged item carries the flag."
- **M3**: The ack prompt must quote both the Value string and the specific unverified premise, inline. Generic "Acknowledge?" is insufficient.
- **M4**: Narrow the OR-fallback from "absent citations in research.md" to "absent `[file:line]` citation within N lines of the Value-supporting claim" — local grounding, not whole-file presence.
- **M5**: Add a constraint note to decompose.md: "Vendor guidance and best practices are not sufficient Value alone — the Value field must state what problem this solves in *this* codebase." Norm-based, not gate-based; attacks the authoring moment.

## Open Questions

- **Trigger semantics for the OR-fallback.** Deferred: will be resolved in Spec by asking the user. Is "absent citations in the source research.md" (ticket body) a whole-research-file check, a per-claim local-window check (M4), or something else? Epic Q6 evidence (citation density is lexical 83–95%, #092 sat at sample floor 83%) suggests whole-file is low-precision; per-claim local-window (M4) is more defensible but still lexical.
- **Flag propagation across §3 Consolidation** (M2). Deferred: will be resolved in Spec by asking the user. Not addressed in ticket body; adversarial review (C5) surfaced the gap — two flagged inputs merged into one could launder the flag.
- **Ack-prompt content specificity** (M3). Deferred: will be resolved in Spec by asking the user. Ticket body says "the user must explicitly acknowledge each such item" but does not specify what must be shown at ack time. Minimum content (Value string + specific unverified premise quote) matters for the rubber-stamp failure mode (C4).
- **Whether to add the norm-based constraint note** (M5). Deferred: will be resolved in Spec by asking the user. Attacks the authoring moment rather than the approval moment — could be additive to the gate or a lighter substitute.
- **Self-referential detection limit (C3).** Deferred: will be resolved in Spec by asking the user. How (or whether) to address the case where the synthesis agent that generated the unflagged Value is also responsible for flagging it. DR-1(c) positions rule edits as the ceiling — spec must make the acceptance of this limit explicit or propose a bounded additional move.
