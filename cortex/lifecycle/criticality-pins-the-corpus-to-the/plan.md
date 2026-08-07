# Plan: criticality-pins-the-corpus-to-the

## Overview

Record the negative decision — ceremony relief is not taken on the criticality axis — as an ADR carrying its marginal-relief evidence, cited from `project.md`, the glossary, and ticket #452. Then give `reconcile-clarify` an optional clause-tagged `--criticality-reason` / `--tier-reason` so the axis becomes auditable for whoever re-opens the question: no rubric change, no predicate change.

**Scope delta from the spec:** the ADR number moves **0035 → 0036**, because `cortex/adr/0035-reviewer-brief-emitted-by-verb-not-reference-prose.md` landed 2026-08-07 (`291a2338`) from the concurrent #455 lifecycle — exactly the race the spec anticipated, which is why its acceptance is the `duplicate_number` assertion rather than the number note. `0036` is free as of this plan.

## Outline

### Phase 1: Record the decision (tasks: 1, 2, 3, 4)
**Goal**: Put the negative answer, its evidence, and its re-open trigger where the next person to ask will find them.
**Checkpoint**: `cortex/adr/0036-*.md` exists and is cited from `project.md`'s "The short road" bullet, the glossary defines *tier* / *criticality* / *short road*, and ticket #452 records the decision.

### Phase 2: Persist the criticality reason (tasks: 5, 6, 7)
**Goal**: Give Clarify's already-computed criticality reasoning a destination on the `criticality_override` row it currently has none for.
**Checkpoint**: `reconcile-clarify --criticality-reason "exposure: …"` writes a `reason` key; omission is byte-identical to today; an out-of-set clause tag is rejected with no append; the refine skill passes the reason.

## Tasks

### Task 1: Write ADR 0036 — ceremony relief is not taken on the criticality axis
- **Files**: `cortex/adr/0036-ceremony-relief-is-not-taken-on-the-criticality-axis.md` (create)
- **What**: Records the negative decision with the marginal-relief measurement as evidence, the conditional scope and re-open trigger, and the recipe for reading the clause distribution Phase 2 starts collecting (R1, and the durable home for R8).
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Frontmatter shape from `cortex/adr/README.md`: `---\nstatus: accepted\n---` (the promotion gate expects the merged file to land `accepted`). Title line format and section shape: follow `cortex/adr/0035-reviewer-brief-emitted-by-verb-not-reference-prose.md` — `# 0036 — <title>`, then `_Decision date: 2026-08-07 (#452 — <ticket title>)._`, then `## Context`, `## Decision`, `## Trade-off`, `## Cross-references`.
  - Body content is **already written** in `cortex/lifecycle/criticality-pins-the-corpus-to-the/spec.md` § "Proposed ADR" (Context / Decision / Scope and re-open trigger / Trade-off). Carry it across; do not re-derive the numbers.
  - Must contain the literal strings `5.0%`, `2.6%`, `33.1%`, `24.7%`, `9.4%`.
  - Add a section (suggested `## Reading the clause distribution`) carrying the R8 recipe verbatim from `spec.md:34` **and** the two reasons an unscoped grep is invalid (`cortex/lifecycle/*/events.log` misses `archive/` — 188 of 353 files; `reason` appears on 16 event types and `--tier-reason` writes the same key onto `complexity_override`). Also carry the Edge-Cases bound a successor must subtract: already-`high`-seeded lifecycles never produce an override row (10.5% cortex-command, 16.7% wild-light of modern-era final-`high`), and partial fill is expected (22–63% on the existing manual path).
  - `cortex/adr/README.md` no-content-duplication rule: the ADR is the canonical home; other docs link by number only (this is why Task 2 is a back-pointer, not a restatement).
  - Three-criteria gate is met: hard to reverse (it gates future rubric/predicate work behind recorded data), surprising without context (the intuitive read is that criticality pins 48–75% so relief belongs there), real trade-off (four routes considered and rejected, stated in Non-Requirements).
- **Verification**: `test -f cortex/adr/0036-ceremony-relief-is-not-taken-on-the-criticality-axis.md && for s in '5.0%' '2.6%' '33.1%' '24.7%' '9.4%'; do grep -qF "$s" cortex/adr/0036-ceremony-relief-is-not-taken-on-the-criticality-axis.md || { echo "MISSING $s"; exit 1; }; done && bin/cortex-adr-citation-audit | python3 -c "import json,sys; d=[f for f in json.load(sys.stdin)['findings'] if f['kind']=='duplicate_number']; assert not d, d" && echo PASS` → prints `PASS`, exit 0. (Baseline on HEAD: the file is absent, so the first `test -f` fails. The `duplicate_number` set is empty on HEAD, so that clause is a non-regression guard against re-taking a number, not the discriminating check — file existence and the five strings are.)
- **Status**: [ ] pending

### Task 2: Back-point `project.md`'s "The short road" at ADR-0036
- **Files**: `cortex/requirements/project.md`
- **What**: The ratified short-road constraint (line 40) carries no ADR reference and no ticket number; add a `→ ADR-0036` back-pointer on that bullet (R2).
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Target: the `- **The short road**: …` bullet under `## Architectural Constraints`. Sibling bullets show the house form for the pointer (`→ ADR-0001: File-based state, no database` at `:35`, `→ ADR-0003` at `:36`, `→ ADR-0024` at the end of the kept-pauses paragraph).
  - Append the pointer to the existing bullet; do **not** restate the decision body (`cortex/adr/README.md` § No-content-duplication discipline rule).
  - `project.md` has no written amendment procedure — every historical amendment rode inside the implementing ticket's commit (`983c98ae`, `57efb93c`, `e3aef4e5`), which is how this lands.
- **Verification**: `grep -n 'ADR-0036' cortex/requirements/project.md | grep -c 'The short road'` = `1`. Baseline on HEAD: `grep -c 'ADR-0036' cortex/requirements/project.md` = `0`, so the check discriminates. (A bare `grep 'ADR-00'` is invalid — it returns 8 matches on the unmodified file.)
- **Status**: [ ] pending

### Task 3: Add glossary entries for *tier*, *criticality*, and *short road*
- **Files**: `cortex/requirements/glossary.md`
- **What**: The glossary currently defines only *scene* and *cockpit*; the three terms this whole decision turns on have no canonical definition anywhere (R9).
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Write via the existing verb, not by hand: `cortex-append-glossary-term --term <t> --definition "<d>"` (`cortex_command/lifecycle/append_glossary_term_cli.py`). It writes into the `## Language` section, always exits 0, and reports `{"state": "appended"|"existed"|"replaced"|...}` on stdout — route on `state`, since exit 0 is not success here.
  - Existing entry style (`cortex/requirements/glossary.md`): `- **term**: lowercase definition, no trailing period`.
  - Definition sources — *tier* = the complexity axis (`simple` / `moderate` / `complex`), rubric at `skills/refine/references/clarify.md` §5.2, decides how deep ceremony reads; *criticality* = the risk axis (`low` / `medium` / `high` / `critical`), rubric at §5.3, decides whether Review runs; *short road* = the phase-fork predicate at `project.md`'s "The short road" bullet — `criticality ∈ {high, critical} OR tier == complex` takes the long road, everything else the short one. The *short road* entry should carry `→ ADR-0036` rather than the rationale.
- **Verification**: `grep -c '^- \*\*\(tier\|criticality\|short road\)\*\*:' cortex/requirements/glossary.md` = `3`. Baseline on HEAD: `0`.
- **Status**: [ ] pending

### Task 4: Record the negative answer on ticket #452
- **Files**: `cortex/backlog/452-criticality-pins-the-corpus-to-the-long-road-so-tier-relief-is-capped.md`
- **What**: The ticket asked a question whose answer is "no"; add a `## Decision` section stating that, linking the research and the ADR, so the ticket does not read as abandoned (R3).
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Append a `## Decision` section after `## Touch points`. Must contain the literal path `cortex/lifecycle/criticality-pins-the-corpus-to-the/research.md` and cite `ADR-0036`.
  - Content: the ticket's own premise is inverted — marginal relief from dropping the criticality clause is 5.0% / 2.6% against 10.7% / 33.1% for the tier clause; the Plan-skip half of the modelled benefit has never fired in ~650 logs; Review's catch rate is 6.5–15.7% and criticality does not predict it. What shipped instead is the reason-persistence half (Phase 2).
  - Do **not** touch frontmatter — `status` and `lifecycle_phase` are the Complete phase's write, via its own verb.
- **Verification**: `grep -c 'cortex/lifecycle/criticality-pins-the-corpus-to-the/research.md' cortex/backlog/452-*.md` ≥ `1` **and** `grep -c 'ADR-0036' cortex/backlog/452-*.md` ≥ `1`. Baseline on HEAD: both `0`.
- **Status**: [ ] pending

### Task 5: Give `reconcile-clarify` optional clause-tagged reason flags
- **Files**: `cortex_command/refine.py`
- **What**: Adds `--criticality-reason` / `--tier-reason` to `reconcile-clarify`; when supplied, the emitted `criticality_override` / `complexity_override` row carries a `reason` key. Validates the optional clause prefix against a closed set before any append (R4, R5, R6, and the data R8 reads).
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Emission site: `_cmd_reconcile_clarify` at `cortex_command/refine.py:288`; the two row dicts are built at `:345-371`. Place `reason` immediately after `"to"` so both writers of `criticality_override` produce the same key sequence as `lifecycle_event.py`'s declared field order (`--from`, `--to`, `--reason`, `lifecycle_event.py:310-325`); `gate` and the conditional `from_seeded` stay last.
  - Contract to match, not reinvent: `lifecycle_event.py:307-325`. Its comment is the ruling on optionality — *"a mandatory flag invites a filler string, which is worse than an absent one because it reads as evidence."* Omission must leave the row byte-identical to today (no `reason: null`).
  - Closed clause set: `reversibility`, `exposure`, `consequence`, `other`. Rule: if the value contains no `:`, accept and record verbatim; if it does, the tag is the text before the **first** colon and must be in the set — otherwise print the offending value to stderr and return non-zero (use `2`, matching the module's existing `_UNSAFE_SLUG_MSG` guard at `:309-311`) with **no** row appended. Validate both flags before the `rows` list is built, so a rejection cannot leave a partial write. The same set applies to both flags (see Risks).
  - Parser block: `rc = sub.add_parser("reconcile-clarify", …)` at `:795-846`; add the two `rc.add_argument` calls alongside `--complexity`/`--criticality`.
  - The existing `noop` arm (already-reconciled, or a suppressed downgrade) appends nothing, so a supplied reason is silently dropped there — that is correct and matches today's suppression behavior; do not add a row to carry it.
  - **Callers of `reconcile-clarify` (searched; the change is purely additive — two optional flags — so none of them requires an edit to keep working)**: `skills/refine/SKILL.md:69-70` (Step 4, the Context A and Context B invocations) — edited by Task 7; `tests/test_refine_reconcile_clarify.py` (invocations plus the contiguous SKILL.md substring pins at `:319-345`) — extended by Task 6; `tests/test_refine_module.py` (12 invocation sites); `tests/test_refine_resume_point.py`, `tests/test_refine_reconcile_wiring.py`, `tests/test_refine_session_ownership.py:301`. No `docs/` file references the verb (grep returned nothing). Only Tasks 6 and 7 change any of them; Task 5 edits `cortex_command/refine.py` alone.
- **Verification**: run the script below from a scratch dir. It must invoke the **working tree** — `cortex-refine` on `PATH` is the installed wheel and will not carry the new flags. Expected output: exactly `PASS a`, `PASS b`, `PASS c`, `PASS d`, `PASS e`, one per line.
  ```bash
  set -u
  R=/Users/charliehall/Workspaces/cortex-command
  W=$(mktemp -d); cd "$W"
  seed() { mkdir -p "cortex/lifecycle/$1"; printf '{"schema_version":"1","ts":"2026-01-01T00:00:00Z","event":"lifecycle_start","feature":"%s","tier":"simple","criticality":"medium","entry_point":"x"}\n' "$1" > "cortex/lifecycle/$1/events.log"; }
  run() { PYTHONPATH="$R" python3 -m cortex_command.refine "$@"; }
  seed f; seed g
  # (a) a tagged reason lands on criticality_override only; the complexity_override row has no reason key
  run reconcile-clarify --lifecycle-slug f --backend none --complexity complex --criticality high --criticality-reason "exposure: shared skill prose" >/dev/null
  python3 -c "import json;rs=[json.loads(l) for l in open('cortex/lifecycle/f/events.log')];c=[r for r in rs if r['event']=='criticality_override'][0];t=[r for r in rs if r['event']=='complexity_override'][0];assert c['reason']=='exposure: shared skill prose',c;assert 'reason' not in t,t;print('PASS a')"
  # (b) an out-of-set tag exits non-zero and appends nothing
  B=$(wc -c < cortex/lifecycle/f/events.log)
  run reconcile-clarify --lifecycle-slug f --backend none --criticality critical --criticality-reason "bogus: x"; rc=$?
  [ "$rc" -ne 0 ] && [ "$(wc -c < cortex/lifecycle/f/events.log)" = "$B" ] && echo "PASS b"
  # (c) an untagged reason is accepted and recorded verbatim
  run reconcile-clarify --lifecycle-slug f --backend none --criticality critical --criticality-reason "plain text" >/dev/null
  grep -q '"reason": *"plain text"' cortex/lifecycle/f/events.log && echo "PASS c"
  # (d) omission is byte-identical to today — no reason key at all
  run reconcile-clarify --lifecycle-slug g --backend none --criticality high >/dev/null
  grep -q '"reason"' cortex/lifecycle/g/events.log || echo "PASS d"
  # (e) R8: the documented recipe tallies criticality clauses only and reaches archive/
  mkdir -p cortex/lifecycle/f/archive; cp cortex/lifecycle/f/events.log cortex/lifecycle/f/archive/events.log
  find cortex/lifecycle -name events.log -exec cat {} + | python3 -c "import sys,json,collections; c=collections.Counter(); [c.update([r['reason'].split(':')[0]]) for l in sys.stdin for r in [json.loads(l)] if r.get('event')=='criticality_override' and r.get('reason')]; print('PASS e' if c['exposure']==2 and c['plain text']==2 and set(c)=={'exposure','plain text'} else ('FAIL',c))"
  ```
- **Status**: [ ] pending

### Task 6: Pin the reason flags with tests
- **Files**: `tests/test_refine_reconcile_clarify.py`
- **What**: Regression tests for the four behaviors Task 5 adds — tagged reason recorded, per-axis independence, out-of-set tag rejected with no append, omission byte-identical (R4, R5, R6).
- **Depends on**: [5]
- **Complexity**: simple
- **Context**:
  - Follow the file's existing shape: `main([...])` from `cortex_command.refine`, `monkeypatch.chdir(tmp_path)`, helpers `_seed_events`, `_lifecycle_start_line`, `_write_backlog`, `_count_overrides` (`tests/test_refine_reconcile_clarify.py:47-124`). `test_reconcile_clarify_standalone_headline_scenario` at `:126` is the closest template.
  - Cases: (1) `--criticality-reason "exposure: shared skill prose"` with both axes ratcheting → the `criticality_override` row carries the reason and the `complexity_override` row has no `reason` key (spec Edge Case "Both axes ratchet in one call"); (2) `--criticality-reason "bogus: x"` → non-zero return **and** `events.log` byte-identical (assert on file bytes, not row count); (3) no flags → no `reason` key on either row; (4) `--criticality-reason "plain text"` (no colon) → accepted, recorded verbatim; (5) a colon inside the body — `"exposure: consumed by overnight/: runner"` → accepted, recorded verbatim (spec Edge Case).
  - Do **not** modify the existing tests — R5 requires them to pass unmodified.
  - The SKILL.md invocation strings are pinned by `test_refine_non_local_reconcile_branch_is_value_aware` at `:319` in this same file; Task 7 must satisfy it, this task must not relax it.
- **Verification**: `uv run pytest tests/test_refine_reconcile_clarify.py tests/test_refine_module.py tests/test_refine_reconcile_wiring.py -q` → exit 0, no failures, and the new tests appear in the collected count (baseline before this task: 5 tests in `test_refine_reconcile_clarify.py`). `tests/test_refine_module.py` and `tests/test_refine_reconcile_wiring.py` are outside this task's **Files** and are run read-only as a regression gate — a failure in either indicates a Task 5 defect and is reported as blocked rather than patched, because R5 requires the pre-existing tests to pass unmodified.
- **Status**: [ ] pending

### Task 7: Carry Clarify's criticality reasoning into the refine Step 4 call
- **Files**: `skills/refine/SKILL.md`
- **What**: Step 4's `reconcile-clarify` invocation passes the criticality reasoning Clarify already produces, tagged per the closed set — no new assessment work, the reasoning exists in-session and is currently discarded at the write (R7).
- **Depends on**: [5]
- **Complexity**: simple
- **Context**:
  - Call site: `skills/refine/SKILL.md:67-70` (Step 4, "Reconcile first"). The reasoning source is `skills/refine/references/clarify.md:34` §5.3, which already requires "brief reasoning" — this is a destination for it, not new work.
  - **Contiguous-substring pins you must not break** (`tests/test_refine_reconcile_clarify.py:333-339`): the Context A line must still contain `reconcile-clarify --backend {resolved} --lifecycle-slug {lifecycle-slug} --backlog-slug {backlog-filename-slug}` and Context B `reconcile-clarify --backend {resolved} --lifecycle-slug {lifecycle-slug} --complexity {value} --criticality {value}` as unbroken substrings. Append the new flag **after** those spans, never inside them. Negative controls at `:344-345` forbid `--complexity simple` / `--criticality medium` literals on the same line.
  - Ordering pin (`tests/test_refine_reconcile_wiring.py`): the invocation must stay before the `specify.md` and follow it` delegation.
  - Prose must state the closed tag set (`reversibility:` / `exposure:` / `consequence:` / `other:`) and that the flag is optional — enough for the model to comply without reading the verb's `--help`.
  - Constraint: `skills/refine/references/` is at exactly zero ratchet headroom (20568/20568). `SKILL.md` is **not** reference-dir-pinned, so keep the change in `SKILL.md`; any spillover into `references/` needs an annotated `# raised:` exception carrying this lifecycle's id. `SKILL.md` is 92/500 lines against `tests/test_skill_size_budget.py`.
  - The `plugins/cortex-core/skills/refine/SKILL.md` mirror is rebuilt from the staged blob by `.githooks/pre-commit` Phase 3 — never stage it by hand, and expect it in the commit.
- **Verification**: `grep -c 'criticality-reason' skills/refine/SKILL.md` ≥ `1` (baseline `0`) **and** `uv run pytest tests/test_refine_reconcile_clarify.py tests/test_refine_reconcile_wiring.py tests/test_refine_skill.py tests/test_skill_size_budget.py -q` → exit 0. (The reason's *content* is `Interactive/session-dependent: model-generated per lifecycle and unpinnable by a fixture` — the flag's presence in the call is what is checkable.) All four pytest files are outside this task's **Files** and are run read-only as a regression gate — a failure in any of them indicates a Task 5 defect and is reported as blocked rather than patched, because R5 requires the pre-existing tests to pass unmodified.
- **Status**: [ ] pending

## Risks

- **The same closed clause set is applied to `--tier-reason` as to `--criticality-reason`.** R6 is written unscoped and its acceptance only exercises the criticality flag. The four tags (`reversibility` / `exposure` / `consequence` / `other`) are derived from the *criticality* rubric's OR-bundle, so a natural tier reason (`design-fork: …`, `blast-radius: …`) will be rejected and have to be written untagged or under `other:`. Chosen over an axis-specific set because R8's tally reads `split(':')[0]` and an unvalidated colon-bearing tier reason would still pollute a tally someone later widens. Reversible in one file if it proves annoying.
- **A criticality reason whose body happens to contain a colon before any tag is rejected** (`"see research.md: line 40"` → tag `see research.md`, out of set). This is the stated contract's direct consequence, not a defect — but it is the shape most likely to surprise an author. Task 7's prose stating the tag set is what prevents it.
- **R8's clause distribution starts empty and stays sparse.** The verification proves the recipe's scoping against a synthetic corpus; it cannot show real data, and the spec already prices the expected fill at 22–63% with an unreachable 10.5–16.7% seeded-`high` population. No test pins the recipe — it lives only in the ADR — deliberately, because a test embedding a copy of the one-liner creates a drift surface between ADR prose and test for no enforcement gain.
- **The ADR number is a live race.** It already moved once (0035 → 0036) mid-lifecycle. Task 1's `duplicate_number` assertion catches a collision at build time; if it fires, renumber to the next free value and re-run Tasks 2–4's greps, which all cite the number.

## Acceptance

`cortex/adr/0036-ceremony-relief-is-not-taken-on-the-criticality-axis.md` exists carrying the five evidence figures, and `grep -rl 'ADR-0036' cortex/requirements/project.md cortex/requirements/glossary.md cortex/backlog/452-*.md` returns all three files.
`reconcile-clarify --criticality-reason "exposure: …"` on a fresh lifecycle appends a `criticality_override` row whose `reason` the R8 recipe tallies as `exposure`; the same call without the flag is byte-identical to today's.
`uv run pytest tests/test_refine_reconcile_clarify.py tests/test_refine_module.py tests/test_refine_reconcile_wiring.py tests/test_refine_skill.py -q` passes with the pre-existing tests unmodified.
