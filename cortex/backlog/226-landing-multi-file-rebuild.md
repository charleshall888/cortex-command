---
schema_version: "1"
uuid: b96fac46-a683-4b7b-a000-25c1e5184685
title: Rebuild docs/index.html as a multi-file landing-page source tree
status: backlog
priority: medium
type: feature
tags: [landing-page, devx, build]
areas: [docs]
created: 2026-05-16
updated: 2026-05-16
lifecycle_slug: null
lifecycle_phase: null
session_id: null
blocks: []
blocked-by: []
---

## Why

`docs/index.html` is a ~257KB single-file artifact (5,900+ lines including the v9 landing page with the carbon stain, the spec-stream, the pipeline, the trust grid, the hood gatefold, the install section, and the redline toggle). The file ships from `landing-page/_imports/Cortex Command v9.html`, which is treated as a read-only canonical source exported from Claude Design.

Two pains follow from the single-file shape:

1. **Iteration is unreadable.** Any change touches one giant HTML/CSS/JS soup. Diffs are hard to review, and changes that look isolated in the source frequently bleed across the file (CSS at line 200 affects markup at line 4500). The Phase 1–4 rollout of this landing required ~10 atomic commits with careful grepping for each anchor; a multi-file source would have produced clearer diffs.
2. **Future Claude Design imports require manual merging.** When a v10 export lands, the diff against current state is intractable to apply by eye. Today the workflow is "strip edit-mode scaffold + diff manually + cherry-pick" — fragile and slow.

## Target architecture (sketch — research could explore alternatives)

One approach might be:

- `landing-page/src/partials/` — HTML fragments by section (hero, spec-stream, pipeline, hood, install, footer)
- `landing-page/src/styles/` — CSS modules grouped by component (base, sidebar, sec, pipe, hood, redline, etc.)
- `landing-page/src/scripts/` — JS modules (spec-lock, pipe-scrub, hood-reveal, redline-toggle, etc.)
- `landing-page/build.py` — concatenator that emits a single `docs/index.html` from the source tree (keeps the GitHub Pages deploy shape unchanged)
- `just landing-{dev,build,validate}` recipes for the inner loop

The key open question is whether the build step should produce a single-file `docs/index.html` (matches today's deploy shape, no infrastructure changes) or split into separate CSS/JS files (smaller initial payload, more HTTP requests). Research should evaluate both against the actual landing-page audience profile.

## Key investment to consider during research

A **reverse-diff tool**: takes a fresh `v10.html` export from Claude Design and emits per-section patches against the current `landing-page/src/` tree. Without this, future imports remain a manual-merge ordeal, defeating the multi-file gain.

## Performance budget (target)

- Initial HTML payload: 60–80KB
- CSS: 50KB
- JS: 25KB (gzipped)

Current single-file shape: ~257KB uncompressed, ~50KB gzipped — already inside this budget at the wire, but the build-time concerns (iteration, future imports) are the actual driver, not bytes.

## Phases (rough order — actual plan emerges from research)

1. Scaffold `landing-page/src/` + `build.py` skeleton + `just` recipes.
2. Extract CSS into modules and verify byte-identical concatenated output.
3. Extract JS into modules.
4. Extract HTML into partials.
5. CI check that `build.py` output matches `docs/index.html`, gated on PRs that touch either tree.
6. Documentation update (landing-page/README.md + docs/ entry).
7. **Stretch:** the reverse-diff tool for v10 imports.

## Size and constraints

- **Size:** L. The bulk of the work is in steps 2–4 (careful extraction without behavior drift); steps 1, 5, 6 are tractable on their own.
- **Constraint:** the deployed artifact at `docs/index.html` must continue to be a single self-contained HTML file (GitHub Pages, no build step on the server side).
- **Constraint:** the v9 source at `landing-page/_imports/Cortex Command v9.html` stays as the read-only canonical Claude Design artifact; the new `src/` tree derives from it but is not bound to it.

## Epic

`landing-page-evolution` — companion to the v9 ship that just landed (Phase 1–5 of the v9 hybrid rollout, commits `a0d137bc..87b41b14`).
