---
schema_version: "1"
uuid: 9cfcaf29-ad85-460c-a44b-aab95905f16b
title: "Make cortex-check-parity context-aware (skip tokens inside fenced code blocks)"
status: deferred
priority: low
type: feature
tags: [tooling, parity-linter, hooks]
areas: [tooling]
created: 2026-05-01
updated: 2026-05-04
session_id: null
lifecycle_phase: null
lifecycle_slug: make-cortex-check-parity-context-aware-skip-tokens-inside-fenced-code-blocks
complexity: complex
criticality: high
---

# Make cortex-check-parity context-aware (skip tokens inside fenced code blocks)

## Problem

`bin/cortex-check-parity` regex-scans markdown for `cortex-[a-z][a-z0-9-]*` tokens and treats anything not in `bin/`, the 3-entry `RESERVED_NON_BIN_NAMES` set, or `bin/.parity-exceptions.md` as a missing script reference (E002). The scan is context-blind — a path-segment placeholder inside a fenced code block is treated identically to a prose script reference.

Ticket 149's lifecycle (2026-05-01) hit this: `docs/setup.md:310` had `/path/to/your/cortex-command-clone/claude/statusline.sh` inside a JSON code block. The `cortex-command-clone` token tripped E002. Worked around by rephrasing the placeholder (commit `f817c11`); the underlying linter limitation is unaddressed.

## Why it matters

Every commit during ticket 149's lifecycle hit this drift. Future docs that need `cortex-*`-shaped path placeholders (especially under the no-clone wheel-install migration where setup.md is still actively edited) will hit the same false-positive treadmill. The `.parity-exceptions.md` schema doesn't fit placeholders — its `category` enum (`maintainer-only-tool` / `library-internal` / `deprecated-pending-removal`) is for actual scripts.

## Proposed approaches (research phase)

1. **Skip fenced code blocks entirely.** Cheapest. Token references inside ` ``` ... ``` ` and inline ` `code` ` spans are excluded from the candidate set. Risk: a real script reference quoted as code (e.g., `` `cortex-pr-rollup` ``) would no longer count as a wiring signal — needs separate audit of whether code-spanned references are load-bearing for current allowlist entries.
2. **Path-segment heuristic.** Skip tokens that appear inside path-like contexts (`/cortex-foo/`, `/cortex-foo/bar`). Narrower; preserves prose code-span scanning. More fragile.
3. **Allowlist placeholder names.** Extend `RESERVED_NON_BIN_NAMES` with documented placeholder tokens. Cheapest by line count; doesn't fix the design issue.

Default recommendation pending research: (1), with a pre-flight scan to confirm code-spanned references aren't load-bearing.

## Discovery context

Surfaced during `/cortex-interactive:lifecycle 149` implementation when every commit hit E002 on `docs/setup.md:310`. Workaround landed as commit `f817c11`.

## Deferral (2026-05-04)

Deferred after a complex/high-criticality lifecycle research pass. Decision rationale and full research are preserved at `lifecycle/make-cortex-check-parity-context-aware-skip-tokens-inside-fenced-code-blocks/research.md` (5-agent research + adversarial review).

**Why deferred**: the motivating false positive (`cortex-command-clone` placeholder in `docs/setup.md:310`) was rephrased away in commit `f817c11` and has not recurred in 17 subsequent commits to that file — including the no-clone wheel-install migration commits (`bc07a80`, `f7c5210`, `4574a21`) cited in the original ticket as the forward-looking justification. A pre-flight audit of all 150 in-scope files confirmed zero deployed scripts are wired only via fenced code blocks today, so no current false positive exists. Per `requirements/project.md:19` ("complexity must earn its place by solving a real problem that exists now"), shipping an asymmetric fenced-skip linter mode now would be speculative complexity.

**Re-open trigger**: re-open this ticket if E002 false-positives surface 2+ times in lifecycle or overnight work over a 60-day window.

**Recommended fix-on-recurrence (Option B)**: extend `RESERVED_NON_BIN_NAMES` (or add a sibling `PLACEHOLDER_NAMES` frozenset) at `bin/cortex-check-parity:45–58` with the offending placeholder token plus a ≥30-char rationale comment. This mirrors the existing precedent (which already handles `cortex-command` and `cortex-overnight` for exactly this class of false positive) and is a ~4-line linter patch + 1 self-test fixture.

**Why not the asymmetric fenced-skip approach (Option A from the original ticket body)**: the adversarial review surfaced (a) the current `FENCED_CODE_RE` produces *spurious partial matches* on ≥4-backtick fences (CommonMark legal, used precisely when content includes triple backticks); (b) the `wired ⊇ candidates` invariant breaks silently with no test enforcement; (c) tilde fences, indented code blocks, and inline placeholders remain unhandled — i.e., A patches one failure shape while leaving four sibling shapes; (d) reverse-asymmetry footgun risk between `collect_wiring_signals` and `collect_reference_candidates`. See research.md §"Adversarial Review" for full analysis.

**Why not the parser AST approach (Option D from the research)**: technically cleanest but requires adding `markdown-it-py` to the linter, breaking the script's stdlib-only convention. ROI doesn't match a one-occurrence-in-six-months problem; reconsider if recurrence pattern proves the regex approach untenable.

**Latent bug surfaced during research (capture-only, not blocking)**: `FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)` at `bin/cortex-check-parity:361` produces a *spurious partial match* on ≥4-backtick fences (CommonMark legal, used precisely when fenced content needs to contain literal triple backticks). The non-greedy match consumes ` ```` ... ``` `, stopping at the first inner triple-backtick — splitting the block in half. Tokens in the back half are then treated as prose. No occurrences in the current corpus, so not actionable today, but worth knowing if the regex is ever revisited (here or in a sibling linter). Tilde fences (`~~~`), 4-space indented code blocks, and leading-1-3-space fence indents are also unhandled by today's regex; same audit confirmed zero current occurrences.
