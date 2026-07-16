# Plan: durable-observed-merge-closer-stranded-work

## Overview

Repair five verified defects in morning-review's post-merge path. Three structural constraints shape the decomposition, each learned from a defect in the prior draft:

1. **Activation and correction are one task.** Adding `--state` makes the merged/closed branches live; those branches currently carry a false advisory and a close directive. A `Depends on` edge only *orders* tasks — it does not guarantee both land, and both executors commit per-task (`implement.md`'s failure menu offers `skip`/`abort`). Splitting them would be prose-only enforcement of a sequential gate, which CLAUDE.md forbids.
2. **A new console script and its prose reference are one task.** `parity_check.gather_deployed()` = `bin/` execs ∪ `[project.scripts]` keys, so the entry point is "deployed" the instant pyproject lands; only a markdown mention discharges W003, and `determine_exit` returns 1 on warnings without `--lenient` (the justfile passes none). Splitting the verb from its walkthrough reference creates a backwards edge no dependency graph can express.
3. **Every `skills/`-touching task runs alone in its batch.** Pre-commit Phase 4's drift check is unconditional over `plugins/*` (`git diff --quiet -- "plugins/$p/"`, working tree vs index across the whole subtree). While `just build-plugin`'s `rsync -a --delete` output sits unstaged, *every co-scheduled sibling's commit is rejected*. Disjoint `Files` cannot reach a tree-wide write, so the skills tasks carry explicit edges that place them alone.

The push verb performs and verifies its **own** push: `cortex-git-sync-rebase` returns at `behind == 0` before its push, and its exit 0 also means "nothing to rebase". Phase 4 therefore does not depend on Phase 1.

**Resulting batches** (`compute_dependency_batches`): 0={1,5,7} (disjoint files, none touch `skills/`) · 1={2,6} · 2={3} · 3={4} · 4={8} alone · 5={9} alone · 6={10} alone.

## Outline

### Phase 1: Sync-path repair (tasks: 1, 2, 3, 4)
**Goal**: make `cortex-git-sync-rebase` do what it documents — live allowlist, no silent false success, conflict path covered.
**Checkpoint**: `tests/test_git_sync_rebase.py` exercises both conflict arms and a failing behind-count; `just test` green.

### Phase 2: Closer id-resolution hardening (tasks: 5, 6)
**Goal**: the overnight write-back never silently resolves the wrong backlog item.
**Checkpoint**: `grep -c "candidates\[0\]" cortex_command/overnight/outcome_router.py` = 0; ambiguity returns `None`.

### Phase 3: Merged-exit reachability (tasks: 7, 8)
**Goal**: the merged/closed exits execute for the first time and say something true when they do.
**Checkpoint**: the `gh pr list --head` invocation carries `--state`; the merged-exit span holds no close directive and names a multi-match branch; mirror in parity.

### Phase 4: Durable close (tasks: 9, 10)
**Goal**: §6b's closures reach `main` — including their cascade writes — or the review says plainly that they did not.
**Checkpoint**: the verb commits and pushes a real closure in a `behind == 0` fixture; a redundant re-close pushes nothing; a rejected push reports `pushed: false` naming the tickets.

## Tasks

### Task 1: Repair `sync-allowlist.conf` patterns and add a coverage test that fails on a dead pattern
- **Files**: `cortex_command/overnight/sync-allowlist.conf`, `tests/test_git_sync_rebase.py`
- **What**: Every pattern omits the `cortex/` umbrella prefix and matches nothing (verified 0/5), so §6a's auto-resolution never fires and it aborts on the first conflict of any kind. Re-prefix each pattern; add a test that fails if any pattern matches no representative path.
- **Depends on**: none
- **Complexity**: simple
- **Context**: One pattern per line, `#` comments ignored. Current set: `lifecycle/sessions/*/`, `lifecycle/*/research.md`, `lifecycle/*/spec.md`, `lifecycle/*/plan.md`, `lifecycle/*/agent-activity.jsonl`, `lifecycle/pipeline-events.log`, `backlog/index.md`, `backlog/archive/*`, `backlog/[0-9]*-*.md`. Consumer `cortex_command/git/sync_rebase.py::_matches_allowlist` (~L79–94) `fnmatch`es against git's **repo-relative** conflict paths (`cortex/backlog/...`); patterns ending `/` use prefix matching. Loader `_load_allowlist` (~L55–75) strips blanks/comments. Representative paths: `cortex/backlog/346-x.md`, `cortex/backlog/index.md`, `cortex/lifecycle/pipeline-events.log`, `cortex/lifecycle/foo/plan.md`, `cortex/lifecycle/sessions/s1/`. Umbrella relocation was `c8110de5` (2026-05-12); the conf was last touched `00cf8864` (2026-05-05). Assert **per-pattern**, not aggregate, so one live pattern cannot mask eight dead ones.
- **Verification**: `python3 -m pytest tests/test_git_sync_rebase.py -q` exits 0; deleting the `cortex/` prefix from any single conf pattern makes the new test fail.
- **Status**: [ ] pending

### Task 2: Cover `sync_rebase`'s conflict-resolution path
- **Files**: `tests/test_git_sync_rebase.py`
- **What**: The conflict/allowlist loop has zero coverage (only noop and clean-rebase exist), which is how Task 1's defect survived two months. Add both arms.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Existing `test_git_sync_rebase_noop_when_up_to_date` (~L65) and `test_git_sync_rebase_clean_rebase_succeeds` (~L125) show the fixture idiom: `git init --bare` origin plus a clone (so `receive.denyCurrentBranch` is a non-issue). Conflict loop at `sync_rebase.py` ~L230–265: allowlist hits resolve `--theirs`, the rest collect into `non_allowlist`, abort at L260 with `return 1`. Module header exit contract: `0` success, `1` conflict, `2` push failed. Arm (i): conflict on a path matching a repaired pattern (e.g. `cortex/backlog/index.md`). Arm (ii): a non-allowlist path (e.g. `README.md`). Depends on [1] because arm (i) only auto-resolves once patterns match, and both edit the same test file.
- **Verification**: `python3 -m pytest tests/test_git_sync_rebase.py -q` exits 0 with both new tests passing; arm (ii) asserts `git status --porcelain` shows no `rebase-merge`/`rebase-apply` left behind.
- **Status**: [ ] pending

### Task 3: Stop `_behind_count` reporting "up to date" on git failure
- **Files**: `cortex_command/git/sync_rebase.py`, `tests/test_git_sync_rebase.py`
- **What**: `_behind_count` returns `0` on any non-zero rc and on `ValueError`, so a missing `origin/main`, shallow clone, auth failure, or network loss renders as "Already up to date" → exit 0 → a silent false success that pushes nothing while reporting success.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: `_behind_count` ~L128–141 runs `git rev-list HEAD..origin/main --count`; both failure returns collapse into the legitimate zero consumed at ~L187–190 (`if behind == 0: return 0`). Exit codes `1` (conflict) and `2` (push failed) are taken per the module header — introduce a new one (e.g. `3`) and document it there alongside the others. Do **not** change the legitimate `behind == 0 → return 0` behavior; only the error path. Depends on [2] to serialize same-file edits to the test module.
- **Verification**: `python3 -m pytest tests/test_git_sync_rebase.py -q` exits 0; a test stubbing a failing `git rev-list` asserts exit ∉ {0, 1, 2} with a diagnostic naming the behind-count step; a second asserts a genuine `behind == 0` still exits 0.
- **Status**: [ ] pending

### Task 4: Resolve the unreachable `_MAX_NON_ALLOWLIST` branch
- **Files**: `cortex_command/git/sync_rebase.py`, `tests/test_git_sync_rebase.py`
- **What**: `if len(non_allowlist) > _MAX_NON_ALLOWLIST` (~L250) can never fire — `if non_allowlist:` (~L260) catches ≥1 first and both return 1. Remove the dead branch and its constant, or give it a distinguishable behavior.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: Both branches `_log`, list unresolved files, `_git(["rebase", "--abort"])`, and `return 1` — the only difference is log text. Default to removal. Depends on [3] to serialize same-file edits.
- **Verification**: `grep -c "_MAX_NON_ALLOWLIST" cortex_command/git/sync_rebase.py` = 0, OR a test asserts a >3-conflict run produces an exit code or structured output distinguishable from a 1-conflict run. `python3 -m pytest tests/test_git_sync_rebase.py -q` exits 0.
- **Status**: [ ] pending

### Task 5: Remove the blind first-match from `_find_backlog_item_path`
- **Files**: `cortex_command/overnight/outcome_router.py`, `cortex_command/overnight/tests/test_outcome_router.py`
- **What**: Step 2 globs `{padded}-*.md` and returns `candidates[0]` with no ambiguity check, unlike the canonical resolver beside it which surfaces `ambiguous` rather than guessing. Delete step 2; route through the canonical resolver, threading `backlog_id` into the step-3 call.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `_find_backlog_item_path` ~L402–436: step 1 matches by slug; step 2 (~L424–429) is the blind glob; step 3 (~L434) calls `_backlog_find_item(feature, backlog_dir=backlog_dir)` — passing only `feature`, **not** `backlog_id`, so the id has no canonical route today. `_backlog_find_item` is `update_item._find_item` → `resolve_item.resolve()` (order: uuid-prefix → numeric → kebab → lifecycle_slug → title; returns ambiguous on ≥2 matches at any step). Caller `_write_back_to_backlog` (~L439–503) wraps everything in a swallow-all `try/except` emitting `BACKLOG_WRITE_FAILED`, so a `None` return degrades to a logged no-write, not a crash. Existing `TestFindBacklogItemPathLifecycleSlug` (~L964–1033) covers the slug fallback; nothing covers step 2. Files are disjoint from batch-0 siblings (Tasks 1, 7) and none touch `skills/`.
- **Verification**: `grep -c "candidates\[0\]" cortex_command/overnight/outcome_router.py` = 0; `python3 -m pytest cortex_command/overnight/tests/test_outcome_router.py -q` exits 0, with a new test asserting two files sharing a numeric prefix resolve to `None` and a second asserting a unique numeric id still resolves.
- **Status**: [ ] pending

### Task 6: Thread the ticket `uuid` through to close time
- **Files**: `cortex_command/overnight/state.py`, `cortex_command/overnight/plan.py`, `cortex_command/overnight/outcome_router.py`, `cortex_command/overnight/orchestrator.py`, `cortex_command/overnight/tests/test_outcome_router.py`
- **What**: Task 5 fixes ambiguity but not renumbering — `resolve()`'s numeric step matches on filename only, so only the uuid path is renumber-proof. Carry the uuid to the write-back and prefer it when present.
- **Depends on**: [5]
- **Complexity**: complex
- **Context**: `BacklogItem.uuid` exists (`overnight/backlog.py` ~L97, populated ~L334 via `uuid=fm.get("uuid") or None`). `plan.py` ~L422–429 builds `OvernightFeatureStatus` copying `backlog_id` and discarding `item.uuid`. `OvernightFeatureStatus` (`state.py` ~L66–109) has no uuid field. `orchestrator.py` ~L262/L280 reads `backlog_ids[name] = fs.backlog_id` into `OutcomeContext.backlog_ids`, feeding every `_write_back_to_backlog(..., backlog_id=...)` call site. Resolution-side needs **zero** changes — `resolve()` step 1 already accepts a uuid prefix (≥8 hex after hyphen-strip). 25 of 374 items lack a uuid, so the numeric path stays as fallback. `Should`-priority: renumbering occurred once (`94eddf11`, fixed by #231); zero duplicate prefixes today.
- **Verification**: `python3 -m pytest cortex_command/overnight/tests/test_outcome_router.py -q` exits 0, with a test where a captured `backlog_id` points at a different item than the uuid identifies, asserting the write-back resolves the uuid's item or returns `None` — never the numerically-matched wrong item; a second asserts a uuid-less item still resolves numerically.
- **Status**: [ ] pending

### Task 7: Correct #346's false premise in the ticket body
- **Files**: `cortex/backlog/346-durable-observed-merge-closer-stranded-work-reconciliation-for-morning-review.md`
- **What**: The Why asserts the post-merge sync is skipped and the local checkout is stale. Step 5 rebases before §6 and has since `428e54ea`. The claim has already re-seeded the wrong design twice; leaving it misleads the next reader.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Rewrite `## Why` to name the two real defects: the merged/closed PR exits are unreachable because the PR query omits an explicit state filter, and the post-merge closer's ticket writes are never committed or pushed. Keep `## Role`/`## Integration`/`## Edges`/`## Touch points` coherent with the narrowed scope — the deferred pieces (auto-close, orphan reconciler, re-pick suppression) leave this lifecycle, so do not leave the body promising them. **LEX-1 constraint (load-bearing)**: `bin/cortex-check-prescriptive-prose` scans `Why`/`Role`/`Integration`/`Edges` and flags `SECTION_INDEX_RE = (?:§|\bR)\d+(?:[a-z]\)?|\([a-z]\))?\b`, a `path:line` form, and multi-line fences. Confirmed empirically: a `## Why` containing `§6b` and `walkthrough.md:291` yields two violations. So write **"the post-merge closer"**, not `§6b`; **"the walkthrough's PR query"**, not `walkthrough.md:291`. The file currently scans clean — do not introduce the first violation. Body edits are plain file edits; do not hand-edit frontmatter (use `cortex-update-item` if a field needs changing). Files are disjoint from batch-0 siblings (Tasks 1, 5) and this task does not touch `skills/`.
- **Verification**: `bin/cortex-check-prescriptive-prose cortex/backlog/346-durable-observed-merge-closer-stranded-work-reconciliation-for-morning-review.md` reports 0 violations (NOT `just validate-commit`, which is the commit-message hook tester and exits 0 regardless of file contents); over the same file `grep -cE "sync step is skipped|checkout is stale|no durable remote signal"` = 0 AND `grep -cE "\-\-state"` ≥ 1 AND `grep -cE "push"` ≥ 1.
- **Status**: [ ] pending

### Task 8: Make the merged/closed exits reachable, honest, and report-only — in one commit
- **Files**: `skills/morning-review/references/walkthrough.md`, `plugins/cortex-overnight/skills/morning-review/references/walkthrough.md`, `tests/test_morning_review_status_close_ordering.py`
- **What**: Add an explicit `--state` to the PR query **and** rewrite the branches it activates, together. The query omits `--state`; `gh` defaults to `open`, so the `MERGED` (L295) and `CLOSED` (L300) branches are dead and a merged PR wrongly reports "No PR found… Use `/pr` to create it manually." Widening alone is unsafe: the activated arm is terminal (`Stop.`), asserts a staleness the rebase disproves, and directs closing this session's tickets — which would fire on a *prior* session's PR under head-name reuse and invert §6's own invariant ("Until a merge is confirmed, completed features' backlog tickets stay open — the work sits on the integration branch, not main"). One task, one commit; there is no coherent state where the activation has landed and the correction has not.
- **Depends on**: [4, 6, 7]
- **Complexity**: complex
- **Context**: Query at L291; merged exit L295–299; closed exit L300. Empirically: the exact command returns `[]` for a known-merged head branch; `--state all` returns `[{"number":25,"state":"MERGED"}]`. `gh pr list --help`: `-s, --state string  Filter by state: {open|closed|merged|all} (default "open")`. **Head-name reuse is real**: `plan.py:391` builds `overnight/{session_id}` from `strftime("overnight-%Y-%m-%d-%H%M")` (L359, minute granularity); the uniquifying loop (L363–370) tests only `os.path.exists(session_dir(session_id))` — a **gitignored** directory — and L391–407 force-deletes and reuses a colliding local branch while the prior session's merged PR persists on GitHub. So >1 match is a real case: surface the candidates, never first-match. The merged exit reports the out-of-band merge and stops; it closes nothing and asserts nothing about whether *this session's* work landed (auto-close needs `merge-base --is-ancestor` plus disambiguation — both deferred). Delete the L296–299 advisory: its staleness claim is false (Step 5 fetched and rebased before §6) and its "close it via the closer, then push" directive is a closure instruction the lexical ordering guard cannot see (it anchors on `CLOSE_LITERAL = "cortex-morning-review-close-tickets"` and `CLOSE_PATTERN = update[-_]item.*--status complete`, neither of which matches prose). **Mirror**: `plugins/cortex-overnight/...` is an **rsync output**, not a source file — do not hand-edit it; run `just build-plugin` (justfile ~L594, `rsync -a --delete`) and stage the regenerated file in the same commit. **Depends on [4, 6, 7] to run alone in its batch**: pre-commit Phase 4's drift check is unconditional over `plugins/*`, so any co-scheduled sibling's commit would be rejected while this task's build-plugin output is unstaged.
- **Verification**: `grep -cE 'gh pr list --head[^`]*--state' skills/morning-review/references/walkthrough.md` ≥ 1; over the §6 step-2 span: `grep -cE "update[-_]item|close-tickets|close it via"` = 0 AND `grep -cE "more than one|multiple PRs|>1"` ≥ 1 AND `grep -cE "first match|\[0\]"` = 0 AND `grep -c "This skips"` = 0; `python3 -m pytest tests/test_morning_review_status_close_ordering.py tests/test_dual_source_reference_parity.py -q` exits 0.
- **Status**: [ ] pending

### Task 9: Report every path a close wrote, so the pushable set is knowable
- **Files**: `cortex_command/overnight/close_tickets.py`, `cortex_command/backlog/update_item.py`, `cortex_command/overnight/tests/test_close_tickets.py`
- **What**: Task 10's verb cannot stage "the closed backlog files" without being told which they are, and a wholesale `cortex/backlog/*.md` glob would sweep concurrent edits to `main`. Worse, a close writes **more** than its own item: `_check_and_close_parent` rewrites the parent epic, and `_remove_uuid_from_blocked_by` rewrites every item whose `blocked-by` referenced the closed uuid — real state, not churn. `close_tickets._close_one` reports only `parent_closed: True`, a bare boolean with no path. Extend the close path to report every file it wrote.
- **Depends on**: [8]
- **Complexity**: complex
- **Context**: `update_item()` (`update_item.py` ~L338–428) writes the item via `atomic_write` (~L385), then under the terminal-status branch (~L411) calls `_remove_uuid_from_blocked_by` (~L193–235) and `_check_and_close_parent` (~L249–331), then regenerates the index (~L417–421). Have `update_item` return (or otherwise expose) the set of paths it wrote; have `close_tickets._close_one` surface them per item as `changed_paths`. `cortex/backlog/index.md` and `index.json` are **gitignored** (`cortex/.gitignore:43-44`) — exclude them from the reported set. Also report whether the status actually changed: `update_item` appends `status_changed` only when `new != old` (~L392), but bumps `updated:` unconditionally (~L382, `# Always update the 'updated' field`) — Task 10 needs that distinction because the overnight **success** path already sets `status: complete` (`_OVERNIGHT_TO_BACKLOG` maps `"merged"` → `{"status": "complete"}`), making §6b's close a redundant re-close in the common case. Preserve the always-exit-0 JSON-struct contract and `KNOWN_STATES`. Depends on [8] to stay out of a batch with a `skills/`-touching task.
- **Verification**: `python3 -m pytest cortex_command/overnight/tests/test_close_tickets.py -q` exits 0, with a test asserting that closing a child whose parent epic then closes reports **both** paths in `changed_paths`, a second asserting a `blocked-by` dependent's path is reported, a third asserting no gitignored index path appears, and a fourth asserting a re-close of an already-complete ticket reports the status as unchanged.
- **Status**: [ ] pending

### Task 10: Build the commit+push verb, register it, and wire it into the walkthrough — in one commit
- **Files**: `cortex_command/overnight/push_closures.py`, `pyproject.toml`, `tests/test_push_closures.py`, `skills/morning-review/references/walkthrough.md`, `plugins/cortex-overnight/skills/morning-review/references/walkthrough.md`
- **What**: §6b writes ticket closures and the review ends; `close_tickets.py` has zero git calls, so a close repairing a failed overnight write-back never reaches `main`. Add a verb that stages exactly the paths Task 9 reports, commits, pushes, and verifies the push by observation — plus the walkthrough hook that invokes it. Verb and prose reference must land together (see Context).
- **Depends on**: [9]
- **Complexity**: complex
- **Context**: **Why one task**: `parity_check.gather_deployed()` = `bin/` execs ∪ `[project.scripts]` keys, so a new console-script key is "deployed" the moment `pyproject.toml` is staged; W003 then demands an in-scope wiring signal, and `collect_wiring_signals` accepts a **markdown inline-code mention** but *not* a Python `subprocess.run([...])` reference. `determine_exit` returns 1 on warnings without `--lenient`, which the justfile recipe does not pass. So the verb cannot commit until its walkthrough mention exists. **Push mechanism**: do **not** delegate to `cortex-git-sync-rebase` — it returns at `if behind == 0: return 0` (~L187–190) over 100 lines before its `git push` (~L292–294), and this scenario *is* `behind == 0`; its exit 0 is documented as "rebase + push completed, **or** nothing to rebase". **`pushed` derivation needs two observations**: `git rev-list origin/main..HEAD --count` = 0 is *not* evidence of a push — it reads 0 both when the push landed and when nothing was ever committed. Capture HEAD before and after the commit; `pushed: true` requires both that a commit was created (pre ≠ post) and that the ahead-count is 0 after the push. No `git fetch` is needed — `git push` updates the remote-tracking ref itself. **Skip pure churn**: the common case is a redundant re-close producing an `updated:`-only diff (the overnight success path already set `status: complete`); use Task 9's status-changed signal to skip the commit entirely rather than pushing timestamp noise to `main` every review. **Shape**: argparse CLI, pure library function returning a JSON-able dict, always exit 0 with errors as `state`/`message` (`close_tickets.py` is the model; register in `pyproject.toml` alongside the existing `cortex-morning-review-*` verbs, ~L85–92 — no `bin/` wrapper is needed, matching `cortex-morning-review-close-tickets`). Pin the flag surface explicitly and use it verbatim in the walkthrough: Phase 1.55 runs `just check-contract --staged`, which AST-extracts the argparse surface and emits E101/E102 against skill-prose invocations. Git subprocess idiom is list-form, never shell strings. Non-fast-forward rejection is the expected push failure — report it, never force. Hook goes after §6b's close loop (§6a, L341–357, is the shape precedent: one verb call plus a compact outcome map); §6b is already after the first `gh pr merge` literal (L313), so the ordering guard is satisfied — re-run it. Regenerate the mirror with `just build-plugin` and stage it in the same commit; do **not** hand-edit the rsync output. Depends on [9] for the `changed_paths`/status-changed contract, and to run alone in its batch (Phase 4's drift check would reject any co-scheduled sibling's commit).
- **Verification**: `python3 -m pytest tests/test_push_closures.py -q` exits 0, including (a) a fixture repo (bare origin + clone) with the remote unmoved (`behind == 0`) where a real status change is committed and pushed, leaving `git rev-list origin/main..HEAD --count` = 0 — this test fails if the push is delegated to `sync_rebase`; (b) a no-op run where nothing was committed asserts `pushed: false` (proving the ahead-count alone is not the derivation); (c) a redundant re-close (`updated:`-only, status unchanged) creates no commit and reports no push; (d) a rejected non-fast-forward push reports `pushed: false` naming the un-pushed ticket ids. Also `python3 -m pytest tests/test_morning_review_status_close_ordering.py tests/test_dual_source_reference_parity.py -q` exits 0 and `just check-parity` exits 0 (W003 discharged by the walkthrough mention).
- **Status**: [ ] pending

## Risks

- **Task 8 activates never-executed code, and it is the highest-risk task here.** The merged/closed branches have never run in production; Task 8 both activates and rewrites them in one commit, so there is no window where the activation ships without the correction. But the first real merged-exit encounter after this lands is still the first time that path has ever executed. It is report-only and terminal-in-the-same-way as today, which bounds the blast radius.
- **`--state all` vs `--state merged`.** `all` also revives the CLOSED branch (useful) but widens the multi-match surface to every historical PR on a reused head name. Task 8's multi-match rule is what makes this safe; if it proves noisy, narrowing to `--state merged` plus a separate closed check is the fallback.
- **Task 9 changes a shared primitive.** `update_item` is called by the overnight write-back, the lifecycle verbs, and the closer. Extending its return surface must not alter its write behavior — the tests around it are the guard.
- **Tasks 6 and 3 are `Should`-adjacent.** If Phase 1/2 run long, Task 5 alone delivers the real resolver protection and Task 3 the real fail-open fix; Tasks 4 and 6 are cleanup and defense-in-depth.
- **Deferred pieces are not filed yet.** Auto-close, the orphan reconciler, and re-pick suppression exit this lifecycle as Non-Requirements with their defects recorded. They need tickets authored from the corrected research, or the analysis decays.
- **The prose-lean constraint is reviewer-enforced, not gated.** `tests/test_skill_size_budget.py` reads only `*/SKILL.md` and `tests/test_l1_surface_ratchet.py` measures only frontmatter bytes — neither can see `references/walkthrough.md` growth. Tasks 8 and 10 rely on review.
- **Batch-0 co-scheduling is safe only as declared.** Tasks 1, 5, and 7 share one worktree and one `.git/index`; their Files are disjoint and none touches `skills/`. Adding a `skills/`-touching task to batch 0 later would reintroduce the Phase-4 drift rejection this decomposition was restructured to avoid.

## Acceptance

A morning review whose PR was merged out-of-band reports that merge instead of "No PR found — use `/pr` to create it manually", surfaces candidates rather than first-matching when the head name resolves to several PRs, and closes nothing on it. On the normal path, a ticket genuinely closed by §6b to repair a failed overnight write-back is committed with its cascade writes and pushed — verified by an observed commit plus `git rev-list origin/main..HEAD --count` = 0 — or reported `pushed: false` naming the un-pushed tickets; a redundant re-close pushes nothing. `just test` is green, including new coverage for the sync conflict path, the behind-count failure, resolver ambiguity, the reported changed-path set, and the push verb.
