# Specification: requirements-loader-matches-index-tags-against

## Problem Statement

`cortex-load-requirements` selects area requirements docs by matching a lifecycle's `index.md` `tags:` as
case-folded **substrings** against free-text trigger phrases in `project.md`'s `## Conditional Loading`.
Measured across all 190 lifecycle indexes: only **17 (8.9%)** load a real area doc; 135 print
`no area docs matched`, and 35 more "match" a path that can never exist — and because a non-empty match
suppresses the fallback note, those 35 report nothing at all. The Review phase's requirements-drift check is
the mechanism that catches an implementation contradicting its area requirements; at a 91% miss rate it is
mostly not running, and its silence is indistinguishable from a clean result. The fix is not invented:
`project.md`'s trigger lists are already synonym sets (`pipeline/overnight runner/conflict resolution/deferral`),
and mechanically splitting them on `/` and kebab-normalizing — with no invention — reproduces an area→doc
map that lifts coverage to **41 (21.6%)**; the vocabulary the repo needs already exists, trapped in free text
that only substring-matches. Everyone refining or building a feature benefits: the governing area doc loads
without the orchestrator knowing to intervene.

## Phases

- **Phase 1: Index carries areas** — `index.md` gains an `areas:` field, written at creation, refreshed on re-entry, and backfilled once across existing indexes.
- **Phase 2: Map-based selection** — `## Conditional Loading` becomes an explicit area→doc map; the loader does exact-key lookup and reports coverage in tiers, both human-readable and machine-readable.
- **Phase 3: Retire the stale prose** — update the docs and scaffolds that describe the replaced mechanism, and wire the Review phase to consume the new coverage marker.

## Requirements

1. **`index.md` carries an `areas:` frontmatter field.** `create_index` writes the parent backlog item's
   `areas:` into the index alongside the existing `tags:`. Acceptance: creating an index with
   `--backlog-file` pointing at an item whose frontmatter has `areas: ['pipeline']` produces an index whose
   `areas:` round-trips as `['pipeline']` through the same frontmatter reader the loader uses. Grounding:
   `cortex_command/lifecycle/create_index.py:221-270`, `_render` at `:115-140`. **Phase**: Index carries
   areas. **Priority**: must-have.

2. **Re-entry refreshes a stale `areas:`.** `cortex-lifecycle-enter --backlog-file <f>` updates an
   **already-linked** index's `areas:` to match the backlog item's current value. This is a new arm:
   `_repair_unlinked_index` today fires only when `parent_backlog_uuid`/`parent_backlog_id`/`tags` all
   byte-match the Shape-B defaults, so every linked index is skipped. Acceptance: given a linked index with
   `areas: ['backlog']` and a backlog item since changed to `areas: ['pipeline']`, running the verb leaves
   the index at `areas: ['pipeline']`; `created`, `artifacts`, and body bytes are unchanged. Grounding:
   `cortex_command/lifecycle/create_index.py:166-218`, `cortex_command/lifecycle/enter.py:321`.
   **Phase**: Index carries areas. **Priority**: must-have.

3. **Refresh is idempotent and does not clobber divergence blindly.** Running the refresh twice produces a
   byte-identical file the second time. Acceptance: run the Requirement-2 command twice; `git diff` is empty
   after the second run. **Phase**: Index carries areas. **Priority**: must-have.

4. **Existing indexes are backfilled with `areas:` in a one-shot pass.** Requirement 2's refresh-on-`enter`
   only touches lifecycles that get re-entered. Measured, only 4 of the 190 lifecycle directories under
   `cortex/lifecycle/` record a terminal event in `events.log` — all four `lifecycle_cancelled`, and **none
   records `lifecycle_complete` at all** (completed lifecycles are moved to `cortex/lifecycle/archive/`,
   which separately holds 166 entries), so the 190 live directories are
   overwhelmingly not-yet-completed lifecycles — there is no basis for assuming they get re-entered before
   Requirement 8's coverage measurement runs. A one-shot backfill verb populates `areas:` on every existing
   **linked** index from its parent backlog item's `areas:` field, using the same read path as Requirement 2;
   it is idempotent (a second run is a no-op) and skips unlinked Shape-B indexes (`parent_backlog_id: null`),
   which have no parent to read. Acceptance: running the backfill once across `cortex/lifecycle/*/index.md`
   populates `areas:` on every linked index whose backlog item declares one; running it a second time
   produces an empty `git diff`; no unlinked Shape-B index gains an `areas:` field. Grounding:
   `cortex_command/lifecycle/create_index.py:166-218` (existing repair/read path), Requirement 2. **Phase**:
   Index carries areas. **Priority**: must-have.

5. **`## Conditional Loading` declares an explicit area→doc map.** Each row maps one or more area **keys** to
   exactly one doc path, many-to-one, with the path as a bare token carrying no trailing free text.
   Acceptance: `_parse_conditional_loading` (or its successor) returns a path for every row that is a bare
   repo-relative `.md` path — no row's path contains a space. This fails at HEAD, where the `lifecycle` row
   yields a 180-character path containing its parenthetical. Grounding: `cortex/requirements/project.md:99-107`,
   `cortex_command/lifecycle/load_requirements_cli.py:169-184`. **Phase**: Map-based selection. **Priority**:
   must-have.

6. **The map preserves the existing synonym sets.** Every synonym currently reachable in a trigger list
   becomes a key. Acceptance: the derived key set is a superset of
   `{pipeline, overnight-runner, conflict-resolution, deferral, statusline, dashboard, notifications,
   remote-access, tmux, mosh, tailscale, agent-spawning, subagents, multi-agent, parallel-dispatch,
   worktrees, model-selection, backlog, ticketing, issue-tracker, backlog-backend, training, workshop,
   presentation, scene-deck}`, **plus** the bare key `lifecycle` (absent today — the trigger normalizes to
   `lifecycle-state-machine`, which is why 44 tickets declaring `areas: ['lifecycle']` miss).
   **Phase**: Map-based selection. **Priority**: must-have.

7. **Selection is exact-key lookup on `areas:`, not substring matching on `tags:`.** An area matches a row
   only when its kebab-normalized value equals a declared key. Acceptance: a feature whose index declares
   the area `pipe` loads no area doc; a feature declaring `overnight-runner` loads
   `cortex/requirements/pipeline.md`. Both traps are confirmed live at HEAD against the current selector:
   `tags: [pipe]` → `['cortex/requirements/pipeline.md']` (false positive on accidental containment),
   `tags: [overnight-runner]` → `(none)` while `tags: [overnight runner]` → `['cortex/requirements/pipeline.md']`
   (false negative on hyphenation).
   **Phase**: Map-based selection. **Priority**: must-have.

8. **Measured coverage rises on the live tree, after backfill.** Acceptance: running the verb across every
   `cortex/lifecycle/*/index.md`, after Requirement 4's backfill has populated existing indexes and
   Requirement 1 covers newly created ones, yields ≥ 40 lifecycles loading at least one area doc that
   exists on disk, versus 17 at HEAD. The 41 figure computed in research (Problem Statement) — read from
   backlog-item `areas:` directly, not through the shipped index-copy path — is the ceiling this backfill
   targets, not a guaranteed outcome: it remains the number to beat. **Phase**: Map-based selection.
   **Priority**: must-have.

9. **Coverage is reported on stderr as both human-readable detail and a structured, machine-parseable
   marker, on the verb's existing single invocation.** No new flag: every run of
   `cortex-load-requirements --feature {f}` emits one stderr line matching
   `^COVERAGE:(loaded|doc-missing|unmapped|no-area)$` alongside the existing human-readable detail,
   distinguishing four states: (a) a declared area mapped to a doc **absent from disk** — `doc-missing`,
   actionable, names the area and the expected path; (b) a declared area with **no map entry** —
   `unmapped`, expected for areas that have no doc by design, at most one terse line; (c) **no area
   declared at all** — `no-area`, preserving the existing `NO_INDEX_NOTE_TEMPLATE` / `FALLBACK_NOTE_TEMPLATE`
   UNVERIFIED-vs-empty split shipped by #427, verbatim in meaning; (d) at least one declared area loads a
   real doc — `loaded`. Stdout is unchanged — paths only, one per line — so #333 needs no carve-out; the
   marker lives entirely on stderr. This collapses an earlier two-piece design (three stderr tiers plus a
   separate flag-gated stdout marker) into one signal, because that design had three problems: three of its
   four marker states duplicated the stderr tiers; a caller needing both the path list and coverage status
   had to invoke the verb twice — an extra turn, which `cortex/requirements/project.md:21` Token economy
   counts directly; and a stdout marker would have needed a carve-out from #333, which this design avoids
   by never touching stdout. A structured marker (versus louder prose alone) is still needed because a
   louder stderr string alone is the same class of fix already tried and missed:
   `skills/build/references/review.md:9` already frames the fallback note as "a warning, not a routine
   fallback," and it was still missed on #465 — CLAUDE.md's guidance to prefer structural separation over
   prose-only enforcement for sequential gates applies directly, since occasional deviation here is not
   cheap (a missed drift check is silent by construction). Acceptance: four fixture runs, each via the
   verb's default invocation (`cortex-load-requirements --feature <f>`, no flags), each produce stderr
   containing exactly one line matching `^COVERAGE:(loaded|doc-missing|unmapped|no-area)$` with the state
   expected for that fixture; the `unmapped` line is at most one line; and stdout in all four cases is
   byte-identical to HEAD's behavior (paths only, one per line). Grounding:
   `cortex_command/lifecycle/load_requirements_cli.py:61-73, 248-264, 301-306`,
   `skills/build/references/review.md:9`. **Phase**: Map-based selection. **Priority**: must-have.

10. **The stderr text stops claiming `project.md` only.** `glossary.md` is `## Global Context` and loads
    unconditionally, including on the fallback path. Acceptance: no stderr string emitted by the verb
    contains the substring `loaded project.md only`. **Phase**: Map-based selection. **Priority**: must-have.

11. **Docs describing the replaced mechanism are corrected in the same phase.**
    `skills/build/references/review.md:9` states the cause as "an index.md that never received its backlog
    tags, repaired by re-running `cortex-lifecycle-enter`"; `skills/requirements/SKILL.md:63` states
    "trigger phrases must intersect real lifecycle `index.md` `tags:` words". Both are false after Phase 2.
    Acceptance — pure absence, four checks, none requiring judgment: (1) `skills/build/references/review.md`
    does not contain the literal substring `an index.md that never received its backlog tags`;
    (2) `skills/requirements/SKILL.md` does not contain the literal substring
    `trigger phrases must intersect real lifecycle`; (3) `plugins/cortex-core/skills/build/references/review.md`
    does not contain the substring from (1); (4) `plugins/cortex-core/skills/requirements/SKILL.md` does not
    contain the substring from (2). **Phase**: Retire the stale prose. **Priority**: must-have.

12. **`review.md` §1 consumes the coverage marker.** `skills/build/references/review.md` §1 ("Gather
    inputs") already runs `cortex-load-requirements --feature {feature}` and records the printed path list
    for the reviewer prompt, and it is already being edited in Requirement 11 to remove its false claim
    about the cause of a miss. In that same edit, §1 also checks the `COVERAGE:` marker Requirement 9 emits
    on stderr and surfaces a non-`loaded` result to the reviewer, alongside the existing path list. This
    closes the gap `cortex/requirements/project.md:23` (Deletion bias) opens for any new surface: "A surface
    with no consumer that fails on its removal carries the presumption of removal; discharge requires either
    a consumer that turns a build or gate red when the surface is removed — not a report-only or
    manually-invoked script — or a filed bug recording observed failure, not a hypothetical." A coverage
    marker with a deferred consumer would be pre-qualified for deletion on arrival; this requirement is what
    discharges that presumption. Acceptance — a bare existence assertion on a machine token whose omission
    fails silently, consistent with `docs/policies.md`'s permitted absence/existence checks (no presence,
    wording, ordering, or occurrence-count assertions beyond this token): `grep -c 'COVERAGE:'
    skills/build/references/review.md` returns ≥ 1, and `grep -c 'COVERAGE:'
    plugins/cortex-core/skills/build/references/review.md` returns ≥ 1. **Phase**: Retire the stale prose.
    **Priority**: must-have.

13. **`glossary.md` defines "area".** It is Global Context, has zero occurrences of the word today, and is
    the term the whole map turns on. Acceptance: `grep -c '\*\*area\*\*' cortex/requirements/glossary.md`
    returns ≥ 1, in the file's existing one-line format. **Phase**: Retire the stale prose. **Priority**:
    nice-to-have — the mechanism functions and is fully specified (Requirements 1-12) without this entry;
    it improves discoverability for a future reader but blocks nothing.

14. **The consumer-repo scaffold teaches a parseable separator.**
    `cortex_command/init/templates/cortex/requirements/project.md:46` shows
    `Working on <area> -> requirements/<area>.md` using ASCII `->`, which the U+2192-only parser cannot
    read — every consumer repo following the scaffold's own example gets zero area docs. Acceptance: running
    (from the repo root)
    ```
    python3 -c "from cortex_command.lifecycle.load_requirements_cli import _parse_conditional_loading; from pathlib import Path; print(_parse_conditional_loading(Path('cortex_command/init/templates/cortex/requirements/project.md').read_text()))"
    ```
    prints a non-empty list — the template's own example line parses into at least one `(trigger, path)`
    pair. Verified at HEAD: this prints `[]`. Grounding: `cortex_command/lifecycle/load_requirements_cli.py:169-184`,
    `cortex_command/init/templates/cortex/requirements/project.md:46`. **Phase**: Retire the stale prose.
    **Priority**: nice-to-have — affects only consumer repos following the scaffold, not this repo's own
    coverage number; adjacent to the ticket's core defect but not required to close it (research's Open
    Question 6).

## Non-Requirements

- **Writing `cortex/requirements/lifecycle.md`.** Owned by #469, which also holds the open question of
  whether `escalation` and `review` route there. This spec adds the `lifecycle` map key; #469 supplies the
  doc. Until it lands, `areas: ['lifecycle']` correctly reports tier (a).
- **A validator or allowed-value list for backlog `areas:`.** The map is the vocabulary; an unknown area is
  reported, not rejected. No change to `create_item.py --areas`.
- **Normalizing the 24 existing `areas:` values across 466 backlog items.**
- **Writing area docs for `skills` (133 items), `hooks`, `tests`, `docs`, `install`.** Their absence is the
  dominant residue and is not a loader defect.
- **Removing `index.md` `tags:`.** Research confirms nothing else reads it, but removal is a 190-file schema
  change with no benefit to this outcome. It becomes inert.
- **Making unresolved coverage block a phase.** Reporting stays non-blocking.

## Edge Cases

- **Context B / ad-hoc lifecycle (no backlog file, no index).** Areas reader returns `[]`; falls through to
  the existing no-index note. Must not error. Verified today at `refine.py:695, 771` and `enter.py:321`.
- **Unlinked Shape-B index** (33 of 190, `parent_backlog_id: null`). No item to read; tier (c).
- **Backlog item with no `areas:` field** (112 of 466). Tier (c), not tier (b).
- **Area mapped to a doc absent from disk.** Keeps the existing `(skipped: file absent)` suffix on stdout
  **and** raises tier (a) on stderr — the two are complementary, not alternatives.
- **Multiple areas mapping to the same doc.** Emitted once; existing dedup-by-resolved-path holds.
- **An area matching a `## Global Context` doc.** Global Context placement wins, per existing dedup rules.
- **`project.md` absent, or present with no `## Conditional Loading` section.** Verified today: emits
  `project.md (skipped: file absent)` / `project.md` respectively, plus the note. Neither errors. Must stay so.
- **The heading `## Conditional Loading` is renamed.** `validate_requirements_doc_cli.py:70-71` asserts the
  heading exists. The heading name must be preserved even though the body format changes.
- **Hand-edited index `areas:` diverging from the backlog item.** Requirement 2 overwrites it on re-entry;
  the index is a cache, not a source of truth. Called out because `_repair_unlinked_index`'s existing
  carve-out establishes the opposite convention for `tags:`.

## Changes to Existing Behavior

- **MODIFIED** — `load_requirements_cli.py`: selection key moves `tags:` → `areas:`; matching moves
  substring → exact key; `_parse_conditional_loading` stops absorbing trailing free text into the path;
  stderr gains a four-state, machine-parseable `COVERAGE:` marker alongside the existing human-readable
  tiers, emitted on the verb's existing default invocation — no new flag; stdout is unchanged.
- **MODIFIED** — `create_index.py`: writes `areas:`; the repair arm extends to already-linked indexes for
  the `areas:` field only; a new one-shot backfill path populates `areas:` on existing linked indexes.
- **MODIFIED** — `cortex/requirements/project.md` `## Conditional Loading` body format. Heading preserved.
- **MODIFIED** — `skills/build/references/review.md`, `skills/requirements/SKILL.md`, and their
  `plugins/cortex-core/` mirrors.
- **MODIFIED** — `cortex_command/init/templates/cortex/requirements/project.md` separator.
- **ADDED** — `areas:` frontmatter field on `cortex/lifecycle/*/index.md`; a one-shot backfill verb for
  existing indexes; an `area` glossary entry; a `COVERAGE:` marker on `cortex-load-requirements`'s stderr.
- **REMOVED** — no behavior removed. `index.md` `tags:` is left in place, inert.
- **Tests rewritten** (semantics change): `test_feature_matching_tags_loads_area_docs:99`,
  `test_empty_string_tag_loads_only_real_match:160`, `test_trigger_only_match_not_path:176`,
  `test_whole_tag_not_split:192`, `test_pure_substring_axis:204`, `test_dedup_multi_tag_one_phrase:310`,
  `test_unmatched_tag_dropped:321`. **Tests tracking the format change**:
  `test_live_project_md_format_invariants:335`, `test_live_conditional_loading_parses_compound_triggers:344`
  (explicitly pins the retired compound-slash format), `test_live_project_md_selection_oracle:360`.

## Technical Constraints

- **ADR-0019** — a `cortex-*` skill-helper verb may act on caller-passed values as a structural guard but
  must not resolve the backend itself. This is why the loader reads only `index.md` and never a backlog
  file: a local `cortex/backlog/NNN-*.md` exists only on the `cortex-backlog` backend, and a stale one left
  after a migration is the silent-corruption footgun that ADR motivates.
- **Ordering constraint** — `cortex-lifecycle-spec-approve` writes `areas:` to the backlog item at refine
  Step 4 (`spec_approve.py:263-268, 344-347`), **after** `create_index` runs at Step 1. An index-time copy
  alone is therefore stale by construction for any ticket whose areas refine infers or corrects. This
  lifecycle is a live instance: its index carries `tags: [requirements-loading]` and no `areas:`, while the
  item carries `areas: ['lifecycle', 'requirements']`. Requirement 2 exists to close this.
- **#333** — the verb prints paths only, never file contents, on stdout. Preserved: Requirement 9's
  `COVERAGE:` marker lives entirely on stderr, emitted on the verb's existing default invocation with no new
  flag — stdout's contract is untouched for every existing caller, so #333 needs no carve-out. An earlier
  design considered a flag-gated stdout marker instead; it was rejected in favor of the stderr-only signal
  precisely because it would have required renegotiating #333's default-mode scope for callers that never
  asked for coverage data.
- **A surface with no consumer is presumed removable** — `cortex/requirements/project.md:23` (Deletion
  bias): "A surface with no consumer that fails on its removal carries the presumption of removal; discharge
  requires either a consumer that turns a build or gate red when the surface is removed — not a report-only
  or manually-invoked script — or a filed bug recording observed failure, not a hypothetical." Requirement 9
  adds a coverage signal; without Requirement 12 wiring `review.md` §1 to read it, that signal would be
  pre-qualified for deletion the moment anyone applies this clause to it.
- **#427** — the UNVERIFIED-vs-empty note split must survive as tier (c).
- **`docs/policies.md:27-41`** — behavior is pinned by CLI-verb output tests only. No presence, wording,
  ordering, proximity, or occurrence-count assertions on skill or reference prose. Requirement 11's
  acceptance is therefore a pure **absence** assertion on named literal strings in named files, which policy
  explicitly permits; Requirement 12's acceptance is the sibling **existence-assertion-on-a-machine-token**
  case the same policy permits.
- **CLAUDE.md** — `load_requirements_cli.py`, `skills/`, and `bin/cortex-*` are lifecycle-gated; the
  pre-commit hook rebuilds `plugins/cortex-core/` mirrors from staged blobs, so the commit will contain
  mirror paths not explicitly named.
- **`resolve_item.py:310-336`** does not search `cortex/backlog/archive/` while four sibling verbs do. This
  spec avoids the gap by never resolving a backlog item from the loader; it is noted so a future change
  toward live resolution does not walk into it.
- **Open Question 2's answer is directional, not proof.** Comparing `review.md`'s recorded drift findings
  (matched on the substring "drift") across lifecycles: those that loaded a real area doc recorded a finding
  in 4 of 14 cases (28.6%); those that did not, 33 of 146 (22.6%). This is weak evidence — n=14, detection is
  a single-substring match, and no causal mechanism is established — but it is directionally supportive of
  the ticket's premise and is not contradicted by any other measurement in research.md. It does not, on its
  own, justify the change; the change is justified on the drift check being ~91% dark (Problem Statement),
  which is measured, not inferred.

## Open Decisions

None. The source-of-truth fork research left open — live resolution vs index copy — is resolved in favor of
**neither**: the index remains the loader's only input (satisfying ADR-0019), and its staleness is closed at
the write side by Requirement 2 rather than at the read side. Both original options were rejected on
constraints research surfaced: live resolution gives a backend-blind verb backend awareness, and a bare
index-time copy is stale by construction against `spec-approve`'s write ordering.

## Proposed ADR

### Proposed ADR: 0037-area-to-doc-map-as-the-requirements-vocabulary

**Context.** Requirements selection has matched lifecycle `index.md` `tags:` as case-folded substrings
against free-text trigger phrases since #333 replaced a hand-executed prose algorithm. Measured across 190
lifecycles, 8.9% load a real area doc. Two independent causes: the selected field (`tags:`, an epic/topic
slug vocabulary) is not the field carrying the area concept (`areas:`), and substring matching both
false-negatives on hyphenation (`'overnight-runner' in 'pipeline/overnight runner/…'` is False) and
false-positives on accidental containment (`pipe` selects `pipeline.md`).

**Decision.** `## Conditional Loading` becomes an explicit many-to-one area→doc map whose keys are the
declared area vocabulary, matched by exact kebab-normalized key lookup against the backlog item's `areas:`,
propagated to the loader through `index.md`. The map *is* the vocabulary — there is no separate validator
over `areas:`, and an unknown area is reported rather than rejected.

**Trade-off.** A strict map keyed on area name alone is a **regression** — measured at 14 lifecycles (7.4%)
versus 17 (8.9%) today. The gain depends entirely on preserving many-to-one synonyms
(`overnight-runner` → `pipeline.md` alone accounts for 26 of 41). So this trades substring matching's
accidental reach for an explicit synonym list that must be maintained by hand as areas are added — a real
recurring cost, accepted because the alternative silently mis-selects and because the synonym sets already
exist in `project.md`'s trigger text and are recovered mechanically rather than invented. Rejected: keying
the loader off the backlog item directly (ADR-0019 backend-awareness boundary); keying off a normalized
substring match (retains accidental containment); a validated closed vocabulary over `areas:` (schema change
across 466 items whose payoff depends on area docs that do not yet exist).
