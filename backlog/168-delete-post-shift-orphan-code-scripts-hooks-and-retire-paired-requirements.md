---
schema_version: "1"
uuid: e4d5251e-3c4f-480c-a69e-f5865878750c
title: "Delete post-shift orphan code/scripts/hooks and retire paired requirements"
status: in_progress
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
session_id: 39045fc2-8919-47a6-b0b4-70f289390c08
lifecycle_phase: implement
lifecycle_slug: delete-post-shift-orphan-code-scripts-hooks-and-retire-paired-requirements
complexity: complex
criticality: medium
spec: lifecycle/delete-post-shift-orphan-code-scripts-hooks-and-retire-paired-requirements/spec.md
---

# Delete post-shift orphan code/scripts/hooks and retire paired requirements

## Context from discovery

`research/repo-spring-cleaning/research.md` junk inventory enumerates orphans across `plugins/`, `scripts/`, `claude/hooks/`, and `bin/` introduced by post-#117/#144/#147 distribution shifts. All have NOT_FOUND grep evidence for current consumers. DR-4 covers paired requirements retirement to prevent spec/code drift.

## Scope — confirmed deletes

| Path | Type | Evidence |
|---|---|---|
| `plugins/cortex-overnight-integration/` (entire directory) | stale rename leftover | Marketplace points at `cortex-overnight` [`.claude-plugin/marketplace.json:33`]; contains only `tests/` referencing a non-existent `server.py` at `plugins/cortex-overnight-integration/server.py` (round 2 corrected: tests are NOT byte-equivalent to `plugins/cortex-overnight/tests/` — they differ at L34/L42 path strings; the description "byte-equivalent dupes" was wrong but deletion is still correct) |
| `scripts/sweep-skill-namespace.py` | one-shot tool | Header: "One-shot helper … for ticket 122 (R8)" [`scripts/sweep-skill-namespace.py:2`]; NOT_FOUND across justfile/CI/skills/hooks/docs |
| `scripts/verify-skill-namespace.py` + `scripts/verify-skill-namespace.carve-outs.txt` | one-shot tool + data | Verifies completed migration; NOT_FOUND across justfile/CI/tests; carve-outs file's only consumer is the script itself [`scripts/verify-skill-namespace.py:381`] |
| `scripts/generate-registry.py` | one-shot tool | Generates `skills/registry.json` per docstring; output never landed (NOT_FOUND for `skills/registry.json`) |
| `scripts/migrate-namespace.py` | one-shot tool | Header: "ticket 120" (completed); only consumer is its own test [`tests/test_migrate_namespace.py`] |
| `tests/test_migrate_namespace.py` + `tests/fixtures/migrate_namespace/` | paired test+fixtures | Tests the deleted `migrate-namespace.py`. Round 2 verified pytest collects this via `pyproject.toml:[tool.pytest.ini_options].testpaths` — leaving it orphans the test suite |
| `.gitignore:20` (`skills/registry.json` line) | paired cleanup | Becomes dead when `scripts/generate-registry.py` is deleted; output artifact never existed in repo |

## Scope — DR-4 hooks (delete WITH parallel requirements retirement and paired test deletion)

DR-4 ratified Option A: delete the unwired post-`cortex setup`-retirement hooks. **Critical**: `requirements/project.md:36` declares `output-filters.conf` as project-level config under the "Context efficiency" quality attribute. The implementing ticket must either retire the requirements line in the same commit, or keep `cortex-output-filter.sh` + `output-filters.conf` and only delete `cortex-sync-permissions.py`.

| Path | Notes |
|---|---|
| `claude/hooks/cortex-output-filter.sh` | Was deployed by retired `cortex setup`; no current deploy mechanism |
| `claude/hooks/output-filters.conf` | Data file consumed only by `cortex-output-filter.sh` |
| `claude/hooks/cortex-sync-permissions.py` | Same status — was user-global via retired `cortex setup` |
| `claude/hooks/bell.ps1` | Manual-wire Windows-only helper; cortex-command is macOS-primary per `requirements/project.md` |

**Paired test deletions** (round 2 audit caught these — orphan tests will break `just test` if deletion is unpaired):

| Path | Notes |
|---|---|
| `tests/test_output_filter.sh` | Tests `claude/hooks/cortex-output-filter.sh` directly — 8+ hard references to deleted paths; entire file unrunnable post-DR-4 |
| `tests/test_hooks.sh:308-end-of-sync-block` | 8+ `cortex-sync-permissions.py` test cases under "cortex-sync-permissions.py tests" header |
| `tests/fixtures/hooks/sync-permissions/` | Fixture dir consumed only by the sync-permissions tests in `tests/test_hooks.sh` |

**Paired requirements retirement**: `requirements/project.md:36` "Context efficiency" line referencing `output-filters.conf` must update or retire if the hook is deleted.

**Paired user-global advisory** (round 2 surfaced): the maintainer's personal `~/.claude/settings.json` may still bind these hooks (legacy from retired `cortex setup` deploy). Add a CHANGELOG entry advising maintainers to grep their `~/.claude/settings.json` for `cortex-output-filter.sh`/`cortex-sync-permissions.py` and unbind. Auditor cannot read user-global from sandbox; the risk is documented, not autopatched.

**REMOVED — already deleted**: `claude/hooks/setup-github-pat.sh` is no longer in the tree (verified `ls` ENOENT). Was retired in `lifecycle/apply-post-113-audit-follow-ups-...` Task 10. The previous version of this ticket had it on the confirmed-delete list — corrected.

## Scope — investigate-then-decide (open questions surfaced by research)

These have ambiguous evidence; plan phase decides:

- **`bin/cortex-validate-spec` + `justfile:326-327` `validate-spec` recipe**: only consumer is the recipe; not in any SKILL.md/hook/doc; not in `bin/.parity-exceptions.md`. **Critical pairing** (round 2): if script is deleted, the recipe must also be removed in the same commit, or `just validate-spec` becomes a recipe-error. Decide: add script to allowlist with `maintainer-only-tool` rationale, OR delete script AND recipe together.
- **`landing-page/`** (3 files: `prompt-1-foundation.md`, `prompt-2-pipeline.md`, `README.md`): Claude Design landing-page prompt material; NOT_FOUND across code/build references. Decide: keep as historical artifact, move to `docs/landing-page/`, or delete.

## Scope — additional cleanups surfaced in round 2

- **`cortex_command/overnight/sync-allowlist.conf:36`**: dead-code allowlist entry for `lifecycle/sessions/*/morning-report.md`. Documented as dead in backlog #129 (status: complete) but the line was never removed. Single-line cleanup.
- **`.gitignore:53` (`debug/test-*/` glob)**: stale glob; current `debug/` entries follow `YYYY-MM-DD-*` pattern, no current matches. Low-priority cleanup; investigate during plan and remove if confirmed dead.
- **`.gitignore:64` (`ui-check-results/`)**: NOT_FOUND for any current consumer. Low-priority; investigate and remove if dead.
- **`.mcp.json` `playwright` MCP server entry**: disabled by default in `.claude/settings.local.json:3`. If no consumer is identified, candidate for removal. Decide during plan.
- **Add `cortex_command/tests` to `pyproject.toml:[tool.pytest.ini_options].testpaths`**: currently picked up incidentally; explicit listing improves config hygiene (round 2 minor finding).

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
