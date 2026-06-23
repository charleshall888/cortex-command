# Research: Extract the `backlog` skill into an optional `cortex-backlog` plugin (epic P1, ticket 316)

> Scope anchor (clarified intent): Extract **only** `skills/backlog` into a new optional `cortex-backlog` plugin (following the cortex-overnight optional-plugin pattern); **keep `backlog-author` in cortex-core** (backend-agnostic body composer the external-tracker path depends on). Packaging-only — no change to the `cortex_command/backlog/*` engine. Land atomically in one commit, and amend `cortex/requirements/backlog.md` to remove its contradictory "both skills move" acceptance criterion (user-confirmed during Clarify).

## Epic Reference

Parent epic: **#315 — Optional backlog plugin + configurable backend**. Epic research/design (ten-piece analysis P1–P10, sequencing): [`cortex/research/backlog-optional-plugin/research.md`](../../research/backlog-optional-plugin/research.md). This ticket is **P1** (the atomic extraction); the config-backend resolver (P4), consumer routing + slash-rename (P6), external best-effort (P7), overnight refusal (P8), and ADR-0015 (P10) are **later tickets** and out of scope here. This research is scoped to P1 only and does not re-open the epic's locked decisions.

## Codebase Analysis

**Move set (authoritative — user-confirmed):** only `skills/backlog/` moves; `skills/backlog-author/` stays in cortex-core. Several research agents drifted to "move both" — that is wrong.

Files, grouped by operation:

- **Create**
  - `plugins/cortex-backlog/.claude-plugin/plugin.json` — hand-authored (must exist *before* first `just build-plugin`; see Build & Distribution).
  - `plugins/cortex-backlog/skills/backlog/**` — generated mirror of `skills/backlog/` (SKILL.md + `references/schema.md`) via `just build-plugin`.
  - `tests/test_cortex_backlog_prefix_collision.py` — new regression guard (see Parity & Test Gates).
- **Modify**
  - `justfile` — `BUILD_OUTPUT_PLUGINS` (line 575) add `cortex-backlog`; `build-plugin` cortex-core arm (line 597) remove `backlog` (keep `backlog-author`); add a `cortex-backlog)` arm with `SKILLS=(backlog) BIN=() HOOKS=()`.
  - `cortex_command/parity_check.py` — move `"cortex-backlog"` from `RESERVED_NON_BIN_NAMES` (line 66) into `PLUGIN_NAMES` (lines 34–43); update the reservation comment.
  - `tests/test_dual_source_reference_parity.py` — `PLUGINS` dict: drop `"backlog"` from the cortex-core tuple, add `"cortex-backlog": ("backlog",)`.
  - `.claude-plugin/marketplace.json` — add the cortex-backlog plugin entry (not gated; for discoverability).
  - `skills/backlog/SKILL.md` — its `/backlog-author` invocation → `/cortex-core:backlog-author` (cross-plugin robustness); its own self-reference prose `/cortex-core:backlog` → `/cortex-backlog:backlog`.
  - `cortex/requirements/backlog.md` — amend Inputs (20), Outputs (21), acceptance criterion (24); add an architectural-constraints bullet; soften "listed as OPTIONAL in the table".
  - `docs/setup.md` — "six available plugins" → "seven"; add cortex-backlog row + a prose prerequisite marking it optional and requiring cortex-core.
- **Delete (must be explicit `git rm` — `build-plugin` will NOT remove it; see Adversarial #1)**
  - `plugins/cortex-core/skills/backlog/**` (the orphaned mirror).

**Unchanged (stay in the wheel, packaging-only invariant):** `cortex_command/backlog/*` (create/update/ready/resolve/generate_index) and the `cortex-*` console scripts (`cortex-create-backlog-item`, `cortex-update-item`, `cortex-backlog-ready`, `cortex-resolve-backlog-item`, `cortex-generate-backlog-index`). These are wheel-resident via `pyproject.toml [project.scripts]`; the plugin is **skills-only** (no `bin/`).

**Canonical skill inventory:** `skills/backlog/` = `SKILL.md` + `references/schema.md`; `skills/backlog-author/` = `SKILL.md` + `references/body-template.md`. Cross-plugin caller edge: `skills/backlog/SKILL.md:59,61,62` invoke bare `/backlog-author interview`.

## Web Research

Authoritative Claude Code docs ([plugins-reference](https://code.claude.com/docs/en/plugins-reference), [plugin-marketplaces](https://code.claude.com/docs/en/plugin-marketplaces), [skills](https://code.claude.com/docs/en/skills), [plugin-dependencies](https://code.claude.com/docs/en/plugin-dependencies)):

- **plugin.json**: only `name` is required (kebab-case, used for namespacing). cortex-overnight's minimal `{name, description, author}` is the repo precedent for a skills-only plugin.
- **Slash namespace is plugin-derived and plugin-scoped**: a skill at `plugins/<plugin>/skills/<dir>/SKILL.md` is addressed `/<plugin>:<dir>`. Moving `skills/backlog` into cortex-backlog **automatically** changes its command `/cortex-core:backlog` → `/cortex-backlog:backlog`; there is no per-skill namespace override.
- **Cross-plugin invocation**: docs say an *explicit* slash reference should be fully-qualified `/plugin:skill`; bare `/skill` is not documented to resolve cross-plugin. **However** (see Adversarial #2) the repo already relies on bare cross-plugin resolution working — morning-review (cortex-overnight) invokes bare `/backlog-author` (cortex-core) in production — because Claude routes skills by description across plugins. Net: fully-qualify `/cortex-core:backlog-author` as the safe/explicit form; the move is not a hard runtime break.
- **Optional-plugin levers (available, but unused by cortex-overnight)**: `defaultEnabled: false` (CC v2.1.154+) and `dependencies: ["cortex-core"]` (same-marketplace auto-enable; version constraints need v2.1.110+/143+). These would formally encode "optional" + the cortex-core prerequisite, but diverge from the repo's prose-only convention — see Open Decisions.
- **Marketplace ordering**: no documented ordering semantics; grouping is via `category`/`tags`. The Codebase-vs-Build agents' insertion-point disagreement is moot — just keep marketplace.json and docs/setup.md mutually consistent.
- **Caveat**: known plugin-skill-registration reliability issues ([#17271](https://github.com/anthropics/claude-code/issues/17271) and related) — verification should confirm both skills surface under `/` after install.

## Requirements & Constraints

- **backlog.md conflict (the Clarify-resolved item), verbatim**:
  - Line 20 (Inputs): "The existing canonical skills `skills/backlog/` and `skills/backlog-author/`."
  - Line 21 (Outputs): "A new `cortex-backlog` plugin containing those two skills … listed as OPTIONAL in the `docs/setup.md` plugin table."
  - Line 24 (acceptance criterion): "`skills/backlog` and `skills/backlog-author` are packaged in the `cortex-backlog` plugin, not in `cortex-core`."
  These say **both** skills move; the design keeps `backlog-author` in core. Amend all three + add an architectural-constraints bullet explaining *why* (discovery/morning-review compose bodies via backlog-author on the external path).
- **Binding architectural constraints (project.md / CLAUDE.md)**: dual-source mirror enforcement (canonical top-level, mirrors regenerated by `just build-plugin`, pre-commit drift gate); Phase-1 fail-closed plugin classification (every `plugins/*/.claude-plugin/` must be in `BUILD_OUTPUT_PLUGINS` or `HAND_MAINTAINED_PLUGINS`); `plugin-list-matches-justfile` self-test (`PLUGIN_NAMES == BUILD_OUTPUT ∪ HAND_MAINTAINED`); SKILL.md 500-line cap; L1 surface ratchet and skill-size budget (both keyed on **canonical skill dir name**, so the move does **not** touch budget rows); MUST-escalation policy (no new routing-prose MUST — none added here).
- **ADR**: P1 is packaging-only and fails the three-criteria gate (not surprising, standard optional-plugin pattern; ADR-0002 already covers CLI-wheel-plus-plugin distribution). **No new ADR for 316.** ADR-0015 (configurable backend + LLM-as-adapter) belongs to the later config-resolver ticket (P4/P10).
- **Events-registry gate**: P1 emits no events — no registry entry.

## Build & Distribution Mechanics

Exact `build-plugin` edits (verified against the live recipe at justfile 588–625):

- Line 575: `BUILD_OUTPUT_PLUGINS := "cortex-core cortex-overnight"` → `… cortex-overnight cortex-backlog"`.
- cortex-core arm (line 597): remove `backlog`, **keep** `backlog-author`: `SKILLS=(commit pr lifecycle backlog-author requirements requirements-gather requirements-write research discovery refine dev diagnose critical-review interview)`.
- New arm (insert before `*)`):
  ```bash
  cortex-backlog)
      BIN=()
      SKILLS=(backlog)
      HOOKS=()
      ;;
  ```
- **Sequencing (critical)**: `build-plugin` skips any BUILD_OUTPUT plugin whose `.claude-plugin/` does not yet exist (justfile:593) — so hand-create `plugins/cortex-backlog/.claude-plugin/plugin.json` **first**, else the build silently skips and a broken commit can pass.
- plugin.json scaffold (minimal, matching cortex-overnight):
  ```json
  {
    "name": "cortex-backlog",
    "description": "Interactive backlog management skill for cortex-command — create, list, pick, ready, archive, and reindex local markdown-frontmatter backlog items.",
    "author": { "name": "Charlie Hall", "email": "charliemhall@gmail.com" }
  }
  ```
- **Co-land atomicity** is forced by: Phase-1 classification (plugin.json present ⇒ must be in justfile) + Phase-4 drift gate (`git diff --quiet plugins/$p/` after rebuild). Per CLAUDE.md "Drift hook + shared-checkout coupling": run `just build-plugin` and commit canonical + generated mirror together — do not defer mirror regen.
- **Orphaned-dir gap (see Adversarial #1)**: removing `backlog` from cortex-core's array does **not** delete `plugins/cortex-core/skills/backlog/`; the plan must `git rm -r` it explicitly.

## Parity & Test Gates

- **`PLUGIN_NAMES` vs `RESERVED_NON_BIN_NAMES` — definitive: MOVE OUT, not dual.** Verified against the scanner: candidate filter (≈635–636) excludes **both** sets; wiring filter (≈607) excludes **only** PLUGIN_NAMES. `TOKEN_RE` is word-boundaried, so `cortex-backlog-ready` etc. extract as full tokens and are **not** shadowed by the `cortex-backlog` prefix. cortex-overnight's dual membership exists only because its MCP name appears in un-path-qualifiable code fences; cortex-backlog's config-value code-span references in backlog.md are **fully** covered by PLUGIN_NAMES membership (it's excluded from both candidates *and* wiring). So moving it out of RESERVED is complete and correct — no regression. The existing "migrate to PLUGIN_NAMES" comment endorses exactly this.
- **`plugin-list-matches-justfile` self-test** asserts `PLUGIN_NAMES == BUILD_OUTPUT ∪ HAND_MAINTAINED` (justfile). Adding cortex-backlog to both BUILD_OUTPUT_PLUGINS and PLUGIN_NAMES keeps it green. **No marketplace assertion exists** in parity_check.py (verified: `grep marketplace` empty) — marketplace.json is human-maintained and ungated.
- **`test_dual_source_reference_parity.py` PLUGINS dict**: drop `"backlog"` from cortex-core, add `"cortex-backlog": ("backlog",)`. The dict is *already* a partial list (omits backlog-author/interview/requirements-gather/requirements-write) — a **pre-existing** coverage gap whose byte-parity is still enforced by the Phase-4 drift gate. Not in scope to fix here (see Open Decisions / Considerations).
- **New prefix-collision regression guard** (`tests/test_cortex_backlog_prefix_collision.py`): assert the backlog `cortex-*` console scripts (`cortex-backlog-ready`, `cortex-create-backlog-item`, `cortex-resolve-backlog-item`, `cortex-update-item`, `cortex-generate-backlog-index`) remain reference-candidates/wired (bin-classified) once `cortex-backlog` is in PLUGIN_NAMES, and that the bare `cortex-backlog` plugin token is excluded. Model assertions on `parity_check.collect_reference_candidates` / `collect_wiring_signals` / `TOKEN_RE`.
- **Unaffected**: L1 ratchet, skill-size budget (canonical-keyed).

## Tradeoffs & Alternatives

1. **parity membership** — move-out vs dual: **move-out** (resolved above; dual is redundant).
2. **docs/setup.md OPTIONAL marking** — table column vs row annotation vs prose-prerequisite: lean **prose-prerequisite** (matches cortex-overnight, minimal-table ethos); amend backlog.md's literal "OPTIONAL in the table" wording to "documented as optional". (Open Decision — presentation choice.)
3. **slash-rename timing** — do the ~21 consumer `/cortex-core:backlog` references move in 316 or 317? The epic assigns the consumer-routing + rename pass to **317 (P6)**. Lean: 316 fixes **only the moved skill's own body** (its self-refs and its `/cortex-core:backlog-author` call); defer the other consumers to 317. (Open Decision — interim-window tradeoff; see Open Questions.)
4. **backlog.md amendment** — minimal vs thorough: amend Functional-Requirement lines (20/21/24) **and** add an architectural-constraints bullet (visible at both requirement and architecture level).
5. **ADR** — none for 316 (resolved above).

## Cross-Plugin Topology & Namespace

- **Dependency direction is safe**: cortex-backlog → cortex-core (optional add-on depends on base). No supported install of cortex-backlog *without* cortex-core. The prerequisite is currently expressed by repo convention in prose (like cortex-overnight); `dependencies: ["cortex-core"]` in plugin.json is the formal alternative (Open Decision).
- **backlog-author is not orphaned** when cortex-backlog is absent: independent callers are `skills/discovery/references/decompose.md` (cortex-core) and `skills/morning-review/SKILL.md:91` + `references/walkthrough.md:413` (cortex-overnight). This is the load-bearing reason it stays in core.
- **Live `/cortex-core:backlog` references (≈21)** in `skills/dev/SKILL.md`, `skills/discovery/references/decompose.md`, `skills/lifecycle/references/clarify.md`, `skills/interview/SKILL.md`, `docs/agentic-layer.md`, `docs/backlog.md`, `docs/overnight.md`, `tests/fixtures/backlog_author/valid_five_section.md` — these go stale on the namespace change. Historical `cortex/lifecycle/**` and `cortex/research/**` references are **excluded** (never edit). The epic routes these consumer edits through 317's single-pass.
- **Mirrors auto-update**: editing canonical `skills/*` and rebuilding refreshes `plugins/cortex-core/skills/*` mirrors; only canonical files are hand-edited.

## Adversarial Review

1. **`build-plugin` orphan (CONFIRMED, critical)**: `rsync --delete` runs per-skill only; a skill removed from the array is never rsynced, so `plugins/cortex-core/skills/backlog/` is left orphaned and the drift gate (no diff on an untouched committed dir) won't catch it. **Mitigation**: explicit `git rm -r plugins/cortex-core/skills/backlog/` in the commit. (Optional durable alternative: harden the recipe to prune skill dirs not in the array — Open Decision.)
2. **Cross-plugin call is a real runtime path, but already proven (REFRAMED)**: morning-review invokes bare `/backlog-author compose` cross-plugin (cortex-overnight→cortex-core) in production today, so cross-plugin skill resolution demonstrably works — the move is **not** a hard break. Still, fully-qualify `skills/backlog/SKILL.md`'s call to `/cortex-core:backlog-author` for explicitness, and verify both skills surface post-install.
3. **PLUGINS dict pre-existing gap (NOTED, not a blocker)**: the dict omits 4 cortex-core skills today; the minimal edit (drop backlog, add cortex-backlog) is correct and sufficient — drift gate enforces the omitted skills' parity. Adversarial overstated this as a blocker.
4. **No marketplace completeness test (CONFIRMED)**: add cortex-backlog to marketplace.json for discoverability; it is not gated.
5. **No programmatic Python consumer** of the `/cortex-core:backlog` *slash* command (overnight/dashboard/hooks all use the `cortex-*` CLI or import the module) — so the stale-string window is documentation/guidance, not pipeline breakage.

## Open Questions

- **Slash-rename timing for the ~21 consumer references** (the one decision carried to the user): confine 316 to the moved skill's own body and defer consumer renames to 317 (recommended; interim window is low-risk — cross-plugin bare resolution works, releases are tag-based so users cross both tickets in one version bump), **or** pull the rename into 316 (no interim window, but widens "packaging-only" scope and risks 317 conflicts). **Deferred: resolved with the user at the Research→Spec boundary (see Decision below); the answer anchors the spec's scope.**
- **Orphaned-mirror cleanup mechanism** — **Resolved**: one-time `git rm -r plugins/cortex-core/skills/backlog/` in this commit. Minimal and correct per solution-horizon (skill relocation is rare; no planned repeat). Recipe-hardening to auto-prune orphaned skill dirs is noted as a possible future build-infra improvement, not 316 scope.
- **plugin.json optionality/dependency fields** — **Resolved**: minimal `{name,description,author}` matching the cortex-overnight precedent the area doc tells us to follow; document the cortex-core prerequisite + optionality in docs prose. `defaultEnabled:false` / `dependencies:["cortex-core"]` are flagged as a possible repo-wide enhancement (applies to cortex-overnight too) for a separate ticket, not 316.
- **docs/setup.md OPTIONAL-marking form** — **Resolved**: prose-prerequisite (matches cortex-overnight; minimal-table ethos) + "six"→"seven"; amend backlog.md's literal "OPTIONAL in the table" wording to "documented as optional in docs/setup.md".
- **Pre-existing PLUGINS-dict gap** — **Resolved**: leave as-is. The 4 missing cortex-core entries are a pre-existing coverage gap (drift gate still enforces their byte-parity); fixing it is out of packaging scope and would be its own follow-up.

## Decision (Research→Spec boundary)

**User decision (slash-rename timing): rename EVERYTHING in 316, comprehensively.** 316 now includes the full consumer-rename `/cortex-core:backlog` → `/cortex-backlog:backlog` across all live files (the work the epic had tentatively assigned to 317). Consequence: **317's scope shrinks to backend-routing only** (branch on `cortex-read-backlog-backend`); its rename sub-step is satisfied by 316. The moved skill's `/backlog-author` call still becomes the fully-qualified `/cortex-core:backlog-author` (backlog-author stays in cortex-core).

### Authoritative rename inventory (complete — "catch everything")

**RENAME `/cortex-core:backlog` → `/cortex-backlog:backlog` — 20 references across 10 live files:**

- `skills/backlog/SKILL.md` — lines 3 (description trigger phrase), 26, 40, 92, 109
- `skills/dev/SKILL.md` — lines 141 (`add`), 151 (`new`), 233 (`new`)
- `skills/discovery/references/decompose.md` — line 138 (`add`)
- `skills/lifecycle/references/clarify.md` — line 19 (`new`)
- `docs/agentic-layer.md` — lines 143 (`pick`), 250 (`reindex`)
- `docs/backlog.md` — lines 6, 69 (heading), 71, 74
- `docs/overnight.md` — lines 107, 261 (`pick`)
- `cortex_command/init/templates/cortex/backlog/README.md` — line 16 (scaffolded into consumer repos)
- `tests/fixtures/backlog_author/valid_five_section.md` — line 15 (example prose)

**KEEP (do NOT rename — backlog-author stays in cortex-core): 2 references** — `skills/interview/SKILL.md` lines 3 and 10 (`/cortex-core:backlog-author`). Plugin mirrors under `plugins/**` auto-regenerate; historical `cortex/lifecycle/**`, `cortex/research/**`, and `CHANGELOG.md` are excluded.

### Three rename gotchas (verified — fold into Spec/Plan acceptance):

1. **L1 ratchet break (must handle)**: `skills/backlog/SKILL.md:3`'s description carries the trigger phrase `"/cortex-core:backlog"`; backlog's measured L1 surface is **319B = exactly its budget row** in `tests/test_l1_surface_ratchet.py`. Renaming to `/cortex-backlog:backlog` adds ~3 bytes → ~322B, exceeding the cap. **Resolve** either by trimming ~3B from the `description`/`when_to_use` surface, or by raising the `backlog` budget row to 322 **with documented rationale + this lifecycle-id** (the re-cap-with-rationale rule from project.md's L1 ratchet constraint). Recommend trimming if painless, else a documented re-cap.
2. **init-template hash bump (must co-land)**: `cortex_command/init/templates/cortex/backlog/README.md` is listed in `scaffold.py:_HASH_INPUT_TEMPLATES` (line 70). Editing line 16 requires bumping the init-artifacts hash in `scaffold.py`, co-landing in the same commit, or the init-drift check fails.
3. **Fixture/heading safety (verified low-risk)**: no anchor links target the renamed `docs/backlog.md` heading. `tests/test_backlog_author.py:150` reads `valid_five_section.md` — confirm it validates structure (not the literal `/cortex-core:backlog` string) before renaming the fixture line.

## Considerations Addressed

- **(1) parity membership shape** — Resolved: **move** `cortex-backlog` RESERVED→PLUGIN_NAMES; dual-membership unnecessary (scanner verified; PLUGIN_NAMES covers both candidate and wiring exclusion; word-boundary tokens prevent prefix shadowing).
- **(2) OPTIONAL-marking convention** — Addressed: no OPTIONAL column exists; recommend prose-prerequisite (cortex-overnight precedent) + "six"→"seven"; amend backlog.md's literal table wording. (Open Decision retained for form.)
- **(3) cross-plugin dependency / install-topology** — Addressed: dependency direction cortex-backlog→cortex-core is safe; backlog-author has independent callers; fully-qualify the cross-plugin call; cortex-core prerequisite documented in prose (or via `dependencies`, Open Decision). Cross-plugin resolution proven by existing morning-review usage.
- **(4) prefix-collision regression guard** — Addressed: new `tests/test_cortex_backlog_prefix_collision.py` with exact assertion targets and modeled on `parity_check` collectors; word-boundary semantics confirmed safe.
- **(5) skills-only build mechanics** — Addressed: exact justfile/PLUGINS/marketplace/plugin.json edits enumerated and verified; plugin.json-before-build sequencing and the orphan-cleanup gap surfaced.
- **(6) backlog.md amendment lines** — Addressed: verbatim lines 20/21/24 captured + architectural-constraints bullet; ties to the OPTIONAL-wording softening.
