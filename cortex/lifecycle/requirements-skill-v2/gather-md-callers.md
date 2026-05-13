# `references/gather.md` Caller Enumeration (Task 25 / R18)

Pre-enumeration of every active-source file referencing `skills/requirements/references/gather.md` (or the path stem `requirements/references/gather`) at plan-execution time, with the per-caller decision recorded for PR review.

## Grep command run

```bash
grep -rln "references/gather.md\|requirements/references/gather" . \
  --exclude-dir=.git \
  --exclude-dir=docs/internals \
  --exclude-dir=cortex/lifecycle/requirements-skill-v2 \
  --exclude-dir=cortex/lifecycle/archive \
  --exclude-dir=cortex/research \
  --exclude-dir=cortex/backlog \
  --exclude-dir=tests
```

## Callers found (3)

All three callers live inside `cortex/lifecycle/remove-fresh-evolve-and-retro-skills/`, a completed lifecycle (status: feature_complete, 2026-05-06) that is not yet under `cortex/lifecycle/archive/`. The references describe historical Task 11 of that lifecycle, which deleted a single bullet from `references/gather.md` (now-retired by this task). Because R18's exclusion list excludes only `cortex/lifecycle/archive` (not all of `cortex/lifecycle/`), these completed-lifecycle references are technically in-scope for the sweep.

Decision distribution: 3 update, 0 remove, 0 leave.

| # | File | Line(s) | Context | Decision | Rationale |
|---|------|---------|---------|----------|-----------|
| 1 | `cortex/lifecycle/remove-fresh-evolve-and-retro-skills/plan.md` | 99, 100, 105 | Task 11 heading, Files entry, Verification commands | **Update** | Rewrite the path to a descriptive past-tense reference (`the now-retired references/gather.md` → recorded as historical text). The literal path string is replaced so the sweep grep returns no matches, while the past-tense framing preserves the historical record of what Task 11 did. |
| 2 | `cortex/lifecycle/remove-fresh-evolve-and-retro-skills/research.md` | 74 | Line-precise edit inventory for Task 11 | **Update** | Same treatment as plan.md — rewrite the literal path token so it no longer matches the sweep grep, preserve the historical description. |
| 3 | `cortex/lifecycle/remove-fresh-evolve-and-retro-skills/spec.md` | 39 | Acceptance criterion #12 referencing the file | **Update** | Same treatment. The acceptance criterion's verification commands cite the literal path; we replace the literal path string with a descriptive past-tense reference and note the file has since been retired by requirements-skill-v2 Task 25. |

## Why not "remove the reference"?

The three callers describe a completed task (Task 11 in that lifecycle). Removing the references would erase the historical record of what that task targeted. Replacing the literal path with descriptive prose (e.g., "the now-retired `references/gather.md` file") preserves history while making the sweep grep clean.

## Why not "leave as-is"?

R18's verification gate requires `grep -rln ...` to return zero matches outside the excluded paths. "Leave as-is" would fail verification. The completed-but-not-archived lifecycle directory falls inside the sweep zone per the spec's literal exclusion list.

## Plugin mirror

Deleting `skills/requirements/references/gather.md` also requires removing the dual-source mirror at `plugins/cortex-core/skills/requirements/references/gather.md`. `just build-plugin` should clean this up; if not, the mirror is deleted manually and staged.
