# Review: no-lifecycle-area-requirements-doc-so — cycle 1

Read-only full review (Stage 1 + Stage 2). All implementation files read from the worktree
`.claude/worktrees/interactive-no-lifecycle-area-requirements-doc-so/` (verified: `project.md` 26,387 B,
`lifecycle.md` 17,542 B). Test baseline consumed as handed over (2550 passed / 0 failures); the suite was
not re-executed. Every check below was re-run or re-derived rather than taken from the plan's status lines.

## Stage 1 — Spec compliance

### R1 — area doc exists and conforms — **PASS**

`uv run python -m cortex_command.lifecycle.validate_requirements_doc_cli --scope area --path cortex/requirements/lifecycle.md`
→ `{"state": "pass", ..., "missing": []}`, all seven H2s present. The header triple is at
`cortex/requirements/lifecycle.md:1,3,5` — `# Requirements: lifecycle`, `> Last gathered: 2026-08-07`,
`**Parent doc**: [requirements/project.md](project.md)` verbatim.

Noted, not charged against the build: the validator checks H2 *presence* only, so R1 could be discharged by
seven empty headings. The spec discloses this in Technical Constraints, and the delivered doc has real
content under every H2, so the criterion is weak but not vacuously satisfied here.

### R2 — routing row is a bare path and the loader resolves it — **PASS**

`cortex/requirements/project.md:107` now ends `→ cortex/requirements/lifecycle.md` with nothing after it
(diff against `main` confirms the entire `(NOT YET WRITTEN — …)` parenthetical is gone). Re-ran the loader:

```
cortex/requirements/project.md
cortex/requirements/glossary.md
cortex/requirements/lifecycle.md
```

Third line is bare — no ` (skipped: file absent)` suffix. Genuinely red at HEAD before the change.

### R3 — seven ADRs cited with status honoured — **PARTIAL**

The stated acceptance passes cleanly, and I re-verified the statuses from frontmatter rather than trusting
the spec's list:

- `accepted`: 0010, 0012, 0017, 0030 — all four still accepted as of this review.
- `proposed`: 0018, 0020, 0022 — all three still proposed. Each is cited on a line carrying
  `(**proposed**, so not binding)` (`lifecycle.md:45`, `:50`, `:84`), and
  `grep -n '0018\|0020\|0022' | grep -c 'ratif'` returns **0**. `:122` additionally holds all three open in
  `## Open Questions`.

The build also went beyond the criterion where it mattered: ADR-0024 (`:44`) and ADR-0025 (`:51`, `:97`) are
both `status: proposed` and are marked as such, even though the plan's Task 2 context falsely asserted they
were not. On `main`, `project.md:49` cited both with no status marking at all, so the relocation *improved*
status discipline on those two.

**The PARTIAL**: two other proposed ADRs are cited without any status marking, and one of them carries a
normative claim.

- `lifecycle.md:98` — "The served-verb class does not reopen **ADR-0019** for other helper verbs. A served
  envelope may name a skill to invoke only when that skill's invocation condition is machine-readable
  state." ADR-0019 is `status: proposed`. This sits under `## Architectural Constraints` and reads as a
  binding constraint derived from an unratified ADR, which is exactly what `cortex/adr/README.md:62`
  forbids a consumer to do.
- `lifecycle.md:37` — "a bounded, wheel-owned exception to **ADR-0019**'s dumb-arg-actor rule". Mitigating:
  this framing is relocated near-verbatim from `project.md:49` on `main`, so the lapse is *inherited*, not
  introduced by this change. R6 requires the removed detail to appear in `lifecycle.md`, so faithful
  relocation and status-marking pull against each other here.
- `lifecycle.md:108` — "the spec-approval write-back is backend-gated; see `cortex/requirements/backlog.md`
  and **ADR-0016**." ADR-0016 is `status: proposed`. Weakest of the three: the primary source cited is
  `backlog.md`, and this is a see-also rather than a binding claim.

Non-blocking — the fix is two parentheticals, and none of the three statements is factually false about the
code. Recorded because the spec calls status discipline "binding, not stylistic" and grounds it in a MUST NOT,
and because the criterion's grep can only ever see 0018/0020/0022.

### R4 — boundary against adjacent docs — **PASS**

Both attributions are present in substance, not as bare citations:

- `lifecycle.md:11` — statusline feature/phase line, dashboard badges and phase progress, and the
  `phase_label` projection attributed to `cortex/requirements/observability.md`.
- `lifecycle.md:13` — `planning → executing → complete` (session machine) and `pending → running → merged`
  (feature status) attributed to `cortex/requirements/pipeline.md`, with an explicit "the two vocabularies
  must not be conflated".

Observation on the criterion, not the build: R4 says "**each** occurrence must sit in a sentence attributing
…". Both paths occur twice; the second occurrence of each is at `:109`, a `## Dependencies` cross-reference
("Consumers of this area's state") that carries neither attribution. Read literally, R4 fails there. I read
that clause as anti-bare-citation guarding rather than a per-occurrence rule, and `:109` is a different kind
of statement, so I rate this discharged. Flagging it because the criterion is ambiguous as written.

### R5 — points at the glossary rather than restating it — **PASS**

`grep -Fc 'cortex/requirements/glossary.md'` → 1, at `lifecycle.md:15`, which states the rationale ("loads
unconditionally via `project.md`'s `## Global Context`. This doc cites them and does not restate them").
All three absence literals return **0**.

I checked the absence criteria are not being satisfied by paraphrase, since the spec admits they are vacuous
until R1 lands. `lifecycle.md:30` writes "the short road (see glossary)" rather than restating the predicate,
and the doc nowhere enumerates the tier or criticality value sets. The negative holds in substance.

### R6 — seven relocations behind pointer stubs — **PASS**

Mechanical half, all seven verified: exactly one matching line each, each containing
`cortex/requirements/lifecycle.md`, at 131 / 136 / 148 / 150 / 150 / 152 / 159 B against the 200 B cap
(total 1,026 B, under the 1,370 B ceiling R8's arithmetic requires).

The load-bearing half — "The removed detail appears in `lifecycle.md`" — has **no mechanical criterion**, is
the highest-risk clause in the spec, and three of seven items were *merged* rather than appended. I verified
it by normalized string comparison against `git show main:cortex/requirements/project.md`:

Relocated byte-identical, modulo the added `(accepted)` / `(proposed)` status markers:

- `Multi-step lifecycle phases` → `lifecycle.md:33` (body identical; only the bold label prefix dropped).
- `Phase boundaries are session boundaries` → `:95`.
- `` Consumer `EnterWorktree` authorization surface `` → `:99`.
- `Override-reason clause vocabulary` → `:101`.

Merged, checked clause by clause:

- `Served lifecycle verb class` → split across `:37` (ADR-0019 exception + read config / resolve identity /
  evaluate guards / serve from the closed transition table), `:44` (legacy typed subcommands + coexistence
  window closed only by an operator-decided protocol-floor bump → ADR-0024), and `:97` (events-authoritative,
  artifact fallback, forfeited prose-side revert, `docs/rollforward-exit.md` → ADR-0025). **Every clause of
  the original survives**, and both ADR citations gained the proposed marking they lacked on `main`.
- `The reviewer brief is a protocol-governed served surface` → `:100`. Reworded (leading clause moved to the
  front) but every element intact: `cortex-lifecycle-review-brief`, both consumers, `PROTOCOL_VERSION` and
  `skills/build/references/protocol-expectation.txt` moving in the same commit, → ADR-0035.
- `Kept user pauses are a marked taxonomy` → `:58` carries the original paragraph verbatim from "of the
  deliberate…" through "…per-kind semantic anchors", and the runtime-consumer sentence is folded into `:60`
  intact (`next` serves each state's pause spec; AskUserQuestion; "read at runtime and not only by the
  parity test").

**One clause lost in the merge**: the kept-pause bullet's trailing `→ ADR-0024` back-pointer. ADR-0024 is
still cited in the doc at `:44`, but no longer from the pause-taxonomy context, so the "the served loop is
why the taxonomy has a runtime consumer" link is now implicit. Minor, and the substance it pointed at is
preserved — recorded rather than charged as a failure.

Also dropped: the era-specific "Under the 374 served loop" framing. That is an improvement.

### R7 — five contested bullets preserved in full — **PASS**

Checked by string equality against `main`, not by presence. All five **byte-identical**:
`Critical-review gates at spec only` (281 B), `The short road` (669 B),
`Lifecycle identity is the canonical slug` (1,062 B), `Lifecycle phase vocabulary` (953 B),
`The lifecycle events corpus is mixed-format` (691 B). The `git diff main...HEAD -- cortex/requirements/project.md`
touches no line in that set — the whole diff is 3 hunks containing only the seven stubs and the routing row.

The spec is right that this criterion passes at HEAD by construction; it did its job as an over-relocation
tripwire and the build did not trip it.

### R8 — measured shrink recorded — **PASS** (with a one-sided record; see Issue 2)

`wc -c` → 26,387 B, i.e. **3,531 B** below the 29,918 B baseline, clearing the 3,000 B bar. The figure is
recorded in `lifecycle.md:90` in greppable form (`29,918 B → 26,387 B`), including the 29,731 B intermediate
and why it differs (the routing-row fix had already removed 187 B — arithmetic checks out).

### R9 — regression test pinning that every Conditional Loading path resolves — **PARTIAL**

The guard is real, not decorative. I re-derived the mutation independently rather than trusting the report,
by calling the test's own helper against mutated strings in memory (no file was written):

| probe | mutation | result |
| --- | --- | --- |
| C | ` (annotation)` appended to the lifecycle row (the #454 shape) | **RED** — emits `UNRESOLVABLE_AREA_DOC_PATH` naming the trigger and the annotated path |
| A | `## Conditional Loading` heading renamed | **green** |
| B | section heading kept, all rows deleted | **green** |
| D | `→` replaced with ASCII `->` on the lifecycle row | **green** |

The live corpus parses 7 rows and 0 diagnostics, so the terminal assertion is genuinely exercising real data.
`tests/test_conditional_loading_paths_resolve.py:38-40` imports the loader's own
`_parse_conditional_loading` as the plan requires — parser parity is what makes probe C catchable.

**The blind spot**: `_find_unresolvable_conditional_paths` returns `[]` both when every row resolves and when
there are no rows at all, and the live test asserts only `diagnostics == []`. This is the standard
assert-empty-list trap — probes A and B show the guard goes silently green if the routing table is emptied or
its heading drifts, which is a *worse* outcome than #454 (every area doc goes dark, not one). One line closes
it: assert the parsed row count is non-zero, or pin the expected set of area-doc paths.

Probe D is a second, weaker gap: an ASCII-arrow row is invisible to both the loader and the guard. The
loader's `no area docs matched` warning would fire only if no *other* area matched — the same boolean-warning
hole the spec already records in Open Decisions — so this is arguably that deferred item's territory, not
this one's.

On the brief's specific question — **no**, the two `tmp_path` self-tests do not mask the live assertion. Both
exercise the same helper that the live test calls (`:94`, `:112-118`), and the negative self-test asserts a
*non-empty* diagnostic list with content checks, so it cannot pass on a helper that returns `[]`
unconditionally. They are supporting tests, not substitutes.

### Stage 1 result

No FAIL. Two PARTIALs (R3, R9), neither blocking. Stage 2 proceeds.

## Stage 2 — Code quality

**Test quality.** `tests/test_conditional_loading_paths_resolve.py` follows the named pattern
(`tests/test_backlog_grep_targets_resolve.py`): helper + `tmp_path` self-tests + one terminal live-corpus
guard. `REPO_ROOT = Path(__file__).resolve().parent.parent` resolves correctly inside the worktree.
The docstring names the failure it prevents (`:14-16`) and explains the parser-parity choice (`:18-21`) and
the Global-Context exclusion (`:23-25`). No skill-prose pinning — it reads a requirements doc as structure,
which is permitted. Diagnostics name both trigger and path, so a failure is actionable. Only defect is the
empty-list vacuity above.

**Plan verification steps actually executed.** Yes, and independently reproducible — I re-ran R1–R5's checks
and the R6/R7/R8 measurements and got results matching the recorded ones. Task 3's mutation was re-derived
from the helper. Nothing in the plan's status lines is a claim I could not confirm.

**Recorded deviations are honest.** Three are logged and all three check out:

1. `just test -k <expr>` is not runnable (`test` is argument-less) — confirmed by reading the recipe;
   targeted runs correctly fell back to `uv run pytest <file>`.
2. Task 2's context falsely asserted ADR-0024/0025 were not proposed. Both **are** `status: proposed`. The
   builder caught it by reading frontmatter and marked them proposed in the merged text (`:44`, `:51`, `:97`).
   No check keyed on it, so the correction depended entirely on the builder not trusting its own plan — worth
   noting as a near-miss, not a defect.
3. Task 1a missed its ≤11,000 B gate at 13,787 B. **The recorded deviation is honest and the doc's size is
   defensible.** The status line states the exact figure, names precisely what would have had to be deleted,
   and names the compensating lever — and the lever measurably worked (+3,755 B into `lifecycle.md` against
   4,370 B removed from `project.md`, so the merge recovered 615 B). Reading the delivered doc end to end, I
   found no padding: `## Functional Requirements` is 60-odd distinct invariants, not a capability inventory,
   and the seven ADR citations are one line each. I could not identify 2,787 B of cuttable content that isn't
   a rule a builder would violate by accident.

**Pattern consistency.** The doc matches the sibling area docs' rhythm (`remote-access.md`, `pipeline.md`),
keeps H2 names verbatim and greppable for `review.md` §3a's drift append, and stubs point at constraints
rather than section anchors, so a rename in `lifecycle.md` cannot break one — matching the spec's Edge Cases.

**Minor internal tension, not worth a cycle.** `lifecycle.md:102` says operational detail "lives in
`CLAUDE.md` and `docs/`, not here", while `:58` (1,060 B) names the generator verb, the TOML data file, and
the parity-test filename. That text is relocated verbatim under R6's preservation clause, so trimming it would
put R6 and `:102` in direct conflict. Recorded, not requested.

## Issues

### Issue 1 — two proposed ADRs cited as settled doctrine (R3, non-blocking)

`lifecycle.md:98` states a normative `## Architectural Constraints` clause resting on ADR-0019
(`status: proposed`); `:37` and `:108` cite ADR-0019 and ADR-0016 (also `proposed`) without marking.
`:37`'s framing is inherited verbatim from `project.md:49` on `main`. Suggested fix, if taken: mark them the
same way 0018/0020/0022/0024/0025 are marked, or drop `:108`'s ADR-0016 see-also since `backlog.md` already
carries it.

### Issue 2 — the delivered size trade is 2.6–6× the disclosed cost, and only the benefit is recorded

Measured on the branch:

| | before | after | delta |
| --- | --- | --- | --- |
| non-lifecycle feature (`project.md` + `glossary.md`) | 31,094 B | 27,563 B | **−3,531 B** |
| lifecycle-tagged feature (+ `lifecycle.md`) | 31,094 B | **45,105 B** | **+14,011 B** |

The spec's "Who pays and who benefits" block projected a lifecycle-tagged load of 33,400–36,400 B, i.e.
+2,330 to +5,330 B. The delivered figure is +14,011 B. The non-lifecycle side landed essentially on
projection (−3,531 vs −3,670 projected), so the projection is wrong on exactly the half that pays.

**Is the projection being wrong a finding? Yes — but the miss itself is not a build defect.** It was detected
at implement time, escalated to the operator, and answered with Task 1a rather than absorbed silently; that is
the right handling, and the doc's content survived my search for padding. **The finding is that the corpus now
records only the favourable half.** `lifecycle.md:90` — the Token economy bullet, exactly where a future
reader looks — states the 3,531 B saving and is silent on the 14,011 B cost. `CLAUDE.md`'s front-door
evidence bar requires an efficiency-framed change to state "its expected net effect on the surface it claims
to shrink", and a one-sided record is the failure mode that bar exists to prevent. The fix is one appended
sentence at the site that already holds the other number (see Suggested Requirements Update below).

### Issue 3 — the R9 guard goes silently green if the routing table is emptied or its heading drifts

See R9. Demonstrated by probes A and B. One assertion closes it.

## Requirements Drift

- **State**: `detected`
- **Findings**:
  - `cortex/requirements/lifecycle.md:90` records the `project.md` shrink (−3,531 B for non-lifecycle
    features) but not the corresponding increase for lifecycle-tagged features (26,387 + 1,176 + 17,542 =
    45,105 B, **+14,011 B** against the prior 31,094 B). The requirements corpus therefore captures only the
    favourable half of a trade the spec framed as the ticket's central disclosure, and the spec's own
    projection (+2,330 to +5,330 B) is now contradicted by the delivered artifact with nothing recording the
    correction.
- **Update needed**: `cortex/requirements/lifecycle.md`

## Suggested Requirements Update

- **File**: `cortex/requirements/lifecycle.md`
- **Section**: `## Non-Functional Requirements`
- **Content**:

```
- **The area-doc load, measured**: a lifecycle-tagged feature loads `project.md` + `glossary.md` + this doc = 45,105 B, against 31,094 B before this doc existed — **+14,011 B**, well above the 33,400–36,400 B projected when the work was specced. Non-lifecycle features pay −3,531 B. The shrink's beneficiary is the non-lifecycle majority; this area pays for its own coverage.
```

## Verdict

Nothing here blocks. The nine spec requirements are all discharged, the two criteria the spec flagged as
non-failing behaved as flagged, and the three highest-risk areas the brief named — merge fidelity, R7
byte-identity, and whether the regression test is a real guard — each held up under a check that could have
gone the other way. Merge fidelity in particular preserved every clause across three merged items and
*improved* status discipline on ADR-0024/0025 relative to `main`. The two PARTIALs are a two-parenthetical
status-marking lapse (partly inherited) and a one-line assertion gap in a test that already catches the
defect it was built for. Issue 2 is the one I would most want addressed, and it is fully served by the
requirements append above rather than a rework cycle.

```json
{"verdict": "APPROVED", "cycle": 1, "issues": ["R3 PARTIAL: ADR-0019 (lifecycle.md:37,98) and ADR-0016 (:108) are status:proposed but cited without the proposed marking; :98 states a normative Architectural Constraint resting on an unratified ADR, against cortex/adr/README.md:62. The :37 framing is inherited verbatim from project.md:49 on main. Non-blocking; fix is two parentheticals.", "R9 PARTIAL: the live guard asserts only `diagnostics == []`, so it goes silently green if the `## Conditional Loading` heading is renamed or its rows are deleted (verified by probing the helper). It correctly goes red on the #454 annotated-path shape. Add an assertion that the parsed row count is non-zero. An ASCII `->` arrow is also invisible to both loader and guard.", "R6 minor: the kept-pause bullet's trailing `-> ADR-0024` back-pointer was dropped in the merge; ADR-0024 survives at lifecycle.md:44 but no longer from the pause-taxonomy context. All other clauses of all seven relocated items verified preserved.", "Size trade under-disclosed: a lifecycle-tagged load is 45,105 B (+14,011 B vs 31,094 B before) against the spec's projected +2,330 to +5,330 B. lifecycle.md:90 records only the -3,531 B benefit to non-lifecycle features and is silent on the cost, which the front-door evidence bar exists to prevent. Covered by the suggested requirements update."], "requirements_drift": "detected"}
```
