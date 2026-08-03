# Specification: triage-routes-ready-items-by-ticket

## Problem Statement

`cortex-backlog-triage` renders the board `/cortex-core:dev` prints, and its Ready block computes each row's workflow recommendation from the ticket's `type` rather than its readiness (`cortex_command/backlog/triage.py:78-84`). Because the `bug`/`chore` branch returns before `_is_refined()` is consulted, a ticket with an approved spec is still told "direct implementation" — silently orphaning a spec someone paid an interactive refine to produce. The same run's epic block marks children purely on `_is_refined()`, so one invocation gives two contradictory routings for the same ticket type (observed 2026-08-03 in wild-light: `#432`/`#433` told to implement directly while `#413`, also `type: chore`, was told to refine). Consumers feel this, not this repo — in wild-light the type-only path covers 15 of 18 ready items. Fixing it makes a row's rendered route depend on the ticket's actual state rather than on which block it happens to appear in.

## Phases

- **Phase 1: Unify the recommendation** — one shared function computes the recommendation for both blocks from readiness, and the trivial-change cheap path is delegated to the dev skill's existing rule 4.
- **Phase 2: Behavioral coverage** — establish the first real test coverage of `render()`, including a drift guard that compares the two blocks' actual output on type-sensitive fixtures.

## Requirements

1. **Readiness governs the recommendation for every type.** A ready item with a non-empty `spec:` renders `` `/cortex-core:build` `` regardless of `type`; without one it renders `` `/cortex-core:refine` ``. Acceptance: a unit test in `tests/test_triage_render.py` feeds `render()` an item with `type: "chore"`, `status: "refined"`, `spec: "cortex/lifecycle/x/spec.md"` and asserts the rendered Ready row contains `` `/cortex-core:build` `` and does not contain `direct implementation`. **Phase**: Unify the recommendation

2. **A single shared function produces the recommendation string for both blocks.** `render()`'s flat loop and `_render_epic_block` both call it; neither computes a recommendation inline. It returns a single line — no embedded newline — so it composes with `_render_epic_block`'s existing `" ".join(marks)` assembly (`triage.py:98-101`). Acceptance: (a) `grep -c "direct implementation" cortex_command/backlog/triage.py` returns `0`; (b) a test asserts the function's return value for every fixture in `tests/test_triage_render.py` contains no `\n`; (c) a test asserts `_workflow`-style inline recommendation literals appear in neither `render` nor `_render_epic_block` by checking `inspect.getsource` of each contains no `/cortex-core:` literal. **Phase**: Unify the recommendation

3. **The same (type, status, spec) triple renders byte-identically in both blocks, verified on type-sensitive fixtures.** Acceptance: a test in `tests/test_triage_render.py` parametrized over `type` in `("bug", "chore", "idea", "feature")` calls `render()` twice with the same item dict — once as a child of a ready epic, once with `epic_map={}` so it falls into `## Ready` via `triage.py:167-169` — extracts each recommendation substring by regex keyed on the item id (never recomputed from the item), and asserts the two extracted strings are byte-identical. The `bug`, `chore`, and `idea` cases are mandatory: they are the only types whose output differs between a full `by_id` record and the type-less epic-map child envelope, so a `feature`-only fixture would pass whether or not the epic block threads `by_id` correctly. **Phase**: Behavioral coverage

4. **The trivial-change cheap path is delegated to the dev skill, not rendered per row.** `skills/dev/SKILL.md` Step 3's `ok` branch gains a single control-flow clause routing a picked item back through Step 1, making rule 4's existing judgment-based trivial-change hatch reachable — it currently is not, because rule 1 already matched and consumed Step 1. No hint text is rendered on any row. Acceptance: (a) `skills/dev/SKILL.md` Step 3's `ok` bullet contains the substring `route it from Step 1`; (b) `grep -c "implement directly if trivial" cortex_command/backlog/triage.py` returns `0`; (c) `uv run pytest tests/test_dev_triage_refs_wired.py -q` passes, confirming no `_MOVED_TOKENS` string was reintroduced. **Phase**: Unify the recommendation

5. **The `idea` → `/cortex-core:discovery` branch is preserved.** Acceptance: a unit test in `tests/test_triage_render.py` asserts an item with `type: "idea"` renders `` `/cortex-core:discovery` `` in the Ready block, both with and without a `spec:` value. **Phase**: Unify the recommendation

6. **The epic footer does not contradict the per-child recommendation above it.** The footer at `triage.py:126-137` currently partitions children on `_is_refined()` alone and tells the reader to "Run `/cortex-core:refine` on each unrefined child" — which, once per-child lines route `idea` to `/cortex-core:discovery`, would give opposite advice for the same child three lines apart. `idea`-typed children (resolved via the `by_id` records already in `_render_epic_block`'s scope) are excluded from the footer's unrefined-refine bucket and from the all-refined overnight arm. Acceptance: a test in `tests/test_triage_render.py` renders an epic whose children include one unrefined `type: "idea"` child and asserts the rendered block does not contain that child's id in the "Run `/cortex-core:refine` on each unrefined child" sentence, and does not emit the `/cortex-overnight:overnight` sentence solely because the idea child was filtered out. **Phase**: Unify the recommendation

7. **`tests/test_dev_triage_refs_wired.py` stays green without weakening its assertions.** Acceptance: `uv run pytest tests/test_dev_triage_refs_wired.py tests/test_build_epic_map.py -q` reports `24 passed`. If the shared function replaces `_workflow`, `test_verb_renders_the_blocks:101`'s `inspect.getsource(triage_mod._workflow)` binding is repointed to the new symbol — a symbol rename only; the four asserted tokens at `:102` are unchanged. **Phase**: Unify the recommendation

8. **Behavioral coverage exists for `render()` where none did.** Layer A unit tests over `render()` using a local `_item(**kwargs)` factory per the convention in `tests/test_backlog_readiness.py:29` and `tests/test_generate_backlog_index.py:26`. Cases: a ready epic whose children span both readiness states **and** the types `bug`, `chore`, `idea`, `feature`; flat item with and without `spec`; epic with zero active children (`triage.py:111-116`); empty backlog (`triage.py:178-182`); deferred item excluded from both blocks. Acceptance: `tests/test_triage_render.py` passes and asserts exact rendered strings, not substrings, so the recommendation syntax is pinned. **Phase**: Behavioral coverage

9. **A regression guard reproduces the shipped defect.** Per the convention at `tests/test_backlog_ready_render.py:16-20,190-191`, a fixture engineered to hit the prior-broken path with an inline comment citing ticket 425. Acceptance: the guard asserts a `type: "chore"` item with `status: "refined"` and a non-empty `spec:` renders `` `/cortex-core:build` `` in the Ready block — an assertion that is false against the pre-change behavior described in the Problem Statement and true after. **Phase**: Behavioral coverage

10. **The child-of-non-ready-epic behavior is pinned, not fixed.** An individually-ready item whose parent epic is not itself ready is in `child_ids` (`triage.py:152-154`) but gets no epic block (`:161-165`), so it appears in neither block. Acceptance: a test in `tests/test_triage_render.py` renders such an item and asserts its id appears nowhere in the returned markdown, so any accidental change to this behavior fails the suite. **Phase**: Behavioral coverage

## Non-Requirements

- **One line changes in `skills/dev/SKILL.md`, and only control flow.** Requirement 4 adds a routing clause to Step 3, not behavior — behavior stays in the verb per `#343`. Control flow is the sanctioned exception to keeping prose out of skills, and one line once is strictly less surface than a hint rendered on ~15 of 18 rows on every invocation. The `dev` L1 frontmatter budget row (285/285 bytes, zero headroom) is untouched, since only the body changes; the file is 41 lines against a 500-line cap.
- **`_is_refined()` gains no on-disk existence check.** It reads frontmatter only, so a stale `spec:` pointer will render `/cortex-core:build` for a spec file that no longer exists. This change extends that pre-existing exposure to `bug`/`chore` for the first time rather than creating it. Coupling a per-row predicate to the filesystem is out of scope.
- **The child-of-non-ready-epic bug is not fixed** — pinned by requirement 10, fixed under its own ticket. It is a membership bug in `render()`, not a routing bug.
- **The epic footer's sequencing policy is unchanged.** Requirement 6 changes only which children the footer's partition includes; the sentence "one at a time, each needs interactive spec approval before the next" (`triage.py:129-131`) exists nowhere else and stays as-is.
- **The `[blocked]` mark keeps its bracket vocabulary** beside a backtick-styled recommendation. The two encode orthogonal facts and mixing the styles is accepted rather than harmonized, to avoid widening this change into a rendering-vocabulary redesign.
- **`docs/skills-reference.md:19,78` prose is unchanged.** Both lines describe `/cortex-core:dev`'s own Step 1 routing outcomes ("...or direct implementation"), and "direct implementation" remains a real outcome of Step 1 rule 4 (the trivial-change path), which this change makes *more* reachable rather than removing — so the prose stays accurate.
- **No ADR is proposed** — see Proposed ADR.

## Edge Cases

- **Refined `bug`/`chore`** (the unambiguous defect): renders `` `/cortex-core:build` ``.
- **Unrefined `bug`/`chore`**: renders `` `/cortex-core:refine` ``. Triviality is judged by the agent reading the ticket under Step 1 rule 4, which the renderer cannot assess and no longer gestures at.
- **`type: idea`**: renders `` `/cortex-core:discovery` `` and is checked before the readiness arm — `idea` is a readiness statement, unlike `bug`/`chore` which are problem-kind labels.
- **Unrefined `idea` as an epic child**: renders `/cortex-core:discovery` on its own line and is excluded from the footer's refine bucket (requirement 6), so the block gives one answer rather than two.
- **An epic whose only unrefined children are `idea`-typed**: the footer emits neither the refine sentence nor the overnight sentence, since the remaining children are refined but the idea children are not ready for either path.
- **Unknown types** (`task`, `fix`, `spike`, `enhancement`, `needs-discovery`): fall through to the readiness-only arm, which is already rule-5-consistent. No new handling.
- **`type: epic` in the Ready block**: filtered out at `triage.py:169`. Unaffected.
- **Blocked epic child**: keeps its `[blocked]` mark alongside the recommendation; the two are orthogonal and both render on one line.
- **Epic child with a held status**: excluded from `recommendable` by the existing `_HELD_STATUSES` filter. The per-child recommendation still renders, as today.
- **Item whose `spec:` is the string `"null"`, `"~"`, or `"None"`**: treated as unrefined by `_is_refined()`'s existing sentinel check (`triage.py:74`). Unchanged.

## Changes to Existing Behavior

- **MODIFIED** — `cortex_command/backlog/triage.py:78-84`: the type-only branch returning `"direct implementation"` is removed; readiness governs the recommendation for every type except `idea`.
- **MODIFIED** — `triage.py:95`: `_render_epic_block`'s inline `[refined]` / `[needs /cortex-core:refine]` mark is replaced by a call to the shared recommendation function, resolved from the `by_id` full record rather than the type-less epic-map child envelope. The `[blocked]` mark is retained and still appends after it on the same line.
- **MODIFIED** — `triage.py:176`: the Ready row's `→ {_workflow(item)}` call site renders the shared function's output.
- **MODIFIED** — `triage.py:126`: the footer's `unrefined` partition excludes `idea`-typed children (requirement 6).
- **MODIFIED** — `skills/dev/SKILL.md` Step 3: one control-flow clause routing a picked item back through Step 1.
- **ADDED** — a shared recommendation function in `triage.py`; `tests/test_triage_render.py` with Layer A coverage, the type-parametrized cross-block drift guard, and the ticket-425 regression guard.
- **REMOVED** — the string `"direct implementation"` from rendered output. Nothing parses it (the only repo occurrences outside `triage.py` are descriptive prose at `docs/skills-reference.md:19,:78` and two archived lifecycle docs), so no consumer breaks.

## Technical Constraints

- **The shared function must return a single line.** `_render_epic_block` assembles its row with `" ".join(marks)` and appends `[blocked]` afterward (`triage.py:96-101`); a multi-line return would embed a raw newline mid-row and reorder `[blocked]` below it.
- **The epic block must resolve `type` from `by_id`, not from the child envelope.** `build_epic_map.py:158-163` emits only `id`, `spec`, `status`, `title` — the keyset is locked by `tests/test_build_epic_map.py:124` and must not be widened. `_render_epic_block` already holds `by_id` and uses it for `status`/`blocked_by` at `:94`.
- **`_is_refined()`, not `is_item_ready()`, is the predicate.** `is_item_ready()` is already fully consumed upstream by `_ready_set()` (`triage.py:41-70`), so every item reaching either renderer has passed it — re-checking at render time would be constant-true and carry zero information.
- **`triage.py` is a wheel module, not in the dual-source mirror set** (`.githooks/pre-commit:530`). `skills/dev/SKILL.md` **is** mirrored — its `plugins/cortex-core/` copy is rebuilt from staged blobs at pre-commit and must never be hand-staged.
- **`tests/test_dev_triage_refs_wired.py:101` binds `_workflow` by name.** Deleting the symbol outright raises `AttributeError` before any assertion runs; renaming requires repointing that binding. The four tokens asserted at `:102` survive either way — `/cortex-core:refine` and `/cortex-overnight:overnight` also live in the epic footer (`:130`, `:135`).
- **Do not reuse the `_MOVED_TOKENS` strings** (`tests/test_dev_triage_refs_wired.py:30-46`) in the SKILL.md edit — particularly `"Block 1: Epic sections"`, `"Block 2: Flat ready list"`, `"Per-epic workflow recommendation"`. Requirement 4's criterion (c) is the check.
- **The test-authoring trap**: a test that recomputes the expected recommendation by calling the same predicate the renderer uses proves nothing. Requirement 3's two-render comparison is the dodge, but only when parametrized over type-sensitive fixtures — `type: "feature"` alone (this repo's default fixture convention, e.g. every record in `tests/test_backlog_ready_render.py`) makes the guard vacuous.
- **Cross-block comparison must restrict to the ready subset.** The epic block renders all children regardless of status, while Ready contains only `_ready_set()` survivors; an unrestricted comparison would test against items that structurally cannot appear in the flat block.
- **`#343` is the governing precedent**: the recommendation computation belongs in the verb, not in skill prose re-read on every triage (`tests/test_dev_triage_refs_wired.py:1-17`). This spec keeps it there — requirement 4 adds control flow to the skill, not a recommendation rule.

## Open Decisions

None.

## Proposed ADR

None considered. The skill-vs-CLI boundary question this touches was settled once by #343 and drifted back via `_workflow()`'s type branch, which is an argument for recording it — but `CLAUDE.md:29` prefers structural separation over prose-only enforcement, and this spec's structural guards (one shared function used by both renderers, plus requirement 3's type-parametrized byte-identity test) enforce the boundary directly where an ADR would only describe it. Revisit if the boundary drifts a third time despite the tests.
