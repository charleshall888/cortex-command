---
feature: delete-post-shift-orphan-code-scripts-hooks-and-retire-paired-requirements
phase: research
tier: complex
criticality: medium
created: 2026-05-05
parent_backlog: 168-delete-post-shift-orphan-code-scripts-hooks-and-retire-paired-requirements
parent_epic: 165-repo-spring-cleaning-share-readiness-epic
---

# Research: Delete post-shift orphan code/scripts/hooks and retire paired requirements

## Epic Reference

This ticket is one child of epic [#165 — Repo spring cleaning: share-readiness for installer audience](backlog/165-repo-spring-cleaning-share-readiness-epic.md). The epic-level audit lives at [research/repo-spring-cleaning/research.md](research/repo-spring-cleaning/research.md) and covers junk inventory, doc inventory, README target shape, lifecycle/research archive disposition, and ratified decisions DR-1 through DR-4. This ticket implements only DR-4 (junk deletion + paired requirements retirement) and the F-6/F-7/F-8 dispositions; sibling tickets #166 and #169 cover docs/README cleanup and lifecycle/research archive sweep respectively.

## Codebase Analysis

### Files to delete (round-3 verified)

#### Confirmed-delete category (paths from backlog/168 §"Scope — confirmed deletes")

- **`plugins/cortex-overnight-integration/` (entire dir)** — contains only `tests/` (`test_overnight_start_run.py` + `test_overnight_schedule_run.py`); `.claude-plugin/marketplace.json:32-36` references only `cortex-overnight`; `justfile:458` BUILD_OUTPUT_PLUGINS lists `cortex-overnight` (no `-integration`); `grep -r "cortex-overnight-integration" --include="*.json" --include="*.md" --include="*.py"` → 16 matches all in `research/`/`backlog/`/`lifecycle/archive/` (historical only, no active code/config). Round-3 surprise: no `.claude-plugin/` dir inside the integration dir — never fully materialized as a plugin.
- **`scripts/sweep-skill-namespace.py`** — header "One-shot helper … for ticket 122 (R8)" [`scripts/sweep-skill-namespace.py:2`]; `grep -r "sweep-skill-namespace" --include="*.py" --include="*.sh" --include="justfile" --include="*.json"` → 0 matches in active code; appears only in `lifecycle/archive/`.
- **`scripts/verify-skill-namespace.py` + `scripts/verify-skill-namespace.carve-outs.txt`** — script verifies completed migration; `grep` → 0 active-code matches; carve-outs file's only consumer is the script itself at line ~75 (argument-parser default).
- **`scripts/generate-registry.py`** — generates `skills/registry.json`; `ls skills/registry.json` → file does not exist; `grep` → 0 active-code consumers; `.gitignore:20` lists the (never-generated) output as ignored.
- **`scripts/migrate-namespace.py`** — header "for ticket 120 to prepare … cortex-interactive plugin" [`scripts/migrate-namespace.py:2`]; sole consumer is `tests/test_migrate_namespace.py:29` (`SCRIPT_PATH = REPO_ROOT / "scripts" / "migrate-namespace.py"`).
- **`tests/test_migrate_namespace.py` + `tests/fixtures/migrate_namespace/` (8 files)** — pytest collects via `pyproject.toml:40` testpaths (`tests/` listed). Tests only `migrate-namespace.py` — orphans the test suite if hook is deleted alone.
- **`.gitignore:20` (`skills/registry.json` line)** — paired cleanup for `generate-registry.py` deletion. Surrounding context (lines 19–21):
  ```
  # Auto-generated skill registry
  skills/registry.json
  ```
  Recommend removing both lines (the comment becomes dead with the entry).

#### DR-4 hooks category

- **`claude/hooks/cortex-output-filter.sh`** — 207-line bash, reads `output-filters.conf`. NOT_FOUND in any in-repo `hooks.json` (searched `cortex_command/init/`, `plugins/*/`); NOT_FOUND in any `settings*.json` in repo. User-global `~/.claude/settings.json` is outside sandbox visibility — the CHANGELOG advisory addresses this risk surface.
- **`claude/hooks/output-filters.conf`** — 62 lines; sole active consumers: `cortex-output-filter.sh:28` (GLOBAL_CONF) and `tests/test_output_filter.sh:100,101` (test fixture).
- **`claude/hooks/cortex-sync-permissions.py`** — 182 lines; SessionStart hook merging user-global perms into project-local; NOT_FOUND in any active `hooks.json` or `settings*.json` in repo.
- **`claude/hooks/bell.ps1`** — Windows-only PowerShell helper (55 lines); referenced descriptively at `docs/agentic-layer.md:216` ("Flash the WezTerm screen … (Windows)") — not a deploy directive. NOT_FOUND in any active deploy mechanism.
- **`requirements/project.md:36`** — Context efficiency QA. Exact current text:
  ```
  - **Context efficiency**: Deterministic preprocessing hooks filter verbose tool output (test runners, build tools) before it enters the context window. Configured via pattern files (`output-filters.conf`) at global and per-project levels. Filtering is substring-based grep, not model judgment — no token cost for the filtering itself.
  ```
  Round-3 verdict: **mechanism-bound, not generic** — explicitly names `output-filters.conf`. Per DR-4 = AND retirement, this line must change atomically with hook deletion.
- **Paired tests:**
  - **`tests/test_output_filter.sh`** — 372-line bash test suite (sections a–j); runs via `bash tests/test_hooks.sh` in justfile `test-hooks` recipe (NOT pytest-collected).
  - **`tests/test_hooks.sh:308-380`** — `cortex-sync-permissions.py tests` block (73 lines, 4 test cases: no-local-settings / local-no-permissions-key / merge-fresh / already-synced).
  - **`tests/fixtures/hooks/sync-permissions/`** — 2 fixture files (`no-local-settings.json`, `local-no-permissions-key.json`); only consumer is `tests/test_hooks.sh:312,318,333`.

#### Investigate-then-decide category (round-3 evidence)

- **`bin/cortex-validate-spec` + `justfile:326-327` validate-spec recipe** — script not in any SKILL.md/hook/doc. `grep -r "validate-spec"` → only the recipe itself. Recipe NOT referenced from any documented workflow. Pairing constraint per backlog/168:70 — script delete REQUIRES recipe delete in same commit.
- **`landing-page/`** — 3 files (`prompt-1-foundation.md`, `prompt-2-pipeline.md`, `README.md`); `grep -r "landing-page" *.md *.json justfile *.toml *.sh *.py` excluding `lifecycle/`/`research/`/`retros/` → 0 matches. Pure content-policy decision; no code coupling.

#### Round-2 config-hygiene category (round-3 evidence)

- **`cortex_command/overnight/sync-allowlist.conf:36`** — exact line: `lifecycle/morning-report.md`. Documented as dead in backlog #129 (status: complete). NOT_FOUND for any active consumer; safe to delete.
- **`.gitignore:53` (`debug/test-*/`)** — `find . -type d -path "*/debug/test-*"` → 0 matches; safe to delete.
- **`.gitignore:64` (`ui-check-results/`)** — NOT_FOUND for any consumer; `find . -type d -name "ui-check-results"` → 0 matches; safe to delete.
- **`.mcp.json` `playwright` entry** — current `.mcp.json:3-6`:
  ```json
  {
    "mcpServers": {
      "playwright": {
        "command": "npx",
        "args": ["@playwright/mcp@0.0.70", "--headless"]
      }
    }
  }
  ```
  `.claude/settings.local.json:3` disables it; `grep -r "playwright"` excluding lifecycle/research → 0 active consumers. Round-3 verdict: orphan; recommend deletion.
- **`pyproject.toml:40` testpaths** — current value:
  ```python
  testpaths = ["tests", "cortex_command/dashboard/tests", "cortex_command/pipeline/tests", "cortex_command/overnight/tests", "cortex_command/init/tests", "cortex_command/backlog/tests"]
  ```
  Round-3 finding: `cortex_command/tests/__init__.py` exists with at least one real test (`test_install_guard_relocation.py`); pytest currently collects it incidentally via package-mode. Adding `cortex_command/tests` makes the listing symmetric with the 5 sibling component-level dirs already enumerated.

### Files to modify (verified)

- `requirements/project.md:36` — retire/reword per DR-4 (see Tradeoffs Decision 2 for option matrix).
- `.gitignore:20` — delete `skills/registry.json` line; consider deleting line 19 comment too.
- `.gitignore:53` — delete `debug/test-*/` line (no matches in tree).
- `.gitignore:64` — delete `ui-check-results/` line (no matches).
- `.mcp.json:3-6` — delete `playwright` entry (no consumers).
- `pyproject.toml:40` — add `cortex_command/tests` to testpaths array.
- `cortex_command/overnight/sync-allowlist.conf:36` — delete `lifecycle/morning-report.md` line.
- `CHANGELOG.md` (`[Unreleased]` section) — add `### Removed` advisory entries for deleted hooks with the user-global grep advisory inline (per Tradeoffs Decision 5 recommended Option A).
- `justfile:326-327` — delete `validate-spec` recipe IF Decision 3 = Option B (delete script).
- `bin/.parity-exceptions.md` — add `cortex-validate-spec` row IF Decision 3 = Option A (keep+allowlist).
- `docs/agentic-layer.md:216` — remove the descriptive `bell.ps1` line if hook is deleted (consistency, not blocking).

### Paired-deletion invariants (must hold within their commit)

1. `bin/cortex-validate-spec` deletion ↔ `justfile:326-327` validate-spec recipe deletion (same commit, or `just validate-spec` becomes a recipe-error).
2. `scripts/migrate-namespace.py` deletion ↔ `tests/test_migrate_namespace.py` + `tests/fixtures/migrate_namespace/` deletion (same commit, or pytest collection breaks).
3. `scripts/generate-registry.py` deletion ↔ `.gitignore:20` `skills/registry.json` line deletion (same commit, or .gitignore comment becomes dead).
4. `claude/hooks/cortex-sync-permissions.py` deletion ↔ `tests/test_hooks.sh:308-380` block + `tests/fixtures/hooks/sync-permissions/` deletion (same commit, or test_hooks.sh fails).
5. `claude/hooks/cortex-output-filter.sh` + `claude/hooks/output-filters.conf` deletion ↔ `tests/test_output_filter.sh` deletion (same commit, or hook tests fail).
6. **DR-4 atomicity**: `claude/hooks/cortex-output-filter.sh` + `claude/hooks/output-filters.conf` deletion ↔ `requirements/project.md:36` retirement (same commit per parent epic DR-4 ratified decision; mixed-state forbidden).
7. `claude/hooks/bell.ps1` deletion ↔ `docs/agentic-layer.md:216` line removal (same commit; consistency only — descriptive reference, non-blocking if missed).

### Existing patterns (apply at implement time)

- **Commit conventions** (CLAUDE.md): imperative mood, capitalized, no trailing period, ≤72 char subject; created via `/cortex-core:commit` skill.
- **Bin parity allowlist schema** (`bin/.parity-exceptions.md`): markdown table with columns `script | category | rationale | lifecycle_id | added_date`. Categories closed-enum: `maintainer-only-tool | library-internal | deprecated-pending-removal`. Rationale ≥30 chars after trim; forbidden literals (case-insensitive): `internal | misc | tbd | n/a | pending | temporary`. Precedent for maintainer-only-tool: `cortex-archive-sample-select` row at `bin/.parity-exceptions.md:19`.
- **CHANGELOG style** (Keep-a-Changelog format per `CHANGELOG.md:5`): `[Unreleased]` and dated tag sections; `### Added | ### Changed | ### Removed` subsections; entries are bullet-points with bold identifiers. Existing v0.1.0 `### Removed` entries (lines 35–40) demonstrate inline-prose advisory style (e.g., "Removed: `cortex_command/cli.py:_resolve_cortex_root()` and all `CORTEX_COMMAND_ROOT` consumers in `cli.py` and `install_guard.py`").

## Web Research

### Claude Code missing-hook behavior

Authoritative finding: **warn-and-continue.** Per the Hooks reference at https://code.claude.com/docs/en/hooks, "for most hook events, only exit code 2 blocks the action," and "any other exit code is a non-blocking error … the transcript shows a `<hook name> hook error` notice followed by the first line of stderr… Execution continues and the full stderr is written to the debug log." A missing hook script returns exit 127 (`/bin/sh: <path>: not found`), which falls under the "any other exit code" non-blocking branch. Empirical confirmation: anthropics/claude-code#5648 reproduces exit 127 on a missing hook command and shows session continuation.

Per-hook-type differential: docs language is "for most hook events" — implying not all. PreToolUse uses exit 2 specifically to block; for a missing script (exit 127), behavior remains non-blocking even on PreToolUse. Confidence: high for SessionStart/PostToolUse/Stop; medium for PreToolUse (no direct repro found).

### Hook-framework cleanup patterns (industry)

- **pre-commit framework**: missing hook ids fail loudly at install/run time; cleanup convention is to remove stale `repos:` entry from `.pre-commit-config.yaml` (sources: https://stefaniemolin.com/articles/devx/pre-commit/troubleshooting-guide/, https://github.com/pre-commit/pre-commit/issues/577).
- **Husky**: missing `.husky/<hook>` file means no hook to run — silent. Non-executable hook is "ignored with a warning" (https://github.com/typicode/husky/issues/1177, https://typicode.github.io/husky/troubleshoot.html).
- **Lefthook**: missing referenced script reported when hook fires but does not break the repo.

Prevailing convention: none of these tools advertise "you must clean up references after retiring a mechanism" as a release-note advisory. They fail-soft (Husky/Lefthook) or fail-loud-but-recoverable (pre-commit). Community-standard cleanup guidance is at the *config* layer (remove stale entry), not at the *script-on-disk* layer.

### Claude Code plugin marketplace stale-entry behavior

Mixed: cosmetic vs fatal. anthropics/claude-code#9431 ("Plugin source missing error on every startup with marketplace plugins") shows that when cached `plugin.json` lacks a field that `marketplace.json` references, Claude Code logs `[ERROR] Error: Plugin source missing` but plugins still load — purely cosmetic. anthropics/claude-code#33068 / #33739 show that an *unrecognized source type* in `marketplace.json` fails the entire marketplace's validation. Inference (marked): "referenced plugin not on disk" is closer to source-missing (cosmetic) than schema-invalid (fatal). Confidence: medium.

### Risk-surface verdict

The CHANGELOG advisory is **precautionary-only, not load-bearing.** Claude Code's documented and observed behavior for a missing hook script path is non-blocking; the maintainer's personal `~/.claude/settings.json` referencing now-deleted `claude/hooks/` paths will produce noisy `<hook name> hook error` lines per affected event firing, but no session-breaking failure. Industry convention does not treat stale script references as fatal. Therefore the advisory should be framed as a quality-of-life heads-up (clean up local settings to silence transcript noise) rather than as a critical migration step.

Sources: [Hooks reference](https://code.claude.com/docs/en/hooks), [#5648](https://github.com/anthropics/claude-code/issues/5648), [#9431](https://github.com/anthropics/claude-code/issues/9431), [#33068](https://github.com/anthropics/claude-code/issues/33068), [husky#1177](https://github.com/typicode/husky/issues/1177), [pre-commit#577](https://github.com/pre-commit/pre-commit/issues/577).

## Requirements & Constraints

### requirements/project.md:36 — Context efficiency QA

Mechanism-bound (not generic) — explicitly names `output-filters.conf`. The QA is not just "filter output" but specifically pegged to a file-based pattern config. This rules out a no-edit retire-the-hook-but-keep-the-line path; some change at line 36 is mandatory if the hook is deleted. Implications:
- Option (a) preserve-and-reword: feasible; drop the parenthetical mechanism reference, keep the QA's outcome-statement.
- Option (b) cut-entirely: feasible; no other QA depends on context-efficiency conceptually.
- Option (c) replace-mechanism: feasible only if a replacement mechanism exists or is named (none currently does).

### requirements/project.md:27 — SKILL.md-to-bin parity enforcement

> `bin/cortex-*` scripts must be wired through an in-scope SKILL.md / requirements / docs / hooks / justfile / tests reference (see `bin/cortex-check-parity` for the static gate). Drift between deployed scripts and references is a pre-commit-blocking failure mode. Allowlist exceptions live at `bin/.parity-exceptions.md` with closed-enum categories and ≥30-char rationales.

Note that **justfile** is on the allowed reference list — `bin/cortex-validate-spec`'s justfile-only wiring is parity-compliant today; the investigate-then-decide is about whether the recipe itself is dead, not about parity enforcement per se.

### requirements/project.md:35 — Defense-in-depth for permissions

> For sandbox-excluded commands (git, gh, WebFetch), the permission allow/deny list is the sole enforcement layer; keep global allows read-only and let write operations fall through to prompt.

Relevant constraint: deletion of repo-checked-in hook code does NOT remove user-global wired hooks; the maintainer must remove bindings from their personal `~/.claude/settings.json` manually. Per this requirement, no autopatch into user-global is permissible from inside the sandbox.

### Parent epic #165 DR-4 (research/repo-spring-cleaning/research.md DR-4)

> **Recommendation**: A — but only with parallel retirement of the requirements line. `requirements/project.md:36` declares `output-filters.conf` as project-level config under the "Context efficiency" quality attribute. Deleting the implementation without retiring this line creates spec/code drift (caught in critical review). The implementing ticket MUST either (i) retire the `output-filters.conf` mention in `requirements/project.md:36` in the same commit, OR (ii) keep `cortex-output-filter.sh` + `output-filters.conf` and only delete `cortex-sync-permissions.py`.

Operative interpretation per the lifecycle's clarify-critic alignment finding (F8): the AND retirement (path i) is the intended path. The OR phrasing in the child ticket is treated as imprecise; we proceed with path (i).

### Parent epic #165 #168 line item (backlog/165:30)

> **#168**: Code/script/hook deletion. Remove stale `plugins/cortex-overnight-integration/`, completed-migration scripts under `scripts/`, post-`cortex setup`-retirement hooks (`cortex-output-filter.sh`, `cortex-sync-permissions.py`, `setup-github-pat.sh`, `bell.ps1`). Includes parallel retirement of `requirements/project.md:36` (`output-filters.conf` mention) to prevent spec/code drift.

Note: epic mentions `setup-github-pat.sh` but child ticket round-2 verified that file is already deleted (not in scope today). Otherwise epic and child agree on hook list.

### Parent epic open questions deferred to lifecycle (backlog/165:42-48)

1. `landing-page/` disposition (keep/move/delete) — child #168 (this ticket).
2. `bin/cortex-validate-spec` keep-and-allowlist vs delete — child #168.
3. `cortex dashboard` verb policy — child #166 (out of scope for this ticket).

### CLAUDE.md project-level

- **Commit conventions** (lines 38–48): imperative, capitalized, no trailing period, ≤72 chars; created via `/cortex-core:commit`.
- **MUST-escalation policy** (lines 52–60): adding new MUST/CRITICAL language requires a commit-body or PR-description link to one of three evidence artifacts (events.log F-row, retros entry, transcript URL/excerpt). The DR-4 "atomic retirement" requirement is pre-existing-grandfathered (rationale: caught in critical review during discovery), not new MUST language being introduced by this ticket.
- **CLAUDE.md 100-line cap** (line 68): currently at 68 lines; cleanup-related policy edits are within budget.

### Other requirements files

`multi-agent.md`, `observability.md`, `pipeline.md`, `remote-access.md`: no relevant constraints. `requirements/pipeline.md:130` references retired `claude/reference/output-floors.md` — separate cleanup (#148 N8 leftover), not in this ticket's scope.

### Architectural constraints applying

1. DR-4 atomicity (single-commit binding for hook+requirements retire).
2. Parity + recipe coupling (script delete ↔ recipe delete same commit).
3. Test coverage pairing (hook delete ↔ paired test delete same commit).
4. No autopatch into user-global (`~/.claude/settings.json`); CHANGELOG advisory only.
5. CLAUDE.md 100-line cap (currently 68; cleanup edits within budget).

### Scope boundaries

In scope: confirmed-deletes; DR-4 hooks + paired tests + paired requirements; investigate-then-decide (validate-spec, landing-page); round-2 config hygiene; CHANGELOG advisory.

Out of scope: README cleanup (#166); doc reorg (#166 consolidated, was #167); lifecycle/research archive sweep (#169); `requirements/pipeline.md:130` cleanup (#148 N8 leftover, separate work).

## Tradeoffs & Alternatives

### Decision 1: Commit granularity

- **Option A (one mega-commit, ~30+ paths)**: pros — single atomic landing, one `just test` run; cons — review surface enormous, mega-rollback for any single failing pairing, bisect blob.
- **Option B (per-category, 4 commits — confirmed-deletes / DR-4 / investigate-then-decide / round-2 hygiene)**: pros — bisect lands on category, each commit has coherent rationale and own evidence section in ticket scope, paired-deletion closures naturally fit per-category boundaries, CHANGELOG advisory pairs with DR-4 commit; cons — 4 `just test` runs, paired-deletion invariants must be preserved within each category.
- **Option C (per-pairing-invariant, ~6–8 commits)**: pros — maximum bisect granularity, each commit is "delete X + retire its paired test/requirement/recipe"; cons — uneven granularity (2-path vs 4-path pairings), CHANGELOG entry coupling awkward, ~6–8 `just test` runs.

**Recommended: Option B (per-category, 4 commits).** The ticket scope is already organized into exactly four categories at backlog/168 lines 29–79; per-category boundaries already enforce paired-deletion safety as long as each commit pulls in its full pairing closure. Bisect-friendliness highest under B with no extra invariant risk versus A. CHANGELOG advisory entry should land in the DR-4 commit specifically (where the user-global risk lives).

### Decision 2: requirements/project.md:36 retire-disposition (a/b/c) — SPEC-PHASE USER DECISION

- **(a) preserve QA, reword to drop `output-filters.conf` mechanism reference**: keeps Context efficiency as a stated QA, leaves a requirements home for future preprocessing work; con — produces aspirational requirement with no implementing mechanism (drift DR-4 was meant to prevent).
- **(b) cut the QA entirely**: cleanest alignment with current state (no in-repo deploy mechanism exists); con — loses institutional record that context efficiency was once a stated concern.
- **(c) name a replacement mechanism**: avoids drift AND information loss; con — forces future-architecture commitment now (violates "complexity must earn its place" per project.md:19).

### Decision 3: bin/cortex-validate-spec keep vs delete — SPEC-PHASE USER DECISION

- **A (keep + allowlist with `maintainer-only-tool` rationale ≥30 chars)**: script is functionally complete as a pre-orchestrator-review gate; allowlist precedent at `bin/.parity-exceptions.md:19` (`cortex-archive-sample-select`); ~1 line of allowlist edit. Con — no agent flow currently uses it.
- **B (delete script AND drop `justfile:326-327` recipe in same commit)**: zero residual maintenance; matches disposition pattern of other one-shot scripts in this ticket. Con — loses working spec-validation logic (heading structure, MoSCoW classification, acceptance-criteria format checks).

### Decision 4: landing-page/ disposition — SPEC-PHASE USER DECISION

- **A (keep at root)**: zero churn; per DR-2 reasoning, historical artifacts at root have low effort cost. Con — directly contradicts epic's installer-audience-primary thesis.
- **B (move to `docs/landing-page/`)**: removes from root installer-visible surface. Con — `docs/` is the installer-facing index; `docs/internals/` (DR-3) is for maintainer-internal docs but landing-page material isn't documentation either.
- **C (delete)**: removes the artifact category entirely. Con — irreversible loss of carefully-crafted prompts (specific aesthetic decisions, fonts, acceptance criteria, budget guidance per landing-page/README.md:13–28).

### Decision 5: CHANGELOG advisory placement

- **A (add to [Unreleased] CHANGELOG.md)**: matches existing Keep-a-Changelog convention; discoverability structurally good (anyone running `cortex upgrade` is in changelog-reading mode); pros over B/C strong.
- **B (separate `docs/upgrade-notes.md`)**: gives action-required advisories a dedicated home; con — discoverability collapses (no convention, no link from CLI).
- **C (skip)**: zero content to land; con — un-does round-2 mitigation; assumes maintainer remembers DR-4.

**Recommended: Option A (CHANGELOG.md `[Unreleased]` `### Removed` subsection).** Frame the advisory as part of the Removed prose, e.g. "Removed: `claude/hooks/cortex-output-filter.sh`, `claude/hooks/output-filters.conf`, `claude/hooks/cortex-sync-permissions.py`, `claude/hooks/bell.ps1`. Maintainers who installed these via the retired `cortex setup` flow should grep `~/.claude/settings.json` for these script names and remove the bindings; cortex no longer deploys them." Per Web research, missing hooks fail-open (warn-and-continue), so the advisory is precautionary, not migration-critical.

### Decision 6: pyproject.toml testpaths — operator-pick recommended Option A

- **A (add `cortex_command/tests`)**: explicit > implicit; symmetric with the 5 sibling component-level test dirs already enumerated; mechanically a one-line edit; current implicit-collection is the kind of brittle behavior that breaks silently when pytest config changes.
- **B (leave implicit)**: nothing currently broken; zero risk of breaking anything. Con — asymmetric with the rest of the array.
- **C (restructure into single `tests/` root)**: maximally navigable; con — massive blast radius (hundreds of test imports), out-of-scope for cleanup ticket.

**Recommended: Option A (operator-pick, non-controversial)** — natural alignment with the existing array's pattern; trivial mechanical edit.

## Open Questions

These resolve at Spec phase via user interview:

1. **requirements/project.md:36 disposition** — Decision 2: (a) preserve+reword, (b) cut entirely, or (c) name replacement mechanism? Default lean: (a) preserve+reword to drop the `output-filters.conf` mechanism reference while keeping the Context efficiency QA outcome statement.
2. **bin/cortex-validate-spec** — Decision 3: (A) keep + add to `bin/.parity-exceptions.md` with `maintainer-only-tool` rationale ≥30 chars, or (B) delete script AND `justfile:326-327` recipe in same commit?
3. **landing-page/** — Decision 4: (A) keep at root, (B) move to `docs/landing-page/`, or (C) delete?

## Considerations Addressed

- **Per parent epic #165 DR-4 AND retirement is operative path; OR phrasing in child ticket is imprecise** — Addressed: Requirements & Constraints section quotes DR-4 verbatim (research/repo-spring-cleaning/research.md DR-4 Recommendation A) confirming AND retirement; Codebase Analysis paired-deletion invariant #6 codifies single-commit atomicity; Tradeoffs Decision 1 recommends per-category commits with DR-4 atomicity preserved within its commit.
- **requirements/project.md:36 QA disposition options (a/b/c)** — Addressed: Tradeoffs Decision 2 evaluates all three options with strongest-pro / strongest-con framing; flagged as spec-phase user decision (no pre-pick); Requirements section confirms the QA is mechanism-bound (rules out no-edit path) and Decision 2 details which options are feasible.
- **Round-3 NOT_FOUND re-verification of confirmed-delete paths** — Addressed: Codebase Analysis "Files to delete (round-3 verified)" section ran fresh grep for every path with command + result count; surprise findings caught (no `.claude-plugin/` dir inside `cortex-overnight-integration/`; `setup-github-pat.sh` already absent so excluded from scope; `cortex_command/tests/__init__.py` exists with real tests).
- **Claude Code missing-hook behavior characterization** — Addressed: Web Research section established documented and empirically-observed behavior is warn-and-continue (exit 127 → "any other exit code" → non-blocking); CHANGELOG advisory verdict is precautionary-only, not load-bearing; advisory should be framed as quality-of-life heads-up.
- **Acceptance criteria coverage for all enumerated deliverables** — Addressed: Files-to-modify and Paired-deletion-invariants sections enumerate all deliverables (confirmed-deletes, DR-4 hooks + paired tests + paired requirements, investigate-then-decide options, round-2 config hygiene, CHANGELOG advisory, pyproject testpaths addition); spec phase will fold these into acceptance criteria.
- **Investigate-then-decide pairing invariants** — Addressed: paired-deletion invariant #1 codifies `bin/cortex-validate-spec` ↔ `justfile:326-327` recipe coupling; Tradeoffs Decision 3 surfaces the keep+allowlist option with the schema constraint quoted (`maintainer-only-tool` category, ≥30-char rationale, no forbidden literals). Allowlist precedent cited (`cortex-archive-sample-select` row).
