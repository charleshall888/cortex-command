---
schema_version: "1"
uuid: fcbf4c15-f86d-4a37-846e-3ef46f50fdd0
title: CORTEX_AUTO_ENSURE=0 cannot be honoured inside a worktree, so init-ensure blocks lifecycle entry with no escape hatch
status: in_progress
priority: medium
type: bug
created: 2026-08-07
updated: 2026-08-08
tags: ['lifecycle', 'worktree', 'init-ensure']
areas: ['lifecycle', 'install', 'tests']
complexity: moderate
criticality: high
spec: cortex/lifecycle/cortex-auto-ensure0-cannot-be-honoured/spec.md
lifecycle_phase: research
---
## Why

`CORTEX_AUTO_ENSURE=0` is documented as the opt-out that silences `cortex-lifecycle-init-ensure`, in two places: the verb's own docstring (`cortex_command/lifecycle/init_ensure.py:16`, "0 -- success / no-op (or CORTEX_AUTO_ENSURE=0 opt-out)") and `cortex/requirements/project.md`'s `CORTEX_AUTO_ENSURE=0 opt-out` bullet ("Silences `cortex init --ensure` (and `cortex-lifecycle-init-ensure`)"). Inside an attached git worktree it does not work, because the R11 worktree guard returns exit 2 at `init_ensure.py:115` before control ever reaches the handler that honours the opt-out at `cortex_command/init/handler.py:141`. The in-code comment states the ordering is deliberate: "R11: refuse inside an attached worktree BEFORE any other check."

**Observed failure, 2026-08-07, lifecycle #469.** Running the build skill's Review phase from inside the interactive worktree, `cortex-lifecycle-enter --phase review` returned `{"state":"blocked","ensure_code":2}` with `.session` unwritten. Re-running with `CORTEX_AUTO_ENSURE=0` produced byte-identical output — the documented escape hatch had no effect in exactly the situation that needs it. The lifecycle could only proceed by leaving the worktree entirely (`ExitWorktree`) and re-entering the phase from the primary checkout.

Same root cause, second symptom: three `just test` recipes (`test-init`, `tests`, `tests-lifecycle-backlog-cortex`) fail for any run inside a worktree. A builder on #469 independently diagnosed these as worktree-environment failures and verified they were pre-existing by moving its own test file aside.

Third symptom, downstream: being forced out of the worktree makes `cortex-load-requirements` report the *primary* checkout's state. During #469's review that meant the loader printed the pre-fix routing row with `(skipped: file absent)` — a reviewer following `skills/build/references/review.md` §1 literally would have assessed the feature against the very defect it fixes, with no warning, since the no-match note only fires when *zero* area docs match. Inputs had to be gathered from the worktree by hand.

## Role

Decide which of two stated requirements outranks the other when they conflict, then make code and docs agree. This is not a one-line reorder — both sides are pinned by tests:

- **R11(a)** (`cortex_command/lifecycle/tests/test_init_ensure.py:302`) asserts exit 2 plus a stderr diagnostic inside an attached worktree.
- **R11(b)** (`:377`) sets `CORTEX_AUTO_ENSURE=0` and its docstring explicitly relies on the current ordering — "the helper short-circuits immediately after the probe passes".

So the ordering is load-bearing in at least one existing test's reasoning, and flipping it changes a contract rather than fixing an oversight.

## Integration

Candidate resolutions, to be weighed in refine rather than pre-selected here:

1. **Opt-out wins**: check `CORTEX_AUTO_ENSURE=0` before the worktree probe and return 0. Rationale — with the opt-out set the verb writes nothing, so refusing protects against nothing and only blocks the caller. Costs an R11(a) amendment.
2. **Guard wins, docs corrected**: keep the ordering and remove the opt-out claim from the docstring and `project.md`, then give `cortex-lifecycle-enter` its own way to proceed when ensure is not required for the phase being entered.
3. **Narrow the guard**: refuse only when ensure would actually write (no marker / scaffolding needed), returning 0 when it would be a no-op regardless of the opt-out.

Whichever wins, `cortex-lifecycle-enter` should not return `blocked` for a phase that needs no scaffolding — the `cortex/` tree is already bootstrapped in the shared repo, and every worktree sees it.

## Edges

- The guard exists for a real reason: scaffolding `cortex/` from a worktree could write to the wrong root. Any fix must keep that protection for the case where ensure would genuinely write.
- `plugins/cortex-overnight/install_core.py` duplicates install-state logic inline for the SessionStart hook; check whether the same ordering assumption is mirrored there before changing the contract.
- The overnight runner uses worktrees heavily. Verify whether it hits this path today or bypasses it, since a behavior change there is higher-stakes than the interactive path.

## Touch-points

- `cortex_command/lifecycle/init_ensure.py:104,115` — the docstring claim and the guard.
- `cortex_command/init/handler.py:140-141,382` — the two opt-out checks that never run inside a worktree.
- `cortex_command/lifecycle/tests/test_init_ensure.py:302,377` — R11(a)/R11(b).
- `cortex/requirements/project.md` — the `CORTEX_AUTO_ENSURE=0 opt-out` bullet.
- `cortex_command/lifecycle/enter.py` (the `blocked` / `ensure_code` path) — the caller that surfaced this.
- `justfile` — the three recipes that fail inside a worktree.
