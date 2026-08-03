# Review: triage-routes-ready-items-by-ticket (cycle 2)

Reviewed at `460ca112` (cycle-1 review was at `eb84b296`; lifecycle base `81b8b48a`).
Criticality `high`, tier `complex`. Focused re-review of the operator-directed rework —
not a from-scratch repeat. Source-read + static verification only; the post-rework
full-suite baseline (`2279 passed, 19 skipped, 1 xfailed, 13 subtests passed`, zero
failures, identical to cycle 1) was provided and **not** re-run.

## Cycle 1 summary and disposition

Cycle 1 returned **APPROVED** with 8 PASS / 2 PARTIAL and five non-blocking issues. The
operator overrode the approval and directed rework on exactly one of them. Dispositions:

| # | Cycle-1 rating | Finding | Disposition |
|---|---|---|---|
| R1 | PASS | Readiness governs the recommendation for every type | Carried forward |
| R2 | PARTIAL | (a) PASS; (b) `test_recommendation_never_spans_lines` vacuous by construction; (c) deviation accepted | **Accepted as-is** — the single-line constraint is held by the module's exact-full-block assertions |
| R3 | PASS | Byte-identity guard on type-sensitive fixtures (with the observation that only `idea` is now type-sensitive) | Carried forward |
| R4 | PASS | Trivial-change cheap path delegated to the dev skill | Re-checked this cycle (rework target) |
| R5 | PASS | `idea` → `/cortex-core:discovery` preserved | Re-checked this cycle (rework target) |
| R6 | PARTIAL | Footer/child contradiction closed for *unrefined* ideas; a **refined** `idea` child still licenses the overnight sentence | **Deferred** to backlog item **#431** — requirement 6's acceptance criterion covers unrefined ideas only, so this is a scope extension, not a spec miss |
| R7 | PASS | `test_dev_triage_refs_wired.py` green without weakening | Carried forward |
| R8 | PASS | Behavioral coverage for `render()` | Carried forward |
| R9 | PASS | Ticket-425 regression guard | Carried forward |
| R10 | PASS | Child-of-non-ready-epic behavior pinned | Carried forward |
| Stage 2 (v) | Non-blocking issue | `skills/dev/SKILL.md`'s Step 3 clause claimed rules 3-5 key on `type`, so a picked `idea` could route to `/cortex-core:refine` against the `/cortex-core:discovery` the board just printed | **FIXED in `460ca112`** — the subject of this cycle |
| Stage 2 (blocked-child) | Non-blocking issue | The spec's `[blocked]`-mark edge case is correct by inspection but untested | Unchanged; still open, still non-blocking |
| Requirements drift | detected | No loaded requirement captured the triage routing rule | **Applied** to `cortex/requirements/backlog.md` (verified below) |

## Cycle 2 findings

### 1. The rework fixes what it claimed, and introduces nothing new — **PASS**

The commit touches exactly two files, one canonical and one mirror:

```
 plugins/cortex-core/skills/dev/SKILL.md | 4 ++--
 skills/dev/SKILL.md                     | 4 ++--
```

New wording (`skills/dev/SKILL.md:36-38`):

```
- **`ok`** → print `blocks` verbatim, then ask which item to pick up. Once picked,
  route it from Step 1 (first match wins), honoring the printed recommendation for
  an `idea` row — rules 3-5 key on phrasing, triviality, and readiness, not on `type`.
```

**Accuracy against Step 1 (`:14-18`), rule by rule:**
- Rule 3 — "**Vague topic** ("not sure how to approach", "explore", "investigate")" → keys
  on **phrasing**. ✓
- Rule 4 — "**Trivial change** (single file, existing pattern, one obvious approach)" → keys
  on **triviality**. ✓
- Rule 5 — "**Otherwise** → assess criticality (Step 2), then route by the ticket's
  **readiness**" → keys on **readiness**. ✓

None of the three inspects `type`. The negative half of the clause ("not on `type`") is
literally true, and the positive half enumerates the three keys in rule order. The
cycle-1 defect — an assertion that was simply false about the file it pointed at — is
gone.

**Does the fix actually close the routing contradiction?** Yes, and without a first-match-wins
conflict. The board prints `/cortex-core:discovery` for an `idea` row; honoring it lands the
item at rule 3's destination, and rule 3 *precedes* rules 4 and 5 in the ladder. So "honor
the printed recommendation" and "first match wins" agree rather than compete — the honor
clause is a tie-break that the ladder's own ordering already licenses, not an override
bolted on top of it. Had the fix instead added a `type: idea → discovery` rule to Step 1,
it would have restored the exact ordering ambiguity plus a prose copy of a verb-owned rule.

**Is it on the right side of the #343 boundary?** Yes. The clause names `idea` only as *the
row shape whose printed recommendation must be honored* — it does not restate the rule
`idea → /cortex-core:discovery`. If the verb ever changed `idea`'s destination, this prose
would remain correct without edit. That is the correct coupling: the skill defers to the
verb's rendered output rather than mirroring its logic. Control flow only, per the
Non-Requirements and #343.

**Why only `idea` needs the honor clause** (a deliberate asymmetry the clause does not
spell out, and does not need to): for every other type the board's recommendation is
derivable from the ladder — a refined item prints `/cortex-core:build` and rule 5 routes it
to `/cortex-core:build`; an unrefined one prints `/cortex-core:refine` and rule 5 routes it
to `/cortex-core:refine`. The only intentional divergence is rule 4's trivial hatch, which
requirement 4 exists specifically to make reachable, so a picked trivial refined chore
landing on rule 4 instead of the printed `/cortex-core:build` is the designed behavior, not
a regression of the same class.

**Nothing new introduced:**
- `_MOVED_TOKENS` negative control — all twelve strings from
  `tests/test_dev_triage_refs_wired.py:30-46` checked against the post-rework file;
  resident set is `[]`. Requirement 4(c) holds.
- `## Step 2: Criticality Pre-Assessment` (the `_STUB_HEADINGS` anchor) and
  `cortex-backlog-triage` both still present, so `test_stub_headings_survive` and
  `test_skill_invokes_the_triage_verb` are structurally safe.
- L1 surface untouched — the ratchet measures `description` + `when_to_use` frontmatter
  only (`tests/test_l1_surface_ratchet.py:1-11`), and the rework edits the body. The
  `"dev": 285` budget row is unaffected.
- Line count unchanged (the clause still hard-wraps across the same three physical lines);
  the file is 42 lines against a 500-line cap.

**Dual-source mirror — PASS.** `diff skills/dev/SKILL.md
plugins/cortex-core/skills/dev/SKILL.md` is clean (byte-identical), and both sides moved 4
lines in the same commit, consistent with a hook-rebuilt mirror rather than a hand edit.
`triage.py` is correctly still absent from the mirror set.

### 2. Requirement 4 re-check — **PASS**

- (a) `route it from Step 1` occurs exactly once, inside Step 3's `ok` bullet
  (`skills/dev/SKILL.md:37`). The substring survived the rewording — it was preserved
  verbatim, with the change confined to the clause that follows it.
- (b) `grep -c "implement directly if trivial" cortex_command/backlog/triage.py` → `0`;
  `triage.py` is untouched by the rework, so this carries forward unchanged.
- (c) No `_MOVED_TOKENS` string reintroduced (verified above); the guard file is green in
  the baseline.
- The clause remains genuinely enabling — with an argument present, Step 1's ladder skips
  rule 1 and can reach rule 4, which was unreachable on the triage path before this change.

### 3. Requirement 5 re-check — **PASS**

The verb side is untouched: `_recommendation` still tests `type == "idea"` before consulting
`_is_refined`, and `test_idea_routes_to_discovery_with_and_without_spec` still pins both arms
with exact full-block assertions. What the rework adds is the *consumer-level* half that
cycle 1 found missing: previously the verb correctly printed `/cortex-core:discovery` for an
idea row and the skill then contradicted it by routing the picked item through rules 3-5 on
`type` (which no rule reads), typically landing on rule 5 → `/cortex-core:refine`. The new
clause makes the printed recommendation binding for that row. Requirement 5's preservation
now holds end-to-end — board **and** the route the picked item actually takes — rather than
only at the render boundary.

### 4. Nothing else regressed — **PASS**

`git diff --stat eb84b296 HEAD -- cortex_command/backlog/triage.py tests/test_triage_render.py
tests/test_dev_triage_refs_wired.py` is empty: all three are byte-identical to the cycle-1
reviewed state. The only other commit in the range (`2bd09eac`) adds three unrelated
harness-friction backlog tickets and touches no feature file. The full range
`eb84b296..HEAD` is: 3 new backlog ticket files, plus the 4-line clause change on each side
of the dual-source pair. Test baseline is byte-identical to cycle 1's, which is the expected
signature of a prose-only edit that no test asserts on.

### 5. Carried-forward ratings (R1, R2, R3, R6, R7, R8, R9, R10)

All carry forward at their cycle-1 values. This is safe because the rework changed **only
markdown prose in `skills/dev/SKILL.md`** and its mechanically-regenerated mirror —
verified by `git show --stat 460ca112`, not inferred. Requirements 1, 2, 3, 5 (verb side),
6, 8, 9 and 10 are all satisfied by `cortex_command/backlog/triage.py` and
`tests/test_triage_render.py`, both provably untouched; requirement 7 is satisfied by
`tests/test_dev_triage_refs_wired.py`, also untouched and still green. The one place the
rework could have reached a carried-forward rating is requirement 7 — via `_MOVED_TOKENS`
reintroduction or a lost stub heading — and both were re-checked directly above rather than
assumed. Requirements 4 and 5 were the rework targets and were re-derived from scratch.

The two cycle-1 PARTIALs stay PARTIAL: R2 by operator acceptance (the vacuous
single-line test), R6 by deferral to #431. Neither was in scope for this rework.

### 6. Stage 2 notes (cycle 2 only)

- **Prose cost.** The clause grew roughly +65 bytes (~98 → ~163 chars). This is L2 body
  prose, re-read only when the `dev` skill actually loads, not L1 frontmatter carried in
  every session's system prompt. Given that it converts a false statement into a true one
  and closes a consumer-visible routing contradiction, the trade is clearly worth it — but
  worth noting explicitly under the standing token-reduction posture rather than letting it
  pass silently.
- **Cosmetic, carried from cycle 1 and unchanged:** the Non-Requirements say "one line
  changes in `skills/dev/SKILL.md`" — it is one clause, still hard-wrapped across three
  physical lines while every sibling bullet in that list is a single unwrapped line. Not
  introduced by the rework; the wrap shape is identical to cycle 1's.
- **Uncommitted working-tree state (expected, flagged for the complete phase, not a
  defect):** the requirements drift bullet in `cortex/requirements/backlog.md` and ticket
  `cortex/backlog/431-*.md` are both present on disk but not yet committed, alongside the
  usual lifecycle artifacts (`events.log`, `index.md`, `plan.md`) and the `425` ticket's
  status update. They need to land with the completion commit — if the drift bullet in
  particular is dropped, the cycle-1 drift finding silently reopens.

## Requirements Drift

**State**: none

**Findings**:
- The cycle-1 drift finding was **applied** and verified. `cortex/requirements/backlog.md`
  `## Architectural Constraints` (`:102`) now carries the suggested bullet **verbatim**:
  > Triage recommendations are computed by the `cortex-backlog-triage` verb from readiness
  > (`spec:` presence), never from ticket `type` — `idea` is the sole type-keyed exception,
  > because it is a readiness statement rather than a problem-kind label. Both rendered
  > blocks call the one shared function, so a ticket's route cannot depend on which block it
  > appears in (#425; the verb-not-prose boundary is #343).

  Verified against the shipped source: it is accurate on all three claims — readiness-keyed
  (`_recommendation` consults `_is_refined`), `idea` as sole type-keyed exception (the one
  `type ==` test in the function), and both blocks calling the one shared function
  (`render()`'s flat row and `_render_epic_block`'s per-child mark). It sits in the right
  section, alongside the other backend/boundary constraints, and back-points rather than
  restating rationale, matching the section's established style.
- It is a working-tree modification, not yet committed — see the Stage 2 note above.
- The rework introduced no new drift. It changed only skill body prose, and the behavior it
  describes (honor the printed recommendation; the ladder keys on phrasing/triviality/
  readiness) is already covered by the bullet just added plus the #343 verb-not-prose
  boundary it cites. No loaded requirement (`project.md`, `glossary.md`, `backlog.md`) makes
  a claim the new wording contradicts.

**Update needed**: none

## Verdict

```json
{"verdict": "APPROVED", "cycle": 2, "issues": ["Rework verified: skills/dev/SKILL.md:36-38 now correctly states rules 3-5 key on phrasing, triviality, and readiness (matching Step 1 rules 3/4/5 exactly) and makes the printed recommendation binding for an idea row; the honor clause agrees with first-match-wins because rule 3 already precedes rules 4-5, and it defers to the verb's output rather than restating the idea->discovery rule, so the #343 boundary holds", "Carried forward from cycle 1, accepted by operator: test_recommendation_never_spans_lines cannot fail (non-DOTALL regex capture on rendered text rather than _recommendation()'s return value); the single-line constraint is held instead by the exact-full-block assertions in the requirement-8 tests", "Carried forward from cycle 1, deferred to backlog #431: a refined `idea` child still counts toward the all-refined bucket and licenses the /cortex-overnight:overnight sentence three lines below its own /cortex-core:discovery row; requirement 6's acceptance criterion covers unrefined ideas only, so this is a scope extension rather than a spec miss", "Carried forward from cycle 1, still open and non-blocking: the spec's blocked-epic-child edge case ([blocked] retained after the recommendation on one line) is correct by inspection but has no test anywhere in tests/", "Housekeeping for the complete phase, not a defect: the requirements drift bullet in cortex/requirements/backlog.md and ticket cortex/backlog/431-*.md are present on disk but uncommitted; if the drift bullet is dropped from the completion commit the cycle-1 drift finding silently reopens", "Minor: the clause grew ~65 bytes of L2 skill-body prose (not L1 frontmatter, so the dev 285-byte ratchet row is unaffected) and still hard-wraps across three physical lines while sibling bullets are single unwrapped lines"], "requirements_drift": "none"}
```
