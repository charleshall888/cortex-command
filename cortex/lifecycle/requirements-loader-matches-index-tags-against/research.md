# Research: Replace `cortex-load-requirements`' tag-substring selection with an explicit area→doc map

Sourced from the backlog item's `areas:`, so a feature with a governing area doc always loads it, and a
declared area that maps to no doc reports loudly instead of silently succeeding.

Ticket: [[472-requirements-loader-matches-index-tags-against-area-triggers-so-72-of-lifecycles-load-projectmd-only]]

## Baseline measurement

All numbers re-derived against live code (`resolve()` called directly), not inferred. Population is the
190 `cortex/lifecycle/*/index.md` files present on 2026-08-07.

| Outcome today | Count | % |
|---|---|---|
| `no area docs matched` note → project.md + glossary.md only | 135 | 71.1% |
| "matched" a malformed path, **no note printed** | 35 | 18.4% |
| Loads ≥1 real area doc | **17** | **8.9%** |

The ticket's headline (72% / 134 of 186) reproduces, but it measures the *note*, not the outcome. Two
corrections matter for scoping:

- **"loads `project.md` only" is inaccurate.** `glossary.md` is `## Global Context` and loads
  unconditionally, including on the fallback path — a documented correction in the verb's own docstring
  (`load_requirements_cli.py:38-41`). The stderr string says otherwise; the string is wrong, not the code.
- **Real coverage is 8.9%, not 28%.** The 35 "matched" cases are worse than the 135: they suppress the
  fallback note (`resolve()` only sets it when `matched` is empty, `load_requirements_cli.py:248-264`), so
  they look covered and are not.

### The malformed-path defect

`_parse_conditional_loading` splits each bullet on the first `→` and takes the **entire remainder** as the
path (`load_requirements_cli.py:179-183`). The `lifecycle` row in `project.md:107` carries a trailing
parenthetical, so the emitted path is:

```
cortex/requirements/lifecycle.md (NOT YET WRITTEN — `areas: ['lifecycle']` tickets currently load
project.md only; statusline/dashboard narration ...) (skipped: file absent)
```

This falsifies the ticket's Edges claim that the arm "is expected to match nothing and must not be counted
as a failure". `'lifecycle'` **is** a substring of the trigger, the arm matches 43 lifecycles, and it emits
a path that cannot ever exist. An Edges bullet pointing a builder away from a live defect in the exact
function named as Integration point #1 is the most damaging error in the ticket.

## Codebase

### Where `areas:` becomes readable — the central fork

Two designs, both viable, with a decisive ordering constraint neither the ticket nor the codebase angle
identified:

**(i) Loader resolves slug → backlog item live** (via `index.md`'s `parent_backlog_id`/`parent_backlog_uuid`).
- 157 of 190 indexes (82.6%) carry a usable parent link; the other 33 are unlinked Shape B.
- `resolve_item.py:310-336` globs only `cortex/backlog/[0-9]*-*.md` and does **not** search
  `cortex/backlog/archive/`, while `create_item.py:86-91`, `update_item.py:287`, `generate_index.py:143-150`
  and `ready.py:265-267` all do. This repo's `archive/` is empty today, so the gap is latent here and live
  in any repo that archives.
- **Constraint:** a local `cortex/backlog/NNN-*.md` only exists on the `cortex-backlog` backend. Reading it
  unconditionally gives a backend-blind verb backend awareness, and a stale local file left after a backend
  migration is the exact silent-corruption footgun ADR-0019 was written about
  (`cortex/adr/0019-*.md`, Context §3). ADR-0019 permits a *caller-passed* `--backend` structural guard but
  forbids the verb resolving the backend itself.

**(ii) `create_index.py` copies `areas:` into the index at creation**, loader keeps reading the index only.
- Nearly free: `create_index()` and `_repair_unlinked_index()` already call `_parse_frontmatter(backlog_path)`
  and read `fm.get("tags")` (`create_index.py:205, 243`). Adding `fm.get("areas")` is a one-line change at
  both existing call sites (`enter.py:321`, `refine.py:771-775`).
- Keeps the loader backend-blind — the caller that has `--backlog-file` is already backend-aware.
- **Decisive defect: stale by construction on the normal path.** `cortex-lifecycle-spec-approve` writes
  `areas:` to the *backlog item* at refine Step 4 (`spec_approve.py:263-268, 344-347`), long after
  `create_index` ran at Step 1. Refine is *instructed* to infer areas ("Infer areas by naming the primary
  subsystem modified", refine SKILL.md Step 4). So for every ticket whose areas refine sets or corrects, an
  index-time copy captures the pre-refine value. This lifecycle is a live instance: its `index.md` carries
  `tags: [requirements-loading]` and no `areas:` at all, while the backlog item carries
  `areas: ['lifecycle', 'requirements']`.

Design (ii) therefore requires a refresh at spec-approve (or on every `enter`) to be correct; design (i) is
correct by construction but must answer ADR-0019 and the `archive/` gap.

### Context B degradation

`refine.py:695` sets `context = "A" if item is not None else "B"`, and `refine.py:771` only calls
`create_index` when `context == "A"`. `enter.py:321` always calls it, rendering Shape B
(`parent_backlog_uuid: null`, `parent_backlog_id: null`, `tags: []`) when `--backlog-file` is empty. So a
Context B lifecycle has either no index or an unlinked one. Under both designs the areas reader returns `[]`
and `resolve()` falls through to the existing `NO_INDEX_NOTE_TEMPLATE` / `FALLBACK_NOTE_TEMPLATE` split —
today's behavior, no error. **Both designs degrade correctly.**

### Consumers of `index.md` `tags:`

`load_requirements_cli.py` is the only code consumer. `skills/requirements/SKILL.md:63` (and its mirror)
documents the current mechanism in prose and goes stale. `skills/discovery/references/decompose.md:45`
concerns backlog-item tags, not index tags. **Once selection stops using it, `index.md` `tags:` is dead.**

### `## Conditional Loading` format change

Nothing else parses the section body. `validate_requirements_doc_cli.py:70-71` asserts only that the
*heading* exists; `list_requirements_cli.py:73` counts bullets generically. **The heading name must be
preserved; the body format is free.** No other live-tree reader exists (checked hooks, dashboard, overnight
runner, `cortex init`, plugin mirrors).

`bin/cortex-load-requirements` has a plugin mirror at `plugins/cortex-core/bin/` (currently byte-identical),
so the dual-source rebuild applies.

**Consumer-repo defect found:** `cortex_command/init/templates/cortex/requirements/project.md:42-46`
scaffolds the section with an example using an ASCII `->`, which the U+2192-only parser
(`load_requirements_cli.py:60`) cannot parse. Any consumer repo following the scaffold's own example gets
zero area docs.

### Degenerate inputs

Verified by running `resolve()` against a synthetic tree: absent `project.md` → emits
`project.md (skipped: file absent)` plus the no-index note; `project.md` with no `## Conditional Loading`
section → emits `project.md` alone. Neither errors.

### Backfill

No sweep/migration verb pattern exists. `_repair_unlinked_index` (`create_index.py:166-218`) fires only when
`parent_backlog_uuid`/`parent_backlog_id`/`tags` **all** byte-match the Shape-B defaults, so all 157
already-linked indexes are excluded by design. Backfill needs a new verb or mode; it cannot reuse the repair.

Note this also corrects the ticket's Integration claim that `cortex-lifecycle-enter --backlog-file` repair
"does not cover this case" for #465. #465's backlog item has **no `tags:` field at all** — the repair had
nothing to copy and `tags: []` was correct output. The repair is not defective; the field is wrong.

### Test surface

Rewritten by a semantics change (all `tests/test_load_requirements_cli.py`):
`test_feature_matching_tags_loads_area_docs:99`, `test_empty_string_tag_loads_only_real_match:160`,
`test_trigger_only_match_not_path:176`, `test_whole_tag_not_split:192`, `test_pure_substring_axis:204`,
`test_dedup_multi_tag_one_phrase:310`, `test_unmatched_tag_dropped:321`.

Tracking a format change: `test_live_project_md_format_invariants:335`,
`test_live_conditional_loading_parses_compound_triggers:344` (explicitly pins the compound-slash format),
`test_live_project_md_selection_oracle:360`.

Untested behaviors a fix must pin (CLI-verb level only, per `docs/policies.md`):
1. A declared area with **no map entry** vs a declared area **mapped to an absent doc** — distinct signals.
   Nothing distinguishes them today.
2. Index frontmatter round-trips `areas:` through the same reader the loader uses (design ii).
3. The parser must not absorb a trailing parenthetical into the path — pin directly to the
   `lifecycle.md (NOT YET WRITTEN — ...)` shape now in `project.md:107`.
4. Any backfill verb: idempotent on re-run, reports counts, skips hand-edited indexes.

## Requirements & Constraints

- **`project.md:99-107`** `## Conditional Loading` is the section being replaced; **`:109-111`**
  `## Global Context` (currently `glossary.md` alone) must stay unconditional.
- **No numeric token budget exists.** Nearest binding statement is Token economy (`project.md:21`):
  "the levers are session length, turn count, and fan-out width" — resident context size is not named.
  #469's Edges inherit the discipline by precedent, not by rule.
- **Deletion bias / front-door evidence bar (`project.md:23`)** binds directly: this is harness machinery,
  so the Why must name measured cost. It does (see Baseline).
- **`glossary.md`** is 5 one-line entries under `## Language`, format
  `- **term**: one sentence, optional rubric pointer, optional → ADR-NNNN`. Zero occurrences of "area".
  No inclusion-criteria section exists. An "area" entry is a permanent per-lifecycle cost.
- **ADR-0019** bounds skill-helper verb judgment (see fork above). **ADR-0024** defines a narrower
  served-verb class that `cortex-load-requirements` is not in, and is silent on extending it.
  **ADRs 0008, 0025, 0026** are orthogonal. **No ADR governs `cortex-load-requirements` by name**, and none
  is contradicted. `cortex/adr/README.md:45` records that ADR *frontmatter* deliberately has no `area:`
  field — a naming collision only, not a constraint here.
- **#333's shipped constraint** survives: the verb prints paths only, never file contents.
- **#427 (complete)** shipped the `NO_INDEX_NOTE_TEMPLATE` vs `FALLBACK_NOTE_TEMPLATE` distinction
  (`load_requirements_cli.py:61-73`); it must be preserved. Sourcing from `areas:` may make the no-index
  case moot, which is a simplification, not a licence to collapse the signals.
- **`docs/policies.md:27-41`**: behavior must be pinned via CLI-verb output tests; no presence, wording,
  ordering, proximity, or occurrence-count assertions on skill or reference prose. Editing
  `skills/build/references/review.md` is in scope for the same phase — its stated cause
  ("an index.md that never received its backlog tags") goes stale.
- **CLAUDE.md**: `load_requirements_cli.py`, `skills/`, and `bin/cortex-*` are lifecycle-gated; the
  dual-source mirror rebuild will add plugin paths to the commit.
- **Scope boundary — #469** owns writing `cortex/requirements/lifecycle.md` and explicitly holds the open
  question "whether `escalation` and `review` tags route here or stay unrouted". This ticket must not
  resolve that. It is a coordination point: if the map's structure changes, #469 registers into the new
  structure.
- **Area-doc format model** (`pipeline.md`, `backlog.md`, `multi-agent.md`): `# Requirements: <area>`,
  `> Last gathered: <date>`, `**Parent doc**` back-link, then Overview / Functional Requirements /
  Non-Functional / Architectural Constraints / Dependencies / Edge Cases / Open Questions.

## Adversarial

> ⚠️ **The dispatched adversarial agent returned nothing.** It idled twice, including after a chase with the
> JSON envelope waived. The checks below were run by the orchestrator against live code. Items 2 and 5 got
> materially less scrutiny than a dedicated agent would have given them and are carried to Open Questions.

### The coverage number survives — but only with many-to-one synonyms

The codebase angle claimed the fix "does not meaningfully raise real coverage (14/157 ≈ 8.9%)". Re-derived
directly, that number is not wrong — **it measures a different design**, and the distinction is the whole
finding:

| Map design | Lifecycles loading ≥1 real area doc | vs today (17 / 8.9%) |
|---|---|---|
| **Strict** — area name must equal doc stem | 14 (7.4%) | **worse than today** |
| **Many-to-one synonyms** | **41 (21.6%)** | **2.4×** |

A strict area→doc map is a *regression*. The gain lives entirely in synonyms — `overnight-runner` →
`pipeline.md` alone accounts for 26 of the 41.

**The synonyms are not hand-picked.** Splitting `project.md`'s *existing* trigger lists on `/` and
kebab-normalizing — zero invention — reproduces 41/190 exactly. The vocabulary the repo needs is already
written down; it is trapped in free text that only substring-matches. This reframes the change: not
"replace synonym lists with exact area names", but **"keep the synonym lists, make them exact-match keys"**.

One gap the derivation exposes: the `lifecycle` trigger normalizes to `lifecycle-state-machine`, so the 44
tickets declaring `areas: ['lifecycle']` still miss. The map needs `lifecycle` as an explicit key.

Ceiling: 41 now; ~85 (45%) once #469 writes `lifecycle.md`.

### The `skills` cliff is real — loudness must be two-tiered

Under the derived map, declared-but-unmapped areas across lifecycles are `skills` 53, `hooks` 7, `tests` 5,
`docs` 3, `install` 2, `requirements` 2, `tooling` 1, `discovery` 1 — ~74 lifecycles, plus 44 with no
declaration at all. If all of those print a loud report on every refine and build, the change trades a
silent miss for recurring noise operators learn to ignore, which is the failure mode the ticket is trying to
fix. **The loud signal must distinguish:**
- declared area → **mapped doc missing from disk** — actionable, and #469 is the fix. Loud.
- declared area → **no map entry** (`skills`, `hooks`, `tests`) — expected, no doc exists by design. Terse
  or silent.
- **no area declared** — the #427 UNVERIFIED case. Keep its existing distinct note.

### Migration risk is low

No production code other than the loader reads the section body; `validate_requirements_doc_cli.py` pins
only the heading name. Three live-parse tests need updating. The plugin mirror is byte-identical and
rebuilt from staged blobs.

## Open Questions

1. **Which design owns the fork — live resolution (i) or index copy (ii)?** Not resolved by research.
   (i) is correct-by-construction but must answer ADR-0019's backend-awareness boundary and the missing
   `archive/` lookup in `resolve_item.py`. (ii) keeps the verb backend-blind but is stale by construction
   because `spec-approve` writes `areas:` after `create_index` runs, so it needs a refresh trigger. **For
   Spec to resolve** — this is the ticket's own "deciding the source of truth is the actual design work".
2. **Does loading an area doc actually improve outcomes?** *Under-researched — the adversarial agent
   failed.* The ticket's evidence is a single anecdote (#465). No counter-evidence was gathered: nobody
   checked whether lifecycles that *did* load a real area doc drifted less, or whether Review's drift check
   finds anything when it does run. The change is justified on the drift check being ~91% dark, not on a
   measured improvement when it is lit.
3. **Why would a louder note work when the existing warning framing did not?** *Under-researched.*
   `skills/build/references/review.md:9` already calls the note "a warning, not a routine fallback" and it
   was still missed on #465. A louder string is the same class of fix that already failed once. CLAUDE.md
   prefers structural separation over prose enforcement for sequential gates — the structural option
   (e.g. the reviewer prompt carrying coverage status as data rather than the orchestrator relaying a
   string) was not explored.
4. **Does `index.md` `tags:` get removed, or left inert?** Research confirms nothing else reads it. Removal
   is a schema change across 190 files; leaving it is dead weight that will re-confuse a future reader.
5. **Backfill the 190 existing indexes, or start correctness at the next `create-index`?** Only matters
   under design (ii). No sweep-verb precedent exists to follow.
6. **Is the ASCII-`->` scaffold defect in scope?**
   `cortex_command/init/templates/cortex/requirements/project.md:46` teaches consumer repos a separator the
   parser rejects. Small, adjacent, and arguably the same bug class.
