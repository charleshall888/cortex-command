# Research: Fix feature_complete emission-ordering strand on Step-11a commit failure (#339)

Make the lifecycle Complete phase recover cleanly from a failed Step-11a finalization commit: on re-invocation, retry the finalization when `feature_complete` is present-but-uncommitted *because the commit failed*, while still treating the legitimate uncommitted-and-done cases as done — without leaving a permanently-dirty working tree on the success path or duplicating `feature_complete` rows.

## Epic Reference

Parent epic: **#336 — Offload deterministic lifecycle mechanics to CLI verbs**. #339 fixes the offloaded `complete-route` verb (#331's output); it is a correctness-design bug, not itself an offload. (Epic #336's body has no scope text; its sibling tickets scope #329/#335 correctness bugs out as "independent — not offloads," so the parent linkage is defensible-but-worth-confirming — see Open Questions.)

## Codebase Analysis

**The bug, exactly.** `complete_route.classify()` (`cortex_command/lifecycle/complete_route.py:419-458`) scans **only the working-tree** `events.log` (`events_log.read_text()`, lines 419-421), sets `complete_seen` on any `feature_complete` row (shape-agnostic, event-key match only), and Branch 2 (453-458) short-circuits `complete_seen → already_complete → continue_to:"step12"`. Branch 2 runs **strictly before** the on-main short-circuit, Branch 3, and `_branch4` (the only `_branch4` call sites, lines 490 and 499, are after Branch 2's early-return at 458). So a working-tree `feature_complete` routes `already_complete → step12` and **never reaches 4d** — confirming the ticket's Why and **refuting its Edges claim** that a failed 11a "currently routes Branch 4d."

**Emission ordering.** `complete.md` Step 11 (147-157) emits `feature_complete` via `cortex-lifecycle-event log` **before** Step 11a. Step 11a (`cortex-lifecycle-stage-artifacts --phase complete`) stages a set that **includes `events.log`** (`stage_artifacts.py:242`), so on success the row Step 11 wrote is committed at 11a. This is exactly why #331's prescribed "emit after the commit" fix is itself buggy: `events.log` is in the staged set, so emitting after would leave the terminal row permanently uncommitted.

**Path-specific.** The interactive Complete path (`merge_anchor="merge"`) is the only one with the strand. The overnight pipeline emits `feature_complete` at review/merge time (`review_dispatch.py:323,613`, `merge_anchor="review"`), not gated by a Step-11a commit.

**Consumer map of the per-feature `feature_complete` signal — every reader reads the WORKING TREE, none reads HEAD:**

| Consumer | file:line | keys on |
|---|---|---|
| `complete_route.classify` (under fix) | complete_route.py:421 | `complete_seen` → `already_complete` |
| `detect_lifecycle_phase` (statusline + dashboard phase) | common.py:358 | substring `"feature_complete"` → `complete` |
| `extract_feature_metrics` | metrics.py:223-227 | **duplicate-tolerant** — "Use the *last* feature_complete event" |
| `scan_lifecycle._events_log_has_event` | scan_lifecycle.py:272-276 | substring |
| `_pipeline_state._has_feature_complete_event` | _pipeline_state.py:226 | substring |

If only `complete_route` becomes committed-aware, these four diverge during the rare failed-commit window (they'd say "complete" while the router retries) and self-heal once the commit lands. They are read-only observability surfaces, out of the ticket's touch-points.

**State space & routes.** `classify()` returns **12 routes** today (`_base_result` table; double-pinned by `tests/test_complete_route.py::_GOLDEN` and `tests/test_lifecycle_complete_state_routing.py::_ROUTE_CASES` + `test_twelve_routing_branches_covered`). The gap: no branch distinguishes "uncommitted because 11a failed (retry)" from "uncommitted because already done (skip)" — both collapse to `already_complete`. **Req 1b** (`test_complete_route.py:469`) pins that `classify()` writes zero `events.log` lines on every route → any committed-state check must be **read-only**. No existing committed-vs-working-tree distinction exists to reuse; `_git_out`/`_run` (95-100) are the graceful git shims (failure → None, never a traceback per the module's 30-33 contract). Worktree-CWD resolution uses `_resolve_user_project_root_from_cwd()` (ignores `CORTEX_REPO_ROOT`, honors the `.git`-file marker).

## Web Research

Every mature system facing this shape resolves it the same way: **the committed/durable record is the source of truth for "done"; the working-state marker is only "intent."** Confirmed across the DB outbox pattern (`ProcessedDate NULL`-vs-timestamp), ARIES checkpoints ("transactions up to here are committed → skip on redo," with idempotent redo), 2PC crash-recovery (a recovering participant **queries the durable record**, never guesses from local state), and migration-history tables (the canonical bug is crashing between applying and recording; the fix is atomic apply+record).

Load-bearing takeaways:
- **Marker-then-commit ordering is correct** *iff* the commit step is idempotent (commit-if-present, no-op-if-in-HEAD). Keep it; do not move to commit-then-marker (which risks double-completion).
- **Split idempotency in two**: emit-is-idempotent (don't double-append the row) and commit-is-idempotent (commit-if-pending, no-op-if-landed).
- **"Exactly-once is a myth"** — it's at-least-once + idempotent convergence under retries.
- **Anti-pattern**: conflating "clean working tree / nothing to stage" with "success" — a clean tree is ambiguous between "everything committed" and "nothing was done." The disambiguator is **what HEAD contains**, never working-tree cleanliness.

Caveat surfaced by later angles: the Web model's clean 3-state table ("uncommitted marker → always retry the commit") silently assumes the recovery action (commit) can always make progress. That assumption does **not** hold under this codebase's `commit-artifacts:false` flag and gitignored-lifecycle configs (see Adversarial).

## Requirements & Constraints

- **ADR-0004** (`cortex/adr/0004-...md`, accepted) owns "when `feature_complete` fires / what Done means." It mandates state-aware idempotent re-invocation and treats **the working-tree events.log as the canonical state store** and **emission as terminal** — it **nowhere requires `feature_complete` to be committed**. So "committed iff complete" is a **new, unencoded invariant**. Its reversal-cost gate enumerates the coupled surfaces (complete.md, review_dispatch.py, metrics.py, statusline.sh, scan-lifecycle, the kept-pauses inventory, the parity test). → The durable home for the new invariant is an **ADR-0004 amendment** (no-content-duplication rule forbids stating it only in prose); project.md:25 may want a back-pointer.
- **project.md:25** ("Multi-step lifecycle phases") binds the finalization tail (Steps 9-11a) committing artifacts via a flag-gated stage-first step on all three completion paths; the merge-wait pause (kept-pauses.md) must stay parity-green if any `AskUserQuestion` moves (it doesn't here).
- **Golden route table is triple-pinned**: `_GOLDEN` (12 rows) + `_ROUTE_CASES` (12 rows) + the "exactly 12" count assertion all update together when a route is added.
- **events-registry**: `feature_complete` is registered with a 6-key shape `{ts, event, feature, tasks_total, rework_cycles, merge_anchor}` (no `schema_version`). Idempotent emission must preserve this exact shape and not introduce a raw `"event":"feature_complete"` literal outside the registered verb path (else `cortex-check-events-registry` fires). `bin/.events-registry.md` carries a stale `common.py:198` consumer cite (actual is ~358) — a known #331 follow-up, not this ticket.
- **Metrics duplication is count-integrity hygiene, not a corpus crash** — `metrics.py` is duplicate-tolerant ("use last"); no test enforces uniqueness. Idempotent emission is still wanted for correct per-feature counts, but the ticket's "hard-indexes the corpus" framing overstates the failure mode.
- **`classify()` must stay read-only** (Req 1b). The committed check is `git show HEAD:…`/`git cat-file`, not a mutation.
- **Authoring gates**: dual-source mirror (edit canonical `complete.md`, `just build-plugin`, commit canonical+mirror together); the `<!-- finalization-commit-step -->` region token guard (`test_complete_md_finalization_commit.py`); MUST-escalation (author the idempotent guard + halt framing as soft routing, not new imperatives); "prescribe What/Why not How"; and the explicit **discriminating round-trip test, not a self-sealing prose-only test** expectation. complete.md is a reference file, so the L1 ratchet / 500-line SKILL cap do not bind unless `SKILL.md` itself is edited.

## Tradeoffs & Alternatives

Five macro-approaches were weighed. The decisive constraint is that **`commit-artifacts:false` exists** (`complete.md:162-164`): it skips Step 11a's commit by design, so `feature_complete` is legitimately, permanently uncommitted on that path. This sinks any approach whose "done" signal is "the row is in HEAD," because under that flag the row never reaches HEAD.

- **A — committed-gate + idempotent emission** (ticket's literal prescription): correct locus, but a bare in-HEAD gate **loops forever** on `commit-artifacts:false` and on any genuinely-nothing-to-commit case. Insufficient alone.
- **B — two-commit** (commit the row separately): makes the success signal unambiguous on the flag-true path, but carries the inter-commit residual window (#331-documented), a cosmetic 1-line commit per completion, and **still loops under `commit-artifacts:false`**.
- **C — emit-then-rollback** (delete the row on commit failure): **mutates an append-only log** (convention violation, auditability loss) and the rollback has its own unrecoverable crash window — the exact crash class this ticket targets. #331-documented as fragile.
- **D — commit-pending sentinel / separate `finalization_committed` event**: decidable but **adds state surface** (the spec complexity/value gate will scrutinize a new marker file or event type; the marker-file variant recurses the committed-vs-not problem; the event variant expands the registry/metrics/dashboard schema). Heaviest footprint for a rare bug.
- **E — make the terminal decision a decidable read-only predicate** (HEAD ∨ flag-false ∨ nothing-committable): closes both no-op success cases with no new state, reusing existing artifacts.

**Converged recommendation (core wave): A fused with E** — committed-aware Branch 2 + idempotent emission + a new non-terminal `finalization_retry` route, with the terminal decision made decidable. **The adversarial pass then refuted the specific predicate this converged on (`git diff HEAD`); see below for the corrected predicate.**

## State-Disambiguation Design

Defines the signals and the loop-free routing the corrected design rests on.

Signals at re-invocation: **W** (`feature_complete` in working-tree events.log), **H** (in HEAD's events.log), **flag** (`commit-artifacts`), **P** (a committable pending delta in the finalization set). Branch 2 should trigger on **(W ∨ H)** — not W alone — so the pathological ¬W∧H case (committed, then working tree reverted) still routes `already_complete`.

New Branch 2, still strictly before on-main/Branch-3/Branch-4 (which become reachable only under ¬W∧¬H, so a failed-finalization dirty tree can never fall into 4d):
- **2a: H** → `already_complete` → step12 (committed done; covers normal success + merge-brought-in success + ¬W∧H).
- **2b: W ∧ ¬H ∧ ¬flag** → `already_complete` → step12 (`commit-artifacts:false`; operator owns the commit).
- **2c: W ∧ ¬H ∧ flag ∧ ¬P** → `already_complete` → step12 (genuinely nothing git can commit — gitignored lifecycle / no repo).
- **2d: W ∧ ¬H ∧ flag ∧ P** → `finalization_retry` → re-enter the finalization tail (commit failed; re-stage+commit only).

`finalization_retry` re-enters to re-stage+commit without re-running cleanup or re-emitting; Step 11 also gains an idempotent-emission guard as a backstop. Both golden tables + the count assertion grow accordingly.

## Adversarial Review

The adversarial pass **fatally refuted the core-wave predicate** (`P := git diff HEAD -- <paths>`) and verified the refutation against git's actual behavior. `git diff HEAD` **does not report untracked files**; `stage_artifacts.stage()` uses `git add` + `git diff --cached`, which **does** stage untracked files. The two disagree precisely on untracked files, and that breaks the design in two opposite directions:

- **Finding 1 (FATAL — reproduces the ticket bug).** On the **on-main path**, `complete.md:21` skips Step 2, so artifacts are committed for the *first time* at Step 11a. A failed first commit leaves `events.log` **untracked** → `git diff HEAD` reads empty → **C=false → 2c → `already_complete`/done while artifacts stay uncommitted** = the original strand, reproduced. (The ticket Edges explicitly require this path to "re-run 9-12 cleanly.")
- **Finding 2 (FATAL — false loop-freedom).** On the **worktree/feature-branch path**, Step 2 commits artifacts, so `events.log` is tracked; in the `W∧¬H∧flag` band a tracked file differing from HEAD **always** diffs → C is identically **true**, so 2c's `¬C` arm is **unreachable**. On a persistent pre-commit-hook rejection (this repo's dual-source drift hook on a stale mirror is a live example) the commit never lands → `2d → step11a → fail → 2d` indefinitely. The "decidable, terminating machine" claim is false; it converts a *silent* strand into a *loud, non-terminating* re-halt.

Root cause: **`git diff HEAD` is the wrong predicate for "is there something to finalize-commit."** The faithful untracked-inclusive, ignored-exclusive read-only equivalent is **`git status --porcelain -- <paths>`** (or `git add --dry-run`). This correction fixes Finding 1; Finding 2's non-termination is **not** fixed by any committability predicate — it is intrinsic, and must be handled by an explicit termination policy.

Other findings:
- **F3:** `classify()` cannot compute `stage()`'s exact outcome while read-only (that needs `git add`); the plan must adopt `git status --porcelain` and **stop claiming C ≡ stage()'s signal**.
- **F4:** the existing `already_complete` golden fixtures never call `_init_repo` — they pass via a no-repo arm that's impossible in production, so the **committed (2a) path is untested**. Discriminating tests need **real repos** for: committed (2a), uncommitted+flag-false (2b), uncommitted+flag-true with **untracked** artifacts (Finding 1 lock-down), and a **failing-then-succeeding** round-trip (2d→2a).
- **F5:** the H-read must reuse `_git_out` (exit 128 / no-commits / git-absent → H=false, no traceback) **and read from the same `root` as W** — anchoring H via `_resolve_worktree_path` instead can read a *different* events.log (a stale `interactive/{slug}` worktree) → W and H decided on mismatched trees.
- **F6:** making Branch 2 own all `(W∨H)` states removes 4d `merged_dirty`'s conservative "resolve first" guard for a botched/conflicted merge that *also* has `feature_complete` present — 2d would blindly re-commit on a corrupt tree. Keep a dirtiness/sanity gate inside the retry route.
- **F7:** importing `stage_artifacts.collect_paths` drags a `cortex/backlog/*.md` glob + YAML parse onto the routing path (no hard cycle, but a weight regression); `read_commit_artifacts` (`lifecycle_config.py:157`) is the lightweight, importable flag reader.
- **F8:** the Step-11 idempotent guard is **belt-and-suspenders, not the dedup mechanism** — `finalization_retry` re-enters at the finalization tail and Branch 2 intercepts every W=true state before any path that re-runs Step 11. The spec should not market the guard as the load-bearing dedup.
- **F9 (needs verification):** the overnight path emits `feature_complete` (`merge_anchor:"review"`) without running Step 11a, and the agent could not confirm the per-feature `events.log` is committed to main's HEAD. If it is left uncommitted, a later interactive `complete` on an overnight feature would see W∧¬H∧flag∧P → spurious `finalization_retry`.

## Recommended Approach (post-adversarial, corrected)

**Committed-aware Branch 2 with a `git status --porcelain` committability guard and operator-driven (not machine-claimed) termination.** This is the ticket's prescribed structural locus, corrected for the two fatal flaws.

All signals are read-only, anchored to the **same `root`** (`_resolve_user_project_root_from_cwd()`), via the graceful `_git_out`/`_run` helpers (failure → degrade, never traceback):
- **H** = `feature_complete` in `git show HEAD:cortex/lifecycle/{slug}/events.log` (cwd=root, root-relative path; exit 128 → H=false).
- **flag** = `commit-artifacts` via `read_commit_artifacts` (lifecycle_config.py:157 — **not** `collect_paths`).
- **P** = `git status --porcelain -- <finalization set>` non-empty (untracked-inclusive, ignored-exclusive — **not** `git diff HEAD`).

Branch 2 (trigger `W∨H`, strictly before on-main/3/4):
- **2a: H** → `already_complete` → step12.
- **2b: W∧¬H∧¬flag** → `already_complete` → step12.
- **2c: W∧¬H∧flag∧¬P** → `already_complete` → step12 (gitignored-lifecycle / no-repo fallback — degrades to today's behavior for repos that don't commit `cortex/lifecycle/`).
- **2d: W∧¬H∧flag∧P∧(sanity)** → `finalization_retry` → re-enter the finalization tail; if the dirty tree looks like a botched/conflicted merge, halt "resolve first" (4d-style) instead of blind re-commit.

**Termination is operator-driven, not machine-loop-free.** 2d → finalization commit; success → H → 2a (done); failure → loud per-invocation halt (today's model, now *retryable* instead of stranded). The spec should state this honestly and may add an attempt-count marker / distinct terminal route after N failures to protect any automated caller.

Keep the idempotent Step-11 emission guard (belt-and-suspenders). Amend ADR-0004 with the committed-iff-complete invariant and its gitignore-mode fallback. Tests: real-repo discriminating fixtures (above) + the route-count assertions.

This rejects two-commit (inter-commit window; still loops under flag-false) and emit-then-rollback (append-only mutation; own crash window) on their #331-documented weaknesses, and rejects the sentinel/extra-event approaches as adding state surface for a rare bug.

## Open Questions

- **Overnight-path interaction (Adversarial F9):** Does the overnight pipeline commit the per-feature `feature_complete` row (`merge_anchor:"review"`) into main's HEAD? *Deferred — resolve in Spec by reading `runner.py`/`review_dispatch.py` commit timing. If the row is left uncommitted, Branch 2 needs an explicit guard so an overnight-completed feature re-invoked interactively does not spuriously route `finalization_retry` (e.g. treat `merge_anchor:"review"` as terminal, or require interactive `merge_anchor:"merge"` for 2d).* This is the one residual question that could add a structural guard, not just a detail.
- **`finalization_retry` re-entry point:** continue_to `step11a` (minimal re-entry; assumes Steps 8-11 outputs persist in the dirty tree; new continue_to value) vs `step9` (reuse an existing entry point; re-run the finalization tail; rely on the idempotent Step-11 guard). *Deferred — Spec/Plan choose; lean `step9` for reuse + safety unless the narrower `step11a` re-entry is proven to commit a complete set.*
- **Botched-merge sanity gate (Adversarial F6):** the predicate distinguishing failed-finalization-dirty (→ retry) from conflicted-merge-dirty (→ resolve-first). *Deferred — Spec to define (e.g. check `MERGE_HEAD`/conflict markers, or restrict 2d's re-commit to the finalization paths and halt if foreign paths are dirty).*
- **Committability probe scope:** `git status --porcelain` over `events.log` alone (cheap; sufficient since it carries the row) vs the full finalization stage set (matches `stage()` exactly but pulls the backlog-resolving `collect_paths`). *Deferred — Spec decide; lean `events.log`-only to keep `classify()` light.*
- **ADR-0004 amendment vs new ADR** for the committed-iff-complete invariant. *Deferred — lean amendment (ADR-0004 is the natural owner).*
- **`complete.md:176` `nothing_staged` note staleness (Adversarial Risk #5):** re-validate that "common on the worktree path post-merge" still describes reality under the new ordering. *Deferred — Spec/Plan re-validate the doc phrasing.*
- **Reader divergence (Clarify obj 4 / `common.py:358`):** *Resolved — the working-tree readers are read-only observability surfaces that show "complete" during the rare failed-commit window and self-heal on retry; left working-tree-based (out of the ticket's touch-points) and documented as a known cosmetic edge. Spec to confirm acceptance.*
- **`nothing_staged` row-in-HEAD contradiction** (Codebase said in-HEAD via merge; Tradeoffs implied absent): *Resolved — the corrected predicate routes both readings to "done" (2a if in HEAD; 2c if clean/ignored), so the design is robust to it.*
