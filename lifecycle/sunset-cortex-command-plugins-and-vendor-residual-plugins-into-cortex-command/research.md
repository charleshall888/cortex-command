# Research: Sunset cortex-command-plugins and vendor residual plugins into cortex-command

> Topic: Vendor `android-dev-extras` and `cortex-dev-extras` from `cortex-command-plugins` into `cortex-command/plugins/`, register both in `cortex-command/.claude-plugin/marketplace.json` (modern schema), classify as `HAND_MAINTAINED_PLUGINS` in the justfile, update both READMEs, and **archive** (not delete) the sibling repo on GitHub once parity is verified.
>
> Lifecycle: 147. Tier: complex. Criticality: high.

## Epic Reference

This ticket implements DR-1 (Option C — sunset cortex-command-plugins) from the post-113 discovery research at [`research/post-113-repo-state/research.md`](../../research/post-113-repo-state/research.md). The epic re-examined DR-9's original premise (kept the marketplaces split to avoid forcing global install of orthogonal skills) and found the premise no longer carries under per-plugin install semantics. Discovery already chose Option C and rejected Options A (status quo), B (delete), D (re-home android-dev-extras to a Google upstream), and E. **Do not re-litigate that decision** — research below scopes the *implementation* trajectory only.

## Codebase Analysis

### File inventory of source plugins

**`cortex-command-plugins/plugins/android-dev-extras/` (14 files):**
- Root: `.claude-plugin/plugin.json` (35B, minimal `{"name": "android-dev-extras"}`), `HOW-TO-SYNC.md` (9.3K), `LICENSE` (Apache 2.0, 11K), `NOTICE` (521B)
- `skills/android-cli/`: `SKILL.md` (9.0K, contains `<!-- CFA-PATCH: see plugins/android-dev-extras/HOW-TO-SYNC.md §Accepted divergences -->` and a dynamic `!command -v android` injection); `references/interact.md`, `references/journeys.md`
- `skills/r8-analyzer/`: `SKILL.md` (3.5K); `references/{CONFIGURATION.md, REFLECTION-GUIDE.md, REDUNDANT-RULES.md, KEEP-RULES-IMPACT-HIERARCHY.md}`; `references/android/topic/performance/app-optimization/enable-app-optimization.md` (4-deep nested)
- `skills/edge-to-edge/`: `SKILL.md` (14K)

**`cortex-command-plugins/plugins/cortex-dev-extras/` (8 files):**
- Root: `.claude-plugin/plugin.json` (30B, minimal)
- `skills/devils-advocate/SKILL.md` (6.1K)
- `skills/skill-creator/SKILL.md` (24K) + `references/{contract-patterns.md, orchestrator-patterns.md, output-patterns.md, state-patterns.md, workflows.md}`

Neither plugin has `bin/` or `hooks/` directories.

### Pre-commit dual-source enforcement

`/Users/charlie.hall/Workspaces/cortex-command/.githooks/pre-commit` enforces a 4-phase policy on every commit:
- **Phase 1 (lines 41–62)**: walk `plugins/*/.claude-plugin/plugin.json`, require non-empty `name`, require classification in `BUILD_OUTPUT_PLUGINS` or `HAND_MAINTAINED_PLUGINS` (read dynamically from `justfile:403-404`). **Unclassified plugins fail commits.**
- **Phase 2**: short-circuit decision — only run `just build-plugin` if staged paths match `^(skills/|bin/cortex-|hooks/cortex-validate-commit\.sh$)` or `^plugins/<BUILD_OUTPUT_PLUGIN_NAME>/`.
- **Phase 3**: conditional rebuild via `just build-plugin`.
- **Phase 4 (line 101)**: drift loop iterates `BO[@]` (BUILD_OUTPUT only) and fails on `git diff --quiet -- plugins/$p/` mismatch. HAND_MAINTAINED plugins are skipped from the drift loop.

`justfile:403-404` current state:
```
BUILD_OUTPUT_PLUGINS := "cortex-interactive cortex-overnight-integration"
HAND_MAINTAINED_PLUGINS := "cortex-pr-review cortex-ui-extras"
```

`just build-plugin` only has manifests (justfile:417-449) for BUILD_OUTPUT plugins, mapping canonical top-level `skills/`, `bin/cortex-*`, `hooks/cortex-*.sh` into the plugin tree via `rsync -a --delete`. There is no canonical mirror inside cortex-command for android-dev-extras's three skills or cortex-dev-extras's two skills.

**Classification choice for both new plugins: `HAND_MAINTAINED_PLUGINS`.**
- android-dev-extras: the "build" is HOW-TO-SYNC.md's AI-guided procedure (pulls `dl.google.com/dac/dac_skills.zip` or `gh api repos/android/skills`, applies CFA-PATCH guard positionally, reapplies divergences). Outside rsync's vocabulary; cannot be expressed as a build manifest. Misclassification as BUILD_OUTPUT would either fail Phase 1 (missing manifest case) or wipe the vendored skill files in Phase 4 (no canonical source to rsync from).
- cortex-dev-extras: skills are originals authored in the plugin tree; no canonical source elsewhere to mirror from. Same misclassification consequence.

### Marketplace.json schema parity

**Current cortex-command marketplace** (`/Users/charlie.hall/Workspaces/cortex-command/.claude-plugin/marketplace.json`) uses modern schema:
- Root: `$schema` (json.schemastore.org/claude-code-marketplace.json), `name`, `version`, `owner.{name,email}`, `metadata.description`, `plugins[]`
- Per-plugin: `name`, `source`, `description`, `category`

**Old cortex-command-plugins marketplace** uses minimal schema:
- Root: `name`, `owner.{name,email}`, `plugins[]` (no `$schema`, no `version`, no `metadata`)
- Per-plugin: `name`, `source` only (no `description`, no `category`)
- Critically: **the file still lists `cortex-ui-extras` and `cortex-pr-review`** even though both directories were vendored out by ticket #144. Discovery N1 documents this orphan state.

Required new entries in cortex-command's marketplace.json:
```json
{
  "name": "android-dev-extras",
  "source": "./plugins/android-dev-extras",
  "description": "Android development skills vendored from Google's Android Skills (Apache 2.0): R8 analyzer, edge-to-edge migration, and Android CLI orchestration",
  "category": "development"
},
{
  "name": "cortex-dev-extras",
  "source": "./plugins/cortex-dev-extras",
  "description": "Developer productivity skills: devil's advocate challenge and skill creation guides",
  "category": "development"
}
```

### READMEs to edit

- **`cortex-command/README.md:97-108`** — plugin-roster table currently says "ships four plugins" and notes "android-dev-extras lives in the cortex-command-plugins companion repo." Must become six plugins; link to companion repo must be removed.
- **`cortex-command-plugins/README.md:1-35`** — currently advertises plugins and includes copy-pasteable `enabledPlugins` block. Must become a redirect notice pointing at cortex-command's marketplace.

### CI workflow that dissolves

`cortex-command-plugins/.github/workflows/validate.yml` runs `validate-skill.py` against all plugin trees plus a call-graph guard plus a hardcoded `~/.claude/skills/ui-` grep guard. Currently passes nothing because most plugin dirs have been removed (discovery N2). cortex-command has **no `.github/` directory at all** — vendoring eliminates working CI with no successor.

### Files that will change in cortex-command (summary)

**Created:**
- `plugins/android-dev-extras/` — full tree (14 files: plugin.json, HOW-TO-SYNC.md, LICENSE, NOTICE, plus 3 skills)
- `plugins/cortex-dev-extras/` — full tree (8 files: plugin.json, plus 2 skills)

**Modified:**
- `.claude-plugin/marketplace.json` — add 2 plugin entries
- `justfile:404` — add 2 plugin names to `HAND_MAINTAINED_PLUGINS`
- `README.md:97-108` — plugin-roster table grows from 4 to 6; remove companion-repo reference

**No changes needed:**
- `.githooks/pre-commit` — reads classification dynamically from justfile
- `justfile:417-449` — BUILD_OUTPUT manifests only; HAND_MAINTAINED needs no manifest

**Modified in cortex-command-plugins (separate repo):**
- `README.md` — replace with redirect notice
- `.claude-plugin/marketplace.json` — gut to `plugins: []` or delete the file

## Web Research

### Modern marketplace schema (canonical Anthropic doc)

Schema is documented at [`https://code.claude.com/docs/en/plugin-marketplaces`](https://code.claude.com/docs/en/plugin-marketplaces) (older `docs.claude.com` URLs 301 to `code.claude.com`).

**Per-plugin required fields:** `name`, `source`.
**Per-plugin optional fields:** `description`, `version`, `author`, `homepage`, `repository`, `license`, `keywords`, `category`, `tags`, `strict`, plus component overrides (`skills`, `commands`, `agents`, `hooks`, `mcpServers`, `lspServers`).

**Critical finding:** there are **NO documented deprecation, redirect, archived, sunset, moved-to, or migration fields** in the marketplace.json schema. The 1051-line marketplace doc was grepped for `deprecat|archive|sunset|redirect|migration|moved|tombstone` — only unrelated hits. Sunset must be communicated via existing fields (`description`, `homepage`) plus README plus the GitHub archive banner. There is no in-schema way to express "this plugin moved."

The unofficial schema repo `hesreallyhim/claude-code-json-schema` was archived 2026-04-27 with a note that schemastore.org now hosts the official schemas at `https://json.schemastore.org/claude-code-marketplace.json`.

### `/plugin install` behavior + GitHub archive impact

- `/plugin marketplace add owner/repo` clones the repo into `~/.claude/plugins/known_marketplaces.json` (per-user).
- `/plugin install name@marketplace` reads `marketplace.json`, fetches per `source`, copies into `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`.
- `enabledPlugins` is keyed by `"plugin-name@marketplace-name": true`. **The marketplace name is part of the key.** No auto-migration when a plugin moves between marketplaces; user must `/plugin uninstall` then `/plugin install`.
- Archived GitHub repos remain cloneable and fetchable. `/plugin marketplace add` and the periodic auto-update `git pull` both still succeed against archived repos (no new commits, but no errors).
- `/plugin marketplace remove` warns "Removing a marketplace will uninstall any plugins you installed from it" — so users who manually re-add the new marketplace and remove the old will lose their old enabledPlugins entries.

### Industry sunset patterns (third-party reference)

- **npm**: `npm deprecate` flags packages in CLI output. No marketplace equivalent.
- **Homebrew**: `tap_migrations.json` does automatic redirect from old tap to new. **Closest precedent for marketplace-level sunset.** Claude Code has no equivalent.
- **VS Code Marketplace**: no automated cross-publisher migration. Pattern is manual deprecation announcement + UI strikethrough + "Migrate" button.

Common pattern across all three: (1) ship a deprecation tombstone in the old location pointing at the new, (2) keep the old location read-only/archived but reachable, (3) communicate via README + release notes + (where supported) in-tool deprecation warnings.

### Verification before sunset

Anthropic's canonical pattern: `claude plugin validate .` (checks marketplace.json + plugin.json + skill/agent/command frontmatter + hooks.json schema), then `claude --plugin-dir ./local-plugin` for dry-run install. Industry convention for sibling-repo sunset:
1. Vendor plugins.
2. Run validation on the new location.
3. Install each from the new marketplace into a clean cache and exercise.
4. Optionally diff plugin contents byte-for-byte if literal parity is required.
5. Update old README + (optional) gut old marketplace.json.
6. Archive the old GitHub repo only after verification.

### Anti-patterns to avoid

- **Deleting** the old marketplace repo: irreversible; breaks every existing user's clone permanently.
- **Renaming** the new parent marketplace's `name` to match the sunset one: rejected by Anthropic's reserved-name list.
- **Relying on Claude Code to auto-migrate `enabledPlugins`**: there is no such mechanism.
- **Pushing a "redirect plugin"** in the old marketplace: no schema field to express it; users would just see a broken plugin.
- **Removing the old marketplace from your own settings before users have migrated**: `/plugin marketplace remove` uninstalls all plugins from it locally; don't run before the new install is verified.

## Requirements & Constraints

### Distribution model

- `CLAUDE.md:5,22`: "Ships as a CLI (`uv tool install -e .`) plus plugins installed via `/plugin install`."
- `requirements/project.md:53`: "publishing to PyPI or other registries is out of scope."

The system uses a **single-marketplace strategy** post-DR-1: cortex-command is the authoritative marketplace for all distributed plugins.

### Plugin scope boundaries

- DR-9 (`research/overnight-layer-distribution/research.md:309-314`): originally kept the marketplaces split to "preserve a clean boundary." Premise was: "absorbing extras would force global install of truly orthogonal skills."
- DR-1 (`research/post-113-repo-state/research.md:135-141`): re-examined post-#144. Premise no longer carries — Claude Code plugins install per-plugin, not per-marketplace. A single cortex-command marketplace can list `android-dev-extras` without forcing it on anyone.

### Plugin classification rules

`justfile:403-404` is load-bearing for the dual-source pre-commit policy. Classification is binary: `BUILD_OUTPUT_PLUGINS` (regenerated and drift-checked) or `HAND_MAINTAINED_PLUGINS` (excluded from drift loop). Unclassified plugins fail Phase 1 of the pre-commit hook.

### Maintainability through simplicity

- `requirements/project.md:18-21`: "Complexity: Must earn its place… When in doubt, the simpler solution is correct."
- `requirements/project.md:31-32`: "Maintainability through simplicity: Complexity is managed by iteratively trimming skills and workflows."

The sunset's value case is: replace recurring sync cost (N1, N2, N5 from discovery) with one-time migration cost.

### No backward-compat requirement

Per ticket #147 and the post-113 discovery, the existing user base of `cortex-command-plugins` is small (primarily the maintainer plus chickfila-android — verified during adversarial review). Migration is one-time; users update muscle memory to the new unified marketplace.

### Apache 2.0 obligations

`cortex-command-plugins/plugins/android-dev-extras/LICENSE` is Apache 2.0 verbatim from upstream. `NOTICE` carries attribution and currently states (line 9–10): "Plugin scaffolding (plugin.json, HOW-TO-SYNC.md, marketplace registration) is original and covered by the cortex-command-plugins repository's root LICENSE." The receiving cortex-command repo is **MIT-licensed** at `/Users/charlie.hall/Workspaces/cortex-command/LICENSE`. Apache 2.0 §4(c) requires NOTICE to be carried forward in derivative works. The current NOTICE references a license file that becomes archive-only-readable post-sunset — the reference must be rewritten to point at cortex-command's MIT license file (or to inline the scaffolding-portion's terms).

### Atomic file-based shared state (unaffected)

`requirements/pipeline.md`'s atomic-file-write contract is preserved; vendoring does not change the CLI/plugin coordination surface.

### Bin ownership (unaffected)

Plugin-local `bin/` does not participate in the top-level `bin/cortex-*` mirroring (`CLAUDE.md:18`). Neither vendored plugin ships a `bin/` directory.

## Tradeoffs & Alternatives

### Sequencing

| Option | Pros | Cons |
|---|---|---|
| **(a) Vendor → redirect → archive in one merge train** ✓ recommended | Side-by-side parity check possible; rollback trivial via revert; maintainer dogfooding well-defined | Brief two-install-surface window; collision risk if both marketplaces enabled simultaneously |
| (b) Archive first, then vendor | Forces parity; clear migration signal | Breaks chickfila-android until vendoring lands; rollback requires un-archive + re-push; cannot diff against frozen source |
| (c) Multi-week parallel-run | Soft migration window | Sibling already in N1/N2 broken state; extending window perpetuates orphan failures; ongoing dual-source drift risk |

**Choice: (a) compressed.** Discovery's N1/N2 already prove "leave the old repo live as a parallel marketplace" produces brittle states; multi-week parallel-run repeats that failure mode.

### Plugin classification per plugin

Both plugins fit `HAND_MAINTAINED_PLUGINS`:
- **android-dev-extras**: HOW-TO-SYNC.md's AI-guided procedure cannot be expressed as a `just build-plugin` rsync manifest. CFA-PATCH placement is positional; outside rsync's vocabulary.
- **cortex-dev-extras**: skills are plugin-tree originals; no canonical source elsewhere in cortex-command to mirror from.

Misclassification consequence is loud and immediate: Phase 1 fails ("plugin 'X' not classified") on the first commit attempt.

### Sibling-repo end-state

| Option | Pros | Cons |
|---|---|---|
| **(a) Archive on GitHub** ✓ recommended (user-confirmed during Clarify) | Read-only-but-clonable; reversible via un-archive; pinned URLs continue to resolve; preserves git history including android-dev-extras sync log | marketplace.json is still stale at archive-time unless gutted in the redirect commit |
| (b) Keep alive as no-op redirect marketplace | Updates can propagate | Ongoing maintenance; two sources of truth permanently; Claude Code has no HTTP-redirect semantics — "redirect" is README text only |
| (c) Delete entirely | Eliminates orphan state | Irreversible; breaks pinned URLs; destroys sync history; **explicitly out-of-scope per user choice** |
| (d) Convert to "cortex-command marketplace mirror" | Pinned URLs keep working | Two marketplace.jsons in lockstep forever; defeats sunset goal |

**Choice: (a)** with a redirect-notice-README commit + marketplace.json gutting commit landing **before** archive.

### Marketplace strategy

| Option | Pros | Cons |
|---|---|---|
| **(a) Single existing marketplace.json** ✓ recommended | Single source of truth; matches #144 precedent; per-plugin install means listing ≠ adoption | 6 plugins listed instead of 4 |
| (b) Split into "extras" marketplace inside cortex-command | Cosmetic separation of core vs. extras | Re-creates DR-9's split that DR-1 retired; inconsistent with cortex-pr-review/cortex-ui-extras already in main marketplace |

**Choice: (a)**. Splitting (b) re-introduces the problem the sunset is solving.

### Vendoring style

| Option | Pros | Cons |
|---|---|---|
| (a) Copy with full git history (subtree/filter-repo) | Preserves android-dev-extras sync history | Bigger PR; intermixes cortex-command log with sync-task commits; marginal benefit since HOW-TO-SYNC.md documents provenance |
| **(b) Plain copy without history** ✓ recommended | Simplest; clean single commit; archived sibling preserves history retrievably | `git blame` on CFA-PATCH guard shows "vendored" not original divergence-decision commit |
| (c) Git submodule | True single source of truth | Incompatible with archive (submodule UX awkward against archived target); tooling friction across `cortex setup`, `just build-plugin`, dual-source pre-commit |

**Choice: (b)**. Sibling archive preserves provenance retrievably.

## Adversarial Review

### Compliance defect: NOTICE references the source repo's LICENSE

`cortex-command-plugins/plugins/android-dev-extras/NOTICE` line 9–10:

> "Plugin scaffolding (plugin.json, HOW-TO-SYNC.md, marketplace registration) is original and covered by the **cortex-command-plugins repository's root LICENSE**."

After vendoring, "cortex-command-plugins repository's root LICENSE" is in an archived sibling. cortex-command's root LICENSE is **MIT**, not Apache 2.0. Apache 2.0 §4(c) requires NOTICE to be carried forward in derivative works. The NOTICE must be rewritten before vendoring to point at cortex-command's actual license file (compatible — Apache 2.0 + MIT mix is permitted with proper NOTICE) or to inline the scaffolding-portion's MIT terms explicitly.

### Sibling marketplace.json gutting is in-scope (not just README)

The sibling's `.claude-plugin/marketplace.json` already lists already-removed `cortex-ui-extras` and `cortex-pr-review` (orphans from #144, discovery N1). Users who run `/plugin install cortex-ui-extras@cortex-command-plugins` against the archived marketplace will fail with "plugin source not found" because the source path doesn't exist. The ticket body says "Update README" but does not say "gut marketplace.json." **The redirect is incomplete unless marketplace.json is also reduced to `plugins: []` or the file is deleted.** This must be added to scope.

### Real downstream consumer with both old keys

`/Users/charlie.hall/Workspaces/chickfila-android/.claude/settings.local.json:280-281`:
```
"android-dev-extras@cortex-command-plugins": true,
"cortex-dev-extras@cortex-command-plugins": true
```

This is a known downstream consumer with both old marketplace keys enabled. Migration must be documented as a hand-edit step in the merge train: update chickfila-android's settings.local.json to the new keys.

### Skill collision when both marketplaces enabled simultaneously

If a user has both `android-dev-extras@cortex-command-plugins: true` AND `android-dev-extras@cortex-command: true` enabled, two copies of `android-cli`, `r8-analyzer`, `edge-to-edge` skills are loaded. Slash-command resolution behavior for `/android-cli` (which copy? which CFA-PATCH dynamic injection fires?) is unspecified. The right ordering for users is **uninstall old THEN install new** — opposite to the natural instinct of "verify new before retiring old." This must be documented in the redirect README and the migration recipe.

### HOW-TO-SYNC.md has hardcoded paths that break post-vendor

- Line 49: `python3 scripts/validate-skill.py plugins/android-dev-extras/skills` — script exists in cortex-command (verified identical), but the procedural framing is "from the cortex-command-plugins repo root."
- Line 51: push target is `https://github.com/charleshall888/cortex-command-plugins.git`. Post-archive, push must target `cortex-command.git`.
- Line 73: CFA-PATCH placement-by-frontmatter rule is repo-agnostic; survives.

**HOW-TO-SYNC.md must be rewritten in the vendoring PR.** Otherwise the next AI-guided sync (per line 38: "Ask Claude: 'sync android skills per HOW-TO-SYNC.md'") pushes to a non-existent remote.

### skill-creator is broken-by-vendoring

`skills/skill-creator/SKILL.md` cites:
- `~/.claude/reference/context-file-authoring.md` (line 332), `~/.claude/reference/claude-skills.md` (lines 333, 371) — exist on the maintainer's machine, but `cortex setup` does NOT write them.
- `${CLAUDE_SKILL_DIR}/references/...` (lines 245, 341–345) — unsubstituted variable; doc bug.
- `scripts/init_skill.py`, `scripts/package_skill.py` (lines 312, 387, 393) — **do not exist in cortex-command, do not exist in cortex-command-plugins, do not exist in `~/.claude/skills/skill-creator/`**.
- Line 9 preconditions: "Python 3 available (for init_skill.py and package_skill.py)" — names files that don't exist.

skill-creator is **already broken in its current location** and vendoring inherits the broken state. Three options: (a) fix during vendoring (create the missing scripts and substitute paths), (b) gut the broken references in the SKILL.md during vendoring, or (c) do not vendor skill-creator and treat it as deprecated.

### devils-advocate vs critical-review semantic collision

`/Users/charlie.hall/Workspaces/cortex-command/plugins/cortex-interactive/skills/critical-review/SKILL.md:3` description **explicitly self-bills as superseding** /devils-advocate:

> "More thorough than /devils-advocate because parallel agents remove anchoring bias and produce deeper per-angle coverage than a single sequential pass."

Vendoring devils-advocate creates a self-contradicting marketplace where one official plugin's description deprecates another official plugin's main feature. Both will trigger on "challenge this", "poke holes", "argue against this". Critical-review's description claims it's strictly better. This is a marketplace-quality regression, not just redundancy.

Three options: (a) vendor with description rewrite to differentiate niches (sequential vs parallel; targeted vs broad), (b) rename devils-advocate, (c) retire devils-advocate (don't vendor it) and ship cortex-dev-extras as skill-creator-only (or as nothing if skill-creator is also retired).

### CI gap is total post-archive

cortex-command has no `.github/` directory. cortex-command-plugins's `.github/workflows/validate.yml` runs `validate-skill.py` + `validate-callgraph.py` + a hardcoded `~/.claude/skills/ui-` grep guard. After archive, all three checks vanish with no successor. Future android-dev-extras syncs that introduce malformed YAML would land unchallenged.

Two options: (a) port the workflow to cortex-command (in-scope expansion), (b) explicitly scope-out CI parity in the ticket and accept the regression. Don't let it slip silently.

### The merge train cannot be atomic

Three actions span:
- **cortex-command repo**: vendor PR (2 plugin trees, marketplace.json edit, justfile edit, README plugin-roster table edit, removal of companion-repo link)
- **cortex-command-plugins repo**: redirect-README PR + marketplace.json gutting PR
- **GitHub UI**: archive button on cortex-command-plugins repo

Strict ordering: cortex-command merged → sibling redirect/gutting merged → users (chickfila-android) migrated → sibling archived. Repo B's redirect cannot be merged AFTER archive (archived repos are read-only). This is a non-atomic, multi-step procedure with hand-offs.

Rollback is **not** "git revert A" because users may have already done `/plugin install` from the new marketplace and rebuilt their settings.local.json keys. Rollback must include enabledPlugins-key churn instructions.

### Intra-PR commit ordering matters

Pre-commit Phase 1 fails any commit that introduces a `plugins/X/.claude-plugin/plugin.json` for an unclassified plugin. **The justfile:404 update must be in or before the commit that introduces the new plugin.json files.** If the vendor PR splits "vendor plugins" from "update justfile" into separate commits (a natural rebase shape), the first commit fails.

### Cache-vs-source caveat for HOW-TO-SYNC

`HOW-TO-SYNC.md:37` says "Open a Claude Code session in this plugin directory." Post-vendor, "this plugin directory" is `cortex-command/plugins/android-dev-extras/`. That works for the maintainer editing the cortex-command source clone. **Users who installed cortex-command via `/plugin install` and try to re-sync from `~/.claude/plugins/cache/cortex-command/plugins/android-dev-extras/` are operating on the cache, not the source.** The procedure should explicitly note: "sync only works in a clone of cortex-command, not in the plugin cache."

## Recommended Approach Summary

- **Sequencing**: vendor → redirect README + marketplace.json gut → migrate chickfila-android → archive, all in one merge train (compressed, no multi-week parallel).
- **Classification**: both plugins as `HAND_MAINTAINED_PLUGINS`. One-line edit at `justfile:404`. Justfile update must be in or before the commit that introduces the plugin.json files.
- **Sibling end-state**: GitHub archive after redirect-README and marketplace.json-gut commits land.
- **Marketplace strategy**: single existing `cortex-command/.claude-plugin/marketplace.json` with two new entries using modern schema.
- **Vendoring style**: plain copy without history. Sibling archive preserves provenance.
- **Mandatory in-scope additions surfaced by adversarial review**:
  1. Rewrite `NOTICE` to reference cortex-command's MIT license (not the soon-archived sibling).
  2. Gut `cortex-command-plugins/.claude-plugin/marketplace.json` (set `plugins: []` or delete) before archive.
  3. Rewrite `HOW-TO-SYNC.md` (push target, repo-root framing, cache-vs-source caveat).
  4. Update chickfila-android `settings.local.json` to the new marketplace keys.
  5. Add migration recipe to redirect README (`/plugin uninstall <name>@cortex-command-plugins` then `/plugin install <name>@cortex-command`).
- **Decisions to surface in Spec** (see Open Questions): skill-creator policy, devils-advocate redundancy resolution, CI workflow port-or-scope-out.

## Open Questions

1. **skill-creator policy**: skill-creator is broken in its current location (missing `scripts/init_skill.py`, `scripts/package_skill.py`, unsubstituted `${CLAUDE_SKILL_DIR}`, references to `~/.claude/reference/*` files that `cortex setup` does not deploy). Three options: (a) fix during vendoring — create the missing scripts and substitute paths, (b) gut the broken references in the SKILL.md during vendoring (lighter), (c) do not vendor skill-creator and treat as deprecated. **Deferred to Spec** — consequential decision; user input determines whether the ticket grows by ~scripts worth of scope or shrinks by one skill.

2. **devils-advocate vs critical-review redundancy**: critical-review's description explicitly self-bills as superseding devils-advocate. Three options: (a) vendor with differentiated description (sequential vs parallel niche), (b) rename devils-advocate, (c) do not vendor devils-advocate (retire). **Deferred to Spec** — affects whether cortex-dev-extras ships with 2, 1, or 0 skills.

3. **CI workflow disposition**: cortex-command has no `.github/`. cortex-command-plugins's `validate.yml` dissolves with the archive. Two options: (a) port the workflow to cortex-command in this ticket (in-scope expansion), (b) explicitly scope-out CI parity and accept the regression. **Deferred to Spec** — straightforward decision but should be documented explicitly rather than implicit.

4. **Empirical collision-behavior verification**: the failure mode of "both marketplaces enabled simultaneously" is theorized in adversarial review (per Agent 2: enabledPlugins keys are marketplace-bound, both copies load). **Resolved** — verification happens during implementation as a smoke test, not during spec design. Mitigation is the migration recipe in the redirect README directing users to uninstall-old-first.

5. **NOTICE rewrite phrasing**: Apache 2.0 §4(c) compliance is well-defined; the exact wording is editorial. **Deferred to Spec** — short text decision; user can suggest phrasing or accept a default.
