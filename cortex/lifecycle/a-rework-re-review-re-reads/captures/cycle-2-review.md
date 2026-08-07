# Review — a-rework-re-review-re-reads · cycle 2 · rework re-review (scoped)

Tier `complex` · criticality `high`.

Test baseline consumed as handed: `just test` → 8/8 suites passed, log at
`/private/tmp/claude-501/-Users-charliehall-Workspaces-cortex-command/9ead0bc7-7d79-4389-8196-0816b761236c/scratchpad/fulltest2.log`.
The suite was not re-executed. As an independent read on the checklist criteria I ran the five
modules the rework touched — `test_common.py`, `test_review_brief_cli.py`,
`test_review_brief_content.py`, `test_stage_artifacts_review_archive.py`,
`test_review_brief_end_to_end.py` → **82 passed**. `cortex_command/tests/` is inside the
`tests-lifecycle-backlog-cortex` suite (`justfile:576`), so the new `test_common.py` guard is in
the baseline's collection rather than orphaned.

Reading scope: `914bc89d..HEAD`. That range contains exactly five commits, all this feature's
(`07a09666 9bd7b128 fcf01eac 78905511 1e80c857`); `git log 914bc89d..HEAD` returns no others, so the
concurrent session's commits are not on this branch and nothing needed attributing away.

Requirements loaded: `cortex/requirements/project.md`, `cortex/requirements/glossary.md`.
`cortex/requirements/lifecycle.md` is still unwritten (#469), so this `areas: ['lifecycle']` ticket's
area-level requirements remain **unassessed** — carried forward from cycle 1 unchanged.

---

## Prior-Cycle Checklist

### 1. Requirement 17 unimplemented, acceptance non-falsifiable — **RESOLVED**

The guard route was taken, and both halves the issue offered were actually done rather than one.

**The guard.** `9bd7b128` adds two classes to `cortex_command/tests/test_common.py`.
`TestCycleCountsReviewVerdictEvents` pins the behaviour on fixtures where the two candidate sources
deliberately disagree (3 `review_verdict` rows against a 1-verdict `review.md` → `cycle == 3`; 1 row
against 5 verdicts → `cycle == 1`), and it asserts the *phase* each yields, so `cycle` is shown to be
load-bearing rather than decorative. `TestCycleDocstringDescribesEventCount` scopes its read to the
`Returns` section's `cycle:` bullet via `_CYCLE_DOC_BULLET` rather than the whole docstring — correct,
because the docstring names `review.md` legitimately elsewhere and a whole-docstring grep could neither
confirm nor refute what `cycle` counts.

**I mutation-tested it independently** rather than accepting the orchestrator's account. Loading
`cortex_command.common` and rewriting the bullet at runtime to the stale pre-`2a4fb715` wording
("the count of `verdict` regex matches in review.md") flips three of the four docstring assertions:
`test_cycle_bullet_names_review_verdict_events`,
`test_cycle_bullet_does_not_describe_a_review_md_regex_count`, and
`test_documented_source_matches_observed_behaviour`. The guard is falsifiable in the direction that
matters. `common.py` itself is untouched by the range (`git diff --name-only 914bc89d..HEAD` does not
list it), so the "do not manufacture a diff" instruction was honoured.

**The record.** `1e80c857` also corrects plan.md task 3's status line: "only the stage_artifacts half
was implemented here. Requirement 17's common.py docstring was ALREADY correct at 4c61e56c^ (fixed
out-of-lifecycle by 2a4fb715), so both its acceptance greps passed on the unmodified repo. Falsifiable
guard added in rework: 9bd7b128." That is the honest record cycle 1 asked for.

The new guard tests do of course pass on an unmodified tree — that is inherent to a regression guard
and is exactly what was commissioned. It is not the requirement-17 defect recurring, because the defect
was an acceptance criterion asserted as *proof of work done*; this is asserted as an invariant.

### 2. Requirement 20 clause 3 / requirement 18 unevidenced — **RESOLVED**

The evidence exists and I verified it on the real repo, not in a fixture.

**Live cycle-2 run.** `cortex/lifecycle/a-rework-re-review-re-reads/review-cycle-1.md` exists and its
sha256 (`2c431f29…ecdb3`) is identical both to the `review.md` committed in `07a09666` and to the
`review.md` still on disk — copy, never move, on the real path, in a real dispatch. `events.log`
carries the live row `{"event": "review_dispatched", "cycle": 2, "mode": "rework", "baseline_sha":
"1e80c857…"}`, and the brief handed to me is the scoped one, carrying all four cycle-1 issue texts and
the range `914bc89d..HEAD` read back from the cycle-1 row.

**The capture.** `cortex/lifecycle/a-rework-re-review-re-reads/captures/cycle-2-scoped-brief.txt`
(7170 B) is byte-for-byte the brief I was handed. I confirmed the rig works against *this* repo rather
than only the test's temp one, by calling `collect_paths` directly: the capture appears in the
candidate set at `complete`, `plan`, `refine`, `implement` and `review`, while `review-cycle-1.md`
appears at `complete` only — precisely the asymmetry the module documents. `git check-ignore` on the
capture exits 1, so nothing silently drops it.

**The pre-step.** The plan's throwaway-capture round trip was replaced by a durable one:
`fcf01eac` adds `test_captures_reach_staged_paths` (parametrized over all three phases `--phase`
accepts), a no-captures control that keeps the assertion discriminating, and a nested/dot-entry case
pinning both enumeration rules — each asserted against a real git index and a real commit's
`--name-only`. This is a stronger substitution than the discarded sample the plan specified, and I am
treating it as satisfying rather than dodging the instruction. `_capture_files` predates this lifecycle
(present at `4c61e56c^`), so these tests pass on an unmodified tree; that is what "confirm
`_capture_files` enumerates it into `staged_paths`" asked for.

**Requirement 18 and requirement 20 clause 3 are now met by this file.** It carries four dispositions,
one per cycle-1 checklist item, and none of those four issue texts is re-emitted under
`## Out-of-Scope Findings`. That is third-party checkable without taking my word for it: count
`### N.` entries in this section against the length of the `issues` array in `review-cycle-1.md`'s
Verdict block.

**One thing I could not close, and it is not blocking.** Plan task 15b asks for "the emitted brief
*and the resulting `review.md`*" under `captures/`. Only the brief is there — the review.md half cannot
exist at dispatch time, and I am read-only with respect to `captures/`. The spec's own acceptance
(requirement 20 clause 3) is stated over `cortex/lifecycle/{feature}/review.md`, which is where this
file lives and which stages at `complete`, so the *requirement* is met regardless. If a cycle 3 ever
runs, this file additionally archives to `review-cycle-2.md`. Flagging it so the orchestrator can copy
it into `captures/` at completion if it wants the plan's literal form.

### 3. Brief's rendered headings do not match the headings it demands — **RESOLVED**

`78905511` changes `review_brief.py:347` to `## Prior-Cycle Checklist` and `:360` to
`## Out-of-Scope Findings`. The brief I was handed renders both in the demanded Title Case, and a
repo-wide grep finds the lowercase spellings nowhere in `cortex_command/`, `skills/`,
`plugins/cortex-core/skills/`, `scripts/` or `tests/`.

The new test is the right shape: `test_rendered_headings_match_the_headings_they_demand` extracts every
rendered `## …` heading and every backtick-quoted `` `## …` `` demanded heading **from the brief
itself**, groups them by casefold, and fails on any group with more than one spelling. Nothing is
hardcoded, so it cannot be satisfied by editing the test to match a drifted heading, and it is
parametrized over both `rework` and `full` mode. Unlike the guards above, this one genuinely fails on
the pre-rework tree — it is the discriminating kind.

Residual, worth stating but not a finding: the check only covers headings the brief both renders and
demands. `## Requirements Drift` and `## Suggested Requirements Update` are demanded but never
rendered, so their casing is unguarded by this test. I checked them by hand against the consumer:
`skills/build/references/review.md` §3 and §3a quote both in exactly the demanded spelling.

### 4. Degraded dispatch records a mode that misdescribes what it served — **RESOLVED**

`_record_baseline` is no longer called before the branch. `main` now closes over a `_record(served_mode)`
helper and each terminal path calls it with what it actually served: `_degrade` records `"full"`
(`review_brief.py:639`), the cycle-1 full path records `"full"` (`:652`), and the scoped path records
`"rework"` (`:698`). The three paths are mutually exclusive and every one of them records, so no
dispatch lost its row and `baseline_sha` capture is unchanged on the degraded path.

**The two-value-enum reasoning holds, and I checked it rather than accepted it.** `cycle = rework_cycles
+ 1` and `mode = "rework" iff rework_cycles >= 1`, so `mode == "full"` is exactly `cycle == 1` at
selection time. `_degrade` is reachable only after the `mode == "full"` branch has already returned.
Therefore a `full` row at `cycle >= 2` can only have come from `_degrade` — the inference "a `full` row
at cycle ≥ 2 is exactly a degraded rework" is sound, and `lifecycle_event.py:337`'s
`("full", "rework")` choice tuple stays honest. No consumer anywhere reads the field
(`grep review_dispatched` finds only `review_brief.py`, `lifecycle_event.py`, and tests), so widening it
to a third value would have bought nothing.

Three new tests pin it, and `test_a_degraded_rework_records_the_full_mode_it_actually_served` asserts
the recorded value is a member of `_typed_mode_choices()` read out of `lifecycle_event._EVENT_SUBCOMMANDS`
rather than a restated literal — so the row cannot drift out of the CLI's vocabulary.

One consequence of the fix is reported under Out-of-Scope Findings below; it is a new narrow case, not
this item recurring.

---

## Out-of-Scope Findings

Two, both minor, neither blocking. Nothing from the checklist is re-emitted here.

**1. Degrade-then-recover pins the wrong mode (introduced by issue 4's fix).** `_record_baseline`'s
idempotency guard is `if _dispatch_row_for_cycle(rows, cycle) is not None: return` (`:543`). It exists
to stop a re-dispatch sliding `baseline_sha` forward onto the rework's own commits — correct, and it
must stay. But `mode` now rides that same guard with the opposite update policy: `baseline_sha` must be
pinned to the first dispatch, while `mode` is supposed to describe the last serve. So an operator who
hits a degrade (say the archive was unreadable), fixes it, and re-dispatches the same cycle gets a
scoped brief while `events.log` keeps saying `"mode": "full"` — the exact inverse of the bug just
fixed, in a narrower case. Impact today is nil (nothing reads the field), the direction is safe (it
over-reports degradation, which prompts a look rather than hiding one), and
`test_a_redispatched_degraded_cycle_appends_no_second_row` deliberately pins the row-count invariant
rather than this. Recording it so it is not rediscovered as a surprise; not worth a rework cycle.

**2. The heading change was a brief-shape change, and I checked it against requirement 9 rather than
assuming.** `project.md`'s newly auto-applied bullet says a brief-shape change *the prose depends on*
moves `PROTOCOL_VERSION` and `protocol-expectation.txt` in the same commit. `78905511` changed the
brief's shape and moved neither. That is correct here — `skills/build/references/review.md` depends on
`## Requirements Drift` (§3) and `## Suggested Requirements Update` (§3a), both untouched, and on
nothing else the brief renders; the two renamed headings appear in no shipped prose and no overnight
prompt. So the constraint was honoured, not skipped. Noting it because "did the rework quietly owe a
protocol bump?" is exactly the question a scoped review is tempted to skip, and the answer wanted to be
on the record.

**Carried forward from cycle 1, unresolved by design and still open:** `ratchet_refs.ratchet_write`
destroying `# raised:` provenance belongs in its own ticket, and #469's missing
`cortex/requirements/lifecycle.md` means this feature's area-level requirements went unassessed by
either cycle. Neither is this rework's work.

---

## Stage 1 — Spec compliance

**Re-verified this cycle** (the rework touched them, or the criterion was cheap enough that carrying it
would have been the lazier call):

- **1, 2 — Prior review archived, never overwritten.** PASS, now on live evidence rather than fixtures:
  `review-cycle-1.md` and the `review.md` committed in `07a09666` share sha256 `2c431f29…ecdb3`, and
  `review.md` is still present with the same digest.
- **4 — Archived reviews are committed.** PASS, unchanged. Confirmed on the real repo that the
  `complete` candidate set names `review-cycle-1.md` and no earlier phase does. Cycle 1's scope note
  about the untracked window during the rework still stands and is still symmetric with `review.md`.
- **7 — Checklist, reading scope, baseline decision.** PASS. All four cycle-1 issue texts, the range
  `914bc89d..HEAD` read from the cycle-1 dispatch row, and exactly one baseline decision (`re-run`) are
  present in the brief I was handed.
- **8 — Scoping bounds reading, never concluding.** PASS. The bounding statement and the
  affirmative-even-when-empty rule survived the heading rename;
  `test_nothing_found_must_still_be_stated_affirmatively` was updated to the new spelling and passes.
- **11, 13 — Baseline decision and SHA capture.** PASS. The cycle-2 row carries a 40-hex SHA
  (`1e80c857…`) that resolves and is HEAD-at-dispatch, and the decision correctly came out `re-run`
  because the range touches `cortex_command/`. `_record` moving into the branches did not disturb the
  read-back: `rows` is snapshotted before any append, so the cycle-1 row lookup is unaffected.
- **12 — `review.md` calls the verb and shrinks.** PASS. Re-measured at HEAD: `skills/build/references`
  = **57183**, pin = **57183**, both `# raised:` lines intact, no new one. No `skills/` or `plugins/`
  path appears in the rework range at all.
- **17 — `common.py`'s stale docstring.** Upgraded **PARTIAL → PASS**. The end state was already
  correct; what was missing was any guard, and `9bd7b128` supplies a falsifiable one (mutation-verified
  above). The plan's record of provenance is corrected in the same rework.
- **18 — Every checklist issue gets a disposition.** Upgraded **PARTIAL → PASS**. The demand side was
  already pinned; the artifact side is this file.
- **19 — Fails open to a full review, never an empty checklist.** PASS. All four degrade conditions are
  intact (`:662, :668, :680, :687`), each still writes a full brief to stdout, a `DEGRADED:` line to
  stderr, and exits 3 — and each now records its dispatch, which the pre-rework code did once for all
  four and the post-rework code does per branch. `build_rework_brief`'s `ValueError` on an empty
  `issues` list is untouched, so the overnight in-process caller still cannot bypass the rule.
- **20 — One criterion asserts the feature is wired.** Upgraded **PARTIAL → PASS**. Clauses 1 and 2
  were closed at cycle 1. Clause 3 is closed by this review, produced by a real reviewer handed a real
  scoped brief built from a real archive on the real path — which is precisely the thing no test could
  be.

**Carried forward from cycle 1** (rated there, untouched by this rework — this is their first and only
carry; a cycle 3 must re-verify rather than carry again):

- **3** — PASS; holds while `common.py`'s detector globs nothing matching `review-cycle-*.md`.
- **5** — PASS; holds while `pyproject.toml`'s console-script entry and `bin/cortex-lifecycle-review-brief`
  are unchanged (neither is in the rework range).
- **6** — PASS; holds while the verb derives mode from `count_rework_cycles` — still true at
  `review_brief.py:617`.
- **9** — PASS on acceptance; holds while the prose depends only on `## Requirements Drift` and
  `## Suggested Requirements Update`, which I re-checked above. Cycle 1's flagged gap — the new
  wheel→prose fence dependency being ungoverned by the version floor — is unchanged and still real.
- **10** — PASS; holds while `parse_carried_forward` and the `## Carry-forward` block are unchanged.
  (Independently corroborated: no cycle-1 requirement was itself carried forward, so the brief
  correctly emitted no re-verification listing.)
- **14** — PASS; holds while `review_dispatch.py:614-628` builds the cycle-2 prompt from
  `build_rework_brief`. Not in the rework range; the heading rename flows through to overnight for free
  and no overnight test asserted the old spelling.
- **15** — PASS; holds while `cortex_command/pipeline/prompts/review.md:96` reads `"cycle": {cycle number}`.
- **16** — PASS; holds while `enumerate_reference_dirs` appends `cortex_command/pipeline/prompts` and
  its `size-pin.txt` is present.

**Stage 1 result: 20 PASS, 0 PARTIAL, 0 FAIL.**

---

## Stage 2 — Code quality

**The fixes are minimal and land in the right layer.** Every one of the four is either a test-only
addition or a control-flow rearrangement inside `main`; no shipped prose, no `common.py`, no
`stage_artifacts.py`, no protocol surface. `review_brief.py`'s diff is 23 lines, of which 9 are the
docstring explaining why a `full` row at cycle ≥ 2 is a degraded rework — the reasoning is recorded
where the next reader will hit it, not only in the commit message.

**The new tests are the derived kind, not the restated kind.** Three of them read their expectation out
of the thing under test rather than hardcoding it: `_heading_spellings` derives both the rendered and
the demanded headings from the brief, `_typed_mode_choices` reads the enum out of
`lifecycle_event._EVENT_SUBCOMMANDS`, and `_cycle_doc_bullet` reads the live docstring. That is the
property that makes them survive a refactor instead of being edited to match one.

**Test-comment density matches the module's existing convention** — the capture-rig block extends the
file's docstring map rather than appending an unexplained section, and `_feature_dir`'s docstring says
why the two counts disagree on purpose. Consistent with the surrounding style.

**Plan checkpointing is now honest.** `1e80c857` re-checkpoints tasks 1, 3 and 15 with what actually
happened rather than re-stamping them done. Task 14's verification command is still wrong as cycle 1
found (`uv run python scripts/ratchet_refs.py` routes to `check()` and cannot print a `pinned` line);
it was not corrected in this rework and I am not raising it again — the substance is covered by
`test_pipeline_prompts_enumerated_and_pinned`, cycle 1 explicitly declined to fail on it, and it is a
stale command in a plan, not a defect in the feature.

Nothing else in the range warrants comment. No naming drift, no new imports, no widening of the
inward-only import direction (`grep -cE '^\s*(from|import)\s+cortex_command\.pipeline'
cortex_command/lifecycle/review_brief.py` still 0).

---

## Requirements Drift

- **State**: `none`
- **Findings**: None
- **Update needed**: None

Reasoning, since the brief says to prefer `detected` under uncertainty and I am not claiming
uncertainty here. Cycle 1's two suggested updates were auto-applied to `project.md`'s
`## Architectural Constraints` and I checked both against the tree rather than assuming: the ratchet
bullet is accurate (`enumerate_reference_dirs` does append `cortex_command/pipeline/prompts`, and its
`size-pin.txt` is seeded), and the protocol bullet is accurate and was correctly *not* triggered by
this rework, as shown under Out-of-Scope Findings 2. The rework itself adds no behaviour a requirements
file would want to describe: three of the four fixes are tests, and the fourth refines the semantics of
an `events.log` field that no requirements document describes at any granularity and that no code reads.

---

## Verdict rationale

All four checklist items are resolved, and three of them were verified by a method independent of the
orchestrator's account — a runtime mutation of `common.py`'s docstring for item 1, a direct
`collect_paths` call against this repo for item 2, and the mutual-exclusivity argument over `main`'s
branches for item 4. Nothing the rework touched broke anything: the five affected test modules are 82
green and the handed baseline is 8/8.

The three requirements cycle 1 left PARTIAL now close. Seventeen has a falsifiable guard and an honest
plan record. Eighteen and twenty's third clause close on this artifact — which was the whole reason
cycle 1 spent a rework cycle rather than approving: the evidence that a reviewer handed a scoped brief
actually writes the dispositions it demands was available only from a real cycle-2 on this very
lifecycle, and it now exists at
`cortex/lifecycle/a-rework-re-review-re-reads/captures/cycle-2-scoped-brief.txt` plus this file. That
was the cheapest correct outcome and it has been taken.

Two things carry forward unresolved and neither belongs here: `ratchet_refs.ratchet_write`'s
destruction of `# raised:` provenance wants its own ticket, and #469's absent
`cortex/requirements/lifecycle.md` means this feature's area-level requirements were never assessed by
either cycle. The degrade-then-recover mode pin is new, narrow, unread by anything, and fails safe.

Approving.

```json
{"verdict": "APPROVED", "cycle": 2, "issues": [], "requirements_drift": "none"}
```
