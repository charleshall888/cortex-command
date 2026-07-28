---
schema_version: "1"
uuid: 11027594-cce7-4a46-b3ff-6cdb286c70e6
title: Move dual-source drift enforcement from the commit gate to the release gate
status: abandoned
priority: medium
type: bug
created: 2026-07-27
updated: 2026-07-28
tags: ['harness', 'git-hooks', 'ci']
areas: ['tooling']
complexity: complex
criticality: high
---
## Why

`.githooks/pre-commit` Phase 4 blocks a commit when `git diff --quiet -- plugins/$p/` reports a difference. That compares the **working tree against the index**, which answers "is the plugin tree clean?" rather than "is this commit internally consistent?" — so it fires on unstaged plugin changes that are not part of the commit at all. Under `git commit --only -- <paths>` (the form `/cortex-core:commit` mandates, and the form every skill-driven commit uses) git hands hooks a temporary index built from HEAD plus the pathspec'd files, so the check degenerates further into working-tree-vs-HEAD.

Observed twice in one build session on 2026-07-27 (#411, lifecycle `add-the-dashboard-ticket-feed-with`), both **false positives**:

- Blocked the plan-artifact commit on uncommitted `skills/refine/` work from a different session. Verified with `cmp`: `plugins/cortex-core/skills/refine/SKILL.md` and `references/research-phase.md` were byte-identical to their canonical sources. No drift existed.
- Blocked the Task 4 commit on a concurrent session's in-flight `skills/build/references/` edits (`plan.md`, `orchestrator-review.md`, `complete.md`, `size-pin.txt`). Same story.

Staging the mirrors does not clear it under `--only`, because the temp index is rebuilt from HEAD regardless. The only resolutions available were to have the other session commit, or to stash paths out from under a live session.

Cost is not confined to the blocked session: any two overlapping sessions in this repo block each other's unrelated commits for as long as either holds uncommitted skill edits.

## Role

Move dual-source enforcement to the boundary where it has consequences, and delete the local gate that produces false positives. Net effect on the surface: `.githooks/pre-commit` loses Phase 4 (~25 lines); `.github/workflows/auto-release.yml` gains one step (~3 lines). Phase 3's automatic `just build-plugin` rebuild — the half that makes drift rare rather than the half that blocks — is retained.

## Integration

`auto-release.yml` already runs a low-privilege `validate` job that the `release` job gates on (`release: needs: validate`), and it already inspects the plugin tree — validating skill schemas and the call graph, but never mirror consistency with `skills/`. The drift check belongs in that job:

```yaml
- name: Dual-source drift — mirrors match canonical sources
  run: just build-plugin && git diff --exit-code -- plugins/
```

On a clean CI checkout this is unambiguous — a committed tree, no index, no working tree, no `--only` temp-index semantics. It gates the release rather than the commit, which is the boundary that matters: consumers install from a tag or the main tip and never see an intermediate commit. It also cannot be bypassed with `--no-verify` and covers pushes from a machine that never ran `just setup-githooks`, both of which the local hook cannot claim.

Note the job would need `just` available on the runner, which the current steps do not install.

## Edges

- Removing Phase 4 without adding the CI step leaves **no** mirror-consistency enforcement anywhere — `validate.yml` does not check it either. The two halves must land together.
- A local pre-push hook is a weaker alternative: better than pre-commit, but still bypassable, per-machine, and opt-in. Acceptable as an addition for fast feedback; wrong as the enforcement.
- What is given up: intermediate commits on a branch may carry stale mirrors. Consumers never see them and CI gates the tip, so the residual loss is bisect purity on generated files.
- CLAUDE.md:27's "the `plugins/cortex-core/{skills,hooks,bin}/` mirrors regenerate via the pre-commit hook" stays accurate — Phase 3 is retained.
- Not a fix for `cortex-lifecycle-stage-artifacts` sweeping unrelated files into its staged set; that is #417.

## Touch points

- `.githooks/pre-commit:551-580` — Phase 3 conditional build (keep) and Phase 4 drift loop (delete)
- `.github/workflows/auto-release.yml:49-85` — the `validate` job the `release` job depends on
- `.github/workflows/validate.yml` — runs on every push and PR but does not gate the release; considered and rejected as the host for this check
- `CLAUDE.md:27` — dual-source statement; verify it still reads true after the change
- `justfile:609-648` — `build-plugin`, the rsync the check would re-run