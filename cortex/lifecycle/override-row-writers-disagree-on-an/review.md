# Review: override-row-writers-disagree-on-an — cycle 1

**Feature**: `override-row-writers-disagree-on-an` (backlog #474) · criticality `high` · tier `complex`
**Scope**: Stage 1 (spec compliance, all 15 requirements) + Stage 2 (code quality) — no Stage-1 FAIL.
**Test baseline consumed, not re-run**: `just test` → 8/8 suites, exit 0
(`/private/tmp/claude-501/-Users-charliehall-Workspaces-cortex-command/ea7c6f0f-bd70-42b1-9a22-e3d391d58a47/scratchpad/baseline.log`).

## Method

Every acceptance criterion below was **executed**, not read. Repo code was exercised via
`uv run --project /Users/charliehall/Workspaces/cortex-command python -m cortex_command.<mod>` (never the
PATH wheel). CLI probes ran against throwaway roots under the scratchpad. Falsifiability was checked by
mutating a `git archive HEAD` copy of the tree in the scratchpad (no repo write, no worktree registration)
and re-running the affected suites — seven mutants, reported inline.

One criterion was found to be **unfalsifiable as first run and was redone**: requirement 9's byte-identity
check initially compared `cortex/lifecycle/events.log`, which `log_event` never writes — the real path is
`cortex/lifecycle/<feature>/events.log`. Re-run against a non-empty real log, it passes.

## Stage 1 — Spec compliance

| # | Rating | Evidence (executed) |
|---|--------|---------------------|
| 1 | PASS | `import cortex_command.override_reason` → `['consequence', 'exposure', 'other', 'reversibility']`; `grep -c "^from cortex_command\|^import cortex_command"` → `0`. |
| 2 | PASS | `grep -c "_ALLOWED_REASON_CLAUSES *[:=] *frozenset" refine.py` → `0`; `grep -c "override_reason" refine.py` → `1`. |
| 3 | PASS | `grep -c "_ALLOWED_REASON_CLAUSES" refine.py` → `0`; `reconcile-clarify --help \| … \| grep -c 'consequence, exposure, other, reversibility'` → `1` (regression guard holds). |
| 4 | PASS | Rejected tag on `criticality-override` emits `cortex-lifecycle-event criticality-override: error: argument --reason: --reason 'zzz: y': clause tag 'zzz' is not one of: …`. Contains `cortex-lifecycle-event`, does not contain `cortex-refine`. See Open item 1 for the doubled flag name. |
| 5 | PASS | `tests/test_override_reason.py` collects all five widened cases plus `zzz: y`. **Falsifiability proven**: replaying the pre-change predicate (raw first-colon prefix, no strip/lower, identity canonicalizer) into the mutation copy turns the suite red — `11 failed, 23 passed`, including `test_tagged_reason_claims_its_canonical_tag['Exposure: x']`. The docstring's claim is true. |
| 6 | PASS | Typed verb: `--reason " Exposure: it feeds spec authoring"` lands as `exposure: it feeds spec authoring`; `--reason "blast radius: unbounded"` lands byte-identical. Refine writer: same two, plus `exposure: it feeds A: B` and `other:x` byte-identical. |
| 7 | PASS | `complexity-override --reason "design-fork: two options"` → exit 2, nothing appended. `criticality-override` with the same string → exit 2, nothing appended. `reconcile-clarify --tier-reason 'design-fork: two options'` → exit 2. Both writers route identically. |
| 8 | PASS | (a) `tests/test_refine_reconcile_clarify.py` → 15 passed. (b) The two-bad-tag probe exits 2 with **exactly two** stderr lines, one per flag. |
| 9 | PASS | Against a **non-empty** (641-byte) real log: rejected tag → exit 2, `cmp` byte-identical. Structural: argparse raises before `_emit_subcommand` runs. |
| 10 | PASS | `--reason ""` and `--reason "   "` both append a row with no `reason` key (`set(row) == {ts, event, feature, from, to}`). |
| 11 | PASS | `feature-complete --tasks-total 0 --rework-cycles 0` → row carries `"tasks_total": 0`, `"rework_cycles": 0` as ints. |
| 12 | PASS | Amended recipe over the specified fixture → `Counter({'exposure': 2, 'untagged': 1})`; HEAD recipe over the same fixture → `Counter({'exposure': 1, 'Exposure': 1, 'blast radius': 1})`. Exactly the stated contrast. Also run over the real corpus: `Counter({'untagged': 7, 'exposure': 6})`, no traceback. |
| 13 | PASS (with note) | All nine `BULLET` greps return their stated values. Every factual claim in the rewritten bullet was verified against running code — see "Prose truth audit". Note: the locator "`skills/refine/SKILL.md` Step 4" is now under-specified (below). |
| 14 | PASS | `awk '/criticality-override/' skills/build/SKILL.md \| grep -c 'reversibility'` → `1`; the `complexity-override` counterpart in `skills/refine/SKILL.md` → `1`. Mirror parity verified by `diff` against `plugins/cortex-core/skills/{refine,build}/SKILL.md` — zero drift, without running `build-plugin`. |
| 15 | PASS (with note) | `cortex/backlog/478-…-no-tag-to-land-on.md` exists, cites `cortex/lifecycle/tier-overrides-record-no-reason-and/spec.md:32` (verified: that line holds both quoted passages verbatim) and states the re-measure trigger. Its measurement query **reproduces exactly**: `{"rows": 57, "filled": 1, "tags": {"other": 1}}`. One incorrect line citation — below. |

No FAIL. Stage 2 proceeds.

## Prose truth audit (the defect class this repo has been shipping)

Each claim below was checked by running something, not by reading.

- `cortex/requirements/lifecycle.md:104` — **all true**. `refine.py:29` does import `lifecycle_event` (verified by grep on the shipped line number). The tag-claim rule and lowercasing match `claimed_tag` exactly. Key order on disk from the typed verb is `['ts','event','feature','from','to','reason']`, and `refine.py` appends `gate` after it — the "order their shared keys `from, to, reason`" claim holds. "The untyped `log --set` escape hatch … can still record `"reason": ""`" — executed: `log --event criticality_override --set reason=` exits 0 and writes `"reason": ""`, and `--set 'reason=zzz: y'` exits 0 and writes the bogus tag. "adding a tag edits all four" — arithmetic checks out (owner + 2 SKILLs + ADR). "`skills/refine/SKILL.md` Step 4" — line 72 is indeed under `## Step 4: Spec`.
- `cortex/adr/0036-*.md` recipe — **isomorphic to the code**, proven by differential testing over 22 adversarial inputs (leading capital, leading space, tab, NBSP, empty prefix, `a:b:c`, inner colon, no colon, empty string): **zero disagreements** with `claimed_tag` + membership. `TAGS == ALLOWED_REASON_CLAUSES` verified as sets.
- `skills/build/SKILL.md:71` — "an unknown tag is rejected and the whole row is discarded, so retag and re-run": executed, exit 2 with nothing appended. True.
- `skills/refine/SKILL.md:63` — "the whole row, `from`/`to` included, is discarded": true. `:72` — "An unknown tag is rejected and nothing is written" for `reconcile-clarify`: true (exit 2, log byte-identical).
- `refine.py:393-403` (Task 10's rewritten comment) — **true**. "`_emit_subcommand` drops an optional field whose value is None or a blank string" verified; "the blank-aware test here drops a None, empty, or whitespace-only reason the same way" verified; and its warning — "Do not narrow this back to plain truthiness … the first writes `"reason": "   "`" — is *executable and confirmed*: mutating both row builders back to truthiness turns `test_reconcile_clarify_whitespace_only_reasons_omit_the_key` red (`1 failed, 14 passed`).
- `lifecycle_event.py:_clause_arg` comment — true as far as it goes; it explains the `{prog}` de-duplication and is silent on the `{flag}` duplication it introduces (Open item 1).
- **No stale references** to `_ALLOWED_REASON_CLAUSES` / `_reason_clause_ok` / `_BAD_REASON_CLAUSE_MSG` survive anywhere outside the historical backlog and lifecycle records.

## Falsifiability (mutation results on a scratchpad copy)

| Mutant | Result |
|---|---|
| `canonicalize_reason` → `return value` | `tests/test_override_reason.py` 1 failed; `test_lifecycle_event.py` 1 failed |
| `claimed_tag` whitespace check removed | `tests/test_override_reason.py` 6 failed |
| `_clause_arg` binding deleted from `_build_parser` | `test_lifecycle_event.py` 5 failed |
| refine row builders → plain truthiness | `test_refine_reconcile_clarify.py` 1 failed |
| `_emit_subcommand` drop → `value is None and not required` | `test_lifecycle_event.py` 2 failed |
| `_CLAUSE` → `_STR` in both table rows | `test_lifecycle_event.py` 5 failed |
| **`canonicalize_reason` calls removed from `refine.py`** | **`test_refine_reconcile_clarify.py` 15 passed — SURVIVOR** |

## Stage 2 — Code quality

**PARTIAL — the refine writer's canonicalization is pinned by no test.** Deleting both
`canonicalize_reason(...)` calls from `cortex_command/refine.py:342-349` leaves
`tests/test_refine_reconcile_clarify.py` fully green (15 passed). The behavior itself is *correct* — a probe
confirms `--tier-reason " Exposure: …"` lands as `exposure: …` and `blast radius: unbounded` byte-identical —
but the spec's whole-ticket Acceptance says `--reason " Exposure: x"` "lands as `exposure: x` **from either
writer**", and only one writer is pinned. A regression on the refine half would ship silently. Requirement 6's
own acceptance names only the typed verb, so this is not a requirement FAIL; it is the coverage gap the ticket's
Acceptance implies. One parametrized case in the existing suite closes it.

**PARTIAL — `lifecycle.md:104`'s restatement locator is under-specified by this ticket's own change.** The
bullet points at "`skills/refine/SKILL.md` Step 4", but requirement 14 added a *second* restatement of the four
tags to that file at line 63, under `## Step 3: Research`. `grep -c reversibility skills/refine/SKILL.md` → `2`.
A maintainer adding a tag and following the bullet's pointer edits Step 4 and misses Step 3. The file count
"all four" stays correct; the within-file locator does not. One-word fix.

**PARTIAL — `#478` cites the wrong line for §5.2.** The ticket references
`skills/refine/references/clarify.md:32` (§5.2) in both **Role** and **Touch points**. Line 32 is §5.1
("Clarified intent statement"); §5.2 — the one carrying "competing designs, a blast radius you can't
enumerate, or a precedent others follow" and "whether the next tier down was considered", both quoted in the
ticket — is **line 33**. Off by one, twice. Every other citation in #478 checks out (`spec.md:32`,
`project.md:64`, `project.md:65`, `f0cf4ec1`), and its measurement reproduces exactly.

**Naming and pattern consistency: good.** `_CLAUSE` / `_clause_arg` mirror `_JSON` / `_json_arg` exactly,
including the `_build_parser` branch shape and the field-kind comment update. The `isinstance(value, str)`
guard on the widened drop is the minimal correct form. `canonicalize_reason(None)` is safe by construction.

**Plan verification steps were executed.** Task 3's and Task 5's mutation checks, Task 11's revert check, and
Task 6's fixture run all reproduce independently at the reported shapes; both mutation-target modules are
byte-identical to their producing task's output (no stub left behind — `git status` shows no modification to
`cortex_command/`).

**Tasks 10 and 11 were the right calls and are complete.** Task 10 removed a comment that Task 4 had made
false in the same commit range — exactly the defect class this repo keeps shipping, and unreachable by any
test. Task 11 closed a real residual: before it, `reconcile-clarify --tier-reason "   "` wrote
`"reason": "   "` while `_emit_subcommand` dropped it, leaving the ticket's headline ("writers disagree on an
empty reason") half-closed. Its reading of the scope question is correct — requirement 10 is phase-scoped to
the typed verbs and its acceptance names only `cortex-lifecycle-event`, but the spec's **Edge Cases** state
the whitespace-only rule unscoped and the Problem Statement frames the whole ticket as writer disagreement.
Resolving toward writer parity is the reading that satisfies both, and it is now the only reading a test holds
(mutation confirmed).

## Known open items — independently verified

1. **Doubled flag name — acceptable, requirement 4 satisfied.** Shipped stderr: `cortex-lifecycle-event
   criticality-override: error: argument --reason: --reason 'zzz: y': clause tag 'zzz' is not one of: …`.
   argparse contributes `argument --reason:`; the shared template's `{flag}` contributes the second. Requirement
   4 asks only that the message name the invoking verb and not `cortex-refine` — both hold, executed. The
   redundancy is cosmetic, the message is not wrong, and Task 5 was correctly told not to pin the shape. If it
   is ever tidied, the fix is symmetric with the existing `{prog}` handling (interpolate `flag=""` and strip the
   separator in `_clause_arg` only) — the template must keep `{flag}` for `refine.py`, which has two flags and
   no argparse prefix. Not blocking.
2. **`_DISCARDED_REASON_MSG` truthiness — confirmed it can never affect a written row.** Executed:
   `reconcile-clarify --tier-reason "   " --criticality-reason "   "` on a lifecycle where neither rank moves
   prints two spurious `discarded:` warnings about reasons that would have been omitted anyway, exits 0, and
   appends **nothing** (log stays at 1 row). Structurally it cannot reach a row: the row builders use the
   blank-aware test, and the warning block at `refine.py:434-457` runs only in the `not <axis>_moved` branch,
   where no row is built at all. Task 11's builder's judgement — stderr-only, out of scope — is correct. A
   stray warning about a blank reason is mildly confusing prose, not a contract defect.
3. **ADR-0036's recipe is unpinned, and that is the right call under this repo's policy.** A test asserting the
   contents of a fenced block in an ADR is precisely the "passes only by keeping the words where they are"
   shape `docs/policies.md` forbids; the structural answer is a CLI verb, which the spec did not scope. The
   agreement is therefore prose-held — but it is *currently true*, proven by the 22-case differential above
   rather than by reading. The residual risk is real and worth naming: a future edit to `claimed_tag` (e.g.
   Unicode-normalizing, or narrowing the set per #478) silently desynchronizes the tally, and nothing fails.
   #478's **Edges** already carries "Forking the set forks the module", which is the nearest thing to a guard.
   Recommend the eventual `cortex-clause-tally` verb be scoped there rather than reopened here.
4. **Plan Task 9's Files list named gitignored artifacts — plan hygiene only, no shipping impact.**
   `git check-ignore` confirms both `cortex/backlog/index.json` (`cortex/.gitignore:52`) and `index.md` (`:54`)
   are ignored. Commit `6895c9b9` contains exactly one file, the new ticket. The listing was a
   verification-output note, not an intent to commit; nothing landed wrongly.
5. **Requirement 10 vs the unscoped Edge Cases — Task 11's reading checked and endorsed.** Covered under
   Stage 2 above. The spec is internally inconsistent on scope (requirement phase-scoped, Edge Case unscoped);
   Task 11 resolved toward the stricter, ticket-premise-serving reading and pinned it. Correct.

## Requirements Drift

**State**: `detected`

**Findings**:
- `_emit_subcommand`'s optional-field drop was widened from `value is None` to "None or a blank string" for
  **every** optional field on **every** typed verb, not only the two `--reason` fields. Verified by execution:
  `feature-paused --feature h --slug "" --kind question` now writes `{ts, event, feature, kind}`, where the
  pre-change drop condition writes `{ts, event, feature, slug: "", kind}`. The spec names this as a
  Non-Requirement ("no requirement asserts it and no test pins it"), so it is an accepted side effect — but no
  requirements file records that typed-verb emission now drops blank optional strings generally.
  `cortex/requirements/lifecycle.md`'s rewritten bullet scopes the omission rule to `reason` alone, and the
  "Event emission and events-as-phase authority" section says nothing about optional-field omission.
- Minor, same mechanism: the clause diagnostic now reports the **lowercased** tag (`badA: x` → `clause tag
  'bada'`) while echoing the value verbatim. Captured by no requirement; harmless.

**Update needed**: `cortex/requirements/lifecycle.md`

## Suggested Requirements Update

- **File**: `cortex/requirements/lifecycle.md`
- **Section**: `### Event emission and events-as-phase authority`
- **Content**:

```
- Typed-verb emission omits any optional field whose value is absent or a blank string, rather than recording `""` — a blank names no axis a corpus tally can bucket on. The rule is general, not `reason`-specific: it covers `feature-paused --slug` on the same line. Falsy JSON values (`--tasks-total 0`, `--rework-cycles 0`, `--cycle 0`) are unaffected and still emit.
```

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": ["Coverage gap: refine.py's canonicalize_reason calls are pinned by no test — deleting both leaves tests/test_refine_reconcile_clarify.py green (15 passed), while the spec's Acceptance requires ' Exposure: x' to canonicalize 'from either writer'. Add one parametrized case to the existing suite.", "cortex/requirements/lifecycle.md:104 points at 'skills/refine/SKILL.md Step 4', but requirement 14 added a second restatement of the four tags at line 63 under Step 3; a maintainer following the pointer edits one of two sites.", "cortex/backlog/478-*.md cites skills/refine/references/clarify.md:32 for §5.2 in both Role and Touch points; line 32 is §5.1 and §5.2 is line 33 — off by one, twice.", "Non-blocking: the rejection stderr doubles the flag name (argparse's 'argument --reason:' plus the template's {flag}); requirement 4 is satisfied and the shape is deliberately unpinned.", "Non-blocking: refine.py's _DISCARDED_REASON_MSG warnings still gate on plain truthiness, so a whitespace-only reason on a suppressed row prints a spurious 'discarded' warning; verified it can never reach a written row."], "requirements_drift": "detected"}
```
