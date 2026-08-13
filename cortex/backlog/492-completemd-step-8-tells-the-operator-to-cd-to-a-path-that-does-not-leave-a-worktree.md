---
schema_version: "1"
uuid: 58da7cd0-9021-481f-914d-42732abd4b2c
title: complete.md Step 8 tells the operator to cd to a path that does not leave a worktree
status: backlog
priority: medium
type: bug
created: 2026-08-13
updated: 2026-08-13
tags: ['lifecycle', 'worktree', 'complete', 'skills']
areas: ['lifecycle']
---
Split out of #487.

## Why

`skills/build/references/complete.md:23` offers, as the non-`ExitWorktree` arm of the Step 8 hard guard, `cd $(git rev-parse --show-toplevel)`. Inside a linked worktree `--show-toplevel` returns **the worktree**, so the operator lands where they already were and the guard re-fires.

## Evidence

Verified in a real `git worktree add` on 2026-08-13, not reasoned about:

    PWD=.../wtdemo/wt
    show-toplevel: .../wtdemo/wt      # the worktree, not the main root
    branch: interactive/demo

## Role

Give Step 8 an escape that actually leaves the worktree.

## Edges

- The correct target is the main root, which `git rev-parse --git-common-dir` reaches (or the worktree gitfile's `commondir` pointer, which `interactive_lock._main_root_from_gitfile` already parses).
- This interacts with #487: whatever the operator does to escape lands them in the primary on `main`, which is the tree from which #487's confirmed defect mis-routes. Sequence accordingly.
- Shipped surface — the `plugins/cortex-core/` mirror is rebuilt by the pre-commit hook; edit the canonical file only.

## Touch-points

- `skills/build/references/complete.md:23` (+ its plugin mirror, regenerated)
