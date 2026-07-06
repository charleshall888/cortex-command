# Tag-Based Requirements Loading

Shared protocol for pulling the minimal set of project and area-level requirements docs into a phase's context. Selection is offloaded to the deterministic `cortex-load-requirements` verb (the single source of selection truth; its `--help` documents the matching semantics) — this reference covers only how a consumer drives it.

## Protocol

1. Run `cortex-load-requirements --feature {slug}` (lifecycle/refine consumers, which have `cortex/lifecycle/{slug}/index.md`) or `cortex-load-requirements` (discovery, no lifecycle index). It prints the resolved repo-relative paths to stdout — a file absent on disk gets a ` (skipped: file absent)` suffix; any no-match fallback note goes to stderr.
2. Read every listed non-skipped path into context — the verb prints paths only, never file contents.
3. Inject the printed path list verbatim into any downstream prompt that must know what was in scope, and relay any fallback note.
