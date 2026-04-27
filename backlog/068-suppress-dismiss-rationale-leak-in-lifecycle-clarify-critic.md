---
id: 68
title: "Suppress Dismiss-rationale leak in lifecycle clarify critic"
type: feature
status: complete
priority: high
parent: 66
tags: [output-signal-noise, lifecycle, clarify]
discovery_source: research/audit-interactive-phase-output-for-decision-signal/research.md
created: 2026-04-11
updated: 2026-04-17
session_id: null
lifecycle_phase: research
lifecycle_slug: suppress-dismiss-rationale-leak-in-lifecycle-clarify-critic
complexity: complex
criticality: high
spec: lifecycle/archive/suppress-dismiss-rationale-leak-in-lifecycle-clarify-critic/spec.md
areas: [lifecycle]
---

The clarify-critic disposition framework instructs: "Dismiss — ...State the dismissal reason briefly." No target audience is specified. Orchestrators surface Dismiss rationales to the user as inline commentary, even though Dismiss items are internal bookkeeping — resolved by the orchestrator, not requiring user input.

The actual noise flow: the critic agent's raw objections stay with the orchestrator (not user-visible). The orchestrator applies dispositions. Apply items are acted on silently (confidence revision). Ask items correctly fold into §4 questions. But Dismiss items have no routing rule — "briefly" is not "to yourself" — so they appear in the conversation.

The fix specifies the Dismiss-rationale target audience (events.log only). This requires changes to two closely related files: `clarify.md` (§3a instruction) and `clarify-critic.md` (Dismiss disposition definition).

The Ask-to-§4-merge path must not be suppressed — Ask items must still surface via `AskUserQuestion` in §4.

## Context from discovery

The research corrected an earlier misdiagnosis: raw critic findings do not leak to the user — only the Dismiss-rationale output channel does. See the Codebase Analysis section for the clarify §3a flow trace.
