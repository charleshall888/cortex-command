---
schema_version: "1"
uuid: bd5b3079-63b0-4913-8abc-fdde00ec02ad
title: Single-source research skill fan-out prose into fanout reference
status: backlog
priority: medium
type: chore
tags: ['skill-value-scorecard']
areas: [skills]
discovery_source: cortex/research/skill-value-scorecard/report.html
created: 2026-07-02
updated: 2026-07-02
parent: "347"
---
## Why
The research skill body duplicates grid, floor, and roster content that fanout.md already owns canonically, and its inline copies carry multiplied cost because they ride into fan-out searcher prompts. The audit verified four MERGE_DEDUP and three coupled COMPRESS verdicts here — but with sharp placement preconditions a naive edit would break.

## Role
Fold the duplicated fan-out prose into fanout.md references (s7, s18, s4), make the fanout read unconditional where the inline floor and corner cases are deleted, and single-source the considerations hand-off contract into one canonical statement (s3 and s6 executed jointly).

## Integration
Verdict preconditions to re-validate at research time: the s18 fold must anchor after the considerations-file paragraph or the standalone-reads-nothing test slice extends past its boundary and fails; the s4 deletion needs a one-line upper-bound-not-quota rider retained, matching the condensed sibling in the discovery cluster; the s3/s6 merged statement must keep the read-and-substitute, no-injection, and do-not-halt phrasings because the handoff tests are file-wide phrasing-sensitive regexes; s13 keeps the resolve-model mechanism lines and cuts only the judgment-inherit rationale (realistic saving 50-70 tokens, less than the scorer estimate).

## Edges
- This skill was trimmed in June 2026 (302 reverted an over-trim of frontmatter; 334 relocated fanout.md) — do not touch the frontmatter description or re-cut anything 302 restored.
- Gate on the research handoff and standalone tests named in the verdicts.

## Touch points
- skills/research/SKILL.md
- skills/research/references/fanout.md
- plugins/cortex-core mirror (same commit)
- cortex/research/skill-value-scorecard/master_candidates.json (verdict source)