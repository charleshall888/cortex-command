---
discovery_phase: research
topic: repo-spring-cleaning
audience: end-user installers (people running `cortex init` to use the agentic layer in their own projects), not forkers
created: 2026-05-05
---

# Research: repo-spring-cleaning

> Audit cortex-command for post-plugin-shift junk, stale documentation, and a bloated README. Produce a streamlined share-ready state optimized for end-user installers (not forkers). The README rewrite supersedes #150 and should be more aggressive than that ticket attempted. Active development surfaces (overnight runner, MCP plugin, sandbox) are user-asserted to be settled — verified in §"Active-vs-done verification" below.

## Research Questions

1. **What dead/orphaned code, scripts, hooks, and dirs exist post-plugin-shift?** → **Resolved**: full inventory in §"Junk inventory." 1 stale plugin dir, 4 one-shot scripts, 5 unwired hooks, 1 parity-orphan bin script, plus `landing-page/` (3 files, no consumers). All citation-backed.
2. **What `docs/` files are stale, duplicated, or installer-irrelevant?** → **Resolved**: per-file table in §"Doc inventory." Two true duplications (`agentic-layer.md` skill tables vs `skills-reference.md`; nothing else load-bearing duplicates). Three docs are pure-internal (pipeline / sdk / mcp-contract) and should move to `docs/internals/`. `setup.md` is bloated at 437 lines. `CHANGELOG.md` references two non-existent docs.
3. **What's the right README shape for the installer audience?** → **Resolved**: target ~80 lines (down from 132). Cut Customization/Distribution/Commands H2s (#150 OE-1 carved them out but #150 dropped them from scope). Cut the 19-line ASCII tier/criticality legend. Fold Authentication into the Documentation index. Benchmarks (uv/mise/gh) confirm none of those tools include Distribution/Customization/Auth as README sections.
4. **Where do docs/code lean forker-first that should re-target installers?** → **Resolved**: README sections 8–11 (Customization, Distribution, Commands, What's Inside) are forker-tier; `docs/dashboard.md`, `docs/overnight.md`, and `docs/setup.md` reference `just` recipes that fail outside a clone; CLI-bin row at `README.md:87` lists 9 utilities while the plugin actually ships 16. `requirements/project.md:7` says "shared publicly for others to clone or fork" — language can soften toward installer audience.
5. **What's the lifecycle/research dir archive disposition?** → **Resolved**: 37 lifecycle dirs at root (not 41 as initially reported; aggregate-counting error caught in critical review). ~30 archive-eligible (~19 strict-recipe-eligible + ~11 YAML-events recipe blind spots). **1 delete candidate**: `feat-a/` (genuine test detritus, no backlog ticket). **3 archive candidates initially mis-classified as deletes** (corrected post-review): `add-playwright-htmx-test-patterns-to-dev-toolchain/` → backlog #029 cites it as research source [`backlog/029-...md:59`]; `define-evaluation-rubric-update-...` → backlog #035; `run-claude-api-migrate-to-opus-4-7-...` → backlog #083, parent epic #82 alive. **1 dir with no `events.log`**: `clean-up-active-sessionjson-...` (invisible to all predicate variants; needs separate inspection). `research/` is 32 dirs, ~30 decomposed-and-stale; no `research/archive/` exists. Visibility-cleanup mechanism (gitignore vs relocate) deferred per DR-2 = C.
6. **What residual work did #150 / #148 leave?** → **Resolved**: #150 shipped 8 of 16 spec requirements; **dropped Customization/Distribution/Commands moves explicitly** (the user's perceived bloat). All four #148 stale-doc fixes (N3, N4, N8, N9) DID land — verified by direct grep. One remaining `claude/reference/` ref escaped #148: `requirements/pipeline.md:130`.
7. **Is the active-vs-done assertion accurate (overnight runner / MCP plugin / sandbox)?** → **Resolved**: confirmed. Most recent sandbox ticket (#164) closed today (2026-05-05, commit `64ec3e3`). No tickets in `status: refined`/`in_progress`/`ready`. Cleanup is safe to proceed.

## Codebase Analysis

### Junk inventory

**Verdict legend**: DELETE (confirmed orphan, no consumer), KEEP (live consumer found), INVESTIGATE (ambiguous; needs decision).

#### Code/scripts/dirs

| Path | Verdict | Evidence |
|---|---|---|
| `plugins/cortex-overnight-integration/` | **DELETE** | Stale rename-leftover. Contains only `tests/` with byte-equivalent dupes of `plugins/cortex-overnight/tests/test_overnight_*.py`; references a non-existent `server.py`. Marketplace points at `cortex-overnight` [`.claude-plugin/marketplace.json:33`]; `BUILD_OUTPUT_PLUGINS` lists `cortex-overnight` [`justfile:458`]. |
| `scripts/sweep-skill-namespace.py` | **DELETE** | Header: "One-shot helper … for ticket 122 (R8)" [`scripts/sweep-skill-namespace.py:2`]. `NOT_FOUND(query="sweep-skill-namespace", scope=justfile+CI+skills+hooks+docs)`. |
| `scripts/verify-skill-namespace.py` + `verify-skill-namespace.carve-outs.txt` | **DELETE** | Verifies completed migration. `NOT_FOUND(query="verify-skill-namespace", scope=justfile+CI+tests)`. Carve-outs file's only consumer is the script itself [`scripts/verify-skill-namespace.py:381`]. |
| `scripts/generate-registry.py` | **DELETE** | Generates `skills/registry.json` per docstring. `NOT_FOUND(query="skills/registry.json", scope=repo)` — output never landed. |
| `scripts/migrate-namespace.py` (+ `tests/test_migrate_namespace.py`) | **INVESTIGATE → likely DELETE** | One-shot for ticket 120 (completed). Sole consumer is a test of the one-shot. Header: "ticket 120 to prepare … cortex-interactive plugin" [`scripts/migrate-namespace.py:2`]. Recommend delete with its test. |
| `bin/cortex-validate-spec` | **INVESTIGATE → KEEP-and-allowlist OR DELETE** | Sole consumer: `justfile:327` recipe `validate-spec`. `NOT_FOUND` in any SKILL.md, hook, doc. Not in `bin/.parity-exceptions.md`. Either add to allowlist with `maintainer-only-tool` rationale or delete (and drop the recipe). |
| `landing-page/` (3 files: `prompt-1-foundation.md`, `prompt-2-pipeline.md`, `README.md`) | **INVESTIGATE** | Marketing-prompt material for a Claude Design landing page. `NOT_FOUND(query="landing-page", scope=*.md+*.json+justfile+*.toml+*.sh+*.py excluding lifecycle/research/retros)`. Either keep as historical artifact (move to `docs/landing-page/`?) or delete. Decision is content-policy; not a code orphan. |
| `claude/hooks/cortex-output-filter.sh` + `claude/hooks/output-filters.conf` | **INVESTIGATE → likely DELETE** | Was deployed by retired `cortex setup`. `NOT_FOUND` in any in-repo `hooks.json` or `cortex_command/init/`. Per `backlog/120-*.md:36`, placement was "deferred" — defer is now stale. Either re-decide deploy path or delete. |
| `claude/hooks/cortex-sync-permissions.py` | **INVESTIGATE → likely DELETE** | Same status as `cortex-output-filter.sh`. No current deploy mechanism after `cortex setup` retirement. |
| `claude/hooks/setup-github-pat.sh` | **DELETE** | Manual-wire helper. `setup-github-pat` justfile recipe **no longer exists** (`grep -n 'setup-github-pat' justfile` returns 0 hits — recipe was removed; this hook was its target). True orphan now. |
| `claude/hooks/bell.ps1` | **INVESTIGATE → likely DELETE** | Manual-wire helper, Windows-only. Documented at `docs/agentic-layer.md:214`. Cortex-command is macOS-primary per `requirements/project.md`. |
| `debug/` | **KEEP** | Documented diagnose-skill fallback write-target [`skills/diagnose/SKILL.md:281,283`]. Entries are intentional breadcrumbs. |
| `claude/statusline.sh` + `statusline.ps1` | **KEEP** | Forker-manual-wire path documented at `docs/setup.md:319-327`. Audience-noise but installer can skip. |
| `cortex_command/` Python package | **KEEP** | All sub-packages (`backlog/`, `dashboard/`, `init/`, `overnight/`, `pipeline/`) actively imported; all `[project.scripts]` resolve [`pyproject.toml:19-25`]. `[premise-unverified: not-searched]` for sub-module dead code (functions/classes within live modules). |
| `bin/cortex-{archive-rewrite-paths,archive-sample-select,audit-doc,backlog-ready,check-parity,commit-preflight,count-tokens,git-sync-rebase,jcc,load-parent-epic,morning-review-complete-session,morning-review-gc-demo-worktrees,resolve-backlog-item,log-invocation,invocation-report}` | **KEEP** | All have ≥1 SKILL.md/justfile/docs/test consumer. |
| `plugins/{android-dev-extras,cortex-dev-extras,cortex-pr-review,cortex-ui-extras,cortex-core,cortex-overnight}` | **KEEP** | All have marketplace entries [`.claude-plugin/marketplace.json:13-47`] and either `HAND_MAINTAINED_PLUGINS` or `BUILD_OUTPUT_PLUGINS` slot [`justfile:458-459`]. |
| `skills/` (16 dirs) | **KEEP** | All 16 mapped via `justfile:480,486` build-plugin recipe; all have SKILL.md present. |

### Doc inventory

#### `docs/` per-file disposition

| File | Audience | Verdict | Key issues |
|---|---|---|---|
| `docs/setup.md` | installer (mostly) + forker (statusline, contributor) | **TRIM** | 437 lines. Bloat: 7-step `cortex init` explainer (L107-128), full `lifecycle.config.md` schema (L130-160), `CLAUDE_CONFIG_DIR` § (L352-388, forker-tier). Auth § (L219-268) is canonical and right-sized. |
| `docs/agentic-layer.md` | mixed (installer for first half, maintainer for L199-313) | **TRIM + REWRITE pointers** | 327 lines. Three stale "bash overnight runner" mentions [`L183`, `L187`, `L313`]; runner is now Python `cortex overnight start`. Skill tables duplicate `skills-reference.md`. |
| `docs/skills-reference.md` | installer | **MERGE source-of-truth target** | Lower duplication tax to keep this and trim `agentic-layer.md`'s table. |
| `docs/overnight.md` | installer (Quick-Start) + operator | **KEEP-AS-IS w/ tweaks** | `just overnight-run` / `just overnight-smoke-test` (L28, L30, L244, L247, L265) are clone-only — should be flagged or replaced with `cortex` equivalents. Layer split with `overnight-operations.md` is intentional and defensible. |
| `docs/overnight-operations.md` | maintainer / operator | **KEEP-AS-IS** | 702 lines, owns round-loop per CLAUDE.md. Out of installer noise budget. |
| `docs/pipeline.md` | maintainer | **MOVE → `docs/internals/`** | Self-labels "Internal reference — not a user-facing skill" [`docs/pipeline.md:5`]. |
| `docs/sdk.md` | maintainer | **MOVE → `docs/internals/`** | Owns SDK model-selection. Maintainer-only. |
| `docs/mcp-contract.md` | maintainer | **MOVE → `docs/internals/`** | Pure CLI/MCP plugin contract internal. |
| `docs/mcp-server.md` | installer (registration) + operator (recovery) | **KEEP-AS-IS** | Registration § is installer-load-bearing. |
| `docs/plugin-development.md` | maintainer | **KEEP-AS-IS or MOVE → `docs/internals/`** | 105 lines, contributor-scope. |
| `docs/release-process.md` | maintainer | **KEEP-AS-IS or MOVE → `docs/internals/`** | Maintainer-only. |
| `docs/dashboard.md` | installer (mostly) | **TRIM** | L14 `just dashboard` is clone-only; either add `cortex dashboard` verb or flag as contributor-only. |
| `docs/backlog.md` | mixed | **TRIM** | L198-234 "Global Deployment (Cross-Repo Use)" §  belongs in `plugin-development.md`. |
| `docs/interactive-phases.md` | installer-onboarding | **KEEP-AS-IS** | Most installer-friendly deep doc. Some duplication w/ `agentic-layer.md` phase map but tolerable. |

#### Root-level docs

| File | Verdict | Key issues |
|---|---|---|
| `README.md` | **REWRITE** | 132 lines; target ~80. See §"README target shape." |
| `CLAUDE.md` | **KEEP-AS-IS** | 100-line cap honored; maintainer-only. |
| `CHANGELOG.md` | **TRIM** | L21-22 reference `docs/install.md` and `docs/migration-no-clone-install.md` — **neither file exists** (`ls` confirms). Rewrite v0.1.0 entry to point at `docs/setup.md`. |
| `lifecycle.config.md` | **KEEP-AS-IS** | Live config for cortex-command itself. |
| `LICENSE` | **KEEP-AS-IS** | MIT. |
| `install.sh` | **KEEP-AS-IS** | 51 lines, focused, correct. Tag pinned to v0.1.0 [`install.sh:41`] — bump per release-process.md. |

#### `requirements/` per-file (mostly maintainer-internal)

| File | Verdict | Issue |
|---|---|---|
| `requirements/project.md` | **TRIM (1 line)** | L7 "shared publicly for others to clone or fork" — soften to lead with installers per audience clarification. |
| `requirements/pipeline.md` | **TRIM (1 line)** | L130 references `claude/reference/output-floors.md` — directory retired in #117. **#148 N8 leftover that escaped that ticket's grep.** |
| `requirements/multi-agent.md`, `observability.md`, `remote-access.md` | **KEEP-AS-IS** | Internal scope intact. |

#### Stale-path hot list (post-#148 residual)

- `requirements/pipeline.md:130` — `claude/reference/output-floors.md` (retired)
- `CHANGELOG.md:21` — promises `docs/install.md` (does not exist)
- `CHANGELOG.md:22` — promises `docs/migration-no-clone-install.md` (does not exist)
- `docs/agentic-layer.md:183`, `L187`, `L313` — "bash runner" / "bash overnight runner" (now Python CLI)
- `README.md:87` — CLI utilities row lists 9; actual `plugins/cortex-core/bin/` ships ~16

`NOT_FOUND(query="~/.claude/skills/", scope=docs/+requirements/+README.md+CLAUDE.md+CHANGELOG.md+install.sh)` — clean post-#148.
`NOT_FOUND(query="~/.claude/hooks/", scope=same)` — clean.
`NOT_FOUND(query="cortex-interactive", scope=same)` — clean (renamed to `cortex-core`).
`NOT_FOUND(query="ln -s.*~/.claude", scope=justfile)` — N9 fully resolved. Recipe `setup-github-pat` was removed entirely.

### README current anatomy + #150 residual

Current `README.md` is 132 lines, 13 sections. Audience score (H/M/L for **Installer**):

| Lines | Section | Installer score | Disposition |
|-------|---------|------|------|
| 1–9 | Title + value-prop pitch | M | trim para 3 (distribution-mechanics blur) |
| 11–29 | ASCII pipeline diagram + tier/criticality legend | M | **CUT** — 19 lines; legend (L20-28) is concept-encyclopedia, not pitch |
| 31–35 | Prerequisites | H | keep |
| 36–50 | Quickstart | H | keep |
| 52–54 | Plugin auto-update + extras-tier callout | M | move to setup.md |
| 56 | Verification pointer | H | keep |
| 58–71 | Plugin roster | M | trim header/footer prose, keep table |
| 73–75 | Authentication pointer | L | fold into Documentation index |
| 77–88 | What's Inside | L | **CUT** (user decision post-critical-review). Installer pre-install evaluation does not need a repo-structure tour; Plugin roster + Docs index already cover decision-relevant surface. CLI-bin row (L87) is a recurring drift vector unenforced by parity check. Repo-structure overview lives in `CLAUDE.md` for the forker / maintainer audience. |
| 89–91 | Customization | L | **MOVE to setup.md** (#150 OE-1 target, dropped) |
| 93–100 | Distribution | L | **MOVE to setup.md** (#150 OE-1 target, dropped) |
| 102–115 | Commands | L | **MOVE to setup.md** (#150 OE-1 target, dropped). Note: setup.md Troubleshooting (currently L49-53) becomes the recovery surface for installers whose `cortex` binary is missing/broken — `cortex --help` is unreachable in that state. Verify Troubleshooting covers `cortex: command not found` AND surfaces the verify-install command (`cortex --print-root`) before cutting Commands H2. |
| 117–128 | Documentation index | M | keep, expand by 1 row (Authentication) |
| 130–132 | License | L | keep |

**#150 residual analysis** (spec at `lifecycle/restructure-readme-and-setupmd-for-clearer-onboarding/spec.md`): of 16 spec requirements, 8 shipped cleanly (R1, R2, R3, R4, R7, R12, R15, R16). R4 shipped a 9-utility list that is **already stale** (plugin ships ~16). R5 (kill ASCII diagram) shipped partially — old 35-line diagram removed, but a new 19-line legend was added. **OE-1's three target moves (Customization, Distribution, Commands) were dropped from #150's scope** — these are the user's currently perceived bloat.

### Lifecycle / research archive state

| Surface | Count | Verdict |
|---|---|---|
| `lifecycle/` top-level (excluding `archive/`, `sessions/`) | 37 dirs | ~30 archive-eligible (~19 recipe-strict, ~11 YAML-blind), ~6 in-flight/recent-keep, 1 delete (`feat-a/`), 3 archive (was mis-classified as delete pre-review) |
| `lifecycle/archive/` | 111 dirs | already archived |
| `research/` top-level | 32 dirs | ~30 decomposed-and-stale; 1 active (this); 1 candidate-keep (`opus-4-7-harness-adaptation/` — epic #82 alive per CLAUDE.md) |
| `research/archive/` | does not exist | needs creation |

**Archive recipe blind spot**: `justfile:212` greps for the JSON-quoted token `"feature_complete"` only. Modern lifecycle dirs use YAML-form events (e.g. `apply-per-spawn-sandboxfilesystemdenywrite-...`). ~11 complete dirs are silently skipped. **Recommended fix** (post-critical-review): anchored alternation regex `grep -qE '"event":[[:space:]]*"feature_complete"|^[[:space:]]*event:[[:space:]]*feature_complete[[:space:]]*$'`. Drop-JSON-quoting alone is line-noise fragile (any future task narrative mentioning "feature_complete" would trip archive); the alternation is safer.

**Delete candidate** (genuine test detritus, no backlog ticket, no cross-references):
- `lifecycle/feat-a/` (42 ERROR-loop events from 2026-04-14, no `index.md`/`research.md`/`spec.md`)

**Archive candidates initially mis-classified as deletes** (corrected post-critical-review — direct backlog grep showed all three have `status: complete` tickets):
- `lifecycle/add-playwright-htmx-test-patterns-to-dev-toolchain/` — backlog #029 cites it at `backlog/029-...md:59` as load-bearing research source. **Archive, do not delete.**
- `lifecycle/define-evaluation-rubric-update-lifecycle-spec-template-create-dashboard-context-md/` — backlog #035 (status: complete). Archive.
- `lifecycle/run-claude-api-migrate-to-opus-4-7-on-throwaway-branch-and-report-diff/` — backlog #083 (status: complete), parent epic #82 alive per CLAUDE.md. Archive.

**Edge case** (separate disposition needed):
- `lifecycle/clean-up-active-sessionjson-when-overnight-session-transitions-to-phasecomplete/` — has no `events.log` at all; invisible to all predicate variants. Inspect manually before bulk-archive run.

**Recipe rewrite scope** (post-critical-review): `bin/cortex-archive-rewrite-paths` walks every `*.md` under repo root excluding only `.git/`, `lifecycle/archive/`, `lifecycle/sessions/`, `retros/`. Will silently rewrite paths in `research/repo-spring-cleaning/research.md` (this artifact) AND `research/opus-4-7-harness-adaptation/research.md` (alive epic). **Ordering constraint**: commit decompose output BEFORE running the recipe, OR add `research/repo-spring-cleaning/` to `--exclude-dir` if the recipe is run mid-decompose.

**Visibility for installer audience**: deferred per DR-2 = C. The lifecycle-archive recipe run + research-archive creation drop ~30 dirs into `archive/` subdirs regardless of mechanism choice; revisit visibility cleanup after observing post-archive GitHub root render.

### Active-vs-done verification

| Module | Verdict | Evidence |
|---|---|---|
| Overnight runner (`cortex_command/overnight/`) | **DONE** | 83 commits in last 2 weeks but all sandbox/lifecycle-163 work; #149 (last functional ticket) `status: complete`. Only #142 open (`status: backlog`, `priority: contingent`). |
| MCP plugin (`plugins/cortex-overnight/server.py`) | **DONE** | Recent commits limited to sandbox preflight gate addition + sync. #148 MCP hardening tasks closed. No open MCP-tagged tickets. |
| Sandbox stack | **JUST CLOSED (today)** | Lifecycle 162/163/164 all complete; commit `64ec3e3` "Close lifecycle 164 with cycle-1 APPROVED verdict" + `5e37bf3` "Pass round_num to _spawn_orchestrator in sandbox test" landed today. Confirm no further commits land before cleanup commit. |

**Active backlog summary** [`grep -h '^status:' backlog/*.md | sort | uniq -c`]:
- 145 complete
- 10 wontfix
- 3 abandoned
- 1 backlog (#142, contingent)
- 1 blocked (#008, upstream Anthropic dependency)
- 1 deferred (#156)

**No** items in `status: refined`, `status: in_progress`, or `status: ready`. Cleanup is collision-safe.

## Web & Documentation Research

### Installer-first dev-tool README benchmarks

| Tool | Lines | Sections | Install snippet | Notable omissions |
|------|-------|----------|-----------------|--------------------|
| uv (astral-sh) | ~280 | 14 | 3 lines (curl) | No config, troubleshooting, env vars, auth |
| mise (jdx) | ~220 | 14 | 8 lines | No plugin docs, troubleshooting, security model, uninstall |
| gh (cli/cli) | ~230 | 12 | 4 lines | No auth/login, config, troubleshooting, plugin architecture |
| fzf | ~1280 | 14 | 3-4 lines | No troubleshooting, internals, perf benchmarks |
| ripgrep | ~1050 | 16 | 3 lines | No troubleshooting, plugin architecture, API docs, upgrade guide |

**Patterns**:
- Install snippet is **3-8 lines** in all five.
- **None** include an Authentication section in the README. Cortex's pointer (L73-75) is on-pattern.
- **None** include "Distribution" mechanics (uv tool internals, upgrade path, fork install URLs). Cortex's L93-100 is an outlier.
- **None** include "Customization" policy. Cortex's L89-91 is an outlier.
- Quickstart-then-link-out is the dominant pattern.
- Reference class for cortex is uv/mise/gh (220-280 lines, narrow-scope tools), not fzf/ripgrep.

### Recommended README target shape

Length: **~80 lines** (currently 132). Sections in order:

1. **Title + 1-paragraph pitch** (~6 lines) — drop distribution-mechanics sentence
2. **Workflow at a glance** (~5 lines prose, link to `docs/agentic-layer.md`) — cut ASCII diagram and legend
3. **Prerequisites** (~5 lines) — keep as-is
4. **Quickstart** (~14 lines, 3-step block) — keep
5. **Plugin roster** (~12 lines, 6-row table) — trim intro/outro
6. **Documentation** (~12 lines, expand by 1 row to absorb Authentication pointer) — keep
7. **License** (~1 line) — keep

Sections to remove entirely (move to `docs/setup.md` if not already): What's Inside, Customization, Distribution, Commands, standalone Authentication H2.

## Domain & Prior Art

Skipped — narrow tactical cleanup with limited cross-domain pattern relevance beyond the installer-README benchmarking already covered.

## Feasibility Assessment

| ID | Approach | Effort | Risks | Prerequisites |
|---|---|---|---|---|
| F-1 | Aggressive README rewrite (cut Customization/Distribution/Commands/What's Inside [pending DR-1 user decision], cut ASCII legend, fold Authentication into doc index, keep title→pitch→quickstart→roster→docs index→license) | S | medium-without-prerequisite, low-with-prerequisite. **Critical**: setup.md does NOT currently contain three load-bearing pieces of L93-100 content (`uv run` operates-on-user-project semantics, `uv tool uninstall uv` foot-gun, fork-install URL pattern at L100). Without setup.md additions landing first, the README cut deletes content from the repo rather than relocating it | **Hard gate**: setup.md must contain (a) `uv run` semantics note, (b) uv-self-uninstall foot-gun, (c) forker fork-install URL pattern (`uv tool install git+https://github.com/<your-fork>/cortex-command.git@<branch-or-tag>`), (d) "Upgrade & maintenance" subsection BEFORE the README cut commit lands. Without these, F-1 risk is medium and the cut is a regression |
| F-2 | `docs/setup.md` trim — collapse `cortex init` 7-step explainer, push `lifecycle.config.md` schema to its own reference card, decide whether `CLAUDE_CONFIG_DIR` § stays or moves | S | low — mostly compression. Keep auth and verify-install exactly as-is | None |
| F-3 | Move `pipeline.md` + `sdk.md` + `mcp-contract.md` (and optionally `plugin-development.md` + `release-process.md`) into `docs/internals/` | S | low — pure relocation. Update cross-refs (CLAUDE.md L34 owning-doc rule mentions these) | Find-and-replace cross-refs |
| F-4 | Merge `agentic-layer.md` skill table → `skills-reference.md` and trim agentic-layer.md to diagrams + workflow narratives | S | low — `skills-reference.md` is already canonical-shaped | None |
| F-5 | Stale-path fixes: `requirements/pipeline.md:130`, `CHANGELOG.md:21-22`, `agentic-layer.md:183/187/313` ("bash runner" terminology), README CLI list update | XS | none | None |
| F-6 | Code/script junk deletion (1 plugin dir + 4-5 scripts + 1-3 hooks) | S | low — all have NOT_FOUND evidence. Defer the INVESTIGATE items (claude/hooks/cortex-output-filter.sh + cortex-sync-permissions.py) until placement decision | Confirm `claude/hooks/cortex-output-filter.sh` + `cortex-sync-permissions.py` placement decision (or delete) |
| F-7 | `bin/cortex-validate-spec` — either add to `.parity-exceptions.md` or delete with its `validate-spec` recipe | XS | low | Decide maintainer-only vs orphan |
| F-8 | `landing-page/` — keep / move to `docs/landing-page/` / delete | XS | low | Content-policy decision (no code dependency) |
| F-9a | Pick `justfile:212` archive predicate (anchored alternation regex `grep -qE '"event":[[:space:]]*"feature_complete"\|^[[:space:]]*event:[[:space:]]*feature_complete[[:space:]]*$'`); document rejected options (drop-JSON-quoting fragile; backlog-ticket defer) | XS | none | — |
| F-9b | Produce per-dir disposition table (slug → predicate-hit (json/yaml/none) → backlog-ref → has-cross-refs-in-research/ → recommended-action) for all 37 lifecycle dirs. Catches `clean-up-active-sessionjson-...` no-events.log edge case. | S | low — read-only audit | F-9a chosen predicate |
| F-9c | Execute archive: run recipe with new predicate; manually archive (not delete) 3 mis-classified dirs (#029/#035/#083); delete `feat-a/` only; investigate `clean-up-active-sessionjson-...` edge case separately | M | medium-high — recipe rewrites every `*.md` outside `.git/`/`lifecycle/archive/`/`lifecycle/sessions/`/`retros/` and will silently rewrite this artifact mid-decompose. **Ordering constraint**: commit decompose output before recipe run | F-9a + F-9b + decompose output committed |
| F-10 | Research archive: create `research/archive/`, move ~30 decomposed-and-stale dirs, keep `repo-spring-cleaning/` + `opus-4-7-harness-adaptation/` | S | low — pure relocation; nothing imports research dirs | None |
| F-11 | (Per DR-2 = C, deferred.) Lifecycle/research dir visibility cleanup. If revisited: A = `git rm --cached` + `.gitignore` (S–M), B = relocate to `.cortex/` (M–L). Pure-`.gitignore` is mechanically inert and was rejected during critical review. | (deferred) | — | DR-2 final call (currently C — leave alone post-archive-run) |
| F-12 | (DROPPED post-critical-review.) `requirements/project.md:7` already encodes installer-primary, forker-secondary ("cloning or forking the repo remains a secondary path for advanced users who want to modify the source"). The user's "main audience: installers, not forkers" framing is a **cleanup-audience** clarification, not a **project-audience** redefinition; the existing line already matches. No edit needed. | (dropped) | — | — |

## Decision Records

### DR-1: README rewrite scope — minimally vs aggressively

- **Context**: User's "severely bloated" framing post-#150. Two flavors: (a) cut only the legend block (L20-28) — narrow per spec R5 carve-out; (b) cut all of L11-29 plus the four explicit OE-1 H2s (Customization, Distribution, Commands, What's Inside).
- **Options**:
  - **A — Conservative**: cut legend only; keep phase-flow ASCII; move OE-1 H2s. Lands ~115 lines.
  - **B — Aggressive**: cut all of L11-29; move OE-1 H2s; cut What's Inside; fold Auth pointer into index. Lands ~80 lines.
- **Decision**: **B** (ratified post-critical-review). User's "bare bones" framing + audience narrowing to installers + uv/mise/gh benchmark patterns all point to B. Conservative-A still leaves concept-encyclopedia content above the fold. What's Inside cut specifically resolved at OQ §6: installer pre-install evaluation does not need a repo-structure tour.
- **Trade-offs**: Loses Distribution-section upgrade-path discoverability above the fold. **Mitigation requires content migration, not just pointers**: a Documentation-index row alone does not make absent setup.md content present. Before cutting Distribution, setup.md must gain (a) the `uv run` operates-on-user-project semantics note, (b) the `uv tool uninstall uv` foot-gun, (c) the forker fork-install URL pattern, and (d) an "Upgrade & maintenance" subsection. Until those land, executing the cut deletes content. Acceptable **with hard prerequisite** per F-1 row.

### DR-2: Lifecycle/research dir visibility for installer audience

- **Context**: ~150 historical-artifact dirs at repo root (37 lifecycle + 32 research + 111 already in `lifecycle/archive/`). Installer cloning the repo (or browsing GitHub) sees the bulk before the README's quickstart.
- **Mechanism correction (post-critical-review)**: An earlier draft of this DR proposed `.gitignore`-only hiding as Option A. That mechanism is **inert for already-tracked files** — per gitignore manpage, `.gitignore` only suppresses untracked-file staging; it does NOT remove tracked files from clones or from GitHub's web tree render. All ~150 dirs are currently tracked. Pure-`.gitignore` produces zero visibility benefit. Options re-stated below with correct mechanisms.
- **Options**:
  - **A — `git rm --cached` + `.gitignore`**: remove the dirs from the index (so future clones don't get them in the working tree, though history retains them) and add `.gitignore` patterns to prevent re-staging. Side effects: existing maintainer clones lose their working-tree copies on next pull (mitigation: `cp -r` to a non-tracked location first if maintainer wants local visibility); GitHub web UI stops showing the dirs at HEAD. Effort: S–M (touches ~150 paths in one commit + accompanying `.gitignore`).
  - **B — Structural relocation to `.cortex/lifecycle/` and `.cortex/research/`**: dirs still exist on clone but under a leading-dot directory that GitHub's web UI sorts to the bottom and many file browsers hide by default. Touches every doc cross-ref (CLAUDE.md L48, archive recipe in justfile, sandbox.filesystem.allowWrite path in `cortex_command/init/handler.py`, every `lifecycle/<slug>` reference in research/backlog/skills). Effort: M–L.
  - **C — Leave alone**: accept as-is. Forker-friendly transparency. No effort.
- **Recommendation**: **C — leave alone, defer the visibility cleanup**. Rationale: (i) `requirements/project.md:7` already encodes installer-primary, forker-secondary; the lifecycle/research dirs ARE the institutional memory secondary forkers need; the user's "main audience: installers" framing is a primacy claim, not an exclusivity claim. (ii) A and B both have non-trivial side effects (existing-clone disruption, cross-ref churn) for a benefit (cleaner GitHub root render) that isn't on the user's enumerated cleanup list. (iii) The bigger lever for installer-audience clarity is the README rewrite (DR-1) and `lifecycle-archive` recipe run (F-9), which together drop ~30 dirs into `archive/` regardless of Option chosen. Run those first, observe GitHub root render, decide DR-2 from a smaller baseline.
- **Trade-offs**: C means GitHub root keeps showing ~140 dirs (post-archive-run) until a future signal motivates A or B. Acceptable for now; share-readiness goal is met by README + docs cleanup primarily.

### DR-3: `docs/internals/` subdirectory creation

- **Context**: 5 docs are pure-maintainer (pipeline, sdk, mcp-contract, plugin-development, release-process). Mixed in with installer-facing docs at `docs/` root, they make the docs index look bigger than it is.
- **Options**:
  - **A — Move all 5 to `docs/internals/`** and update README docs index to omit them.
  - **B — Move only the 3 strict-internals (pipeline, sdk, mcp-contract)** and leave plugin-development + release-process at `docs/` root since they're less deeply internal.
  - **C — Don't move; rely on docs-index curation to omit them from the installer-facing list**.
- **Recommendation**: **B**. Strict internals get the visual demotion; plugin-development and release-process stay discoverable for forkers/contributors who do read `docs/`.
- **Trade-offs**: Three relocations + cross-ref updates. Manageable scope.

### DR-4: `claude/hooks/cortex-output-filter.sh` + `cortex-sync-permissions.py` resolution

- **Context**: Both hooks were deployed by `cortex setup` (retired). Both still exist in `claude/hooks/` with no current deploy mechanism. Per `backlog/120-*.md:36`, placement was "deferred."
- **Options**:
  - **A — Delete both**: assume rules-only deployment per CLAUDE.md is final.
  - **B — Move to a documented manual-install path** (e.g., user adds them to their `~/.claude/settings.json` with copy-pasteable instructions in `docs/setup.md`).
  - **C — Wire into a plugin** (e.g., `cortex-core` SessionStart / PreToolUse hooks).
- **Recommendation**: **A — but only with parallel retirement of the requirements line**. `requirements/project.md:36` declares `output-filters.conf` as project-level config under the "Context efficiency" quality attribute. Deleting the implementation without retiring this line creates spec/code drift (caught in critical review). The implementing ticket MUST either (i) retire the `output-filters.conf` mention in `requirements/project.md:36` in the same commit, OR (ii) keep `cortex-output-filter.sh` + `output-filters.conf` and only delete `cortex-sync-permissions.py`.
- **Trade-offs**: Loses helpers that some maintainers may have wired locally. Mitigation: announce in changelog. The audience-shift framing (installer-primary) does NOT retire all forker-tier infrastructure (CLAUDE.md L18 dual-source, L48 setup-githooks, install.sh `CORTEX_REPO_URL` remain) — see "Forker affordance triage" note in Open Questions.

## Open Questions

These are decisions for the Decompose phase or the user, not further research:

1. **DR-2 final call**: deferred per DR-2 = C (leave alone post-archive-run). Critical review surfaced that gitignore-only is mechanically inert; corrected mechanisms (`git rm --cached` + `.gitignore`, or structural relocation) are more invasive. Recommendation: revisit only if post-archive-run GitHub root render is still cluttered.
2. **`landing-page/` disposition**: keep / move / delete (F-8). No code-orphan question — purely content policy. Quick user call.
3. **`bin/cortex-validate-spec`** keep-and-allowlist vs delete (F-7). If `validate-spec` recipe is part of contributor workflow, allowlist; if it's vestigial, delete recipe + script.
4. **`cortex dashboard` verb policy**: confirmed no `dashboard` subcommand in `cortex_command/cli.py:284-628` (subparsers register `overnight`, `mcp-server`, `init`, `upgrade` only). `docs/dashboard.md:14` instructs `just dashboard`, which only works in a clone. Decision needed: (a) ship a `cortex dashboard` verb, (b) flag dashboard as contributor-only-launchable in docs, or (c) cut `docs/dashboard.md` from installer-facing docs index entirely. User decision.
5. **DR-4 `claude/hooks/` cleanup**: delete (A) vs document manual-install (B) vs plugin-wire (C). Recommendation A **with parallel retirement of `requirements/project.md:36`** (caught in critical review — deleting implementation without retiring the requirements line creates spec/code drift). User to confirm A or B/C; if A, the implementing ticket must include the requirements edit.

All open questions resolved during critical review or user decision. Original list preserved below for audit trail; resolutions follow.

### Resolved

6. ~~What's Inside table disposition~~ → **CUT entirely** (user decision, post-critical-review). Rationale: installer pre-install evaluation needs (value-prop, workflow shape, plugins, docs index) are met without repo-structure tour; Plugin roster + Docs index cover the decision-relevant surface. CLI-bin row staleness (L87) is a recurring drift vector — `bin/cortex-check-parity` enforces SKILL.md↔bin parity but not README↔bin, so the drift is unenforced and repeats with every new bin script. Repo-structure mental model is a forker concern (covered by `CLAUDE.md` repository structure section). DR-1 Option B's What's Inside cut ratified.

7. ~~Forker affordance triage principle~~ → **P-A: forker affordances stay unless they cause user-facing noise** (user decision, post-critical-review). Load-bearing reasoning: the maintainer's own development workflow IS a clone-and-commit forker workflow — dual-source enforcement (`CLAUDE.md:18`), `just setup-githooks` (`CLAUDE.md:48`), `install.sh:25` `CORTEX_REPO_URL`, statusline manual-wire (`docs/setup.md:319-327`) are infrastructure the maintainer uses themselves. "Main audience" is a primacy claim about cleanup surface optimization, not an exclusivity claim about retained infrastructure. DR-4 deletes (unwired post-shift hooks) ratify under P-A because those hooks are not forker affordances — they're orphans with no current deploy mechanism. Scope under P-A: README placement-noise migrations (Distribution/Customization/Commands move to setup.md/docs/internals), unwired-hook deletes, stale-doc fixes, CHANGELOG repairs, lifecycle/research archive sweep. **Out of scope**: any change to `install.sh:25` `CORTEX_REPO_URL`, `setup-githooks` recipe, dual-source enforcement infrastructure, statusline manual-wire path, `requirements/project.md:7` "clone or fork" language.

## Round 2 audit (post-decompose validation)

User-requested deeper-research pass after initial decomposition. 4 fresh agents dispatched in parallel: comprehensive junk scan beyond round 1, comprehensive stale-reference scan repo-wide, migration safety audit for #166, active-workflow impact audit. Findings updated tickets #166/#168/#169 surgically.

### Critical safety gaps caught (would have broken `just test`)

- `tests/test_output_filter.sh` (8+ hard refs to deleted hook paths) — orphaned by DR-4=A. Now paired-delete in #168.
- `tests/test_hooks.sh:308-end-of-sync-block` (8+ test cases) + `tests/fixtures/hooks/sync-permissions/` — orphaned by `cortex-sync-permissions.py` deletion. Now paired-delete in #168.
- `tests/test_migrate_namespace.py` + `tests/fixtures/migrate_namespace/` — orphaned by `migrate-namespace.py` deletion. Now paired-delete in #168.

### Factual corrections to round 1 / decompose findings

- **`claude/hooks/setup-github-pat.sh` already deleted** — verified `ls` ENOENT. The file was retired in `lifecycle/apply-post-113-audit-follow-ups-...` Task 10. Round 1's "true orphan now" classification was based on a stale read of the directory. Removed from #168 confirmed-delete list.
- **`plugins/cortex-overnight-integration/tests/` are NOT byte-equivalent dupes** — files differ at L34/L42 (path strings reference non-existent `plugins/cortex-overnight-integration/server.py`). Deletion verdict still stands; description corrected in #168.
- **`docs/agentic-layer.md:183`** does NOT contain bash-runner terminology in current state. The earlier ticket scope listed it; round 2 sweep showed only L187 and L313 are real instances. Plan phase grep will find them.
- **`CLAUDE.md` doc-ownership rule is at line 50, not line 34** as originally cited. Updated in #166.

### Scope expansions (broader than round 1)

- **"bash runner" terminology drift** is far more pervasive than round 1's 3-line scope. Round 2 sweep found 7+ user-facing instances: `skills/overnight/SKILL.md:3,22,391,400,401`; `skills/diagnose/SKILL.md:62`; `docs/overnight.md:8`; `docs/skills-reference.md:59,71`. All added to #166 scope. Plus 30+ runner.sh provenance comments in `cortex_command/overnight/*.py` (acceptable to leave — internal documentation, not user-facing) and one runtime-narration occurrence in `cortex_command/overnight/prompts/orchestrator-round.md` (flagged for plan-phase investigation).
- **Hidden non-`.md` coupling on docs/internals/ move**: `cortex_command/cli.py:268` (user-facing CLI stderr message references `docs/mcp-contract.md`) and `bin/cortex-check-parity:59` (script comment). Both added to #166 scope. The CLI message is critical — without update, installers see broken-link error in CLI output.
- **`docs/overnight-operations.md` cross-refs at L318/326/339/593/599** to pipeline.md/sdk.md path updates — added to #166 scope.
- **`pipeline-not-a-skill` callout migration**: `docs/agentic-layer.md:64` has the only "internal reference, not a user-facing skill" callout. Skill-table dedup must migrate this to `skills-reference.md`, not silently lose it.
- **`docs/backlog.md` Global Deployment cut is NOT clean delete**: `plugin-development.md` does not cover the `Path.cwd()` rule for repo-local dirs or the per-script bin-deployment mechanism. Ticket #166 corrected to require substantive migration before cut.

### Net-new junk surfaced beyond round 1's #168 list

- `cortex_command/overnight/sync-allowlist.conf:36` — dead-code line (post-#129 cleanup never landed).
- `.gitignore:20` `skills/registry.json` — paired cleanup with `generate-registry.py` deletion.
- `.gitignore:53` `debug/test-*/` and `.gitignore:64` `ui-check-results/` — stale globs (low priority, investigate during plan).
- `.mcp.json` playwright entry disabled by default — candidate for removal.
- Add `cortex_command/tests` to `pyproject.toml:[tool.pytest.ini_options].testpaths` — config hygiene.
- `bin/cortex-validate-spec` decision must couple with `justfile:326-327` `validate-spec` recipe (deleting the script orphans the recipe).
- `scripts/validate-callgraph.py:12` — stale `claude/reference/` mention in script comment.
- `skills/requirements/references/gather.md:201` — broken relative link.
- `backlog/133-...md:56` — broken cross-reference to non-existent lifecycle dir.

### Archive recipe blast-radius mitigation (#169)

`bin/cortex-archive-rewrite-paths` walks every `*.md` outside `.git/`/`.venv/`/`lifecycle/archive/`/`lifecycle/sessions/`/`retros/`. **No `--exclude-dir` flag exists.** Round 2 added two mitigation options to #169:
1. Add `--exclude-dir` flag (small bin/ scope expansion within #169).
2. Sequence-and-accept: commit all discovery+epic+ticket artifacts before recipe run; accept rewrites in archived research artifacts as post-archive correct citations.

### Confirmed-clean surfaces (round 2 verified)

- `.github/workflows/{validate,release}.yml` — no path filters, no retired references; tolerate deletes.
- `.githooks/pre-commit` — all 7 phases load-bearing; none reference delete candidates.
- `pyproject.toml` — every dep imported, every entry point resolves.
- `cortex_command/` — no `TODO`/`FIXME`/`XXX` markers anywhere.
- Marketplace `.claude-plugin/marketplace.json` — no rename leftovers.
- `cortex_command/cli.py` subparsers: `overnight`, `mcp-server`, `init`, `upgrade` only (no `dashboard` verb — confirms OQ §4 still open).
- Sandbox preflight gate — no cleanup ticket touches the four watched files.
- MCP plugin contract — no version bump, no `[project.scripts]` change, MCP discovery cache stable.

### `${CLAUDE_SKILL_DIR}` env-var convention (verified, NOT stale)

Round 2 flagged 11 SKILL.md links using `${CLAUDE_SKILL_DIR}/references/...` template. Spot-checked: this is the documented Claude Code env-var convention used pervasively across the canonical `skills/` source (verified in `skills/{discovery,backlog,morning-review,lifecycle,requirements}/SKILL.md`). Not stale; plugin mirrors regenerate the same convention. **No action needed.**

## Notes

- **Sandbox lifecycle 164 closed today** (commit `64ec3e3`). Confirm no further commits land in `cortex_command/overnight/sandbox_settings.py` or `bin/cortex-check-parity` before the cleanup commit, or rebase.
- **`requirements/project.md:7`** already encodes installer-primary, forker-secondary correctly. F-12 was DROPPED post-critical-review; no edit to this line.
- **Citation gaps acknowledged**: `cortex_command/` deep-module dead-code search was module-level only. `[premise-unverified: not-searched]` for sub-module dead functions/classes within live modules. If maintainer wants that pass, file a separate audit ticket.
- **Critical-review residue**: 1 B-class finding (CLI-bin row staleness separable from What's Inside cut decision) folded into Open Question §6. Note: B-class residue not written to lifecycle sidecar — no active lifecycle context (ad-hoc discovery mode).
