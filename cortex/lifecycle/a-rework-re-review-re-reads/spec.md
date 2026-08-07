# Specification: a-rework-re-review-re-reads

Ticket #455 · tier `complex` · criticality `high`

## Problem Statement

A review that runs after a CHANGES_REQUESTED rework is specified identically to the first one: read every
requirement in the spec, rate each PASS/FAIL/PARTIAL. But its actual question is narrower — did the flagged
issues close, and did any fix break something — and its input is a bounded diff. Measured across five repos,
56 of 511 reviewed lifecycles (11%; 7% in cortex-command, 17% in wild-light) reach a re-review, and today
every one of them pays a full-spec re-read or gets hand-scoped on the fly by an orchestrator improvising
what to skip. The improvisation is the real cost: nothing records what was skipped, so a re-review can
quietly stop covering things. This makes the scoped mode supported and stated, and — because the same
restructure moves output-shape prescription out of always-read prose — pays for itself in bytes rather than
adding to a reference directory that is already at its ratchet ceiling.

## Phases

Each phase must ship behavior that is **live** on completion. An earlier decomposition split the store, the
verb, and the prose that calls them into three phases; that was wrong — the archive had no caller until the
prose landed, so Phases 1–2 would have shipped a copy routine nothing ran and a verb nothing invoked, with
every phase's own criteria passing. Producer and consumer now land together.

- **Phase 1: Scoped interactive review** — the store, the verb, and the `review.md` restructure that calls
  them, shipped as one unit. This is the ticket's integration point and is atomic by nature.
- **Phase 2: Overnight adoption** — the overnight path builds its cycle-2 prompt from the same brief.
- **Phase 3: Ratchet parity** — the prompts directory gains a size pin so review-shaping prose has no
  unmeasured hiding place.

## Requirements

1. **Prior review is archived, not destroyed**: before a review artifact is written for cycle N, any existing
   `cortex/lifecycle/{feature}/review.md` is **copied** to `cortex/lifecycle/{feature}/review-cycle-{N-1}.md`.
   Copy, never move — `review.md` must exist continuously, because a window in which it is absent makes phase
   detection report plain `review` instead of `implement-rework` (`common.py:392-410` falls through to the
   plan-based step when the file is missing).

   **The caller is the brief verb's CLI entry point**, which the review phase invokes at dispatch. The archive
   is not a free-floating step: the verb archives-then-emits in one invocation, so the copy cannot be forgotten
   or silently dropped under byte pressure, and no separate call has to be added to `review.md`. Overnight is
   unaffected because it imports the brief-building function directly (requirement 14) rather than going
   through the CLI entry point — it holds the prior issues in process (`review_dispatch.py:401`) and is never
   forced through a file it does not need. Acceptance: after the archive step, `review-cycle-1.md` is
   byte-identical to the pre-step `review.md` (**true**) and `review.md` still exists (**true**); invoking the
   CLI entry point on a lifecycle with an existing `review.md` produces the archive without any other command
   being run (**true**). **Phase**: Scoped interactive review

2. **The archive never overwrites an existing archive, and is safe to retry**: if
   `review-cycle-{N-1}.md` already exists the step is a no-op. Copy semantics plus no-clobber makes retry after
   a crash — at any point, including after a partial cycle-N write — converge without needing to distinguish
   "archive already taken" from "cycle-N write never completed". Acceptance: running the step twice produces the
   same tree as running it once (`find cortex/lifecycle/{feature} -type f | sort` plus per-file checksums match,
   **true**); running it against a pre-existing archive leaves that archive's checksum unchanged (**true**).
   **Phase**: Scoped interactive review

3. **The current cycle stays at `review.md`**: phase detection reads that exact path
   (`common.py:390-410` takes `verdict_matches[-1]`, and `_stat_key(review.md)` at `:467` is a memoization
   key). Acceptance: `cortex-lifecycle-state --feature {feature}` and `detect_lifecycle_phase` return the same
   phase before and after an archive step, with archives present. **Phase**: Scoped interactive review

4. **Archived reviews are committed**: `cortex_command/lifecycle/stage_artifacts.py`'s explicit allowlist is
   extended to include `review-cycle-*.md`. Acceptance: after a rework cycle,
   `git status --porcelain cortex/lifecycle/{feature}/` shows no untracked `review-cycle-*.md`, and
   `git log --name-only` for the completing commit lists it. Grounding file:
   `cortex_command/lifecycle/stage_artifacts.py` (module docstring §"Per-phase staged set"). **Phase**: Scoped interactive review

5. **A brief verb exists and serves both modes**: a new CLI verb emits the reviewer brief, selecting full or
   rework-scoped on `rework_cycles >= 1`. Acceptance: invoked on a lifecycle with zero CHANGES_REQUESTED rows
   it emits the full brief; on one with ≥1 it emits the scoped brief; both exit 0 and both name the review
   artifact path. **Phase**: Scoped interactive review

6. **The discriminant is the existing counter**: the verb derives mode from `count_rework_cycles`
   (`cortex_command/lifecycle/counters.py:53`), not from `common.py`'s reduced `cycle`. Acceptance: a lifecycle
   whose events.log has one CHANGES_REQUESTED row yields the rework brief even though the reduced `cycle`
   reads 1. **Phase**: Scoped interactive review

7. **The scoped brief carries the checklist, the reading scope, and the baseline decision**: it names each
   issue from the prior cycle, states the commit range to read, and states whether the test baseline is reused
   or re-run. **On the interactive path the checklist is read from `review-cycle-{N-1}.md`** — the archive
   written by requirement 1, which is otherwise a file with no reader. On the overnight path it comes from the
   in-process `issues` list. Acceptance: on a fixture lifecycle with a 3-issue prior verdict, the emitted brief
   contains all three issue texts, a `git diff`-expressible range, and exactly one of "reuse baseline" /
   "re-run" (**true**); with the archive deleted and no in-process issues, the verb takes requirement 19's
   fail-open path rather than emitting an empty checklist (**true**). **Phase**: Scoped interactive review

8. **The brief states that scoping bounds reading, never concluding**, and the output shape it prescribes
   includes a mandatory findings section for anything outside the checklist. Acceptance: the emitted rework
   brief contains both the bounding statement and a required out-of-scope findings heading; a review that
   found nothing outside the checklist must still state that affirmatively rather than omit the section.
   **Phase**: Scoped interactive review

9. **The brief's shape is protocol-governed**: the brief is served by the wheel and consumed by plugin prose,
   so a shape change the prose depends on moves `PROTOCOL_VERSION` (`cortex_command/lifecycle/protocol.py`)
   and the matching range in `skills/build/references/protocol-expectation.txt` in the same commit.
   Acceptance: the existing parity test asserting `PROTOCOL_VERSION ∈ [min, max]` passes at HEAD.
   **Phase**: Scoped interactive review

10. **Carry-forward is stated by reference, with its condition, and is depth-bounded**: a requirement rated in
    the *immediately preceding* cycle and untouched by the rework is reported as carried forward — naming the
    cycle and the condition under which the rating still holds — rather than silently re-asserted as a fresh
    PASS. A rating may be carried forward **once**; a requirement whose rating would be carried a second
    consecutive time must be re-verified instead. Without that bound a cycle-3 review can carry a cycle-2
    carry-forward of a cycle-1 rating, and the line item is never re-read by anyone. Acceptance: the emitted
    brief prescribes the form and states the once-only bound (**true**); a fixture whose prior review already
    marks an item carried-forward produces a brief listing that item as requiring re-verification (**true**).
    **Phase**: Scoped interactive review

11. **The test-baseline decision is stated, not left to judgment**: re-run the configured test command iff
    `git diff <baseline_sha>..<head> --name-only` reports any path other than
    `cortex/lifecycle/{feature}/*.md`; otherwise reuse the baseline. The exemption is deliberately narrow —
    **`events.log` is not exempt**, because `tests/test_clarify_critic_alignment_integration.py`
    (`test_post_migration_clarify_critic_events_are_jsonl`) walks the real `cortex/lifecycle/*/events.log` tree
    and asserts format compliance, so a rework confined to a lifecycle directory can still turn a live test red.
    Two-dot `..` is correct here and not the three-dot trap: the baseline is always an ancestor of HEAD on a
    rework, so `..` and `...` are equivalent, and `..` says what is meant. Acceptance: a diff touching only
    `cortex/lifecycle/{feature}/plan.md` yields "reuse" (**true**); a diff touching
    `cortex/lifecycle/{feature}/events.log` yields "re-run" (**true**); any source path yields "re-run"
    (**true**). **Phase**: Scoped interactive review

12. **`review.md` calls the verb and shrinks**: §§1–2 are restructured so the *narrative* output-shape
    prescription (stage definitions, drift-section format) lives in the verb's brief and the prose keeps
    control flow. **The Verdict JSON block itself stays in prose** — see requirement 19; it is the contract
    `parse_verdict` depends on and must not be reachable only through a subprocess. Acceptance:
    `python3 -c "import sys;sys.path.insert(0,'scripts');import ratchet_refs;from pathlib import Path;print(ratchet_refs.measure(Path('skills/build/references')))"`
    reports **≤ 57964**, and `skills/build/references/size-pin.txt` gains **no** new `# raised:` line. The
    mirror's pin must match: `plugins/cortex-core/skills/build/references/size-pin.txt` is the one mirror path
    staged by hand, and `tests/test_reference_size_ratchet.py` must be green for both directories.

    **The budget must be counted against every addition, not just the verb call.** Phase 1 adds four things to
    this prose — the verb call, the branch on the discriminant, requirement 19's fail-open control flow, and
    requirement 13's baseline-SHA capture — funded by one deletion (the narrative stage and drift-format
    prescription), with the Verdict JSON block explicitly retained. Measured ceiling on what is movable: §2 is
    2099 bytes of which the retained Verdict JSON block is 143, so **at most 1956 bytes** can be reclaimed, and
    the genuinely-movable narrative is less than that. **If the arithmetic does not close, the resolution is a
    compensating trim elsewhere in the directory — never dropping a requirement, and never a pin raise.** An
    implementer who cannot close it must stop and surface the shortfall rather than silently omitting the
    cheapest addition; the archive call is the one with no other test guarding it, and is therefore the one at
    risk.
    **Phase**: Scoped interactive review

13. **The interactive path captures a baseline SHA** so requirement 11 has its input. A deterministic rule fed
    by an inspection-verified input is deterministic only in fixtures, so the capture is machine-checkable:
    the emitted brief names a concrete 40-hex commit SHA. Acceptance: the brief emitted for a rework matches
    `\b[0-9a-f]{40}\b` (**true**), and that SHA resolves — `git cat-file -e <sha>^{commit}` exits 0 (**true**).
    **Phase**: Scoped interactive review

14. **Overnight uses the same verb**: `cortex_command/pipeline/review_dispatch.py`'s cycle-2 construction
    (currently `:596-609`, which reloads the cycle-1 template and appends a sentence) instead builds its
    prompt from the shared brief, in-process. Acceptance: the cycle-2 prompt contains the prior cycle's issue
    texts; today it contains none despite `issues` being in scope at that line. **Phase**: Overnight adoption

15. **The overnight template stops biasing the reported cycle**: `cortex_command/pipeline/prompts/review.md:96`'s
    worked Verdict JSON example must not hardcode a cycle a rework reviewer would copy. Acceptance: grep of the
    template shows no literal `"cycle": 1` in an example a cycle-2 reviewer is shown. **Phase**: Overnight adoption

16. **The prompts directory gains ratchet parity**: seed `cortex_command/pipeline/prompts/size-pin.txt` and
    extend `scripts/ratchet_refs.py`'s directory enumeration to cover it. Acceptance:
    `tests/test_reference_size_ratchet.py` reports the prompts directory as pinned and within its pin; removing
    the pin file makes the suite fail. **Phase**: Ratchet parity

17. **`common.py`'s stale docstring is corrected**: `:462-463` still describes `cycle` as "the count of
    `verdict` regex matches in review.md"; the implementation counts events (`:355`). Acceptance: in
    `cortex_command/common.py`, the substring `regex matches in review.md` is **absent** (grep exit 1) and a
    docstring line naming `review_verdict` events as what `cycle` counts is **present** (grep exit 0).
    **Phase**: Scoped interactive review

18. **Every checklist issue gets a disposition**: the rework review records an explicit disposition for each
    issue on the prior cycle's checklist, so no checklist item is silently dropped. This is also what keeps a
    re-review from re-emitting findings the rework already fixed — the failure mode documented in Qodo/PR-Agent,
    where naive re-review produced duplicate-suggestion spam until dedup was built. Acceptance: on a fixture
    lifecycle with a 3-issue prior verdict, `cortex/lifecycle/{feature}/review.md` contains three dispositions,
    one per prior issue (**true**), and none of those three issue texts appears under the new-problems section
    (**false**). **Phase**: Scoped interactive review

19. **The verb fails open to a full review, never to an empty checklist**: if the verb is absent, errors, or
    cannot read the prior cycle's issues, the review proceeds as a **full** review and the failure is surfaced.
    An empty checklist must never be emitted as if it were a scoped brief — `parse_verdict`'s existing failure
    sentinel is `{"verdict": "ERROR", "cycle": 0, "issues": []}` (`review_dispatch.py:177`), so an empty
    `issues` array is indistinguishable from "the prior cycle found nothing", and a reviewer handed that has no
    signal to widen its reading. The verb's degraded return must be distinguishable from a legitimately empty
    checklist. This matters because the wheel and the plugin are versioned separately: a plugin newer than the
    installed wheel is a real state, not a hypothetical. Acceptance: with the verb absent from `PATH`, the review
    phase runs a full review and reports the degradation (**true**), and no scoped brief is emitted (**false**);
    with the prior issues unreadable, the emitted output names the read failure rather than an empty list
    (**true**). **Phase**: Scoped interactive review

20. **One criterion asserts the feature is wired, not merely present**: every other requirement here certifies
    that an artifact exists and behaves correctly in isolation — the copy function, the verb against fixtures,
    a byte count. None of them would fail if the scoped path never actually ran. This one closes that: a real
    interactive rework, dispatched end to end, must produce a scoped brief built from an archived prior cycle.
    Acceptance: on a lifecycle driven through CHANGES_REQUESTED → rework → second review,
    `cortex/lifecycle/{feature}/review-cycle-1.md` exists (**true**), the second review's brief contains at
    least one issue text from the first cycle's verdict (**true**), and the second review's `review.md`
    contains a disposition for each (**true**). **Phase**: Scoped interactive review

## Non-Requirements

- **Changing `cortex_command/common.py:355`'s semantics.** It is display-only; the rework cap routes on the
  reviewer's self-reported cycle via `_route_target`. `tests/test_lifecycle_auto_advance.py:126-145` pins the
  current count semantics, and five golden-pinned display consumers read it. Out of scope by decision.
- **Unifying the interactive and overnight cycle-2 outcomes.** Interactive escalates; overnight defers to
  morning triage (`cortex/requirements/pipeline.md` § Post-Merge Review). That divergence is deliberate and is
  preserved.
- **Emitting any `review_verdict` row at CHANGES_REQUESTED on the overnight path.** Would make morning
  crash-recovery fabricate an APPROVED completion (see Edge Cases).
- **Putting the issues array in events.log**, under `review_verdict` or a new event name. Measured at 5,672
  bytes against a 7,056-byte log; events.log is parsed per line on every phase detection, statusline render,
  dashboard poll and hook.
- **Resolving the escalation dead end.** `escalated` has no verb to land operator direction in — that is #454,
  and it is interactive-only. **This is the strongest argument for holding Phase 1**: the ticket's
  own Edge says a scoped review is a rubber stamp unless it can still escalate outside the checklist, and
  escalation is the interactive path's only channel for "genuine new problem found". It is judged non-blocking
  because escalation *works* — it transitions and halts with findings presented, and the corpus shows two
  operators resolving it out-of-band successfully — so the gap is degraded ergonomics, not a lost signal. But
  #454 should land before or alongside Phase 1, and if it slips, that is a reason to hold Phase 1 rather than
  ship into it. Note the re-phasing sharpens this: Phase 1 is now the whole interactive feature, so there is no
  longer a partial state to ship while waiting.
- **A recovery path for a reviewer that wrote no artifact at all.** Split to #457 at Clarify. Supersedes the
  ticket body's Edges bullet 5.
- **Fixing the requirements-loader trigger gap.** `project.md:97`'s Conditional Loading vocabulary lacks
  "review"/"rework", so `cortex/requirements/pipeline.md` is silently skipped for every review-tagged ticket.
  Real and worth fixing, but it affects every lifecycle rather than this one. To be filed separately.

## Edge Cases

- **Prior cycle's issues are missing, empty, unreadable, or the verb is absent**: covered by requirement 19 —
  full review, failure surfaced, never a scoped brief on degraded input.
- **A crash between the archive copy and the cycle-N write**: `review.md` is never absent (copy, not move), so
  phase detection keeps reporting `implement-rework` throughout. This is why requirement 1 forbids a rename.
- **The archive is untracked when a `git clean -fd`, fresh clone, or another machine picks up the lifecycle**:
  requirement 4 puts it in the staged allowlist for exactly this reason. Without it the interactive path — the
  only consumer that needs the file at all — silently regresses to working within one continuous session.
- **Wheel/prose version skew**: a served protocol outside `protocol-expectation.txt`'s range halts the loop with
  its existing remediation. Note `cortex-*` on PATH is the released wheel, not the working tree.
- **A crash between cycle 1 and cycle 2 on the overnight path**: must still leave no `review_verdict` row, so
  `advance_lifecycle.py:140-155` `_has_real_review_verdict` cannot mistake a rejected feature for a reviewed one
  and synthesize an APPROVED completion.
- **A rework that touches only test files**: requirement 11 re-runs (tests are outside
  `cortex/lifecycle/{feature}/*.md`). Deliberate — a fix agent editing tests without touching source is itself
  worth a full check.
- **A rework that touches only generated files or lockfiles**: re-runs under requirement 11. Accepted as a
  false-positive-toward-safety, matching Test Impact Analysis's fallback-to-full-suite convention.
- **Review reaches cycle 3**: observed twice in wild-light. Archives accumulate as `review-cycle-1.md`,
  `review-cycle-2.md`; the checklist is built from the immediately-prior cycle.
- **Reviewer disagrees with a carried-forward rating**: it may re-open and re-rate. Carry-forward is a default
  that saves reading, never a constraint on conclusions.

## Changes to Existing Behavior

- **MODIFIED** — `skills/build/references/review.md` §§1–2: output-shape prescription moves into the verb's
  brief; prose keeps control flow. Net byte change must be ≤ 0 for the directory.
- **MODIFIED** — `cortex_command/pipeline/review_dispatch.py:596-609`: cycle-2 prompt built from the shared
  brief instead of the cycle-1 template plus an appended sentence.
- **MODIFIED** — `cortex_command/pipeline/prompts/review.md`: worked Verdict JSON example no longer biases a
  rework reviewer's self-reported cycle.
- **MODIFIED** — `cortex_command/lifecycle/stage_artifacts.py`: allowlist gains `review-cycle-*.md`.
- **MODIFIED** — `scripts/ratchet_refs.py`: directory enumeration covers `cortex_command/pipeline/prompts/`.
- **ADDED** — the brief-emitting CLI verb, its `bin/` wrapper, and its tests. It has two entry points: a CLI
  entry point (interactive) that archives the prior cycle then emits the brief, and an importable
  brief-building function (overnight) that emits without archiving.
- **ADDED** — `cortex_command/pipeline/prompts/size-pin.txt`.
- **ADDED** — `cortex/lifecycle/{feature}/review-cycle-{N}.md` as a committed artifact class.
- **REMOVED** — nothing.

## Technical Constraints

- `skills/build/references/` measures **57964 against a pin of 57964** — zero headroom. `measure()` counts all
  regular files, not just `.md`. Any growth fails `tests/test_reference_size_ratchet.py`.
- Dual-source: edit canonical `skills/` only; `plugins/cortex-core/` mirrors are rebuilt from staged blobs by
  the pre-commit hook. Editing `skills/*/references/` needs ratchet-refs → build-plugin → ratchet-refs, and the
  mirror's `size-pin.txt` is the one mirror path to stage by hand.
- ADR-0009: no reference region reaching a subagent may carry a raw `${CLAUDE_SKILL_DIR}` token; resolve in the
  SKILL.md body and propagate absolute paths. Enforced by `cortex-check-skill-path`.
- ADR-0015 (accepted): the `DispatchResult.success` / `could_not_run` discriminants and the `review_no_artifact`
  cause class are load-bearing for the systemic breaker and must not move.
- `cortex_command/common.py` is lifecycle-gated by CLAUDE.md; `cortex_command/pipeline/**` is not.
- Gates to clear: reference-size ratchet, dual-source and plugin-mirror parity, skill-path lint, kept-pauses
  parity (if any `<!-- pause: -->` marker moves), lifecycle reverse-golden, phase parity, transition-table
  closure/completeness, transition-table describe-golden.
- `docs/lifecycle-transition-table.md` is generated — regenerate via `cortex-lifecycle-describe --write`, never
  hand-edit.

## Open Decisions

None. The two forks raised at spec time (verb scope; whether to close the unratcheted-prompts loophole here)
were both resolved by the operator in favor of the broader option, and are recorded in Requirements 5 and 16.

## Proposed ADR

### Proposed ADR: 0030-reviewer-brief-emitted-by-verb-not-reference-prose

**Context.** The review phase's output shape — stage definitions, the Requirements Drift section format, the
Verdict JSON schema — has always lived in `skills/build/references/review.md`, prose re-read in full on every
review dispatch. That directory is at its down-only ratchet ceiling with zero headroom, and a second,
independent copy of the same specification lives in `cortex_command/pipeline/prompts/review.md` for the
overnight path, where it has already drifted (the overnight cycle-2 path appends a sentence rather than scoping,
and never passes the prior issues).

**Decision.** A wheel-side verb emits the reviewer brief for both modes and both consumers; the prose keeps only
control flow and the call.

**Trade-off.** Gains: one source of truth across two consumers that have already drifted; the byte budget the
restructure needs; and removal of a perverse incentive to hide prose in the unmeasured prompts directory. Costs:
it tightens wheel↔prose coupling — today a stale wheel cannot change what a reviewer is told, afterwards it can
— so the brief's shape becomes protocol-governed and a shape change is a `PROTOCOL_VERSION` floor bump. It also
makes the review's instructions less greppable, since a reader of `review.md` will no longer find the output
shape there. Hard to reverse: unwinding means restoring deleted prose into a directory with no bytes to spare
and moving the protocol floor back.
