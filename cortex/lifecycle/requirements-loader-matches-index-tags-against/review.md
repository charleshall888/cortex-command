# Review: requirements-loader-matches-index-tags-against — cycle 1

**Tier**: complex · **Criticality**: high · **Scope**: Stage 1 (spec compliance) + Stage 2 (code quality)

**Test baseline consumed** (not re-run): `just test` → 8/8 suites PASS, 2579 passed, 19 skipped, 1 xfailed,
14 subtests passed, run by the orchestrator after `b8ef9e5d`.

**Method note.** Every acceptance criterion below was executed against the working tree via
`uv run python -m cortex_command.lifecycle.<module>` or a direct import, never the `cortex-*` binaries on
PATH. That distinction is load-bearing here: `/Users/charliehall/.local/bin/cortex-load-requirements` still
runs the pre-#472 wheel and emits `no area docs matched for tags: [...]; loaded project.md only`. Two
independent derivations were built for the coverage number rather than reading the commit message.

---

## Stage 1 — Spec compliance

| # | Requirement | Rating |
|---|---|---|
| 1 | `index.md` carries `areas:` | PASS |
| 2 | Re-entry refreshes a stale `areas:` | PASS |
| 3 | Refresh is idempotent | PASS |
| 4 | Existing indexes backfilled in one shot | PASS |
| 5 | `## Conditional Loading` is an explicit map | PASS |
| 6 | Map preserves the synonym sets | PASS |
| 7 | Exact-key lookup, not substring | PASS |
| 8 | Measured coverage rises on the live tree | PASS |
| 9 | Four-state `COVERAGE:` marker on stderr | PASS |
| 10 | stderr stops claiming `project.md` only | PASS |
| 11 | Stale mechanism prose corrected | **PARTIAL** |
| 12 | `review.md` §1 consumes the marker | PASS (note) |
| 13 | `glossary.md` defines "area" | PASS (note) |
| 14 | Scaffold teaches a parseable separator | PASS |

No FAIL — Stage 2 ran.

### R1 / R2 / R3 — index write path — PASS

Executed `create_index` against a synthetic repo. Creation from an item with `areas: ['pipeline']` emits
`areas: [pipeline]`, which round-trips as `['pipeline']` through `load_requirements_cli._read_areas` — the
same stdlib reader the loader uses, no PyYAML dump introduced. Changing the item to
`['backlog','lifecycle']` and re-invoking returns `repaired` and leaves `areas: [backlog, lifecycle]` with
`created`, `artifacts`, `tags`, and both body lines byte-unchanged. Three further runs are byte-identical
(same sha1 across all three). Shape B (`--backlog-file ""`) renders `areas: []` and stays unlinked. A
hand-edited *unlinked* index is still skipped outright and gains no `areas:` field, so the existing #400
carve-out is intact.

### R4 — backfill — PASS

Materialized the pre-backfill tree from `3db19174~1` and swept it: `total=191, updated=147, unchanged=0,
unlinked=33, skipped=11`. The `areas:` line produced by that fresh sweep matches the committed data on all
147 files — zero mismatches — so the data commit is exactly what the verb produces.

Idempotence confirmed twice over, which is stronger than the orchestrator's own check:

- Three consecutive runs against the already-backfilled live tree: `updated=0, unchanged=147` each time,
  zero byte changes across 191 files.
- A second run against the freshly-backfilled tree **with `_today` monkeypatched from `2020-01-01` to
  `2099-12-31`**: `updated=0`, zero byte changes. The `updated:` bump lives inside the
  `rendered != text` branch in both `backfill_index_areas.py:141-149` and `create_index._refresh_linked_areas`,
  so a date change alone cannot churn. This was the specific risk raised; it does not exist.

Class handling verified on the live tree: 33 unlinked indexes, **0** of which carry an `areas:` key;
11 linked-but-item-declares-nothing, left without the field; 147 with a non-empty `areas:`, 0 empty.

### R5 / R6 / R7 — the map and its matcher — PASS

`_parse_conditional_loading` on the live `project.md` yields 7 rows; **no row's path contains a space**
(the HEAD defect — the 180-char `lifecycle` path — is gone, its parenthetical moved to a separator-free
prose line at `project.md:111`).

R6 checked adversarially for invention, not just for the superset. The delivered key set is 30 keys; all 26
the spec enumerates are present. The 4 extras are `escalation`, `lifecycle-state-machine`,
`phase-vocabulary`, `served-verbs` — I diffed against `91a5b92b~1:cortex/requirements/project.md`, whose
retired row 7 read `lifecycle state machine/phase vocabulary/served verbs (next, advance, enter)/escalation
→ …`. Splitting on `/` and kebab-normalizing reproduces all four exactly (the `(next, advance, enter)`
parenthetical correctly dropped from the key and relocated to prose). **Zero keys invented.**

R7's two traps confirmed through the real CLI: `areas: [pipe]` → no area doc, `COVERAGE:unmapped`;
`areas: [overnight-runner]` and `areas: [overnight runner]` both → `cortex/requirements/pipeline.md`,
`COVERAGE:loaded`.

### R8 — measured coverage — PASS, and the 41 figure independently confirmed

This was the orchestrator's primary ask, so I re-derived it by two paths that share no code:

- **Route A** — the shipped loader over `index.md` `areas:` for all 191 live indexes.
- **Route B** — straight from each index's parent backlog item's `areas:`, resolving the item by id and
  mapping through `project.md`, **never reading `index.md`'s `areas:` at all**.

| | Route A (loader / index copy) | Route B (backlog items direct) |
|---|---|---|
| covered | **86** | **86** |
| covered excluding `lifecycle.md`-only | **41** | **41** |
| per-lifecycle disagreements | **0** | — |

The 41 figure holds, and the zero per-lifecycle disagreement is the stronger result: the index-copy path did
not lose a single area the items carry. `lifecycle.md` existing on disk does inflate the headline number as
the orchestrator suspected — but the floor is 40 and the conservative reading is 41, so **R8 passes on both
readings**; the inflation does not carry the verdict.

Live state distribution: `loaded` 86, `unmapped` 61, `no-area` 44, `doc-missing` 0 (0 rather than the plan's
predicted 44, solely because `lifecycle.md` now exists). `unmapped` 61 and `no-area` 44 match the plan's
pre-check exactly.

**Regression check (no test covers this, and the ADR predicts a loss).** I rebuilt the HEAD baseline — old
loader module + old `project.md` + pre-backfill indexes — and diffed per lifecycle. HEAD covered 18; now 86.
Five lifecycles lost their HEAD area doc:

- Three (`discovery-output-density-…`, `lead-refine-4-…`, `lifecycle-implement-auto-enter-worktree-drop`)
  matched `remote-access.md` only because the tag `ux` is a substring of `tmux`. Losing these is the fix
  working exactly as specified.
- Two (`re-validate-test-worktree-seatbeltpy-on`, `reduce-sub-agent-dispatch-artifact-duplication`) are
  genuine losses: tags `worktree`/`dispatch` substring-matched `multi-agent.md`/`pipeline.md` plausibly, but
  their tickets declare no `areas:` at all, so they now report `no-area`. This is the tradeoff ADR-0037
  states and the spec's Non-Requirement on the 112 area-less items covers; critically, the loss is now
  *reported* rather than silent, which is the ticket's whole point.

### R9 / R10 — the coverage marker — PASS

Seven fixtures driven through the real CLI entry point with no flags. Every run emitted **exactly one**
`^COVERAGE:(loaded|doc-missing|unmapped|no-area)$` line on stderr, and **no run leaked the marker into
stdout**:

| fixture | marker | stdout |
|---|---|---|
| `areas: [overnight-runner]` | `loaded` | paths only, no detail line |
| `areas: [lifecycle]`, doc removed | `doc-missing` | `…/lifecycle.md (skipped: file absent)` retained |
| `areas: [skills]` | `unmapped` | paths only, **one** terse detail line |
| `areas: []` | `no-area` | `FALLBACK` note |
| dir exists, no `index.md` | `no-area` | `NO_INDEX` note, UNVERIFIED wording intact |
| no `--feature` at all | `no-area` | `FALLBACK` note |

#333's stdout contract survives: paths only, `project.md` first, `(skipped: file absent)` suffix intact.
Dedup verified on a purpose-built fixture — an area mapping to a `## Global Context` path is emitted once in
its Global Context position, and three keys mapping to one doc emit it once. #427's UNVERIFIED-vs-empty
split is preserved verbatim in meaning. R10: `grep -c 'loaded project.md only'` on the module returns 0.

### R11 — stale prose — PARTIAL

All four named absence checks return 0, and both `grep -c 'COVERAGE:'` checks return 1, with
`skills/` and `plugins/cortex-core/skills/` byte-identical for `review.md`, `requirements/SKILL.md`, and
`size-pin.txt`. `scripts/ratchet_refs.py` prints "all directories within their pins".

PARTIAL because a third shipped surface still describes the replaced mechanism and was not corrected:

```
bin/cortex-load-requirements:3
# Prints the tag-relevant requirements file list (paths only) for the repo; read-only, emits no event.
plugins/cortex-core/bin/cortex-load-requirements:3   (same line, mirrored)
```

Selection no longer reads `tags:` at all. This is the same defect class R11 exists to remove, in the same
phase, in a file `CLAUDE.md` gates behind a lifecycle — which #472 is. One line. Outside R11's four named
acceptance checks, hence PARTIAL rather than FAIL.

### R12 — marker consumer — PASS, with a factual note

`review.md` §1 now names all four states, classifies anything but `loaded` as "a warning, not a routine
fallback", and instructs handing it to the reviewer with the path list. That is a real behavioral
instruction, not a decorative mention — substantive on the merits.

Two honest qualifications, neither changing the rating:

1. Per `cortex/requirements/project.md:23`, discharge of the Deletion-bias presumption requires "a consumer
   that turns a build or gate red when the surface is removed". Reference prose is not that, and
   `docs/policies.md` forbids a test that would make it that. The discharge therefore rests on the spec's
   argument rather than on the clause's literal terms. This is the correct outcome given the policy
   constraint, but it should not be recorded as a strict discharge.
2. The consumer is not yet live anywhere. `review.md` §1 prescribes `cortex-load-requirements`, which
   resolves to the released wheel; I ran it and it still emits the pre-#472 text with no `COVERAGE:` line.
   This is ordinary wheel lag resolved by the auto-release on push to `main`, not a defect — but the brief I
   received states the verb "emitted `COVERAGE:loaded`", and that is not reproducible from the PATH binary
   today.

### R13 — glossary — PASS, with a defect the repo's own gate flags

`grep -c '\*\*area\*\*'` returns 1, in the file's one-line format. However the entry ends `→ ADR-0037`, and
**`cortex/adr/0037-*` does not exist** (the directory stops at 0036). Running `bin/cortex-adr-citation-audit`
reports `ADR-0037` in `cortex/requirements/glossary.md` as a phantom citation. `project.md:41` names this
audit as a surviving gate whose evidence is precisely "a consumer repo accumulated dozens of phantom-ADR
references"; `glossary.md` is `## Global Context` and loads on every invocation of the verb. The spec does
propose ADR-0037, so writing it at the complete phase resolves this — recorded so it is not missed.

### R14 — scaffold — PASS

`_parse_conditional_loading` on the template returns
`[('<area>, <alias>', 'cortex/requirements/<area>.md')]` — non-empty (it was `[]` at HEAD), U+2192
separator, repo-root-relative path, comma-separated keys matching the format this repo's own `project.md`
now uses, `TODO:` framing preserved.

---

## Stage 2 — Code quality

**Plan verification steps were genuinely executed.** I re-ran Task 2's parse assertion, Task 3's template
parse, Task 4's grep, Task 5's four greps plus the ratchet, Task 6's four cases, and Task 7's coverage
measurement and idempotence check independently. All reproduce. Nothing was claimed that does not hold.

**The Task 6 parent-resolution deviation is sound — verified, not reasoned.** The builder resolved parents by
`parent_backlog_id` through `resolve_item._resolve_numeric` rather than the plan's
`root/cortex/backlog/<basename>` wikilink route. I cross-checked all **158** id-resolved live indexes by
comparing the index's `parent_backlog_uuid` against the resolved item's `uuid`: **0 mismatches**. The
mis-resolution path is guarded — `_resolve_parent_areas` returns `None` unless exactly one file matches, and
the corpus does contain a duplicate id (`474` appears on two backlog files), which the guard skips safely; no
index points at it. The zero-padding concern is handled by `_resolve_numeric` comparing leading digits as
integers. This deviation is better than the plan's route, and the docstring documents why.

**Naming and pattern consistency: good.** `_extract_areas`/`_read_areas` mirror `_extract_tags`/`_read_tags`
through a shared `_extract_list_field`, preserving the never-raises and empty-strip contracts. `upsert_areas`
is a single shared byte contract used by both `_refresh_linked_areas` and the backfill, so the two writers
cannot diverge. `_render_tags` is reused for `areas:` rather than a second (PyYAML) writer the stdlib reader
could not survive. `_AREAS_BLOCK` correctly absorbs block-sequence continuation lines so replacing an
`areas:` key cannot orphan `- item` lines. Frontmatter edits are bounded to the leading fence throughout.

### Issues

1. **`backfill_index_areas` has no per-file error isolation** (`backfill_index_areas.py:128`). I fed it a
   tree containing one index with malformed YAML frontmatter: `_parse_frontmatter` raised an uncaught
   `yaml.ParserError`, the process died with a traceback at exit 1, and the sweep **aborted mid-run** — a
   later, well-formed index was never processed and no summary was emitted. A whole-tree migration can
   therefore land half-applied on a single hand-edited file. This diverges from the defensive posture of
   both its own seam (`create_index._split_frontmatter` returns `None` specifically to "leave a hand-edited
   file alone rather than guess") and the loader's explicit never-raises contract. Low practical severity —
   the verb is one-shot and has already run cleanly on 191 files — but the guard is a try/except around one
   call. Not covered by any acceptance criterion or test.

2. **The stdout-purity assertions cannot detect the leak they exist to prevent.**
   `tests/test_load_requirements_cli.py:_is_path_line` accepts any line that equals its own strip and
   contains no space. `COVERAGE:loaded` satisfies both, so `test_stdout_is_paths_only` and the stdout half of
   `test_every_run_emits_exactly_one_marker` would pass if the marker were written to stdout — the exact
   #333 violation R9 is built to avoid. I verified empirically that no leak exists today (7 fixtures, 0
   occurrences of `COVERAGE` on stdout), so this is a blind spot, not a live bug. An
   `assert not line.startswith("COVERAGE:")` closes it.

3. **Stale `tag-relevant` comment in `bin/cortex-load-requirements` and its plugin mirror** — see R11 above.

4. **Phantom `ADR-0037` citation in `glossary.md`** — see R13 above.

Issues 3 and 4 are one-line fixes; 1 and 2 are small and non-blocking. None affects delivered behavior.

---

## Requirements Drift

- **State**: detected
- **Findings**:
  - `cortex/requirements/lifecycle.md:119` states that an ad-hoc lifecycle's `index.md` "gets an empty tag
    list, so this doc's trigger cannot match" — false after this change; selection reads `areas:` and never
    `tags:`, and the correct statement is that an ad-hoc index carries `areas: []` and reports `no-area`.
  - `cortex/requirements/lifecycle.md:123` lists as an **open question** whether the `## Conditional Loading`
    matcher "should be widened or replaced — today it is ASCII-casefold substring matching against an index's
    tags", "Owned by backlog #472, out of scope here". #472 has now replaced it; the question is resolved and
    its description of current behavior is false.
  - New lifecycle-surface behavior not captured anywhere in `lifecycle.md`: `index.md` gained an `areas:`
    field refreshed on every linked re-entry, and the requirements verb now emits a four-state `COVERAGE:`
    marker the Review phase reads.
  - Timing note, so this is not misread as a Task 5 miss: `lifecycle.md` was committed by a *different*
    session earlier the same day (`48db0fed`), after #472's plan was written under the assumption the file
    would not exist. The drift is real but was not foreseeable at plan time.
- **Update needed**: `cortex/requirements/lifecycle.md`

## Suggested Requirements Update

- **File**: `cortex/requirements/lifecycle.md`
- **Section**: `## Edge Cases`
- **Content** (replaces the existing line 119 bullet, which must be deleted):

```
- **A lifecycle is created ad-hoc with no backlog file**: its `index.md` carries `areas: []`, so no area doc is selected and the load reports `COVERAGE:no-area` while still loading `project.md` + Global Context. The repair carve-out populates `areas:` once the backlog match is known; until then, read this doc directly.
```

- **File**: `cortex/requirements/lifecycle.md`
- **Section**: `## Architectural Constraints`
- **Content** (append; and delete the now-resolved first bullet under `## Open Questions`, line 123):

```
- **Requirements selection is exact-key lookup on `index.md` `areas:`**: the `## Conditional Loading` map in project.md is the area vocabulary, matched by exact kebab-normalized key — never substring. `index.md` carries `areas:` copied from its backlog item at creation and refreshed on every linked re-entry (`tags:` is retained but inert). Every run of the loader emits one `COVERAGE:(loaded|doc-missing|unmapped|no-area)` line on stderr, which the Review phase reads. → #472, ADR-0037.
```

---

## Verdict

Fourteen requirements, all acceptance criteria executed against the working tree; one PARTIAL, no FAIL. The
load-bearing evidence — that the index-copy path lost nothing relative to the backlog items — reproduces
independently by two disjoint routes with zero per-lifecycle disagreement, and the coverage floor is cleared
on the conservative reading (41 ≥ 40) as well as the headline one (86). The Task 6 deviation from the plan is
better than the plan and verified clean across all 158 resolvable indexes. The four issues are small,
non-blocking, and named above.

```json
{"verdict": "APPROVED", "cycle": 1, "issues": ["backfill_index_areas.py:128 has no per-file error isolation: one malformed index.md frontmatter raises an uncaught yaml.ParserError and aborts the sweep mid-run, leaving a whole-tree migration half-applied with no summary (verified by fixture); diverges from the never-raises posture of its own create_index seam and the loader", "tests/test_load_requirements_cli.py:_is_path_line accepts 'COVERAGE:loaded' as a path line, so test_stdout_is_paths_only and test_every_run_emits_exactly_one_marker cannot detect a marker leak into stdout - the exact #333 violation R9 exists to prevent (no leak exists today; verified over 7 fixtures)", "bin/cortex-load-requirements:3 and its plugins/cortex-core mirror still describe the verb as printing the 'tag-relevant' requirements list - the same replaced-mechanism prose R11 removes elsewhere, in a shipped surface, uncorrected (R11 rated PARTIAL for this)", "cortex/requirements/glossary.md:10 cites ADR-0037, which does not exist; bin/cortex-adr-citation-audit flags it as a phantom citation in a Global Context file loaded on every verb invocation. The spec proposes this ADR, so writing it at the complete phase resolves it"], "requirements_drift": "detected"}
```
