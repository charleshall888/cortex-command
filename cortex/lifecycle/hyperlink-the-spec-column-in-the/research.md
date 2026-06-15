# Research: Hyperlink the spec column in the generated backlog index

Convert the bare checkmark at `cortex_command/backlog/generate_index.py:234` (`spec_display`) into a clickable markdown link to each item's spec path, while preserving deterministic output. The central question going in was: **what link href form resolves correctly from `cortex/backlog/index.md` given repo-root-relative stored spec paths?** Research resolved that question and corrected one load-bearing premise in the ticket.

## Codebase Analysis

**Single file changes:** `cortex_command/backlog/generate_index.py:234`. Current line:
```python
spec_display = "✓" if item["spec"] else "—"
```
The spec path is already in the per-item record (line 200, `"spec": _opt(fm, "spec")`) — no new field or input. The change is a pure render edit in the row-builder loop (lines 231–240): wrap the truthy branch in a markdown link, keep the `—` (em-dash) else-branch verbatim.

**Premise correction — `index.md` is gitignored, not committed.** `cortex/backlog/index.md` and `index.json` are gitignored (`cortex_command/init/templates/cortex/.gitignore:38-39`; `git check-ignore` confirms IGNORED, `git ls-files` empty). They are a regenerated local cache. `skills/overnight/references/new-session-flow.md:17` documents this explicitly ("regenerated local cache and is **not committed** — regenerate it, but do not stage or commit it"). Consequences:
- There is **no regenerate-and-diff staleness check, no pre-commit gate, and no test that diffs a committed `index.md`** — because it isn't committed. The ticket's "regenerate-and-diff staleness check stays clean" framing rests on a false premise.
- The "byte-stability" Edge reduces to *internal generator determinism* (`atomic_write`, sorted input at line 211), which is trivially satisfied — the href is a pure string transform of sorted-input frontmatter.
- Because it is gitignored, `index.md` is **never rendered on GitHub** — it is viewed in a local editor. This sharpens the path-form choice toward local-editor correctness (see Tradeoffs).

**No existing markdown-link render pattern** exists in this generator, sibling backlog generators, the dashboard, or overnight modules. The href form is a fresh decision (resolved below).

**Spec path format confirmed uniform:** all 208 active items carrying a `spec:` value use a repo-root-relative path with exactly two prefixes — `cortex/lifecycle/{slug}/spec.md` or `cortex/lifecycle/archive/{slug}/spec.md`. Zero use a leading slash, `./`, or any non-`cortex/lifecycle/` anchor.

**No consumer parses the Spec column programmatically.** `/dev` reads the `spec` field from `index.json` (via `cortex-build-epic-map`), not the index.md Spec column; the dashboard does not read `index.md`; `/cortex-core:backlog` reads it human-facing only. Adding a link breaks no programmatic consumer — the column is display-only.

**Parity / mirror:** `cortex-generate-backlog-index` is a `[project.scripts]` console entry (`pyproject.toml:28`), **not** a `bin/cortex-*` shell script — outside the dual-source mirror enforcement. No `bin/` or plugin-mirror file to touch in lockstep. Parity wiring is satisfied by the `just backlog-index` recipe (`justfile:126-127`); the render change doesn't alter invocation wiring.

**Test:** `tests/test_generate_backlog_index.py` pins full table-row equality. All current fixtures have `spec=None`, so every pinned row ends `| — |` and **existing assertions stay green unchanged** (the link only renders when spec is set). The `_make_item` factory (lines 26–57) already has a `spec` key — add one new test with `spec` populated to pin the linked form.

**Pre-commit gate (the one real gate):** `.githooks/pre-commit:156` runs the entry-point telemetry check on this file — `main()`'s first statement must remain `_telemetry.log_invocation(...)` (already at line 322, untouched by this change).

## Web Research

**Direct answer to the central question:** for a file at `cortex/backlog/index.md` linking to `cortex/lifecycle/<slug>/spec.md`, the **file-relative `../` form is the only one that resolves correctly across every viewer**: `[✓](../lifecycle/<slug>/spec.md)`.

| Form | GitHub blob | VS Code preview | Local editors |
|------|-------------|-----------------|---------------|
| `../lifecycle/foo/spec.md` (file-relative) | ✓ resolves vs `cortex/backlog/` | ✓ resolves vs current file | ✓ standard relative path |
| `/cortex/lifecycle/foo/spec.md` (leading slash) | ✓ GitHub → repo root | ✗ VS Code → **workspace root**, not repo root (as-designed) | ✗ many treat `/` as filesystem root |
| `cortex/lifecycle/foo/spec.md` (raw, no `../`) | ✗ → nonexistent `cortex/backlog/cortex/lifecycle/...` | ✗ same | ✗ same |

Key sourced facts:
- GitHub docs ([Basic writing and formatting syntax](https://docs.github.com/en/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github/basic-writing-and-formatting-syntax)): "A relative link is relative to the current file"; "Links starting with `/` will be relative to the repository root"; `../` is supported.
- VS Code docs ([Markdown in VS Code](https://code.visualstudio.com/docs/languages/markdown)): "Paths starting with `/` are resolved relative to the **workspace root**, while paths starting with `./` or without any prefix are resolved relative to the current file." VS Code issue [#120754](https://github.com/microsoft/vscode/issues/120754) closed the workspace-vs-repo-root divergence as "as-designed" — the leading-slash trap is permanent.
- GFM table-cell safety ([GFM spec §4.10](https://github.github.com/gfm/)): `[text](url)` links are fully supported inside `|`-delimited cells; only `|` needs escaping (paths never contain one); slashes, brackets, parens need no escaping.
- Prior art: MkDocs and Material for MkDocs use file-relative `../` `.md` links for cross-directory references so links work both rendered and when browsing source — matches the recommended form.

**Note on the gitignored finding:** since `index.md` is never rendered on GitHub (Codebase Analysis), the operative viewer is the local editor. `../`-relative is correct there too, so the recommendation is unchanged and is also the most portable if the file is ever viewed elsewhere.

## Requirements & Constraints

- **Backlog is documented inline — no area requirements doc** (`cortex/requirements/project.md:62`). There is no `backlog.md` area doc; `project.md` is the only governing requirements file. The parent item's tag `cortex-core-tooling-gaps` matches no Conditional Loading phrase, so no area doc loads.
- **No requirements-doc constraint mandates "byte-stability" / "regenerate-and-diff" for the backlog index.** Grep across `cortex/requirements/` finds determinism language only for worktrees, session resume, and the overnight pipeline — none for backlog-index rendering. The byte-stable expectation lives in ticket framing and in the generator/test code, not in requirements. (Consistent with the gitignored-cache finding.)
- **SKILL.md-to-bin parity** (`project.md:33`) applies to the script's reachability but not to render internals; the change doesn't alter wiring and the script is not on the parity-exceptions allowlist.
- **Complexity / Solution Horizon** (`project.md:19, 21`): favors the simplest correct edit anchored on current knowledge — a self-contained render change with no new input/schema.
- **Scope boundaries reinforced:** spec column only; preserve the empty-spec dash; no new field/input; do not disturb the deferred-state rendering, which lives inline in the **Status cell** (line 235), not a separate column.
- `glossary.md` (Global Context) is absent on disk — recorded as skipped; no effect here (the change introduces no glossary-worthy term).

## Tradeoffs & Alternatives

Grounding: `index.md` is always at `cortex/backlog/index.md`; specs always at `cortex/lifecycle/{slug}/spec.md`. The index-dir → spec-dir relationship is fixed (up one, into a sibling), so `os.path.relpath("cortex/lifecycle/foo/spec.md", "cortex/backlog")` is deterministically `../lifecycle/foo/spec.md`.

- **A — Raw stored value** `[✓](cortex/lifecycle/foo/spec.md)`: **broken** — resolves to nonexistent `cortex/backlog/cortex/lifecycle/...`. Zero path logic, but a dead link. Disqualified.
- **B — `../`-relative prefix swap** `[✓](../lifecycle/foo/spec.md)`: **correct** on all viewers; fully deterministic (pure string transform `spec.replace("cortex/", "../", 1)`); one trivial op in the byte-stable region. Weakness: assumes spec paths start with `cortex/` — silent wrong-link if that ever changes (currently 0/208 violate it). Mitigated cheaply with a prefix guard.
- **C — Root-anchored leading slash** `[✓](/cortex/lifecycle/foo/spec.md)`: unreliable on GitHub blob and broken in VS Code (workspace-root divergence). Disqualified.
- **D — `os.path.relpath` / `pathlib` computed**: correct, byte-identical to B for the current corpus, and robust to specs leaving `cortex/`. Cost: most logic in the byte-stable region, requires threading the index dir into `generate_md` (currently it receives only items) or hardcoding `"cortex/backlog"` (which re-introduces the coupling D was meant to avoid), plus a cross-platform separator caveat.

**Recommended: Alternative B with a defensive prefix guard.** Per Solution Horizon, D's only edge — robustness to specs leaving `cortex/lifecycle` — is not earned: no such move is planned, the coupling is a single site, and `cortex/` is an architectural invariant of this repo. The simpler fix is correct. Close B's silent-failure mode with a 2-line guard so a non-`cortex/` path fails loudly instead of silently:

```python
href = item["spec"].replace("cortex/", "../", 1) if item["spec"].startswith("cortex/") else item["spec"]
spec_display = f"[✓]({href})" if item["spec"] else "—"
```

Keep `✓` as the link text (it *is* the affordance; no new token); keep the `—` em-dash for the empty case verbatim. Update the test fixture to pin the linked form plus the unchanged empty-spec dash.

## Open Questions

- **Does the gitignored `index.md` finding change the work?** Resolved: no — it *simplifies* it. The ticket's "regenerate-and-diff staleness check stays clean" premise is false (the file is a gitignored local cache, not committed; no staleness gate exists). The Spec should drop that language and frame byte-stability as internal generator determinism only, which the pure-string href transform trivially preserves. No committed artifact to keep in sync; no user decision required.
- **B-with-guard vs D (computed relpath)?** Resolved (recommendation): B with prefix guard, per Solution Horizon — durable-version criteria (planned follow-up / multi-site patch / named constraint) are all absent, and `cortex/` is an architectural invariant. Carried into Spec as the recommended approach; open to reversal only if the Spec phase surfaces a planned move of specs outside `cortex/lifecycle`.
