# Tag-Based Requirements Loading

Shared protocol for loading project and area-level requirements docs into a phase's working context. Consumed by lifecycle clarify/specify/review, discovery clarify/research, and refine. The protocol ensures each consumer loads the same minimal set of requirements relevant to the lifecycle's tags, avoiding both under-loading (missed constraints) and over-loading (token bloat from irrelevant areas).

## Protocol

Follow these five steps in order:

1. **Always load `cortex/requirements/project.md` and every path enumerated in its `## Global Context` section.** `project.md` is the project-level requirements doc and is unconditionally in scope for every consumer. The `## Global Context` section (positioned between `## Conditional Loading` and `## Optional`) is a bulleted list of paths under `cortex/requirements/` that are always loaded alongside `project.md`, regardless of tag matches. Resolve each entry against the repo root. If an entry's file is absent on disk, record it in the loaded-files list step 4 produces as `<path> (skipped: file absent)` — explicit notation, not silent omission — so downstream drift-check and reviewer-dispatch consumers can distinguish "loaded" from "skipped because absent."

2. **Read the consumer's lifecycle `index.md` and extract the `tags:` array from its YAML frontmatter.** The index lives at `cortex/lifecycle/{feature}/index.md` (or the analogous discovery/refine path). The `tags:` field is a YAML list of short tag words inherited from the parent backlog item.

3. **Read the Conditional Loading section of `cortex/requirements/project.md`.** For each tag word in the `tags:` array, check **case-insensitively** whether any Conditional Loading phrase contains that word. Collect the area doc paths for all matches. A single tag may match multiple phrases; a phrase matched by multiple tags is loaded once.

4. **Load each matched area doc.** Read the files collected in step 3 into the working context alongside `project.md`. Record the full list of loaded requirements files (project.md + matched area docs) so downstream prompts (e.g. reviewer dispatch, drift-check) can be told exactly what was in scope.

5. **Fallback when `tags:` is empty or absent.** If the lifecycle `index.md` has no `tags:` field, or `tags:` is present but empty (`tags: []`), or no tag word matches any Conditional Loading phrase: load `project.md` only and proceed silently. No tags is not an error condition — it is the documented fallback for lifecycles whose parent backlog item has no tags, or for new lifecycles created without a parent backlog. Optionally record a brief note (e.g. "no area docs matched for tags: {tags}; loaded project.md only") for downstream visibility, but do not block, retry, or warn.

## Matching Semantics

- **Case-insensitive substring match against the Conditional Loading phrase text.** A tag word `harness` matches a phrase "Harness adaptation work". A tag word `agent` matches "agent dispatch".
- **Tag words that match nothing are silently dropped.** Other tags in the same array are still evaluated independently. The lifecycle does not fail if a tag word is unrecognized.
- **Whole-tag matching, not partial-tag.** The tag word is the unit of comparison; do not split a tag like `harness-adaptation` into `harness` and `adaptation` unless the tags array itself contains those as separate entries.
- **Global Context uses list-of-paths semantics, not phrase matching.** Each bullet under the `## Global Context` section of `project.md` is a path relative to repo root (e.g. `cortex/requirements/glossary.md`). The loader reads each listed path on every consumer invocation — there is no tag-driven gating and no substring match against the bullet text. Absent paths are recorded as skipped per step 1's `<path> (skipped: file absent)` notation; this is the documented behavior, not an error condition. The section may be empty; an empty `## Global Context` means no always-load files beyond `project.md` itself.

## Why this protocol

The tag-based loader replaces an earlier heuristic that scanned area-doc filenames for words that "suggested relevance" to the lifecycle. The heuristic was lossy in both directions: it missed area docs whose filenames did not echo the lifecycle's topic, and it loaded irrelevant docs whose filenames coincidentally matched. The tag-based protocol uses an explicit, author-curated signal (the lifecycle's `tags:` array, inherited from the parent backlog item) cross-referenced against an explicit, requirements-author-curated signal (the Conditional Loading section of `project.md`). Both signals are human-authored, deterministic, and auditable.
