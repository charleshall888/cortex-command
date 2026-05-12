---
lifecycle_slug: relocate-cortex-command-artifacts-under-cortex-root
backlog_id: 202
parent_epic: 200
audience: implementer (single-user)
created: 2026-05-12
shape: focused addendum to discovery
foundation: research/consolidate-artifacts-under-cortex-root/research.md
---

# Research: relocate cortex-command artifacts under cortex/ root

> Focused addendum to the discovery research at `research/consolidate-artifacts-under-cortex-root/research.md` (376 lines, 10 decision records, critical-review survived). This document does NOT re-derive the design — DR-1 through DR-10 are the binding decisions. It closes the nine specific Apply'd findings the clarify-critic surfaced and stages the spec/plan with a verified touchpoint inventory plus a self-reference operational plan.

## Scope anchor

Relocate cortex-command's eight tool-managed paths (`lifecycle/`, `research/`, `retros/`, `backlog/`, `requirements/`, `lifecycle.config.md`, `.cortex-init`, `debug/`) from repo root into a single visible `cortex/` umbrella directory in one atomic commit. Switch `cortex init`'s sandbox grant to umbrella `cortex/` (DR-5). Tag a major-version bump (DR-9). Foundation #201 (upward-walking project-root detection at `cortex_command/common.py:55-103`) is shipped.

## Closure of clarify-critic Apply'd findings

### 1. Touchpoint-inventory completeness for runner.py / dispatch.py / sandbox_settings.py / pyproject.toml

DR-7 cites edits to `cortex_command/overnight/runner.py` and `cortex_command/pipeline/dispatch.py` as preflight-gate triggers. Discovery's per-file inventory did not list them. Direct read resolved:

- `cortex_command/overnight/runner.py:1804` — `repo_path / "lifecycle" / "pipeline-events.log"` literal. **Must edit** to `repo_path / "cortex" / "lifecycle" / "pipeline-events.log"`. New touchpoint, missed in discovery inventory.
- `cortex_command/overnight/runner.py:421,423` — `Path(worktree_path) / "backlog"` and `repo_path / "backlog"` literals. **Must edit** to `... / "cortex" / "backlog"`. New touchpoints.
- `cortex_command/pipeline/dispatch.py` — no top-level path literals. Lines 551, 553, 606 reference `lifecycle/sessions/<id>/...` only via the `LIFECYCLE_SESSION_ID` env var consumed by per-spawn temp-dir logic (no path-string composition). No edits required.
- `cortex_command/overnight/sandbox_settings.py` — no top-level path literals. Docstring at line 82 references `~/.cache/cortex/` (HOME-relative, unaffected). No edits required.
- `pyproject.toml` — entry-points are Python module paths (`cortex_command.backlog.update_item:main`); testpaths reference module-test directories (`cortex_command/backlog/tests`). Neither references the top-level filesystem `backlog/` directory under relocation. No edits required.

**DR-7 preflight-trigger claim**: was sourced from staged edits to runner.py / dispatch.py matching `bin/cortex-check-parity`'s sandbox-trigger regex. The runner.py edits above will trigger the gate. The dispatch.py / sandbox_settings.py / pyproject.toml claims were aspirational and do not match actual edits. **DR-7 remains valid** for runner.py alone — operational precondition (`fresh preflight against pre-relocation HEAD`) still applies.

### 2. Skill SKILL.md cross-refs (DR-2 trade-off)

DR-2's "every skill SKILL.md and cross-ref must rebase to `cortex/backlog/<id>.md`" framing turned out to be overstated. Direct grep counts:

- Hardcoded `backlog/[0-9]+` literals in `skills/*.md`: **1 site** (`skills/lifecycle/SKILL.md:59` — an example path in resolver-prose).
- Hardcoded `lifecycle/<feature>` paths in `skills/*.md`: ~60 sites across `skills/lifecycle/SKILL.md` and `skills/refine/SKILL.md`. Most are protocol prose like `lifecycle/{feature}/spec.md` — `{feature}` is a placeholder, but the `lifecycle/` prefix is literal and must become `cortex/lifecycle/`.

**Verdict**: skill-prose rebasing is real but bounded (one to two skill files; ~60 cosmetic line edits in two files, not "every skill"). Plugin mirrors at `plugins/cortex-core/skills/lifecycle/{SKILL.md,references/*}` regenerate automatically via the `just build-plugin` pre-commit pipeline — zero manual mirror edits per CLAUDE.md.

### 3. requirements/project.md sandbox-constraint edit

`requirements/project.md:28` reads: *"`cortex init` additively registers the repo's `lifecycle/` path in `~/.claude/settings.local.json`'s `sandbox.filesystem.allowWrite` array."*

DR-5 changes this contract to umbrella `cortex/` registration. The requirements text must update in the same commit. **New touchpoint** beyond the `git mv` of the file itself: the in-file string `lifecycle/` → `cortex/`, plus the surrounding sentence framing (single-narrow-path → single-umbrella-path).

Other requirements-doc edits implied:
- `requirements/project.md:31` (Sandbox preflight gate) mentions `cortex_command/overnight/sandbox_settings.py`, `cortex_command/pipeline/dispatch.py`, `cortex_command/overnight/runner.py`, `pyproject.toml` as preflight-trigger sources. No path-string change here — the file paths are Python module paths, not user-content paths.
- `requirements/project.md` Conditional Loading footer references `requirements/observability.md` etc. — these need updating once `requirements/` moves to `cortex/requirements/`.

### 4. claude/hooks/ audit (four scripts)

Direct grep on the four unaudited scripts:

| Script | Path-handling refs |
|---|---|
| `claude/hooks/cortex-worktree-create.sh` | Zero. Line 57 comment-only ("updatedPermissions research"). |
| `claude/hooks/cortex-worktree-remove.sh` | Zero. |
| `claude/hooks/cortex-skill-edit-advisor.sh` | Zero. |
| `claude/hooks/cortex-permission-audit-log.sh` | Zero. |

**Verdict**: all four are path-handling-free with respect to the relocation. No edits required. This question is fully closed — the open-question entry in research.md:372 can be retired.

### 5. #201 closure verification

`_resolve_user_project_root()` at `cortex_command/common.py:55-103` implements upward-walk detecting `lifecycle/` OR `backlog/` (line 89). All DR-10 callsite categories are wired:

- `cortex_command/common.py:55` — the function itself ✓
- `cortex_command/overnight/daytime_pipeline.py:29,63` — imports and calls `_resolve_user_project_root()` ✓ (literals at lines 181/220-243/391 still use `lifecycle/<feature>` and **belong to #202's migration**, not residual #201 work)
- `cortex_command/backlog/generate_index.py:24,95,97,303` — wired ✓
- `cortex_command/backlog/update_item.py:32,445` — wired ✓
- `cortex_command/backlog/create_item.py:29,163` — wired ✓
- `cortex_command/discovery.py` — **NOT wired through `_resolve_user_project_root`**; uses `_default_repo_root()` at line 62 which calls `git rev-parse --show-toplevel` directly. Treated as parallel-implementation rather than residual #201 wiring. `discovery.py:104,187,195` literals (`repo_root / "lifecycle"`, `repo_root / "research"`) still need to become `repo_root / "cortex" / "lifecycle"` etc., but that is #202 work.

**Verdict**: #201 is closed. The literals using `lifecycle/<feature>` at the wired callsites are explicitly #202's job to migrate.

**Critical implication for #202**: `_resolve_user_project_root()` currently walks for `lifecycle/` OR `backlog/` (line 89). Post-relocation, `lifecycle/` and `backlog/` no longer exist at repo root — they live at `cortex/lifecycle/` and `cortex/backlog/`. The detection predicate must change to walking for `cortex/` (single condition). This is the single most behaviorally load-bearing edit in the relocation. Failure to update this single line bricks every cortex CLI from inside a relocated repo.

### 6. retros/ disposition recommendation

State: `retros/archive/` contains 56 session-retro files dated 2026-04-02 → 2026-05-10. Zero Python references (`NOT_FOUND` in `cortex_command/`). Only `justfile:255,261` exclusion patterns reference it.

**Recommendation: relocate to `cortex/retros/`.** Rationale: (a) consistency with the umbrella scheme — one mental folder for everything cortex-managed; (b) deletion is irreversible (audit value of historical retros), and conflating relocation with deletion in the same commit invites accidental data loss if the relocation is reverted; (c) zero code references means relocation is a pure `git mv` with no follow-on edits. Justfile exclusion patterns (`justfile:255,261`) update to `cortex/retros/archive/...` in the same commit.

### 7. Self-reference relocator mitigation

`research/consolidate-artifacts-under-cortex-root/research.md:373` flags that the lifecycle directory doing the relocation work — currently `lifecycle/relocate-cortex-command-artifacts-under-cortex-root/` — is itself in scope for the `git mv` storm. The session executing the relocation appends to `lifecycle/sessions/<id>/events.log` and `lifecycle/<this-feature>/events.log` during the commit.

**Operational plan** (binding constraint for the spec):

1. Carry the lifecycle through phases (research, spec, plan, implement, review) using normal session writes to `lifecycle/relocate-cortex-command-artifacts-under-cortex-root/`.
2. **The relocation commit itself is executed from a fresh shell session that has neither `LIFECYCLE_SESSION_ID` nor an active overnight session.** Pre-conditions for that fresh session:
   - `cortex overnight status` reports zero live sessions (DR-7 hard precheck).
   - `echo $LIFECYCLE_SESSION_ID` returns empty (the session must not have been launched from a Claude Code conversation tied to this lifecycle).
   - All in-flight lifecycle phase work (including `clarify_critic` / `phase_transition` event writes for this very lifecycle) is committed to git before the relocation commit begins.
3. Order of operations inside the fresh shell:
   - Stage all working-tree changes (path-literal edits + state-file edits + doc edits): `git add -A`. Per DR-7 this is required — selective staging is unsafe because `core.hooksPath` routes pre-commit through `.githooks/pre-commit` and `bin/cortex-check-parity` reads working-copy state.
   - Run `git mv` for every relocated path in a separate phase (script-driven; see Migration runbook below).
   - Re-`git add -A` to capture the renames.
   - Commit. Pre-commit runs path-parity / preflight gates; fresh preflight against pre-relocation HEAD must have been produced beforehand.
4. **Post-commit**: run `cortex init --update` from the fresh shell to refresh `~/.claude/settings.local.json` sandbox grants to the umbrella `cortex/` path (DR-8).
5. **`/plugin update cortex-core`** before the next Claude Code session (DR-9 cutover).

**Self-write hazard for events.log**: between commit-stage and commit-finalize, no writer touches `lifecycle/<this-feature>/events.log`. Mitigation is procedural (point 2 above), not code-enforced. Acceptable for a single-user repo with explicit precheck; if multi-user becomes real, this needs a code-side guard (e.g., a `LIFECYCLE_SESSION_ID`-aware lock during cortex-core relocation).

### 8. Operational documentation lock-step edits

`docs/setup.md` and `docs/agentic-layer.md` describe literal post-init filesystem state (per research.md:374). CLAUDE.md (5 path references) does the same. These are not "batchable prose later" — they are part of the relocation contract.

Edits required in same commit:
- `docs/setup.md` — describe `cortex/` umbrella after `cortex init`, single sandbox-registration entry, optional gitignore-as-unit.
- `docs/agentic-layer.md` — update literal filesystem-layout descriptions and any post-init walkthrough screenshots/diff-snippets.
- `CLAUDE.md` — 5 path refs (verified by `grep -nE 'lifecycle/|research/|backlog/|requirements/|retros/' CLAUDE.md`). Update inline.
- README.md — update top-level layout description and any `cortex init` example output.
- CHANGELOG.md — major-version-bump entry per DR-9 with migration note.

### 9. cortex/README.md affordance

**Recommendation: ship `cortex/README.md` in cortex-command's own repo** explaining the umbrella's contents (one-paragraph each for lifecycle/, research/, backlog/, requirements/, retros/, debug/, .cortex-init, lifecycle.config.md). For installer-generated repos via `cortex init`, defer template authoring to a follow-up — current installer ships `lifecycle/README.md` and `backlog/README.md` separately; consolidating those into a single `cortex/README.md` template is straightforward but not blocking for #202.

## Updated touchpoint inventory (deltas vs discovery research)

The discovery research lists ~30 Python files and ~16 hook/bin sites. This addendum confirms or amends:

| Discovery line | Status | Note |
|---|---|---|
| `init/handler.py:125-153` | ✓ confirmed | Plus collapse from dual-registration to single umbrella per DR-5 |
| `init/scaffold.py:56-61` `_CONTENT_DECLINE_TARGETS` | ✓ confirmed | Update tuple to `("cortex",)` (single entry — directory presence implies a populated cortex repo) |
| `init/scaffold.py:49-52` `.cortex-init` constants | **NEW** | `.cortex-init` marker and `.cortex-init-backup/` directory move under `cortex/`; rename to e.g. `cortex/.init.json` is OUT OF SCOPE (cosmetic, deferrable per backlog item) — keep as `cortex/.cortex-init` for this commit |
| `init/settings_merge.py:65-66` | ✓ confirmed | Lockfile path is HOME-relative; unaffected |
| `overnight/state.py:321` central session_dir | ✓ confirmed | Single most load-bearing edit |
| `common.py:55-103` `_resolve_user_project_root` | ✓ confirmed | Line 89 predicate `(current / "lifecycle").is_dir() or (current / "backlog").is_dir()` becomes `(current / "cortex").is_dir()` — bricks CLIs from inside relocated repo otherwise |
| `common.py:50-51,77-80` error-message strings | **NEW** | Update `CortexProjectRootError` docstring + message to reference `cortex/` |
| `backlog/{generate_index,update_item,create_item}.py` | ✓ confirmed | All wired through `_resolve_user_project_root()` post-#201 |
| `overnight/runner.py:421,423,1804` | **NEW** | Missed in discovery inventory |
| `overnight/daytime_pipeline.py:181,220-243,391` | ✓ confirmed | Literals using `lifecycle.config.md` and `lifecycle/<feature>/...` paths |
| `overnight/report.py:272,276` | ✓ confirmed | `Path("lifecycle").glob(...)` |
| `overnight/backlog.py` `DEFAULT_BACKLOG_DIR` | ✓ confirmed | |
| `overnight/orchestrator.py` factory defaults | ✓ confirmed | |
| `overnight/cli_handler.py:58` | ✓ confirmed | reads `lifecycle.config.md` |
| `dashboard/{app,seed,poller,data}.py` ~15 sites | ✓ confirmed | |
| `discovery.py:62-74,104,187,195` | ✓ confirmed | Uses `git rev-parse --show-toplevel` not `_resolve_user_project_root`; literals at 104/187/195 need rebasing |
| `hooks/cortex-scan-lifecycle.sh` 8 line edits | ✓ confirmed | Lines 26, 50, 84, 114, 328, 349, 361, 381 |
| `claude/hooks/cortex-tool-failure-tracker.sh:42` | ✓ confirmed | |
| `claude/hooks/cortex-worktree-create.sh`, `cortex-worktree-remove.sh`, `cortex-skill-edit-advisor.sh`, `cortex-permission-audit-log.sh` | **AUDITED** | Zero path-handling. No edits required. |
| `.githooks/pre-commit:81` | ✓ confirmed | `requirements/*` → `cortex/requirements/*` |
| `bin/cortex-check-parity:75,112-113` | ✓ confirmed | Glob + `PREFLIGHT_PATH` constant |
| `bin/cortex-log-invocation:46` | ✓ confirmed | |
| `plugins/cortex-overnight/server.py:2164` | ✓ confirmed | Not auto-mirrored; manual edit |
| `requirements/project.md:28,31` sandbox-constraint text | **NEW** | Edit in-file string `lifecycle/` → `cortex/` per DR-5 |
| `requirements/project.md` Conditional Loading footer | **NEW** | Update area-doc paths once `requirements/` moves |
| Skill prose: `skills/lifecycle/SKILL.md`, `skills/refine/SKILL.md` | **NEW** | ~60 `lifecycle/<feature>` prose refs and 1 `backlog/<id>` example — update inline |
| Plugin canonical mirrors | ✓ confirmed | Regenerated by `just build-plugin`; zero manual edits |
| CLAUDE.md | ✓ confirmed | 5 path refs |
| docs/setup.md, docs/agentic-layer.md | ✓ confirmed | Operational-doc edits required (not deferrable prose) |
| Tests: `tests/test_lifecycle_phase_parity.py`, `tests/test_resolve_backlog_item.py` | ✓ confirmed | 11 fixture sites |

**Encoded-data migration** (per discovery §"Encoded path references"): 287 backlog YAML lines across 4 fields + 61 critical-review-residue `"artifact"` keys + ~6 research/<topic>/decomposed.md prose cross-refs. One-time migration script staged inside the relocation commit per DR-7.

## Migration runbook (binding for spec/plan)

Single atomic commit per DR-7 with explicit ordering:

1. **Preflight gate readiness** — produce fresh `lifecycle/apply-per-spawn-sandboxfilesystemdenywrite-at-all-overnight-spawn-sites/preflight.md` against pre-relocation HEAD (since runner.py edits trigger the sandbox-source regex in `bin/cortex-check-parity:89-109`).
2. **Code edits** (single working copy, no partial staging):
   - `_resolve_user_project_root()` predicate switch to `cortex/`
   - Path-literal swaps across the ~30+ enumerated sites above
   - `_CONTENT_DECLINE_TARGETS` collapse
   - Sandbox-registration umbrella swap
   - Skill/doc/CHANGELOG prose
3. **Data migration** (in-place file edits before `git mv`):
   - 287 backlog YAML lines via `sed` (4 fields)
   - 61 `critical-review-residue.json` `"artifact"` keys via JSON-aware script
   - ~6 research/<topic>/decomposed.md prose cross-refs
   - `requirements/project.md:28` sandbox-constraint string edit
4. **`git mv` storm** under `cortex/`:
   - lifecycle/ (38 active + 146 archived dirs) → cortex/lifecycle/
   - research/ (10 active + ~30 archived) → cortex/research/
   - backlog/ (195 files) → cortex/backlog/
   - requirements/ (5 area docs + project.md) → cortex/requirements/
   - retros/archive/ (56 files) → cortex/retros/archive/
   - debug/ (5 files) → cortex/debug/
   - `.cortex-init` → cortex/.cortex-init (path-string, not rename)
   - `lifecycle.config.md` → cortex/lifecycle.config.md
5. **Re-stage**: `git add -A` to capture renames.
6. **Pre-commit runs** drift + preflight + parity gates against the unified working copy.
7. **Commit** with message "Relocate cortex-command artifacts under cortex/ umbrella (#202)".
8. **Post-commit**: `cortex init --update` to refresh sandbox grant. Tag `vN.0.0` for major-version bump.

## Open questions for spec

Most discovery and clarify Open Questions are resolved by this addendum. Remaining items for spec to decide:

- **`bin/cortex-check-parity:112-113` `PREFLIGHT_PATH` literal**: post-relocation it becomes `cortex/lifecycle/apply-per-spawn-.../preflight.md`. Deferred per backlog Out-of-Scope; the relocation commit just updates the literal to track the new path. Data-drivenness deferred to #203 or a separate follow-up.
- **Single atomic commit vs separated rename-only commit + edit-only commit**: DR-7 chose single-atomic. Spec should reconfirm and explicitly forbid splitting (because path-literal edits + `git mv` of the referenced files in different commits introduces a window where the parity gate's globs match a path that exists in neither shape).
- **Naming inside `cortex/`**: backlog Out-of-Scope defers `.cortex-init` → `init.json` and `lifecycle.config.md` → `config.md` cosmetic renames. Spec should explicitly defer.
- **Installer-template README**: spec should decide whether `cortex init` (the installer side) ships a `cortex/README.md` template too, or whether cortex-command's own repo is the only repo with one for this commit.
- **`/cortex-core:research` re-run trigger**: this addendum was produced inline rather than via the standard parallel-research dispatch. Spec should treat the discovery research + this addendum as the binding research artifact set.
