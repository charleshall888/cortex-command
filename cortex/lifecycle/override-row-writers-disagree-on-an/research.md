# Research: Make `cortex-lifecycle-event`'s typed override verbs record a `reason` the way `reconcile-clarify` does

Clarified intent: the two typed override verbs (`criticality-override`, `complexity-override`) should omit an empty
`--reason` rather than writing `"reason": ""`, and should validate its clause tag against the same closed set
`refine.py` already enforces — so ADR-0036's clause tally reads one vocabulary from both writers.

Governing requirement is **`cortex/requirements/lifecycle.md:104`**, not `cortex/requirements/project.md:64` as the
ticket states three times. `project.md`'s bullet is a one-line pointer ("the set an override `reason` may lead with is
closed and wheel-owned. → cortex/requirements/lifecycle.md") and contains neither the divergence, the phrase "tracked
as follow-up", nor `#474`. The ticket's Edges instruction to reword `project.md:64` on a wontfix branch is therefore
misaddressed; the sentence to reword lives at `lifecycle.md:104`.

## Corpus measurement (re-run for this lifecycle)

Measured across all five sibling repos holding `cortex/lifecycle/` (cortex-command, wild-light, gaggimate-barista,
pixel-art-generator, Team-Builder-Bot), `archive/` included, guarding `json.loads` and skipping non-`{` lines per
ADR-0036's recipe.

**554 override rows. 508 carry no `reason` key. 46 carry one. Zero empty strings anywhere.**

| Writer | valid clause tag | colon-less (validator permits) | bogus tag (validator rejects) |
|---|---|---|---|
| `refine.py` `reconcile-clarify` (validated) | 4 | 0 | 0 |
| `_emit_subcommand` typed verbs (unvalidated) | 0 | 14 | 28 |

**The raw 28 overstates the case.** Time-anchored to when the clause vocabulary shipped — commit `2d8e2575`,
2026-08-07 14:49 UTC — 24 of the 28 predate its existence and are not evidence about author behavior under a
vocabulary that did not yet exist. Post-vocabulary the corpus holds **6 reason rows total**: 4 through the validated
path (all valid tags) and **2 through the unvalidated CLI** (one `research:` that would be rejected, one colon-less
that is permitted).

The load-bearing datum survives that correction. In
`cortex/lifecycle/requirements-loader-matches-index-tags-against/events.log`, the same agent in the same lifecycle
wrote a bogus `research:` through the unvalidated CLI at `19:01:11Z` and a correct `exposure:` through the validated
verb **nine seconds later** at `19:01:20Z`. The ticket's `24 free-prose rows` figure is not reproducible as stated;
the reproducible figures are 28 bogus / 14 colon-less all-era, and 1 bogus / 1 colon-less post-vocabulary.

## Codebase

**The table and its dispatcher.** `_EVENT_SUBCOMMANDS` (`cortex_command/lifecycle_event.py:257`) is typed
`dict[str, tuple[str, list]]` — the inner `list` is unconstrained, so nothing blocks a wider tuple statically. The
optional-field drop under change is `lifecycle_event.py:364-365`:
`if value is None and not required: continue`.

**Arity-sensitive sites.** Three hard 5-tuple unpacks break on a 6th element: `lifecycle_event.py:362` (dispatcher),
`lifecycle_event.py:390` (`_build_parser`), and `tests/test_lifecycle_event_roundtrip.py:113`. Two sites are tolerant:
`tests/test_lifecycle_event_roundtrip.py:111` (`(flag, *_rest)`) and
`cortex_command/lifecycle/tests/test_review_brief_cli.py:407` (`spec[4]`, which survives a 6-tuple or NamedTuple but
breaks under a plain dataclass).

**`_emit_subcommand` has exactly one caller** (`lifecycle_event.py:437`). Other consumers of the table:
`cortex_command/tests/test_lifecycle_event.py:909`, `tests/test_lifecycle_event_roundtrip.py`,
`cortex_command/lifecycle/tests/test_review_brief_cli.py:406`.

**No bash parity implementation exists** for `cortex-lifecycle-event`; it is a pure console script
(`pyproject.toml:127`). `tests/test_cortex_lifecycle_state_parity.py` and its
`tests/fixtures/cortex-lifecycle-state/*override*` fixtures belong to a different CLI (`cortex-lifecycle-state`, a
reader/reducer) and carry no `reason` key, so they are insensitive to this change.

**Circular import is real and forces the validator to move.** `refine.py:29` already does
`from cortex_command.lifecycle_event import log_event_at`, and `common.py` imports stdlib only. So `lifecycle_event`
cannot import `refine`; the shared predicate must relocate to a module both can import.

**No test pins the behavior being changed** on the typed-verb side. `--reason` is never exercised for the typed
subcommands at all. `cortex_command/tests/test_lifecycle_event.py:613-626` (`test_set_empty_value`) pins
`--set reason=` → `"reason": ""` on the **generic** `log` path, which is out of scope and stays green.
`refine.py`'s side is fully pinned by `tests/test_refine_reconcile_clarify.py` (`:663` empty-reason omission, `:459`
bad-tag rejection, `:540`/`:570` colon-less and inner-colon passthrough).

**Exit-code precedent.** `lifecycle_event.py`'s only hand-rolled failure is `CortexProjectRootError` → stderr +
`return 1` (`:369-371`); argparse `choices=` failures exit 2. `refine.py`'s hand-rolled validation failures return 2
(`:369`, and the unsafe-slug guard at `:352-354`). Exit 2 is the consistent code for bad input here.

**`feature-paused --slug`** (`lifecycle_event.py:289`) has no live caller: grepping `skills/`, `hooks/`, `claude/`,
`bin/`, `docs/` for `feature-paused` returns only the table, tests, and doc mentions. Every live `feature_paused` row
is written from Python with a hardcoded non-empty slug (`lifecycle/plan_decision.py:203`,
`lifecycle/advance.py:419-420`), bypassing `_emit_subcommand` entirely.

**No plugin mirror for `cortex_command/*.py`.** `just build-plugin` rsyncs only `skills/`, specific `hooks/*.sh` and
`claude/hooks/*.sh`, and `bin/cortex-*`. Editing `lifecycle_event.py`, `refine.py`, or `common.py` needs no mirror
rebuild. **But any `skills/*/SKILL.md` edit does** — `plugins/cortex-core/skills/{refine,build}/SKILL.md` are
byte-identical mirrors, rebuilt from staged blobs by the pre-commit hook.

## Tradeoffs & Alternatives

**No machine caller shells out to these verbs.** Every Python emitter uses `log_event`/`log_event_at` directly
(`plan_decision.py:56`, `review_verdict.py:81`, `spec_approve.py:114`, `finalize.py:86`, `advance.py:101`,
`review_brief.py:93`). The only invocations of the two override verbs anywhere are two lines of skill prose:
`skills/refine/SKILL.md:63` and `skills/build/SKILL.md:71`. A non-zero exit is read by an LLM in a transcript; no
process aborts. Nothing in `cortex_command/overnight/` or `cortex_command/pipeline/` emits them, so the
non-interactive emit hazard is currently nil.

**`cortex-lifecycle-event` is not in the never-crash served-envelope class** (`cortex/requirements/lifecycle.md:90`
scopes that to machine verbs), so a non-zero exit is permitted by contract.

**Decision A — how the per-field rule is expressed.**
- *6th tuple element* — breaks all three hard unpack sites for a value that is inert on 19 of 21 specs. Rejected.
- *NamedTuple/dataclass refactor* — a 21-spec refactor bought for two fields with no second client;
  `project.md`'s "complexity must earn its place" and the Solution-horizon "current knowledge, not prediction" clause
  both say no. Keep as the named upgrade path.
- *Side frozenset of `(command, flag)` pairs* — zero arity change, zero test churn.
- *A third `kind` value* (`_CLAUSE`) — `kind` is a plain string; `_build_parser:396` branches only on `== _JSON`,
  `_emit_subcommand:362` passes it through, `log_event:170` discards it. Breaks **zero** unpack sites, so the stated
  reason for rejecting a 6th element does not apply, and one kind could drive both the parser binding and the drop.
- *Simplest correct form* — enumerating the table, the optional fields with no `choices` and kind `_STR` are exactly
  three (`feature-paused --slug`, and the two `--reason`). Every other optional is `choices`-constrained (argparse
  already rejects `""`) or `_JSON` (`json.loads("")` raises). So
  `if (value is None or value == "") and not required: continue` is **behaviorally identical to a side table over the
  entire current table**, with no side structure and no registration step a future optional string field can silently
  miss — which is the same silent-omission failure class this ticket exists to close. Verified by execution:
  `--tasks-total 0` and `--rework-cycles 0` still emit `0`, so falsy-but-meaningful JSON is untouched by construction.

**Decision B — reject or drop on a bad clause tag.** Reject is the table's own norm (six other fields exit 2 on a bad
value via `choices=`). Against it: a reject discards the **whole override row**, including `from`/`to`, which
`common.py:975,982`'s `reduce_lifecycle_state` supersedes tier and criticality from — so the lost row is routing
state, not annotation, and `skills/refine/SKILL.md:63`'s blanket "Non-zero exit → surface stderr and halt" would
strand the tier change. Warn-and-**drop-the-reason** is precedented in the sibling module: `_DISCARDED_REASON_MSG`
(`refine.py:60-63`) is the established idiom for "the row happened, the reason didn't ride it, here is a stderr line",
and unlike prose it is pinnable by a test on the verb. Warn-and-write is strictly worse than both — it reproduces the
"row looks filled, tallies empty" failure the ticket exists to kill.

**Decision C — `feature-paused --slug`.** No. `--slug ""` is unreachable by any live caller (see Codebase), so adding
it is symmetry with zero mechanism behind it. Separately: the typed `feature-paused` subcommand's only consumers are
its own tests, making it a `project.md` deletion candidate — flag it, do not fold it in.

**Do-nothing branch, weighed honestly.** On a strict reading of CLAUDE.md's front-door bar ("measured cost or observed
failure, not a hypothetical"), the empty-reason half **fails**: zero instances in 554 rows. Pulling the other way: the
marginal cost is one condition on a line already being touched, and the do-nothing branch is not free either — it
requires permanently editing `lifecycle.md:104` to record the divergence as accepted, roughly the same edit.

## Adversarial

**The one piece of real evidence cuts against hard validation.** The 9-second pair admits a competing reading at least
as strong as "the validator produced the correct tag": `skills/refine/SKILL.md:67` names the four tags inline at the
`reconcile-clarify` invocation, while `skills/refine/SKILL.md:63` and `skills/build/SKILL.md:71` — the two CLI override
lines — name none. The agent tagged correctly exactly where it had been told the vocabulary. That is a prose-absence
failure, and prose at the invocation site has never been tried there, so choosing code enforcement first is not
evidence-driven.

**The false-rejection surface is severe.** Verified by executing `_reason_clause_ok`:

```
'exposure: x'                       -> True     'Exposure: x'                       -> False
'other:x'                           -> True     ' exposure: x'                      -> False
''                                  -> True     'blast radius: unbounded'           -> False
                                                'Chose high: consumer-facing'       -> False
                                                'see research.md line 40: the fork' -> False
                                                'design-fork: two options'          -> False
```

The predicate splits on the **first colon anywhere**, unstripped and case-sensitive. So a capitalized tag — the most
likely thing a model writes — and any one-line reason containing a mid-sentence colon are both hard failures. In the
corpus, 28 of 46 reason rows lead with a colon-token that is not a valid tag; era-mixing weakens that as evidence of
post-vocabulary misbehavior but not as evidence of how reasons are actually written.

**A hard-enforced criticality set on the tier verb contradicts a shipped decision.**
`cortex/lifecycle/tier-overrides-record-no-reason-and/spec.md:32` (#471) declines the tier vocabulary as a deliberate
Non-Requirement and records verbatim: *"This slice does not close #471; a tier author reaching for `design-fork:` is
still rejected"*, that classifying the existing free-prose tier reasons put roughly half on `other`, and that *"a
resulting distribution dominated by `other` is evidence **for** a tier-specific vocabulary, not against it"*, with a
re-measure trigger. `complexity-override` is the tier verb. Hard-rejecting tier reasons against the criticality set
enforces the pairing #471 measured and documented as wrong — and manufactures the `other`-dominated distribution #471
designated as the trigger for forking the vocabulary. Under CLAUDE.md's Solution-horizon clause ("a follow-up is
already planned"), the durable shape is an axis-keyed lookup, not one shared set promoted to a leaf module.
Compounding this: `#471` is `status: complete` while its own spec says it does not close #471, so the tier-vocabulary
fork is tracked by no open ticket.

**`_reason_clause_ok` cannot be reused as an argparse `type=` callable.** It returns `bool` and prints to stderr
(`refine.py:319-328`); a `type=` callable must raise `ArgumentTypeError`. Wrapping it emits two-to-three messages for
one typo. Refactoring it to raise breaks `refine.py:356-368`, whose comment is explicit that both predicates run
**unconditionally, non-short-circuiting** so a caller with two bad tags sees both in one run — behavior pinned by #471
spec R8 ("removing one `_reason_clause_ok` call turns it red"). An exception-based validator cannot report both flags.

**Unpriced co-edits in a naive move.** `_BAD_REASON_CLAUSE_MSG` (`refine.py:53-55`) hardcodes the literal
`"cortex-refine: "`; moved as-is, `cortex-lifecycle-event` would print a message blaming a different tool.
`refine.py:937,951` build argparse help text from `_ALLOWED_REASON_CLAUSES`.

**`common.py` is a defensible but not obligatory home.** ~60 modules import it; it is the dependency leaf, importing
zero cortex modules — which means the cycle argument justifies moving *out of* `refine.py` but does not single out
`common.py`. A new leaf module (`cortex_command/override_reason.py`, importing only `sys`) is equally cycle-safe and
touches nothing else. `common.py:1-28` is a curated docstring enumerating its public surface, and CLAUDE.md
lifecycle-gates `common.py` by name.

**The out-of-scope carve-out leaves the divergence partly open.**
`log --event criticality_override --set from=low --set to=high --set reason=` writes a genuine override row with
`"reason": ""`, bypassing both fixes in one line. So `lifecycle.md:104`'s sentence "Both writers of an override row …
with `reason` omitted rather than nulled" stays false unless it is rescoped to the **typed** writers and names the
generic `log` form as the ADR-0020 escape hatch that carries no field validation.

**Restatement-site drift.** `lifecycle.md:104` states the vocabulary is restated in `skills/refine/SKILL.md` Step 4
and ADR-0036, "adding a tag edits all three". Adding tag names at `skills/refine/SKILL.md:63` and
`skills/build/SKILL.md:71` makes it five sites; unless the enumeration is updated in the same change, the next tag
addition mechanically misses two. Neither ratchet constrains this growth: `scripts/ratchet_refs.py:65-69` measures
only `references/` dirs and `pipeline/prompts`, not `SKILL.md` bodies, and the L1 ratchet covers frontmatter only.

**Upgrade ordering is backwards for a narrowing change.** No sibling repo pins a cortex-command version, so the wheel
lands everywhere at once while plugin prose ships separately via `/plugin install`. `lifecycle.md:104` mandates the
wheel land before the prose — correct when *widening* the vocabulary, exactly wrong when *narrowing* it: a wheel ahead
of the plugin leaves every consumer running old prose against a validator that now rejects any colon.

**No consumer would observe a newly-absent key.** No Python module reads `reason` off an override row.
`cortex_command/overnight/report.py` contains no `override` string. The dashboard renders `reason` generically at
`cortex_command/dashboard/templates/feature_cards.html:172` via `r.get('reason') or … or '—'`, so `""` already renders
identically to an absent key. ADR-0036's tally buckets `""` correctly via `if r.get('reason')`. The ticket's stated
harm — "a human reading the row sees a `reason` key and assumes one was recorded" — requires hand-reading raw JSONL
after someone deliberately passed `--reason ""`, which has never happened in 554 rows.

## Open Questions

- **Does clause validation ship at all in this ticket, or does prose-at-the-invocation-site ship first?** *Deferred to
  Spec, with a stated lean.* The Adversarial angle's sequencing argument is sound — #471's own spec imposed a
  re-measure discipline on itself, and A4-style prose has never been tried at the two CLI call sites. But the tier-axis
  contradiction below may make code validation on `complexity-override` wrong regardless of sequencing, which Spec must
  settle first.
- **Can `complexity-override` be validated against the criticality set at all, given #471 declared that pairing
  wrong?** *Deferred to the Spec interview, which must close it — this is the ticket's central design fork and it turns
  on a scope judgment (whether to fork the vocabulary here) that research cannot settle by reading.* Three shapes:
  (a) validate `criticality-override` only, leaving the tier verb unvalidated until the vocabulary forks;
  (b) axis-keyed lookup `{event → clause set}` now, forking the vocabulary as part of this ticket (scope growth,
  and #471 deliberately declined it); (c) validate both against the shared set, accepting that `design-fork:` is
  rejected. The Codebase and Tradeoffs angles assumed (c); the Adversarial angle argues (c) is a redo-in-waiting.
- **Reject-and-discard-the-row versus accept-the-row-and-drop-the-reason.** *Deferred to Spec as a live contradiction
  between angles — recorded rather than reconciled, because both positions rest on verified facts that point opposite
  ways.*
  Tradeoffs recommends reject (exit 2, table norm, consistent with the sibling writer); Adversarial shows the reject
  discards routing state that `common.py:975,982` supersedes from, and points at the precedented
  `_DISCARDED_REASON_MSG` idiom as both safer and test-pinnable. Spec must pick one; if reject, the
  `skills/refine/SKILL.md:63` "halt" instruction needs a retag-and-retry amendment that no test can hold in place.
- **Is the empty-reason half earned?** *Resolved: yes, but not on observed failure.* Zero instances in 554 rows and no
  consumer that would see one. It rides on contract coherence and near-zero marginal cost — one condition on a line
  already being edited. Spec and the commit body must state this explicitly rather than let it read as evidenced.
- **Where does the shared predicate live, and does it keep its bool-and-print shape?** *Deferred to Spec.* Candidates
  are `common.py` (lifecycle-gated, curated docstring, ~60 importers) and a new leaf `override_reason.py`. Whichever
  is chosen must also carry `_BAD_REASON_CLAUSE_MSG`'s hardcoded `"cortex-refine: "` prefix and the help-text builders
  at `refine.py:937,951`, and must preserve `refine.py`'s non-short-circuit two-message behavior pinned by #471 R8.
- **Should `_reason_clause_ok`'s matching be loosened** (strip, case-fold, treat the prefix as a claimed tag only when
  it is a single token) so a capitalized tag or a mid-sentence colon is not a hard failure? *Deferred to Spec.* This is
  a behavior change to the already-validated `refine.py` path, so it is scope growth — but shipping validation on a
  second writer without it multiplies the false-rejection surface measured above.
- **Does `lifecycle.md:104` get rescoped to the typed writers in this change?** *Resolved: yes, unavoidably.* The
  generic `log --set` escape hatch keeps `"reason": ""` reachable, so the current wording is false either way. The
  same edit should correct the restatement-site enumeration and add the widening-versus-narrowing ordering caveat.
- **Should `#471` be reopened or a successor filed for the tier vocabulary?** *Deferred — out of scope for this
  ticket's build, but Spec should record it as a follow-up.* #471 is `status: complete` while its spec says it does not
  close #471.
