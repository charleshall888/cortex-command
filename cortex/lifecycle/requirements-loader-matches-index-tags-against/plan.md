# Plan: requirements-loader-matches-index-tags-against

## Overview

Move requirements selection off substring-matched `index.md` `tags:` and onto exact-key lookup of
`index.md` `areas:` against an explicit many-to-one area→doc map in `project.md`'s `## Conditional
Loading`, then backfill the 190 existing indexes so the change is measurable on the live tree. Two
structural contracts change independently — the index frontmatter schema (`create_index.py`) and the
map format plus its parser (`project.md` + `load_requirements_cli.py`) — so they build in parallel and
only meet at the live backfill, where coverage is measured.

## Outline

### Phase 1: Contract change (tasks: 1, 2)
**Goal**: `index.md` carries `areas:` at every write point, and the loader selects on an exact-key
area→doc map with a four-state coverage marker.
**Checkpoint**: `just test` green; a synthetic index declaring `overnight-runner` resolves
`cortex/requirements/pipeline.md`, one declaring `pipe` resolves no area doc.

### Phase 2: Migration tool and doc retirement (tasks: 3, 4, 5, 6)
**Goal**: the one-shot backfill verb exists, and every doc surface describing the replaced mechanism
is corrected or wired to the new marker.
**Checkpoint**: `just test` green; the backfill verb runs to completion on a throwaway tree and is
idempotent on re-run.

### Phase 3: Live backfill and coverage proof (task: 7)
**Goal**: existing indexes carry `areas:`, and measured coverage clears the spec's floor.
**Checkpoint**: ≥40 of `cortex/lifecycle/*/index.md` load at least one area doc that exists on disk
(17 at HEAD); a second backfill run leaves an empty `git diff`.

## Tasks

### Task 1: `index.md` carries `areas:` at creation and on re-entry
- **Files**: `cortex_command/lifecycle/create_index.py`, `tests/test_create_index.py`
- **What**: Adds an `areas:` frontmatter field to the byte-faithful index template, copies the parent
  backlog item's `areas:` into it at creation, and extends the repair path so an *already-linked*
  index has its `areas:` refreshed on every `cortex-lifecycle-enter --backlog-file` — closing the
  staleness `spec-approve`'s write ordering creates. Satisfies spec Requirements 1, 2, 3.
- **Depends on**: none
- **Complexity**: complex
- **Context**: `_render` at `:110-142` emits the fixed 7-field block; add `areas:` rendered by the
  existing `_render_tags` helper (`:90-107`), which produces the unquoted inline flow form
  (`[a, b]` / `[]`) that `load_requirements_cli._extract_tags` parses — the new field must round-trip
  through that same stdlib reader, so do not introduce a PyYAML dump. `create_index` at `:221-272`
  already calls `_parse_frontmatter(backlog_path)` and reads `fm.get("tags")` at `:243`; read
  `fm.get("areas")` alongside it. `_repair_unlinked_index` at `:166-218` today returns `skipped`
  unless `parent_backlog_uuid`/`parent_backlog_id`/`tags` **all** byte-match the Shape-B defaults
  (`:194-200`) — that guard must keep gating the existing three-line repair, and the new `areas:`
  refresh must run on the *linked* path it currently rejects. Preserve `artifacts`, `created`, and
  body bytes exactly, as the existing repair does. **Seam for Task 6**: expose the frontmatter
  `areas:` upsert (insert when absent, replace when present, scoped to the frontmatter block only) as
  a module-level helper so the backfill verb imports it rather than re-editing this file. Existing
  callers that must keep working unchanged: `enter.py:321`, `refine.py:773`, and the Shape-B
  (`--backlog-file ""`) arm, which renders `areas: []`. Frontmatter edits must stay bounded to the
  leading `---` block, per the existing rationale at `:182-192`.
- **Verification**: `uv run pytest tests/test_create_index.py -q` passes, including a new case
  asserting an index created from an item with `areas: ['pipeline']` round-trips as `['pipeline']`
  through `load_requirements_cli`'s frontmatter reader, and a new case running the refresh twice
  against a linked index whose item changed from `['backlog']` to `['pipeline']` — second run
  byte-identical, `created`/`artifacts`/body unchanged.
- **Status**: [x] done (91a5b92b 2026-08-07T18:07:52-04:00)

### Task 2: Area→doc map replaces trigger-substring selection, with a coverage marker
- **Files**: `cortex/requirements/project.md`, `cortex_command/lifecycle/load_requirements_cli.py`,
  `tests/test_load_requirements_cli.py`, `tests/test_refine_session_ownership.py`
- **What**: Rewrites `## Conditional Loading` as an explicit many-to-one area→doc map, switches
  selection from casefold-substring on `tags:` to exact kebab-normalized key lookup on `areas:`, and
  emits a four-state machine-parseable coverage marker on stderr. Satisfies spec Requirements 5, 6,
  7, 9, 10.
- **Depends on**: none
- **Complexity**: complex
- **Context**: **Map format** — each row keeps the U+2192 separator the parser already requires
  (`ARROW` at `:60`), with a comma-separated key list on the left and a bare repo-relative path on the
  right: `- statusline, dashboard, notifications → cortex/requirements/observability.md`. The
  `## Conditional Loading` **heading text must be preserved** — `validate_requirements_doc_cli.py:70-71`
  asserts it exists. The `lifecycle` row's trailing parenthetical (`project.md:107`) is the live
  malformed-path defect: move that prose onto a line carrying **no** U+2192, or `_parse_conditional_loading`
  will read it as another row. **Key set** — derive keys mechanically by splitting the existing trigger
  lists on `/` and kebab-normalizing; invent nothing. The result must be a superset of the 25 keys spec
  Requirement 6 enumerates, **plus** the bare key `lifecycle`, which today normalizes only to
  `lifecycle-state-machine` and is why 44 tickets declaring `areas: ['lifecycle']` miss.
  `cortex/requirements/lifecycle.md` stays absent — #469 owns writing it, and until then those 44 are
  the `doc-missing` tier, not a defect here. **Parser** — `_parse_conditional_loading` at `:169-184`
  currently takes `path_part.strip()`, absorbing all trailing free text; take the first
  whitespace-delimited token instead so a stray parenthetical can never re-enter a path. **Selection** —
  `resolve` at `:200-266` matches `tag.lower() in trigger_lower` at `:226`; replace with equality on
  kebab-normalized keys (lowercase, spaces and underscores to hyphens) against the index's `areas:`.
  Add an `_extract_areas`/`_read_areas` pair mirroring `_extract_tags` (`:95-126`) and `_read_tags`
  (`:133-150`) — same stdlib-only inline-flow + block-sequence handling, same empty-entry stripping
  (correction (i)), same never-raises contract. `index.md` `tags:` is left in place and becomes inert;
  do not remove it. **Coverage marker** — one stderr line per run matching
  `^COVERAGE:(loaded|doc-missing|unmapped|no-area)$` on the verb's existing default invocation, no new
  flag. Precedence: any declared area resolving to a doc present on disk → `loaded`; else any declared
  area mapped to a doc absent from disk → `doc-missing` (name the area and expected path); else areas
  declared but none in the map → `unmapped`, **at most one terse line** (the live tally is `skills` 45,
  `hooks` 7, `tests` 5 — a per-area report here is the recurring noise that would retrain operators to
  ignore the signal); else → `no-area`, which must preserve #427's `NO_INDEX_NOTE_TEMPLATE` vs
  `FALLBACK_NOTE_TEMPLATE` UNVERIFIED-vs-empty split (`:61-73`, selected at `:248-264`) verbatim in
  meaning. Both templates currently end in `loaded project.md only`, which is false — `glossary.md` is
  `## Global Context` and loads unconditionally on the fallback path — so both strings must be reworded
  (Requirement 10). **stdout is unchanged**: paths only, one per line, `project.md` first, `(skipped:
  file absent)` suffix preserved, dedup-by-resolved-path with Global Context placement winning — #333's
  contract survives untouched, which is why the marker is stderr-only. **Caller enumeration for the
  `resolve()` signature**: returning coverage alongside `(lines, note)` changes the two-tuple unpack at
  `main()` (`:301`), `tests/test_load_requirements_cli.py:23` (module-wide use), and
  `tests/test_refine_session_ownership.py:255,262` — that last one is outside this ticket's obvious
  blast radius and must be updated or the suite goes red. **Tests to rewrite** (semantics change, all in
  `tests/test_load_requirements_cli.py`): `:99`, `:160`, `:176`, `:192`, `:204`, `:310`, `:321`.
  **Tests tracking the format change**: `:335`, `:344` (explicitly pins the retired compound-slash
  format), `:360`. The `:344`/`:360` live tests read the real `project.md` but attach synthetic indexes
  in `tmp_path`, so they do not depend on Task 7's backfill.
- **Verification**: `uv run pytest tests/test_load_requirements_cli.py tests/test_refine_session_ownership.py -q`
  passes, including new cases: an index declaring `pipe` loads no area doc; one declaring
  `overnight-runner` loads `cortex/requirements/pipeline.md`; and four fixture runs of
  `cortex-load-requirements --feature <f>` with no flags each emit exactly one stderr line matching
  `^COVERAGE:(loaded|doc-missing|unmapped|no-area)$` with the state expected for that fixture, with
  stdout byte-identical to HEAD's shape. Plus:
  `uv run python -c "from cortex_command.lifecycle.load_requirements_cli import _parse_conditional_loading as p; from pathlib import Path; rows=p(Path('cortex/requirements/project.md').read_text()); assert rows and all(' ' not in path for _, path in rows), rows; print(len(rows))"`
  exits 0 (fails at HEAD — the `lifecycle` row yields a 180-character path containing its parenthetical).
- **Status**: [x] done (affd88f3 2026-08-07T18:14:10-04:00)

### Task 3: Consumer-repo scaffold teaches a parseable separator
- **Files**: `cortex_command/init/templates/cortex/requirements/project.md`
- **What**: Replaces the scaffold's ASCII `->` example with the U+2192 separator the parser requires,
  in the map format Task 2 establishes, so a consumer repo following the scaffold's own example gets a
  parseable section instead of zero area docs. Satisfies spec Requirement 14.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `:42-46` scaffolds `## Conditional Loading` with the example line
  `Working on <area> -> requirements/<area>.md`. The parser (`load_requirements_cli.py:60`) recognizes
  only U+2192, so this template line parses to nothing today. Two independent defects in one line: the
  ASCII separator, and a path relative to `cortex/requirements/` rather than the repo root that
  `resolve()` resolves literally against. Fix both, and match the comma-separated-keys map shape Task 2
  writes into this repo's own `project.md` so the scaffold teaches the format that is actually read.
  Keep the surrounding `TODO:` framing — this is a template, not a populated doc.
- **Verification**:
  `uv run python -c "from cortex_command.lifecycle.load_requirements_cli import _parse_conditional_loading; from pathlib import Path; print(_parse_conditional_loading(Path('cortex_command/init/templates/cortex/requirements/project.md').read_text()))"`
  prints a non-empty list. Verified at HEAD: prints `[]`.
- **Status**: [x] done (ccdbd86f 2026-08-07T18:02:56-04:00)

### Task 4: `glossary.md` defines "area"
- **Files**: `cortex/requirements/glossary.md`
- **What**: Adds a one-line `area` entry under `## Language`, the term the whole map turns on and which
  has zero occurrences in the file today. Satisfies spec Requirement 13.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The file is five one-line entries under `## Language`, format
  `- **term**: one sentence, optional rubric pointer, optional → ADR-NNNN`. Match that shape exactly;
  the entry defines an area as the backlog-item `areas:` vocabulary that selects requirements docs
  through `project.md`'s `## Conditional Loading` map, and may point at the proposed ADR-0037. Note the
  file is `## Global Context` and loads on **every** invocation of the verb, including the fallback
  path — one line is the whole budget.
- **Verification**: `grep -c '\*\*area\*\*' cortex/requirements/glossary.md` returns ≥ 1.
- **Status**: [x] done (ad845eb6 2026-08-07T18:02:39-04:00)

### Task 5: Retire the stale mechanism prose and wire `review.md` §1 to the marker
- **Files**: `skills/build/references/review.md`, `skills/requirements/SKILL.md`,
  `skills/build/references/size-pin.txt`,
  `plugins/cortex-core/skills/build/references/size-pin.txt` (edited and staged by hand — the one
  mirror path `just build-plugin` does not carry),
  `plugins/cortex-core/skills/build/references/review.md` and
  `plugins/cortex-core/skills/requirements/SKILL.md` (**read-only, for the Verification greps only** —
  both are regenerated from staged blobs by the pre-commit hook and must never be edited or staged by
  hand)
- **What**: Removes the two prose claims that become false after Task 2 and, in the same `review.md`
  §1 edit, has the Review phase read the `COVERAGE:` marker and surface a non-`loaded` result to the
  reviewer alongside the existing path list. Satisfies spec Requirements 11 and 12.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `skills/build/references/review.md:9` states the cause of a miss as "an index.md that
  never received its backlog tags, repaired by re-running `cortex-lifecycle-enter`" — false after Task
  2, since selection no longer reads `tags:` at all. `skills/requirements/SKILL.md:63` states "trigger
  phrases must intersect real lifecycle `index.md` `tags:` words" — likewise false; that line documents
  the `## Conditional Loading` format in the project template and must describe the area→doc map
  instead. §1 of `review.md` already runs `cortex-load-requirements --feature {feature}` and records
  the printed path list for the reviewer prompt; the marker check folds into that same step. The marker
  contract is fixed by the spec and does not depend on Task 2 landing first:
  `^COVERAGE:(loaded|doc-missing|unmapped|no-area)$` on stderr. Wiring a consumer is what discharges
  the Deletion-bias presumption (`cortex/requirements/project.md:23`) against the new marker — without
  it the marker is pre-qualified for removal on arrival. **Size-pin trap**: `skills/build/references/`
  measures **57175 bytes against a pin of 57175 — zero headroom**, so any net growth fails
  `just ratchet-refs`. The removed sentence is the budget; if the edit still grows the directory, add an
  annotated `# raised:` line to `size-pin.txt` in the existing format (reason, `lifecycle-id=472`,
  `date=`) rather than trimming unrelated prose. Sequence per the ratchet/mirror rule:
  `just ratchet-refs` → `just build-plugin` → `just ratchet-refs`; `build-plugin` does not carry
  `size-pin.txt`, so `plugins/cortex-core/skills/build/references/size-pin.txt` is the one mirror path
  to stage by hand — every other `plugins/cortex-core/` path is rebuilt from staged blobs by the
  pre-commit hook and must not be staged manually. Per `docs/policies.md`, add no test asserting this
  prose exists, reads a certain way, or sits in a certain place.
- **Verification**: all four return 0 matches —
  `grep -c 'an index.md that never received its backlog tags' skills/build/references/review.md`,
  `grep -c 'trigger phrases must intersect real lifecycle' skills/requirements/SKILL.md`, and the same
  two greps against `plugins/cortex-core/skills/build/references/review.md` and
  `plugins/cortex-core/skills/requirements/SKILL.md`; **and** `grep -c 'COVERAGE:'` returns ≥ 1 for both
  `skills/build/references/review.md` and `plugins/cortex-core/skills/build/references/review.md`;
  **and** `python3 scripts/ratchet_refs.py` prints "all directories within their pins".
- **Status**: [x] done (5aca8df8 2026-08-07T18:05:09-04:00)

### Task 6: One-shot backfill verb for existing indexes
- **Files**: `cortex_command/lifecycle/backfill_index_areas.py` (new), `pyproject.toml`,
  `tests/test_backfill_index_areas.py` (new)
- **What**: Adds an idempotent sweep that populates `areas:` on every existing **linked**
  `cortex/lifecycle/*/index.md` from its parent backlog item, so coverage does not wait on each of the
  190 lifecycles being re-entered. Satisfies spec Requirement 4.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: No sweep/migration verb precedent exists in the repo — this is a new shape. Import Task
  1's frontmatter `areas:` upsert seam from `create_index.py` rather than re-implementing it, so the
  written bytes match what `create_index` produces; that shared seam is why this task adds a file
  instead of editing `create_index.py` a second time. Resolve each index's parent item the way
  `_repair_unlinked_index` does — `root / "cortex" / "backlog" / <basename>` via `_parse_frontmatter`
  from `cortex_command.backlog.resolve_item`, reading `fm.get("areas")`. Skip unlinked Shape-B indexes
  (`parent_backlog_id: null`, 33 of 190) — they have no parent to read and must not gain an `areas:`
  field. Skip an index whose item is absent or declares no `areas:`. Preserve `created`, `artifacts`,
  and body bytes; bound every edit to the leading frontmatter block. Idempotence is the load-bearing
  property: a second run must be a byte-level no-op, so write only when the rendered `areas:` line
  differs. Emit a compact-JSON count summary on stdout in the `{"signal": ..., ...}` style
  `create_index` uses. Register the console script in `pyproject.toml` alongside the existing
  `cortex-lifecycle-*` entries (`:82-83`); a `bin/` dual-channel wrapper is **not** needed — no skill
  invokes this, it is operator-run once. Use `_resolve_user_project_root` for the write root, as every
  sibling verb does.
- **Verification**: `uv run pytest tests/test_backfill_index_areas.py -q` passes, including cases for:
  a linked index gaining `areas:` from its item; a second run producing byte-identical output; an
  unlinked Shape-B index left without an `areas:` field; and an index whose item declares no `areas:`
  left untouched.
- **Status**: [x] done (0d26e1a4 2026-08-07T18:22:40-04:00)

### Task 7: Run the backfill on the live tree and prove the coverage floor
- **Files**: `cortex/lifecycle/*/index.md`
- **What**: Executes the Task 6 verb once across the live tree and measures the resulting coverage
  through the shipped loader, which is the acceptance evidence for spec Requirement 8.
- **Depends on**: [2, 6]
- **Complexity**: simple
- **Context**: This is a data migration, not a code change — the only edits are `areas:` lines on
  existing index files. Population is the 190 `cortex/lifecycle/*/index.md` files (200 directories, 10
  without an index); `cortex/lifecycle/archive/` is **not** in scope. The measurement must run through
  `resolve()` on the live tree, not against backlog items directly — the 41 figure in the spec was
  computed from backlog-item `areas:` and is the ceiling this backfill targets, not a guarantee. An
  independent pre-check reproduced 41 by that direct route, with the residue landing as `doc-missing`
  44 (all `cortex/requirements/lifecycle.md`, which #469 owns), `unmapped` 61 (`skills` 45 dominating),
  `no-area` 44 — so a live result materially below 41 means the index-copy path lost areas the items
  carry, and is a bug in Task 1 or 6 rather than a reason to lower the bar. Commit the index churn as
  its own commit; do not fold it into a code commit.
- **Verification**: from the repo root —
  ```
  uv run python -c "
  import pathlib
  from cortex_command.lifecycle.load_requirements_cli import resolve
  root = pathlib.Path('.').resolve()
  skip = {'cortex/requirements/project.md', 'cortex/requirements/glossary.md'}
  n = sum(
      any(
          l.startswith('cortex/requirements/')
          and l not in skip
          and not l.endswith(' (skipped: file absent)')
          for l in resolve(root, p.parent.name)[0]
      )
      for p in sorted(root.glob('cortex/lifecycle/*/index.md'))
  )
  print('covered:', n)
  assert n >= 40, n
  "
  ```
  prints `covered: <n>` and exits 0. Measured at HEAD: prints `covered: 17` and exits 1. The glob is the
  190 live indexes only — `cortex/lifecycle/archive/` sits a level deeper and does not match. `uv run
  python` is required: a `cortex-*` binary on PATH runs the released wheel, not the working tree, so it
  cannot see this change. `resolve(...)[0]` indexes the line list positionally rather than unpacking, so
  it stays correct after Task 2 adds a coverage value to the return. **And**: a second backfill run
  leaves `git diff --stat -- cortex/lifecycle` empty.
- **Status**: [x] done (3db19174 2026-08-07T18:25:31-04:00)

## Risks

- **The synonym map is a hand-maintained list.** ADR-0037 accepts this: exact-key matching means a new
  area silently reports `unmapped` until someone adds a row. The alternative — substring reach — is what
  produces the `pipe` → `pipeline.md` false positive. Worth re-surfacing because the recurring cost is
  real and lands on whoever adds the next area.
- **`unmapped` will be the most common non-`loaded` state** (61 of 190, `skills` alone 45), and no doc
  is planned for those areas. If its one terse line reads as a defect rather than an expected state,
  operators learn to ignore the whole marker — the exact failure this ticket exists to fix. Task 2's
  wording carries that weight.
- **Requirement 8's floor is measured through a different path than the number that set it.** The 41
  ceiling comes from backlog items; the acceptance reads the index copies. Any gap between them is a
  Task 1/6 defect, and Task 7 is where it surfaces — late.
- **A separate backfill verb is a permanent surface for a one-shot job.** The spec chose a verb over an
  ad-hoc script so it is testable and idempotent; it will nonetheless outlive its migration and read as
  dead code to a future audit. Scoped as accepted, flagged here rather than re-litigated.
- **`cortex/requirements/lifecycle.md` stays absent**, so 44 lifecycles land in `doc-missing` — the
  loudest tier — from day one. That is #469's work, not a regression, but the noise is real until it
  lands.

## Acceptance

Running `cortex-load-requirements --feature <slug>` across all 190 live `cortex/lifecycle/*/index.md`
yields ≥ 40 lifecycles loading at least one area doc present on disk (17 at HEAD), every run emits
exactly one `^COVERAGE:(loaded|doc-missing|unmapped|no-area)$` line on stderr with stdout unchanged
from HEAD's paths-only contract, and `just test` is green with the reference-size ratchet within pins.
