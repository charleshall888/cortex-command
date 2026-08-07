# Review: review-has-no-recovery-path-for — cycle 1

**Mode**: full · **Tier**: moderate · **Criticality**: high
**Stages run**: Stage 1 (spec compliance) only — Stage 2 is complex-tier-only and this feature is `moderate`.
**Test baseline consumed** (not re-run): full suite at `71a71975` → 4662 passed, 19 skipped, 1 xfailed, 0 failures.

Every acceptance criterion below was executed against the working tree rather than read off the spec.
The live CLI checks ran through `uv run python -m cortex_command.lifecycle.register_artifact` in a
scratchpad fixture (never the `cortex-*` binstub, which serves the installed wheel).

## Stage 1 — Spec compliance

### R1 — Refuse to register a missing artifact — **PASS**

Executed: fixture with `cortex/lifecycle/f/index.md` (`artifacts: []`) and no `review.md`.

```
{"state":"error","message":"artifact file does not exist or is empty: …/cortex/lifecycle/f/review.md","protocol":3}
```

`cmp` of the index before/after exits 0 — byte-identical. The refusal returns at
`register_artifact.py:120-124`, before the `_ARTIFACTS_RE` rewrite and before any `atomic_write`, so
"writes nothing" is structural rather than incidental. The message names the resolved absolute path as
required.

### R2 — Treat an empty artifact as missing — **PASS**

Executed: same fixture with `touch review.md`. Same `"state":"error"`, index still byte-identical
(`cmp` exit 0). The predicate at `:117` is `stat().st_size == 0`, so zero-byte and absent share one arm
— matching the `research-phase.md:23` "exists and is non-empty" idiom the spec cites (verified: that
line still carries the phrase).

### R3 — Resolve the artifact beside `index.md` — **PASS**

`artifact_path = path.parent / f"{artifact}.md"` at `:115`, where `path` is whichever index path
resolved — the injected `index_path` when given, else the root-derived one. Both halves of the
discriminating acceptance criterion are covered by
`test_artifact_check_anchors_to_index_parent_not_feature_slug`
(`test_register_artifact.py:221-260`): Case A puts the index in `unrelated-dir-name/` with the artifact
beside it → `registered`; Case B leaves the artifact only under the feature-derived
`cortex/lifecycle/feat/` path → `error`. Green in the baseline.

**Worktree hazard (spec Edge Cases, "the single most likely source of a false refusal") — closed, and
by construction rather than by assertion.** I checked both ends rather than trusting the plan's
reasoning. `review_brief.main()` resolves its root with `_resolve_user_project_root_from_cwd()`
(`review_brief.py:607`) and hands the reviewer an **absolute, `.resolve()`-d** `review.md` path
(`:618`). `register_artifact` derives the checked path from the index path resolved by the *same*
function (`:105`). Writer and checker therefore agree for any cwd, including a branch-mode worktree,
because neither re-derives a root independently. Residual (observation, not an issue): the two agree
only while §2 and §3 run from one cwd — an orchestrator that ran `review-brief` inside a worktree and
`register-artifact` after leaving it would diverge. That is a generic property of every cwd-resolved
lifecycle verb, not something this change introduced.

### R4 — No new state value, no protocol bump — **PASS**

- `register_artifact.py:64` — `KNOWN_STATES = ("registered", "already-present", "no-index", "error")`, unchanged; the diff touches no line of it.
- `protocol.py:52` — `PROTOCOL_VERSION = 3`.
- `skills/build/references/protocol-expectation.txt` — `min=3`, `max=3`.
- The closed-set assertion survives verbatim at `test_register_artifact.py:302-303`
  (`seen == {"registered", "already-present", "no-index", "error"}` and `seen <= set(ra.KNOWN_STATES)`),
  and the diff shows no edit to that test. `tests/test_protocol_parity.py` green in the baseline.

Worth recording against `lifecycle.md:101` (ADR-0035): that clause moves `PROTOCOL_VERSION` only when
the **brief shape** the prose depends on changes. This change edits §2's writer list and §3's
processing prose in `skills/build/references/review.md`; the Verdict contract block and everything
`review_brief.py` emits are untouched. No bump was owed.

### R5 — Exit code contract preserved — **PASS**

`main()` returns 0 on the sole return path (`:207`); the never-crash net at `:203-204` is unchanged.
Executed live: the R1 refusal, the R2 refusal, the happy path, and the R8 `no-index` case all exit 0.
Satisfies `lifecycle.md:88`'s never-crash-verb requirement (`{"state": …}` envelope at exit 0) — which
the new arm honours, since it returns a dict rather than raising.

### R6 — The overnight path is untouched — **PASS**

`grep -rn 'register_artifact' cortex_command/pipeline/ cortex_command/overnight/` → no matches
(exit 1). Repo-wide, the verb still has **zero** non-test Python callers.

### R7 — Existing behaviour preserved on the happy path — **PASS** (one narrowing noted)

All 20 tests in the file pass (16 pre-existing + 4 new). I diffed the test commit: no assertion about
`registered` / `already-present` / `no-index` semantics was altered — the only changes are fixture
setup (`_write_index` now writes a non-empty sibling for each of the four artifact kinds, gated by a
`write_artifacts=False` opt-out) plus the four new cases. Idempotency
(`test_double_register_is_byte_level_noop`) and the `updated:` bump assertions are byte-for-byte the
originals. Live happy path re-confirmed: `"state":"registered"` and `artifacts: [review]`.

Narrowing (**PARTIAL note, non-blocking**): the check sits after the index read but before the
`_ARTIFACTS_RE` match, per the plan's explicit placement. A *malformed* index (present but with no
`artifacts:` line) whose artifact file is also missing now reports `error` where it previously reported
`no-index` — visible in `test_index_without_artifacts_line_returns_no_index:155`, which had to gain a
`research.md` to keep its result. R8 only guarantees the precedence for an **absent** index, so this is
inside spec; but a genuinely malformed index is now diagnosed as a missing artifact, which is the less
useful of the two messages. Cheap to fix later by moving the check below the `match is None` branch;
not worth a rework cycle on its own.

### R8 — Refusal precedence over `no-index` — **PASS**

Executed with neither file present: `{"state":"no-index","feature":"f","artifact":"review","protocol":3}`.
Structurally guaranteed — the `FileNotFoundError` arm at `:110-111` returns before the artifact check at
`:115` is reached. Pinned by `test_neither_index_nor_artifact_returns_no_index_not_error` with a
docstring that names the precedence, so a future reordering fails loudly.

### R9 — §2 single-writer rule admits resumption — **PASS**

`review.md:23` now reads "only the reviewer role writes `review.md`: this sub-task, resuming that
reviewer, and §3's and §3a's re-dispatches." Resumption is admitted, the rule stays role-scoped, and
the two re-dispatch routes are preserved (collapsed into one clause, which is a wording compression,
not a semantic loss). Acceptance is session-dependent by the spec's own admission and cannot be
exercised from a test; assessed by reading. The mirrored plugin copy is byte-identical (`cmp` exit 0).

### R10 — §3 defines the missing-artifact response — **PARTIAL**

Acceptance criterion **met**: `grep -c 'read the existing file' skills/build/references/review.md` = 0,
and no instruction anywhere in the file now prescribes reading an existing file as the remedy for an
absent one. §3 gained "No review.md at all → resume the original reviewer and await its return; never
re-check immediately" — which also encodes the spec's resume-race guard (resume-then-await, never
resume-then-recheck) rather than dropping it.

**The orchestrator's flagged gap is real, but it is not a spec violation.** Grammatically, the closing
"Still absent → escalate" attaches to the missing-`## Requirements Drift` re-dispatch that immediately
precedes it, so a *resumed* reviewer that still writes nothing falls back onto the same sentence it
just executed — resume, await, resume — with no written terminal. The spec anticipated the termination
question and answered it: Non-Requirements, "A retry cap for resumption. Resumption is bounded by
orchestrator judgment; when it falls through to re-dispatch, §3's existing cap governs. No new cap is
introduced." The residual is that the shipped sentence never states that fall-through exists, so "§3's
existing cap governs" has nothing in the prose to attach to. This is the one recurrence case the ticket
exists to serve, so it is worth closing — but the spec explicitly declined to require a cap, so
withholding approval over it would be reviewing against a requirement that was not written.

Concrete fix if taken up (roughly +45 B, which the raised pin does not currently cover — it would need
another `# raised:` increment or an offsetting trim elsewhere in the directory): end the first clause
with "…await its return; never re-check immediately. Still nothing → re-dispatch under §3a's cap, then
escalate."

### R11 — Ratchet stays green, both pins — **PASS**

Route (iii) was taken, as the spec pre-authorized. Verified independently of the suite by calling
`ratchet_refs.measure()` / `classify()` directly:

- measured `skills/build/references` = **57236**; pin = **57236**; `classify()` returns `[]` (no violation).
- `cmp skills/build/references/size-pin.txt plugins/cortex-core/skills/build/references/size-pin.txt` exits 0 — byte-identical.
- The new marker matches both existing precedents and the ratchet's own parser (`# raised: <reason ≥30 chars>, lifecycle-id=<NNN>, date=<YYYY-MM-DD>`): reason well over 30 chars, `lifecycle-id=457`, `date=2026-08-07`, `SS3`/`SS2` ASCII spelling consistent with the 433 and 449 lines. `classify()` returning `[]` is executable proof the marker parses, not an eyeball match.
- `tests/test_reference_size_ratchet.py` 12 passed in the baseline.

### R12 — New refusal coverage — **PASS**

Four new tests, all four required cases, each naming the refusal in its assertion or docstring:
`test_missing_artifact_file_returns_error` (also asserts `research.md` appears in the message and that
`artifacts: []` survives), `test_zero_byte_artifact_file_returns_error`,
`test_neither_index_nor_artifact_returns_no_index_not_error` (R8 precedence), and
`test_artifact_check_anchors_to_index_parent_not_feature_slug` (R3, both directions). Happy-path
registration still covered by the untouched originals. 20 passed in the baseline.

## Additional checks

**Return-shape consistency of the new `error` (asked explicitly).** Not a defect — it matches the
pre-existing precedent. Both existing `error` returns (`:154-158` `CortexProjectRootError`, `:159-160`
`OSError`) carry `state` + `message` only, as does `main()`'s never-crash net at `:204`. The new arm's
`{"state", "message"}` is exactly that shape. `feature`/`artifact` appear only on the arms that got far
enough to be about a specific index (`no-index`, `already-present`, `registered`). Adding them would be
a mild improvement to a caller trying to correlate output, but no caller does — the verb has zero
non-test Python callers, and all five prose call sites are fire-and-forget.

**The docstring risk the plan named was paid.** `register_artifact.py:29-33` and the function docstring
at `:94-95` both now describe `error` as covering a routine precondition failure *or* an unexpected
exception, so the contract no longer contradicts the code. This was called out as a plan risk and was
actually discharged.

**Call-site inventory re-verified, not taken from the spec.** All five prose call sites exist as
claimed (`skills/build/references/review.md:35`, `plan.md:76`, `backlog-writeback.md:19`,
`skills/refine/SKILL.md:76`, `skills/refine/references/research-phase.md:23`), each passes
`--artifact <name>` where `<name>.md` is the file written beside `index.md`, and none branches on the
returned state. So no call site can false-refuse on a naming mismatch, and none breaks. The spec's
"enforcement must be the withheld write, not a returned value" premise holds.

**Plan verification steps were actually executed.** Task 1's, Task 2's and Task 3's stated verification
commands all reproduce: the three-way CLI fixture behaves as written, the targeted test file is green,
`grep -c 'read the existing file'` is 0, and both pins `cmp` clean.

## Requirements Drift

- **State**: detected
- **Findings**:
  - `cortex/requirements/lifecycle.md` landed mid-build (#469) and neither `research.md` nor `spec.md`
    saw it — both still assert it does not exist. Assessed fresh here. Its `### Served verb class`
    section is where per-verb refusal invariants live (`advance` refuses on a from-state gate mismatch;
    every verb rejects an unsafe slug before filesystem access), and this change adds exactly such an
    invariant: `register-artifact` now refuses to record an artifact whose file is absent or zero-byte.
    The doc captures no clause for it, so the new refusal — and its precedence behind `no-index` — is
    unreflected behaviour.
  - Non-drift, checked and clear: `lifecycle.md:88` (never-crash verbs) is satisfied, not extended;
    `lifecycle.md:101` / ADR-0035 does not fire because the served brief shape is unchanged;
    `project.md`, `glossary.md`, and `pipeline.md` carry nothing this work contradicts or exceeds.
- **Update needed**: `cortex/requirements/lifecycle.md`

## Suggested Requirements Update

- **File**: `cortex/requirements/lifecycle.md`
- **Section**: `### Served verb class`
- **Content**:

```
- `register-artifact` refuses to record an artifact whose `{artifact}.md` is absent or zero-byte, returning the existing `error` state and writing nothing, so `index.md`'s `artifacts:` array can never claim an artifact that was never produced. The checked file is resolved beside the index that was resolved, not from the feature slug.
- That refusal sits behind the missing-index check: a feature with no `index.md` still returns `no-index`, keeping a missing index distinguishable from a missing artifact.
```

## Verdict

Twelve requirements: eleven PASS, one PARTIAL (R10), zero FAIL. The gate does what the ticket was filed
for — a `review.md` that was never written can no longer be recorded as existing, verified live rather
than inferred — and every preservation invariant holds under execution. The single PARTIAL is a prose
terminal the spec explicitly declined to require, plus one minor diagnostic narrowing under R7; both are
recorded above as follow-up rather than rework.

```json
{"verdict": "APPROVED", "cycle": 1, "issues": ["R10 (minor, non-blocking): review.md §3's closing \"Still absent → escalate\" grammatically terminates the missing-drift re-dispatch, not the new no-artifact branch, so a resumed reviewer that still writes nothing loops on resume-and-await with no written terminal. The spec's Non-Requirements assumes a fall-through to re-dispatch under §3's cap, but the shipped sentence never states one. Suggested wording and its ~45 B ratchet cost are in the R10 section.", "R7 (minor, non-blocking): the precondition sits before the artifacts:-line match, so a malformed index.md (present, no artifacts: line) whose artifact is also missing now reports \"error\" naming the artifact instead of \"no-index\". Inside spec — R8 only covers an absent index — but the less useful of the two diagnostics. Moving the check below the `match is None` branch would restore it."], "requirements_drift": "detected"}
```
