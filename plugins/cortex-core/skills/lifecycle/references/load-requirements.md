# Tag-Based Requirements Loading

Shared tag-based loading protocol for pulling the minimal set of project and area-level requirements docs into a phase's working context. Selection is offloaded to the deterministic `cortex-load-requirements` verb (the single source of selection truth); its `--help` documents the matching semantics, and this reference covers only how a consumer drives it.

## Protocol

1. Run `cortex-load-requirements --feature {slug}` (lifecycle/refine consumers, which have a `cortex/lifecycle/{slug}/index.md`) or `cortex-load-requirements` (discovery, which has no lifecycle index). It prints the resolved repo-relative requirements paths to stdout; a file absent on disk carries a ` (skipped: file absent)` suffix. Any no-match fallback note is printed to stderr.
2. Read every listed non-skipped path into your working context — the verb prints paths only, never file contents.
3. Inject the printed path list verbatim into any downstream prompt (reviewer dispatch, drift-check) that must know what was in scope, and relay any fallback note.

If a concept you need is not yet defined in the glossary, treat the absence as a signal to surface the term in the next requirements interview.
