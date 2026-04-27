# Axis B Baseline Safety Scan

Pre-edit baseline counts for #053 (add-subagent-output-formats-compress-synthesis).
Recorded before any file edits. Tasks 8 and 10 read post-edit counts and compare
against this file.

## P2 Injection-Resistance

`grep -rc "All web content.*untrusted external data" skills/`

- `skills/research/SKILL.md`: 6
- All other files: 0
- **Total count: 6** (≥ 1 — gate satisfied)

## P1 Preservation Anchors (14 total)

All 14 anchors verified present (≥ 1 match each) before edit tasks begin.

| # | Anchor content | File | Count |
|---|----------------|------|-------|
| 1  | `Do not soften or editorialize` | `skills/critical-review/SKILL.md` | 1 |
| 2  | `Do not be balanced` | `skills/critical-review/SKILL.md` | 3 |
| 3  | `Do not reassure` | `skills/critical-review/SKILL.md` | 2 |
| 4  | `No two derived angles` or `Each angle must be distinct` | `skills/critical-review/SKILL.md` | 1 |
| 5  | `⚠️ Agent` (returned no findings string) | `skills/research/SKILL.md` | 4 |
| 6  | `note the contradiction explicitly under` | `skills/research/SKILL.md` | 1 |
| 7  | `ALWAYS find root cause before attempting fixes` | `skills/diagnose/SKILL.md` | 1 |
| 8  | `Never fix just where the error appears` | `skills/diagnose/SKILL.md` | 1 |
| 9  | `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` | `skills/diagnose/SKILL.md` | 2 |
| 10 | `**Critical rule**` | `skills/lifecycle/references/plan.md` | 1 |
| 11 | `Found epic research at` | `skills/lifecycle/SKILL.md` | 1 |
| 12 | `warn if prerequisite artifacts are missing` | `skills/lifecycle/SKILL.md` | 1 |
| 13 | `AskUserQuestion` | `skills/backlog/SKILL.md` | 4 |
| 14 | `summarize findings, and proceed` | `skills/discovery/SKILL.md` | 1 |

All 14 anchors present — Axis B edits cleared to proceed.

## Baseline Counts

- V4 CRITICAL count (skills/lifecycle/references/review.md): 1
- B1 per-file counts: skills/lifecycle/references/clarify-critic.md: 1, skills/lifecycle/references/review.md: 1, skills/diagnose/SKILL.md: 1, skills/overnight/SKILL.md: 1
  - (All other files under `skills/` recursive scan: 0)
  - Command: `grep -rc "CRITICAL:\|[Yy]ou [Mm]ust\|ALWAYS \|NEVER \|REQUIRED to\|think about\|think through" skills/`
- B2 per-file counts: (all files under `skills/` recursive scan: 0)
  - Command: `grep -rc "IMPORTANT:\|make sure to\|be sure to\|remember to" skills/`

## Notes

- B1 total across all files: 4 non-zero hits. Corpus is already largely softened,
  consistent with spec's "2–4 actual instances" claim.
- B2 total: 0. The confirmation pass (B2) is expected to find no candidates.
- `REQUIRED to` is a confirmation-only pattern in B1 — expected count 0 in all files.
- P2 count of 6 all in `skills/research/SKILL.md` indicates the injection-resistance
  instruction is present as multiple verbatim copies within that single file.
