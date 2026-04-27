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
