# Research: Make `complete-route` produce the same terminal routing verdict regardless of which tree it is invoked from

Scope anchor (clarified intent): reconcile each `complete-route` verdict input's **read** anchor with
the anchor its **writer** uses, so the verdict cannot depend on the invoking tree.

**Headline correction to the ticket.** #487 describes one defect with two symptoms. Execution shows the
opposite: the `events.log` half of its Why is **largely dead**, and the `pr.json` half in its Evidence is
**real, confirmed end-to-end, and fixed by neither of the ticket's proposed moves**. Details in
`## Adversarial`. Two of this document's findings were produced by running code after both static angles
had concluded; nothing below marked CONFIRMED rests on reading alone.

## Codebase

### The verdict has nine tree-dependent inputs, not two

`main()` (`complete_route.py:684`) resolves one `root` via `_resolve_user_project_root_from_cwd()` and
hands it to `classify(slug, root)`, which derives `lifecycle_dir = root/"cortex"/"lifecycle"/slug`
(`:528`). Both `events_log` and `pr_json` descend from it — but four further inputs bypass `root`
entirely and read the bare process CWD.

| Input | Site | Anchor today | Writer's anchor |
|---|---|---|---|
| `events.log` scan (Branch 1/2) | `:530,538` | `root` (CWD) | mixed — see below |
| `pr.json` read | `:529,654-659` | `root` (CWD) | CWD (`record_pr_opened.py:143`) — **agrees** |
| `_current_branch()` | `:116-119` | **bare process CWD** (no `cwd=`) | n/a (reflects real git state) |
| `_head_has_feature_complete` | `:290,295` | `cwd=root` — asks *which commit that tree's HEAD is* | n/a |
| `_finalization_committable` | `:358-361` | `cwd=root` — that tree's index/worktree state | n/a |
| `_drift_files_from_review` | `:355` | `root` (CWD) | reviewer writes `review.md` where the work is — agrees |
| `read_commit_artifacts(root)` | `lifecycle_config.py:217` | `root` | tracked project config, not per-tree |
| `_resolve_worktree_path` | `:133,155` | process CWD, `root` only as fallback | discovers the real worktree itself |
| `_orphan_probe` / `_gh_repo` | `gh`, no `cwd=` | process CWD | n/a |
| `_reconstruct_pr_json` **write** | `:267` | `root` (CWD) | is itself a writer |

### There are four root-resolution flavours in this subsystem, not two

- `log_resolver.resolve_main_repo_root` → `interactive_lock._resolve_main_repo_root`: **env-first**, else
  worktree-gitfile walk, else `_resolve_user_project_root()`.
- `common._resolve_user_project_root_from_cwd`: CWD only, ignores `CORTEX_REPO_ROOT`.
- `common._resolve_user_project_root`: env-first, else first `cortex/`-bearing ancestor.
- bare process CWD: `_current_branch`, `gh` calls, `git worktree list`.

### #484 did **not** pin "every appending verb" — CONFIRMED

It pinned every verb routed through `lifecycle_event.log_event`. Two writers call the low-level
`_append_event_atomic` directly and remain unpinned:

- `record_pr_opened.py:181` appends `pr_opened` to `lifecycle_dir/"events.log"` with `lifecycle_dir`
  from a CWD-anchored root (`:143`) — importing `_append_event_atomic`, not `log_event` (`:70`).
- `wontfix_cli.py:129` appends `feature_wontfix` to the **archived** log after `_archive_move`
  (`:194-196`), under `_resolve_user_project_root()` (env-first, `:172`).

### Sole caller, and the precedent

Only `skills/build/references/complete.md:8` (plus its plugin mirror) invokes the verb, as agent prose
during the live Complete phase, from whatever tree the session CWD is in.
`tests/test_complete_route.py:805-823` guards against other callers.

The per-artifact-anchor precedent already exists in this subsystem — `review_brief.py:706-713`:
"Two anchors, deliberately: artifacts follow the CWD because the reviewer writes review.md where the
work is … while events.log follows the pinned main-root resolver because that is the copy next/advance
read and append to (#484)."

### `pr.json` is runtime scratch — CONFIRMED

Not gitignored, but `stage_artifacts.py:349-401` never includes it in any phase's candidate set, so it is
never staged or committed. A worktree-local `pr.json` therefore does **not** survive `git worktree
remove` and has no merge path. Its only non-router consumer is `dashboard/data.py:2043`
(`parse_feature_pr_artifact`), called from `poller.py:356` with the dashboard's own root — never a
worktree, so a worktree-local `pr.json` is already invisible to the dashboard today.

### At-risk test

`tests/test_complete_route.py:753-796` `test_worktree_cwd_resolution_ignores_env` (spec Req 7) asserts the
verb reads the **worktree's** `events.log` and **ignores** a divergent `CORTEX_REPO_ROOT`. Any anchor
routed through `log_resolver` inverts both halves. `tests/test_complete_route.py:1059-1099`
(`test_branch2_nested_cortex_root_H_uses_show_prefix`) pins `root` as "the checkout whose HEAD you mean
to inspect". Baseline: `uv run pytest tests/test_complete_route.py -q` → **36 passed**.

## Tradeoffs & Alternatives

**A — re-anchor the `events.log` read only** (`:530` → `resolve_events_log(slug)`). One line. Fixes the
Branch-2 `feature_complete` miss. Does **not** fix the measured harm. Introduces an env dependence
(below).

**B — re-anchor `root` wholesale.** *Rejected.* `_head_has_feature_complete` does not read a file at
`root`; it asks which commit that working tree's HEAD points at. From the main root, HEAD is main's tip,
so Branch 2's `H` signal would permanently ask "does **main** already carry the committed
`feature_complete` row" — almost always No pre-merge — silently reclassifying `already_complete`/retryable
for exactly the worktree-driven population being fixed. `_finalization_committable` has the same problem
against the wrong index. Trades one silent-wrong-verdict bug for another.

**C — per-artifact: move `pr.json`'s read *and* write to the main root**, treating it as lifecycle state
rather than a work artifact. This is the only option that fixes the measured harm. `pr.json` reads as
state on the repo's own boundary (consumed by a routing decision, written once by a mechanical verb,
re-read by every later invocation) versus `review.md`, which `b61c3abc` explicitly keeps CWD-anchored
("the reviewer writes review.md where the work is"). Must move the `pr_opened` append (`:181`) with it or
it creates a new split inside one verb. Migration: orphaned worktree `pr.json` files are cheaply
regenerated by the existing Branch-3 `_reconstruct_pr_json`, so warn rather than migrate — matching
#484's stated warn-don't-heal precedent.

**D — a new refusal route via `detect_split_log`.** *Rejected.* `project.md:61`'s "`route` may not be
discriminated" is scoped to `common.py`'s resolvers and the nine-state closed table; `complete_route`'s
`route` is a separate 12-value enumeration emitting no `phase`, so the rule does not bind it by the
letter. But the cost it prices still applies — a 13th value needs a new arm in `complete.md`'s closed
if/elif — and refusing is not simpler than answering correctly once C exists.

**E — always run `_orphan_probe` before concluding `on_main`.** *Rejected as scoped* (see Adversarial);
viable only in a demotion-only form.

**A new `VerdictAnchors` resolver object.** *Rejected.* `log_resolver` already is the structural fix, as a
function; extending it to a second artifact is C, not a new abstraction. No third artifact is evidenced,
so Solution horizon's test ("the same patch would apply in multiple known places you can name") is not met.

## Adversarial

### Defect 1 as filed is largely dead — CONFIRMED by execution

The ticket's Why, and the orchestrator's initial reproduction, both drove `feature_wontfix` through the
generic `cortex-lifecycle-event log` escape hatch. The real producer is `wontfix_cli.py`, which:
(a) resolves via `_resolve_user_project_root()`, not the pinned resolver; (b) **refuses to run from a
worktree** without `CORTEX_REPO_ROOT` (`:176-182`); and (c) appends to `archive/{slug}/events.log`
*after* moving the directory (`:194-196`) — a path `classify()` never reads. Corpus: `feature_wontfix`
appears in **0** live `cortex/lifecycle/*/events.log` and **19** archived ones. Branch 1
(`complete_route.py:566`) is therefore dead for its real producer irrespective of anchoring.

**The Branch-2 arm survives and is the real events.log defect.** `finalize.py:185` resolves a CWD root and
reads `events_log = feature_dir/"events.log"` for both the idempotency scan (`_feature_complete_exists`,
`:195`) and `count_rework_cycles` — while `log_event` writes `feature_complete` to the **main-root** log.
So `feature_complete` lands main-root and a worktree-run `complete-route` misses it.

### Adjacent defect found: `finalize` is split inside itself — CONFIRMED

`finalize.py:56-58` states the counters, the idempotency scan, and `log_event`'s write target "all resolve
against the same physical tree". Post-#484 that is false. Consequences: from a worktree,
`_feature_complete_exists` reads an empty CWD log and **re-emits `feature_complete` on every re-run**
(idempotency broken), and `tasks_total`/`rework_cycles` are computed from a partial log. Not caused by
this ticket; worsened by the same commit.

### A substitutes an invisible env dependence for a visible CWD one — CONFIRMED by execution

`interactive_lock._resolve_main_repo_root:178-180` is `if env_root: return Path(env_root).resolve()` —
verbatim, **no existence check and no `cortex/` guard**. Under
`test_worktree_cwd_resolution_ignores_env`'s exact fixture, an Option-A-patched copy of the module routed
`already_complete → step12` (the skip-everything arm) where the test asserts `wontfix`. A nonexistent
`CORTEX_REPO_ROOT` is returned as-is, after which every read is empty and the route silently degrades.
Today's tree-dependence is observable and fixable by `cd`; an inherited env var is neither.

### `CORTEX_REPO_ROOT` means different things per launch path — CONFIRMED

- `pipeline/dispatch.py:700` pins it to the **worktree** (`_env["CORTEX_REPO_ROOT"] = str(worktree_path)`).
- `overnight/runner.py:1964,2902` pin it to the **project/repo root**.
- Interactive sessions: normally unset (no match in `hooks/cortex-scan-lifecycle.sh`).

So an env-honouring anchor resolves to the *worktree* under overnight dispatch — i.e. A is a no-op there
and changes behaviour only for interactive sessions.

### E is a net regression as scoped — CONFIRMED from the call path

Replacing the `on_main` short-circuit with `_orphan_probe` inherits all its exits (`:629-646`):

- **0 matches → `first_run` → step1**, which per `complete-first-run.md:28` runs `gh pr create` +
  `record-pr-opened`. Genuine direct-to-main work would be routed into **opening a PR**.
- **`gh` absent/unauthenticated/offline → `pr_unknown`**, blocking every offline direct-to-main completion
  that needs no network today.
- **Stale same-name branch** — the probe queries `--state all` (`:637`), so a *merged* PR from an earlier
  lifecycle reusing the slug is a single match → `_reconstruct_pr_json` writes `pr.json` → Branch 4 →
  possibly `merged_clean_ancestor` → Step 8 `cleanup_worktree`, **deleting a worktree and branch**.
- `orphan_ambiguous` becomes reachable on direct-to-main work, prompting an operator pick with no correct
  answer.

Viable only demotion-only: a probe result may downgrade `on_main` when a match is **OPEN** and its head
branch matches, and may never route to `first_run`/`pr_unknown` or reconstruct `pr.json`.

### The headline harm is real end-to-end — CONFIRMED

Nothing downstream of step9 re-checks PR state: `finalize.py` and `stage_artifacts.py` contain zero
references to `gh`, `pr.json`, or PR state. `on_main` also skips Step 8 entirely (`complete.md:16`). So
from the primary on main, an open-PR feature is marked complete, `feature_complete` is emitted, artifacts
are committed, and the worktree is orphaned — silently.

### Adjacent defect: the Step 8 escape hatch is a no-op — CONFIRMED in a real worktree

`complete.md:23`'s "else `cd $(git rev-parse --show-toplevel)`" does not leave a worktree — inside one,
`--show-toplevel` returns the *worktree* path. The operator loops, and whatever they do to escape lands
them in the primary on `main`, which is exactly the tree from which the measured defect mis-routes.

## Open Questions

1. **Should `complete-route`'s anchor honour `CORTEX_REPO_ROOT`?** *Unresolved — the central spec fork.*
   Req 7 mandates ignoring it; `log_resolver` honours it first and returns it unvalidated; and
   `dispatch.py:700` points it at a worktree. Reusing `resolve_events_log` as-is silently adopts all
   three behaviours. Options: reuse as-is; add a CWD-flavoured sibling to `log_resolver` that skips the
   env branch; or keep `_resolve_user_project_root_from_cwd` and re-anchor nothing. **Spec must decide.**
2. **Do `pr.json` and its `pr_opened` append move together?** *Resolved:* yes — splitting them creates a
   new intra-verb split (`record_pr_opened.py:161` vs `:181` share one `lifecycle_dir`).
3. **What about `_current_branch()`?** *Unresolved.* Even after C it reads the bare process CWD, so the
   `on_main` conjunction stays tree-dependent. Is "which branch am I on" legitimately a property of the
   invoking tree, or should it derive from the lifecycle (e.g. `pr.json`'s `head_branch`)? **Spec must
   decide**; it determines whether any form of E is still needed.
4. **Branch 1 is dead code for its real producer.** *Deferred* — a separate finding about
   `wontfix_cli`'s archive-then-append order, not an anchoring defect. File separately rather than
   widening this ticket; nothing here depends on the answer.
5. **`finalize.py`'s internal split and broken idempotency.** *Deferred* — same root cause (#484's
   partial pinning) but a different verb with its own blast radius. File separately; note that fixing
   `complete-route` alone leaves a worse-anchored writer behind the reader just moved.
6. **`complete.md:23`'s no-op `cd` escape.** *Deferred* — prose defect in the Step 8 guard, unrelated to
   anchoring. File separately.
