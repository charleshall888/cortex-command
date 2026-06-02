# Research: Surface built-but-merge-blocked overnight features as recoverable (#284)

> Topic: make the overnight runner surface a home-repo feature that BUILT correctly but is genuinely merge-blocked (real conflict, repair exhausted) as "built, merge-blocked, recoverable on `pipeline/<feature>`" — distinct from "never built" and from "awaiting a human answer". It must stop auto-retrying into recovery, not cascade-fail/strand siblings, and not count toward a `0/N` + `[ZERO PROGRESS]` PR. This is the reporting/state-surfacing Phase 2 of #281.

**Headline for Spec:** the load-bearing fork (reuse `deferred`+`recoverable_branch` metadata **vs** mint a new `merge_blocked` status) is **genuinely open** — #281 did *not* decide it (its spec reads `## Proposed ADR: None considered`; the #284 ticket's "ADR 0007" citation is a confirmed misattribution to an unrelated discovery ADR). Symmetric research initially leaned *mint*; the adversarial pass materially weakened that and surfaced a third option (a scoped MVP that defers the status-token decision). Two genuine design holes and a 7th unscoped work item (resume) were found. All are carried to Spec below.

---

## Codebase Analysis — Status Vocabulary & Conventions

**Overnight FEATURE status set** (`cortex_command/overnight/state.py`): `FEATURE_STATUSES = ("pending","running","merged","paused","failed","deferred")` (`:28-30`); `_TERMINAL_FEATURE_STATUSES = ("merged","failed","deferred")` (`:619`). `paused` is deliberately non-terminal — it **auto-retries every round** (the property #284 must avoid). Validation enforced in three places: `OvernightFeatureStatus.__post_init__` (`:106-110`), `update_feature_status` (`:585-589`), and the integer guards.

**Two distinct vocabularies — do not conflate:**
- **Overnight FEATURE statuses** (above) — what #284 actually touches.
- **BACKLOG-item statuses** — `common.py:TERMINAL_STATUSES` frozenset (`:162-171`), mirror `overnight/plan.py:_TERMINAL` (`:149-151`), `normalize_status`/`_STATUS_MAP` (`common.py:815`). `deferred` is in *neither*. **A new feature status touches NONE of these** — the ticket's claim that minting must update the backlog mirrors is FALSE (verified).
- Bridge: `outcome_router.py:_OVERNIGHT_TO_BACKLOG` (`:327-348`) maps feature→backlog (`merged→complete`, `paused→in_progress`, `failed→refined`, `deferred→backlog`).
- A *separate* PIPELINE feature vocabulary exists (`cortex_command/pipeline/state.py:31-33`, no `deferred`); `batch_plan.py`/`map_results.py` translate pipeline→overnight.

**Blast radius — every site that enumerates a feature-status string** (what a *mint* must update): `state.py:28-30/605/619`, `map_results.py:32`, `runner.py:357 (_count_pending)/1499 (_count_merged_home_repo)/1613-1618/2694`, `status.py:329-336`, `report.py:264/366-368/1074-1077`, `outcome_router.py:327-348`. ~13 sites, **none centralized behind a predicate** (no `is_terminal()`/`blocks_round()` helper).

**Existing `deferred` consumers** (what a *reuse* must add a discriminator to): set at `feature_executor.py:296/495/551/818`, `batch_plan.py:160-161`, `map_results.py:116`, `outcome_router.py:662/709/1013`. Consumed at `state.py:619/671/735`, `runner.py:357/2694`, `status.py:335`, `report.py:264/282-294/367/411/964-993`, `outcome_router.py:344-347/769/1155`, dashboard (`alerts.py`, `feature_cards.html`, `session_panel.html`).

**Convention — field vs status:** adding an optional metadata field (e.g. `recoverable_branch: Optional[str] = None` on the `OvernightFeatureStatus` dataclass, `state.py:91-103`) is the established cheap pattern — `save_state` (`asdict`, `:405`) and `load_state` (`**fs_dict` splat, `:336`) round-trip it with automatic backward-compat (absent key → default). Precedent: `recovery_attempts`, `recovery_depth`, `repo_path`, `intra_session_blocked_by`. Adding a *status* requires re-deriving `deferred`'s behavior at the ~13 scattered sites above.

**Existing sub-distinction precedent:** `batch_plan.py:160` / `outcome_router.py` already route `paused`→`deferred` by testing `"deferred" in error` — i.e. "discriminate a sub-case of a status by an extra signal" is already in the codebase (and is itself a known prose-coupling smell).

---

## Web Research

Prior art splits into two camps, and the split is the whole story.

**Status + reason/flag (the "reuse" shape) — used by the TWO closest analogs:**
- **Buildkite**: `blocked` is **not a state value** — it is a separate boolean field; the build `state` retains its last value (e.g. `passed`) and `blocked=true`. A separate `blocked_state` controls rendering. This is *exactly* the proposed `deferred`/built + `recoverable_branch` shape, shipped in production.
- **GitHub PRs**: a coarse `mergeable` boolean plus a reason-bearing `mergeStateStatus` enum (`DIRTY` = "merge commit cannot be cleanly created" = the genuine-conflict case, `BLOCKED`, `BEHIND`, `CLEAN`, …). GitHub did *not* mint top-level PR states per reason; it kept one axis + a reason enum.
- **GitLab merge trains** / **GitHub merge queue**: drop the MR/PR from the train/queue and record the reason in event metadata / timeline — not a dedicated status.

**Distinct state (the "mint" shape) — used by workflow orchestrators, but only when CONTROL FLOW differs:** Airflow (`up_for_retry` vs `upstream_failed` vs `deferred`=auto-resume-on-trigger vs `skipped`), Argo (`Failed` vs `Omitted` vs `Error`), Templal/Temporal closed states, Jenkins `FAILED` vs `UNSTABLE`. The consistent litmus: a distinct state is minted **iff downstream control flow differs**.

**FSM/domain-modeling guidance:** the State/Status Segregation pattern — "core phase that changes what can happen next → State; contextual detail/result → Status"; "make illegal states unrepresentable" (a flag-on-shared-status leaves illegal combos like `failed + recoverable_branch` representable; a distinct state forbids them by construction). Enums-over-booleans triggers only at 3+ mutually-exclusive flags.

**Naming (if minting):** `merge_blocked` or `integration_failed` read most clearly to humans; `dirty` (GitHub) is precise but jargon; `blocked` (Buildkite/GitLab) inherits "waiting-on-gate" ambiguity; **`deferred` collides with Airflow's "auto-resumes on trigger" meaning** — a caution against overloading it further.

**Deciding question the web frames:** not "is this conceptually different?" (it is) but "does the orchestrator and its consumers *act* differently?" The adversarial section below argues the honestly-distinct behaviors here are **reporting + write-back**, not control flow — which is the camp Buildkite/GitHub put in "reuse".

---

## Requirements & Constraints

**`pipeline.md:37-39` (the hardest semantic constraint), verbatim:** `deferred` means *"awaiting explicit human decision — deferred features do not auto-retry. Sources: ambiguous intent (exit report `action: "question"`), CI gate block, or non-APPROVED post-merge review verdict after rework exhaustion."* None of the three sources is "built-but-merge-blocked". Reusing `deferred` requires **explicitly widening this definition** (adding a fourth source) — a documentation cost, not a control-flow cost.

**`pipeline.md:42` cascade, verbatim:** *"When a feature reaches terminal `failed`, an end-of-round sweep transitions every not-yet-terminal feature whose `intra_session_blocked_by` lists it to `failed`… A `paused` blocker does not cascade; only terminal `failed` triggers it."* Code-confirmed `state.py:622-688`. So dependents of a merge-blocked (`deferred`-or-new) blocker get **no cascade path out of `pending`** → `_count_pending` stays > 0 → `circuit_breaker (stall)`. **Required in both paths.**

**`pipeline.md:88-95` Deferral System:** the deferral artifact is question-shaped (`lifecycle/deferred/{feature}-q{NNN}.md`). A merge-blocked feature has no question → confirms it renders nowhere / mislabels in the `deferred` consumers.

**`pipeline.md:26` ZERO PROGRESS:** the `[ZERO PROGRESS]` draft gate must keep blocking accidental merge of a genuinely-empty integration branch while no longer labeling a session with built-but-merge-blocked work as zero-progress.

**`project.md:36` status-vocabulary discipline:** governs the BACKLOG terminal vocabulary (update `common.py:TERMINAL_STATUSES` + `plan.py:_TERMINAL` + `normalize_status` together). Applies *literally* only if #284 adds a terminal backlog status; applies *by analogy* (definition set + terminal mirror) if a feature status is minted. **`project.md:35`**: new events register in `bin/.events-registry.md`. **`project.md:44`**: any `grep -c` acceptance token must resolve to a real literal under `cortex_command/` or the registry (so acceptance criteria can't assert against a not-yet-existing `recoverable_branch`/status literal — the literal must land first).

**`project.md:19-21` Complexity / Solution Horizon:** "Complexity must earn its place… simpler wins"; the durable-version test fires when "the patch applies in multiple known places you can name" — which #284's own enumerated multi-consumer fan-out satisfies, so raising the durable-vs-simple question is in-scope (not premature prediction). "A scoped phase of a multi-phase lifecycle is not a stop-gap."

**ADR three-criteria gate (`adr/README.md:21-27`):** the reuse-vs-mint decision plausibly clears all three (hard-to-reverse multi-call-site + data-field; surprising-without-context; real trade-off with a named credible alternative). An ADR is plausibly warranted. **No existing ADR governs status vocabulary**; the real `0007-decompose-groups-pieces-into-tickets` is unrelated.

**#281→#284 boundary (`overnight-merge-recovery-strands-a-successfully/spec.md`):** `:7/:24/:29/:52-54` explicitly split ALL surfacing (the `deferred`+`recoverable_branch` state, recoverable rendering, dashboard, ZERO-PROGRESS suppression, write-back change, sibling cascade) to #284, state "Does **not** introduce a new feature status" *for #281's own scope only*, and record `## Proposed ADR: None considered` with a comment that the decision "moves with the surfacing work to #284." **The fork is open; #284 owns it.**

---

## Tradeoffs & Alternatives — reuse `deferred`+metadata (A) vs mint a status (B)

**The expensive work is SHARED and unavoidable in both:** a new recoverable render path, a non-rebuild write-back, and the sibling-cascade fix are required either way (#281's own adversarial findings #4–#7 prove A still needs all of it). So the decision turns on the *marginal* cost of the token choice plus correctness/honesty.

**A (reuse) — marginal cost:** add a `recoverable_branch`-presence discriminator at ~9 `deferred` consumers (`report.py:264/282-294/367/411/964-993`, `dashboard/alerts.py:81-86`, `app.py:77/90`, `feature_cards.html:123`, `session_panel.html`, `outcome_router.py:344-347`), plus `update_feature_status` + `_write_back_to_backlog` signature threading. Failure mode of a missed site: a **silent mislabel** ("answer the question" for a feature with no question). Pro: `deferred` already supplies the exact *behavioral* shape (terminal, no auto-retry, no `failed`-cascade). Con: a permanent semantic override on a status documented as "human answer required".

**B (mint) — marginal cost:** ~7 mechanical enum/map edits (`FEATURE_STATUSES`, `_TERMINAL_FEATURE_STATUSES`, `update_feature_status` `completed_at` tuple, `map_results._TERMINAL_STATUSES`, `status.py` bucket, `_OVERNIGHT_TO_BACKLOG`, dashboard badge/icon). The ticket's claim that B must touch the backlog mirrors is FALSE (verified). Pro: self-describing; write-back correct-by-construction; "illegal states unrepresentable". Con: ~13 scattered tuple sites, none centralized → durable move would first add `is_terminal()`/`blocks_round()` helpers (larger than scoped).

**Initial recommendation: B, medium confidence** — on the grounds that costs are near-even once the shared work is removed, and the tiebreakers (self-describing, "loud crash" on a missed site, correct-by-construction write-back) favored B. **This recommendation is materially weakened by the adversarial pass below** (the "loud crash" tiebreaker is false; the closest prior art favors A). Treat the fork as still contested going into Spec.

**"It depends on X":** the unmeasured real-world frequency of genuine home merge-blocks after #281 lands. If ≈0, the cheaper-to-ship option wins; if recurring, the durable/honest model earns its footprint.

---

## State-machine & Sibling-cascade Integration

**Stop-auto-retry mechanics:** `paused` auto-retries via `_count_pending` (`runner.py:357`, counts `pending/running/paused`) and the orchestrator `features_to_run` (`orchestrator-round.md:127/139-146`, "paused always included"). `deferred` is excluded from both → does not re-dispatch. **So a merge-blocked feature must land `deferred`-shaped (reuse) or a new terminal status (mint) — never `paused`.**

**Routing point to change:** recovery-exhausted merge failure currently routes to **`paused`** at `outcome_router.py:1116-1140` (and the plain-merge-fail fallthrough `:666-694`). These are the exact sites #284 re-points. (`paused`→re-auto-retry-forever→stall is the observed #281 symptom class.)

**Cascade gap:** `sweep_blocker_failed_dependents` (`state.py:619/662-685`) fires ONLY on terminal `failed`; dependents of a merge-blocked blocker stay `pending` forever → stall. Sibling-exit options (no forced winner):
- **A. New sweep variant `sweep_blocker_blocked_dependents`** — defers (not fails) the subtree; mirrors the existing tested pattern; keeps `failed`-cascade untouched. *Leading*, BUT see the open hole below (the deferred dependents have no recoverable branch → mislabel). Two sweeps → ordering matters (failed-sweep first is correct).
- **B. Extend the existing sweep** — overloads its deliberately-narrow "cascade only on `failed`" contract; high regression risk on the parity tests.
- **C. Re-point the prose dependency gate** (`orchestrator-round.md:189-194`) — prose-only, fragile, violates the repo's "structural over prose" gate principle.
- **D. `_count_pending` ignores merge-blocked-blocked dependents** — cheapest, but leaves dependents persisted as `pending` (misleading report/resume).

**Reuse-vs-mint divergence here:** reuse gets "stop auto-retry" *free* (deferred already excluded) but the sweep trigger needs a **metadata sub-test** (real question-deferrals also use `deferred` and must NOT cascade siblings); mint gets a clean status test for the sweep but must teach `_count_pending`/`_count_merged`/`status.py` the new status or it silently drops out.

---

## Surfacing & Reporting Integration

`recoverable_branch` does not exist anywhere today. All claims confirmed:
- `render_failed_features` filters `status in ("failed","paused")` (`report.py:1074-1077`) — excludes `deferred`. It already prints `- **Recovery branch**: pipeline/{name}` (`:1146`) but **double-gated** behind `conflict is not None` (a `merge_conflict_classified` event) AND failed/paused status — never reached by the merge-blocked case, and the bare `pipeline/{name}` drops the `-2/-N` suffix.
- `render_deferred_questions` (`:964-1011`) is **file-driven** (`data.deferrals`) — a `deferred` feature with no question file renders NOWHERE.
- `render_executive_summary` (`:366-368/411`) counts `deferred` as "(questions need answers)" → mislabel.
- `create_followup_backlog_items` (`:264/282-294`) writes a `deferred` feature a NEW backlog file with `status: backlog` + a wrong "unanswered questions, see deferred/{name}-q*.md" body — **a second rebuild-from-scratch bug independent of `_OVERNIGHT_TO_BACKLOG`.**

**Fix shape:** a new `render_built_merge_blocked` section + a distinct exec-summary counter; the load-bearing operator artifact is the recovery branch name `pipeline/<feature>`.

**ZERO PROGRESS — two gates, the summary's single-gate patch is insufficient:**
- **Outer** `commit_count == 0` (`runner.py:1695`, `_integration_commit_count` = `git rev-list main..overnight/<session>`) fires FIRST and **skips PR creation entirely**. A merge-blocked feature's commits live on `pipeline/<feature>`, never on the integration branch — so a session whose *only* outcome is merge-blocked produces **NO PR at all**, not even a draft. Operator's only surface is the morning report unless this outer gate also learns about merge-blocked.
- **Inner** `mc_merged_count == 0` (`:1717`) stamps `[ZERO PROGRESS]` — add `and not _count_built_merge_blocked_home_repo(state)`.
- **Stall breaker** (`:2711`, `merged_delta <= 0`) trips on a build-but-no-merge round — redefine "progress" to include built-but-merge-blocked transitions at both the `merged_before`(`:2329`)/`merged_after`(`:2636`) sites.

**Non-regression:** the question-deferral surface is disjoint from the recoverable surface **only if** every consumer checks `recoverable_branch` presence FIRST and falls through to the question path when None — BUT this 2-way split mis-handles the never-built transitively-blocked dependent (see Adversarial + Open Questions).

---

## Data-threading, Provenance & Events

**`recoverable_branch` provenance:** the suffix-correct branch (`pipeline/<name>` or collision-renamed `-2/-N`, from `pipeline/worktree.py:_resolve_branch_name:98-116`) enters runtime only as `info.branch` from `create_worktree()` → `orchestrator.py:336-342` `worktree_branches[name]` → `OutcomeContext.worktree_branches` (`outcome_router.py:73/832`). It is **persisted nowhere on the feature record today** (orchestrator-runtime-only, rebuilt every batch). The only durable record is the **`merge_start` event** `branch` field (`pipeline/merge.py:205`, in the *pipeline* events log). The bare `pipeline/<name>` reconstruction (`report.py:1146`, and `or f"pipeline/{name}"` fallbacks throughout `outcome_router.py`) is the bug.

**Threading:** add `recoverable_branch: Optional[str] = None` to `OvernightFeatureStatus` (`state.py:67-103`) and a keyword-only param to `update_feature_status` (`:554-561`) with in-place assign. Atomicity preserved automatically (`save_state` = `asdict` + tempfile + `os.replace`, `:388-431`); backward-compat via the dataclass default. **`recoverable_branch` is needed in BOTH reuse and mint** — it is orthogonal to the status token.

**Write-back:** `_OVERNIGHT_TO_BACKLOG["deferred"] = {"status":"backlog"}` (`outcome_router.py:344-347`) is the latent rebuild-from-scratch bug. `_write_back_to_backlog` (`:388-394`) receives only the status string; the merge-blocked sub-case must select a non-`backlog` target (record "recover on branch X" in the backlog frontmatter). Two shapes: a discriminator param, or a new overnight-status key with its own `_OVERNIGHT_TO_BACKLOG` row.

**Events:** a NEW event is NOT required. The branch is already in `merge_start.branch`; the recoverable state is best carried by the persisted field + (optionally) a **field-additive `recoverable_branch` extension on the existing `feature_deferred` event** (the registry documents this mechanism and tolerates extra fields). If a new event IS minted: `EVENT_TYPES` in `events.py` (hard-enforced at runtime by `log_event` ValueError) + a 10-column registry row + note that `cortex-check-events-registry` only scans `skills/**/*.md` + `overnight/prompts/*.md` (Python-only emit sites are not gate-blocked).

---

## Adversarial Review

**1. The "loud crash" tiebreaker for *mint* is FALSE (HIGH).** `dashboard/templates/session_panel.html:17-23` is an `{% if/elif %}` chain over `feat.status` with **no `{% else %}`** → a minted status renders nowhere, silently. `dashboard/data.py` count helpers (`:759-761/833-835/962-965`) tally only named statuses, silently ignoring unknowns. The dataclass field is a permissive string (no enum), so persistence won't crash either. Mint's central advantage over reuse is significantly overstated.

**2. `batch_plan.py:157-168` maps an unknown status to `running` → REBUILD (HIGH).** A minted `merge_blocked` returned by the pipeline is re-classified `running` ("didn't finish") and re-dispatched. The reuse path must ensure the merge-blocked error string contains `"deferred"` to hit `:160` or it maps to `paused`. Unflagged by any agent; a status-inference site both paths must handle.

**3. TWO independent rebuild bugs in the reuse path (HIGH).** Beyond `_OVERNIGHT_TO_BACKLOG["deferred"]→backlog`, `create_followup_backlog_items` (`report.py:282-317`) *also* writes a `status: backlog` follow-up with a wrong body — doubling the "non-rebuild write-back" work the Tradeoffs agent treated as one shared cost.

**4. OPEN HOLE — dependents of a merge-blocked blocker (HIGH, unclosed).** They never built → have **no recoverable branch**. Under sibling-exit Option A they become `deferred` with `recoverable_branch=None`, so the "check `recoverable_branch` first" invariant routes them to the **question-deferral path** — but they have no question file → they render NOWHERE and are counted as "questions need answers" (a lie). The 2-way discriminator collapses a *third* state (transitively-blocked, never-built) into the question bucket. Needs a 3-way discriminator (built+branch / question+file / blocked+neither) OR sweep these dependents to a `failed`/`blocked` terminal instead of `deferred`. **Sibling-cascade Option A is not safe to ship without this third surface.**

**5. Steelman of A — the mint recommendation is theory-biased against the closest prior art.** The "does the orchestrator ACT differently?" test is the wrong axis: no-auto-retry is a `_count_pending` membership predicate (satisfied by `deferred` already), branch-preservation is a data field, and the cascade/report/write-back/ZERO-PROGRESS/resume work is shared. The genuinely-distinct behaviors are **reporting + write-back routing**, not control flow — exactly the case Buildkite/GitHub resolved with status+flag. Mint's marginal cost (≥13 tuple sites + the silent-drop sites in #1/#2) exceeds reuse's (~9 discriminator checks that at least stay visible). Net: the evidence tilts back toward **A (reuse)** on marginal-cost + closest-prior-art grounds; A's real liability (overloading `deferred`'s documented semantics) is a definition-widening cost, cheaper than the predicate-refactor mint needs to be safe.

**6. Resume is BROKEN in BOTH paths today (HIGH, 7th unscoped work item).** `determine_resume_point` (`state.py:713-745`) treats ONLY `merged` as completed; a merge-blocked feature (`deferred` or minted) lands in `pending_features` → re-dispatch candidate on resume. Task idempotency (`feature_executor.py:637-648`) prevents code re-write but NOT worktree re-creation / re-merge churn. Fixing resume = teaching `determine_resume_point` (+ the orchestrator prompt) to treat merge-blocked as completed-for-resume. Neither ticket scopes this.

**7. `recoverable_branch` provenance is NOT robust (HIGH).** `ctx.worktree_branches` is rebuilt every batch; if the worktree *path* was cleaned/TMPDIR-purged but the branch survives, `create_worktree`→`_resolve_branch_name` mints a FRESH empty `-2` branch, so `worktree_branches[name]` points at the WRONG (empty) branch. Sourcing `recoverable_branch` from live `worktree_branches` at merge-block time can silently strand the real work. Mitigation: source from `merge_start.branch` (the branch actually being merged), assert non-empty/has-commits, never fall back to bare `pipeline/<name>`.

**8. MVP scope challenge.** Frequency is unmeasured; the path fires only after #281 lands and only on a genuine repair-exhausted home conflict (the #281 incident never exhibited one). The sibling-cascade work — the most complex piece and the home of the open hole in #4 — is **unreachable without a multi-feature dependency chain whose head also genuinely merge-conflicts** (third-order rare). MVP that captures the bulk of value, correct-by-construction: **(i)** fix the `deferred→backlog` write-back (+ the wrong-body follow-up) so built work is not rebuilt, and **(ii)** surface the recovery branch (one report line + the persisted field). Defer the new status, the sibling cascade, and the dashboard work until a real occurrence is observed. (Recording the deferral satisfies the solution-horizon clause.)

**9. Confirmed:** the "#281 chose reuse / ADR 0007" premise is false; the recovery-exhausted→`paused` routing (`outcome_router.py:1116-1140`) is the only current outcome and is wrong for both paths (shared, correctly identified).

---

## Open Questions

- **The load-bearing fork is genuinely contested — resolve in Spec's interview + the §4 complexity/value gate.** Reuse `deferred`+`recoverable_branch` (A) vs mint `merge_blocked` (B) vs a scoped MVP that defers the token decision. Symmetric evidence: initial Tradeoffs leaned B (medium); the adversarial pass falsified B's "loud crash" tiebreaker (B has silent-drop sites: `session_panel.html` else-less elif, `data.py` counters, `batch_plan.py` unknown→`running`→rebuild) and showed the two closest prior-art systems (Buildkite/GitHub) chose A; net the evidence now tilts toward **A** on marginal-cost + prior-art grounds, with B's edge being semantic honesty. Not pre-decided here.
- **The transitively-blocked-dependent hole is unhandled (design decision for Spec).** Dependents of a merge-blocked blocker never built (no recoverable branch) and the 2-way `recoverable_branch` discriminator mislabels them as question-deferrals where they render nowhere. Choose: a 3-way discriminator (built+branch / question+file / blocked+neither) vs sweeping these dependents to a distinct `failed`/`blocked` terminal. Sibling-cascade Option A cannot ship without this.
- **Is fixing resume in scope (a 7th work item)?** `determine_resume_point` treats only `merged` as completed, so a merge-blocked feature re-enters the pending set on a resumed session (both paths) and churns worktree-recreation/re-merge. In scope for #284, or a separate follow-up?
- **`recoverable_branch` authoritative source.** Source from `merge_start.branch` (assert non-empty/has-commits) vs live `ctx.worktree_branches[name]` (can point at an empty `-N` branch after worktree cleanup). Resolve before writing the field.
- **ZERO PROGRESS outer gate.** The `commit_count == 0` gate skips PR creation entirely for a merge-blocked-only session (no PR at all; morning-report-only surface). Is report-only acceptable, or must the outer gate also learn about merge-blocked so the operator gets a PR-level signal?
- **ADR.** The reuse-vs-mint decision plausibly clears the three-criteria gate. Should #284 record an ADR (and correct the ticket's ADR-0007 misattribution / pick the next free ADR number)?
- **Scope/value (drives the §4 gate).** Given unmeasured frequency, the #281 dependency, and the third-order-rare sibling-cascade path that harbors the open hole above, should #284 ship the MVP (rebuild-bug fix + branch surface) and defer the status token + sibling cascade + dashboard + resume — or build the full design now?
