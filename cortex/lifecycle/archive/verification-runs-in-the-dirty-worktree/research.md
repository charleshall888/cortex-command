# Research: Give task_git_state a consumer, so an untracked file at implement exit produces an observable consequence rather than a log line nobody reads

**Bottom line: the proposal does not survive its own evidence.** Both candidate consumers are
provably unreachable in the source incident, and 100% of the noise they would have to filter is
produced by four lines of dead code that should be deleted regardless. The recommendation is to
delete `cortex_command/pipeline/worktree.py:324-327` and close #467 unbuilt. Detail below.

## Codebase

### Producer and current consumers

`cortex_command/overnight/feature_executor.py:726-754` writes `task_git_state` per task, with
`cwd=worktree_path`. `git_status` is **not** truncated (unlike `task_output`'s `[:2000]` at `:706`).
Error sentinel is `git_status="(error)"` / `new_commit_count=-1` (`:744-746`) — any consumer must
handle it. The only consumer repo-wide is `cortex_command/overnight/smoke_test.py:213-219`, which
prints it.

### Placement candidates

| Candidate | Sees the event? | Interactive? | Verdict |
|---|---|---|---|
| No-commit guard, `outcome_router.py:856-879` | yes | no | **Reject** — gated on `if not changed_files:` (`:857`); the incident feature produced 5+ commits, so it is structurally unreachable. The guard is not at `batch_runner.py:1279` as the ticket assumed; `batch_runner.py` is now a 49-line CLI shim, and ticket 002 already replaced the message, which no longer mentions `task_git_state`. |
| Pre-merge, `completed` arm — `outcome_router.py:853` (sync), `:2007` (async) | yes | no | Only point where blocking is still cheap — **but see Adversarial §1** |
| Morning report merged block, `report.py:772` `_render_feature_block` | yes (`data.pipeline_events_path` in scope at `:791`) | no | Report-only — **but see Adversarial §1** |
| Morning report failed block, `report.py:1490-1578` | yes | no | Fires only for *failed* features |
| Implement exit, `feature_executor.py:754` | is the producer | no | No merge authority, no operator surface |
| Post-merge | yes | no | Too late by construction |
| "Batch checkpoint" | — | — | **Does not exist.** Only `approval_checkpoint_responded` in `discovery.py:354+`, unrelated. |

**The interactive path is untouched.** `execute_feature` (`feature_executor.py:392`) has exactly one
non-test caller, `orchestrator.py:399`, so `task_git_state` is never written interactively and
`report.py` never runs. The interactive analog exists only as skill prose:
`skills/build/references/complete.md:27` gates worktree *cleanup* on
`git status --porcelain --ignored=traditional` being empty — it does not block completion.

**Router asymmetry.** The two routers differ downstream: sync (`:856-879`) inlines the pause with
`_classify_no_commit` and `no_commit_guard: True`; async (`:2011-2014`) does not, falling through to
`_apply_feature_result`. A consumer "in both routers" inherits two idioms, not one.

### The `.venv` contradiction — resolved and independently reproduced

`cortex_command/pipeline/worktree.py:324-327` symlinks `.venv` into every non-cross-repo worktree.
`.gitignore:10` is `.venv/` — **trailing slash matches directories only**, and git does not follow
symlinks for pathspec matching, so the symlink is reported untracked. Reproduced in a scratch repo:

- real directory → `git status --short` empty, `git check-ignore -q .venv` rc **0**
- symlink → `git status --short` = `?? .venv`, `git check-ignore -q .venv` rc **1**

The absent trailing slash in `?? .venv` is itself the tell: `git status --short` collapses untracked
*directories* with a trailing `/`. Not `core.excludesFile`, not `.git/info/exclude`, not
sparse-checkout, not a nested checkout.

### Arming `test_command` does not subsume a reader

`runner.py:3259`'s `test_command=None` is **vestigial**: `git log -S 'test_command=None,'` returns
one commit, `c2a09f62` ("Add overnight runner.py pure-Python round-dispatch loop"), with no comment
at the call site and no rationale in the body. The surrounding plumbing is fully built and fully
dead — `runner.py:1955` sends `"none"`, `batch_runner.py:32-33` converts it back to `None`, and
`pipeline/parser.py:280-281` can parse `test_command` from the master plan but `orchestrator.py:252-253`
reads only `master_plan.features`, never `master_plan.config`.

Arming it would **not** have caught the source incident, and would not catch a non-manual instance of
the same shape. `merge.py:340` runs `run_tests(test_command, cwd=str(repo))` in the integration
checkout against committed content only, so a catch depends on the configured command *referencing*
the missing file. In wild-light, `7f8e2d9c` — the commit that first put `run_python_tests.py` into
`test-command` — is **inside** the merge `db94189c`. A `test_command` armed at session start would
have carried the pre-#479 value (`validate_project.py && run_unit_tests.py`), which never touches the
missing script, so the post-merge run would have passed. It is systematically blind to a feature's
own new deliverable, which is the most common shape of this defect.

### Patterns to copy, if anything is built

Idiom — scan `pipeline-events.log` as JSONL, keep the last event matching `event`/`feature`, fail
open on `OSError`/`JSONDecodeError`, return a rendered string:
`report.py:2305-2338` `_read_last_task_output` (canonical minimal shape);
`report.py:2358+` `_read_last_task_diagnostics` (closest analog — added later as a deliberate sibling
reading extra fields off an existing event without touching the original reader, design rule stated
in its docstring at `:2362-2380`); `report.py:2410+` `_aggregate_feature_cost` (already called from
both the merged block at `:791` and the failed block at `:1504`, proving reachability).

**Caveat: the reader idiom is untested.** `grep -rn "_read_last_task_output\|_read_last_task_diagnostics\|task_output" tests/`
returns nothing. The pattern worth copying is the producer/consumer coupling test in
`tests/test_no_commit_classification.py`, and `tests/test_complete_cleanup_gates.py:79-142` for the
real-temp-git-repo shape (reusable `_git`/`_init_repo` helpers at `:41-66`).

## Requirements & Constraints

- **`project.md:41`** — "a pre-commit/CI gate survives only by naming the specific, evidenced failure
  it prevents… **A new gate enters only with its named failure stated here.**" A blocking consumer
  requires an edit to this clause.
- **`project.md:23`** (Deletion bias) — discharge requires "a consumer that turns a build or gate red
  when the surface is removed — **not a report-only or manually-invoked script**". A report-only
  consumer therefore does **not** discharge `task_git_state`'s own presumption of removal.
- **`project.md:21`** — "anything that exists to police or observe the harness itself is presumed
  deletable unless it names specific evidence."
- **`pipeline.md:42`** — fail-forward: "One feature's failure does not block other features in the
  same round." In direct tension with a blocking pre-merge gate.
- **`pipeline.md:149`** — `pipeline-events.log` is named as an **audit trail**, not a decision
  surface. Untracked files, `git status`, and `task_git_state` are **not addressed anywhere** in
  `pipeline.md` (zero grep hits).
- **`pipeline.md:90-102`** (Post-Merge Test Failure Recovery) is triggered *after* merge and is
  upstream-blind to an implement-exit event; it constrains this work only if a consumer routes into
  post-merge repair, in which case `:98`'s 2-attempt cap and `:155`'s "fixed architectural
  constraint" bind.
- **`glossary.md`** — nothing bearing. Not addressed.
- **Lifecycle gating**: none of the touch points (`feature_executor.py`, `smoke_test.py`, `runner.py`,
  `pipeline/merge.py`, `lifecycle_config.py`, `pipeline/worktree.py`) appear in `CLAUDE.md:28`'s
  gated list.

### `_LIVE_PROSE_KEYS` is not ratified and forbids nothing here

No ADR and no requirements clause records it — zero grep hits for `test-command`, `LIVE_PROSE`, or
`live-in-prose` across `cortex/adr/` and `cortex/requirements/`. The "activation must be loud and
deliberate" guard at `lifecycle_config.py:38-42` is scoped **explicitly and only** to `_DORMANT_KEYS`
(`:46-48` = `{skip-specify, skip-review, default-tier, default-criticality}`); `test-command` is not a
member. The `_LIVE_PROSE_KEYS` comment (`:36-37`) is descriptive, not prohibitive. Origin is
`cortex/research/cli-served-lifecycle-state-machine/research.md:52` (row A4), landed by #372.
**Parsing `test-command` in Python violates no recorded decision** — the only obligation is
documentation truth (`docs/overnight-operations.md:728`: do not enumerate scaffolded fields in more
than one doc).

### Consumer-repo surface

Wheel-only: `plugins/` contains no overnight Python. **No sibling repo pins a cortex-command
version** (zero hits across all four repos' manifests), so a wheel change reaches every consumer at
once — the premise `lifecycle.md:105`'s wheel-first/prose-first asymmetry rests on, here confirmed
empirically. Config state: wild-light **sets** `test-command`; gaggimate-barista and Team-Builder-Bot
have it commented out; hall-dental has no `lifecycle.config.md` at all.

### Incidence data

| repo | `task_git_state` events | events with ≥1 `??` | distinct `??` paths |
|---|---|---|---|
| wild-light (1 session) | 28 | 28 | 6 — `.venv` ×28, `run_python_tests.py` ×5, ADR ×1, `test_worldgen_digest.py` ×1, `captures/` ×1, `line-ledger.md` ×1 |
| cortex-command | 34 | 34 | 2 — `.venv` ×34, `refine.py` ×1 |
| gaggimate-barista | 0 | — | no data |
| Team-Builder-Bot | 0 | — | no data |
| hall-dental | 0 | — | no data |

wild-light's `cortex/.gitignore:31` ignores `lifecycle/sessions/`, so all of this is untracked
local-only data; 2 of its 3 overnight session dirs hold no `pipeline-events.log` at all.

## Adversarial

### 1. Both proposed consumers were unreachable in the source incident

Final dispositions in `overnight-2026-08-07-0252` — verified directly against
`overnight-events.log`:

- `no-gate-anywhere-runs-pytest-so` → **`feature_failed`** @ 07:15:46 (`$TMPDIR` worktree gone)
- `a-generator-version-bump-has-an` → **`feature_failed`** @ 07:15:46, same exception
- `probe-game-stategd-is-1195-lines` → **`feature_deferred`** @ 07:48:24

Zero features reached `result.status == "completed"`; zero `feature_merged`; `merge_start: 2` with
`merge_complete: 0` and `merge_failed: 0`. Both insertion points sit inside the `completed` arm
(`:850` `elif result.status == "completed":`, `:1996` `if result.status != "completed": … return`),
and `_render_feature_block` is reached only for merged features. **The proposal's only observed
incident is structurally invisible to both proposed consumers.** The defect reached `main` through a
human `git merge`, and no proposed consumer sits on that path.

### 2. The noise source is dead code — a strictly cheaper competing ticket

`worktree.py:324`'s comment reads "Symlink .venv so runner.sh's venv check succeeds in worktrees."
**`runner.sh` does not exist**: deleted in `3cbf00ed` ("Retire runner.sh and bin/overnight-{start,status}
shims"). Those four lines are now the only `venv` reference in `cortex_command/overnight/` or
`cortex_command/pipeline/`, and no test references `.venv` or `symlink_to`.

They produce **100% of all observed noise in both corpora** (28/28 and 34/34). Deleting them clears
Deletion bias on its own terms — `project.md:23`: "A surface with no consumer that fails on its
removal carries the presumption of removal" — at a cost of 4 lines, versus a gate that must first buy
an amendment to `project.md:41`. The `.gitignore` half of "fix at source" is *not* available to
cortex-command: with no consumer pinning a version, a fix requiring every consumer to edit its own
`.gitignore` is unenforceable. Only the `worktree.py` deletion (or a per-worktree `.git/info/exclude`
write, which cortex-command controls) fixes it for all consumers.

### 3. The persistence discriminator does no separating work

`.venv` persists to the last event in **6 of 6** features across both corpora, so persistence does not
separate it from signal — the hardcoded drop-list is still required, and once it exists, persistence
separates exactly one observation from four. The full non-`.venv` population is **n=6**:

| path | pattern | committed? |
|---|---|---|
| `scripts/tools/run_python_tests.py` | persists to last | `9cde2d0f` — after the fact; the incident |
| `cortex/adr/0080-…md` | vanishes | `64d32acc` |
| `tests/python/test_worldgen_digest.py` | vanishes | `304b6a9d` |
| `cortex/lifecycle/…/captures/` | vanishes | `dd214a24` |
| `cortex/lifecycle/…/line-ledger.md` | vanishes | `df90d7bb` |

0 false negatives, 0 false positives — but 1/1 true positives, fitted to and validated on the single
observation it was designed around. Five of six data points are the negative class.

### 4. The discriminator reads a race as a signal

`task_git_state` is written per-task inside `asyncio.gather` (`feature_executor.py:749`, inside
`_run_task`). Therefore: events arrive in **completion order, not task order** (for
`a-generator-version-bump-has-an`: 6, 12, 8, 7, 9, 1, 3, 10, 4, 2, 5, 11, 13), so "the last
`task_git_state`" is whichever task finished last; `git status` covers the **whole shared worktree**,
not the emitting task's changes, so `test_worldgen_digest.py` appears in task 10's snapshot and is
absent from task 4's because a *different* concurrent task committed it in between; and a
single-task batch has no vanish opportunity at all.

### 5. `_defer_unresolved_worktree` is not an honest route

Reading `outcome_router.py:690-736`: `error = "integration worktree unresolved"` is **hardcoded** at
`:713`; event details are hardcoded `{"unresolved_worktree": True, "conflict": False}` at `:726-730`;
the docstring states no `recoverable_branch` is recorded, and "its absence is what keeps
`_count_built_merge_blocked_home_repo` from counting the feature as progress"; backlog write-back is
`"paused"` → `in_progress` (`:732`), deliberately not `"deferred"`. Every choice is reasoned from
"TMPDIR purged, work is stranded, do not rebuild" — none describe "the builder forgot a `git add`."
Reuse means lying in the event stream; forking re-opens 20 lines of settled disposition design.

### 6. Blast radius runs the wrong way

In cortex-command's own corpus **6/6 features would hit a `??` line** at the gate; every one is
`.venv`. If the drop-list is ever wrong, stale, or repo-divergent, the gate converts a 100%-merge
session into a 100%-blocked one. In wild-light, `a-generator-version-bump-has-an` (13 tasks, 13
commits, legitimate) would have hit the gate if either `captures/` or `test_worldgen_digest.py` had
happened to be the last sample — 2 of its 13 snapshots carried a non-`.venv` path, and *which*
decides the outcome is asyncio scheduling. The asymmetry is backwards: a false positive parks a full
feature's work as non-progress; a true positive saves 49 minutes of review latency.

### 7. Also noted

`_get_changed_files` (`:420-438`) is `git diff --name-only base...branch` — committed content only.
So a report-only annotation competes against simply noting that `key_files_changed` and the worktree
disagree, with no new event consumer at all.

## Open Questions

- **Does `task_git_state` itself survive Deletion bias?** — *Answered, and it is the real question.*
  `project.md:23` gives a surface with no failing consumer the presumption of removal, and
  `project.md:21` presumes harness-observing machinery deletable absent specific evidence. After the
  `worktree.py` deletion, `task_git_state`'s only consumer is a smoke-test print. The honest framing
  is whether the **writer** survives, not what reads it. This is a distinct decision from #467 and
  should be filed separately rather than settled here.
- **Would a per-worktree `.git/info/exclude` write be preferable to deleting the symlink?** —
  *Deferred.* It only matters if some consumer still needs `.venv` present in the worktree; no such
  consumer was found (`runner.sh` is retired and no test references it), so the question is moot
  unless the deletion surfaces one. Re-open only on an observed failure after the deletion lands.
- **Should `test_command` be armed through `runner.py:3259` regardless?** — *Deferred, on its own
  merits.* It is fully-built dead code with a revert path already wired, and parsing `test-command`
  violates no recorded decision (no ADR, and the `_DORMANT_KEYS` guard does not cover it). But it
  does not address this ticket — it is blind to a feature's own new deliverable — and arming it would
  immediately begin parsing wild-light's live value with no version pin to hold it back. Separate
  ticket, separate evidence.
- **Do the other three sibling repos exhibit this at all?** — *Answered: unknown and unmeasurable
  today.* gaggimate-barista, Team-Builder-Bot, and hall-dental have zero `pipeline-events.log` files,
  so no incidence data exists or can be derived. The corpus is one session in one sibling repo. Per
  `measure-consumer-features-across-sibling-repos`, cortex-command alone is the least representative
  denominator, so no generalisation is supportable on this evidence.
- **Was the sync/async router asymmetry accounted for in the placement recommendation?** —
  *Answered: no.* The core wave described only the sync router's inlined pause; the async twin
  (`:2011-2014`) falls through to `_apply_feature_result`. Moot if nothing is built, but it would be a
  correctness trap for any future consumer placed "in both routers."
