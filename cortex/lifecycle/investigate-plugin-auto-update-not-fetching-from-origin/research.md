# Research: Plugin auto-update — best-practice publish/refresh workflow for cortex-core

## Clarified scope

Investigate why `/plugin update cortex-core` did not advance the marketplace clone past `16eb3cc` despite `autoUpdate: true` and 30+ commits on `origin/main`. The user's actual goal is broader than forensics: **what is the best-practice workflow for keeping the cortex-core plugin cache fresh after main is pushed?** The four forensic questions (cadence, fetch-vs-pull, version-bump gating, bug/config/expected) are evidence-gathering inputs to the workflow recommendation, not the final deliverable.

Evidence depth: empirical experiments + public Claude Code docs/SDK; file upstream if behavior remains unclear after that. Time-box: single session.

## Codebase Analysis

### Plugin manifest state (cortex-command repo)

- **`.claude-plugin/marketplace.json`** (repo root) — top-level `version: "1.0.0"`, unchanged since inception. Contains 6 plugin entries with relative `source` paths. No `autoUpdate`/`checkInterval` fields.
- **`plugins/cortex-core/.claude-plugin/plugin.json`** — only `name`, `description`, `author`. **No `version` field.** Same for `plugins/cortex-overnight/.claude-plugin/plugin.json`.
- **Implication**: per Claude Code docs (see Web Research §1), version resolution falls back to commit SHA — every commit *should* be treated as a new version.

### CLI release pipeline (existing)

- **`pyproject.toml`** — `version = "0.1.0"` (CLI source of truth)
- **`.github/workflows/release.yml`** — triggers on tag push matching `v[0-9]+.[0-9]+.[0-9]+`; runs `uv build --wheel` → GitHub Release + wheel asset
- **`.github/workflows/validate.yml`** — runs on every push/PR; skill syntax + call-graph validation; **does not touch plugin/marketplace metadata**
- **No existing workflow modifies `marketplace.json` or `plugin.json` on main push.** Versioning is manual.

### Plugin/CLI coupling

- `plugins/cortex-overnight/server.py:105` — `CLI_PIN = ("v0.1.0", "1.0")` constant
- MCP server detects `CLI_PIN[0]` bump on next tool call and shells out to `uv tool install git+url@<new-tag>` under `flock` at `${XDG_STATE_HOME}/cortex-command/install.lock`
- Tag-before-coupling discipline (`docs/release-process.md:124-135`): tag is pushed first, *then* `CLI_PIN[0]` is bumped — never the reverse, because the plugin references the tag literally
- Post-ticket-141: `cortex_command.cli._dispatch_upgrade()` is **advisory only** — prints `/plugin update` and `uv tool install` instructions, does not auto-install (per `requirements/observability.md` "Install-mutation classifications")

### Marketplace clone behavior

- `~/.claude/plugins/marketplaces/cortex-command/` is a git clone of `github.com:charleshall888/cortex-command.git`
- Cache dir naming: `~/.claude/plugins/cache/cortex-command/cortex-core/<short-sha>/` — SHA matches **marketplace clone working-tree HEAD**, not `origin/main`
- `installed_plugins.json` records both `version` (= cache dir SHA = working-tree HEAD) and `gitCommitSha` (= `origin/main` at install time)
- Empirical: clone stayed at `16eb3cc` while `origin/main` advanced to `5342192`; manual `git -C … fetch origin` produced `16eb3cc..5342192 main -> origin/main`

### Plugin build discipline (relevant if a CI publish path is chosen)

- `just build-plugin` regenerates `plugins/cortex-core/` and `plugins/cortex-overnight/` from canonical sources (`skills/`, `hooks/`, `bin/`)
- `.githooks/pre-commit` enforces dual-source parity — any change to canonical source must include the mirrored plugin update
- Plugin classification (`BUILD_OUTPUT_PLUGINS` vs `HAND_MAINTAINED_PLUGINS`) is enforced by pre-commit; adding a plugin requires editing the classifier

### Files likely to change for a publish/refresh workflow

| File | Change | Purpose |
|---|---|---|
| `plugins/cortex-core/bin/cortex-refresh-plugins` (new) | New bin script | Local `git fetch + reset --hard origin/main` against marketplace clone, with cache invalidation |
| `docs/setup.md` (existing) | Add "keeping plugins fresh" section | Document the refresh story |
| `justfile` (existing) | New recipe (optional) | `just refresh-plugins` wrapper |
| `bin/` (canonical) | Mirror of refresh script | Dual-source discipline |
| `.github/workflows/*.yml` | **No change required for recommended approach** | (CI changes are reserved for tag-bump/version-bump alternatives — see Tradeoffs B) |

## Web Research

### Authoritative quotes from Claude Code docs

**Version is the cache key for updates** (`code.claude.com/docs/en/plugins-reference`, "Version management"):

> "Claude Code uses the plugin's version as the cache key that determines whether an update is available. When you run `/plugin update` or auto-update fires, Claude Code computes the current version and skips the update if it matches what's already installed."

Version resolution order:
1. `version` field in `plugin.json`
2. `version` field in the plugin's marketplace entry in `marketplace.json`
3. Git commit SHA of the plugin's source (for `github`, `url`, `git-subdir`, and relative-path sources in a git-hosted marketplace)
4. `unknown` for `npm` sources or local non-git directories

> "If you set `version` in `plugin.json`, you must bump it every time you want users to receive changes. Pushing new commits alone is not enough… If you're iterating quickly, leave `version` unset so the git commit SHA is used instead."

**`autoUpdate: true` semantics** (`code.claude.com/docs/en/discover-plugins`):

> "Claude Code can automatically update marketplaces and their installed plugins at startup… If any plugins were updated, you'll see a notification prompting you to run `/reload-plugins`."

> "Official Anthropic marketplaces have auto-update enabled by default. **Third-party and local development marketplaces have auto-update disabled by default.**"

> "Background auto-updates run at startup without credential helpers, since interactive prompts would block Claude Code from starting."

**Net**: `autoUpdate: true` fires **at session start only**. No documented background polling cadence. Issue [#10265](https://github.com/anthropics/claude-code/issues/10265) is an open feature request for configurable cadence.

**`/plugin marketplace update` does perform `git pull`** (plugin-marketplaces doc, "Marketplace updates fail in offline environments"):

> "**Cause**: By default, when a `git pull` fails, Claude Code removes the stale clone and attempts to re-clone."

`/plugin update <plugin>` "Updates an individual plugin to its newest available version"; per changelog 2.1.101/2.1.126 it now triggers a marketplace refresh and surfaces a warning if the refresh fails.

### Recent changelog fixes relevant to this symptom

- **2.1.98 (Apr 9, 2026)**: "Fixed `claude plugin update` reporting 'already at the latest version' for git-based marketplace plugins when the remote had newer commits."
- **2.1.101 / 2.1.126 (Apr/May 2026)**: "Improved `/plugin` and `claude plugin update` to show a warning when the marketplace could not be refreshed, instead of silently reporting a stale version."
- **2.1.117 (Apr 22, 2026)**: "background plugin auto-update now auto-installs missing plugin dependencies from marketplaces you've already added."
- **2.1.128 (May 4, 2026)**: "Fixed `/plugin update` never detecting new versions of npm-sourced plugins."

### Open Anthropic issue relevant to cortex-core's bundled hooks

[Issue #52218](https://github.com/anthropics/claude-code/issues/52218) — "Plugin autoUpdate doesn't update `installed_plugins.json`, leaving bundled hooks pinned to stale installPath":

> "When a plugin has `autoUpdate: true`… Claude Code does update the runtime version shown in `/plugin` UI (skills/commands) but fails to update `~/.claude/plugins/installed_plugins.json`. Because bundled hooks load from the `installPath` recorded in `installed_plugins.json`, users remain pinned to the old version's hooks."

> "Status: Not resolved — open issue with `bug` and `has repro` labels."

cortex-core ships bundled hooks. If `autoUpdate` advances the runtime version but not `installed_plugins.json`'s `installPath`, hooks will silently lag.

### Documented publish/refresh workflow for plugin authors

The docs describe **two and only two** subscriber-refresh paths:
1. `autoUpdate: true` on the marketplace entry — at session start, `git pull` of marketplace clone, then re-evaluate each installed plugin's version key.
2. Manual: `/plugin marketplace update <name>` then `/plugin update <plugin>`.

**No webhook, cron, or Anthropic-side cache invalidation API exists.**

**No Anthropic-blessed "auto-bump version and publish on push to main" GitHub Action** is documented. Docs explicitly say: "you can update [the marketplace] by pushing changes to your repository. Users refresh their local copy with `/plugin marketplace update`."

The `claude plugin tag --push` CLI command exists for creating release tags from inside a plugin folder, but it's for the dependency-resolution tag convention (`{plugin-name}--v{version}`), not a separate publish channel.

### Direct answers to the four forensic questions (per docs)

1. **Does `autoUpdate: true` poll origin on any cadence?** No. Refresh-at-session-start only. No background polling. Feature request open at #10265.
2. **Does `/plugin update <name>` `git fetch` or only `git pull` pre-fetched state?** Per docs, performs `git pull` (with re-clone fallback) against the remote — it does fetch fresh state. **However**, see Tradeoffs §"Critical constraint" for contradicting field reports.
3. **Does absence of version-bump signal gate the updater?** Conditionally. If `plugin.json` has a `version` field that isn't bumped, yes — `/plugin update` is a no-op. If absent (cortex-core's case), Claude Code falls back to commit SHA and every new commit *should* be treated as a new version.
4. **Bug, missing config, or expected behavior?** Per docs, most likely **missing config** — `autoUpdate: true` may not actually be set on the cortex-command marketplace entry in `known_marketplaces.json` (third-party default is `false`); OR a pre-2.1.98 Claude Code version; OR a silent refresh failure (now warned in 2.1.101+).

## Requirements & Constraints

From **`requirements/project.md`** (Distribution):
> "Distributed CLI-first as a non-editable wheel installed from a tag-pinned git URL (`uv tool install git+<url>@<tag>`); cloning or forking the repo remains a secondary path for advanced users who want to modify the source."

From **`requirements/project.md`** (Out of Scope):
> "Published packages or reusable modules for others — the `cortex` CLI ships as a non-editable wheel installed from a tag-pinned git URL via `uv tool install git+<url>@<tag>`; PyPI publication remains out of scope."

From **`requirements/observability.md`** (Install-mutation classifications, post-ticket-141):
- The only install-mutation entry point is `_ensure_cortex_installed()` in the MCP server, on first use.
- `cortex_command.cli._dispatch_upgrade()` is **advisory only** — prints instructions, does not auto-install.
- `_orchestrate_upgrade` and `_orchestrate_schema_floor_upgrade` short-circuit under wheel install (no `.git/` at `cortex_root`).

From **`requirements/pipeline.md`** (Dependencies):
> "Pre-install in-flight guard: `cortex` aborts when an active overnight session is detected… bypassable inline via `CORTEX_ALLOW_INSTALL_DURING_RUN=1` (do NOT export)."

From **`CLAUDE.md`** (Conventions):
> "New global utilities ship via the `cortex-core` plugin's `bin/` directory; see `just --list` for available recipes."

### Architectural constraints relevant to the workflow choice

- **Tag-pinned distribution** — applies to the cortex CLI, not the plugin. The plugin is a rolling artifact in the marketplace, not a versioned wheel.
- **Plugin byte-identity requirement** — referenced in the runtime adoption telemetry spec; any refresh mechanism must produce deterministic, reproducible plugin contents.
- **Dual-source enforcement** — anything in `plugins/cortex-core/bin/` must have a canonical source in `bin/`; pre-commit hook enforces.
- **Advisory-only install model post-141** — the cortex-command project has explicitly moved away from auto-installing things in user environments. Any "refresh plugins" mechanism we ship should match that posture (recommend a command; don't silently mutate).

### Scope boundaries

- **In scope**: AI workflow orchestration, plugin and CLI distribution mechanics, observability, global agent configuration.
- **Out of scope (relevant here)**: PyPI publication, application code, machine-config / dotfiles.
- The ticket's own Out of Scope: fixing Claude Code internals (file upstream); bumping `marketplace.json` version as a workaround pending understanding.

## Tradeoffs & Alternatives

### Critical constraint flagged by Tradeoffs agent (contradicts Web Research §"Direct answers")

The Tradeoffs agent's review of community bug threads identified multiple reports that `/plugin update` and `autoUpdate` do **not** in fact `git fetch` against the marketplace clone before checking versions, contradicting the docs' claim that `/plugin update` does `git pull`. Specific issues cited: #36317, #37252, #46081, #29071, #17361. **These specific issue numbers are not independently verified in this research session** — only #52218 and #10265 were directly fetched and confirmed. The contradiction is real, but the specific bug-thread evidence needs verification (see Open Questions).

### Alternative approaches

**A. GitHub Actions on push-to-main bumps `version` in `marketplace.json` + commits + pushes**
- Pros: Forces a clearly-different version string per push.
- Cons: cortex-core has **no** `version` field, so per docs it already uses commit SHA — bumping marketplace.json version is redundant. Adds a CI-driven commit loop on `main` (history noise + risk of CI loops). Directly contradicts the docs' guidance ("leave `version` unset… if iterating quickly").
- Must empirically verify: whether bumping any version field triggers refresh when the marketplace clone isn't being fetched.

**B. GitHub Actions on push-to-main creates an annotated git tag**
- Pros: Aligns with existing `release.yml` and with the cortex CLI's tag-pinned `uv tool install …@v0.1.0` pattern.
- Cons: Requires users to set `ref:` in `extraKnownMarketplaces`; most users today point at the default branch. The underlying clone-refresh question still applies.
- Must empirically verify: whether `/plugin marketplace update` runs `git fetch --tags`; whether changing `ref:` in user settings is honored without re-running `/plugin marketplace add`.

**C. Manual `/plugin update cortex-core` after each main push, relying on `autoUpdate: true`**
- Pros: Zero implementation cost.
- Cons: Empirically already demonstrated not to work (the ticket's repro). `lastUpdated` moves but `origin/main` does not.
- Verification status: failure already empirically observed.

**D. CI-side `git push` to a "release" branch the marketplace tracks**
- Pros: Decouples merged-to-main from shipped-to-users; enables release gating.
- Cons: Adds release-channel concept that doesn't exist today; doesn't solve the underlying clone-refresh question, just relocates it.
- Verification status: same `/plugin update` refresh question; also whether `ref:` is re-read at each Claude Code start.

**E. Documented `cortex-refresh-plugins` shell helper (new bin script)**
- Description: A small script under `plugins/cortex-core/bin/` (with canonical mirror in `bin/`) that runs `git -C ~/.claude/plugins/marketplaces/cortex-command/ fetch origin && git -C … reset --hard origin/main`, optionally clears `~/.claude/plugins/cache/`, optionally touches `~/.claude/plugins/installed_plugins.json` if #52218 applies, and prints SHA delta.
- Pros: **Directly addresses the root cause** if the clone-refresh-skip hypothesis (Tradeoffs §critical) holds. Works today regardless of which docs claim. Composes with the existing `bin/` distribution pattern and dual-source discipline. Zero CI changes. When Anthropic fixes the upstream bug (if there is one), the helper becomes a no-op and can be deprecated. Matches the post-141 "advisory only" posture (recommend a command; don't silently mutate).
- Cons: Manual step (mitigatable via SessionStart hook or `cortex init` extension). Touches `~/.claude/` paths that are not technically owned by cortex-command; future Claude Code releases could change the layout.
- Must empirically verify: (1) that `git pull` in the marketplace clone followed by `~/.claude/plugins/cache/` clear actually causes Claude Code to pick up new plugin contents on next session start; (2) whether `installed_plugins.json` needs touching per #52218.

### Recommended approach: **E** (shell helper / `cortex-refresh-plugins`), keep `plugin.json` version-less, no CI changes — *conditional on empirical verification*.

Rationale:
1. **The bug, if it exists, is on the consumption side.** Every CI-based alternative (A, B, D) tries to make the published artifact "more obviously updated," but if Claude Code doesn't fetch the marketplace clone before checking, no upstream version-bumping helps. A and D would add machinery that doesn't solve the problem.
2. **Claude Code docs explicitly recommend the version-less setup for actively-developed plugins.** cortex-core already does this correctly.
3. **Tag-based releases (B) fit the CLI's distribution model precisely *because* the CLI is a discrete versioned artifact users opt into upgrading.** The plugin is the opposite — a rolling internally-developed catalog. Forcing tag-pinning on the plugin would make day-to-day iteration heavier.
4. **The helper composes with existing patterns.** `plugins/cortex-core/bin/` already ships utilities like `cortex-jcc`, `cortex-update-item`, `cortex-resolve-backlog-item`.
5. **It's removable.** When/if Anthropic fixes the upstream behavior, the helper becomes redundant and can be deleted with a one-line note.

**Conditionality**: this recommendation depends on the empirical experiments in Open Questions confirming that (a) the marketplace clone is not being fetched by `/plugin update`/`autoUpdate`, and (b) the shell-helper refresh path actually causes Claude Code to pick up new content on next session.

## Open Questions

**Documented-behavior vs reported-behavior contradiction** — Per Claude Code docs (Web Research §authoritative quotes), `/plugin marketplace update` performs `git pull` against the marketplace remote. Per community bug reports cited by the Tradeoffs agent, it does not. Resolution requires empirical experiment, not further research.

The following empirical experiments belong in the Spec phase and should produce evidence sufficient to answer all four forensic questions:

1. **Verify `autoUpdate: true` is actually set on the cortex-command marketplace entry** — Read `~/.claude/plugins/known_marketplaces.json` and `~/.claude/settings.json` to confirm the field is `true` for cortex-command and was honored on the most recent session start. **Deferred: will be resolved in Spec by running the read commands.**
2. **Verify Claude Code version is ≥ 2.1.98** — `claude --version` against the install fixing the canonical "already at latest" bug. **Deferred: will be resolved in Spec.**
3. **Run `/plugin marketplace update cortex-command` with a fresh `git log --oneline origin/main..main` snapshot before and after, and check whether the marketplace clone's `origin/main` ref moves** — direct test of whether the command runs `git fetch`. **Deferred: will be resolved in Spec.**
4. **Run the proposed `cortex-refresh-plugins` recipe (`git fetch + reset --hard origin/main + clear cache`) and observe whether the cache dir SHA advances on next session** — direct test of approach E. **Deferred: will be resolved in Spec.**
5. **Verify specific Anthropic bug numbers (#36317, #37252, #46081, #29071, #17361) before citing them in the spec** — the Tradeoffs agent cited these but did not independently verify each via WebFetch in this research session. **Deferred: will be resolved in Spec by spot-checking the specific issue URLs.**
6. **Decide whether `installed_plugins.json` `installPath` needs to be touched as part of the refresh helper** — depends on whether issue #52218 applies to cortex-core's bundled hooks. **Deferred: will be resolved in Spec by reading the file and checking whether the recorded path lags behind the cache dir SHA.**

## Considerations Addressed

(No `research-considerations` were passed by the orchestrator — no parent epic loaded, no Apply'd alignment findings from clarify-critic. Section emitted as required by lifecycle mode but lists no items.)
