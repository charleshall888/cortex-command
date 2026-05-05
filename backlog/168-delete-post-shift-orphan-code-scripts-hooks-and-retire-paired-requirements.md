---
schema_version: "1"
uuid: e4d5251e-3c4f-480c-a69e-f5865878750c
title: "Delete post-shift orphan code/scripts/hooks and retire paired requirements"
status: backlog
priority: medium
type: feature
tags: [repo-spring-cleaning, cleanup, hooks, scripts, plugins]
areas: []
created: 2026-05-05
updated: 2026-05-05
parent: "165"
blocks: []
blocked-by: []
discovery_source: research/repo-spring-cleaning/research.md
session_id: null
lifecycle_phase: null
lifecycle_slug: null
complexity: standard
criticality: medium
---

# Delete post-shift orphan code/scripts/hooks and retire paired requirements

## Context from discovery

`research/repo-spring-cleaning/research.md` junk inventory enumerates orphans across `plugins/`, `scripts/`, `claude/hooks/`, and `bin/` introduced by post-#117/#144/#147 distribution shifts. All have NOT_FOUND grep evidence for current consumers. DR-4 covers paired requirements retirement to prevent spec/code drift.

## Scope — confirmed deletes

| Path | Type | Evidence |
|---|---|---|
| `plugins/cortex-overnight-integration/` (entire directory) | stale rename leftover | Marketplace points at `cortex-overnight` [`.claude-plugin/marketplace.json:33`]; contains only byte-equivalent dupes of `plugins/cortex-overnight/tests/test_overnight_*.py` referencing a non-existent `server.py` |
| `scripts/sweep-skill-namespace.py` | one-shot tool | Header: "One-shot helper … for ticket 122 (R8)" [`scripts/sweep-skill-namespace.py:2`]; NOT_FOUND across justfile/CI/skills/hooks/docs |
| `scripts/verify-skill-namespace.py` + `scripts/verify-skill-namespace.carve-outs.txt` | one-shot tool + data | Verifies completed migration; NOT_FOUND across justfile/CI/tests; carve-outs file's only consumer is the script itself [`scripts/verify-skill-namespace.py:381`] |
| `scripts/generate-registry.py` | one-shot tool | Generates `skills/registry.json` per docstring; output never landed (NOT_FOUND for `skills/registry.json`) |
| `claude/hooks/setup-github-pat.sh` | manual-wire helper | `setup-github-pat` justfile recipe was removed; `grep -n setup-github-pat justfile` returns 0 hits — true orphan |

## Scope — DR-4 hooks (delete WITH parallel requirements retirement)

DR-4 ratified Option A: delete the unwired post-`cortex setup`-retirement hooks. **Critical**: `requirements/project.md:36` declares `output-filters.conf` as project-level config under the "Context efficiency" quality attribute. The implementing ticket must either retire the requirements line in the same commit, or keep `cortex-output-filter.sh` + `output-filters.conf` and only delete `cortex-sync-permissions.py`.

| Path | Notes |
|---|---|
| `claude/hooks/cortex-output-filter.sh` | Was deployed by retired `cortex setup`; no current deploy mechanism |
| `claude/hooks/output-filters.conf` | Data file consumed only by `cortex-output-filter.sh` |
| `claude/hooks/cortex-sync-permissions.py` | Same status — was user-global via retired `cortex setup` |
| `claude/hooks/bell.ps1` | Manual-wire Windows-only helper; cortex-command is macOS-primary per `requirements/project.md` |

Paired retirement: `requirements/project.md:36` "Context efficiency" line referencing `output-filters.conf` must update or retire if the hook is deleted.

## Scope — investigate-then-decide (open questions surfaced by research)

These have ambiguous evidence; plan phase decides:

- **`scripts/migrate-namespace.py` + `tests/test_migrate_namespace.py`**: header indicates one-shot for ticket 120 (completed); sole consumer is its own test. Likely DELETE but confirm no callers in archived lifecycle artifacts.
- **`bin/cortex-validate-spec`**: only consumer is `justfile:327` recipe `validate-spec`; not in any SKILL.md/hook/doc; not in `bin/.parity-exceptions.md`. Decide: add to allowlist with `maintainer-only-tool` rationale OR delete script + recipe.
- **`landing-page/`** (3 files: `prompt-1-foundation.md`, `prompt-2-pipeline.md`, `README.md`): Claude Design landing-page prompt material; NOT_FOUND across code/build references. Decide: keep as historical artifact, move to `docs/landing-page/`, or delete.

## Out of scope

- README cleanup — child #166.
- Doc reorg — child #167.
- Lifecycle/research archive sweep — child #169.

## Acceptance signals

- Confirmed-delete paths absent from working tree.
- `requirements/project.md:36` either retired or hook implementation retained (no spec/code drift).
- Three investigate-then-decide items have a documented disposition decision in the lifecycle plan or implementation evidence.

## Research

See `research/repo-spring-cleaning/research.md` — junk inventory table, DR-4 (`claude/hooks/` resolution), F-6, F-7, F-8.
