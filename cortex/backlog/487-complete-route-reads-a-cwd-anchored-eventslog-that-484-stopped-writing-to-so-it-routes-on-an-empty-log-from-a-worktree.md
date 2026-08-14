---
schema_version: "1"
uuid: 9f25d6f0-e4bc-4cfd-9a35-fe81a29e014c
title: 'complete-route reads a CWD-anchored events.log that #484 stopped writing to, so it routes on an empty log from a worktree'
status: complete
priority: high
type: bug
created: 2026-08-13
updated: 2026-08-13
tags: ['lifecycle', 'worktree', 'events-log', 'cli', 'complete-route']
areas: ['lifecycle']
blocked-by: []
blocks: []
complexity: complex
criticality: high
spec: cortex/lifecycle/complete-route-reads-a-cwd-anchored/spec.md
lifecycle_phase: complete
---
Filed from wild-light, 2026-08-13, while routing wild-light's downstream copy of #484
(`538-lifecycle-verbs-disagree-on-repo-root-inside-a-worktree`) back upstream. #484 fixed the writer
half; this is the reader that was left behind, and the fix made its exposure *worse*, not better.

## Why

`b61c3abc` ("Anchor every lifecycle verb to one events.log") pinned every **appending** verb to
`log_resolver.resolve_events_log`, i.e. the main root. `cortex-lifecycle-complete-route` is a **reader**
of that same log and was not pinned. It resolves via `_resolve_user_project_root_from_cwd()`
(`complete_route.py:684`, and named as deliberate at `complete_route.py:26`), then reads
`lifecycle_dir / "events.log"` from disk at `complete_route.py:530,538,540` to drive its Branch-1
(`feature_wontfix`) and Branch-2 scans, plus `_head_has_feature_complete` at `:276`.

So from inside a worktree, `complete-route` decides a lifecycle's terminal routing by reading a file
**that the pinned writers no longer write to**. Before #484 the worktree copy at least received the
CWD-anchored appends from `event` and `review-brief`; after #484 it receives none. The reader's input is
now reliably empty-or-stale rather than merely partial.

## Evidence

Measured in wild-light on 2026-08-12 (wild-light #538, same session family that filed #484): with a PR
open, `cortex-lifecycle-complete-route` returned **`pr_open`** ("merge first") when run from the worktree
and **`on_main` → step9** when run from the primary, for one and the same lifecycle.

`on_main` → step9 is the finalize leg. Running it from the wrong tree therefore **completes a ticket
whose PR is still open** — the backlog item flips to `complete` with the work unmerged, and there is no
error, no warning, and no `detect_split_log` call on this path to surface the divergence.

## Role

Make `complete-route`'s reads of `events.log` resolve the same anchor its writers now use, so a routing
verdict cannot depend on which tree it was invoked from.

## Edges

- **`pr.json` is a different case from `events.log`.** `record_pr_opened.py:143` writes `pr.json`
  CWD-anchored and `complete_route` reads it CWD-anchored, so those two agree with each other. The defect
  is that a single verdict mixes a CWD-anchored `pr.json` with an `events.log` whose writers are
  main-root-pinned. Decide the anchor per artifact, then make reader and writer agree — do not assume
  both artifacts want the same answer.
- **`register_artifact.py:105` is correctly CWD-anchored and should stay.** `b61c3abc`'s own message
  states the rule: "Artifacts stay CWD-anchored: the reviewer writes review.md where the work is."
  This ticket is not an argument to pin everything.
- **`detect_split_log` already exists** and is the reporting half #484 shipped. The cheap first move may
  be to call it here and refuse rather than to re-anchor, since a wrong verdict is worse than no verdict.
- **`cortex-lifecycle-enter` refusing inside a worktree (#475) is the reason this is reachable at all** —
  the operator workaround for #475 is "run some verbs from the primary", which is exactly what produces
  a mixed-anchor session.

## Touch-points

- `cortex_command/lifecycle/complete_route.py` — `:26` (docstring stating the CWD choice), `:276`
  `_head_has_feature_complete`, `:529-540` artifact reads, `:684` root resolution
- `cortex_command/lifecycle/log_resolver.py` — `resolve_events_log`, `detect_split_log`
- `cortex_command/lifecycle/record_pr_opened.py:143`, `register_artifact.py:105` — the two CWD-anchored
  siblings, one to reconcile and one to leave alone
- `cortex_command/lifecycle/tests/test_worktree_log_anchor.py` — the #484 suite this would extend
