# Research: Harden lifecycle complete-phase finalization and rework_cycles counter

Four latent defects surfaced during feature #291's trunk completion, in the `/cortex-core:lifecycle` Complete-phase finalization tail (`skills/lifecycle/references/complete.md` Steps 10–11a) and the `rework_cycles` counter. This research maps each defect's true fix surface, weighs candidate approaches, and — via an adversarial pass over the 189-feature lifecycle corpus — corrects several first-pass conclusions. Read alongside `cortex/backlog/296-*.md`.

**Headline corrections from the adversarial pass (supersede earlier angle conclusions where they conflict):**
1. Defect 4's correct counter source is the **events.log `review_verdict` stream (count `CHANGES_REQUESTED`)**, *not* a regex over `review.md` text. The buggy counter mis-reports ~78/84 reviewed features, not just first-pass approvals.
2. There are **five** `rework_cycles`/cycle computation sites, not three — `common.py` (cycle-number, leave) and `walkthrough.md:280-283` (crash-recovery, *also buggy*) were missed.
3. The defect-2/3 fix should **enumerate the logical change-set**, not blanket `git add -u`.
4. `bin/cortex-lifecycle-counters` is a dual-channel wrapper (no second regex implementation) — defect-4 fixture churn is smaller than feared, but the `multiple-phases` fixture needs a real rewrite (its `REWORK` verdict never occurs in the corpus).

---

## Codebase Analysis

### Defect 1 — Dead index-sync first fallback (complete.md Step 10)
- **Defect site = edit target:** `skills/lifecycle/references/complete.md:214` — `python3 cortex_command/backlog/generate_index.py`. The full fallback chain is lines 213–216 (fallback 1 = bare python3 script-path; fallback 2 = `cortex-generate-backlog-index` console script; fallback 3 = warning).
- **Why dead:** `cortex_command/backlog/generate_index.py:20-22` does `from cortex_command.backlog import _telemetry` / `from cortex_command.common import …`. Running by script-path puts the *file's* dir on `sys.path[0]`, not the repo root → `ModuleNotFoundError`. The `if __name__=="__main__"` block (lines 336-337) never reaches `main()`.
- **The script is correct; the caller is wrong.** generate_index.py is a read-only reference for this defect.
- **Repo idiom (verified):** every other package-module invocation in `skills/` and `bin/` uses `python3 -m cortex_command.<module>` or the console script — `complete.md:214` is the *only* bare `python3 <path>.py` invocation across all of `skills/`. `cortex_command/backlog/update_item.py:411-414` already regenerates this exact index via `subprocess.run([sys.executable, "-m", "cortex_command.backlog.generate_index"])`. The console script exists: `pyproject.toml:28` → `cortex-generate-backlog-index = "cortex_command.backlog.generate_index:main"`.
- **Lint gap:** L201 (`cortex_command/lint/bare_python_import.py`) catches `import cortex_command` statements in skill python-source regions, NOT a `python3 path.py` shell invocation in inline-backtick prose. Defect 1 is genuinely uncaught.

### Defect 2 — Drift-drop on the trunk completion path (complete.md Step 11a)
- **Producer of the dropped edit:** `skills/lifecycle/references/review.md:191` (§4a "Apply the update") reads a tracked requirements file, appends, writes — **never commits**. Target named only in review.md's `## Suggested Requirements Update → File:` field (review.md:79-87); default `cortex/requirements/project.md`.
- **Why dropped:** complete.md:21 on-`main` short-circuit **skips Steps 2–5** (no source commit). Step 11a (lines 243-262) stages only enumerated `cortex/lifecycle/{slug}/` artifacts + `git add cortex/backlog/`. Neither covers `cortex/requirements/`. **Trunk-only** — PR paths commit the edit via Step 2 before the PR.
- **No event records the applied path.** Only `review_verdict` (with `requirements_drift: detected`) and the failure-path `drift_protocol_breach` exist. The authoritative record of *which file* is the review.md `File:` field.

### Defect 3 — Backlog dir-add sweeps unrelated untracked tickets (complete.md Step 11a)
- **Defect site = edit target:** `complete.md:256-260`. Line 256 documents the deliberate rationale: capture the resolved item, `index.json`/`index.md`, and "any sibling/parent `.md` files rewritten by `cortex-update-item`'s terminal-status cascade."
- **Cascade file set (`cortex_command/backlog/update_item.py`, verified):** resolved item `.md` (`atomic_write` line 378, in-place edit of a pre-existing file); sibling `blocked-by` `.md` rewrites (`_remove_uuid_from_blocked_by` lines 186-239, globs existing files, `atomic_write` line 239); parent epic `.md` auto-close (`_check_and_close_parent` lines 242-324, line 323). **The cascade only ever modifies already-tracked files in place — it never creates a new file** (adversarially re-verified: no `open(…, "w")` on a new path).
- **`index.json`/`index.md` are GITIGNORED** (`git check-ignore` confirms; `cortex/.gitignore`). complete.md:256's claim the dir-add "captures the regenerated index.json/index.md" is **misleading** — they are never staged.
- **update_item reports nothing usable:** returns `None`; prints only `Updated: {resolved item}` (line 595) and a conditional parent-closed line (408). The silent sibling rewrites mean Complete cannot learn the cascade set from update_item stdout today.

### Defect 4 — rework_cycles over-count + multiple divergent computations
Five verdict/cycle-derived integers exist (adversarial expansion):
1. **`cortex_command/lifecycle/counters.py:52-63` `count_rework_cycles`** = `len(RE_VERDICT.findall(review.md))`, `RE_VERDICT = r'"verdict"\s*:\s*"[A-Z_]+"'` (line 33). **THE BUGGY PRODUCER.** Counts all verdict blocks (incl. APPROVED and stray `[A-Z_]+` noise). Written into the *interactive* `feature_complete` event via complete.md Step 11 (line 228 runs `cortex-lifecycle-counters`).
2. **`cortex_command/dashboard/data.py:342-347` `parse_feature_events`** = counts `review→implement(-rework)` phase-transition loop-backs. **Correct semantics** (0 for first-pass) for the 84/84 features that emit `phase_transition` events; returns 0 for the ~13 legacy features lacking those events even when review.md shows real rework. Feeds `alerts.py`.
3. **`cortex_command/pipeline/metrics.py:236`** reads `final_complete.get("rework_cycles")` **verbatim** from the event (no recomputation) → inherits counters.py's bug for interactive features. Aggregated into `avg_rework_cycles` (lines 1034-1036, 1056) and the morning-report calibration line (1098-1101); read by `hooks/scan_lifecycle.py:506,508`.
4. **`cortex_command/common.py:257,296`** `_detect_lifecycle_phase_inner` computes `review_verdict_count` and `cycle = count if >0 else 1`. A **cycle NUMBER**, not a rework count — currently correct for its purpose; document so it isn't "fixed" to match rework semantics.
5. **`skills/morning-review/references/walkthrough.md:280-283`** (crash-recovery) writes `rework_cycles: C` where C = last `review_verdict` cycle number → **ALSO BUGGY** (first-pass APPROVED at cycle 1 writes 1, true 0). The synthetic skip-review path (walkthrough.md:260-262, `cycle: 0` → `rework_cycles: 0`) is consistent and fine.

**The overnight `feature_complete` (`review_dispatch.py:287`) OMITS `rework_cycles`** → metrics reads `None` there. So the stored-value contamination is **interactive-lifecycle-only** — a small, bounded backward-compat surface.

---

## Web Research

- **Python module invocation:** `python3 path/to/pkg/module.py` sets `__package__=None` and puts the *script dir* (not package root) on `sys.path`, breaking `from pkg.x import y`. Canonical fixes, in order: (1) installed **console-script entry point** — CWD-independent, identical across editable/non-editable installs; (2) **`python3 -m pkg.sub.module`** — sets `__package__` correctly, works for installed pkgs and source trees when the root is importable; (3) `PYTHONPATH`/`sys.path` hacks — brittle anti-pattern. "Always use `python -m`, never `python file.py`." (Python Packaging User Guide — Entry points; setuptools entry_point docs.)
- **Git staging scoped to a known set:** `git add -u <pathspec>` stages tracked modifications/deletions only (no new files) — safe against untracked sweep. Best practice for "stage exactly this change-set": `-u` for tracked + explicit pathspec adds for known-new files, or `git add --pathspec-from-file=-` fed from a computed set; `:(exclude)` magic when interlopers are predictable. Bare `git add <dir>/` (the defect-3 anti-pattern) sweeps all untracked. (git-add docs; CSS-Tricks pathspec guide.)
- **Rework vs review-cycle metric convention:** "Review cycles" = back-and-forth loops; **first-pass approval is conventionally ZERO iterations**. Gerrit tags amended patch-sets `kind: REWORK` and the *first* patch-set is not rework → **rework = patch-sets − 1**, 0 on first-pass. DORA's "rework rate" is a *different* production-bug concept — don't conflate. Verdict: computing rework as "count of verdicts" is the classic fencepost error; first-pass must be 0. (software.com Engineering Metrics; Gerrit Patch Sets concept + REST API.)
- **One metric, two computations:** single-source-of-truth literature names this exact failure ("each module defines/calculates differently → conflicting numbers"). Fix: one canonical definition all consumers call. When *changing* a metric's definition, **version it / recalibrate thresholds** and don't silently mix old+new historical values. (PowerMetrics; dbt Semantic Layer.)

---

## Requirements & Constraints

- **project.md "Multi-step lifecycle phases" (L25):** the finalization tail (Steps 9–11a) commits artifacts + backlog write-back "via a **flag-gated, stage-first step on all completion paths** (trunk, worktree-interactive post-merge, feature-branch post-merge)." Defects 2/3 change *what* is staged; the flag gate (`cortex-read-commit-artifacts`) and `git diff --cached --quiet` idempotent guard must be preserved.
- **project.md "Wheel-binstub vs working-tree invocation" (L38) + "Skill-helper modules" (L35):** console-script (`cortex-<skill>`) is the recommended idiom; `python3 -m cortex_command.<skill>` is the readable working-tree fallback; never bare `python3 <path>`. Directly governs defect 1.
- **pipeline.md "Metrics and Cost Tracking" (L99-110):** `rework_cycles` is a required per-feature metric + tier aggregate, computed by parsing `feature_complete` events; "last `feature_complete` per feature is canonical." Changing the counter's *value* changes future events only — the parse path and tolerant reader are unaffected; **no events-registry or schema_version change needed** (value-semantics change to an existing field is neither a new event nor a new field).
- **pipeline.md "Post-Merge Review" (L60-72) + `walkthrough.md` corpus convention:** the authoritative intended semantic is the `review_verdict.cycle` number — **cycle 0 = clean approval (no rework)**. walkthrough.md skip path writes `rework_cycles: 0`. This corroborates: `rework_cycles` should be 0 for first-pass approval (rework iterations, not verdict count).
- **ADR-0004 (multi-step-complete):** the phase restructuring is hard-to-reverse and coordinates complete.md / review_dispatch.py / metrics.py / statusline / scan-lifecycle / SKILL.md kept-pauses / parity test. The four defects are localized staging/counter fixes — they do NOT touch phase boundaries, so the kept-pauses inventory and Step-6 pause are untouched.
- **Backward-compat:** repo convention is read-tolerance / **no back-migration of event logs** (events.log is an append-only ledger; mirrors the `merge_anchor` shim at metrics.py:222-226). Do not rewrite historical events.
- **Hard gates that fire on these edits:**
  - **Dual-source mirror:** `skills/lifecycle/references/complete.md` (and `review.md`) mirror byte-identically to `plugins/cortex-core/skills/...`; editing canonical triggers `just build-plugin` regen — commit canonical + mirror **together** (per the drift-hook coupling memory). `counters.py`'s wrapper `bin/cortex-lifecycle-counters` mirrors to `plugins/cortex-core/bin/`.
  - **`tests/test_complete_md_finalization_commit.py`:** structural guard over the `<!-- finalization-commit-step -->` region. **Requires** the `cortex/backlog/` substring + enumerated lifecycle filenames + `git diff --cached --quiet`; **forbids** `git add cortex/lifecycle/`, `git push`, `gh pr create`. Defect-3 edit must keep `cortex/backlog/` satisfiable (a scoped path still contains the substring) and **the test must be updated** to encode the new scoping contract; defect 2 needs a new positive token.
  - SKILL.md-to-bin parity (`bin/cortex-check-parity`), size budget, kept-pauses parity, events-registry, grep-target test — none newly tripped by these localized edits (verified), provided defect 1 references a no-required-flag console script.

---

## Tradeoffs & Alternatives (per defect)

**Defect 1 — recommended: `python3 -m cortex_command.backlog.generate_index`** (smallest diff, exact repo idiom, matches update_item.py's own internal call, satisfies the bare-python-m audit). Defensible alternative: drop fallback 1 and lead with the `cortex-generate-backlog-index` console script (more durable single-source, but loses the source-tree fast path before a `uv tool install` refresh). Rejected: PYTHONPATH/FORCE_SOURCE (FORCE_SOURCE governs canonical/mirror selection, not import resolution — wouldn't even fix the error).

**Defect 2 — recommended: thread the drift `File:` path from review.md into Step 11a's staged set** (review.md already names the file; stage exactly that path). Alternative: scoped `git add -u cortex/requirements/` (the drift target is always pre-tracked, so `-u` loses nothing; low untracked-churn dir). Rejected: a new review→complete handoff state file/event (over-engineered — review already records the path).

**Defect 3 — recommended: enumerate the change-set** — lifecycle artifacts (already enumerated) + resolved item by path + cascade-touched siblings/parent, captured via `git add -u` over the **named cascade-target paths** (or have `update_item` print the paths it wrote), NOT a blanket `git add -u cortex/backlog/`. This gets cascade-capture without sweeping unrelated tickets. (Adjudication detail under Adversarial Review.)

**Defect 4 — recommended: redefine the counter to count `CHANGES_REQUESTED` `review_verdict` events from events.log** (see rework_cycles Reconciliation + Adversarial Review for why events.log beats a review.md regex). Keep `dashboard/data.py` as-is (already correct); make counters.py agree with it. Regenerate the `multiple-phases` fixture; add a real unit test. Keep `first_pass_approval_rate` (complementary: "did it pass first try?" vs "how deep was rework?").

**Sequencing:** see Adversarial Review — split into Commit A (defects 1-3, skill prose, one mirror regen, shared staging-contract test) and Commit B (defect 4, Python + fixtures + the fifth writer). One ticket/spec; two-commit implementation.

---

## rework_cycles Reconciliation

**Truth table** (what each method returns vs. correct target):

| Case | review.md verdicts | counters.py (verdict count) | data.py (transition loops) | events.log CHANGES_REQUESTED count | **CORRECT** |
|------|--------------------|-----------------------------|----------------------------|-------------------------------------|-------------|
| (a) simple, no review | none | 0 ✓ | 0 ✓ | 0 ✓ | **0** |
| (b) complex, first-pass APPROVED | 1 | **1 ✗** | 0 ✓ | 0 ✓ | **0** |
| (c) 1× CHANGES_REQUESTED → APPROVED | 2 | **2 ✗** | 1 ✓ | 1 ✓ | **1** |
| (d) 2-cycle rework | 3 | **3 ✗** | 2 ✓ | 2 ✓ | **2** |

**Empirical corpus result (adversarial):** events.log-CHANGES_REQUESTED-count vs data.py = **0 mismatches in 84 event-emitting features**; buggy counters.py vs truth = **78/84 mismatches**. So the bug mis-reports essentially *every reviewed feature*, not only first-pass approvals. One archived feature (`wire-requirements-drift-check-into-lifecycle-review`) showed counters.py=2, data.py=0, historical-event=1 (three values, truth 0) because a review.md can hold **multiple verdict blocks per round** (a requirements-drift sub-verdict + main verdict) — so counters.py is inflatable *beyond* a clean off-by-one.

**Correct definition:** `rework_cycles` = number of `CHANGES_REQUESTED` `review_verdict` events = review→implement loop-backs. events.log is reachable from counters.py's `feature_dir` (currently ignored). This is immune to review.md being overwritten per-round (the dominant behavior) and handles REJECTED-escalation correctly.

**Alert threshold (`high_rework >= 2`, alerts.py):** reads data.py's *already-correct* value (not the counter), so the threshold needs **no change** and keeps meaning "2+ real rework loops" before and after the fix.

**Backward-compat:** historical *interactive* `feature_complete` events keep old inflated values; `metrics.py:avg_rework_cycles` transiently mixes old+new (biases the average slightly high, self-corrects forward). No migration (append-only ledger convention). **Note:** `tests/failure_matrix.py:52-79` buckets on EXACT values with no read-tolerance — historical buggy events land permanently in the "1 cycle" bucket; descriptive-only (not an alert), so calibration isn't broken, but the stored-history contamination is real.

**Keep data.py's independent computation** — it reads events.log (present for in-flight features the dashboard monitors live), so reading the completion-only event value would lose the live metric. Fix its docstring (line 299) to state the actual predicate (requires prev transition `to == review`).

---

## Test & Regression Surface

- **Breaking fixtures (defect 4):** `tests/fixtures/cortex-lifecycle-counters/multiple-phases.{review_md,stdout}` hardcodes `rework_cycles: 2` — must change, AND **needs a full rewrite**: its `"verdict": "REWORK"` is a synthetic value that appears **0 times** in the corpus (real values: APPROVED, CHANGES_REQUESTED). Replace with a realistic CHANGES_REQUESTED→APPROVED review.md.
- **Parity test nuance to verify in Plan:** the Test agent flagged `tests/test_bin_lifecycle_state_parity.py:127` as re-deriving the buggy regex locally (`expected_rework = len(RE_VERDICT.findall(review_text))`) — a potential "false-parity trap." The Adversarial agent confirmed `bin/cortex-lifecycle-counters` is a *dual-channel wrapper* (execs `python3 -m cortex_command.lifecycle.counters`, no second regex), and `test_cortex_lifecycle_counters_parity.py` is a golden-replay. **Reconcile in Plan:** if a test file recomputes expectations from the old regex, update that recompute logic too; the bash wrapper itself needs no change.
- **Coverage gap:** there is **no direct unit test** for `count_rework_cycles`. Add `cortex_command/lifecycle/tests/test_counters.py` (auto-collected per `pyproject.toml` testpaths) covering cases (a)-(d) + REJECTED-escalation.
- **Defects 1-3 are skill-prose** (complete.md is markdown, no bin/ helper performs the staging). Feasible coverage: extend `test_complete_md_finalization_commit.py` with positive/negative tokens encoding the new staging contract (defect 2: require the requirements-drift staging token; defect 3: assert scoped staging + negative-assert the unscoped `git add cortex/backlog/`). Defect 1: a string-absence test that complete.md no longer contains `python3 cortex_command/…py` (or extend the L201 lint to flag bare `python3 <path>.py` cortex_command invocations). True behavioral staging coverage would need a hermetic-git-repo dry-run harness (pattern exists: `test_complete_cleanup_gates.py`) — durable but requires extracting staging into a testable bin/ helper.
- **Dashboard tests** (`test_alerts.py` threshold-2, `test_templates.py` rework:0) inject values directly and do not break; re-validate `test_alerts.py` semantics against the corrected source.
- **Invocation:** `just test` (pytest across the testpaths roots).

---

## Finalization Staging Completeness

**Three completion paths × file-category matrix** (Step 11a time, uncommitted state):

| File category | Trunk (on-main short-circuit) | Worktree-interactive (post-merge) | Feature-branch (post-merge) |
|---|---|---|---|
| Lifecycle artifacts | **pending** (Steps 2-5 skipped) | already-committed (merged) | already-committed (merged) |
| Feature source | **pending** (Step 2 skipped) | committed/merged | committed/merged |
| Backlog `complete` write-back | **pending** | **pending** | **pending** |
| Cascade-rewritten siblings/parent `.md` | **pending** (if fired) | **pending** (if fired) | **pending** (if fired) |
| Review-phase requirements drift | **pending** ← Defect 2 | committed (rode Step 2) | committed (rode Step 2) |
| index.json / index.md | gitignored | gitignored | gitignored |
| Unrelated untracked tickets | swept by dir-add ← Defect 3 | swept | swept |

**Stage-first invariant (complete.md:264-271):** stage exactly the feature's logical change-set — all of it, nothing extraneous — on every path; `git diff --cached --quiet` no-ops the commit on the worktree path. Current Step 11a violates it both ways: under-stages (trunk drift, defect 2) and over-stages (untracked sweep, defect 3).

**Key fact:** the trunk path has **NO clean-tree guard** (the porcelain dirty guards at complete.md:159,187 are worktree-only), so on trunk the working tree legitimately holds uncommitted feature source AND can hold unrelated dirty files (project.md L55 "destructive operations preserve uncommitted state" anticipates this). Reliably-NEW files = lifecycle artifacts (trunk only). Reliably-MODIFIED (pre-tracked) = resolved item, cascade siblings/parent, drift target, feature source. **There is no reliably-new backlog item** — the lifecycle resolves a pre-existing ticket; it never calls `cortex-create-backlog-item`.

**Recommendation:** one unified Step 11a *reframing* — enumerate the logical change-set (lifecycle artifacts + resolved item by path + named drift `File:` path + cascade-touched paths) — resolves both defects with one edit. Do NOT delegate to a blanket `git add -u` (over-stages on the guard-less trunk path).

---

## Adversarial Review

Verified against the 189-feature corpus and the code; corrections folded into the sections above. Load-bearing adversarial findings:

- **Defect 4 formula:** "count non-APPROVED verdicts over review.md" is **wrong** — fails on (1) REJECTED-escalation (review.md:152-157 routes REJECTED → escalate, no re-implement, so it's not rework), (2) review.md being overwritten per-round (78/84 features → regex undercounts), (3) stray `[A-Z_]+` verdicts (PARTIAL/PASS/ERROR/A) miscounted. `count - 1` underflows to -1 on empty review.md. **Robust answer: count `CHANGES_REQUESTED` events in events.log** (matches data.py 84/84 and the overnight-stored value). Fallback if review.md-only is mandated: count `CHANGES_REQUESTED` specifically (not non-APPROVED), but flag that it undercounts overwritten-review.md features.
- **Defect 3 cascade-never-creates: confirmed true** (both helpers only `atomic_write` glob-matched pre-existing files). But a *different* path can leave a new untracked backlog file — a follow-up ticket authored during the lifecycle — which `git add -u cortex/backlog/` would drop and the current dir-add captures. Cuts toward enumeration.
- **git add -u adjudication:** scoped `git add -u cortex/backlog/` canNOT sweep source outside backlog/ (pathspec confines it), so the "sweeps feature source" critique misfires for the *scoped* form. But the live tree proves the residual risk: `git status` shows `M cortex/backlog/296-…md` (tracked-modified) alongside untracked 293/294. A concurrent unrelated ticket can be untracked (`-u` skips — good) OR tracked-modified (`-u` sweeps — bad); both occur. **Enumerate named paths** is the safe resolution.
- **Five computation sites** (counters.py, data.py, metrics.py, **common.py cycle-number**, **walkthrough.md:280-283 crash-recovery — also buggy**). The fifth writer needs its own semantic fix; common.py's cycle-number is correct-for-purpose, just document it.
- **`bin/cortex-lifecycle-counters` is a wrapper, not a twin** — defect-4 churn is bounded (counters.py + fixture rewrite + unit test + walkthrough.md + a failure_matrix read-note); no second regex to keep in lockstep.
- **alerts.py is NOT contaminated** (reads data.py's correct value); threshold safe.
- **Sequencing:** split into Commit A (defects 1-3) and Commit B (defect 4) — defect 4 drags fixture churn + the fifth writer that the four-defect framing omitted.

---

## Open Questions

All converged to research-backed recommendations; each is **deferred to the Spec phase** for the user decision the recommendation implies (none blocks Spec entry).

1. **Defect 4 counter data source — events.log vs review.md.** Recommendation: count `CHANGES_REQUESTED` `review_verdict` events from events.log (robust; matches data.py 84/84; immune to review.md overwrite). Trade-off: it changes the counter's input from review.md text to the event stream, a slightly larger but more correct change. *Deferred: Spec confirms the data source.*
2. **Scope expansion to the fifth writer.** `walkthrough.md:280-283` (morning-review crash-recovery `rework_cycles: C`) is independently buggy — not among the four named defects. Recommendation: include it (same bug class; leaving it inconsistent re-introduces the divergence the ticket is closing) and add a one-line note documenting `common.py`'s cycle-number as deliberately distinct. *Deferred: Spec decides whether to fold the fifth writer into this ticket or split a follow-up.*
3. **Defect 2/3 staging mechanism — enumerate vs scoped `git add -u`.** Adversarially adjudicated toward **enumerating the change-set** (+ threading review's `File:` path). The sub-question of *how* to capture cascade siblings — have `update_item` print the paths it wrote, vs. enumerate parent+blocked-by paths in the skill, vs. scoped `git add -u` over named paths — is a Plan-level mechanism choice. *Deferred: Spec sets the contract (enumerate logical change-set), Plan picks the cascade-capture mechanism.*
4. **Implementation sequencing — one commit vs two.** Recommendation: one spec/ticket, two-commit implementation (A: skill-prose defects 1-3 + mirror; B: Python defect 4 + fixtures + fifth writer). *Deferred: Plan finalizes task decomposition.*
