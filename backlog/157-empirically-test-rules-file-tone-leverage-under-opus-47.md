---
schema_version: "1"
uuid: 4ca8d1fe-5592-47b2-9d63-d748d499167f
title: "Empirically test rules-file tone leverage under Opus 4.7+"
status: wontfix
priority: low
type: chore
created: 2026-05-04
updated: 2026-05-04
parent: "82"
blocked-by: []
tags: [opus-4-7-harness-adaptation, policy]
---

## Motivation

Gives R7 trigger (b) a concrete re-litigation path by converting the deferred
empirical question from a passive note into an actionable backlog gate. Until
this test exists, the trigger ("an empirical test of rules-file tone leverage
under 4.7+ returns a positive result") cannot fire because no test is queued.
References ticket #91 (parent epic #82); #91 documented the OQ6 escalation-tone
policy and explicitly punted the empirical question to this follow-up.

## Test design

- Write a single tone directive to `~/.claude/rules/cortex-tone-test.md` (e.g. a
  short, unambiguous instruction biasing toward warmer user-facing summaries).
- Run paired dispatches on a fixed user-facing-summary prompt under Opus 4.7+:
  one dispatch with the rules file present, one with it removed.
- Compare the two outputs for any warmth shift attributable to the directive
  (e.g. softer hedging, more affirming phrasing, differences in sign-off tone).
- Document the result inline in this ticket; if positive, that finding is the
  R7 trigger (b) signal that re-opens the OQ6 must/should-escalation decision.

## Out-of-scope

One-shot empirical test, not ongoing rules-file deployment. No infrastructure
changes, no new harness mechanism, no recurring tone-monitoring system. The
output is a single recorded result that either fires R7 trigger (b) or does
not.

## Resolution (2026-05-04) — wontfix

Closing without execution. R7 trigger (b) (in-repo empirical test) is
dominated by triggers (a) (Anthropic publishes guidance) and (e) (Anthropic
ships an officially-supported tone-control mechanism), which are stronger
signals for revisiting OQ6. A positive in-repo paired-dispatch result would
be a weak basis for reversing a policy hedge that's grounded in harness
architecture; if Anthropic publishes harness-level guidance or ships output
styles, the policy revisits through those paths without needing this test.
OQ6 remains functionally revisitable via the stronger triggers.
