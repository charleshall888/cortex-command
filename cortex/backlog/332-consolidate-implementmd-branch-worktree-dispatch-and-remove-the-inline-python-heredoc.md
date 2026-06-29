---
schema_version: "1"
uuid: 512a7b4d-e097-4b13-b941-e170ef75189b
title: Consolidate implement.md branch/worktree dispatch and remove the inline Python heredoc
status: complete
priority: low
type: chore
created: 2026-06-25
updated: 2026-06-29
parent: 336
complexity: complex
criticality: high
spec: cortex/lifecycle/consolidate-implementmd-branch-worktree-dispatch-and/spec.md
areas: ['lifecycle']
---
## Why

`implement.md`'s branch/worktree pre-flight (~170 lines; at 25KB the biggest single reference file) re-narrates the branch-mode + worktree decision tree that CLI verbs **already resolve** — `cortex-lifecycle-picker-decision`→`{fire,reason}`, `branch-mode`, `dispatch-choice`, `worktree-create/resolve`. The skill reads all the prose, then calls the verb that returns the answer anyway. Worse, the worktree pre-flight embeds a **33-line `python3 - <<EOF` heredoc** that checks "is the worktree path inside the repo" — a script masquerading as a reference. Surfaced in the 2026-06-25 lifecycle reference-file audit.

## Role

- Fold the path-inside-repo check into `cortex-worktree-create` (as a postcondition) or a small `cortex-worktree-verify` verb, deleting the heredoc.
- Trim the branch/worktree prose to route on the verbs' outputs (`fire`/`reason` → picker / feature-branch / worktree) rather than re-explaining each branch the CLI already computed.
- Optionally a `cortex-lifecycle-picker-options` verb emitting the resolved options array, leaving the agent to own only the `AskUserQuestion` surface.

## Integration

New/extended `cortex_command` worktree verb + edits to `references/implement.md` (+ mirror) → lifecycle-gated. **GUARDRAIL — preserve these overnight-pinned headings verbatim** (overnight prompts cite them by designator): `### 1a. Check Criticality`, `### 1b. Competing Plans`, `### 4a. Auto-Apply Requirements Drift`, `### 5. Transition`, `### Step 2 — Commit Lifecycle Artifacts`. KEEP the `${CLAUDE_SKILL_DIR}` sidecar resolution and the `EnterWorktree` auto-enter structural branch (ADR-0008/0009) — do not flatten to prose. Coordinate with #330 (implement.md's `batch_dispatch` / `phase_transition` event sites).

## Edges

- The worktree-path verify must keep the exact inside-repo contract (exit 0/2).
- Don't flatten the `selected`-vs-`suppressed` entry-mode branch to prose-only — it's a structural authorization gate.
- The `bash -s --` sidecar arg passing is load-bearing.

## Touch-points

- `cortex_command` worktree module + entry + test
- `skills/lifecycle/references/implement.md` (+ mirror)