# Review — a-rework-re-review-re-reads · cycle 1 · full review

Tier `complex` · criticality `high` — both stages run.

Test baseline consumed as handed: `just test` → 8/8 suites passed at `914bc89d`, log at
`/private/tmp/claude-501/-Users-charliehall-Workspaces-cortex-command/9ead0bc7-7d79-4389-8196-0816b761236c/scratchpad/fulltest.log`.
The suite was not re-executed. Targeted re-runs of the five test modules this feature added or
touched (`test_review_brief_cli.py`, `test_review_brief_content.py`, `test_review_brief_end_to_end.py`,
`test_stage_artifacts_review_archive.py`, `tests/test_reference_size_ratchet.py`) → 53 passed, as an
independent read on the criteria rather than a re-baseline.

Requirements loaded: `cortex/requirements/project.md`, `cortex/requirements/glossary.md`.
`cortex/requirements/lifecycle.md` is not yet written (backlog #469), so the area-level requirements
governing this `areas: ['lifecycle']` ticket are **unassessed**, not absent-by-design. Every drift
judgement below is therefore against `project.md` only.

---

## Stage 1 — Spec compliance

### Requirement: 1 — Prior review is archived, not destroyed

**PASS.** `review_brief._archive_prior_cycle` (`cortex_command/lifecycle/review_brief.py:499-522`) uses
`shutil.copy2`, never a rename, and returns early when the target exists. It is called from `main` at
`:621`, before anything else touches the directory, so the CLI entry point archives-then-emits in one
invocation exactly as the requirement specifies — no separate call was added to `review.md`.
`test_review_brief_end_to_end.py::test_cycle_two_dispatch_archives_the_prior_review_byte_for_byte`
asserts both clauses against the real `bin/` wrapper: `sha256(review-cycle-1.md) ==` the pre-dispatch
digest, and `review.md` still present with identical bytes. Overnight is correctly exempt — it calls
`build_rework_brief` in-process (`review_dispatch.py:614`) and never reaches the archive.

### Requirement: 2 — The archive never overwrites, and is safe to retry

**PASS.** `if not source.is_file() or target.exists(): return` (`review_brief.py:517`) gives no-clobber;
copy semantics give the crash-convergence property. Covered in `test_review_brief_cli.py` by the
tree-plus-checksum idempotency case named in the plan.

### Requirement: 3 — The current cycle stays at `review.md`

**PASS**, with a note. `common.py`'s detector globs nothing matching `review-cycle-*.md`, so archives
are inert to phase detection and `_stat_key(review.md)` is untouched.
`test_stage_artifacts_review_archive.py` asserts invariance with archives present, including the
`implement-rework` case. Note: this criterion would also pass on the unmodified repo — it is a
no-regression guard rather than a proof of new behavior. That is inherent to what it asserts, not a
defect, but it should not be counted as evidence the feature works.

### Requirement: 4 — Archived reviews are committed

**PASS**, with a scope note. `stage_artifacts._review_cycle_archives` (`:218-234`) enumerates
`review-cycle-*.md` into explicit repo-relative paths — glob-built list, explicit `git add`, exactly the
discipline the module docstring licenses for `captures/`. The docstring's "Per-phase staged set" section
was updated (`:33-35`). Wired into `collect_paths`'s `complete` branch only.

Note: the acceptance's first clause — "after a rework cycle, `git status --porcelain` shows no untracked
`review-cycle-*.md`" — is not literally true *during* a rework. The archive is created at cycle-N
dispatch and staged only at `complete`, so it is untracked for the whole rework-and-cycle-2 window, and
a lifecycle that escalates on the rework cap never stages it at all. I am not failing this: `review.md`
itself receives identical treatment (`collect_paths` has no `review` or `implement` branch), so the
window is pre-existing and symmetric, and the acceptance's second clause — the completing commit lists
the archive — is fully met. Worth stating so the edge case the requirement cites (`git clean -fd`,
fresh clone) is understood to be closed only at completion.

### Requirement: 5 — A brief verb exists and serves both modes

**PASS.** `pyproject.toml:86` registers the console script; `bin/cortex-lifecycle-review-brief` is
present and executable; `tests/test_lifecycle_verb_deployment.py` carries its row. Mode selection at
`review_brief.py:615-617`. Both modes name the absolute review path (`:613`, resolved). Both exit 0 on
the happy path.

### Requirement: 6 — The discriminant is the existing counter

**PASS.** `from cortex_command.lifecycle.counters import count_rework_cycles` (`:87`), used at `:615`.
`common.py`'s reduced `cycle` is never read. `counters.count_rework_cycles` counts
`review_verdict`/`CHANGES_REQUESTED` rows, so one such row yields `rework_cycles == 1` → rework mode
while the reduced `cycle` reads 1. Pinned in the CLI tests and again end-to-end, where the verdict row
comes from the real `bin/cortex-lifecycle-advance` rather than a hand-written line.

### Requirement: 7 — Checklist, reading scope, baseline decision

**PASS.** `build_rework_brief` emits all three: one numbered entry per prior issue (`:343`), the
`{baseline_sha}..HEAD` range (`:335`), and exactly one of `reuse baseline` / `re-run` (`:365-382`).
The interactive checklist is read from the archive (`main` `:645-669`), the overnight one from the
in-process list (`review_dispatch.py:614-628`). The second clause holds: archive deleted → `_degrade`,
never an empty checklist.

### Requirement: 8 — Scoping bounds reading, never concluding

**PASS.** The bounding statement is at `review_brief.py:338-340` and the mandatory
`## Out-of-Scope Findings` section at `:358-362`, with the affirmative-even-when-empty rule stated
explicitly. `test_review_brief_content.py::test_nothing_found_must_still_be_stated_affirmatively`
pins it.

### Requirement: 9 — The brief's shape is protocol-governed

**PASS on acceptance**, with a real gap flagged below. `protocol.py` gained the governance note
(`:45-50`) and the module docstring names the brief as a served surface (`:8`). The parity test passes.
The plan's decision not to move `PROTOCOL_VERSION` is defensible: no served payload shape changed, and
requirement 19 wants a stale wheel to degrade rather than halt.

**But** — the acceptance criterion ("the existing parity test passes at HEAD") passes on the unmodified
repo and so cannot decide anything, which the plan's Risks section already concedes. More importantly,
this feature introduced a *new* wheel↔prose shape dependency in the opposite direction, and it is not
governed by anything: the wheel's `parse_verdict_block` now requires the ```` ```json ```` fence that
`skills/build/references/review.md` prescribes. A new wheel against an old plugin (bare fence) makes
every interactive rework degrade to a full brief. That is the exact skew requirement 9 exists to catch,
it is fail-open rather than fail-loud, and the version floor does not see it. Filed as an issue.

### Requirement: 10 — Carry-forward by reference, with condition, depth-bounded

**PASS.** The form, the naming of cycle and condition, and the once-only bound are all in the
`## Carry-forward` block (`:384-403`). `parse_carried_forward` (`:139-166`) reads the archive and the
already-carried items are listed as **requiring re-verification** (`:396-403`). Four content tests cover
the form, the bound, the re-verification listing, and the absence of the listing when nothing was
carried; the end-to-end test confirms `CARRIED_REQUIREMENT` reaches the brief from the archive's own
prose.

### Requirement: 11 — The test-baseline decision is stated, not left to judgment

**PASS.** `decide_test_baseline` (`:169-198`) implements the rule as specified, with `events.log`
correctly non-exempt (only flat `*.md` directly under the feature dir is exempt — the `"/" not in
path[len(prefix):]` guard also correctly excludes `captures/`). Two-dot `..` at `:565`. All three
acceptance cases are pinned over a real temp repo:
`test_lifecycle_markdown_only_diff_reuses_the_baseline`, `test_events_log_is_not_exempt_and_forces_a_re_run`,
`test_any_source_path_forces_a_re_run`. An untakeable diff decides toward `re-run` (`:680-682`) —
safe, and not something the spec anticipated.

### Requirement: 12 — `review.md` calls the verb and shrinks

**PASS on substance**, with a note on the criterion. `skills/build/references/` measures **57183**, and
the pin was lowered `57964 → 57185 → 57183` with both `# raised:` lines intact (verified by hand-edit,
per `a6a4478d`'s commit body). No new `# raised:` line. The mirror pin matches.
`tests/test_reference_size_ratchet.py` is green for both directories.

I diffed the pre-lifecycle §§1–2 against the brief to confirm nothing was silently dropped rather than
moved. Everything moved is present: stage definitions and their tier gate → `build_full_brief`'s
`## Scope`; drift-section and suggested-update formats → `_output_shape_section`; verdict field-name
prohibitions → same; PARTIAL and uncertain-drift guidance → same; the read-only/no-suite-re-run rule →
`_preamble`. The Verdict JSON block correctly stayed in prose (`review.md:27-29`), and the §1 pointer at
the brief's reuse/re-run decision was added. The budget closed with 781 bytes to spare, so none of the
four additions the spec warned might get silently dropped — including the archive call — was omitted.

Note: as written, both acceptance criteria ("measures ≤ 57964" and "no new `# raised:` line") pass on
the unmodified repo, since the directory measured *exactly* 57964 at lifecycle start. The real
evidence is the pin lowering, which no stated criterion demands. Recording this because it is the same
class of defect as requirement 17.

### Requirement: 13 — The interactive path captures a baseline SHA

**PASS.** `_record_baseline` (`:525-555`) writes an additive `review_dispatched` row carrying a
`git rev-parse HEAD` value validated against `^[0-9a-f]{40}$`, idempotent on the cycle so a re-dispatch
does not slide the baseline onto the rework's own commits. `test_cycle_two_brief_names_a_sha_that_resolves_in_the_repo`
asserts the SHA matches, resolves via `rev-parse --verify <sha>^{commit}`, is the cycle-1 baseline
rather than the rework SHA, and that `rev-list sha..HEAD` is non-empty — that last check goes beyond the
criterion and closes the "resolves but scopes to nothing" hole. This lifecycle's own `events.log` carries
the live row: `{"event": "review_dispatched", "cycle": 1, "mode": "full", "baseline_sha": "914bc89d…"}`.

### Requirement: 14 — Overnight uses the same verb

**PASS.** `review_dispatch.py:614-628` builds the cycle-2 prompt from `build_rework_brief` with the
in-process `issues`, threading `before_sha` as the baseline and stating `RE_RUN` explicitly rather than
inheriting a path-derived decision. The template-reload-plus-appended-sentence construction is gone
(`grep 'Focus on whether the flagged issues were resolved'` = 0). The empty-`issues` branch degrades to
`build_full_brief` with a named reason rather than raising. The `except (FileNotFoundError, OSError,
ValueError)` deferral path is intact and now also catches the `ValueError` `build_rework_brief` raises on
an empty checklist. ADR-0015's discriminants did not move — `could_not_run` remains at
`review_dispatch.py:182` and `REVIEW_NO_ARTIFACT` at `overnight/constants.py:26`.

### Requirement: 15 — The overnight template stops biasing the reported cycle

**PASS.** `cortex_command/pipeline/prompts/review.md:96` now reads `"cycle": {cycle number}`; the
literal `"cycle": 1` was present at lifecycle start and is now absent. Line 55's description is retained
as the authority. Falsifiable and falsified in the right direction.

### Requirement: 16 — The prompts directory gains ratchet parity

**PASS.** `enumerate_reference_dirs` appends `cortex_command/pipeline/prompts` (`ratchet_refs.py:68`)
with the rationale in the docstring; `cortex_command/pipeline/prompts/size-pin.txt` is seeded at 9398.
`tests/test_reference_size_ratchet.py` adds both halves the requirement asks for:
`test_pipeline_prompts_enumerated_and_pinned` and `test_pipeline_prompts_missing_pin_is_reported`, the
latter over a real copy with the pin removed. The `test_mirror_dirs_deduplicate` partition question the
plan raised was answered assertively (`:150-154`) rather than left incidental.

### Requirement: 17 — `common.py`'s stale docstring is corrected

**PARTIAL.** Both acceptance criteria hold at HEAD — `grep 'regex matches in review.md'` exits 1, and
`common.py:479-480` names `review_verdict` rows as what `cycle` counts. But **this feature produced
neither**. I verified both against the tree at `4c61e56c^` (the commit before this lifecycle's first):
the stale string was already gone, removed by the unrelated `2a4fb715`, and the replacement docstring
line was already present verbatim. `common.py` appears in none of the sixteen lifecycle commits, and
task 3's commit `64aa2f18` touched only `stage_artifacts.py` and its test. The orchestrator's finding #1
is confirmed in full, and it is the more serious half that matters: **both criteria were non-falsifiable
from the moment the spec was written**, so nothing in this lifecycle could have detected that the task
was not done. Task 3 is nevertheless marked `[x] done`. The end state is correct; the plan's record of
how it got there is not, and no test guards it against a future regression.

### Requirement: 18 — Every checklist issue gets a disposition

**PARTIAL.** The brief demands it correctly and unambiguously: `## Prior-cycle checklist`
(`review_brief.py:345-354`) requires "one explicit disposition per item below", names the vocabulary,
forbids silent dropping, and forbids re-emitting a resolved item under new problems.
`test_brief_demands_one_disposition_per_prior_issue` and
`test_brief_forbids_re_emitting_resolved_issues_as_new_problems` pin the demand.

But the acceptance is stated over the *artifact* — "`cortex/lifecycle/{feature}/review.md` contains three
dispositions, one per prior issue" — and nothing verifies that. Only a real reviewer on a real cycle-2
can produce it, and no such artifact exists. The requirement is implemented as far as machine
verification can reach; its stated acceptance is not met. See requirement 20, which is the same gap.

### Requirement: 19 — The verb fails open to a full review, never to an empty checklist

**PASS.** Four degrade conditions, each with a distinct reason string: archive missing/unreadable
(`:648`), unparseable verdict block (`:654`), empty `issues` array (`:666`), no baseline row (`:673`).
All four write a **full** brief to stdout, a `DEGRADED: <reason>` line to stderr, and exit 3. The full
brief opens by naming the failure and explicitly tells the reviewer the read failure is not evidence the
prior cycle found nothing (`:262-267`) — that is the requirement's "distinguishable from a legitimately
empty checklist" clause, satisfied in the payload rather than only in the exit code. Root-resolution
failure exits 1 writing nothing, so the prose's "non-zero exit **or no output**" rule covers it. The
verb-absent-from-PATH clause is prose, and `review.md:19` states it correctly.

`build_rework_brief` additionally raises `ValueError` on an empty `issues` list (`:321-325`), so the
in-process overnight caller cannot bypass the rule either. Both callers converge on the same invariant —
this is the cleanest part of the feature.

### Requirement: 20 — One criterion asserts the feature is wired, not merely present

**PARTIAL.** Clauses 1 and 2 are genuinely closed, and closed well.
`cortex_command/lifecycle/tests/test_review_brief_end_to_end.py` drives a throwaway lifecycle through
cycle-1 dispatch → CHANGES_REQUESTED verdict → rework commit → cycle-2 dispatch using the real
`bin/` wrappers under `CORTEX_COMMAND_FORCE_SOURCE=1` (correctly avoiding the wheel-on-PATH trap), with
the verdict row written by the real `cortex-lifecycle-advance` rather than by hand. Crucially, it reads
the Verdict fence's info string out of the *shipped prose at runtime* rather than hardcoding a
convenient one — so a prose/parser mismatch fails this test instead of passing it. That is the design
that makes the criterion non-vacuous, and it is better than the spec asked for.

Clause 3 — "the second review's `review.md` contains a disposition for each" — is **unevidenced**. It
needs a real reviewer agent, which no test can be. The plan's answer (task 15b) was to capture it from
this lifecycle's own review under `cortex/lifecycle/a-rework-re-review-re-reads/captures/`. That
directory does not exist, and cannot yet: this is cycle 1, a full review, which produces no
dispositions. The plan's own pre-step for that rig — "produce and validate a discarded sample of the
exact committed-evidence shape end to end … then delete it" — has no trace in `914bc89d`, whose diff is
the 401-line test file and nothing else. Task 15 is marked `[x] done` against a verification line that
says "Interactive/session-dependent", which is honest but is not the same as satisfied.

So the requirement written specifically to prove the feature is wired is itself two-thirds proven. It is
worth being precise about what remains: the *scoped brief path* is proven live end to end. What is
unproven is that a reviewer handed that brief actually writes the dispositions it demands. That is a
prose-adherence question, and this review — a full-mode dispatch — cannot answer it.

**Stage 1 result: 16 PASS, 4 PARTIAL, 0 FAIL.** Stage 2 runs.

---

## Stage 2 — Code quality

**Plan verification steps — one cannot pass as written.** Task 14's verification says
`uv run python scripts/ratchet_refs.py` prints a `pinned` line naming the prompts directory. It cannot:
the bare invocation routes to `check()` (`ratchet_refs.py:227`), which prints only
`reference-size ratchet: all directories within their pins`. The `pinned` line is emitted by
`ratchet_write`, reachable only via `--write`. Confirmed by reading both branches. The orchestrator's
finding #3 is correct; the substance is covered by `test_pipeline_prompts_enumerated_and_pinned`
instead, so nothing is unverified — the plan's command is simply wrong. Every other task's verification
command I checked (1, 2, 3, 5, 6, 7, 8, 13) executes and reports as claimed.

**The fence defect and its fix (orchestrator finding #2).** Verified independently: `parse_verdict_block`
(`review_brief.py:106`) and `review_dispatch.parse_verdict` (`:207`) use byte-identical regexes requiring
```` ```json ````, while `skills/build/references/review.md` prescribed a bare ```` ``` ```` fence — and
had done so since before this lifecycle (`4c61e56c^:25`). The fix in `02cd9f43` is correct and minimal,
and it paid its 4 bytes by trimming the same paragraph rather than raising the pin.

On whether requirement 12's restructure should have caught it: **yes, and the plan actively worked
against it.** Task 13's context instructed "Retain: … explicitly — the Verdict JSON fenced block at lines
25–27 (143 B)", framing the block as a byte to preserve rather than a contract to reconcile with the
parser task 1 had just written. The builder retained it verbatim, correctly. The defect is a plan
defect, not a builder defect. It was caught in-lifecycle and is now pinned by
`test_shipped_prose_prescribes_the_fence_the_parser_requires`, which asserts the info string equals
`"json"` and states the failure mode in its message. Good recovery.

**Naming and pattern consistency.** The module mirrors `stage_artifacts.py` as the plan specified — pure
helpers, `_`-prefixed IO layer, thin `main(argv) -> int`. `_read_events` reuses the tolerant-reader
convention from `counters.py`/`common.py`. `log_event_at` is the correct shared writer. The
inward-only import direction is stated in both modules' docstrings and enforced by the plan's grep. No
`${CLAUDE_SKILL_DIR}` token in the brief; `cortex-check-skill-path --audit`, `cortex-check-contract`
and `cortex-adr-citation-audit` all exit 0.

**PARTIAL — heading case does not match between the brief's own sections and the sections it demands.**
The brief renders its sections as `## Prior-cycle checklist` and `## Out-of-scope findings` while
instructing the reviewer to write `## Prior-Cycle Checklist` and `## Out-of-Scope Findings`. A reviewer
mirroring the headings it can see writes the lowercase form. Nothing parses these today, so the impact
is zero right now — but this feature's entire premise is that a re-review can quietly stop covering
things, and an inconsistent heading is exactly how a future `## Out-of-Scope Findings` presence check
would silently miss. Cheap to align.

**PARTIAL — a degraded dispatch records `mode: "rework"` for a full brief.** `_record_baseline`
(`main` `:624`) runs before the degrade branches, so a dispatch that falls through to `_degrade` writes
`{"event": "review_dispatched", "mode": "rework", …}` while serving an unscoped brief. Only
`baseline_sha` is ever read back, so nothing breaks — but the row is the only durable record of what a
dispatch did, and it misdescribes the degraded case. Recording the mode actually served (or a third
`degraded` value) would make the log answer "did any rework silently degrade?", which is a question this
feature's fail-open design makes worth asking.

**Note — `parse_carried_forward` closes a block on any `#`-initial line** (`:159-161`), including a
comment inside a fenced code block in the prior review. Tolerable for the shape reviews actually take,
and the failure direction is safe (an item is missed from the re-verification list rather than
fabricated into it).

**Out-of-scope finding — `ratchet_refs.ratchet_write` destroys `# raised:` provenance.** Both the seed
branch (`:189`) and the lower branch (`:192`) do `pin_path.write_text(f"{measured}\n")`, dropping every
annotated raise line. The evidence that this already bites: `a6a4478d`'s commit body records that the
implementer hand-edited `skills/build/references/size-pin.txt` specifically because "the ratchet's
`--write` path rewrites the file as a bare number and would drop them." So `just ratchet-refs` — the
affordance the ratchet's own docstring calls the expected way to lower a pin — silently discards the
audit trail that makes a raise legitimate.

I do **not** think task 14 should have fixed it. Requirement 16 asks only for enumeration and a pin file,
the defect predates this feature, and widening task 14 into `ratchet_write` would have put an unrelated
behavior change inside a phase-3 parity task. But it is now materially worse than before: the feature
added a fourteenth pinned directory and a documented hand-edit workaround that lives only in a commit
message. It belongs in a ticket, not in this lifecycle. Confirming orchestrator finding #5 as real,
correctly deferred, and worth filing.

**Note — orchestrator finding #4 is a non-issue.** `review_no_artifact` appears in no Python source at
all; the constant is `REVIEW_NO_ARTIFACT` in `cortex_command/overnight/constants.py:26`, and task 7's
plan context was citing ADR-0015's constraint language rather than making a file claim. The constraint
held: neither `could_not_run` (`review_dispatch.py:182`) nor the cause class moved. Nothing was lost.

**Systematic check for criteria that pass on the unmodified repo**, as instructed. I checked all twenty
against `4c61e56c^`. Four do not discriminate:

- **17** — both greps passed before the lifecycle began. Unimplemented and undetectable. Reported above.
- **12** — the directory measured *exactly* 57964 at lifecycle start, so "≤ 57964" and "no new
  `# raised:` line" were both already true. The substance (the pin lowering) is real but uncommanded.
- **9** — "the existing parity test passes at HEAD" is stated as a no-op; the plan's Risks section says
  so outright.
- **3** — a no-regression guard, inherently true before the change. Legitimate as an invariant, but not
  evidence of the feature.

The remaining sixteen genuinely discriminate. Requirement 20 does close the wiring hole it was written
for, for the brief-emission half — see its rating for the part it does not close.

---

## Requirements Drift

- **State**: `detected`
- **Findings**:
  - `project.md`'s Architectural Constraints scopes the reference-size ratchet to `skills/*/references/`
    ("targeting ~10x reduction of `skills/*/references/` — enforced by the down-only reference-size
    ratchet"). Requirement 16 extended the enumeration to `cortex_command/pipeline/prompts/`, which is
    not a `references/` directory and is not shipped prose. The gate's governing statement no longer
    describes what the gate measures.
  - The `## Architectural Constraints` "CLI/plugin version contract" and served-verb entries do not
    capture that the reviewer brief's *shape* is now a wheel↔prose contract governed by
    `PROTOCOL_VERSION`. ADR-0035 and `protocol.py` record it, and `project.md` back-points to ADRs by
    convention — so this one is borderline. Logging it per the brief's instruction to prefer `detected`
    when uncertain; a reviewer who judges the ADR back-pointer sufficient should decline the second
    suggested update.
- **Update needed**: `cortex/requirements/project.md`

## Suggested Requirements Update

- **File**: `cortex/requirements/project.md`
- **Section**: `## Architectural Constraints`
- **Content**:
```
- **Ratchet scope extends past `references/`**: the down-only reference-size ratchet also pins `cortex_command/pipeline/prompts/`, which is review-shaping prose loaded like reference prose but served by the wheel rather than shipped in a skill. Named evidence (#455): the overnight review template was the one unmeasured place output-shape prescription could accumulate while `skills/build/references/` sat at its ceiling. → `scripts/ratchet_refs.py:enumerate_reference_dirs`.
```

- **File**: `cortex/requirements/project.md`
- **Section**: `## Architectural Constraints`
- **Content**:
```
- **The reviewer brief is a protocol-governed served surface**: `cortex-lifecycle-review-brief` emits the review phase's output-shape prescription for both the interactive prose and the overnight pipeline, so a brief-shape change the prose depends on moves `PROTOCOL_VERSION` and `skills/build/references/protocol-expectation.txt` in the same commit. → ADR-0035.
```

---

## Verdict rationale

No requirement is broken and no shipped behavior is wrong. The core of the feature — the verb, the
archive, the fail-open contract, the byte budget, the overnight rewiring, the ratchet parity — is
implemented carefully and tested better than the spec demanded in several places (the runtime fence
coupling in the end-to-end test, the non-empty-range assertion on the SHA, the missing-pin test over a
real copy). The 781 bytes of headroom mean none of the additions the spec warned would be dropped under
byte pressure was dropped.

I am returning CHANGES_REQUESTED rather than APPROVED on four items, two of which are substantive:

Requirement 17 was never implemented and its acceptance could never have detected that. The end state is
correct by accident of an unrelated commit, the task is marked done, and nothing guards it. This is the
third documented instance of this failure class in this repo; leaving it unremarked in a completed
lifecycle is how the record stays wrong.

Requirements 18 and 20's disposition clause are unevidenced, and — this is the part that decides the
verdict — they are evidenceable *only* by a cycle-2 review of this very lifecycle. The plan said so
explicitly and built the capture rig for it. Approving now closes the lifecycle with the one criterion
written to prove the feature is wired left two-thirds proven, and permanently forecloses the evidence,
because there is no other in-flight rework to harvest it from. A rework cycle here costs one review and
produces exactly the artifact requirement 20 asks for, on the real path, from a real reviewer. That is
the cheapest correct outcome available and it is available only now.

The other two items are small: the heading-case mismatch and the degraded-dispatch mode field, both
one-line fixes worth folding into the same rework.

Not blocking, for the record: the `ratchet_refs` provenance bug should be filed as its own ticket rather
than fixed here, and the `cortex/requirements/lifecycle.md` gap (#469) means this feature's area-level
requirements went unassessed by anyone.

```json
{"verdict": "CHANGES_REQUESTED", "cycle": 1, "issues": ["Requirement 17 was not implemented by this feature and its acceptance criteria are non-falsifiable. Verified at 4c61e56c^ (the commit before this lifecycle): `grep 'regex matches in review.md' cortex_command/common.py` already exited 1, and the replacement docstring line naming `review_verdict` rows was already present at common.py:479-480. The stale string was removed by the unrelated commit 2a4fb715. common.py appears in none of this lifecycle's sixteen commits, and task 3's commit 64aa2f18 touched only stage_artifacts.py and tests/test_stage_artifacts.py, yet task 3 is marked done. Fix: either correct plan.md task 3's status and record that requirement 17 was satisfied out-of-lifecycle, or add a guard so the corrected docstring cannot silently regress. Do not re-edit common.py to manufacture a diff.", "Requirement 20's third acceptance clause is unevidenced, and requirement 18's acceptance is stated over the same missing artifact. test_review_brief_end_to_end.py closes clauses 1 and 2 well, but 'the second review's review.md contains a disposition for each' needs a real reviewer on a real cycle-2. cortex/lifecycle/a-rework-re-review-re-reads/captures/ does not exist, and commit 914bc89d contains only the 401-line test file - the plan's own pre-step (write a throwaway capture, confirm _capture_files enumerates it into staged_paths, delete it) has no trace. Fix: this rework cycle produces the evidence. At cycle-2 dispatch, record the emitted scoped brief and the resulting review.md under captures/ per plan task 15b, and validate the discarded sample first as the plan instructs.", "The brief's own section headings do not match the headings it instructs the reviewer to write: cortex_command/lifecycle/review_brief.py:345 renders `## Prior-cycle checklist` and :358 renders `## Out-of-scope findings`, while the demanded sections are `## Prior-Cycle Checklist` and `## Out-of-Scope Findings`. A reviewer mirroring the casing it can see writes the wrong heading. Nothing parses these today, so impact is currently zero - but a future presence check on `## Out-of-Scope Findings` would silently miss, which is precisely the quiet-loss-of-coverage this feature exists to prevent. Fix: align the brief's headings to the demanded form.", "A degraded dispatch records a mode that misdescribes what it served. In review_brief.main, _record_baseline runs at :624 before the _degrade branches at :648/:654/:666/:673, so a dispatch that falls through to a full brief still writes {\"event\": \"review_dispatched\", \"mode\": \"rework\"}. Only baseline_sha is read back so nothing breaks, but the row is the only durable record of what a dispatch did, and the fail-open design makes 'did any rework silently degrade to a full review?' a question worth being able to answer from events.log. Fix: record the mode actually served, or a distinct `degraded` value."], "requirements_drift": "detected"}
```
