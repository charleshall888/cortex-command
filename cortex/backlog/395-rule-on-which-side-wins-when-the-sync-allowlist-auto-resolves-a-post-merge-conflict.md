---
schema_version: "1"
uuid: 442b4caa-4b05-4b53-93c4-08f657354abe
title: Rule on which side wins when the sync allowlist auto-resolves a post-merge conflict
status: complete
priority: high
type: bug
created: 2026-07-16
updated: 2026-07-17
tags: ['overnight', 'morning-review', 'git']
areas: ['agentic-layer']
---
# Rule on which side wins when the sync allowlist auto-resolves a post-merge conflict

> **RULED + SHIPPED (2026-07-17, ADR-0029).** The winning side is a per-pattern property, exactly as the "single global flag is likely the wrong shape" hunch predicted: lifecycle phase artifacts (research/spec/plan.md) keep **remote** (the merged PR owns them), backlog item files keep **local** (the review's closes are the later, better-informed writes). The conf format is now `<side> <pattern>` with no silent default — a side-less line resolves nothing and its conflicts abort loudly. A replayed commit wholly superseded by remote-wins resolution is dropped via `git rebase --skip`. Tests pin both semantics and the fail-safe; pipeline.md, the conf header, and the sync docstring now state the ruling instead of describing unratified behavior. The pipeline-events.log stays un-allowlisted (union merge remains the named fix if revisited). Full rationale, rejected alternatives, and the merge-strategy coupling: `cortex/adr/0029-per-pattern-side-ruling-for-sync-allowlist-conflicts.md`.

## Why

The post-merge sync auto-resolves allowlisted conflicts by keeping the **local/replayed** side. Nobody has ever ruled that this is correct. It is the behavior the code has always had, and it went unexamined for two months because every allowlist pattern was dead — the patterns predated the umbrella relocation and matched nothing, so the resolution branch never ran. Repairing the patterns made this live for the first time.

Three documents used to claim the opposite — that the remote side wins. That claim traced to a single unexamined parenthetical in a config comment written one commit *before* the resolution script existed, then restated into a spec acceptance criterion and promoted into pipeline doctrine. The original implementation used the flag but never asserted what it meant. Git inverts the ours/theirs nomenclature during a rebase: the flag names the replayed side, so it keeps local and discards remote. Confirmed empirically against a fixture, and by the flag's own manual page. The predecessor lifecycle that made the loop live corrected all three documents to describe the real behavior **without endorsing it**, and deliberately changed nothing — this ticket is the deferred ruling that correction points at.

This is the second time this defect has been found. A prior lifecycle diagnosed the inversion correctly, recorded it as out of scope, recommended a follow-up ticket — and none was filed. The analysis then decayed for two months. Filing it this time is the whole point.

## Role

Decide which side should win, per pattern, and make the code say so. The evidence is genuinely split, which is why the predecessor deferred rather than swapping a flag:

- **Remote should win** — the only rationale ever written for the allowlist says to auto-resolve *because the overnight version from the merged pull request is authoritative*. After a merge, the remote holds the reconciled result.
- **Local should win** — a later lifecycle's post-sync content check depended on local session commits surviving the sync. Keeping remote would discard the review's own deliberate writes.

Both directions lose real data, which is what makes this a ruling rather than a bug fix:

- Keeping local can **revert merged content and push it**. The review's ticket close is written against pre-merge local state, so it lacks the write-back edits the merged pull request made to that same file. Auto-resolution then discards them and the closure verb pushes the result. The overnight write-back and the review's closer write the same frontmatter on the same ticket files, so this overlap is routine, not hypothetical.
- Keeping remote discards the review's closes — the later, better-informed actor, which ran after the merge and saw the merged state.

A single global flag is likely the wrong shape. The answer plausibly differs between files the merged pull request owns and files the review itself writes.

## Integration

The surviving allowlist patterns are the lifecycle research, spec, and plan artifacts plus the numbered backlog items — the four that match tracked files. Five were pruned as unfireable: four matched zero tracked files (a file that is never tracked cannot conflict), and the append-only pipeline event log was removed because **neither side is correct for an append-only file** — picking either discards the other's appended events. Removing it makes such a conflict abort loudly rather than silently lose events. If the ruling revisits it, the honest fix is a union merge, not a side.

Note the ruling interacts with the merge strategy: the predecessor spec calls the resolution's dependence on the pull request being merged with a merge commit a load-bearing coupling, and says a change of strategy would require re-evaluating the resolution.

## Edges

- Do not rule from the documents. Every "remote wins" statement traced back to one parenthetical nobody re-derived; the documents now say "local", which is a description of behavior, not a decision. Both are evidence about *what people believed*, not about what is right.
- The conflict-path coverage deliberately does **not** assert which side survives, so the tests will not block either ruling — and will not catch a wrong one either. A test that pins the chosen semantic is part of the work.
- Whichever side wins, the loop is live now and keeps local in the meantime.

## Touch points

- `cortex_command/git/sync_rebase.py` — the resolution call and its docstring
- `cortex_command/overnight/sync-allowlist.conf` — the pattern list and its header
- `cortex/requirements/pipeline.md` — where the old claim became doctrine
- `tests/test_git_sync_rebase.py` — the conflict arms that decline to pin a side
- `skills/morning-review/references/walkthrough.md` — the post-merge sync step that invokes it