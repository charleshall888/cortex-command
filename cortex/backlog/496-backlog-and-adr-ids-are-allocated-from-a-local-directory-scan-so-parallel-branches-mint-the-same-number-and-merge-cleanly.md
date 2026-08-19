---
schema_version: "1"
uuid: 6c518dba-14f7-4337-b9a4-168637fce973
title: Backlog and ADR ids are allocated from a local directory scan, so parallel branches mint the same number and merge cleanly
status: backlog
priority: medium
type: bug
created: 2026-08-19
updated: 2026-08-19
tags: ['id-allocation', 'backlog', 'adr', 'concurrency', 'create-item']
areas: ['backlog']
---
Filed from wild-light, 2026-08-19, during a cleanup of eight duplicated backlog ids and two duplicated
ADR numbers in that repo.

## What happens

`_get_next_id` (`cortex_command/backlog/create_item.py:103`) allocates by scanning the **local working
directory only**:

```python
paths = [
    *backlog_dir.glob("[0-9]*-*.md"),
    *(backlog_dir / "archive").glob("[0-9]*-*.md"),
]
...
next_id = (max(ids) + 1) if ids else 1
```

It never consults git. It cannot see another branch, another worktree, `origin/main`, or an unmerged
commit. Two sessions working in parallel therefore read the same maximum and both take `max + 1`.

Neither commit conflicts, because the two files have **different names** — `558-foo.md` and
`558-bar.md` merge cleanly and silently.

## Measured damage in one consumer

In `wild-light` on 2026-08-19: **8 backlog ids** held by two or three tickets each (`#536`, `#554`,
`#555`, `#558`, `#559`, `#560`, `#561`, `#567`) and **2 ADR numbers** (`0093`, `0097`) held by two
accepted records each.

`#554` was a **four-way** collision at its worst. One of its holders was renumbered to `#559` — and
**collided again there**, against a ticket a concurrent session had filed in the meantime.

Both surviving pairs are confirmed parallel by ancestry, not same-tree mistakes:

```
#536: 206ff4dc9 is NOT an ancestor of 0e258ec99
#555: 0bc63d6cd is NOT an ancestor of daaec38e5
```

## Why "verify after filing" does not fix it

The consumer repo already does this, and it is documented there as insufficient. The exposed window runs
from **allocation to merge** — measured at ~85 minutes on one ticket, during which concurrent sessions
filed their own copies of all three renumbered ids. A check taken at filing time is true when taken and
stale when it matters.

## Why it is expensive to repair late

The consumer's ratified rule is *a fresh, uncited collision gets renumbered; a landed, cited one keeps
its number and is disambiguated by meaning.* That rule has a half-life. Five of the eight collisions were
renumbered on 2026-08-19 for the cost of one `git mv` each, because nothing cited them yet. The other
three are now **permanent** — every holder is cited from shipped source, an ADR or a requirements doc, so
they are carried with prose disambiguation blocks instead. A bare `#554` will never resolve again.

## Options, in rough order of appetite

1. **Widen the scan to git refs.** `_get_next_id` also reads `git ls-tree -r --name-only` over
   `origin/main`, local branches and linked worktrees. Narrows the window a lot; does not close it (an
   unpushed branch on another machine is still invisible), and adds a git dependency to a function that
   currently has none.
2. **Ship a detector verb** — e.g. `cortex-check-duplicate-ids`, exit non-zero on any id held twice
   across `backlog/` and `adr/`. Consumers wire it wherever it fits their workflow. This is the cheapest
   useful thing, and it is what the consumer is building locally anyway; having it here means every
   consumer gets it and the logic is not re-implemented per repo.
3. **Make the number non-authoritative.** `uuid` is already the identity and `events.jsonl` already keys
   off it; the number lives only in the filename. If cross-referencing moved to slug-or-uuid by
   convention and tooling, a collision would be cosmetic. This is the honest fix and the largest one.
4. **Mint collision-resistant numbers** — e.g. a per-session discriminator in the allocated id. Solves
   it outright but makes ids uglier and breaks the "next number" mental model.

Option 2 is the recommendation if only one lands. It has no design risk and it is the piece consumers
cannot write correctly on their own for `adr/` as well as `backlog/`.

## Not in scope here

The consumer-side hook wiring stays in `wild-light` (`#592` there), per its own dev-tooling rule that a
defect in `cortex_command/` is filed here while `.pre-commit-config.yaml` and hook scoping stay local.
Worth knowing that the consumer's evidence puts the right stage at **pre-push** and **post-merge**, not
pre-commit — a pre-commit check catches none of these, because each parallel branch is clean on its own.
