---
status: proposed
---

# Per-pattern side ruling for sync-allowlist conflict auto-resolution

_Decision date: 2026-07-17 (#395 — the deferred ruling the predecessor lifecycle's doc corrections pointed at)._

## Context

The post-merge sync (`cortex_command/git/sync_rebase.py`, invoked by the morning review's §6a) auto-resolves conflicts on allowlisted files during the rebase of local `main` onto the just-merged remote. Until this ruling, every auto-resolution kept the **local/replayed** side — not because anyone decided that, but because the code had always passed `--theirs`, and git inverts the ours/theirs nomenclature during a rebase (`--theirs` names the replayed side, i.e. local). Three documents claimed the opposite for months; every "remote wins" statement traced to a single unexamined parenthetical written one commit before the resolution script existed. The behavior itself went unexercised for two months because every allowlist pattern was dead after the `cortex/` umbrella relocation. Repairing the patterns made the resolution live, the predecessor lifecycle corrected the documents to describe the real behavior *without endorsing it*, and this ruling is the deferred decision.

Both directions lose real data, which is what made this a ruling rather than a bug fix:

- **Keeping local can revert merged content and push it.** The review's ticket close is written against pre-merge local state, so it lacks the write-back edits the merged PR made to the same file; auto-resolution discards them and the closure verb pushes the result.
- **Keeping remote discards the review's closes** — the later, better-informed actor, which ran after the merge and saw the merged state. A later lifecycle's post-sync content check depends on local session commits surviving.

## Decision

**The winning side is a per-pattern property of the allowlist, not a global flag.** The conf format becomes `<side> <pattern>` and the ruling is:

- **Lifecycle phase artifacts** (`cortex/lifecycle/*/{research,spec,plan}.md`) → **remote wins.** The merged pull request owns these files: the reviewed, reconciled revision is authoritative, and a divergent local copy is stale by construction. This honors the only rationale ever written for the allowlist ("the overnight version from the merged pull request is authoritative"), which was written about exactly these files.
- **Backlog item files** (`cortex/backlog/[0-9]*-*.md`) → **local wins.** These are files the review itself writes: the close is the later, deliberate act on that specific file, its terminal status supersedes the write-back's status edits, and the post-sync content check depends on those commits surviving.

Supporting rules:

- **No silent default.** A conf line without a valid side is skipped with a warning; its conflicts abort the rebase loudly (exit 1). The pre-ruling one-column format must never be silently interpreted as either side.
- **An emptied replayed commit is skipped.** When a remote-wins resolution supersedes everything a replayed commit carried, the commit is dropped via `git rebase --skip` rather than left to fail `--continue`.
- **`cortex/lifecycle/pipeline-events.log` stays un-allowlisted.** It is append-only, so *neither* side is correct; if it is ever revisited, the honest fix is a union merge (`.gitattributes merge=union`), not a side.
- The ruling inherits the predecessor's load-bearing coupling: resolution semantics depend on the PR being merged with a merge commit; a merge-strategy change requires re-evaluating this ruling.

`tests/test_git_sync_rebase.py` pins both semantics (remote-wins on a lifecycle artifact, local-wins on a backlog item) and the fail-safe (a side-less line resolves nothing).

## Trade-off (stated honestly)

Auto-resolution still discards one side's data per conflict — that is what auto-resolution *is*. This ruling confines each loss to the direction that hurts least: a discarded **local** lifecycle-artifact edit is a stale pre-merge copy of a file the session should not have been authoring; a discarded **remote** backlog write-back is a frontmatter update the close's terminal status supersedes. The residual hazard — a merged PR making a *non-status* edit to a ticket the review simultaneously closes — is accepted: the alternative (aborting on every routine backlog overlap) would re-manualize the most common conflict the sync exists to absorb.

## Rejected alternatives

- **Keep global local-wins (the status quo, rejected).** Simplest, and the live loop ran this way in the interim. Rejected because for lifecycle artifacts it can revert merged, reviewed phase outputs and push the reversion — data the repo treats as authoritative history — on the strength of a behavior nobody ever chose.
- **Global remote-wins (the documents' old claim, rejected).** Honors the original write-up but discards the review's ticket closes on every routine overlap, breaking the post-sync content check and re-teaching operators to hand-fix the sync — the habit this whole area exists to end.
- **Union merge for the allowlisted markdown (rejected).** Correct for the append-only event log (where it remains the named future fix), but wrong for YAML-frontmatter markdown: a union of two frontmatter revisions is not valid frontmatter, and a silently doubled body is worse than either side.

## Three-criteria gate clearance

- **Hard to reverse.** The effects of a resolution ruling are unrecoverable by construction — each auto-resolution permanently discards one side's data and may push the result; flipping the ruling later cannot restore what earlier syncs discarded. The ruling also spans code, conf format, tests, and doctrine docs in one coordinated contract.
- **Surprising without context.** The ours/theirs inversion misled every prior reader of this code; a contributor seeing `--theirs` mapped to "local" (and per-pattern sides at all) would "correct" it without this record. The same defect was independently found twice and the analysis decayed once already.
- **Real trade-off.** Both global directions and a union merge were credible and are rejected above for stated reasons; both surviving directions still lose real data, and the per-pattern split is the deliberate compromise.
