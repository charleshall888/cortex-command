# Routing Disambiguation Eval — /interview ↔ backlog-author

**Task**: Task 4 (spec R1, R14). Verify representative "interview me about X" priming
phrasings route to `/interview` and ticket-authoring phrasings still route to
`backlog-author`, with no mis-route. R14 (a minimal `backlog-author` description
clarification) fires ONLY on a residual collision.

**Method**: In-session routing judgment over the concatenated `description:` +
`when_to_use:` L1 routing surface of each skill (the surface Claude Code's listing
exposes for routing). The two competing surfaces:

- `/interview` — leads with "General-purpose priming interview … help you think through
  a topic, then offers a concise brief. This is a thinking-partner interview, NOT
  backlog-ticket authoring"; `when_to_use` lists "interview me about X", "grill me on X",
  "help me think through X". Self-disambiguates by naming `/cortex-core:backlog-author`.
- `backlog-author` — leads with "Compose structured backlog ticket bodies using the
  Why/Role/Integration/Edges/Touch-points template"; trigger tokens include a bare
  "interview" but the whole surface is saturated with ticket-authoring context, and the
  `interview` subcommand is explicitly "produces a ticket body".

## Representative phrasing set + routing outcome

| Phrase | Expected | Routed to | Result |
|--------|----------|-----------|--------|
| "interview me about the auth refactor" | /interview | /interview | PASS |
| "grill me on this caching design" | /interview | /interview | PASS |
| "help me think through the migration approach" | /interview | /interview | PASS |
| "interview me before I start coding" | /interview | /interview | PASS |
| "author a backlog item for the rate limiter" | backlog-author | backlog-author | PASS |
| "write a ticket body for the new endpoint" | backlog-author | backlog-author | PASS |
| "compose a backlog ticket" | backlog-author | backlog-author | PASS |
| "interview me to draft a backlog ticket" | backlog-author | backlog-author | PASS |

The last row is the deliberate borderline: it carries both an "interview me" token
(→/interview) and an "…backlog ticket" token (→backlog-author). The ticket-authoring
object ("a backlog ticket") dominates, and `backlog-author`'s `interview` subcommand
exists for exactly this — it routes to `backlog-author` as intended.

## Verdict

**no mis-route** in the representative set. `/interview` and `backlog-author` each
resolve to their own skill. The bare "interview" token remaining in `backlog-author`'s
description is contextually dominated by its ticket-authoring surface and did not pull
any priming phrasing away from `/interview`; conversely the ticket phrasings were not
pulled to `/interview`.

**R14 disposition: NOT FIRED.** No residual collision, so the conditional
`backlog-author` description clarification is not applied — consistent with the
Non-Requirement that `backlog-author` is not changed unless the eval gate fires. The
disambiguation was achieved entirely from the `/interview` side via its self-describing
"NOT backlog-ticket authoring" framing.

Note (honest limitation, per the spec's "verified, not asserted" intent): this is an
in-session router judgment over the L1 surfaces, not an automated harness assertion —
`tests/test_skill_routing_disambiguation.py` covers the dev/lifecycle/refine/research/
discovery/critical-review cluster and does not include `interview`/`backlog-author`, so
no fixture regression is at stake. The representative-set pass is recorded here for later
inspection per R1's acceptance.
