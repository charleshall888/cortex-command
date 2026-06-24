# Specification: harden-overnight-review-agents-reviewmd-artifact

> **Scope reframed during research (user-approved).** Backlog #319 was filed as "harden the review
> agent's artifact-write *adherence*." Research falsified that premise: in the incident the review
> agent *did* write a complete, valid `APPROVED` review.md — to the worktree, where the gate never
> reads. The verified root cause is a **worktree-vs-main path-contract divergence** in the
> worktree-mode overnight review gate. This spec addresses that path contract, not write-adherence.
> The adherence mechanisms in the ticket (prompt strengthening, Stop-hook self-check, effort bump)
> are declined with rationale — see Non-Requirements. Full evidence in `research.md`.

## Problem Statement

In the overnight pipeline's worktree-mode post-merge review, the review agent runs with
`cwd=worktree_path` (`dispatch.py:792`) and is handed a **relative** write target,
`cortex/lifecycle/{feature}/review.md` (`prompts/review.md:51`), so it writes inside the worktree.
The gate computes the same relative path against the **orchestrator's** cwd — the main repo — because
`lifecycle_base` defaults to the relative `Path("cortex/lifecycle")` (`review_dispatch.py:149,208`)
and all three `dispatch_review` call sites omit it (`outcome_router.py:1114,1521,1831`). Writer and
reader anchor the identical relative path to different roots: the agent writes to the worktree, the
gate (and every downstream reader) looks in main and finds nothing → synthetic `ERROR` →
`could_not_run`. The fix makes the writer and the gate use one explicit absolute path under the
main-repo lifecycle base, where the morning report, verdict extraction, and drift reader already
look. This restores trustworthy worktree-mode overnight reviews; the operator benefits because a
clean merge is no longer flagged "unreviewed — needs human re-review" on a false signal.

**Premise dependency (recorded for honesty).** This diagnosis holds *if* the incident was a
could-not-run (agent ran, `success==True`, gate read an empty main path). The independently-verified
worktree artifact — a valid 5181-byte `APPROVED` review.md the agent wrote — is strong corroboration
that the agent did run and write. The incident's `feature_deferred` event also carried
`review_dispatch_crashed=true`, which in current code is mutually exclusive with `could_not_run`; that
contradiction is the deferred flag-coherence defect (see Non-Requirements) and the build-version-at-run
is unverified. The path fix is correct under the could-not-run reading the artifact evidence supports;
the flag-coherence triage is what confirms it conclusively.

## Phases
- **Phase 1: Path-contract fix** — make the review agent write, and the gate read, one absolute main-repo `review.md` path across all three review-gate call sites and **both** prompt-render seams (cycle 1 and cycle 2).
- **Phase 2: Regression guard** — a test that pins the property that actually distinguishes the bug (the rendered prompt carries the absolute path and no bare-relative literal, in both render seams), so the divergence cannot silently return, with the full suite green.

## Requirements

1. **Agent writes to the absolute main-repo path (writer side), at every render seam.** The review
   prompt the agent receives names an absolute `review.md` path under the main-repo lifecycle base,
   not a relative one. `_load_review_prompt` (`review_dispatch.py:110-135`) gains a `{review_md_path}`
   substitution, `prompts/review.md:51` uses it, and **both** invocations of `_load_review_prompt` —
   cycle 1 (`review_dispatch.py:243`) and cycle 2 (`review_dispatch.py:519`) — pass the absolute path,
   so neither render emits an unsubstituted `{review_md_path}` literal. Prefer making the new
   parameter **required** (no default) so a missed call site fails at construction rather than
   rendering a literal placeholder. **Acceptance:** a unit test renders the prompt via
   `_load_review_prompt` for each render seam with a sample absolute path and asserts the rendered
   prompt (a) contains that absolute path and (b) contains no bare relative
   `cortex/lifecycle/<feature>/review.md` literal. Pass if both hold for both seams. **Phase**: Path-contract fix

2. **Gate reads the absolute main-repo path (reader side), at both cycle seams.** `dispatch_review`
   resolves `review_md_path` (`review_dispatch.py:208`) to an absolute path under the main-repo
   lifecycle base (the `_resolve_lifecycle_base()` resolver, `feature_executor.py:91`), passes that
   same absolute value into both `_load_review_prompt` calls, and the cycle-1 read (`:293`) and
   cycle-2 read (`:563`) both consult it. **Acceptance:** a unit test invokes the path resolution with
   an absolute `lifecycle_base` and asserts `review_md_path.is_absolute()` is true and
   `review_md_path == lifecycle_base / feature / "review.md"`. Pass if both hold. **Phase**: Path-contract fix

3. **All three review-gate call sites anchored to an absolute base.** The primary
   (`outcome_router.py:1831`), recovery (`:1114`), and repair-completed (`:1521`) `dispatch_review`
   calls each pass an absolute `lifecycle_base` (via `_resolve_lifecycle_base()`), so worktree-mode
   review works on every merge-to-`merged` site. **Acceptance:** a test asserts that, for each of the
   three call paths, the `lifecycle_base` reaching `dispatch_review` satisfies `Path(...).is_absolute()`
   (value-level check — not a `grep` for the token, which cannot distinguish an absolute base from a
   relative one). Pass if all three resolve absolute. **Phase**: Path-contract fix

4. **Regression guard pins the bug-distinguishing property (not a same-source tautology).** A test
   guards the property whose absence *was* the production bug: that the path the agent is told to write
   (the rendered prompt literal) is the same absolute path the gate reads, AND that the rendered prompt
   contains no bare-relative `cortex/lifecycle/<feature>/review.md` that would re-resolve against the
   agent's worktree cwd — checked for **both** the cycle-1 and cycle-2 renders. A bare
   `writer_path == reader_path` equality of two same-source in-process values is explicitly
   insufficient (it passes by construction and never exercises the cwd/env split). **Acceptance:** a
   new test (e.g. `tests/test_review_path_contract.py`) asserts, for both render seams, that the
   rendered-prompt target equals the gate's `review_md_path`, that target `.is_absolute()`, and that the
   rendered prompt contains no bare-relative review.md literal; the test runs under `just test`. Pass if
   the test exists and all assertions hold. **Phase**: Regression guard

5. **Suite green.** The full test suite passes with the change. **Acceptance:** `just test` exits 0;
   pass if exit code = 0 (external/environmental failures — concurrent-fixture races, sandbox-network
   MCP — excluded per prior lifecycle precedent). **Phase**: Regression guard

## Non-Requirements

- **Does NOT modify the #314/ADR-0015 gate.** The `could_not_run` vs `review_dispatch_crash` split,
  the preserve-vs-revert decision, the `could_not_run` discriminator, the integration-PR degraded
  marker, and the systemic breaker are all unchanged. `parse_verdict` remains the gate seam; this spec
  only changes *which absolute directory* that seam reads and the agent writes.
- **Does NOT add a Stop hook, structured-output (`output_format`), or forced-tool affordance.** Per
  research/adversarial analysis these target write-*adherence*, which was not the failure; a Stop hook
  in particular runs in the agent's worktree cwd, would find the file present there, and never fire.
- **Does NOT bump effort or escalate the review model.** Declined: model-gated (sonnet rejects
  `xhigh`, `dispatch.py:188`) and the failure was mechanical, not reasoning-depth. Per the
  MUST-escalation policy the decline is recorded here; a separate low-priority note may capture that
  the review dispatch exposes no independent effort override.
- **Does NOT strengthen the prompt's write instruction.** It already carries CRITICAL/MUST language;
  the agent obeyed it. More prose would not help.
- **Does NOT change the interactive reviewer prompt** (`skills/lifecycle/references/review.md`). It
  already agrees with the overnight prompt on the verdict-JSON contract; agent cwd == gate cwd == main
  on the interactive path, so no divergence occurs there.
- **Does NOT add review.md to `sync-allowlist.conf`.** review.md is a **main-written runtime
  orchestrator artifact** in the same lane as the per-feature `events.log` (also written to main by the
  orchestrator and also absent from the allowlist) and the morning report (committed to local main
  directly per `pipeline.md`). It is deliberately *not* a PR-traveling implement-time artifact like
  `research.md`/`spec.md`/`plan.md` (which are committed in-worktree and reconciled via the allowlist),
  so no allowlist entry is needed or wanted.
- **Does NOT fix the flag-coherence defect** (incident `feature_deferred` asserting `merge_reverted` +
  `could_not_run` + `review_dispatch_crashed` simultaneously). Filed as a separate ticket; the premise
  note above records the dependency.

## Edge Cases

- **Agent cannot write the absolute main path (sandbox/permission).** The write succeeds because
  `cortex init` registers `<main-repo>/cortex/` in the **user-scope** `settings.local.json`
  `sandbox.filesystem.allowWrite`, which unions with the per-dispatch `--settings` sandbox config under
  the documented `denyWrite > allowWrite` precedence (`docs/overnight-operations.md:639`). Note
  `--dangerously-skip-permissions` does **not** override a sandbox denial (`overnight-operations.md:659`),
  and the per-dispatch `build_dispatch_allow_paths` (`sandbox_settings.py:138-168`) does *not* itself
  emit the main path — so the cortex-init user-scope registration is the load-bearing dependency (see
  Technical Constraints). If the write is ever genuinely denied, the existing `could_not_run` gate still
  catches the missing artifact (preserve merge + flag) — the safety net is unchanged.
- **Trunk/interactive review path** (agent cwd == gate cwd == main). With both sides on an absolute
  main path the result is identical to today — the fix must not regress the path that already works.
  Covered by R5 (existing review-gate tests stay green).
- **Cycle-2 review after rework.** Both the cycle-2 prompt render (`review_dispatch.py:519`, writer)
  and the cycle-2 read (`:563`, reader) use the same absolute path as cycle 1; R1, R2, and the R4
  parity guard all explicitly cover both render seams, so a cycle-2 render cannot keep a relative target.
- **A stale `review.md` already in the main lifecycle dir.** The #314 fix already prevents a stale
  on-disk verdict from approving a crashed dispatch (`success==False` forces ERROR without reading
  disk); anchoring the write to the same absolute path means a fresh run overwrites the stale file
  in place. No new stale-read surface is introduced.

## Changes to Existing Behavior

- **MODIFIED:** review prompt write target — relative `cortex/lifecycle/{feature}/review.md` → an
  absolute main-repo path substituted as `{review_md_path}`, at both the cycle-1 (`:243`) and cycle-2
  (`:519`) prompt renders.
- **MODIFIED:** `dispatch_review` `review_md_path` resolution — relative-default `lifecycle_base` →
  absolute main-repo base supplied by all three call sites.
- **MODIFIED (incidental, behavior-preserving):** because `lifecycle_base` also derives
  `feature_events_log` (`review_dispatch.py:207`) and `learnings_dir` (`:400`), anchoring it to absolute
  also governs those writes. This is a **no-op today**: the orchestrator runs with home-repo cwd on
  `main` (`runner.py` "home-repo CWD on `main`"), so the relative default already resolved to the same
  main path. The change makes that resolution explicit rather than cwd-dependent.
- **ADDED:** a regression test pinning writer/reader path agreement and rendered-prompt absoluteness
  across both render seams.

## Technical Constraints

- The agent runs with `cwd=worktree_path` and `CORTEX_REPO_ROOT=worktree_path` (`dispatch.py:690,792`);
  the orchestrator's `CORTEX_REPO_ROOT` is pinned to the home/main repo (`runner.py` sets it before
  spawning the orchestrator). The fix must therefore pass an **explicit absolute** path computed
  orchestrator-side (not rely on either side's cwd/env), so the two environments cannot re-diverge.
- **Resolver parity:** the writer base `_resolve_lifecycle_base()` (`feature_executor.py:91`) and the
  reader paths in the morning report (`report.py:904/920/1129`) and verdict extraction (`common.py:328`)
  all bottom out in `_resolve_user_project_root()`, so they compute the byte-identical absolute
  `<main>/cortex/lifecycle/...` path. Reuse `_resolve_lifecycle_base()` rather than introducing a new
  path-resolution path.
- **Sandbox dependency:** the agent's out-of-cwd write to the absolute main path relies on cortex-init's
  user-scope `allowWrite` registration of `<main>/cortex/` (the per-dispatch sandbox does not grant it).
  cortex-init is required setup, so this holds for any correctly-initialized deployment; if a future
  Claude Code change made `--settings` *replace* rather than union the sandbox config, the fix would
  need an orchestrator-side write instead (the orchestrator is not per-dispatch-sandboxed). Recorded so
  the dependency is not silent.
- No L1-surface, SKILL-parity, or size gate governs `prompts/review.md` or `review_dispatch.py`
  (package internals); the events-registry gate only fires if a new event name is introduced (none is).

## Open Decisions

None. The fix direction (anchor to absolute main path — chosen over read-from-worktree because every
downstream reader resolves the main path and review.md shares the per-feature `events.log` main-written
lane) and the backstop (a bug-distinguishing regression test, no runtime re-check) were resolved during
the spec interview and the critical-review pass.

## Proposed ADR

None considered. The change is a correctness fix, not a hard-to-reverse architectural decision with a
real trade-off; the #314/ADR-0015 decision it sits in front of is unchanged.
