# Specification: override-row-writers-disagree-on-an

Backlog item: `474-override-row-writers-disagree-on-an-empty-reason-and-emit-subcommand-validates-no-clause-tag`
Research: `cortex/lifecycle/override-row-writers-disagree-on-an/research.md`

## Problem Statement

An override row's `reason` has two writers that disagree. `refine.py`'s `reconcile-clarify` validates both of its reason
flags against the closed clause set and omits the key on an empty value; `cortex-lifecycle-event`'s two typed override
verbs validate nothing and write `"reason": ""`. The disagreement is not axis-shaped — `reconkile-clarify` enforces the
criticality set on `--tier-reason` too (`refine.py:364`), so `research: …` is rejected there today and accepted by the
CLI verb writing the same `complexity_override` row. #471 deferred closing that split to this ticket by name.

The evidence is small and pointed in one direction, and the spec states it plainly rather than inflating it. Across
five sibling repos, 554 override rows: **zero** carry `reason: ""`, so the empty-reason half has no observed instance
and rides on contract coherence, not measured harm. Post-vocabulary, three reason rows were written through the
unvalidated CLI path and **all three are `complexity_override`** — the tier axis. One is mis-tagged (`research: …`,
2026-08-07T19:01:11Z), written nine seconds before the same agent tagged correctly through the validated verb in the
same lifecycle. An earlier draft of this spec proposed exempting the tier axis; that would have left every observed
defect unfixed, which is why requirement 7 validates both.

The beneficiary is the successor who reads the clause distribution to decide whether ADR-0036's deferred
criticality-rubric change is justified. That successor is served only if the validator and the tally agree on what a
tag is — requirements 5, 6 and 7 exist to keep those two definitions identical.

## Phases

- **Phase 1: Relocate and loosen** — move the clause predicate to a home both writers can import, narrow its
  false-rejection surface, and canonicalize what gets stored so the tally can still count it.
- **Phase 2: Wire the typed verbs** — clause validation and the empty-reason drop on `_emit_subcommand`'s parser and
  dispatcher.
- **Phase 3: Reconcile the record** — align the tally recipe, correct `lifecycle.md:104`, add tag guidance at both CLI
  call sites, and file the tier-vocabulary successor.

## Requirements

1. **The clause predicate and its allowed set live in a module both writers can import.** A new leaf module
   `cortex_command/override_reason.py` holds `ALLOWED_REASON_CLAUSES` and the predicate; it imports no `cortex_command`
   module. Acceptance: `uv run python -c "import cortex_command.override_reason as m; print(sorted(m.ALLOWED_REASON_CLAUSES))"`
   prints `['consequence', 'exposure', 'other', 'reversibility']` (HEAD: `ModuleNotFoundError`);
   `grep -c "^from cortex_command\|^import cortex_command" cortex_command/override_reason.py` returns `0`.
   **Phase**: Relocate and loosen

2. **`refine.py` consumes the relocated predicate rather than defining its own.** Acceptance:
   `grep -c "_ALLOWED_REASON_CLAUSES *[:=] *frozenset" cortex_command/refine.py` prints `0` (HEAD: `1`, the definition
   at `refine.py:50`), and `grep -c "override_reason" cortex_command/refine.py` prints at least `1` (HEAD: `0`).
   **Phase**: Relocate and loosen

3. **The two `reconcile-clarify` help builders re-point at the relocated set, and keep enumerating it.** The relocation
   has two co-edits inside the parser that the definition-site greps above cannot see: `refine.py:939` interpolates
   `", ".join(sorted(_ALLOWED_REASON_CLAUSES))` into `--criticality-reason`'s help string (opened at `:937`), and
   `--tier-reason`'s help at `:951` inherits the vocabulary by reference. Leaving either behind means the removed name
   survives in the parser, or the four tags stop appearing in `--help` at all — the only place a CLI author can
   discover them. Acceptance: `grep -c "_ALLOWED_REASON_CLAUSES" cortex_command/refine.py` prints `0` (HEAD: `5`); and
   — **regression guard**, true on HEAD and required to stay true —
   `uv run python -m cortex_command.refine reconcile-clarify --help 2>&1 | tr '\n' ' ' | tr -s ' ' | grep -c 'consequence, exposure, other, reversibility'`
   prints `1`. **Phase**: Relocate and loosen

4. **The diagnostic message names the invoking verb, not a hardcoded `cortex-refine`.** `_BAD_REASON_CLAUSE_MSG`
   (`refine.py:53-55`) currently hardcodes `"cortex-refine: "`. The relocated message takes the program name as a
   parameter. Acceptance: `cortex-lifecycle-event criticality-override --feature x --from low --to high --reason "zzz: y" 2>&1`
   contains `cortex-lifecycle-event` and does not contain `cortex-refine` (HEAD: emits no diagnostic at all, so the
   first half is false). **Phase**: Relocate and loosen

5. **A leading tag is only claimed when it is a single whitespace-free token, matched case-insensitively after
   stripping.** So `Exposure: x` and ` exposure: x` are recognized as the tag `exposure`, and `blast radius: unbounded`,
   `Chose high: consumer-facing`, and `see research.md line 40: the fork` are treated as untagged prose rather than
   rejected. Acceptance: a test asserts all five of those strings pass the predicate and that `zzz: y` fails; running
   it against the pre-change predicate turns it red on at least the `Exposure: x` case. **Phase**: Relocate and loosen

6. **A recognized tag is canonicalized in the stored value, so the validator and the tally agree on what a tag is.**
   Requirement 5 widens *matching* only; without this requirement, `Exposure: x` is certified valid and then stored
   verbatim, and ADR-0036's tally — `r['reason'].split(':')[0]`, unstripped and case-sensitive — counts `exposure`,
   `Exposure`, and ` exposure` as three separate clauses. The current predicate is deliberately unstripped for exactly
   this reason (`refine.py:311-313`: "unstripped, because that is exactly the key a corpus tally buckets on"), so
   loosening the match without canonicalizing the write would break an isomorphism the code documents. When a tag is
   recognized, the written reason leads with the canonical lowercase tag followed by `: ` and the unmodified body.
   Untagged prose is written verbatim, unmodified. Acceptance: emitting
   `criticality-override --reason " Exposure: it feeds spec authoring"` appends a row whose `reason` starts with the
   exact bytes `exposure: ` (HEAD: the row is written with the leading space and capital `E` intact); emitting
   `--reason "blast radius: unbounded"` appends that string byte-for-byte unchanged.
   **Phase**: Relocate and loosen

7. **Both override axes validate against the same clause set.** `criticality_override` and `complexity_override` both
   reject an unrecognized single-token tag. This matches what `reconcile-clarify` already enforces on `--tier-reason`
   (`refine.py:364`) and what #471 recorded — "The tier clause vocabulary stays the criticality set for now" — so the
   two writers of a `complexity_override` row stop disagreeing, which is the ticket's stated purpose. Acceptance: the
   same reason string is routed identically by both writers —
   `cortex-lifecycle-event complexity-override --feature x --from moderate --to complex --reason "design-fork: two options"`
   exits non-zero and appends nothing (HEAD: exits 0 and appends the row), matching
   `reconcile-clarify --tier-reason 'design-fork: two options'`, which rejects it on HEAD today.
   **Phase**: Wire the typed verbs

8. **`refine.py`'s non-short-circuit two-message behavior is preserved.** Both `--tier-reason` and
   `--criticality-reason` are still validated unconditionally in one run, each emitting its own diagnostic, per #471
   R8. Acceptance: (a) `uv run python -m pytest tests/test_refine_reconcile_clarify.py` exits 0.
   (b) `uv run python -m cortex_command.refine reconcile-clarify --lifecycle-slug zzz-nonexistent-probe --complexity moderate --criticality low --tier-reason 'badA: x' --criticality-reason 'badB: y'`
   exits 2 and prints exactly two stderr lines, one naming `--tier-reason` and one naming `--criticality-reason`.
   Both are **regression guards** — true on HEAD and required to stay true.
   Note deliberately: these guards cannot detect requirements 5 and 6, because every reason literal in that test file
   is a valid lowercase tag, a single-token bogus tag, `plain text`, or `""` — none is a string requirement 5 flips.
   Requirements 5 and 6 carry their own acceptance for that reason; this requirement claims only that the relocation
   does not weaken #471's pin, not that the phase as a whole is behavior-preserving. **Phase**: Relocate and loosen

9. **A rejected clause tag writes nothing and exits 2.** Validation runs at argparse parse time, so no partial row can
   land. Acceptance: on a lifecycle whose `events.log` is byte-copied first,
   `cortex-lifecycle-event criticality-override --feature x --from low --to high --reason "zzz: y"` exits 2 and the
   log is byte-identical to the copy. **Phase**: Wire the typed verbs

10. **An empty or whitespace-only `--reason` omits the key rather than writing `""`.** This half has **zero** observed
    instances in 554 corpus rows and no consumer that would render one differently — it rides on contract coherence and
    near-zero marginal cost, not on measured harm, and must not be described as evidenced. Acceptance:
    `cortex-lifecycle-event criticality-override --feature x --from low --to high --reason ""` appends a row for which
    `python3 -c "import json,sys; print('reason' in json.loads(sys.stdin.read()))"` prints `False` (HEAD: `True`).
    **Phase**: Wire the typed verbs

11. **Falsy-but-meaningful JSON values still emit.** Acceptance:
    `cortex-lifecycle-event feature-complete --feature x --tasks-total 0 --rework-cycles 0` appends a row containing
    `"tasks_total": 0` and `"rework_cycles": 0`. This passes on HEAD and is a regression guard, not a new behavior.
    **Phase**: Wire the typed verbs

12. **ADR-0036's tally recipe drops keys outside the allowed set.** The recipe is an unconditional
    `c.update([r['reason'].split(':')[0]])` that never consults the clause set, so the "untagged prose" category
    requirements 5 and 6 create is invisible to the only consumer: `blast radius: unbounded` still becomes a bucket
    named `blast radius`, which is precisely the "whole-sentence bucket masquerading as a clause" this spec names as
    the harm. The recipe gains a membership check so untagged prose is counted as untagged rather than as a clause.
    Acceptance: the recipe's code block contains a test against the allowed set; running the amended recipe over a
    fixture containing `exposure: a`, `Exposure: b`, and `blast radius: c` yields exactly one `exposure` bucket of
    count 2 plus one untagged bucket, where the HEAD recipe yields three buckets of count 1.
    **Phase**: Reconcile the record

13. **`cortex/requirements/lifecycle.md`'s "Override-reason clause vocabulary" bullet (line 104 at HEAD) is corrected
    on four counts.**
    (a) *Ownership.* The pointer moves off `cortex_command/refine.py:_ALLOWED_REASON_CLAUSES` onto
    `cortex_command/override_reason.py`, per requirement 1.
    (b) *Scope of the agreement sentence.* "Both writers of an override row … with `reason` omitted rather than
    nulled" is scoped to the two **typed** writers, and the generic `log --event <e> --set k=v` form is named as the
    ADR-0020 escape hatch that carries no field validation and can still write `"reason": ""`. Without that rescoping
    the sentence stays false after this ticket, because the escape hatch bypasses both fixes in one line.
    (c) *Restatement sites.* At HEAD the bullet names three — `refine.py:_ALLOWED_REASON_CLAUSES`,
    `skills/refine/SKILL.md` Step 4, and `cortex/adr/0036-*.md` — and says "adding a tag edits all three". After this
    ticket the set is **four**: `cortex_command/override_reason.py` (owner), `skills/refine/SKILL.md`,
    `skills/build/SKILL.md` (added by requirement 14), and `cortex/adr/0036-*.md`.
    (d) *Ordering rule.* The wheel-before-prose rule gains a widening-versus-narrowing distinction: wheel-first is
    correct when **widening** the set, and wrong when **narrowing** it, because no sibling repo pins a cortex-command
    version — the wheel lands everywhere at once while plugin prose ships separately via `/plugin install`.
    Acceptance — let `BULLET` denote
    `grep '^- \*\*Override-reason clause vocabulary\*\*' cortex/requirements/lifecycle.md`, which matches exactly one
    line: (a) `BULLET | grep -c 'refine\.py:_ALLOWED_REASON_CLAUSES'` prints `0` (HEAD: `1`) **and**
    `BULLET | grep -c 'override_reason\.py'` prints `1` (HEAD: `0`). (b) `BULLET | grep -c -- '--set'` prints `1`
    (HEAD: `0`) **and** `BULLET | grep -c 'ADR-0020'` prints `1` (HEAD: `0`). (c)
    `BULLET | grep -c 'skills/build/SKILL\.md'` prints `1` (HEAD: `0`), `BULLET | grep -c 'all four'` prints `1`
    (HEAD: `0`), **and** `BULLET | grep -c 'all three'` prints `0` (HEAD: `1`). (d) `BULLET | grep -c 'widening'`
    prints `1` (HEAD: `0`) **and** `BULLET | grep -c 'narrowing'` prints `1` (HEAD: `0`).
    **Phase**: Reconcile the record

14. **Both CLI override call sites name the clause vocabulary.** `skills/refine/SKILL.md:63` invokes
    `complexity-override` and `skills/build/SKILL.md:71` invokes `criticality-override`; both currently pass
    `--reason "<one line>"` with no tag guidance. Under requirement 7 the two axes share one set, so the guidance is
    symmetric and neither site contradicts `skills/refine/SKILL.md` Step 4, which already states the four tags for
    `reconcile-clarify`'s flags. Note the evidence does not isolate prose from enforcement — the one correctly-tagged
    row in the cited pair came from a site that is both documented *and* backed by exit 2 — so this requirement is
    justified as removing a known inconsistency between call sites, not as the measured cause of correct tagging.
    Acceptance: `awk '/criticality-override/' skills/build/SKILL.md | grep -c 'reversibility'` prints `1` (HEAD: `0`);
    `awk '/complexity-override/' skills/refine/SKILL.md | grep -c 'reversibility'` prints `1` (HEAD: `0`);
    **regression guard** — `just build-plugin` leaves `plugins/cortex-core/skills/{refine,build}/SKILL.md` reconciled
    with zero drift at commit. **Phase**: Reconcile the record

15. **A successor ticket exists for the tier clause vocabulary.** #471 declined to *define* a tier vocabulary while
    keeping the criticality set applied to tier, and set a re-measure trigger; #471 is `status: complete`, so that fork
    is tracked by nothing. This ticket does not re-defer its own work — requirement 7 closes what #471 deferred here —
    it tracks only the vocabulary fork. Acceptance: a `cortex/backlog/NNN-*.md` exists whose body cites
    `cortex/lifecycle/tier-overrides-record-no-reason-and/spec.md:32` and states the re-measure trigger (HEAD: no such
    file). **Phase**: Reconcile the record

## Non-Requirements

- **Validating the generic `log --event X --set k=v` path.** It remains able to write `"reason": ""` and any tag. This
  is the ADR-0020 escape hatch and is unvalidated by design; requirement 13 makes the requirement text honest about it
  rather than closing it.
- **Defining the tier clause vocabulary.** Deliberately declined here, as #471 declined it. Requirement 7 applies the
  existing set to both axes exactly as #471 left it; requirement 15 tracks the fork.
- **Retroactive migration of existing rows.** The 42 reason-bearing rows written through this path record what the runs
  actually did. Requirement 6's canonicalization applies at write time only.
- **`feature-paused --slug` joining the empty-drop.** `--slug ""` is unreachable by any live caller. Requirement 10's
  mechanism happens to cover it, but no requirement asserts it and no test pins it.
- **Removing the caller-less typed `feature-paused` subcommand.** A genuine deletion candidate surfaced by research,
  but it sits inside ADR-0020's uniform table and is a scoped decision, not a drive-by.
- **Changing `_emit_subcommand`'s generic optional-field drop to blanket truthiness.** Explicitly rejected: it would
  silently discard `--cycle 0`, `--tasks-total 0`, and `--rework-cycles 0`.

## Edge Cases

- **`--reason` omitted entirely**: unchanged — the key is absent, as today.
- **`--reason` is whitespace only (`"   "`)**: treated as empty; the key is omitted.
- **Reason whose body contains a colon after a valid tag** (`exposure: it feeds A: B`): accepted, tag is `exposure`,
  body unmodified. Pinned today by `tests/test_refine_reconcile_clarify.py:570` and must stay green.
- **Reason that is a single word with a trailing colon** (`zzz:`): tag is `zzz`, invalid, rejected. An empty body after
  a valid tag (`exposure:`) is accepted — the tally buckets on the tag, not the body.
- **`design-fork:` on either override verb**: rejected, identically by both writers. It names a tier concept with no
  tag in the current set, which is exactly the signal #471's re-measure trigger watches for.
- **A reason whose first colon-prefix is multi-word** (`blast radius: unbounded`): accepted as untagged prose, written
  verbatim, and counted as untagged by the amended recipe in requirement 12.
- **Wheel upgraded ahead of the plugin**: consumers run old prose (no tag guidance) against the new validator. Because
  requirement 5 accepts untagged prose and only rejects a single-token bogus tag, the old `--reason "<one line>"`
  pattern degrades to accepted-untagged rather than hard failure.
- **`events.log` unwritable or project root unresolvable**: unchanged — `CortexProjectRootError` → stderr, exit 1.
  Requirement 9's exit 2 is parse-time and strictly earlier.

## Changes to Existing Behavior

- **MODIFIED** — both typed override verbs now reject a single-token bogus clause tag (exit 2, nothing written) where
  they previously accepted anything.
- **MODIFIED** — both typed override verbs now omit `reason` on an empty or whitespace-only value where they
  previously wrote `"reason": ""`.
- **MODIFIED** — `_reason_clause_ok`'s matching loosens on the already-validated `refine.py` path: `Exposure: x`,
  ` exposure: x`, and multi-word prefixes like `blast radius: unbounded` now pass where they previously exited 2.
- **MODIFIED** — a recognized tag is canonicalized to lowercase in the written value on both paths.
- **MODIFIED** — ADR-0036's documented tally recipe gains an allowed-set membership check.
- **MODIFIED** — the bad-tag diagnostic is prefixed with the invoking program name instead of `cortex-refine`.
- **ADDED** — `cortex_command/override_reason.py`.
- **REMOVED** — `_ALLOWED_REASON_CLAUSES` and `_reason_clause_ok` as `refine.py`-owned definitions.

## Technical Constraints

- **`lifecycle_event` cannot import `refine`.** `refine.py:29` already imports `log_event_at` from `lifecycle_event`.
  This forces requirement 1's relocation; it does not by itself select the destination.
- **`common.py` was considered and rejected as the home.** It is the dependency leaf imported by ~60 modules, carries a
  curated docstring enumerating its public surface, and is lifecycle-gated by name in CLAUDE.md.
- **No 6th tuple element on `_EVENT_SUBCOMMANDS`.** Three hard 5-tuple unpacks would break: `lifecycle_event.py:362`,
  `lifecycle_event.py:390`, `tests/test_lifecycle_event_roundtrip.py:113`.
- **The empty-drop needs no side table.** The only optional fields with no `choices` and kind `_STR` are
  `feature-paused --slug` and the two `--reason`; every other optional is `choices`-constrained or `_JSON`, where `""`
  is already unreachable. A single condition on the existing drop line is therefore behaviorally identical to a
  registration table, without a registration step a future field can silently miss.
- **`_build_parser` already routes a per-field callable** via `kwargs["type"]` for `_JSON` fields
  (`lifecycle_event.py:396-397`), which is the wiring point for requirements 7 and 9.
- **An argparse `type=` callable must raise `ArgumentTypeError`**, while the existing predicate returns `bool` and
  prints. Requirement 8 constrains how that is reconciled: `refine.py`'s two-message non-short-circuit behavior is
  pinned and must survive, so the predicate keeps a non-raising form and the parse-time wrapper raises.
- **The validator and ADR-0036's tally must define a tag identically.** Requirements 5, 6 and 12 move together; landing
  any one alone reintroduces the counting defect this ticket exists to remove.
- **`cortex_command/*.py` is not plugin-mirrored**, so Phases 1–2 need no `just build-plugin`. Requirement 14 edits
  `skills/` and does — the pre-commit hook rebuilds those mirrors from staged blobs.
- **Requirement 14's SKILL.md prose growth is unratcheted.** `scripts/ratchet_refs.py:enumerate_reference_dirs`
  (`:65-69`) enumerates exactly `skills/*/references`, `plugins/*/skills/*/references`, and
  `cortex_command/pipeline/prompts` — no `SKILL.md` body is in that set — and `tests/test_l1_surface_ratchet.py` bounds
  frontmatter only. The two pins that read a `SKILL.md` body are loose ceilings with wide headroom, not ratchets.
  Growth control on those two lines is prose policy (`docs/policies.md`), not machinery.
- **No test pins the behavior being changed** on the typed-verb side. `cortex_command/tests/test_lifecycle_event.py:613-626`
  pins `--set reason=` → `""` on the generic path and must stay green.

## Open Decisions

None. The two forks research left open — tier-axis handling and the validation failure mode — were resolved at the
Specify interview, and the tier-axis resolution was then inverted by critical review on the evidence that
`refine.py:364` already enforces the criticality set on the tier axis. Recorded as requirements 7 and 9.

## Proposed ADR

### Proposed ADR: 0038-one-clause-set-for-both-override-axes-enforced-at-parse-time

**Context.** An override row's `reason` has two writers. `reconcile-clarify` validates both of its flags — including
the tier-side `--tier-reason` — against `{reversibility, exposure, consequence, other}`, while the `cortex-lifecycle-event`
typed verbs validate nothing. An earlier draft of this spec proposed making validation axis-keyed and exempting the
tier verb, on the reading that #471 had declined tier validation. It had not: #471 declined to *define* a tier
vocabulary and recorded that "the tier clause vocabulary stays the criticality set for now", naming validation of
`complexity-override --reason` as the follow-up this ticket closes.

**Decision.** One clause set governs both override axes, enforced at argparse parse time so a rejected tag writes
nothing. A recognized tag is canonicalized to lowercase in the stored value, and the documented tally drops keys
outside the set, so validator and consumer share one definition of a tag.

**Trade-off.** Tier reasons keep landing on `other` for want of tier-shaped tags, and a hard reject discards the whole
override row — including `from`/`to`, which `common.py:975,982` supersedes lifecycle state from. Both are accepted:
the `other` concentration is #471's own pre-registered signal to fork the vocabulary rather than a defect to suppress,
and the reject is atomic at parse time, so the operator retags and re-emits with no partial row. The rejected
alternative — exempting the tier axis — would have split the tier corpus by writer, leaving a successor unable to tell
an `other:` written under constraint from free prose written without it.
