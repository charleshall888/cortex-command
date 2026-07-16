---
schema_version: "1"
uuid: d6860b1b-f56a-465f-812c-37650a123379
title: cortex-lifecycle-enter/state accept a numeric feature and create a shadow lifecycle dir instead of resolving or rejecting
status: in_progress
priority: medium
type: bug
created: 2026-07-15
updated: 2026-07-16
tags: ['lifecycle', 'cli', 'slug-resolution']
areas: ['lifecycle']
lifecycle_phase: research
lifecycle_slug: cortex-lifecycle-enter-state-accept-a
complexity: complex
criticality: high
spec: cortex/lifecycle/cortex-lifecycle-enter-state-accept-a/spec.md
---
## Why

Found during an interactive `/cortex-core:lifecycle 269` run in a consumer repo (wild-light). `cortex-lifecycle-next 269` resolves the ticket id to the slug correctly (`"feature":"night-fairness-accessibility-backbone","resolved_from":"269"`). But the sibling lifecycle verbs do **not** apply that resolution, and they diverge in silent, data-placement-corrupting ways when handed the same numeric id:

- `cortex-lifecycle-enter --feature 269 …` **silently created a shadow `cortex/lifecycle/269/` dir** (a fresh `index.md` + `.session`) instead of binding to the existing `night-fairness-accessibility-backbone/` lifecycle, returning `{"index":"created","feature":"269"}`. Its own help declares `--feature SLUG`, so a numeric arg is off-contract — yet it neither resolves nor rejects; it treats the number as a brand-new slug and materializes a directory.
- Because `.session` bound to the shadow dir, `cortex-critical-review-write-residue` (via `cortex-critical-review-resolve-feature`, which returned `"269"`) wrote `critical-review-residue.json` into `269/`, not the real lifecycle dir — the morning report would never find it.
- `cortex-lifecycle-register-artifact` then returned `{"state":"no-index"}` (the index was in the shadow dir).
- `cortex-lifecycle-state --feature 269 --field criticality` returned `{}` (empty), while `--feature <slug>` worked.

Recovery required manually re-running `enter` with the slug, moving the residue, and `rm -rf cortex/lifecycle/269/`. Left unrecovered, this yields a shadow lifecycle dir, a mis-bound session, and residue the morning report cannot see.

This is the same resolver-consumer gap #254 closed for `cortex-update-item` (extending the #109/#176 unified resolver), and the same numeric-vs-slug family as #378 item 1 (numeric `lifecycle_slug` frontmatter) — but the lifecycle verbs (`enter`, `state`) and the critical-review residue resolver were never extended to that shared resolver, and their failure mode (silent shadow-dir + mis-bound session) is worse than a fast reject.

## Proposed direction

Two viable fixes; the maintainer should pick:

1. **Resolve** — route `enter` / `state` / the residue resolver through the shared slug resolver under `cortex_command/backlog/` (the module #254 reused), so a numeric id resolves to its slug dir like `cortex-lifecycle-next` already does. Confirm reachability without crossing the install_guard boundary (the DR4 concern from #254).
2. **Reject** — since `enter` may intentionally trust a pre-resolved slug from `next`'s envelope, make it (and `state`, and the residue resolver) **fail loud** on a feature that has no matching lifecycle dir: `no such lifecycle "269"; did you mean night-fairness-accessibility-backbone?` — instead of silently creating a shadow `<value>/` dir.

Silent shadow-dir creation on an unmatched feature is the core footgun regardless of which fix lands. A regression sample should cover every (lifecycle verb, numeric-feature input) pair.

## Edges — considered

- `cortex-lifecycle-enter` is the highest-risk consumer because it **writes** (creates the dir + binds `.session`); `state` only reads (returns `{}`). Fixing only the read side leaves the corruption path open.
- Partly caller misuse: the lifecycle SKILL.md Step 2 tells the caller to thread the served `feature` slug, and passing the raw ticket id is off-contract. This ticket is about the tooling's **silent** failure mode, not the misuse itself — a verb that silently forks a shadow lifecycle is worth hardening regardless.
- If the fix is "resolve," note behavior change: each verb begins accepting inputs it currently mishandles; evaluate the fail-fast regression sample first (same caution #254 recorded).

## Touch points

- `cortex_command/lifecycle/enter.py` + `bin/cortex-lifecycle-enter` (`--feature SLUG`) — the shadow-dir + `.session` write path.
- `bin/cortex-lifecycle-state` — returns `{}` on a numeric feature.
- `cortex_command/critical_review/resolve_feature_cli.py` + `cortex_command/critical_review/write_residue_cli.py` — session→dir resolution; residue landed in the shadow dir.
- `bin/cortex-resolve-backlog-item` / the shared resolver module under `cortex_command/backlog/` — the candidate reuse surface (already consumed by `cortex-update-item` per #254).
- Related: #254 (resolver → `cortex-update-item`, complete), #251 (harness-friction epic, complete), #378 item 1 (numeric `lifecycle_slug` frontmatter).