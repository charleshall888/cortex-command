# Plan: override-row-writers-disagree-on-an

## Overview

Relocate the override-reason clause predicate out of `refine.py` into a stdlib-only leaf module both writers can
import, loosen its tag-claim rule and canonicalize the tag it stores, then bind it to `_emit_subcommand`'s two
`--reason` fields at argparse parse time — so the typed verbs and `reconcile-clarify` agree on what a clause tag is,
and ADR-0036's tally buckets on the same definition. Key decisions: a new `_CLAUSE` field kind carries the parse-time
binding (zero tuple-arity change, zero unpack sites broken); the `type=` callable both validates and canonicalizes,
so requirement 9's "rejected tag writes nothing" falls out of argparse rather than being hand-rolled; the empty-reason
drop is one condition on the existing drop line, no side table.

**Architectural Pattern**: layered
<!-- A stdlib-only leaf module is introduced beneath both writers specifically to break the refine→lifecycle_event
     import cycle; that layering is the change's structural commitment. -->

## Outline

### Phase 1: Relocate and loosen (tasks: 1, 2, 3)
**Goal**: `cortex_command/override_reason.py` owns the clause set, the tag-claim predicate, the canonicalizer, and the
prog-parameterized diagnostic; `refine.py` consumes it and defines none of them, with its two-message
non-short-circuit behavior intact.
**Checkpoint**: `grep -c "_ALLOWED_REASON_CLAUSES" cortex_command/refine.py` prints `0`,
`uv run python -m pytest tests/test_refine_reconcile_clarify.py` exits 0, and `reconcile-clarify --help` still
enumerates the four tags.

### Phase 2: Wire the typed verbs (tasks: 4, 5)
**Goal**: `criticality-override` and `complexity-override` reject a bogus single-token tag at parse time (exit 2,
nothing appended), canonicalize a recognized tag into the stored value, and omit `reason` on an empty or
whitespace-only value — with falsy-but-meaningful JSON fields still emitting.
**Checkpoint**: the new typed-verb tests pass and `cortex_command/tests/test_lifecycle_event.py` stays green.

### Phase 3: Reconcile the record (tasks: 6, 7, 8, 9)
**Goal**: the tally recipe, the governing requirement bullet, both CLI call sites, and the tier-vocabulary successor
ticket all describe what actually shipped.
**Checkpoint**: every requirement-12/13/14/15 acceptance grep returns its stated value, and `just build-plugin`
leaves the two mirrored SKILL.md files with zero drift.

## Tasks

### Task 1: Create the stdlib-only clause module
- **Files**: `cortex_command/override_reason.py` (new)
- **What**: Establishes the single home for the clause vocabulary, the tag-claim rule, the write-time canonicalizer,
  and the diagnostic template, importing no `cortex_command` module so `refine.py` and `lifecycle_event.py` can both
  import it without reintroducing the cycle at `refine.py:29`. Satisfies requirements 1, 4 (message half), 5, 6
  (mechanism half).
- **Depends on**: none
- **Complexity**: moderate
- **Context**: Public surface, all four names exported:
  - `ALLOWED_REASON_CLAUSES: frozenset[str]` — `{"reversibility", "exposure", "consequence", "other"}`, moved with
    the explanatory comment now at `refine.py:46-49`.
  - `BAD_REASON_CLAUSE_MSG: str` — the template at `refine.py:53-55` with the hardcoded `"cortex-refine: "` prefix
    replaced by a `{prog}` field; keeps `{flag}`, `{value}`, `{tag}`, `{allowed}`.
  - `claimed_tag(value: str | None) -> str | None` — returns the lowercased text before the first colon when that
    text, after `.strip()`, is non-empty and contains no whitespace; otherwise `None`. `None` therefore covers
    "no colon", "empty prefix", and "multi-word prefix", all of which are untagged prose. Replaces the
    unstripped/case-sensitive first-colon split at `refine.py:314-315`.
  - `reason_clause_ok(flag: str, value: str | None, prog: str) -> bool` — non-raising, prints
    `BAD_REASON_CLAUSE_MSG` to stderr and returns `False` only when `claimed_tag` is non-`None` and outside the set.
    The bool-and-print shape is deliberate: `refine.py:356-368`'s two unconditional calls depend on it (requirement 8).
  - `canonicalize_reason(value: str) -> str` — when `claimed_tag(value)` is in the set, return
    `f"{tag}:{body}"` where `body` is `value.split(":", 1)[1]` **byte-unmodified**; otherwise return `value`
    unchanged. This canonicalizes the tag only, which is the isomorphism requirement 6 exists to protect, and leaves
    `exposure: it feeds A: B` byte-identical as the Edge Cases section requires.
  - Module docstring states why the module exists (cycle break) and that it must stay stdlib-only.
- **Verification**: `uv run python -c "import cortex_command.override_reason as m; print(sorted(m.ALLOWED_REASON_CLAUSES))"`
  prints `['consequence', 'exposure', 'other', 'reversibility']`; `grep -c "^from cortex_command\|^import cortex_command" cortex_command/override_reason.py`
  returns `0`.
- **Status**: [x] done (bd1000e5 2026-08-10T21:52:04-04:00)

### Task 2: Re-point `refine.py` at the relocated module
- **Files**: `cortex_command/refine.py`
- **What**: Deletes `_ALLOWED_REASON_CLAUSES`, `_BAD_REASON_CLAUSE_MSG`, and `_reason_clause_ok` as `refine.py`-owned
  definitions, imports the relocated names, re-points both `reconcile-clarify` help builders, and canonicalizes the
  reason before it is written onto either override row. Satisfies requirements 2, 3, 4 (call-site half), 6 (refine
  path), and preserves 8.
- **Depends on**: [1]
- **Complexity**: moderate
- **Context**: **Caller enumeration (run, not assumed)** — `grep -rn` for all three names across `*.py` and `*.md`
  returns callers only inside `refine.py` itself (`:307`, `:311`, `:317`, `:320`, `:324`, `:364`, `:365`, `:939`).
  **No test and no other module imports any of them**, so `tests/test_refine_reconcile_clarify.py` needs no edit and
  Files stays a single file. The only prose references are `cortex/requirements/lifecycle.md:104` (owned by Task 7)
  and the bodies of backlog items #471 and #474, which are historical records of what was true when written and are
  deliberately left alone. Five edit sites, all inside `refine.py`:
  - `:46-55` — remove the clause-set and message definitions; add
    `from cortex_command.override_reason import ALLOWED_REASON_CLAUSES, canonicalize_reason, reason_clause_ok`
    beside the existing `lifecycle_event` import at `:29`. `_DISCARDED_REASON_MSG` (`:57-63`) stays — it is a
    refine-only idiom, not shared.
  - `:307-328` — delete `_reason_clause_ok` outright.
  - `:364-366` — the two call sites pass `prog="cortex-refine"`. Both calls stay unconditional and both results are
    combined only afterwards, so a caller with two bad tags still sees two diagnostics in one run (#471 R8).
  - After the `if not tier_reason_ok or not criticality_reason_ok: return 2` gate at `:368`, canonicalize both
    locals (`tier_reason = canonicalize_reason(tier_reason) if tier_reason else tier_reason`, same for
    `criticality_reason`) so the rows built at `:423` and `:440` carry the canonical tag. Placing it after the gate
    keeps a rejected reason from being rewritten and keeps the append all-or-nothing (R6).
  - `:937-946` and `:947-953` — `--criticality-reason`'s help interpolates
    `", ".join(sorted(ALLOWED_REASON_CLAUSES))`; `--tier-reason`'s help keeps inheriting the vocabulary by reference.
    Both must keep rendering the four tags in `--help`, which is the only place a CLI author discovers them.
- **Verification**: `grep -c "_ALLOWED_REASON_CLAUSES" cortex_command/refine.py` prints `0`;
  `grep -c "override_reason" cortex_command/refine.py` is at least `1`;
  `uv run python -m cortex_command.refine reconcile-clarify --help 2>&1 | tr '\n' ' ' | tr -s ' ' | grep -c 'consequence, exposure, other, reversibility'`
  prints `1`; `uv run python -m pytest tests/test_refine_reconcile_clarify.py` exits 0; and
  `uv run python -m cortex_command.refine reconcile-clarify --lifecycle-slug zzz-nonexistent-probe --complexity moderate --criticality low --tier-reason 'badA: x' --criticality-reason 'badB: y'`
  exits 2 printing exactly two stderr lines, one naming each flag.
- **Status**: [x] done (4e51dc59 2026-08-10T21:57:11-04:00)

### Task 3: Unit-test the tag-claim rule and the canonicalizer
- **Files**: `tests/test_override_reason.py` (new), `cortex_command/override_reason.py` (mutation check only —
  stubbed then reverted; the file must be byte-identical to Task 1's output when this task reports)
- **What**: Pins requirement 5's widened matching and requirement 6's canonicalization at the module boundary, where
  the existing `reconcile-clarify` suite cannot see them — every reason literal in that suite is a valid lowercase
  tag, a single-token bogus tag, `plain text`, or `""`, so none of them flips under this change.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Cases to pin, drawn from the spec's requirement 5 and Edge Cases:
  - Accepted as tagged: `exposure: x`, `Exposure: x`, ` exposure: x`, `other:x`, `exposure:` (empty body),
    `exposure: it feeds A: B` (inner colon).
  - Accepted as untagged prose: `blast radius: unbounded`, `Chose high: consumer-facing`,
    `see research.md line 40: the fork`, `plain text`, `""`, `None`.
  - Rejected: `zzz: y`, `zzz:`, `design-fork: two options`.
  - Canonicalization: `" Exposure: it feeds spec authoring"` → starts with the exact bytes `exposure: `;
    `"blast radius: unbounded"` → returned byte-for-byte unchanged; `"exposure: it feeds A: B"` → unchanged.
  - `reason_clause_ok` prints the invoking `prog` it was handed and no other program name (capsys).
  - The test must be red against the pre-change predicate on at least `Exposure: x`; note that expectation in a
    docstring rather than asserting it, since the old predicate will be gone.
- **Verification**: `uv run python -m pytest tests/test_override_reason.py` exits 0 with every case above collected;
  **and** the suite is falsifiable rather than self-sealing — with `canonicalize_reason` temporarily stubbed to
  `return value`, the run fails on the `" Exposure: it feeds spec authoring"` case, and with `claimed_tag`'s
  whitespace check removed it fails on `blast radius: unbounded`. Report both mutant runs' failure counts.
- **Status**: [x] done (c757c1c7 2026-08-10T22:01:00-04:00)

### Task 4: Bind clause validation and the empty-drop to the typed verbs
- **Files**: `cortex_command/lifecycle_event.py`
- **What**: Adds a third field kind for the two `--reason` fields, routes it to an argparse `type=` callable that
  validates and canonicalizes, and widens the optional-field drop to cover an empty or whitespace-only string.
  Satisfies requirements 7, 9, 10 and preserves 11.
- **Depends on**: [1]
- **Complexity**: moderate
- **Context**: Three edit sites plus the table:
  - Beside `_STR`/`_JSON` (`:252-253`) add `_CLAUSE = "clause"`. `kind` is a plain string that
    `_emit_subcommand:362` passes through and `log_event:169` discards (`for _kind, key, value in fields`), and no
    test enumerates kind values — the three hard 5-tuple unpacks (`:362`, `:390`,
    `tests/test_lifecycle_event_roundtrip.py:113`) are arity-sensitive only, so this breaks none of them. This is
    the mechanism the spec's Technical Constraints point at when they name `kwargs["type"]` as the wiring point.
  - `_EVENT_SUBCOMMANDS` — change `("--reason", "reason", _STR, False, None)` to `_CLAUSE` in both
    `criticality-override` (`:310-313`) and `complexity-override` (`:321-324`). Both axes validate against the one
    set, matching what `refine.py:364` already enforces on `--tier-reason` (requirement 7).
  - New `_clause_arg(value: str) -> str` beside `_json_arg` (`:343-351`): calls `override_reason.claimed_tag`; when
    the tag is non-`None` and outside `ALLOWED_REASON_CLAUSES`, raises `argparse.ArgumentTypeError` built from
    `BAD_REASON_CLAUSE_MSG` with the flag and tag interpolated; otherwise returns
    `override_reason.canonicalize_reason(value)`. Raising here is what makes requirement 9 structural — argparse
    exits 2 before `_emit_subcommand` runs, so no partial row can land. Requirement 4's "names the invoking verb"
    falls out of argparse's own `prog="cortex-lifecycle-event"` prefix (`:376`), so the template's `{prog}` field is
    filled with the empty-safe form rather than a second hardcoded name — do not reintroduce `cortex-refine` here.
  - `_build_parser:394-399` — bind `kwargs["type"] = _clause_arg` when `kind == _CLAUSE`, alongside the existing
    `_JSON` branch.
  - `_emit_subcommand:363-365` — widen `if value is None and not required: continue` to also drop a string that is
    empty or whitespace-only. Guard on `isinstance(value, str)` so `--tasks-total 0` / `--rework-cycles 0` /
    `--cycle 0` (all `_JSON`) are untouched (requirement 11). Update the trailing comment, which currently says
    "optional flag omitted — drop the field entirely", to name the empty case and why: `""` is not an axis a corpus
    tally can bucket on. Record in the comment that this half has **zero** observed instances in 554 corpus rows and
    rides on contract coherence, not measured harm.
  - Do **not** touch the generic `log --set` path: `cortex_command/tests/test_lifecycle_event.py:613-626` pins
    `--set reason=` → `""` and must stay green (it is ADR-0020's escape hatch, a stated Non-Requirement).
- **Verification**: `uv run python -m pytest cortex_command/tests/test_lifecycle_event.py tests/test_lifecycle_event_roundtrip.py`
  exits 0.
- **Status**: [x] done (c728f9c2 2026-08-10T21:58:21-04:00)

### Task 5: Test the typed override verbs end to end
- **Files**: `cortex_command/tests/test_lifecycle_event.py`, `cortex_command/lifecycle_event.py` (mutation check
  only — the `_clause_arg` binding is removed then restored; the file must be byte-identical to Task 4's output when
  this task reports)
- **What**: Pins requirements 7, 9, 10, 11 against the verb, since no existing test exercises `--reason` for the
  typed subcommands at all.
- **Depends on**: [4]
- **Complexity**: moderate
- **Context**: Follow the existing class's tmp-root fixture and `self._read_row(root, "f")` helper (used at
  `:903-907`) — every case must run against a throwaway project root, never the repo tree, because `log_event`
  resolves its log path from CWD and would otherwise append to `cortex/lifecycle/`. Cases:
  - Requirement 7 symmetry: `complexity-override --from moderate --to complex --reason "design-fork: two options"`
    exits 2 and appends nothing; the same string on `criticality-override` exits 2 and appends nothing.
  - Requirement 9 atomicity: byte-compare `events.log` before and after a rejected
    `criticality-override --reason "zzz: y"`.
  - Requirement 6 on this path: `--reason " Exposure: it feeds spec authoring"` appends a row whose `reason` starts
    with the exact bytes `exposure: `; `--reason "blast radius: unbounded"` appends that string byte-for-byte.
  - Requirement 10: `--reason ""` and `--reason "   "` each append a row with no `reason` key at all.
  - Requirement 11 regression guard: `feature-complete --tasks-total 0 --rework-cycles 0` appends
    `"tasks_total": 0` and `"rework_cycles": 0`.
  - Requirement 4: the stderr of a rejected tag contains `cortex-lifecycle-event` and does not contain
    `cortex-refine`.
- **Verification**: `uv run python -m pytest cortex_command/tests/test_lifecycle_event.py` exits 0; deleting the
  `_clause_arg` binding from `_build_parser` turns the requirement-7 case red.
- **Status**: [x] done (15059794 2026-08-10T22:04:52-04:00)

### Task 6: Amend ADR-0036's tally recipe
- **Files**: `cortex/adr/0036-ceremony-relief-is-not-taken-on-the-criticality-axis.md`
- **What**: Adds an allowed-set membership check to the documented recipe so the untagged-prose category requirements
  5 and 6 create is counted as untagged rather than as a whole-sentence bucket masquerading as a clause. Satisfies
  requirement 12.
- **Depends on**: [4]
- **Complexity**: simple
- **Context**: The recipe's code block sits at `:57-67`; the unconditional bucket line is
  `c.update([r['reason'].split(':')[0]])` at `:64`. Amend to bucket on the tag only when the split-and-stripped
  prefix is a single token in the four-tag set, and to a single `untagged` bucket otherwise. The line filter and the
  `except ValueError` are load-bearing (`:69-72` says so) and stay. The paragraph at `:74-77` describing
  whole-sentence buckets as today's reality needs its tense reconciled with the amended recipe rather than left
  contradicting it.
- **Verification**: the amended block, run over a fixture containing `exposure: a`, `Exposure: b`, and
  `blast radius: c`, yields exactly one `exposure` bucket of count 2 plus one untagged bucket, where the HEAD recipe
  yields three buckets of count 1. Capture that run in the task's report, using a fixture written under the
  scratchpad.
- **Status**: [x] done (c8764a56 2026-08-10T22:00:41-04:00)

### Task 7: Correct the governing requirement bullet
- **Files**: `cortex/requirements/lifecycle.md`
- **What**: Rewrites the "Override-reason clause vocabulary" bullet on the four counts requirement 13 enumerates —
  ownership, the scope of the agreement sentence, the restatement-site enumeration, and the widening-versus-narrowing
  ordering rule — and removes the now-closed "tracked as follow-up (#474)" sentence.
- **Depends on**: [4]
- **Complexity**: moderate
- **Context**: One line, `cortex/requirements/lifecycle.md:104`, matched by
  `grep '^- \*\*Override-reason clause vocabulary\*\*'`. The four corrections:
  (a) ownership moves from `cortex_command/refine.py:_ALLOWED_REASON_CLAUSES` to `cortex_command/override_reason.py`;
  (b) "Both writers of an override row … with `reason` omitted rather than nulled" is scoped to the two **typed**
  writers, and `log --event <e> --set k=v` is named as the ADR-0020 escape hatch that carries no field validation and
  can still write `"reason": ""` — without this the sentence stays false after the ticket;
  (c) the restatement set becomes **four** — `cortex_command/override_reason.py` (owner), `skills/refine/SKILL.md`,
  `skills/build/SKILL.md`, `cortex/adr/0036-*.md` — so "adding a tag edits all three" becomes "all four";
  (d) the wheel-before-prose rule gains the distinction that wheel-first is correct when **widening** the set and
  wrong when **narrowing** it, because no sibling repo pins a cortex-command version — the wheel lands everywhere at
  once while plugin prose ships separately via `/plugin install`.
  Also drop the trailing "Closing that gap needs a per-field validator hook in `_emit_subcommand` and is tracked as
  follow-up (#474)" sentence, which this ticket closes.
- **Verification**: with `BULLET` = that grep — `BULLET | grep -c 'refine\.py:_ALLOWED_REASON_CLAUSES'` prints `0`;
  `BULLET | grep -c 'override_reason\.py'` prints `1`; `BULLET | grep -c -- '--set'` prints `1`;
  `BULLET | grep -c 'ADR-0020'` prints `1`; `BULLET | grep -c 'skills/build/SKILL\.md'` prints `1`;
  `BULLET | grep -c 'all four'` prints `1`; `BULLET | grep -c 'all three'` prints `0`;
  `BULLET | grep -c 'widening'` prints `1`; `BULLET | grep -c 'narrowing'` prints `1`.
- **Status**: [x] done (9162cfdd 2026-08-10T22:01:46-04:00)

### Task 8: Name the clause vocabulary at both CLI override call sites
- **Files**: `skills/refine/SKILL.md`, `skills/build/SKILL.md`, `plugins/cortex-core/skills/refine/SKILL.md`,
  `plugins/cortex-core/skills/build/SKILL.md` (mirrors — listed because `just build-plugin` rsyncs into them during
  this task's own verification; write them only through that recipe, never by hand, and never stage them)
- **What**: Adds the four tags to the two skill lines that invoke the override verbs, which today pass
  `--reason "<one line>"` with no tag guidance — the only two invocations of these verbs anywhere. Satisfies
  requirement 14.
- **Depends on**: [4]
- **Complexity**: simple
- **Context**: `skills/refine/SKILL.md:63` invokes `complexity-override`; `skills/build/SKILL.md:71` invokes
  `criticality-override`. Under requirement 7 the two axes share one set, so the guidance is symmetric and neither
  site contradicts `skills/refine/SKILL.md` Step 4 (`:70`), which already states the four tags for
  `reconcile-clarify`'s flags. Keep the addition to the existing sentence — both files are L1 surfaces under the
  budget policy in `docs/policies.md`, and this is prose growth on a surface no ratchet measures
  (`scripts/ratchet_refs.py:65-69` enumerates only `references/` dirs and `pipeline/prompts`), so the restraint is
  policy, not machinery. `refine/SKILL.md:63` also carries "Non-zero exit → surface stderr and halt"; under
  requirement 7 a rejected tag now discards the whole override row including `from`/`to`, so that instruction needs
  a retag-and-re-emit amendment rather than a bare halt. Edit the canonical `skills/` sources only — the
  `plugins/cortex-core/skills/` mirrors are rebuilt from staged blobs by the pre-commit hook and must never be
  staged by hand.
- **Verification**: `awk '/criticality-override/' skills/build/SKILL.md | grep -c 'reversibility'` prints `1`;
  `awk '/complexity-override/' skills/refine/SKILL.md | grep -c 'reversibility'` prints `1`;
  `uv run python -m pytest tests/test_l1_surface_ratchet.py tests/test_refine_skill.py` exits 0; and
  `just build-plugin` leaves `plugins/cortex-core/skills/{refine,build}/SKILL.md` reconciled with zero drift.
- **Status**: [x] done (3b05a2c7 2026-08-10T22:05:05-04:00)

### Task 9: File the tier-vocabulary successor ticket
- **Files**: `cortex/backlog/` (one new `NNN-*.md`), `cortex/backlog/index.json`, `cortex/backlog/index.md`
  (both regenerated by `just backlog-index` in this task's verification)
- **What**: Creates the open ticket that tracks #471's declined tier-clause vocabulary, which is currently tracked by
  nothing — #471 is `status: complete` while its own spec says it does not close #471. Satisfies requirement 15.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Author via the backlog CLI so the id and frontmatter are allocated the normal way, not hand-numbered.
  The body must cite `cortex/lifecycle/tier-overrides-record-no-reason-and/spec.md:32` and state #471's re-measure
  trigger verbatim: a resulting distribution dominated by `other` on `complexity_override` rows is evidence **for**
  a tier-specific vocabulary, not against it. Scope the ticket to defining the tier vocabulary only — this ticket's
  requirement 7 already closes the validation half #471 deferred here, so the successor must not restate it as open.
  Front-door evidence bar: the Why names the measurable trigger and the corpus query that reads it, not a
  hypothetical.
- **Verification**: `grep -rl 'tier-overrides-record-no-reason-and/spec.md:32' cortex/backlog/` returns exactly one
  new file, and `just backlog-index` regenerates cleanly with it present.
- **Status**: [x] done (6895c9b9 2026-08-10T21:54:50-04:00)

### Task 10: Correct the now-false divergence comment in `refine.py`
- **Files**: `cortex_command/refine.py`
- **What**: Added during Implement, not at plan time. Task 4 widened `_emit_subcommand`'s optional-field drop to
  discard empty and whitespace-only strings, which inverted a comment Task 2 left standing at
  `refine.py:393-402`: it still tells the reader the omission test "diverges from that module deliberately" because
  `lifecycle_event.py` "still keys off `is not None` and would record `"reason": ""`". After `c728f9c2` the two
  writers **agree**, so the comment is false about live code in the same commit range that made it false.
- **Depends on**: [2, 4]
- **Complexity**: simple
- **Context**: Discovered by Task 7's builder while reading the shipped code to check whether its own rewritten
  requirement bullet was true. No test can observe a comment, so neither Task 2's nor Task 4's verification could
  have caught this, and Review reading artifacts rather than running them would likely miss it too. Rewrite the
  comment to state the agreement and what still differs (`refine.py` appends its own `gate` key; the two share
  `from, to, reason` order), and keep the load-bearing half — that an empty string is not an axis a corpus tally
  can bucket on. Do not restate the `--set` escape hatch here; `cortex/requirements/lifecycle.md:104` owns that.
- **Verification**: `grep -c 'is not None' cortex_command/refine.py` returns no match inside that comment block, and
  `uv run python -m pytest tests/test_refine_reconcile_clarify.py` exits 0. Quote the rewritten comment in the
  report so the claim can be read against `lifecycle_event.py`'s actual drop condition.
- **Status**: [x] done (5c81a92b 2026-08-10T22:04:45-04:00)

### Task 11: Close the residual whitespace-only disagreement in `refine.py`
- **Files**: `cortex_command/refine.py`, `tests/test_refine_reconcile_clarify.py`
- **What**: Added during Implement, not at plan time. Task 10 established that the two writers still disagree on a
  whitespace-only reason: `_emit_subcommand` drops it (`not value.strip()`), while `refine.py`'s row builders gate on
  plain truthiness, so `--tier-reason "   "` is truthy and lands as `"reason": "   "`. The spec's Edge Cases state
  the behavior unscoped — *"`--reason` is whitespace only (`"   "`): treated as empty; the key is omitted"* — and the
  ticket's own title is that the writers disagree on an empty reason, so a residual disagreement leaves the headline
  half-closed.
- **Depends on**: [2, 10]
- **Complexity**: simple
- **Context**: Requirement 10 is phase-scoped to the typed verbs and its acceptance names only
  `cortex-lifecycle-event`, so this is not a requirement-10 violation — it is the Edge Cases line and the ticket
  premise that this task serves. Change both row builders' `reason` guards from truthiness to a blank-aware test so
  `""` and `"   "` are both omitted, matching `_emit_subcommand` exactly. Do not reintroduce an `is not None` test —
  #471 moved these off that deliberately. Task 10's comment at `:393-403` ends by naming this exact residual gap;
  once closed, that closing sentence must be removed or the comment becomes false in the other direction.
- **Verification**: a `reconcile-clarify` run with `--tier-reason "   "` and `--criticality-reason "   "` on a
  throwaway lifecycle under the scratchpad appends rows with no `reason` key (assert via
  `python3 -c "import json,sys; print('reason' in json.loads(...))"` printing `False`); a new case in
  `tests/test_refine_reconcile_clarify.py` pins it; `uv run python -m pytest tests/test_refine_reconcile_clarify.py`
  exits 0; and reverting the guard turns the new case red — report that failure count.
- **Status**: [x] done (01dbc4d3 2026-08-10T22:08:13-04:00)

## Risks

- **Canonical form of the body.** Requirement 6 says the written reason "leads with the canonical lowercase tag
  followed by `: ` and the unmodified body", while the Edge Cases require `exposure: it feeds A: B` to keep its body
  unmodified. Those pull apart when the body's leading whitespace is not exactly one space. Task 1 resolves it as
  `f"{tag}:{body}"` with `body` byte-unmodified — the tag is canonicalized, the body never is. This satisfies both
  stated acceptances (`" Exposure: it feeds spec authoring"` → starts with `exposure: `; `"blast radius: unbounded"`
  → byte-identical) and leaves `other:x` as `other:x`, which no criterion pins. Flagged for review rather than
  decided silently.
- **Requirement 7 is a narrowing change shipped ahead of its prose.** The wheel lands on every sibling repo at once
  (none pins a version) while the Task 8 prose ships separately via `/plugin install`. Requirement 5's loosening is
  what makes this survivable — old prose's untagged `--reason "<one line>"` degrades to accepted-untagged rather
  than a hard failure — but a consumer that writes `design-fork:` on an old plugin gets exit 2 with no local
  guidance. Task 7(d) records the ordering rule; nothing enforces it.
- **A rejected tag discards routing state.** Exit 2 drops the whole override row including `from`/`to`, which
  `common.py:975,982` supersedes lifecycle tier/criticality from. Accepted per the spec's ADR (atomic at parse time,
  operator retags and re-emits), but it makes Task 8's amendment to `refine/SKILL.md:63`'s blanket "halt" load-bearing
  and unpinnable by any test.
- **The empty-reason half is unevidenced by design.** Zero instances in 554 corpus rows. It rides on contract
  coherence and one condition on a line already being edited. Task 4's comment must say so; the commit body must not
  let it read as measured harm.

## Acceptance

`cortex-lifecycle-event complexity-override --reason "design-fork: two options"` and
`cortex-refine reconcile-clarify --tier-reason 'design-fork: two options'` reject identically (exit 2, nothing
appended), `--reason " Exposure: x"` lands as `exposure: x` from either writer while `--reason "blast radius: x"`
lands byte-identical, `--reason ""` writes no `reason` key, and ADR-0036's recipe run over that corpus buckets those
three rows as one `exposure` clause plus one untagged — the validator and the tally reading one definition of a tag,
which is the outcome the ticket exists to produce.
