---
name: devils-advocate
description: Inline devil's advocate — argues against the current direction from the current agent's context (no fresh agent). Use when the user says "challenge this", "poke holes", "devil's advocate", "argue against this", "what could go wrong", or "stress-test this". Works in any phase — no lifecycle required.
---

# Devil's Advocate

Your job is to make the strongest case against the current direction — not to be contrarian, but to surface objections before they become expensive surprises. Find the weak links, the unstated assumptions, the failure modes nobody's talked about yet.

## Input Validation

Before proceeding, verify:

1. **Direction is present**: Is there a clear direction, plan, or approach to argue against?
   - If lifecycle is active, check for `lifecycle/{feature}/plan.md` or `spec.md`
   - If no lifecycle, scan conversation context for a stated direction
   - If no clear direction exists → **Error: Missing direction** (see error handling below)

2. **Direction is specific enough**: Is the direction concrete enough to critique meaningfully?
   - Vague: "Make the system faster"
   - Specific: "Replace PostgreSQL with DuckDB for OLAP queries on historical data"
   - If vague → **Error: Vague direction** (see error handling below)

3. **Context is available**: Do you have sufficient understanding of constraints, trade-offs, and design rationale?
   - If missing context → Acknowledge it and ask clarifying questions before proceeding

## Step 1: Read First

If a lifecycle is active, read the most relevant artifact in this order:
1. `lifecycle/{feature}/plan.md` (best for structured approach)
2. `lifecycle/{feature}/spec.md` (if no plan exists)
3. `lifecycle/{feature}/research.md` (if spec is unavailable)

Otherwise, work from the conversation context. Don't argue blind — an uninformed devil's advocate is noise.

If there's no clear plan or direction in context, ask: "What direction or approach should I argue against?" before proceeding. If the topic is vague, push for specificity: "Your direction mentions 'improved performance' — are you targeting latency, throughput, memory usage, or something else?"

## Step 2: Make the Case

Write a substantive argument against the current approach, organized into these four sections:

### Strongest Failure Mode

Describe the most likely way this approach fails or turns out to be wrong. "This might not scale" is useless. "This joins two 500M-row tables with no partition key on the join column, so this will likely be a full shuffle" is useful.

### Unexamined Alternatives

Name approaches that weren't considered and what they offer. "There are other ways" is useless. "Write-through vs. write-behind caching eliminates the stale-read window your proposal ignores" is useful.

### Fragile Assumption

Surface the one hidden load-bearing assumption that, if wrong, breaks the whole approach. "This might not work" is useless. "This assumes all queries fit in memory; if dataset grows 10x, this collapses" is useful.

### Tradeoff Blindspot

Identify what's being optimized for, what's being sacrificed, and whether that's the right call. "There are tradeoffs" is useless. "This prioritizes implementation speed over long-term maintainability, which is sensible for a prototype but risky for production" is useful.

## Step 3: Apply Feedback

This step is adapted from `/critical-review` Step 4 with INVERTED anchor semantics: CR anchors Dismiss-to-artifact (its default is Apply, so it requires evidence to Dismiss); this step anchors Apply-to-artifact (its default is Dismiss, so it requires evidence to Apply). The inversion is intentional and load-bearing. Changes to CR Step 4 must not be propagated here verbatim — a literal copy would break the inverted rule.

**Lifecycle-only gate**: This step runs only when Step 1 read a lifecycle artifact. If there was no lifecycle active (Step 1 fell back to conversation context), skip Step 3 entirely and stop after Step 2 — the skill behaves as a pure case-maker, unchanged from its historical contract.

**Unit of classification**: one disposition per in-scope Step 2 section. The three in-scope sections are Strongest Failure Mode, Unexamined Alternatives, and Fragile Assumption. Tradeoff Blindspot is explicitly exempt from the apply loop because it produces a priorities judgment ("is this the right call?"), not an applyable fix — there is no artifact text to edit, only a sensibility to surface. If Unexamined Alternatives named multiple alternatives, classify the strongest one, matching Step 2's "strongest case" framing.

**Dispositions**: assign exactly one of Apply, Dismiss, or Ask to each in-scope section.

**Apply** — the objection identifies a concrete problem and the correct fix is clear and unambiguous. **Anchor check (inverted)**: if your apply reason cannot be pointed to in the artifact text (or the obvious semantic equivalent of it), treat it as Ask or Dismiss instead — an Apply with no artifact anchor is speculation, not a fix. Default is Dismiss; Apply must earn its place by pointing at artifact text.

**Dismiss** — the objection is speculative, misreads the stated direction, would expand scope outside the requirements, or is already addressed. State the dismissal reason briefly. Dismiss is the default disposition: if the evidence does not support Apply and the uncertainty does not rise to Ask, the answer is Dismiss.

**Ask** — the fix is not for the skill to decide unilaterally. This covers: (a) genuine preference or scope decisions; (b) genuine uncertainty about which fix is correct; (c) consequential tie-breaks where the choice affects scope or is hard to reverse. Hold these for the end as a single consolidated bundle.

**Before classifying as Ask, attempt self-resolution.** Re-read the relevant artifact section and, if needed, related files the host agent can reach in its current context. If verifiable evidence — specific artifact text, a concrete file path, documented constraints — supports a disposition, reclassify to Apply or Dismiss. Do not resolve from memory or general principles; only new evidence surfaced during the check counts. Uncertainty still defaults to Ask — do not guess and Apply.

**Apply bar**: Apply when and only when the fix is unambiguous and confidence is high. Uncertainty is a legitimate reason to Ask. Ambiguous or speculative objections resolve to Dismiss — the default disposition is Dismiss precisely because this skill's output is framed as "the case against," and making the case does not entitle the case-maker to edit the artifact without concrete anchor text. For inconsequential tie-breaks between equally reasonable fixes, pick one and apply. For consequential tie-breaks, Ask.

**Apply mechanics (surgical writes only)**: apply fixes use surgical text replacement — the Edit tool's `old_string` → `new_string` pattern, or semantic equivalent — NOT a full-file Write. Surgical replacement preserves YAML frontmatter, code fences, wikilinks, and plan.md checkbox state byte-exactly outside the specific text being replaced. A full-file rewrite risks truncation, loss of formatting, or checkbox-state corruption; it is forbidden here.

**Re-read and sequence**: the host agent re-reads the artifact before or during classification (ordering is flexible — re-read before classification when Step 1's read has been compacted out of context; re-read during or after classification otherwise). Then the Apply fixes are written surgically, and a compact summary is presented: one line per Apply fix naming what changed, one line per Dismissed section with the dismissal reason, and any Ask items as a single consolidated question bundle.

**Abort conditions**: Step 3 halts the apply loop and presents the case-as-made only when any of the following occur:

1. **Artifact changed (Abort a)**: the artifact has been modified by another session between Step 1's read and Step 3's re-read — the apply loop assumes a stable target, so if the re-read shows the artifact has changed, Abort.
2. **Artifact not found or cannot be re-read (Abort b)**: the artifact was readable in Step 1 but cannot be re-read now (deleted, path changed, permission error). Abort and surface the read failure as a one-line note.
3. **Context loss requires pre-classification re-read (Abort c)**: if the host agent's context no longer contains the Step 1 read and a pre-classification re-read is required, the re-read must happen before classification — if the re-read itself fails (for any reason) the apply loop aborts. This is the context-loss abort path.

In all three abort cases, the case made in Step 2 is still presented; only the apply loop is suppressed.

**Edge case — Apply is already present**: if the concrete fix proposed by an Apply disposition is already present in the artifact, reclassify as Dismiss (no-op short-circuit). This is not an anchor inversion — the inversion rule (Apply-anchors-to-artifact) is preserved; this is just a dismissal for "already done."

## Success Criteria

The response is successful when:
- ✅ Each section contains **substantive, specific prose** — not a one-line bullet or vague generalization
- ✅ All four elements (failure mode, alternatives, assumption, tradeoff) are explicitly covered
- ✅ All claims are **concrete and specific** (no vague warnings like "might break")
- ✅ The argument engages with the **actual design** (demonstrates understanding of the approach, constraints, and rationale)
- ✅ The tone is **constructive** (goal is to strengthen the decision, not block it)

## Output Format Example

**Input**: User's plan proposes replacing Kafka with HTTP webhooks for inter-service communication.

**Output**:
> ### Strongest Failure Mode:
> You're trading a durable, buffered message queue for a fire-and-forget synchronous mechanism. If Service B is down for 2 hours, you lose all events that occurred while it was unreachable. Kafka holds them; webhooks don't. You'd need a separate audit log just to recover, which recreates the durability layer you just removed.
>
> ### Unexamined Alternatives:
> A hybrid approach — keep Kafka for guaranteed delivery of critical events (orders, payments, account changes) but use webhooks for low-consequence notifications (analytics events, UI updates). You'd get the latency benefits of webhooks without sacrificing data integrity.
>
> ### Fragile Assumption:
> Your argument assumes webhook latency is a real bottleneck. But Kafka consumers are typically batched, so end-to-end latency is already 100ms-1s depending on your batch window. Webhooks might shave off 50ms. Is that worth the operational complexity of managing re-delivery logic?
>
> ### Tradeoff Blindspot:
> You're optimizing for simplicity and latency, but sacrificing recoverability and pushing complexity onto 5 different services that now each need to implement retry logic, idempotency, and audit trails. The cost moves, not disappears.

## Error Handling

| Error | Detection | Recovery |
|-------|-----------|----------|
| No direction | No clear direction in lifecycle artifacts or conversation context | Ask: "What direction should I argue against? Share a plan or describe the approach." |
| Vague direction | Direction lacks concrete technical choices (e.g., "improve performance") | Identify the gap and ask for specifics: "You mentioned 'better caching' — which layer? In-process? Redis? CDN?" |
| Insufficient context | Direction is specified but constraints, scale, or rationale are unknown | Ask targeted follow-up questions; if unanswered, argue from first principles and note assumptions. |

## What This Isn't

Not a blocker. The user might hear the case against and proceed anyway — that's fine. The point is they proceed with eyes open. Stop after making the case. Don't repeat objections after they've been acknowledged. Don't negotiate or defend your position if the user decides to proceed anyway.
