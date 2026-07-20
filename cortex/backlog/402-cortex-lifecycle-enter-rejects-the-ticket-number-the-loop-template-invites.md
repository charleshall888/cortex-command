---
schema_version: "1"
uuid: 47f91f1b-faab-41d5-857b-ebffeb761b48
title: 'cortex-lifecycle-enter rejects the raw ticket number the loop template invites, exit-3ing a valid resume'
status: complete
priority: medium
type: bug
created: 2026-07-18
updated: 2026-07-20
tags: ['lifecycle', 'verbs', 'skills', 'ergonomics']
areas: ['lifecycle', 'skills']
---
## Why

Observed 2026-07-18 resuming wild-light #356. `cortex-lifecycle-next "356"` resolves the ticket
number fine — the envelope carries `feature: replace-the-night-compositor-with-real` plus
`resolved_from: "356"`. The skill's Step 2 then instructs
`cortex-lifecycle-enter --feature {feature} …`, and a natural reading substitutes the token the
user typed (`356`). Enter does no number→slug resolution of its own, so it exit-3'd the resume:

> `no such lifecycle '356': --phase 'implement' is a resume, but cortex/lifecycle/356/ does not
> exist … the caller mis-threaded the identity (a raw token such as a ticket number passed where
> the resolver's canonical slug belonged …)`

The refusal itself is the right guard — an earlier incident (wild-light, `--feature 268` on a
create path) minted a duplicate `cortex/lifecycle/268/` dir when a raw number slipped through, and
this error is what now prevents that. But the identity threading is a standing trap: the resolver
owns number→slug resolution, enter deliberately doesn't, and the loop prose's `{feature}`
placeholder never says which of the two values (user token vs envelope `feature`) to thread. Every
session that resumes by ticket number pays one failed call + an error-message archaeology round to
recover. A session memory in the consuming repo currently papers over what the tooling should make
unambiguous.

Sibling ergonomic hit in the same session, worth dispositioning together: Step 1 passes the user's
args verbatim, and `cortex-lifecycle-next "356 resume implementing"` errored with
`route 'resume' is not a transition-table state` — trailing natural-language tokens are parsed as
a route rather than ignored, so the documented "pass the invocation args through" contract and the
parser disagree.

## Proposed direction

Not adjudicated — operator explicitly left the fix path open (2026-07-18); the implementer
investigates and picks. Candidate shapes:

1. **Enter resolves like next** — enter accepts a numeric/raw token and runs it through the same
   backlog resolution `cortex-lifecycle-next` uses, keeping the exit-3 guard for tokens that
   resolve to nothing (the duplicate-dir protection must survive any liberalization).
2. **Enter stays strict, prose pins the value** — SKILL.md Step 2 renames the placeholder to
   something un-misreadable (`{envelope.feature}` / `{resolved-feature-slug}`) and states the
   user's raw token must never be threaded.
3. **The envelope pre-substitutes** — next's payload carries the exact ready-to-run enter command
   (or at least a `feature_for_enter` field), removing the substitution step entirely.

Whichever lands, `cortex-lifecycle-next`'s trailing-token route parsing gets a ruling too: ignore
extra tokens, fuzzy-route them, or error with a message that names the accepted routes.

## Edges

- The duplicate-lifecycle-dir guard (raw number minting `cortex/lifecycle/<number>/`) must hold in
  every candidate — option 1 must resolve *before* the existence check, never fall back to
  creating.
- Resolution must have a single authority: if enter learns to resolve, it calls the same code path
  as next, not a second implementation that can drift.
- `resolved_from` in next's envelope suggests the resolver already distinguishes token vs slug —
  reuse that seam rather than re-deriving.
- Any prose change is plugin-side and rides the protocol-expectation range discipline; verb
  changes are wheel-side — keep both in one commit per the parity convention.

## Touch points

- `cortex_command/lifecycle/` — the enter verb's identity handling + the shared resolver next
  uses; the route/args parser behind `cortex-lifecycle-next`.
- `plugins/cortex-core/skills/lifecycle/SKILL.md` — Step 1 (args-verbatim contract) and Step 2
  (the `{feature}` placeholder and its substitution rule).
- Repro provenance: wild-light #356 resume session, 2026-07-18 — next resolved `"356"`, enter
  exit-3'd the same token with `--phase implement`.
