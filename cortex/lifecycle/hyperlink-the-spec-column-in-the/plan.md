# Plan: hyperlink-the-spec-column-in-the

## Overview
A one-line production render change in the backlog-index generator, landed together with its test coverage: the Spec-column `✓` becomes a `../`-relative markdown link to each item's spec, the empty-spec em-dash is preserved, and a `startswith("cortex/")` guard keeps a non-`cortex/` spec path from being silently mis-rewritten. The change and its tests land in one atomic task so trunk never holds a transiently-failing test.

## Outline

### Phase 1: Link the spec marker (tasks: 1)
**Goal**: The Spec-column checkmark renders as a `../`-relative markdown link to each item's spec, with the empty-spec dash and the non-`cortex/` guard intact, pinned by tests.
**Checkpoint**: `just test` green, including new assertions for the linked cell, the raw-fallback cell, and the unchanged empty-spec dash.

## Tasks

### Task 1: Render the spec-column checkmark as a relative markdown link, with tests
- **Files**: `cortex_command/backlog/generate_index.py`, `tests/test_generate_backlog_index.py`
- **What**: Change the Spec-column render so a present spec produces a `../`-relative markdown link, keep the empty-spec em-dash, and pin all three behaviors (linked, raw-fallback, empty) with test cases.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - *Production change* — `cortex_command/backlog/generate_index.py` line 234 currently reads `spec_display = "✓" if item["spec"] else "—"`, inside the row-builder loop (lines 231–240). `item["spec"]` is the raw repo-root-relative path populated at line 200 (`cortex/lifecycle/{slug}/spec.md`, incl. `cortex/lifecycle/archive/...`). Apply the transform fixed in `spec.md` Requirements 1 & 3 / Technical Constraints: when `item["spec"]` starts with `cortex/`, the href is that value with the leading `cortex/` replaced by `../` (a single replacement → `../lifecycle/.../spec.md`); otherwise the href is the raw value; the present-spec cell renders `[✓](href)`. Em-dash literal is `—`, checkmark `✓`. Do not change the 8-column count/order (Spec is last); paths contain no `|`, so no cell escaping. `main()`'s first statement (the `_telemetry.log_invocation("cortex-generate-backlog-index")` call near line 322) must stay first — pre-commit Phase 1.7 telemetry gate. This is the only production file: `cortex-generate-backlog-index` is a `[project.scripts]` console entry, not a `bin/cortex-*` script, so there is no `plugins/cortex-core/bin/` mirror to update.
  - *Tests* — `tests/test_generate_backlog_index.py` imports `from cortex_command.backlog import generate_index as _gen_index` and renders via the helper `_render(items)` (≈ line 81) which calls `_gen_index.generate_md(...)`; `_make_item(**kwargs)` (line 26) already exposes a `spec` key defaulting to `None`. Add: (a) an item with `spec="cortex/lifecycle/foo/spec.md"` whose rendered row contains the literal `[✓](../lifecycle/foo/spec.md)` (Req 1); (b) an item with `spec="external/foo/spec.md"` whose row contains `[✓](external/foo/spec.md)` — raw fallback, not `../foo/...` (Req 3); (c) a `spec=None` item whose Spec cell is still `| — |` (Req 2 — the existing pinned rows at lines 104/114/183/213 already assert this; reuse or add one explicit case). Follow the existing row-assertion idiom (substring / row-equality against the `generate_md` output string). The expected link literals are fixed by the spec, so the tests assert an externally-defined target, not the implementation's own output.
- **Verification**: `just test` exits 0 — the new linked-cell, raw-fallback, and empty-spec assertions pass and no existing assertion regresses. (`just test` imports the source-linked `cortex_command`; see Risks.)
- **Status**: [ ] pending

## Risks
- **Implement on trunk / sequentially — not a worktree.** This change edits the `cortex_command` package, and the editable install's `.pth` resolves `cortex_command` to the parent working tree (confirmed: `cortex_command.__file__` → repo root). Inside an `Agent(isolation:"worktree")` checkout, `just test`/pytest would import the stale parent copy, not the worktree edits — so verification would test the wrong code. `branch-mode` is `prompt`, so the implement picker fires; choose **trunk** (or otherwise dispatch sequentially in the tree the editable install points at). Per the "editing the cortex_command package → sequential dispatch, not worktree" constraint.
- **Ticket-premise correction already absorbed.** The ticket's "regenerate-and-diff staleness check" framing is moot — `index.md` is gitignored, so there is no committed-artifact gate; byte-stability here is internal generator determinism only, trivially preserved by a pure string transform. No action required; noted for reviewer awareness.
