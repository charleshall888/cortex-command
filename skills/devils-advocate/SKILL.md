---
name: devils-advocate
description: Stress-tests a direction, plan, or approach by arguing against it. Use when the user says "challenge this", "poke holes", "devil's advocate", "what could go wrong", "stress test this", "argue against this", or "play devil's advocate". Works in any phase — no lifecycle required. Reads relevant artifacts if a lifecycle is active; otherwise works from conversation context.
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

Write a coherent argument against the current approach — not a bullet list of nitpicks. Cover these four things in a flowing narrative (not a checklist):

**Strongest failure mode**: What's the most likely way this approach fails or turns out to be wrong? Be specific. "This might not scale" is useless. "This joins two 500M-row tables with no partition key on the join column, so this will likely be a full shuffle" is useful.

**Unexamined alternatives**: What approaches weren't considered, and what do they offer? Name them — don't just say "there are other ways." For example, if the plan proposes caching, mention specific alternatives like write-through vs. write-behind, or in-process vs. distributed cache.

**Fragile assumption**: What's the one thing that, if it turns out to be different than expected, breaks the whole approach? Surface the hidden load-bearing assumption. Example: "This assumes all queries fit in memory; if dataset grows 10x, this collapses."

**Tradeoff blindspot**: What's being optimized for? What's being sacrificed? Is that the right call given the actual constraints? Example: "This prioritizes implementation speed over long-term maintainability, which is sensible for a prototype but risky for production."

## Success Criteria

The response is successful when:
- ✅ The argument is **coherent and narrative** (not a bullet list of gripes)
- ✅ All four elements (failure mode, alternatives, assumption, tradeoff) are explicitly covered
- ✅ All claims are **concrete and specific** (no vague warnings like "might break")
- ✅ The argument engages with the **actual design** (demonstrates understanding of the approach, constraints, and rationale)
- ✅ The tone is **constructive** (goal is to strengthen the decision, not block it)

## Output Format Examples

### Example 1: Architectural Decision Under Attack

**Input**: User's plan proposes replacing Kafka with HTTP webhooks for inter-service communication.

**Output**:
> **The core problem I see**: You're trading a durable, buffered message queue for a fire-and-forget synchronous mechanism. The failure mode is clear — if Service B is down for 2 hours, you've now lost all events that occurred while it was unreachable. Kafka holds them; webhooks don't. You'd need to add a separate audit log just to recover, which recreates the durability layer you just removed.
>
> **You haven't weighed the alternative**: A hybrid approach exists — keep Kafka for guaranteed delivery of critical events (orders, payments, account changes) but use webhooks for low-consequence notifications (analytics events, UI updates). You'd get the latency benefits of webhooks without sacrificing data integrity.
>
> **The hidden assumption**: Your argument assumes webhook latency is a real bottleneck. But Kafka consumers are typically batched (consume in chunks), so end-to-end latency is already 100ms–1s depending on your batch window. Webhooks might shave off 50ms. Is that worth the operational complexity of managing re-delivery logic?
>
> **What you're optimizing vs. what you're losing**: You're optimizing for simplicity and latency. Fair priorities. But you're sacrificing recoverability and pushing complexity onto 5 different services that now each need to implement retry logic, idempotency, and audit trails. The cost moves, not disappears.

### Example 2: Input Validation Failure (Vague Direction)

**Input**: User asks to "challenge the new API design" without specifying what that design is.

**Output**:
> I don't have enough to argue against. "Challenge the API design" — but I need to know:
> - **What's the design?** (endpoint structure, payload format, auth scheme, versioning strategy?)
> - **What problem does it solve?** (was the old API slow? unreadable? inflexible?)
> - **What constraints exist?** (backward compatibility? performance targets? team size?)
>
> Share the design doc or describe the approach, and I'll make a strong case against it.

## Error Handling

**Error: No direction provided**
- **Detection**: After reading available context (lifecycle artifacts or conversation), no clear direction exists
- **Recovery**:
  1. Ask explicitly: "What direction or approach should I argue against? (Share a plan, design doc, or describe the approach in a few sentences.)"
  2. Wait for user response before proceeding
  3. If user still can't articulate a direction, suggest: "Perhaps start with a quick plan or spec first — once you've crystallized the approach, I can poke holes in it."

**Error: Direction is too vague**
- **Detection**: Direction lacks specificity (e.g., "improve performance," "better UX," "scale the system") without concrete technical choices
- **Recovery**:
  1. Identify what's vague: "You mentioned 'better caching' — which layer? In-process? Redis? CDN?"
  2. Ask: "Can you be more specific? What exactly are you proposing?"
  3. Example of sufficient specificity: "Use Redis for session cache with TTL of 15 minutes"
  4. Only proceed after getting concrete details

**Error: Insufficient context to argue meaningfully**
- **Detection**: The direction is specified but you lack domain knowledge or constraints (e.g., user proposes a database choice but hasn't mentioned scale, consistency requirements, or operational constraints)
- **Recovery**:
  1. Acknowledge what you understand: "I understand you're proposing X. To argue against it fairly, I need to know..."
  2. Ask specific follow-up questions: "What's the expected data volume? Consistency requirements? Operational budget?"
  3. Once context is provided, proceed with the argument
  4. If context still isn't available, argue from first principles and note your assumptions: "Assuming you need ACID guarantees and sub-100ms latency, here's why this approach breaks..."

**Error: Lifecycle artifact not found**
- **Detection**: A lifecycle is marked as active, but expected artifacts (plan.md, spec.md) don't exist
- **Recovery**:
  1. Fall back gracefully to conversation context: "I didn't find a plan in the lifecycle directory. I'll work from what you've described in conversation instead."
  2. Proceed with conversation-based argument
  3. If conversation context is also insufficient, return to input validation error handling

## What This Isn't

Not a blocker. The user might hear the case against and proceed anyway — that's fine. The point is they proceed with eyes open. Stop after making the case. Don't repeat objections after they've been acknowledged. Don't negotiate or defend your position if the user decides to proceed anyway.
