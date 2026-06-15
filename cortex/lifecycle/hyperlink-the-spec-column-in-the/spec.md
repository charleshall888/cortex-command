# Specification: hyperlink-the-spec-column-in-the

## Problem Statement
The generated backlog index (`cortex/backlog/index.md`) renders a bare `✓` in the Spec column to mark items that have a spec, but the marker is not clickable even though the per-item record already holds the spec's path. A reader who wants to open an item's spec from the index must locate the file by hand. Making the marker a navigable link turns the index into a jumping-off point. Beneficiary: any operator scanning the index in a local editor; cost is one line of render logic plus a guard.

## Phases
- **Phase 1: Link the spec marker** — render the Spec-column checkmark as a relative markdown link to the item's spec, preserving the empty-spec dash and the generator's deterministic output.

## Requirements
1. **(Must) Spec-column marker renders as a relative markdown link when a spec path is present.** The truthy branch at `cortex_command/backlog/generate_index.py:234` renders `[✓](<href>)`, where `<href>` is the stored spec path rewritten relative to the index file's directory (`cortex/backlog/`). Acceptance: a test case in `tests/test_generate_backlog_index.py` constructs an item with `spec="cortex/lifecycle/foo/spec.md"` and asserts the rendered Spec cell equals the literal `[✓](../lifecycle/foo/spec.md)`; the targeted pytest (`uv run pytest tests/test_generate_backlog_index.py`) exits 0. **Phase**: Link the spec marker.
2. **(Must) Empty-spec case keeps the bare em-dash, unlinked.** When `item["spec"]` is falsy, the Spec cell renders `—` (`—`) exactly as today. Acceptance: the existing full-row equality assertions in `tests/test_generate_backlog_index.py` for `spec=None` items (rows ending `| — |`) remain green with **no edit**; `just test` exits 0. **Phase**: Link the spec marker.
3. **(Should) Non-`cortex/`-prefixed spec path falls back to the raw stored value rather than a silent `../` rewrite.** The href transform applies the `cortex/`→`../` swap only when the stored path begins with `cortex/`; otherwise it emits the raw value. Acceptance: a test case with `spec="external/foo/spec.md"` asserts the cell renders `[✓](external/foo/spec.md)` (raw, not `../foo/...`); the targeted pytest exits 0. **Phase**: Link the spec marker.

## Non-Requirements
- Does not add a tags section, relocate the event log, or make any other index column (ID/Title/Status/Priority/Type/Blocked By/Parent) clickable — **Spec column only**.
- Does not change `index.json`, add a new frontmatter field, or add a new input — pure render change reusing the existing `spec` value.
- Does not adopt Alternative D (`os.path.relpath`/`pathlib` computation, or threading the index directory into `generate_md`). The prefix-swap-with-guard is sufficient on current knowledge; `cortex/` is an architectural invariant of this repo.
- Does not make non-`cortex/`-prefixed spec paths *resolve correctly* — none exist today; the guard only prevents a silently wrong `../` rewrite, surfacing such a path as a visible raw value rather than fixing it.
- Does not change the empty-spec `—` marker or the deferred-state rendering (which lives inline in the Status cell, `generate_index.py:235`).

## Edge Cases
- **Empty/absent spec** (`item["spec"]` falsy): renders bare `—`, unlinked — unchanged from today.
- **Archive spec path** (`cortex/lifecycle/archive/{slug}/spec.md`): the single-occurrence prefix swap (`replace("cortex/", "../", 1)`) correctly yields `../lifecycle/archive/{slug}/spec.md` — the `archive/` segment is preserved.
- **Spec path not starting with `cortex/`** (zero in the current 208-item corpus): the guard emits the raw stored value instead of a wrong `../`-rewrite — a deliberate loud-but-visible signal that would prompt an upgrade to a computed relpath if spec locations ever diversify.
- **Spec path containing `|`**: would break the GFM table cell, but lifecycle slugs/paths never contain a pipe; no escaping is added (consistent with the adjacent `parent_display`/`blocked_display` cells).

## Changes to Existing Behavior
- MODIFIED: Spec-column truthy render `✓` → `[✓](../lifecycle/{slug}/spec.md)` (relative markdown link). The em-dash empty-spec branch is unchanged.

## Technical Constraints
- **`index.md` is a gitignored local cache, not a committed artifact** (`cortex/.gitignore:38-39`; confirmed via `git check-ignore`/`git ls-files`). There is no regenerate-and-diff staleness gate, no pre-commit diff gate, and no test that diffs a committed `index.md`. The ticket's "regenerate-and-diff staleness check stays clean" framing rests on a false premise; here "byte-stability" means internal generator determinism only (`atomic_write` + sorted input, `generate_index.py:211, 327-331`), which a pure string transform trivially preserves. The file is viewed in a local editor, never rendered on GitHub.
- **Link form must be `../`-relative.** It is the only href that resolves across GitHub blob view, VS Code preview, and plain local editors; a leading-slash form resolves to the *workspace root* (not repo root) in VS Code — VS Code #120754, closed "as-designed" — and a raw path resolves to the nonexistent `cortex/backlog/cortex/lifecycle/...`. Source: `research.md` Web Research.
- **GFM table-cell link safety**: `[text](url)` is valid inside `|`-delimited cells; slashes, brackets, and parens need no escaping; only a literal `|` would (paths never contain one). Source: GFM spec §4.10, cited in `research.md`.
- **Single-file change, no mirror.** `cortex-generate-backlog-index` is a `[project.scripts]` console entry (`pyproject.toml:28`), not a `bin/cortex-*` shell script, so it is outside the dual-source mirror enforcement — no `plugins/cortex-core/bin/` mirror to update in lockstep.
- **Pre-commit telemetry gate** (`.githooks/pre-commit:156`, Phase 1.7): `main()`'s first statement must remain `_telemetry.log_invocation("cortex-generate-backlog-index")` (line 322) — untouched by this change.
- **No programmatic consumer of the Spec column**: `/dev` reads the `spec` field from `index.json` (unchanged here), the dashboard does not read `index.md`, and `/cortex-core:backlog` reads it human-facing only — adding a link breaks no consumer.

## Open Decisions
None. The path form (`../`-relative) and the B-vs-D approach choice (prefix-swap-with-guard over computed relpath) were resolved in `research.md`.

## Proposed ADR
None considered.
