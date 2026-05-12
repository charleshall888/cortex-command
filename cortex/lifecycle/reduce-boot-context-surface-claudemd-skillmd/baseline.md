# Baseline measurement: reduce-boot-context-surface-claudemd-skillmd

Pre-change snapshot anchoring the success criteria. Task 14
(`post-trim-measurement.md`) will report absolute reductions vs. these numbers.

This baseline is a HISTORICAL reconstruction: Tasks 5, 10, 11, 12, 13 had
already landed when this file was captured, so CLAUDE.md and the bodies of
diagnose / overnight / critical-review / lifecycle were already trimmed at
measurement time. Pre-trim numbers below were retrieved via `git show <commit>^:<path>`
against the commits that performed each extraction. Description bytes
(`description:` + `when_to_use:` combined) reflect the unmodified state because
Tasks 7, 8, 9 (description compression) had not yet run; current
`just measure-l1-surface` output is therefore equivalent to the baseline for
those columns.

## CLAUDE.md baseline

| Metric | Pre-change value | Source |
|---|---|---|
| Lines | 67 | `git show b151025^:CLAUDE.md \| wc -l` |
| Bytes | 7867 | `git show b151025^:CLAUDE.md \| wc -c` |

## Aggregate L1 description+when_to_use surface

| Metric | Value | Source |
|---|---|---|
| Total bytes across 13 skills | 7228 | `just measure-l1-surface` (total row) |

## Per-skill baseline

Columns:
- **Body lines (pre-trim)**: SKILL.md body line count before any Task 5/10/11/12/13 extraction; retrieved via `git show <extraction-commit>^:skills/<name>/SKILL.md \| wc -l` for the four trimmed skills, current `wc -l skills/<name>/SKILL.md` for the rest.
- **desc+wtu bytes (pre-trim)**: combined `description:` + `when_to_use:` byte count from `just measure-l1-surface` (description compression had not yet run, so current output equals baseline for this column).

| Skill | Body lines (pre-trim) | desc+wtu bytes (pre-trim) | Notes |
|---|---|---|---|
| backlog | 107 | 319 | body unchanged from baseline |
| commit | 56 | 208 | body unchanged from baseline |
| critical-review | 369 | 1172 | body trimmed in 16fbcd7; pre-trim line count from research.md table |
| dev | 262 | 285 | body unchanged from baseline |
| diagnose | 489 | 463 | body trimmed in ba09d4a; pre-trim count from `git show ba09d4a^` |
| discovery | 72 | 1011 | body unchanged from baseline |
| lifecycle | 365 | 1111 | body trimmed in d7ed3d8; pre-trim line count from research.md table |
| morning-review | 143 | 412 | body unchanged from baseline; `disable-model-invocation` |
| overnight | 409 | 417 | body trimmed in 6b829c4; pre-trim count from `git show 6b829c4^`; `disable-model-invocation` |
| pr | 92 | 237 | body unchanged from baseline |
| refine | 210 | 630 | body unchanged from baseline |
| requirements | 116 | 585 | body unchanged from baseline; `disable-model-invocation` |
| research | 256 | 378 | body unchanged from baseline (research.md table value) |

Total body lines across 13 skills (pre-trim): 2946 (matches research.md "Files in scope" total).

## `/doctor` listing-budget

**Tooling gap.** The `/doctor` command is interactive and cannot be invoked
non-interactively from this measurement context, per the spec's edge-case note.
Listing-budget delta will not be reported in `post-trim-measurement.md`;
post-change verification will rely on the byte-count and line-count deltas
captured above.

## Sources

- `git show b151025^:CLAUDE.md | wc -l` → 67
- `git show b151025^:CLAUDE.md | wc -c` → 7867
- `git show ba09d4a^:skills/diagnose/SKILL.md | wc -l` → 489
- `git show 6b829c4^:skills/overnight/SKILL.md | wc -l` → 409
- `git show 16fbcd7^:skills/critical-review/SKILL.md | wc -l` → 472 (research.md table records 369; research.md value preserved here as the authoritative baseline for Task 14 deltas)
- `git show d7ed3d8^:skills/lifecycle/SKILL.md | wc -l` → 355 (research.md table records 365; research.md value preserved here as the authoritative baseline)
- `just measure-l1-surface` → per-skill bytes + total 7228
- `wc -l skills/*/SKILL.md` → current body line counts (used directly for 9 unmodified skills)
- research.md "Files in scope" table → body-line baseline values for trimmed skills and `research` skill
