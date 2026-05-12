---
discovery_phase: research
topic: consolidate-artifacts-under-cortex-root
audience: end-user installers (people running `cortex init` in their own projects) as primary, cortex-command's own repo as dogfooding secondary
created: 2026-05-11
---

# Research: consolidate-artifacts-under-cortex-root

> Investigate consolidating cortex-command's deployed artifacts — `lifecycle/`, `research/`, `retros/`, `backlog/`, `requirements/`, `.cortex-init`, `lifecycle.config.md` — under a single root directory at the repo level, so users can gitignore the whole tree as one unit. End-user repos are the primary lens; cortex-command's own repo adopts the same scheme as dogfooding. Migration cost is unconstrained (single-user reality per user statement 2026-05-11).

## Research Questions

1. **What's the exact touchpoint inventory and blast radius?** → **Resolved**. ~5,695 `lifecycle/` references repo-wide, 1,602 `backlog/`, 1,472 `requirements/`, 1,240 `research/`, 405 `lifecycle.config`, 216 `retros/` (mostly archive-pattern artifact), 130 `.cortex-init`. Most are prose; the **load-bearing surface is ~25–30 Python files** (init, common, overnight, dashboard, backlog modules) — the rest are doc/test prose batchable via search-and-replace. See §Codebase Analysis for breakdown.
2. **How is the `cortex init` + sandbox-registration contract structured today?** → **Resolved**. Two literal `lifecycle/` and `research/` registrations in `cortex_command/init/handler.py:143,153` write to `~/.claude/settings.local.json`'s `sandbox.filesystem.allowWrite` array, serialized via `~/.claude/.settings.local.json.lock` flock [`cortex_command/init/settings_merge.py:65-66`]. **Dual-registration invariant** for TOCTOU closure (legacy narrow `lifecycle/sessions/` + wide `lifecycle/`) is the load-bearing constraint [`cortex_command/init/handler.py:125-126`]. Scenario B (path-specific) requires only swapping literals; Scenario A (umbrella) collapses two entries to one.
3. **What are idiomatic precedents for tool-managed root dirs?** → **Resolved**. Every comparable AI tool surveyed uses a **hidden** root: `.cursor/`, `.claude/`, `.aider*`, `.continue/`. Closest mixed-content precedent (user-authored + tool-consumed under one root) is `.github/` — also hidden. The veggiemonk/`backlog` CLI tool defaults to `.backlog/`. **No major AI tool uses a visible tool-named root.** This contradicts the user's clarify-phase preference for visible `cortex/`; see DR-1.
4. **Should the consolidated root mix tool-generated and user-authored content?** → **Resolved**. Mixing is feasible (`.github/` is the precedent) but the inversion check argues against forcing `backlog/` and `requirements/` under any tool-named root — they're user-authored project content and idiomatically live at repo root (no comparable tool puts `linear/` or `jira/` at root; task-tracking either lives external or under a hidden root). Recommendation: **tool-only consolidation** (`.cortex/lifecycle/`, `.cortex/research/`, `.cortex/retros/`, `.cortex/.cortex-init`); leave `backlog/` and `requirements/` at repo root. See DR-2.
5. **Is there an inversion — gitignore-only — that captures most of the benefit?** → **Resolved**. Yes, partially. `cortex init` can write/append a `cortex.gitignore` snippet covering the current flat layout at near-zero effort (Alternative A in the inversion check). But this only addresses *tracked-files bloat*, not the conceptual containment / `ls` clutter the user implicitly objects to via "polluting their repo." Inversion check reads the user's framing as targeting the *end* (conceptual containment) with gitignore-ability as means; relocation is therefore on-target. See DR-3.
6. **State-file disposition: `.cortex-init`, `lifecycle.config.md` at root or under the consolidated root?** → **Resolved**. `.cortex-init` (a generated JSON marker, no bootstrap dependency) moves inside the consolidated root. `lifecycle.config.md` is a **user-edited** project-level config that is read by `cortex_command/overnight/daytime_pipeline.py:35` and `overnight/cli_handler.py:58` — it should also move inside the consolidated root for consistency, but the schema (test-command, skip-specify, etc.) is a user surface and should remain markdown-editable in place. See DR-4.

## Codebase Analysis

### Touchpoint inventory (counts via grep, full sweep)

| Path root | Total | Python (load-bearing) | Tests | Docs/prose | Build/config | Plugin mirrors |
|---|---|---|---|---|---|---|
| `lifecycle/` | ~5,695 | 310 LOC across ~16 files | 204 | 1,200+ | 140 (justfile, settings) | 127 (auto-regenerated) |
| `backlog/` | ~1,602 | 40 LOC across ~5 files | 50 | 140+ | 20 | ~50 |
| `research/` | ~1,240 | 20 LOC across ~3 files | 34 | 80+ | 30 | ~80 |
| `requirements/` | ~1,472 | 4 LOC | 1 | 80+ | 15 | ~20 |
| `.cortex-init` | ~130 | 60 (init/scaffold.py) | 30 | 20 | — | — |
| `lifecycle.config.md` | ~405 | 15 LOC | 8 | 10 | — | ~10 |
| `retros/` | ~216 | 0 | 0 | — | 1 (justfile exclude pattern) | — |

**Reading the numbers**: total counts are inflated by prose mentions in completed lifecycle artifacts under `lifecycle/<feature>/` (each lifecycle dir contains many self-references). The **operative surface is the Python and the canonical skill markdown** — not the prose count. `retros/` is effectively orphaned in code: 0 Python refs, 1 justfile exclusion pattern [`justfile:255,261`]; safe to ignore or relocate without code impact.

### Load-bearing surfaces (must change for relocation)

#### Sandbox + init contract

| File | Lines | Reference kind | Notes |
|---|---|---|---|
| `cortex_command/init/handler.py` | 125–126, 143, 153, 203–204 | string literal `"lifecycle"`, `"research"` | Hardcoded dual-registration; not parameterized. Load-bearing for sandbox grant. |
| `cortex_command/init/settings_merge.py` | 65–66, 79, 140–164, 256–262 | path computation + flock + re-check-after-lock | Lockfile path `~/.claude/.settings.local.json.lock` is sibling-inode-stable; no change needed |
| `cortex_command/init/scaffold.py` | 56–60 (`_CONTENT_DECLINE_TARGETS`), 351–373 (`write_marker`) | tuple of target paths; JSON marker writer | `_CONTENT_DECLINE_TARGETS` gates re-init refusal; marker filename hardcoded |

#### Runtime path computation (overnight, dashboard, backlog)

| File | Lines | Kind |
|---|---|---|
| `cortex_command/common.py` | 80 (`is_cortex_project`), 373 (`lifecycle_base` default) | CWD project-root heuristic + parameterizable function default |
| `cortex_command/backlog/generate_index.py` | (module-level `BACKLOG_DIR = Path.cwd() / "backlog"`) | Module-level const |
| `cortex_command/backlog/update_item.py` | same | Module-level const |
| `cortex_command/backlog/create_item.py` | same | Module-level const |
| `cortex_command/overnight/daytime_pipeline.py` | 35 (`config_path = cwd / "lifecycle.config.md"`), 59 (`Path("lifecycle").is_dir()` guard), 69 (PID file path) | Hard CWD guard — breaks if not updated |
| `cortex_command/overnight/report.py` | 272, 276 | `Path("lifecycle").glob("*/review.md")` |
| `cortex_command/overnight/backlog.py` | `DEFAULT_BACKLOG_DIR = Path("backlog")` | Module-level const |
| `cortex_command/overnight/orchestrator.py` | multiple | `/ "lifecycle" / "overnight-state.json"` factory defaults |
| `cortex_command/overnight/cli_handler.py` | 58 | reads `lifecycle.config.md` synthesizer-overnight flag |
| `cortex_command/dashboard/{app,seed,poller,data}.py` | ~15 sites total | JSON seed and live-poll paths |
| `cortex_command/discovery.py` | 30–33, 37–39, 160–161, 188–193 | `lifecycle/{feature}/events.log` and `research/{topic}/events.log` write targets |

**Parameterizable callsites already exist**: `common.py:read_criticality(feature, lifecycle_base=Path("lifecycle"))`, `common.py:read_tier(...)`, `pipeline/review_dispatch.py:dispatch_review(*, lifecycle_base=Path("lifecycle"))`. The `lifecycle_base` parameter pattern is established and can be extended through the overnight runner.

### Pre-commit gating coverage

- `bin/cortex-check-parity` enforces SKILL.md ↔ bin parity and SKILL.md ↔ source-skill prose parity. **Does NOT gate path-string hardcoding** [`bin/cortex-check-parity:1` — premise verified by sub-agent grep].
- `hooks/cortex-validate-commit.sh` validates commit message format only.
- No existing gate catches new `Path("lifecycle/...")` literals from being introduced post-relocation. A new gate would be needed to prevent drift; see Open Questions.

### Plugin mirrors (per CLAUDE.md, NOT manual copies)

Per `/Users/charlie.hall/Workspaces/cortex-command/CLAUDE.md` lifecycle skill description: "Auto-generated mirrors at `plugins/cortex-core/{skills,hooks,bin}/` regenerate via pre-commit hook; edit canonical sources only." The touchpoint-inventory agent reported these as potential manual edits (~250+); that's incorrect — only canonical sources change, mirrors regenerate. **Effective plugin-mirror churn for relocation: 0 manual edits** (build-output regeneration is automatic).

### `retros/` is effectively orphaned

`NOT_FOUND(query="retros/", scope="cortex_command/**/*.py")` — zero Python references. Only references are `[justfile:255]` and `[justfile:261]` as exclusion patterns in archive-orphan-reference scans. No skill writes there; no `cortex init` template scaffolds it. It exists on disk because a user (or earlier scheme) created it. **Disposition: include in `cortex/retros/` relocation for consistency, or delete during this work — either is safe.**

### Additional surfaces (round-2 findings)

#### Central path-computation site

- `cortex_command/overnight/state.py:321` — `_session_dir()` defaults to `_resolve_user_project_root() / "lifecycle"`. **This is the single most load-bearing path computation** in the codebase — dispatch, runner, orchestrator, and worktree-spawned agents all resolve session_dir through this function. Relocation requires this become `_resolve_user_project_root() / "cortex" / "lifecycle"` (or accept a configured base).
- `cortex_command/common.py:79-80` — `_resolve_user_project_root()` detects project root via `(cwd / "lifecycle").is_dir()` OR `(cwd / "backlog").is_dir()`. After relocation, a single `(cwd / "cortex").is_dir()` check is more robust. **No upward-walking logic exists** — cortex relies entirely on cwd at invocation time; invocation from a subdirectory is currently not supported and remains unsupported post-relocation.

#### Worktree settings inheritance

- `cortex_command/overnight/worktree.py:174` — when a worktree is created, `~/.claude/settings.local.json` is **copied** into the worktree, not re-registered. The copy contains `sandbox.filesystem.allowWrite` entries from the parent repo's settings at copy time. **Implication**: after relocation, `cortex init` must register the new `cortex/` paths in parent settings *before* any worktree spawn, or worktree agents will hit sandbox denial when writing to `cortex/lifecycle/sessions/<id>/`.

#### Sandbox preflight gate

- `bin/cortex-check-parity:112-114` — hardcoded `PREFLIGHT_PATH` constant pointing at a specific lifecycle feature directory:
  ```
  PREFLIGHT_PATH = "lifecycle/apply-per-spawn-sandboxfilesystemdenywrite-at-all-overnight-spawn-sites/preflight.md"
  ```
  Must update to `cortex/lifecycle/apply-per-spawn-.../preflight.md` after relocation.

#### SessionStart hook

- `hooks/cortex-scan-lifecycle.sh:26` — `LIFECYCLE_DIR="$CWD/lifecycle"`. After relocation: `LIFECYCLE_DIR="$CWD/cortex/lifecycle"`. Affects lines 26, 50, 84, 114, 328, 349, 361, 381 (`LIFECYCLE_DIR` expansions plus user-facing context messages).

#### Other hooks and pre-commit infrastructure (round-3 findings)

- `claude/hooks/cortex-tool-failure-tracker.sh:42` — `TRACK_DIR="lifecycle/sessions/${LIFECYCLE_SESSION_ID}/tool-failures"`. Must become `cortex/lifecycle/sessions/...`. PostToolUse hook; without update, failure-tracker writes to stale path and morning-report aggregation misses entries.
- `.githooks/pre-commit:81` — parity trigger pattern includes `requirements/*`. Must become `cortex/requirements/*` so the parity check fires when staged diffs touch the relocated requirements docs. The pre-commit orchestrates Phase 2 (detect source changes) → Phase 3 (`just build-plugin` rsync) → Phase 4 (`git diff` drift validation). Plugin mirrors regenerate automatically; no manual mirror edits needed.
- `bin/cortex-check-parity:75` — scans `"requirements/**/*.md"` glob; must become `"cortex/requirements/**/*.md"`.
- `bin/cortex-check-parity:112-113` — `PREFLIGHT_PATH` constant (already cited above) used at lines 1001, 1005, 1010, 1019, 1027, 1052, 1064, 1080, 1090.
- `hooks/cortex-validate-commit.sh` — operates on commit-message syntax only; no path references; no change required.
- `tests/test_plugin_mirror_parity.py:35-57` — CI defense-in-depth: byte-for-byte comparison of canonical `skills/lifecycle/references/{plan.md, specify.md, orchestrator-review.md}` vs `plugins/cortex-core/skills/lifecycle/references/`. Auto-passes after rsync; no relocation-specific change.
- `plugins/cortex-overnight/server.py:2164` — `Path(cortex_root) / "lifecycle" / "sessions" / payload.session_id` literal; this plugin's Python body is **not** auto-mirrored (only its skills/hooks are); must be manually updated.
- **Not yet audited (flagged as open question)**: `claude/hooks/cortex-worktree-create.sh`, `claude/hooks/cortex-worktree-remove.sh`, `claude/hooks/cortex-skill-edit-advisor.sh`, `claude/hooks/cortex-permission-audit-log.sh`. Likely low/no path-handling, but should be audited during spec/plan.
- **CLAUDE.md MUST-escalation policy wording** at lines 85–86 cites `lifecycle/<feature>/events.log` paths as evidence-link format. No gate parses these (manual policy); just update the example path post-relocation to `cortex/lifecycle/<feature>/events.log`.

#### Build pipeline confirms self-correcting

`justfile:507-539` `build-plugin` recipe rsyncs canonical sources into `plugins/cortex-core/{skills,hooks,bin}/` and `plugins/cortex-overnight/{skills,hooks}/`. The pre-commit hook runs this build before commit, then diffs the rebuilt mirror against the staged index. **Implication for relocation**: updating canonical sources (`skills/`, `hooks/`, `bin/`) propagates to plugin mirrors automatically; no manual mirror editing required. Hand-maintained plugins (`cortex-pr-review`, `cortex-ui-extras`, `cortex-dev-extras`, `android-dev-extras`) have **zero** references to the relocated paths.

#### Encoded path references (must migrate, not just rebase)

Path strings stored *inside* file content — distinct from prose references which batch-rewrite cleanly. **Round-2 audit was materially incomplete; revised counts below from critical-review reviewer 2:**

| Source | Count | Auto-rewritable | Failure mode if stale |
|---|---|---|---|
| `backlog/[0-9]*.md` YAML `discovery_source:` field | 153 | Yes (`sed`) | `/cortex-core:refine` reads this; broken refines |
| `backlog/[0-9]*.md` YAML `spec:` field | 130 | Yes (`sed`) | `cortex_command/backlog/generate_index.py:166-169`, `cortex_command/overnight/backlog.py:316-317`, `cortex_command/backlog/build_epic_map.py:160` consume this; broken index/epic-map/runner intake |
| `backlog/[0-9]*.md` YAML `plan:` field | 3 | Yes (`sed`) | Same consumers as `spec:` |
| `backlog/[0-9]*.md` YAML `research:` field | 1 | Yes (`sed`) | Same consumers |
| **Backlog YAML total** | **287 lines across 4 fields** | | |
| `lifecycle/<feature>/critical-review-residue.json` `"artifact"` key | 61 distinct values across active + archive | Yes (one-time migration script) | `cortex_command/overnight/report.py:950` reads these; morning-report breakage when residue points at stale path |
| `lifecycle/<feature>/events.log` `"epic_research"` structural key | 3+ instances sampled | Manual (immutable log convention) | Producer at `skills/lifecycle/SKILL.md` emits this key; SKILL.md update propagates to new emissions, but old emissions stay stale (accepted as grandfathered) |
| `cortex_command/dashboard/seed.py:99-100` `f"lifecycle/{slug}/spec.md"` | 2 | Yes (code edit) | Dashboard renders bad links |
| `cortex_command/overnight/state.py` `FeatureStatus.spec_path` ≈ `f"lifecycle/{feature}/plan.md"` | runtime-resolved | Yes (code edit) | Feature executor reads wrong path |
| `cortex_command/overnight/backlog.py` reads `discovery_source` and threads through | passes through | Yes (code edit) | Tied to backlog YAML migration |
| `research/<topic>/decomposed.md` prose cross-refs | ~6 | Manual review (prose) | Cosmetic; broken citation links in archived research |
| `bin/.parity-exceptions.md`, `bin/.events-registry.md` | 0 | — | — |
| `.github/ISSUE_TEMPLATE/`, PR templates | 0 | — | — |
| `lifecycle/<feature>/preflight.md` YAML `target_path:` | uses `$TMPDIR` env var | — | — (env-variable, not lifecycle-relative) |
| Plugin manifests (`marketplace.json`, `plugin.json`) | 0 | — | — |

#### `debug/` is cortex-adjacent

CLAUDE.md describes `debug/` as a "documented diagnose-skill fallback write-target" [`skills/diagnose/SKILL.md:281,283`]. The touchpoint-inventory round missed it. **Disposition: relocate to `cortex/debug/` for consistency** — it's cortex-managed scratchpad, not user-authored content. Trivial scope addition (5 files, all manual artifacts).

#### `ui-check-results/` is NOT cortex-core managed

Owned by `plugins/cortex-ui-extras/` (`/ui-lint`, `/ui-judge`, `/ui-a11y`, `/ui-check` skills). Stays at repo root; not in scope for this relocation. Could relocate later as a separate concern if the cortex-ui-extras plugin adopts the same pattern.

#### Dogfood scale (cortex-command's own repo)

- 38 active lifecycle dirs (+ `lifecycle/archive/` with 146 archived dirs)
- 10 active research dirs (+ `research/archive/` with ~30 archived)
- 195 backlog markdown items (`backlog/[0-9]*.md`)
- 5 requirements area docs
- 5 CLAUDE.md path references (trivial)
- `retros/archive/` only (no active retros)
- **No external GitHub URLs** (`github.com/.../blob/main/(lifecycle|backlog|research)/...`) reference these paths in `docs/` or `README.md` — `NOT_FOUND(query="github.com.*blob.*\\(lifecycle\\|backlog\\|research\\)", scope="docs/**/*.md, README.md")`. Zero external-link breakage.

#### Archive work prerequisite — already done

The `repo-spring-cleaning` epic #165 archive sweep has landed: 146 dirs in `lifecycle/archive/`, ~30 in `research/archive/`, retros consolidated under `retros/archive/`. **The relocation can proceed without an archive-first prerequisite.** Active vs archived dirs are already partitioned; both move together under `cortex/`.

## Web & Documentation Research

### AI-tooling root-dir naming convention (post-2023 cohort)

| Tool | Root | Visible? | Notes |
|---|---|---|---|
| Claude Code | `.claude/` | hidden | `skills/`, `hooks/`, `settings.json` under one hidden root |
| Cursor | `.cursor/rules/` | hidden | User-authored `.mdc` rule files, committed and shared |
| Aider | `.aider.conf.yml`, `.aiderignore`, `CONVENTIONS.md` | dotfiles + 1 visible | Hybrid: tool config hidden, user-facing conventions visible |
| Continue.dev | `.continue/` | hidden | Tool config |
| Copilot | `.github/copilot-instructions.md` | hidden | Lives under existing `.github/` |
| veggiemonk/backlog | `.backlog/` | hidden | The closest analog to cortex's `backlog/` |

**Finding**: Every comparable AI tool surveyed uses a hidden root. `NOT_FOUND(query="visible tool-named root for AI dev tools", scope="web-search")`. The post-2023 AI-tooling cohort has converged on hidden roots, treating themselves as analogous to `.git/` / `.vscode/`.

### Mixed-content under one root (user-authored + tool-consumed)

- `.github/` — workflows, issue/PR templates, CODEOWNERS — all user-authored, tool-interpreted. Hidden.
- `.devcontainer/` — entirely user-authored, tool-consumed. Hidden.
- `.cursor/rules/` — user-authored rule files, tool-consumed. Hidden.

`.github/` is the cleanest precedent for the cortex situation: a hidden tool-named root containing user-authored content that the tool reads to do its job.

### Gitignore-as-a-unit patterns

Three observed patterns:
1. **Whole-root ignore** (`node_modules/`, `target/`) — entire root gitignored.
2. **Sibling split** (Terraform): `.terraform/` ignored, `.terraform.lock.hcl` committed at root.
3. **Selective un-ignore with nested `.gitignore`** — supported by git but uncommon; most tools prefer sibling-split.

For cortex, pattern (1) maps cleanly to a `.cortex/` root if everything inside is tool-state.

### Citations

- [Cursor Rules](https://docs.cursor.com/context/rules) `[premise-unverified: not-searched]` (sub-agent fetched; not re-verified here)
- [Claude Code Skills](https://code.claude.com/docs/en/skills) `[premise-unverified: not-searched]`
- [Aider conventions](https://aider.chat/docs/usage/conventions.html) `[premise-unverified: not-searched]`
- [veggiemonk/backlog](https://github.com/veggiemonk/backlog) — `.backlog/` default `[premise-unverified: not-searched]`
- [Git gitignore docs](https://git-scm.com/docs/gitignore) `[premise-unverified: not-searched]`

## Domain & Prior Art

### What "feels like" a tool-managed dir vs project content?

Three signal strengths emerged from the prior-art survey:

| Signal | Tool-managed feel | Project-content feel |
|---|---|---|
| Lifetime | Regenerable from history | Hand-authored, intent-bearing |
| Edit cadence | Tool writes; user rarely edits | User edits; tool reads |
| Audience | Maintainers / debug | Contributors / reviewers |

By these signals, the cortex artifacts split cleanly:
- **Tool-managed**: `lifecycle/<feature>/{events.log,research.md,spec.md,plan.md,review.md,...}`, `research/<topic>/`, `retros/`, `.cortex-init`
- **Project-content**: `backlog/<NNN>-*.md`, `requirements/*.md`, `lifecycle.config.md` (user edits the config, even though it lives in the tool ecosystem)

This is the same logic behind:
- `node_modules/` (tool) vs `package.json` (user)
- `.terraform/` (tool) vs `*.tf` and `terraform.tfstate.d/` (user/output)
- `.github/workflows/` *blurs* this — workflows are user-authored CI code that lives under a tool-named hidden root. This is an exception, not the rule.

### Why the user's "visible `cortex/`" instinct is defensible

The visible choice isn't wrong — it's a framing claim. If cortex is positioned as a **project-content framework** (where the AI orchestration is incidental and the user is meant to spend real time in `lifecycle/<feature>/`, `research/<topic>/`, and `backlog/`), then visibility tracks that framing. `Pods/`, `vendor/`, and `coverage/` are precedents for visible tool-managed roots when the content is substantive and user-navigated.

But cortex evolved out of Claude Code conventions and ships *as* a Claude Code plugin. The dominant framing in the codebase (and in `requirements/project.md:7`) is **agentic workflow toolkit for AI-assisted software development** — a tool, not a project-content framework. That framing argues for hidden.

## Feasibility Assessment

| Approach | Effort | Risks | Prerequisites |
|---|---|---|---|
| **A**: Gitignore-only (ship `cortex.gitignore`, leave paths alone) | XS (~1 day) | Doesn't address `ls`/GitHub-tree clutter; misses the conceptual-containment goal | None |
| **B-hidden**: Tool-only relocation under `.cortex/` (lifecycle, research, retros, state files); backlog/requirements stay at root | M (3–5 days) | `daytime_pipeline.py:59` is a hard CWD guard; sandbox dual-registration invariant must be preserved; need a new parity gate to prevent drift | New `bin/cortex-check-path-hardcoding` gate (optional but recommended) |
| **B-visible**: Same as B-hidden but `cortex/` (visible) | M (3–5 days) | Same as B-hidden, plus breaks AI-tooling convention | Same |
| **C-hidden**: Full relocation under `.cortex/` (incl. backlog, requirements) | L (1–2 weeks) | All B risks plus: forces `cortex/backlog/<id>.md` paths into every skill SKILL.md and every doc reference; touches `requirements/` cross-refs from CLAUDE.md and per-area docs | Same as B |
| **C-visible**: Same as C-hidden but `cortex/` (visible) — the user's clarify-phase ask | L (1–2 weeks) | All C-hidden risks plus convention break | Same |
| **D**: Status quo + better `cortex init` notice | XS (~2h) | Zero structural change; relies on user reading the notice | None |

**Effort components for the selected option (C-visible: full relocation under visible `cortex/`):**

- `cortex_command/init/handler.py` + `scaffold.py` literal/tuple updates: ~5–8 lines
- `cortex_command/overnight/state.py:321` central path-computation: 1 line (most load-bearing single change)
- `cortex_command/common.py:79-80` project-root detection: 1–2 lines
- Backlog modules (`generate_index.py`, `update_item.py`, `create_item.py`): 3 files, module-level const swaps
- Overnight modules (`daytime_pipeline.py`, `report.py`, `backlog.py`, `orchestrator.py`, `cli_handler.py`, `feature_executor.py`): 6 files, defaults + literal swaps
- Dashboard modules (`app.py`, `seed.py`, `poller.py`, `data.py`): 4 files, ~15 path-construction sites
- Discovery module (`cortex_command/discovery.py`): 1 file, write-target paths
- SessionStart hook (`hooks/cortex-scan-lifecycle.sh`): 1 file, 8 line edits (lines 26, 50, 84, 114, 328, 349, 361, 381)
- PostToolUse hook (`claude/hooks/cortex-tool-failure-tracker.sh:42`): 1 line
- Pre-commit + parity (`.githooks/pre-commit:81`, `bin/cortex-check-parity:75,112-113`): 3 line edits across 2 files (plus ~9 sites referencing `PREFLIGHT_PATH`)
- Bin scripts (`bin/cortex-log-invocation:46`): 1 line
- Plugin canonical sources not auto-mirrored (`plugins/cortex-overnight/server.py:2164`): 1 line
- Encoded data migration: one-time script for 153 `discovery_source:` YAML rewrites + ~6 markdown-prose cross-refs in research/
- Test fixtures: 11 sites across `tests/test_lifecycle_phase_parity.py`, `tests/test_resolve_backlog_item.py`
- Doc/prose rebases: ~140 lines in `docs/`, ~80 in README/setup, 5 in CLAUDE.md, 1,200+ in lifecycle/ self-references (auto-stale but harmless)
- Plugin-mirror regeneration: 0 manual edits (pre-commit hook handles per CLAUDE.md)
- `git mv` operations: 38 active lifecycle dirs + lifecycle/archive/ (146 dirs) + 10 active research dirs + research/archive/ + 195 backlog files + 5 requirements files + retros/archive/ + 5 debug files + `lifecycle.config.md` + `.cortex-init` → all under `cortex/`
- New parity gate (optional): `bin/cortex-check-path-hardcoding` to prevent post-relocation drift
- Upward-walking project-root helper (per DR-10): new helper in `cortex_command/common.py` (~10–15 lines) + retarget ~5 callers (`common.py:79-80`, `daytime_pipeline.py:59`, `backlog/{generate_index,update_item,create_item}.py`, `discovery.py`). Adds ~0.5 days
- Plugin-version transition documentation (per DR-9): single-line CHANGELOG entry + commit message guidance. Negligible
- Migration runbook: capture DR-7 operational preconditions (`git add -A`, fresh preflight, no overnight active) in `lifecycle/<feature>/preflight.md`-style runbook for the relocation commit itself

## Decision Records

### DR-1: Hidden `.cortex/` vs visible `cortex/`

- **Context**: User chose visible `cortex/` in clarify phase. Research surfaced that every comparable AI tool uses hidden.
- **Options considered**:
  - **A**: Visible `cortex/` — breaks the AI-tooling convention but is more discoverable for users who don't gitignore.
  - **B**: Hidden `.cortex/` — matches `.claude/`, `.cursor/`, `.aider*`, `.continue/`, `.github/`; idiomatic for tool-managed roots.
- **Decision (user confirmed 2026-05-11)**: **A (visible `cortex/`).** User reasoning: "Some folks will gitignore, and some won't" — visibility serves the not-gitignoring path, which would otherwise require `ls -a` to find the tool's working area.
- **Trade-offs accepted**: breaks the post-2023 AI-tooling hidden-root convention. Mitigated by: cortex is a multi-surface system (overnight runner, dashboard, lifecycle artifacts) more like a project-content framework than pure tool config; visible communicates "this is content you'll spend time in" matching that framing.

### DR-2: Full vs partial relocation (backlog/requirements scope)

- **Context**: User chose to include `backlog/` and `requirements/` in clarify. Inversion check and prior-art argued for partial.
- **Options considered**:
  - **A**: Full relocation — `cortex/backlog/`, `cortex/requirements/`, etc. One mental folder, one gitignore line.
  - **B**: Partial — tool-state under `cortex/`, `backlog/` and `requirements/` stay at root.
- **Decision (user confirmed 2026-05-11)**: **A (full relocation).** User reasoning: prefers "one folder for everything cortex-related" purity over preserving the idiomatic root-level task-tracking convention.
- **Trade-offs accepted**: ~2x touchpoint count vs partial (L effort, ~1–2 weeks); `backlog/<id>.md` paths in every skill SKILL.md and cross-ref must rebase to `cortex/backlog/<id>.md`. Breaks the convention that task tracking lives at repo root (new contributors clone and won't see `backlog/` until they look inside `cortex/`). Mitigated by: cortex-command is single-user today; `cortex/` is visible so discoverable; cortex init can print a "your project content lives under `cortex/`" notice.

### DR-3: Gitignore-only inversion (Alternative A) — rejected

- **Context**: Inversion check raised gitignore-only as a low-effort alternative.
- **Recommendation**: **Reject as standalone solution; bundle as affordance regardless.** Reasoning: the user's framing ("polluting their repo") reads as targeting conceptual containment, not just tracked-files hygiene. Gitignore-only leaves the visual `ls` clutter and the GitHub-tree-render bloat the user implicitly objects to. *However*, `cortex init` should still write a `.gitignore` entry for `.cortex/` (and any other tool-deployed state) as part of the relocation — that's cheap and eliminates the "I forgot to ignore this" failure mode.
- **Trade-offs**: None — bundling A as an affordance under B costs ~2 hours and has no downside.

### DR-4: State-file disposition (`.cortex-init`, `lifecycle.config.md`)

- **Context**: These are special-cased. `.cortex-init` is a generated JSON marker; `lifecycle.config.md` is user-edited project config.
- **Options considered**:
  - Both move inside `.cortex/`: `.cortex/.cortex-init`, `.cortex/lifecycle.config.md`.
  - Both stay at repo root for bootstrap discoverability.
  - Split: `.cortex/.cortex-init` (tool-state) inside; `lifecycle.config.md` stays at root (user-editable).
- **Recommendation**: **Move both into `.cortex/`.** Reasoning: `.cortex-init` has no bootstrap dependency — `cortex init` knows to look inside `.cortex/` for it because the tool itself sets the convention. `lifecycle.config.md`, while user-edited, is conceptually tool-config (it tunes lifecycle-phase behavior) and belongs alongside the tool's other state. Path becomes `.cortex/lifecycle.config.md`; `daytime_pipeline.py:35` and `cli_handler.py:58` swap one literal.
- **Trade-offs**: `lifecycle.config.md` becomes slightly less discoverable to new users; mitigated by `cortex init` printing its path on completion.

### DR-5: Sandbox-registration mechanism (umbrella vs path-specific)

- **Context**: `cortex init` registers paths in `~/.claude/settings.local.json` `sandbox.filesystem.allowWrite`. Under the new layout, do we register one umbrella entry (`cortex/`) or multiple specific entries (`cortex/lifecycle/`, `cortex/research/`, `cortex/debug/`)?
- **Options considered**:
  - **A**: Umbrella — single entry for `cortex/`. Sandbox grants write to everything under `cortex/`, including future tool-state subdirs. One settings entry per repo.
  - **B**: Path-specific — separate entries per subdir. Tighter grant; future tool subdirs require re-registration.
- **Recommendation**: **A (umbrella).** Reasoning: cortex *is* the tool that writes there. Granting it write to its own root is the same blast radius as the status quo (`lifecycle/` + `research/` already cover everything cortex writes today); the umbrella simplifies the contract and future-proofs tool-state expansion. Defense-in-depth still applies: `~/.claude/settings.json` deny-list is independent.
- **Trade-offs**: Slightly broader grant than path-specific. But the lockfile + serialization + dual-registration-invariant complexity of the current code [`cortex_command/init/handler.py:125-126`] exists primarily because the legacy narrow path (`lifecycle/sessions/`) had to coexist with the wide path; umbrella collapses that to one entry and likely *simplifies* the init contract.

### DR-6: Include `debug/` in the relocation set

- **Context**: Round-2 hidden-surfaces sweep identified `debug/` as cortex-adjacent (documented diagnose-skill fallback write-target). The user's original list did not include it.
- **Recommendation**: **Include `debug/` → `cortex/debug/`.** Reasoning: it's cortex-managed scratchpad, gitignore-eligible by the same logic as `lifecycle/sessions/`, and the relocation cost is trivial (5 manual artifact files, no skill-code references beyond `skills/diagnose/SKILL.md:281,283`).
- **Trade-offs**: Slight scope creep but improves consistency.

### DR-7: Migration sequencing — single atomic commit

- **Context**: Cortex-command's own repo has 38 active + 146 archived lifecycle dirs, 10 active + ~30 archived research dirs, 195 backlog items, 5 requirements docs, 5 debug files, `lifecycle.config.md`, `.cortex-init`. The user said "I am the only real user right now" — migration cost for **cortex-command's own repo** is unconstrained. Migration for downstream `cortex init` installer-repos is deferred (no live installers today; first external installer triggers a separate migration story).
- **Options considered**:
  - **A**: Single atomic commit — one `git mv` storm, all code/doc rebases, all encoded-path migrations, all in one commit. Simplest history.
  - **B**: Phased — code-and-paths-decoupled (introduce `cortex/` as alias first, deprecate old paths, then move). Lower-risk for shared repos with multiple contributors.
  - **C**: Per-subdir phased — relocate `lifecycle/` first, then `research/`, then `backlog/`, etc. Bounded scope per commit.
- **Recommendation**: **A (single atomic commit).** Reasoning: single-user reality eliminates the coordination cost that phased approaches solve. Archive work is complete, so `git mv` operates on a stable set. One commit is easier to revert if something breaks. The encoded-data migration (287 backlog YAML lines + 61 critical-review-residue artifacts) is mechanical and runs in the same commit.
- **Operational preconditions** (added post-critical-review):
  - **Use `git add -A`** (or equivalent staging-of-everything). Selective staging via `git add -p` is unsafe — `core.hooksPath` (set by `just setup-githooks`) routes pre-commit through `.githooks/pre-commit` in the working tree, and `bin/cortex-check-parity` executes from disk; running hook scripts read working-copy state, so partial staging makes working-copy and staged versions diverge.
  - **Stage `bin/cortex-check-parity:75,112-113` and `.githooks/pre-commit:81` edits together with the `git mv`s.** Otherwise the parity scan globs (`requirements/**/*.md`) silently scan an empty corpus.
  - **Fresh sandbox preflight against pre-relocation HEAD.** The relocation edits `cortex_command/overnight/runner.py` and `cortex_command/pipeline/dispatch.py` to update path literals; those edits will trivially match the `sandbox`/`--settings` regex patterns in `bin/cortex-check-parity:89-109`, firing the preflight gate. Without a fresh preflight, the commit fails with E102 (stale `commit_hash`). Resolution: run preflight against HEAD immediately before the relocation commit, OR split path-only edits to those two files into a preceding zero-functional-change commit that the gate doesn't fire on (verify regex behavior first).
  - **No overnight session active during the relocation commit.** Worktree agents writing to `lifecycle/sessions/<id>/events.log` while the parent repo's `git mv` runs will lose writes. Verify via `cortex overnight status` returning no live sessions; this is a hard precheck, not a soft user-discipline note.
- **Trade-offs**: The commit diff is large (touches every backlog item, every lifecycle dir's metadata, every requirements doc). Mitigated by: git's `--follow` and `git log --diff-filter=R` handle renames correctly; reviewers can grep for the few hand-edited code/doc sites among the renames.

### DR-8: Worktree settings.local.json coordination

- **Context**: `cortex_command/overnight/worktree.py:174` *copies* `~/.claude/settings.local.json` into worktrees at creation time, including `sandbox.filesystem.allowWrite` paths. After the relocation, the worktree's spawned agents write to `cortex/lifecycle/sessions/<id>/` but the inherited settings may still grant `lifecycle/sessions/` (stale).
- **Options considered**:
  - **A**: Re-run `cortex init` once after the relocation lands, before any new overnight run. Updates parent settings; subsequent worktree spawns inherit the new grants.
  - **B**: Have the worktree creation path call into `settings_merge.register()` to re-register `cortex/` for the worktree.
  - **C**: Use the umbrella grant (per DR-5) — register `cortex/` once at parent init; covers all subdirs and future-proofs.
- **Recommendation**: **A + C combined.** Run `cortex init --update` after the relocation lands to refresh parent settings to the umbrella `cortex/` grant. Subsequent worktree creations inherit the correct grant. No code change to `worktree.py` needed.
- **Preconditions** (added post-critical-review):
  - **No overnight session active during the relocation commit** (cross-ref DR-7 operational preconditions).
  - Post-commit, run `cortex init --update` before the next overnight start.
- **Trade-offs**: Requires a manual `cortex init --update` step post-relocation; documented in the migration runbook.

### DR-9: Plugin-version transition story

- **Context**: Cortex skills (`/cortex-core:lifecycle`, `/cortex-core:discovery`, etc.) ship via the `cortex-core` plugin installed in user `~/.claude/plugins/`. After the relocation, the canonical skill prose says agents should write to `cortex/lifecycle/{feature}/`. But any Claude Code session that loaded the prior plugin version will keep executing prose telling agents to write to `lifecycle/{feature}/`. The build-pipeline regeneration (per `justfile:507-539`) only updates the cortex-command repo's plugin mirrors — it does not propagate to already-installed user-side plugin versions.
- **Options considered**:
  - **A**: Tag a major-version bump and require users to `/plugin update cortex-core` before next session. Hard cutover.
  - **B**: Make skill prose tolerant of both layouts for one release — try `cortex/lifecycle/` first, fall back to `lifecycle/`. Soft cutover with grandfather period.
  - **C**: Add a SessionStart guard that detects layout mismatch (e.g., `cortex/` exists but plugin's skill prose references `lifecycle/`) and aborts the session with a clear message ("plugin out of date — run `/plugin update cortex-core`").
- **Recommendation**: **A (major-version bump + plugin reinstall).** Reasoning: the user is the only consumer today; coordinating a single `/plugin update` is trivial. (B) introduces fallback complexity in every skill, multiplying the surface that has to be reasoned about. (C) is right for a multi-user future but premature now. Document the transition in the relocation commit message and in `docs/setup.md`.
- **Trade-offs**: First external installer (when one materializes) will need explicit upgrade guidance. Acceptable — they don't exist yet, and a single-line CHANGELOG entry covers them when they do.

### DR-10: Upward-walking project-root detection

- **Context**: Surfaced by critical-review reviewer 3. DR-1 chose visible `cortex/` because it's "content you'll spend time in" — implying users will `cd` into `cortex/lifecycle/<feature>/` to read artifacts. But `_resolve_user_project_root()` at `cortex_command/common.py:79-80` detects project root via `(cwd / "lifecycle").is_dir()` (post-relocation: `(cwd / "cortex").is_dir()`) — pure cwd, no upward walk. From `cortex/lifecycle/<feature>/`, that check fails and CLIs misfire. Every comparable tool (git, npm, cargo, terraform, kubectl) walks upward.
- **Options considered**:
  - **A**: Add upward-walking — replace the cwd-only check with a helper that walks up from `cwd` looking for `cortex/` (or `.git/`, as a parent-marker). +1 helper + ~3 caller updates.
  - **B**: Preserve cwd-only — retarget detection from `(cwd / "lifecycle")` to `(cwd / "cortex")`, document "cortex CLIs must run from repo root."
  - **C**: Defer to a separate ticket.
- **Decision (user confirmed 2026-05-11)**: **A (add upward-walking).** Reasoning: the relocation is the cheapest moment to introduce upward walk; DR-1's visibility rationale ("content you'll spend time in") only makes sense paired with CLIs that work from inside `cortex/`. Resolves the contradiction reviewer 3 surfaced.
- **Scope**: implement a small helper (e.g., `_resolve_user_project_root_with_walk()`) that walks upward from `cwd` until it finds `cortex/` (the new umbrella) OR `.git/` (parent marker). Update callsites in `common.py:79-80`, `daytime_pipeline.py:59`, `backlog/{generate_index,update_item,create_item}.py`, and `discovery.py`. Emit the resolved root in CLI invocation logging (one line) so failure modes are self-diagnosing.
- **Trade-offs**: changes behavior for the "no cortex repo found anywhere up the tree" case — previously fails fast at cwd, now walks up to `/` before failing. Mitigation: stop the walk at `.git/` boundaries.

## Open Questions

- **Should a `bin/cortex-check-path-hardcoding` gate be added** to prevent post-relocation drift (new code introducing `Path("lifecycle/...")` literals instead of `Path("cortex/lifecycle/...")` or, better, the parameterized `lifecycle_base`)? Recommendation: yes, as a follow-up ticket — not a blocker for the relocation itself.
- **`retros/` final disposition** — relocate to `cortex/retros/` for consistency, or delete entirely since it has zero Python consumers? Decision deferrable to spec/plan phase; either is mechanically safe.
- **Does `cortex/` need a `README.md` inside** explaining the layout to contributors who land there? Suggest yes for cortex-command itself (dogfooding); for end-user installer repos, the existing `lifecycle/README.md` and `backlog/README.md` templates would shift to `cortex/lifecycle/README.md` and `cortex/backlog/README.md`. Cheap.
- **Renaming `.cortex-init` to just `init.json` inside `cortex/`** — once it's inside a `cortex/` root, the `.cortex-` prefix is redundant. Cosmetic, deferrable. Same logic for `lifecycle.config.md` → `config.md`.
- **Schedule of work**: archive cleanup from `repo-spring-cleaning` has already landed, so no prerequisite blocking. **Recommendation: proceed directly.**
- **Should `bin/cortex-check-parity:112-114` `PREFLIGHT_PATH` constant become data-driven** (e.g., read the path from a registry) rather than hardcoded? Currently it's a single hardcoded path to one specific lifecycle feature. After relocation it becomes a slightly-worse hardcoded path. Worth a small follow-up to parameterize, but not a blocker.
- **Four `claude/hooks/` scripts not audited in this research**: `cortex-worktree-create.sh`, `cortex-worktree-remove.sh`, `cortex-skill-edit-advisor.sh`, `cortex-permission-audit-log.sh`. Likely low/no path-handling but must be audited during spec/plan phase to confirm.
- **The relocator's self-reference**: the lifecycle directory currently doing this research (`lifecycle/consolidate-artifacts-under-cortex-root/`) is itself in scope for the `git mv`. During the relocation commit, the relocator's session is still appending to `lifecycle/sessions/<id>/events.log` and `lifecycle/<this-feature>/events.log`. Mitigation: complete the lifecycle phases through plan/implement, archive the lifecycle dir, then run the relocation commit from a fresh session that has no active `LIFECYCLE_SESSION_ID`. Alternative: run the relocation as its own lifecycle but exclude `lifecycle/<relocation-feature>/` from the `git mv` until the final commit.
- **`docs/setup.md` and `docs/agentic-layer.md` are operational documentation**, not just prose. They describe literal post-`cortex init` filesystem state users will see (per `docs/agentic-layer.md:254` quoting filesystem paths users observe). Onboarding correctness depends on updating these in lock-step with the relocation — they are not "batchable prose later."
- **DR-1 visibility rationale vs cwd-only resolution** — resolved per DR-10 (add upward-walking).
