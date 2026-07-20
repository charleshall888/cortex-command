---
schema_version: "1"
uuid: ff0c5545-2ada-49f7-aec6-a39e843f1e0b
title: Parity test splits frontmatter on a naive byte split, so a comment containing three dashes fails elsewhere
status: complete
priority: low
type: bug
created: 2026-07-16
updated: 2026-07-20
tags: ['tests', 'config', 'parity']
areas: ['tests']
---
## Why

Two definitions of "frontmatter" coexist for the same file and diverge on ordinary content. `tests/test_lifecycle_config_parity.py` slices the region with a naive byte split on the delimiter sequence — matching those bytes anywhere, including inside a comment — while the production reader `cortex_command/lifecycle_config.py`'s `_extract_frontmatter_text` matches only a line that *is* the delimiter after stripping. The test's docstring frames the divergence as deliberate CRLF sensitivity, and for line endings it is; the byte-anywhere behavior is broader than that rationale and is pinned by nothing.

The trap is that it fails misleadingly. Verified during lifecycle 380: injecting a triple-dash into a template comment truncated the compared region from 1752 to 560 bytes, and the resulting failure named `missing required option line(s): ['# backend: jira', 'harden in #318']` — an error pointing at the `backlog:` backend block, with no hint that a comment elsewhere in the file caused it. Byte-parity still passed, because both copies truncate identically, so the one assertion that would localise the fault stays green. Lifecycle 380 avoided this by pinning a "no triple-dash in any hint" constraint into its plan and using an em-dash, which is a workaround at the authoring layer for a defect at the parsing layer.

## Role

After this lands, the two frontmatter definitions agree on where the region ends, or the divergence is explicit, pinned, and named where an author would see it. A comment that happens to contain three dashes either parses correctly or fails with a message naming the real cause. No future ticket has to carry a hand-written constraint telling authors which characters the test cannot survive.

## Integration

Touches the parity test's region extractor and the production extractor it deliberately bypasses, plus the new dormancy pin, which consumes the production extractor for the same files — so the two tests currently disagree about where a region ends and would report different faults for the same malformed template. Any change must preserve what the bypass was built for: catching CRLF and trailing-newline drift that the tolerant production reader normalizes away, and refusing a vacuous pass when extraction returns empty for both copies.

## Edges

- The CRLF sensitivity is deliberate and must survive — the test exists partly to catch drift the production reader forgives.
- The convergent-loss sentinel must keep failing when both copies lose an option line simultaneously.
- Delimiter-line matching alone would still leave a stray delimiter *line* inside a comment ambiguous; that is a narrower case and may be acceptable.

## Touch points

- `tests/test_lifecycle_config_parity.py` — `_frontmatter_region`'s naive byte split; the docstring's CRLF rationale; `_REQUIRED_OPTION_LINES`, whose failure message misattributes the fault.
- `cortex_command/lifecycle_config.py` — `_extract_frontmatter_text`, the production line-match extractor.
- `tests/test_lifecycle_config_dormant_template.py` — the dormancy pin, which uses the production extractor over the same three files.
- `cortex/adr/0017-reconcile-and-gate-lifecycle-config-sources.md` — the parity contract the test implements.
- `cortex/lifecycle/lifecycleconfig-template-ships-dormant-skip-specify/plan.md` — Task 1's "no triple-dash in any hint" constraint, the authoring-layer workaround this would retire.
