# Review: criticality-pins-the-corpus-to-the (cycle 2)

Tier `complex`, criticality `high` → Stage 1 (spec compliance) runs; Stage 2 (code quality) runs only if
Stage 1 has no FAIL. Stage 1 has no FAIL this cycle, so **Stage 2 runs** (it was skipped in cycle 1).

Test baseline accepted as given: `just test` → exit 0, 8/8 suites, re-run after both new commits. Not re-run
here.

**Scope of this cycle.** A scoped re-review, not a fresh full read. Cycle 1 rated R1–R7 and R9 PASS and R8
FAIL. Two commits landed since: `44059571` (the R8 fix, confined to the ADR) and `7e6f36fb` (the cycle-1
requirements-drift auto-apply). R8 is re-rated from scratch, R1 is re-checked as the regression the R8 fix
could plausibly have broken, `7e6f36fb` is checked against what cycle 1 asked for, and the remaining
requirements carry their cycle-1 ratings forward unchanged.

Known and accounted for, not rediscovered: the approved 0035 → 0036 ADR-number delta; `--tier-reason`
shipping with zero tests and zero callers; `--criticality-reason ""` writing an empty `reason` key.

---

## Stage 1 — Spec compliance

| Req | Rating | Basis |
|-----|--------|-------|
| R1 | **PASS** | Re-verified this cycle (regression check below) |
| R2 | **PASS** | Carried forward from cycle 1 |
| R3 | **PASS** | Carried forward from cycle 1 |
| R4 | **PASS** | Carried forward from cycle 1 |
| R5 | **PASS** | Carried forward from cycle 1 |
| R6 | **PASS** | Carried forward from cycle 1 |
| R7 | **PASS** | Carried forward from cycle 1 |
| R8 | **PASS** | Re-rated this cycle — see below |
| R9 | **PASS** | Carried forward from cycle 1 |

### R8 — The clause distribution is greppable without new tooling — **PASS** (was FAIL)

The recipe was **extracted programmatically** from the committed ADR rather than retyped: the fenced block
following the `Reading the clause distribution` heading in
`cortex/adr/0036-ceremony-relief-is-not-taken-on-the-criticality-axis.md` was sliced out by a regex, written
to a scratch file, and executed from the repo root **with stderr visible**.

Result — a populated `Counter`, exit 0, and **zero bytes on stderr**:

```
Counter({"Research established the ticket must modify _TicketBodySanitizer, the XSS boundary on #412's
shipped reader, not just add new routes": 1, 'backlog item #239 explicitly recorded criticality': 1,
'Per clarify.md §5 default': 1, 'Clarify rubric': 1, 'clarify-critic': 1,
'Manual Clarify reconciliation (dogfooding #285 workaround)': 1,
'Scope collapsed to 3 markdown files; no code, no skills/, trivially reversible': 1})
EXIT=0
```

Seven buckets, all seven pre-existing manual-path reasons. Acceptance holds on every clause:

- **Per-clause counts, `criticality_override` rows only.** The `r.get('event') == 'criticality_override'`
  filter survived the rewrite intact, so the 92 `sentinel_absence` rows and any `complexity_override` reason
  stay out of the tally — the merge R8's own text names as the reason a bare grep is invalid.
- **Across the whole corpus.** `find cortex/lifecycle -name events.log` matches **355** files, **166** of them
  under `archive/` — the `archive/` coverage that the `cortex/lifecycle/*/events.log` glob misses.
- **Exit 0, output produced.** Both halves fail on the pre-fix ADR (cycle 1 measured empty output and a
  `JSONDecodeError` on line 1 of the stream), so this discriminates against the shipped defect.
- **Without new tooling.** The fix is prose inside a code fence — no module, script, or verb was added.

Root cause is closed at the mechanism, not papered over. The corpus really is mixed-format: of **10,951**
concatenated lines, **4,727** do not parse as JSON (4,605 legacy YAML-format rows, 120 blanks, 2 malformed).
The new form skips any line not starting with `{`, wraps `json.loads` in `except ValueError` (the correct
superclass — `JSONDecodeError` subclasses it), and no longer redirects stderr. The two added paragraphs are
accurate and load-bearing: the "~4,600 lines" figure matches the 4,605 non-JSON-start count, the warning that
a suppressed traceback "reads identically to 'no clause data yet'" states the exact failure cycle 1 found,
and the note that pre-existing reasons are untagged free prose bucketed by whole sentence matches the seven
whole-sentence buckets the run actually produced — it names three of them verbatim and all three appear.

Portability checked beyond the shell it was authored in: the recipe is documentation meant to be pasted, and
the multi-line `python3 -c "…"` form embeds single quotes inside a double-quoted argument. Run under **zsh**
(the user's shell) it produces byte-identical output and exit 0, as it does under bash.

**Recorded deviation (non-blocking).** The ADR recipe no longer matches `spec.md:34`, which still holds the
broken one-liner — as does the plan's Task 5 verification clause (e) at `plan.md:107`. R8's Acceptance is
written as *"the following returns per-clause counts…"* with that one-liner inline, so read literally the
spec's own command still fails; read for substance — which is what the requirement's title states — the
shipped recipe satisfies it and the spec's version does not. I rate the substance and record the divergence:
a successor reading `spec.md` or re-running the plan's verification gets the pre-fix recipe, with nothing to
catch it (see Stage 2). Neither file is in this review's write scope.

### R1 — An ADR records the decision and its evidence — **PASS** (regression check)

The R8 fix touched only the ADR, so R1 is the one carried-forward rating it could have broken. Re-run:

- All five evidence literals present: `5.0%` (2), `2.6%` (2), `33.1%` (2), `24.7%` (1), `9.4%` (1).
- `bin/cortex-adr-citation-audit | python3 -c "…assert not duplicate_number"` exits **0**. 67 findings total,
  **0** of kind `duplicate_number`.

The finding count moved 66 → 67 since cycle 1 — corpus drift from concurrent lifecycles, all `slug_mismatch`
or `unresolved`, none of the only kind that can fire here. The `git show --stat` for `44059571` is one file,
+25/−1, entirely inside `## Reading the clause distribution`; the Context / Decision / Scope / Trade-off
sections and the unscoped-grep caveats below the fence are untouched.

### `7e6f36fb` — cycle-1 drift auto-apply — **faithful**

Verified rather than assumed. The landed bullet was compared **byte-for-byte** against the Content block in
cycle 1's own Suggested Requirements Update, parsed out of the previous `review.md`: **identical**, no
paraphrase, no truncation. It sits at `cortex/requirements/project.md:64` under the heading
`## Architectural Constraints` — the section cycle 1 named — appended after the sibling
`**The reviewer brief is a protocol-governed served surface**` bullet, matching the file's `- **Name**: …
→ ADR-NNNN` house form. One occurrence; the diff is `1 file changed, 1 insertion(+)` with no other edits.
Not re-flagged as drift.

---

## Stage 2 — Code quality

Surface: `cortex_command/refine.py` (`2d8e2575`), `tests/test_refine_reconcile_clarify.py` (`22ed33b0`),
`skills/refine/SKILL.md` (`5fbd32d9`).

**Overall: PASS with notes.** Nothing here is a blocker; the notes below are PARTIALs and observations.

### Naming consistency — **PASS with one note**

`_ALLOWED_REASON_CLAUSES` follows the two frozensets directly above it (`_ALLOWED_CRITICALITY`,
`_ALLOWED_COMPLEXITY`), including the module habit of a comment above the set explaining *why* the vocabulary
is closed. `_BAD_REASON_CLAUSE_MSG` follows `_UNSAFE_SLUG_MSG` — the module's only other `_*_MSG` constant —
in name, placement, and `str.format` keyword style, and the error text reuses its `cortex-refine: ` prefix.
Flag names match the sibling `--complexity` / `--criticality` pair in shape.

- **PARTIAL — the verb now carries both axis vocabularies on adjacent flags.** `--tier-reason` writes onto the
  `complexity_override` row and sits beside `--complexity`, whose own help text reads *"Explicit desired
  tier"*. The new flag picked the glossary-canonical name this same ticket just ratified (R9 defines *tier*),
  which is the right long-term direction, but the result is a parser where the same axis is `--complexity`,
  `--tier-reason`, and `complexity_override` within four lines. Not worth churning a shipped flag over;
  recorded so a future rename is a deliberate sweep rather than a surprise.
- **Note — `_reason_clause_ok` is a predicate that also writes to stderr.** The module's other bool-returning
  helper, `_lifecycle_start_present`, is pure. The impurity is contained (one call site, message ownership
  next to the constant) and the alternative — returning the message to the caller — would duplicate the
  formatting at both flag sites. Defensible; noted for consistency, not as a defect.

### Error handling — **PASS with one note**

The all-or-nothing property is real and structural, not incidental. Validation is hoisted above
`events_log.parent.mkdir(...)` **and** above the `rows` build, with an inline comment saying exactly that;
re-verified in a scratch directory that a rejected tag returns 2, leaves the seeded log at its original line
count, and creates no new directory. Exit code `2` matches the neighbouring `_UNSAFE_SLUG_MSG` guard rather
than inventing a code. Message goes to stderr with stdout empty, so a caller parsing the JSON envelope reads
nothing on the failure path. `except ValueError` in the ADR recipe (and `except json.JSONDecodeError` in the
test helper) are both correct for their contexts.

- **PARTIAL — only the first offending flag is reported when both are bad.** The guard is
  `if not _reason_clause_ok("--tier-reason", …) or not _reason_clause_ok("--criticality-reason", …)`, and
  `or` short-circuits. Verified: passing `--tier-reason "design-fork: x" --criticality-reason "alsobogus: y"`
  prints only the `--tier-reason` message and exits 2. An author with two bad tags fixes one, re-runs, and
  meets the second — two round-trips where one would do. The plan's own Risks section names `design-fork:` as
  the most likely rejected tier tag, so this is the realistic collision, not a contrived one. Cheap to fix by
  evaluating both before branching; not worth blocking a cycle-2 approval.

### Plan Verification steps actually executed — **PARTIAL**

Cycle 1 confirmed Tasks 1–4, 6 and 7's Verifications were executed and discriminating. Re-checked this cycle:

- **Task 1** was correctly re-run after the rework — its Status line records `(rework: R8 recipe hardened;
  original 2b842b72)` against `44059571`, and I re-executed the Verification myself: five literals present,
  `duplicate_number` assertion exits 0.
- **Task 5's Verification is now stale as well as weak.** Cycle 1 recorded that clauses (b) and (d) cannot
  fail. The rework did **not** update clause (e) at `plan.md:107`, which still embeds the pre-fix one-liner —
  so re-running the plan's own Task 5 gate today exercises the broken recipe against a synthetic clean-JSONL
  corpus and still prints `PASS e`. The verification that missed the defect would miss it again. This is the
  concrete cost of the plan's deliberate "no test pins the recipe" Risk: the recipe is now stated in three
  places (`spec.md:34`, `plan.md:107`, the ADR) with two of them wrong and no drift surface to notice.
- **Task 6** meets its Verification and exceeds its brief: all five specified cases landed.
- **Task 7** meets its Verification — 3 `criticality-reason` matches in `SKILL.md`, both contiguous-substring
  pins intact with the flag appended after each pinned span, and the `plugins/cortex-core/` mirror re-checked
  byte-identical this cycle.

### Pattern consistency with surrounding code — **PASS**

- `refine.py`: the `**({"reason": …} if … is not None else {})` splat matches the `from_seeded` conditional
  key immediately below it, so the two optional keys on the same row read alike. `reason` is positioned
  between `to` and `gate` to match `lifecycle_event.py`'s declared field order, and the comment explains the
  *why* of the position rather than restating the code — the module's prevailing comment style.
- Tests: they use the file's existing `_seed_events` / `_lifecycle_start_line` helpers and `main([...])` entry
  rather than a new harness, and the two new helpers (`_override_rows`, `_only`) carry docstrings justifying
  their existence against the pre-existing `_count_overrides`. The assertion quality is the best part of this
  change set: the rejection case pins exit code **2 exactly** and asserts the file's bytes are unchanged, and
  the omission case asserts the rows *were* appended with the right `from`/`to` before asserting the key is
  absent — both closing the "a verb that never ran also passes" hole that Task 5's hand-run gate left open.
  Key order is pinned as a list equality, so a future writer that moves `reason` goes red.
- `SKILL.md`: the flag was appended to both invocations and the explanatory line placed after them, matching
  Step 4's existing bullet-then-prose shape; it states the closed set, the optionality, and the
  omit-rather-than-fill rule in one line without duplicating the verb's `--help`.

### Coverage gaps (carried forward, still open)

- `--tier-reason` ships with **zero tests and zero callers** — confirmed again. Nothing goes red if it is
  deleted, which `project.md`'s deletion-bias clause treats as a presumption of removal. R7 is scoped to
  criticality and R4 only requires the flag to exist, so this is not a spec failure; it is a flag whose only
  defence is that a future ticket wants it.
- `--criticality-reason ""` writes `"reason": ""` — filtered out of the tally by the recipe's
  `if r.get('reason')` guard, so it cannot pollute the data, but it is an empty-evidence key on the row.
- A tag with trailing whitespace (`"exposure : x"`) is rejected, deliberately and per the function's
  docstring. Second-most-likely author surprise after the inner-colon case the plan already priced.

---

## Requirements Drift

**State:** detected

Cycle 1's drift finding (the override-reason clause vocabulary) is **applied and closed** by `7e6f36fb` and
is not re-reported. One finding remains outstanding, surfaced by the R8 defect itself.

**Findings:**
- **The lifecycle events corpus is not uniformly JSONL, and no loaded requirement says so.** 4,605 of the
  10,951 lines under `cortex/lifecycle/**/events.log` are legacy YAML-block rows, plus 120 blanks and 2
  malformed rows — 43% of the corpus. `project.md` records a **Historical compatibility shim pattern** for
  `pipeline-events.log`, and the "readers tolerate every prior shape forever" rule exists only in
  `skills/refine/references/clarify-critic.md`, which is a shipped surface scoped to `clarify_critic` events
  and therefore not a governance home for a repo-corpus fact. The consequence is measured, not hypothetical:
  a recipe written against the assumption of one JSON object per line shipped through spec, plan, a task
  verification and a full review cycle before failing on the first line of the real corpus — and failing
  *silently*, because the documented form suppressed stderr. Anything that walks this corpus needs the same
  two guards, and nothing states them.

**Update needed:** `cortex/requirements/project.md`

---

## Suggested Requirements Update

**File:** `cortex/requirements/project.md`
**Section:** `## Architectural Constraints`
**Content:**

```
- **The lifecycle events corpus is mixed-format, not uniform JSONL**: 4,605 of the 10,951 lines under `cortex/lifecycle/**/events.log` (including `archive/`, which is 166 of the 355 files) are legacy YAML-block rows, alongside ~120 blanks and a few malformed rows — so any reader or documented recipe that walks the corpus skips lines not starting with `{` and guards `json.loads`, rather than assuming one JSON object per line. Never suppress such a reader's stderr: named evidence (#452) is a corpus recipe that shipped ending in `2>/dev/null`, aborted on line 1, and printed nothing — indistinguishable from "no data yet" while seven reasoned rows were already recorded. → ADR-0036.
```

---

```
{"verdict": "APPROVED", "cycle": 2, "issues": ["Non-blocking: the fixed clause-distribution recipe lives only in cortex/adr/0036-ceremony-relief-is-not-taken-on-the-criticality-axis.md. spec.md:34 and the plan's Task 5 verification clause (e) at plan.md:107 both still embed the pre-fix one-liner, so the plan's own gate would print PASS e against the broken form and a successor reading the spec gets the recipe that fails. Three statements of one command, two of them wrong, with no drift surface between them.", "Non-blocking: --tier-reason still has zero tests and zero callers; nothing goes red if it is deleted, which is the deletion-bias presumption-of-removal condition. Recorded in cycle 1 and unchanged.", "Non-blocking (Stage 2): validation short-circuits on `or`, so when both --tier-reason and --criticality-reason carry bad clause tags only the first is reported. Verified: `--tier-reason 'design-fork: x' --criticality-reason 'alsobogus: y'` prints only the tier message and exits 2, costing an author two fix round-trips. `design-fork:` is the exact tag the plan's Risks section predicts a tier author will reach for.", "Non-blocking (Stage 2): the verb carries both axis vocabularies on adjacent flags - --tier-reason writes the complexity_override row and sits beside --complexity, whose help text calls it the tier. The new flag uses the name R9's glossary entry just ratified, so the fix is a deliberate rename sweep, not a revert."], "requirements_drift": "detected"}
```
