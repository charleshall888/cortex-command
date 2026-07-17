---
schema_version: "1"
uuid: 746eeb6a-5aa8-405c-b187-81d39549d42c
title: The post-merge sync's documented contract still misstates success and overloads exit 1
status: complete
priority: medium
type: bug
created: 2026-07-16
updated: 2026-07-17
tags: ['overnight', 'morning-review', 'git']
areas: ['agentic-layer']
---
> **SHIPPED (2026-07-17).** The fetch failure got its own code — exit 4 — documented in the module header beside the others, mapped in the walkthrough's §6a arm (network/auth, nothing rebased, no conflict to resolve, re-run after checking connectivity), and pinned by a stubbed-subprocess test copying the behind-count idiom. The success criterion in `pipeline.md` is now one-sided, as the code can hold: not-behind only, with `cortex-morning-review-push-closures` named as the reason the other direction is deliberately unpromised. The third exit-1 site is diagnosed, not just listed: exhausted passes deliberately **shares** exit 1 with the conflict abort — both leave the same aborted-and-restored state with the same manual remedy — and the walkthrough's exit-1 arm now names both causes with stderr as the discriminator, so the operator prose is truthful for every exit-1 fire.

# The post-merge sync's documented contract still misstates success and overloads exit 1

## Why

Two surviving mismatches between the post-merge sync's documented contract and its code, both found by review while confirming a lifecycle that repaired five others of exactly this class. Neither was in that lifecycle's scope: one is a claim that was never true rather than one that went stale, and the other sits one step earlier than the requirement that fixed its sibling. Both are cheap to lose now that the lifecycle carrying the analysis is archiving, which is the only reason this ticket exists.

**The success criterion is false on the common path.** The pipeline requirements claim that after the sync completes successfully, local and remote are identical — both directions of the revision count read zero. They are not. The sync returns success from its early up-to-date exit roughly ninety-five lines before it ever reaches its push, so a successful run routinely leaves local ahead of remote with nothing pushed. This is not staleness: the claim never held. The code and the closure verb's own requirement agree with each other and describe this correctly — the closure verb refuses to delegate its push to the sync *because* of this early return, and says so. Only the requirements line dissents.

**Exit 1 is overloaded, and the operator-facing prose misreports one of its causes.** The sync returns 1 from three unrelated places: a failed fetch, a conflict outside the allowlist, and exhausted rebase passes. Both the module header and the morning review's exit-1 arm describe only the conflict case. So after a fetch failure the operator is told that the sync hit unresolvable conflicts and that local main is diverged, and is handed a manual rebase command — three claims that are each false in that case, and the suggested command fails the same way the fetch just did. The behind-count requirement that landed in the same lifecycle names an auth failure and network loss among the modes to surface honestly; it fixed them at the behind-count step while the sibling failure one step earlier still renders as a conflict.

## Role

Make the sync say what it did. The lifecycle that preceded this ticket established the pattern to follow: a failure mode that cannot be distinguished by its exit code gets its own code, documented in the module header beside the others, and mapped in the operator-facing prose — including a catch-all so the next code cannot silently reopen the gap. The fetch failure is the same shape as the behind-count failure that got this treatment: an infrastructure fault masquerading as a normal outcome.

The success criterion needs the opposite move — delete the claim rather than restate it. Prefer stating what success means in terms the code can hold to; a criterion that reads as a two-sided identity invites exactly the false-confidence this ticket documents.

## Integration

The exit-code map in the morning review now carries an arm per documented code plus a catch-all for unrecognized ones, so a new code for the fetch failure has an obvious home and the catch-all covers the window before the prose is updated. The module header is the single list every consumer reads.

Whoever takes this should check the remaining exit-1 site — exhausted passes — with the same question: does the operator prose tell the truth when this one fires? It is listed here as a third instance rather than diagnosed; the reviewer named it but did not trace it.

## Edges

- The success-criterion line and the exit-code overload are one ticket because they are one class, not because they are one fix. They touch different files and neither depends on the other.
- Do not fold in the allowlist side ruling — that is a separate open decision with its own evidence.
- The conflict-path coverage exercises the allowlist arm and the abort arm. A fetch failure has no test today; the behind-count failure's stubbed-subprocess test is the idiom to copy.

## Touch points

- `cortex/requirements/pipeline.md` — the false success criterion
- `cortex_command/git/sync_rebase.py` — the three exit-1 sites and the module header
- `skills/morning-review/references/walkthrough.md` — the exit-1 arm that misreports a fetch failure
- `tests/test_git_sync_rebase.py` — where a fetch-failure case would go