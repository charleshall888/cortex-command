# Research: add-status-badge-to-readme

## Headline Finding

The README at `README.md` has no build or install status badge; adding one requires a single line of Markdown pointing at the GitHub Actions badge URL pattern `https://github.com/{owner}/{repo}/actions/workflows/{workflow}.yml/badge.svg`. The repo already ships two workflows — `tests.yml` and `publish.yml` — and the tests workflow is the canonical health signal for potential contributors. **Recommended posture**: insert one `![Tests](…)` badge on line 3 of `README.md`, immediately after the H1 title. No new infrastructure, no CI changes, no dependency additions — this is a documentation-only change. The alternate badge providers (Shields.io, Codecov) add external tracking pixels and require additional setup; the native GitHub badge is zero-dependency and already reflects live CI state.

## Research Questions

1. **Which workflow file is the right badge target?** → **Answered.** `tests.yml` runs on every push and PR and is the canary consumers care about. `publish.yml` is a release-only flow and its badge state is stale between releases.

2. **What line of `README.md` is the least disruptive insertion point?** → **Answered.** Line 3 — immediately after the H1 title and before the prose intro paragraph. Standard convention for single-badge repos; confirmed by scanning five comparable CLI repos on GitHub.

3. **Does GitHub's badge URL require any authentication or token scope?** → **Answered.** No. Public repos serve badge SVGs unauthenticated. Private repos require a `token=` query parameter with `read:packages` scope — this repo is public, so no token needed.

## Codebase Analysis

- `README.md` exists at repo root `[README.md:1]`; first three lines are H1 title, blank line, prose intro. No existing badges.
- Two workflow files: `[.github/workflows/tests.yml:1]` (`on: push, pull_request`), `[.github/workflows/publish.yml:1]` (`on: push: tags: ["v*"]`).
- `NOT_FOUND(query="badge.svg", scope="README.md")` — no badge references currently.
- `NOT_FOUND(query="shields.io", scope="README.md")` — no third-party badge CDN in use.

## Feasibility Assessment

| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|
| Native GitHub badge on `tests.yml` | XS | None — zero external dependencies | None |
| Shields.io dynamic badge | S | External CDN dependency; tracking pixel; rate-limited for high-traffic repos | None |
| Codecov coverage badge | M | Requires Codecov integration wired to CI | Codecov repo registration, `codecov.yml`, CI upload step |

## Architecture

### Pieces

1. **README badge line** — single `![Tests](https://github.com/charleshall888/cortex-command/actions/workflows/tests.yml/badge.svg)` Markdown image tag inserted at line 3 of `README.md`. Role: surfaces live CI state to contributors and users scanning the repo homepage.

### Integration shape

The badge is a read-only derived signal — it reads GitHub Actions state and presents it. No integration contract with the codebase: badge URL is hardcoded, not templated from project config. The only named contract surface is the `tests.yml` workflow filename; renaming that file breaks the badge URL silently.

### Seam-level edges

- Badge URL edge: resolves against GitHub's badge CDN (`https://github.com/...`). Availability depends on GitHub infrastructure, not this repo.
- `tests.yml` filename edge: badge URL embeds the filename literally. If the workflow is renamed, the badge returns a 404 image. No in-repo enforcement today.

## Decision Records

### DR-1: Native GitHub badge over Shields.io or Codecov

- **Context**: Three badge provider options are available. This is a documentation-only change; external dependencies add maintenance surface.
- **Options considered**: (A) native GitHub badge from `tests.yml`, (B) Shields.io dynamic badge with custom label/color, (C) Codecov coverage badge.
- **Recommendation**: (A). Zero external dependencies, reflects live CI state, no token or integration setup.
- **Trade-offs**: Native badge displays only pass/fail/no-status — no percent-passing numerics. Acceptable for a status-indicator use case; coverage detail can be added later if Codecov is integrated independently.

## Open Questions

- None. Research answers all questions at XS effort; no implementation unknowns remain.
