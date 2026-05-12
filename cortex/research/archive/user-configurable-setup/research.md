# Research: user-configurable-setup

> Investigate how to make the cortex-command agentic layer modularly opt-in:
> users install globally but choose which portions (skills, hooks, permissions,
> lifecycle behaviors, overnight runner, dashboard, plugins) they actually want,
> with a small per-repo config layer that can override or scope behavior locally
> (e.g., "only use project permissions in this repo, ignore global allows").

> **Note**: This artifact was substantially rewritten after critical review.
> The initial version recommended a new `.cortex/config.md` file, named bundles,
> and a SessionStart hook that mutated `~/.claude/settings.json` for the stated
> per-repo permissions use case — all deferred to a phased rollout whose final
> phase was labeled "stretch — may not be needed." Review surfaced that this
> demoted the use case the research was commissioned to investigate, proliferated
> config files against the project's simplicity principle, and bet against active
> upstream Claude Code work. The recommendation now favors reusing existing
> infrastructure and using a documented Claude Code feature (`CLAUDE_CONFIG_DIR`)
> for per-repo scoping, with an explicit upstream-activity check as a prerequisite.

## Research Questions

1. **Full component inventory of the agentic layer.**
   → **Answered.** 26 skills across 4 clusters, 13 hooks, ~20 settings.json sections, 2 rules files, 5 reference docs, 10 bin utilities, overnight runner (Python + bash), dashboard (Flask), conflict pipeline (Python), statusline, notification system, 3 plugins. Authoritative deployment list is the `setup-force` recipe in `justfile`. Full table in Codebase Analysis §1.

2. **Hard dependencies between components.**
   → **Answered.** Three coupling bands: (a) UI toolchain, plugins, reference docs, bin utilities, notifications, dashboard, and all "invocation-only" skills (`skill-creator`, `diagnose`, `harness-review`, `retro`, `evolve`, `fresh`, `devils-advocate`, `requirements`, `pr`, `pr-review`) = **cleanly optional**; (b) overnight runner, critical-review, morning-review, refine = **moderate coupling** (depend on lifecycle/backlog/git/Python); (c) lifecycle skill, backlog, SessionStart hooks (`sync-permissions`, `scan-lifecycle`, `setup-gpg-sandbox-home`), commit + validate-commit hook, dev router = **highly coupled / install floor**. See §2.

3. **Natural bundles / personas.**
   → **Reversed from initial draft — no named bundles.** §2 produces three coupling *bands*, not five bundles. Band C is the install floor (fixed by hard dependencies); Band A items are individually optional with no cross-dependencies that would benefit from bundling. Invented bundles (`core`/`autonomous`/`observability`/`ui`/`meta`) drifted from Band A/B/C mapping and would create a second enable-layer on top of per-component enables. Per-component enable above the install floor is sufficient for 26 skills + 13 hooks. See DR-3.

4. **What can Claude Code settings layering already express, and where does it fall short?**
   → **Answered — this is the hard constraint but it is not permanent.** Merge is **strictly additive for arrays, scalar-wins-by-precedence for scalars, deep-merge for objects**. No negation syntax, no per-hook disable (only all-or-nothing `disableAllHooks: true`). `sandbox.enabled` is a scalar so project can toggle it; sub-arrays merge. Project `.claude/settings.json` **does not walk up parent directories** — open issue anthropics/claude-code#12962 tracks this exact gap. **`CLAUDE_CONFIG_DIR` environment variable can swap the entire user scope per-invocation** — this is a documented Claude Code feature that delivers "scope permissions to this repo" without any settings mutation. See §3 and DR-1.

5. **Shape and location of a per-repo config file.**
   → **Answered — reuse existing `lifecycle.config.md`; do not add a new file.** The file already exists at the project root, is git-committed, is read by lifecycle phases, and is thin enough to accommodate new sections without disruption. Adding a second file would create a distributed refactor across the four phase files that read `lifecycle.config.md` independently (§1.E), with no exit condition for the "dual-read transition." See DR-2.

6. **Install-time vs runtime selection — which for which component type?**
   → **Answered — install-time for skills/hooks via `/setup-merge`; `CLAUDE_CONFIG_DIR` + direnv for per-repo permissions; existing config reads for lifecycle flags.** No new SessionStart mutation layer. The already-shipped `/setup-merge` skill is the natural extension point for install-time selection (Feasibility Row H, rated S effort). See DR-4.

7. **Current `lifecycle.config.md` surface and resolver.**
   → **Answered.** Thin: 4 flags actively read (`test-command`, `commit-artifacts`, `default-tier`, `default-criticality`), 2 documented but not implemented (`skip-specify`, `skip-review`), 1 orphan (`type`). No centralized resolver — each phase reads the file independently. This fragility is exactly why DR-2 refuses to add a second config file. See §1.E.

8. **Prior art — how do comparable tools handle this?**
   → **Answered.** Dominant patterns: (a) declarative `enable = true/false` flag per component, (b) directory-walk cascade with closer-wins semantics, (c) explicit "off" escape hatch. Anti-patterns: bundle-everything with zero discovery, no-subtract merge, recommendations-only enforcement, hidden inter-module deps, destructive sync. The strongest precedent for per-repo scoping is **direnv + per-directory environment variables**, which pairs exactly with `CLAUDE_CONFIG_DIR` as the mechanism for "point Claude Code at a different user scope in this repo." See §4.

---

## Codebase Analysis

### 1. Component Inventory

The authoritative deployment surface is `justfile` (recipes `setup`, `setup-force`, `deploy-*`) combined with `claude/settings.json` hook registration.

#### A. Skills (26)

| Cluster | Skills |
|---------|--------|
| **Core dev flow** | `lifecycle`, `dev`, `discovery`, `refine`, `backlog`, `commit` |
| **Overnight / review** | `overnight`, `morning-review`, `critical-review`, `pr`, `pr-review`, `harness-review` |
| **Lifecycle ancillary** | `research`, `requirements`, `diagnose`, `skill-creator`, `retro`, `evolve`, `fresh`, `devils-advocate` |
| **UI toolchain** | `ui-check`, `ui-lint`, `ui-a11y`, `ui-judge`, `ui-brief`, `ui-setup` |

All 26 deploy via `ln -sfn` in `deploy-skills`.

#### B. Hooks (13)

| Hook | Event | Role | Band |
|------|-------|------|------|
| `cortex-sync-permissions.py` | SessionStart | Merges global permissions into project `settings.local.json` | Install floor |
| `cortex-scan-lifecycle.sh` | SessionStart | Injects session ID into `lifecycle/.session` files | Install floor |
| `cortex-setup-gpg-sandbox-home.sh` | SessionStart | GPG sandbox home for commit signing | Optional |
| `cortex-validate-commit.sh` | PreToolUse (Bash) | **Blocks** invalid git commit messages | Install floor (paired with `commit`) |
| `cortex-output-filter.sh` | PreToolUse (Bash) | Filters verbose bash output (non-blocking) | Optional |
| `cortex-tool-failure-tracker.sh` | PostToolUse (Bash) | Records bash failures for metrics | Optional |
| `cortex-skill-edit-advisor.sh` | PostToolUse (Write/Edit) | Warns on skill/hook edits without lifecycle | Optional |
| `cortex-cleanup-session.sh` | SessionEnd | Cleans temp files and stray worktrees | Optional |
| `cortex-notify.sh` | Notification | Local desktop notification | Optional |
| `cortex-notify-remote.sh` | Notification, Stop | Remote webhook logging | Optional |
| `cortex-permission-audit-log.sh` | Notification | Audit log of permission events | Optional |
| `cortex-worktree-create.sh` | WorktreeCreate | Runs when lifecycle creates worktrees | Moderate (overnight) |
| `cortex-worktree-remove.sh` | WorktreeRemove | Runs when lifecycle removes worktrees | Moderate (overnight) |

#### C. Settings.json sections

Currently handled by `/setup-merge` per-category prompts: `permissions.allow`, `permissions.deny`, hooks block (required vs optional split), sandbox config, statusLine, plugins, apiKeyHelper.

Not yet handled as opt-in: `model`, `effortLevel`, `alwaysThinkingEnabled`, `skipDangerousModePermissionPrompt`, `cleanupPeriodDays`, `env`, `attribution`, `permissions.ask`, `permissions.defaultMode`. These are global scalars — `/setup-merge` documentation already classifies them as "personal, never touch."

#### D. Other components

| Component | What deploys | Coupling |
|-----------|-------------|----------|
| **Rules files** (`claude/rules/*.md`) | Symlinked to `~/.claude/rules/cortex-*.md` | None — advisory context |
| **Reference docs** (5 files) | Symlinked to `~/.claude/reference/` | None — conditionally loaded |
| **Bin utilities** (10 scripts) | Symlinked to `~/.local/bin/` | `overnight-start`, `generate-backlog-index` required by overnight; others independent |
| **Overnight runner** (`claude/overnight/`: 16 Python modules + `runner.sh` + prompts) | Not symlinked — invoked via `overnight-start` + `CORTEX_COMMAND_ROOT` | Depends on: refine/lifecycle, backlog index, git worktrees, Python 3 |
| **Conflict pipeline** (`claude/pipeline/`: ~11 Python modules) | Not symlinked | Imported by overnight runner |
| **Dashboard** (`claude/dashboard/`: Flask app) | Not symlinked — separate process | Reads lifecycle session state |
| **Statusline** (`claude/statusline.sh`) | Symlinked; referenced from `statusLine` in settings | None |
| **Plugins** | `enabledPlugins` in settings (context7, claude-md-management) | None — graceful fallback |

#### E. Current `lifecycle.config.md` surface

Template at `skills/lifecycle/assets/lifecycle.config.md`. Active project root copy at `lifecycle.config.md`.

| Flag | Default | Read by | Status |
|------|---------|---------|--------|
| `test-command` | none | `references/complete.md` | **Active** — runs in complete phase if present |
| `commit-artifacts` | `true` | research, specify, plan, complete | **Active** — controls staging of `lifecycle/` in commits |
| `default-tier` | `simple` | research phase §0 | **Active** — seeds initial complexity |
| `default-criticality` | `medium` | research phase §0 | **Active** — seeds initial criticality |
| `skip-specify` | `false` | — | **Documented but not implemented** |
| `skip-review` | `false` | — | **Documented but not implemented** |
| `type` | inferred | — | **Orphan** — not consulted by any phase |

**No centralized resolver.** Each phase reads `lifecycle.config.md` independently. This is a limitation, but a known one that does not require fixing to land this work — see DR-2 for how the reuse plan accommodates it.

### 2. Hard Dependency Map

Three bands based on what breaks if you opt out.

#### Band A — Cleanly optional (no cascade)

UI toolchain (all 6 `ui-*` skills + `ui-setup`), plugins (`context7`, `claude-md-management`), reference docs, rules files, notifications (`cortex-notify.sh`, `cortex-notify-remote.sh`, `cortex-permission-audit-log.sh`), dashboard, `harness-review`, `skill-creator`, `diagnose`, `retro`, `evolve`, `fresh`, `devils-advocate`, `requirements`, `pr`, `pr-review`, `cortex-output-filter.sh`, `cortex-tool-failure-tracker.sh`, `cortex-skill-edit-advisor.sh`, `cortex-cleanup-session.sh`, `cortex-setup-gpg-sandbox-home.sh`.

Each is invocation-only or advisory. No callers silently break when removed.

#### Band B — Moderate coupling (bundle awareness required)

| Component | Depends on | Opt-out implication |
|-----------|-----------|---------------------|
| `overnight` skill + runner + pipeline | `refine` or `lifecycle`, `backlog`, `generate-backlog-index`, `overnight-start`, git worktrees, Python 3, `CORTEX_COMMAND_ROOT`, `cortex-worktree-*` hooks | Must opt out as a cluster |
| `morning-review` | Overnight session artifacts, `update-item` bin util | Only meaningful if overnight is installed |
| `critical-review` | Auto-invoked from `lifecycle` review phase; reads `requirements/project.md` | Opting out needs explicit skip flag in lifecycle config |
| `discovery` | `backlog`, `requirements/` (optional) | Safe without requirements; needs backlog for ticket creation |
| `refine` | `backlog`, `lifecycle` research/specify, `update-item` | Only meaningful with backlog + lifecycle |

#### Band C — Install floor (cannot opt out without breaking core)

| Component | Why it's load-bearing |
|-----------|----------------------|
| `lifecycle` skill | `dev` routes to it; `refine` invokes it; `overnight` depends on its artifacts |
| `commit` skill + `cortex-validate-commit.sh` hook | Almost every skill transition ends in a commit; validate-commit blocks malformed commits |
| `backlog` skill + `create-backlog-item`/`update-item`/`generate-backlog-index` bin utils | `dev`, `overnight`, `refine`, `discovery`, `morning-review` all depend |
| `cortex-sync-permissions.py`, `cortex-scan-lifecycle.sh` | Run on every session; break permissions merge and `/fresh` respectively |
| `dev` skill | Router for all other workflow skills |

**Band C is the install floor.** Any user of cortex-command must have these. Above Band C, per-component or per-cluster (Band B) opt-in is the unit of selection.

### 3. Per-repo config surface today

- **`lifecycle.config.md`** (project root, committed): Thin YAML frontmatter + free-form review criteria. See §1.E.
- **`.claude/settings.local.json`** (project, git-ignored): Written by `cortex-sync-permissions.py` at SessionStart. Merges global allow/deny/ask into local; also holds `enabledMcpjsonServers`.
- **`requirements/project.md`, `requirements/{area}.md`** (committed): Read by `lifecycle`, `critical-review`, `discovery`.
- **`.claude/` project directory**: Already used for project-local skills.
- **`sandbox.filesystem.allowWrite`**: Merged per-repo by `justfile` during `deploy-config` for `~/cortex-command/lifecycle/sessions/`.

---

## Web & Documentation Research

### Claude Code settings layering — the constraint

Merge semantics (verified via Claude Code docs, as of April 2026):

- **Arrays** concatenated and deduplicated across all scopes. No negation.
- **Scalars** scalar-wins-by-precedence (project > user).
- **Objects** deep-merged.
- **Precedence**: managed > local > project > user.

| Capability | Native support | Workaround |
|-----------|----------------|------------|
| Project ignores user-scope allow list | No | `CLAUDE_CONFIG_DIR` to swap entire user scope; or `defaultMode: "dontAsk"` |
| Project weakens user-scope deny | No (deny is monotonic) | Must remove from user scope directly |
| Project disables one specific user-scope hook | No | `disableAllHooks: true` (all-or-nothing); or swap user scope |
| User/project "final word" over lower scopes | No (managed-only) | None |
| Project `.claude/settings.json` walks up from subdir | No — CWD only | Open issue [#12962](https://github.com/anthropics/claude-code/issues/12962) |
| Project disables inherited sandbox | Yes — `sandbox.enabled: false` scalar | Sub-arrays still merge |
| Env var escape hatch | **Yes** — `CLAUDE_CONFIG_DIR` | Swaps entire user scope per-invocation |

### `CLAUDE_CONFIG_DIR` is the key unlock

`CLAUDE_CONFIG_DIR` is a **documented Claude Code environment variable** that points the CLI at an alternate user-config directory (default `~/.claude`). Setting it to a path like `~/.cortex/repo-shadows/<repo-hash>/` per-invocation gives you an entirely swappable user scope — including `settings.json`, hooks, skills, rules, everything. Combined with per-directory environment-variable injection (direnv, mise, or a shell wrapper), this delivers the commissioned use case ("only use project permissions in this repo, ignore global allows") **without any settings mutation** and **without any cortex-side state machine**. See DR-1 for the design.

### Upstream issues tracking native support

- [anthropics/claude-code#12962](https://github.com/anthropics/claude-code/issues/12962) — settings.json doesn't walk up parent directories
- [anthropics/claude-code#37344](https://github.com/anthropics/claude-code/issues/37344), [#35561](https://github.com/anthropics/claude-code/issues/35561), [#26489](https://github.com/anthropics/claude-code/issues/26489) — related per-project scope asks

All open. The initial draft dismissed these with "no timelines." See DR-7 — any implementation of per-repo override work should begin with an explicit activity audit of these issues (comment counts, last-activity dates, Anthropic-engineer engagement, linked PRs). If any show momentum, the right answer may be to wait rather than build a workaround.

### Community workarounds observed

- **[inancgumus dotfile zsh wrapper](https://github.com/anthropics/claude-code/issues/12962#issuecomment-4114842453)** — shell wrapper that swaps `~/.claude/settings.json` based on cwd before launching `claude`. ~20 lines.
- **[yurukusa hook-based symlink approach](https://github.com/anthropics/claude-code/issues/12962#issuecomment-4150305251)** — SessionStart hook symlinks a project-specific settings file into `~/.claude/settings.json`. ~30 lines.

These are both much smaller than the "L effort" SessionStart mutation approach the initial draft recommended. The symlink approach is essentially the manual version of what `CLAUDE_CONFIG_DIR` + direnv delivers cleanly.

### Why settings mutation is the wrong shape

See DR-8 for the enumerated failure modes that would make a "SessionStart rewrite `~/.claude/settings.json`" approach substantially harder than the initial draft's "L effort" estimate suggested.

---

## Domain & Prior Art

### Dominant patterns across comparable tools

From the prior-art scan (oh-my-zsh, Prezto, chezmoi, brew bundle, mise/asdf, VS Code extension packs, home-manager, ESLint, Prettier, EditorConfig, tsconfig, git config, direnv, Starship):

**Pattern 1 — Declarative `enable = true/false` per component.** Home-manager, Starship, ESLint rules, VS Code extensions. Grep-able, diff-able, decouples install from activation.

**Pattern 2 — Directory-walk cascade with closer-wins semantics.** mise, EditorConfig, ESLint, Prettier, git config, direnv. Users intuitively understand "closer file wins."

**Pattern 3 — Explicit disable escape hatch.** git `""`, ESLint `"off"`, EditorConfig `root = true`, tsconfig `false`. Essential whenever there's global state.

**Pattern 4 — Environment-variable scoping via direnv-style tools.** direnv's `.envrc` is per-directory-subtree, trust-gated (`direnv allow`), and purely additive to shell env. Pairs with `CLAUDE_CONFIG_DIR` as the natural mechanism for "different Claude Code user scope in this repo." No code in the tool itself — the whole mechanism is "set an env var when `cd`-ing."

**Pattern 5 — Git's `[includeIf]` conditional includes.** One `~/.gitconfig` behaves differently in `~/work/` vs `~/personal/` via conditional include blocks keyed on `gitdir:`. The only pattern in the scan that delivers true "this directory tree, different behavior" with a single config file. Conceptually closest to what we want for cortex, but requires upstream Claude Code support.

### Anti-patterns to avoid

- **Bundle everything, enable a subset** (oh-my-zsh): Wastes install footprint for heavy components.
- **"No subtract" merge** (tsconfig): Users assume omitting = disabling; they get burned.
- **Recommendations-only enforcement** (VS Code workspace extensions): Advisory-only override defeats the purpose for permissions.
- **Destructive sync** (`brew bundle cleanup`): Silently uninstalls things missing from the manifest.
- **Hidden inter-module deps** (oh-my-zsh, Prezto plugins): Users hit weird runtime failures.
- **Settings-file mutation with single-file backups**: See DR-8 for why this is a specific anti-pattern for cortex-command.

---

## Feasibility Assessment

| Approach | Effort | Risks | Status |
|----------|--------|-------|--------|
| **A: Add new `.cortex/config.md` file** | M | Yet-another-config-file fatigue; dual-read refactor across four lifecycle phase files | **Rejected** — see DR-2 |
| **B: Rename `lifecycle.config.md` to `cortex.config.md`** | M | Breaking change for existing installs | **Rejected** — see DR-2 |
| **C: Install-time selection via a new global setup.config.md** | S–M | Doesn't solve runtime per-repo overrides | **Partially adopted** — see H below |
| **D: SessionStart hook rewrites `~/.claude/settings.json` based on per-repo config** | **XL**, not L | Concurrent sessions corrupt backups; SessionEnd not guaranteed; atomicity not addressed; `cortex-sync-permissions.py` architecturally unsuited; conflicts with upstream if #12962 lands | **Rejected as primary approach** — see DR-1 and DR-8 |
| **E: `CLAUDE_CONFIG_DIR`-pointed shadow user scope per repo + direnv integration** | S–M | Requires direnv (or equivalent) + shell integration; user-visible state in `~/.cortex/repo-shadows/` | **Adopted as primary mechanism for per-repo permissions override** — see DR-1 |
| **F: Named bundles (`core`/`autonomous`/`ui`/...)** | M | Drift from component set; second enable-layer on top of per-component enables; Band A items don't benefit from bundling | **Rejected** — see DR-3 |
| **G: Runtime self-exit guards in hooks** (each hook reads project config and no-ops if disabled) | S per hook | Doesn't work for `validate-commit` (hard block); adds a second enable-layer on top of install-time selection | **Deferred** — see DR-4 |
| **H: Extend `/setup-merge` to cover skills and hooks (not just settings.json sections)** | **S** | None significant — extends already-shipped skill | **Adopted** — see DR-4 |
| **I: `cortex doctor` CLI — read-only diagnostic reporting installed vs enabled state** | S | Must stay in sync with actual components | **Adopted** — see DR-4 |

### Recommended stack

The recommended design is the simpler counter-proposal surfaced during critical review. It drops the phased rollout, the new config file, and named bundles entirely.

1. **Reuse `lifecycle.config.md`**, add `skills:` and `hooks:` sections to the existing YAML frontmatter. One file; existing readers continue working (the new sections are ignored by lifecycle phases that don't use them).

2. **Extend `/setup-merge`** to add per-skill and per-hook prompts (Row H, S effort). The skill already handles the per-category opt-in pattern for settings.json sections — extending to skills and hooks is the natural next step.

3. **Add `cortex doctor`** as a read-only `bin/` utility. Reports: installed components, enabled state (per `lifecycle.config.md`), Claude Code version, upstream issue activity (see DR-7), any drift between installed and configured state. Zero mutation.

4. **Deliver per-repo permissions scoping via `CLAUDE_CONFIG_DIR` + direnv** (Option E). Add documentation + a small optional `bin/cortex-shadow-config` generator that produces a shadow `~/.cortex/repo-shadows/<repo-name>/` directory mirroring the user's `~/.claude/` but with the repo's overrides applied. Users opt in by adding one `.envrc` line per repo (`export CLAUDE_CONFIG_DIR=...`) and running `direnv allow`. Delivers the commissioned use case using a documented Claude Code feature. Uses the direnv + env-var-scoping pattern that users already know from mise/asdf/direnv itself.

5. **Gate implementation on an upstream audit.** Before any of 1–4 ships, check the activity on #12962 and related issues (see DR-7). If upstream is imminent, delay or align.

This delivers the topic statement ("only use project permissions in this repo") without adding new config files beyond what already exists and without any SessionStart mutation of the user's global settings. It is smaller than the initial draft's phased rollout and actually answers the question the research was commissioned to investigate.

---

## Decision Records

### DR-1: Per-repo permission override uses `CLAUDE_CONFIG_DIR`, not settings mutation

- **Context**: The commissioned use case is "in this repo, use project-only permissions; don't run the global hooks." Claude Code's merge semantics are strictly additive with no negation mechanism below the managed scope (see §Web & Documentation Research). A mechanism external to the native merge is required to deliver this.
- **Options considered**:
  - (a) Wait for upstream (issues #12962, #37344 tracking the gap)
  - (b) SessionStart hook rewrites `~/.claude/settings.json` based on project config
  - (c) `CLAUDE_CONFIG_DIR`-pointed shadow user scope per repo, activated via direnv or shell wrapper
  - (d) Abandon per-repo override as a goal
- **Decision**: **Option (c)** — `CLAUDE_CONFIG_DIR` + direnv. Gate on DR-7 upstream audit before building.
- **Why not (b)**: Option (b) was the initial draft's recommendation, selected on sunk-cost grounds ("cortex-command already has SessionStart infrastructure via `cortex-sync-permissions.py`"). Critical review established that (i) the existing hook is architecturally unsuited to this extension — it silently swallows exceptions (correct for "merge permissions into a per-repo file," disastrous for "save a backup, then mutate the user's global settings"), uses non-atomic `Path.write_text`, and has no backup concept; (ii) the true scope of Option (b) is XL not L (see DR-8); (iii) Option (b) mutates a file Claude Code owns and will need re-validation against every Claude Code release, while Option (c) uses a documented Claude Code feature and inherits upstream changes automatically; (iv) when upstream closes #12962, Option (b) will likely fight the native resolution (two override systems operating on different source files), while Option (c) will continue to work or be cleanly retired.
- **Why not (a)**: The upstream issues have no timeline. DR-7 makes this a gated check rather than a blanket dismissal — if the audit shows imminent upstream support, deferring is correct.
- **Why not (d)**: The topic statement commissioned this capability as the concrete example. Deferring without explicit user agreement would silently change the research question.
- **Trade-offs**: Option (c) requires users to install and configure direnv (or equivalent) and to run `direnv allow` per repo. This is a real friction point for users who don't already use direnv. Mitigation: the `bin/cortex-shadow-config` generator can produce a one-line `.envrc` snippet; users who refuse to install direnv can set the env var manually via shell wrapper or alias. Cortex ships the mechanism, not the direnv dependency — users choose their integration.

### DR-2: Reuse `lifecycle.config.md` — do not add a new config file

- **Context**: The initial draft proposed a new `.cortex/config.md` at the project root. Critical review established that (i) this adds a seventh distinct config surface for users to learn (`~/.claude/settings.json`, `.claude/settings.local.json`, `~/.claude/CLAUDE.md`/`rules/`, `lifecycle.config.md`, new `.cortex/config.md`, `requirements/project.md` + area files, plus hypothesized `~/.cortex/install.config.md`); (ii) the initial draft's "keep reading both during transition" migration contradicts §1.E (no centralized resolver) — every lifecycle phase file that reads `lifecycle.config.md` would need to learn to read both files with no exit criterion; (iii) the rationale for rejecting `.claude/settings.local.json` as a config home was "wrong scope for team-shared project config," but the project is "primarily personal tooling, shared publicly for others to clone or fork" — teams are not the target audience.
- **Options considered**:
  - (a) New file `.cortex/config.md`
  - (b) New file `cortex.config.md` at project root
  - (c) **Reuse `lifecycle.config.md`** — add `skills:`, `hooks:`, and (if DR-1 Option (c) is adopted) `permissions:` sections to the existing YAML frontmatter
  - (d) Split across multiple files
  - (e) Use `.claude/settings.local.json` under a `cortex:` key
- **Decision**: **Option (c)**. `lifecycle.config.md` already exists, already lives at the project root, is already committed, and is read by lifecycle phases. Adding sections is a single-file change. Lifecycle phases that don't care about the new sections ignore them at no cost.
- **Naming trade-off**: The file name "lifecycle.config.md" is narrower than its new scope would suggest. Accept this — renaming is a breaking change for existing installs, and critical review flagged that any rename would still require dual-read during transition given §1.E's decentralized read pattern. The file's internal header can be updated to "Cortex-Command Project Configuration" without renaming the file.
- **Trade-offs**: The file's name is no longer perfectly descriptive of its full content. The alternative (add a new file) was materially worse per critical review.

### DR-3: No named bundles

- **Context**: The initial draft proposed five named bundles (`core`, `autonomous`, `observability`, `ui`, `meta`) "grounded in the dependency map (§2)." Critical review established that (i) §2 produces three coupling *bands* (A/B/C), not five bundles, and the bands→bundles mapping was invented; (ii) `observability` bundled four hooks that §2 Band A explicitly lists as "cleanly optional and independent" — they do not need bundling; (iii) `meta` was a catch-all of eight invocation-only skills that §2 describes as having no cross-dependencies; (iv) when a user's needs don't match a bundle (e.g., "overnight without morning-review"), they fall back to per-component enables anyway — bundles become a second layer, not a replacement; (v) the initial draft admitted bundles "will drift" and proposed a generator script to keep them in sync — complexity begetting complexity.
- **Decision**: No named bundles. Band C from §2 defines the install floor — users cannot opt out of it without breaking core workflows. Above the install floor, per-component enable is the unit of selection. The 26 skills + 13 hooks are tractable to list individually in `/setup-merge` prompts.
- **Install floor (Band C)**: `lifecycle`, `backlog`, `commit`, `dev` skills; `cortex-validate-commit.sh`, `cortex-sync-permissions.py`, `cortex-scan-lifecycle.sh` hooks; `update-item`, `create-backlog-item`, `generate-backlog-index` bin utilities.
- **Above the install floor**: `/setup-merge` extension presents per-skill and per-hook opt-in prompts, grouped by the clusters in §1.A and §1.B for scannability — but the groups are display-only, not bundle names that users reference in config.
- **Trade-offs**: Users who want "the overnight stack" must opt in to each piece individually rather than typing one bundle name. Mitigation: `/setup-merge` can show the cluster header "Overnight / Review (12 components)" with a bulk-enable shortcut, giving bundle ergonomics without bundle naming semantics.

### DR-4: Install-time selection for skills/hooks; `CLAUDE_CONFIG_DIR` for permissions; existing config reads for lifecycle flags

- **Context**: Different component types have different opt-out semantics. The initial draft proposed a mix of install-time, runtime, and SessionStart mutation; critical review converged on a simpler per-type mapping.
- **Decision per type**:

  | Component type | Selection mechanism | Rationale |
  |----------------|---------------------|-----------|
  | **Skills** | Install-time only (don't symlink), via `/setup-merge` | No runtime cost if installed but unused; per-repo "hide this skill" is low-value |
  | **Hooks** | Install-time only, via `/setup-merge` | Simpler than runtime self-exit guards; users who want per-repo hook disable can achieve it via `CLAUDE_CONFIG_DIR` shadow |
  | **Permissions** | `CLAUDE_CONFIG_DIR` + direnv (per-repo override) | Only mechanism that actually delivers the commissioned use case without mutating user-owned settings files |
  | **Lifecycle flags** | Runtime config read (existing) | No change — `lifecycle.config.md` already serves this |
  | **Heavy components (overnight, dashboard)** | Install-time only, via explicit `just install-X` recipes | High install cost makes install-time the natural gate |
  | **Settings.json sections (statusLine, plugins, sandbox)** | `/setup-merge` per-category prompts (already shipped) | No change |
- **What this means for `/setup-merge`**: Today it handles settings.json sections; extending to skills and hooks is Row H in Feasibility (S effort). The skill becomes the single install-time selection surface for the whole agentic layer.
- **Trade-offs**: Users who want "installed globally but disabled in this specific repo" for a skill or hook have two options: (a) use `CLAUDE_CONFIG_DIR` to point at a shadow scope without that skill/hook, or (b) uninstall and reinstall at a different granularity. Option (a) is cleaner for per-repo cases; (b) is cleaner for permanent changes. `cortex doctor` can surface the current state.

### DR-5: Tight shipping plan — no phased rollout

- **Context**: The initial draft proposed a four-phase rollout where Phase 4 (the SessionStart mutation layer) was the only phase that delivered the commissioned use case, and Phase 4 was labeled "stretch — may not be needed... only build if someone actually asks for it." Critical review established that this systematically routes around the topic question.
- **Decision**: Ship the recommended stack (§Feasibility Assessment) as a tight plan, not a phased rollout. Order by dependency, not by "quick wins":

  1. **Upstream audit (DR-7)** — gating check. Before any implementation, audit the activity on #12962, #37344, #35561, #26489. If any show imminent movement, pause and reassess.
  2. **Extend `lifecycle.config.md` schema** (DR-2) — add `skills:`, `hooks:`, and optional `permissions:` sections. Update the file's internal header and `skills/lifecycle/assets/lifecycle.config.md` template.
  3. **Extend `/setup-merge` for skills and hooks** (Row H) — add per-component prompts grouped by cluster.
  4. **Ship `bin/cortex-shadow-config` and direnv integration docs** (DR-1 Option (c)) — deliver the commissioned per-repo permissions override use case.
  5. **Ship `cortex doctor`** (Row I) — read-only diagnostic CLI.
- **Each item is independently shippable.** No item's design forces schema commitments that other items must later work around (unlike the initial draft, where Phase 1's manifest schema would have pre-committed the project to Phase 4's mutation semantics).
- **Trade-offs**: Less room for "quick win" early tickets that ship visible changes before delivering the commissioned capability. This is the correct trade — critical review flagged that the initial draft's Phase 1 ("a manifest file that parses but doesn't gate anything") was pure ceremony.

### DR-6: Non-destructive

- **Context**: `brew bundle cleanup` is a cautionary tale — removing stale entries from a manifest silently uninstalls work.
- **Decision**: `/setup-merge` and `just setup` must be strictly additive when reading `lifecycle.config.md`. Setting a component to `enable: false` in the manifest does not *uninstall* it — it just skips the component on fresh install. Explicit opt-out requires an explicit `just uninstall-X` recipe (future work; not part of this discovery).
- **Trade-offs**: Toggle-driven uninstall is a common user expectation. Acceptable because cortex components are symlinks — `rm` is one command away.

### DR-7: Upstream activity audit as a gating prerequisite

- **Context**: The initial draft dismissed upstream Claude Code issues with "no timelines" as the entire case for building a cortex-side workaround. Critical review flagged this as a shrug, not an assessment — the research is written in April 2026 and Claude Code has shipped significant settings/hook/permission schema changes on a roughly quarterly cadence.
- **Decision**: Before any implementation work on this discovery's recommended stack begins, conduct an explicit upstream activity audit. The audit produces a short report covering:
  - Current comment count, thumbs count, and last activity date on [#12962](https://github.com/anthropics/claude-code/issues/12962), [#37344](https://github.com/anthropics/claude-code/issues/37344), [#35561](https://github.com/anthropics/claude-code/issues/35561), [#26489](https://github.com/anthropics/claude-code/issues/26489).
  - Presence of any Anthropic staff engagement (labels, assignees, comments).
  - Presence of any linked PRs or related closed issues suggesting work-in-progress.
  - Any recent Claude Code release notes (past 3 months) that touched settings layering, hook registration, or permission merge semantics.
- **Audit outcomes** (original 6-ticket-plan phrasing; updated below for the collapsed docs-only shape):
  - **Quiet** (no recent activity, no Anthropic engagement): ship the full supported-pattern docs — walkthrough, fallbacks, troubleshooting. Treat `CLAUDE_CONFIG_DIR` + direnv as the primary documented mechanism.
  - **Warm** (some activity, no commitments): ship the full docs but frame the pattern as "documented mechanism, upstream may land native support" with an explicit "watch these issues" callout in the preamble.
  - **Hot** (active PR, roadmap mention, or Anthropic staff commentary): ship a **minimal wait-oriented page** — status paragraph foregrounding the tracking issue, a brief hand-edit snippet (<20 lines) for users who can't wait, no full walkthrough, no fallbacks section, no troubleshooting beyond one sentence. Do not mark the epic complete; revisit once upstream ships.
  - **Note**: the original "pause the work" phrasing for hot assumed a heavier scaffolding stack (generator binary, hooks, doctor CLI) that could be paused independently of the docs. Under the collapsed docs-only plan, the docs ARE the work — so "pause" collapses to "ship the minimum useful page and don't build habits around it." DR-7's core intent (don't over-invest in a pattern that is about to become native) is preserved by the minimal-under-hot shape.
- **Decompose impact**: The audit becomes the first ticket of the epic. Its outcome gates the rest.
- **Trade-offs**: Adds a research step before implementation. Worth it — the cost is ~1 hour of investigation, the benefit is avoiding building scaffolding around a constraint that's about to disappear.

### DR-8: If Option D is ever pursued, here is the real scope

- **Context**: The initial draft recommended SessionStart mutation of `~/.claude/settings.json` and rated it "L effort" with "risks: state mutation risk... complex edge cases (nested repos, detached sessions)." Critical review enumerated the failure surfaces that would need to be addressed. This DR preserves those requirements so any future pursuit of Option D cannot repeat the initial draft's underestimate.
- **Requirements for a correctness-first Option D implementation**:
  1. **Atomic writes**: Use write-to-tempfile-then-rename with `fsync` for every mutation of `~/.claude/settings.json`. `Path.write_text` is not acceptable — SIGKILL between truncate and write completion leaves zero-byte or truncated JSON.
  2. **Parse-failure recovery**: On SessionStart, if `~/.claude/settings.json` fails to parse, treat any existing `.cortex-backup` as authoritative and restore from it before mutation.
  3. **SessionEnd is not guaranteed**: Enumerate failure modes: `kill -9`, SIGHUP, OS reboot, sleep-to-battery-death, harness crash, 5-second hook timeout at `claude/settings.json:251`, `cortex-cleanup-session.sh`'s early-exit on `/clear`. Restore logic must be tolerant of all of these.
  4. **Provenance marker**: Add a sentinel key like `_cortexMutatedBy: <session_id>` to the mutated settings so next SessionStart can detect "previous session crashed without restoring." `_globalPermissionsHash` is a content-identity check and cannot distinguish pristine from mutated — it is not the right mechanism.
  5. **Concurrent sessions**: Single-file backup convention (`~/.claude/settings.json.cortex-backup`) does not survive concurrent sessions in different repos — session B reads session A's mutated state and saves *that* as "original." Backup keying must be per-session (PID or session ID), and restore must handle multi-session races correctly.
  6. **User edits mid-session**: During long sessions (6+ hours for overnight runs), the user may hand-edit `~/.claude/settings.json` or run `/setup-merge`. Restore logic must hash-check before overwriting and bail (not overwrite) if the file has drifted from the mutation-applied state.
  7. **Silent-exception handling is unsafe**: `cortex-sync-permissions.py`'s `try: ... except: pass` pattern is correct for its current job ("worst case: a local file isn't updated") but disastrous for mutation ("backup save fails silently, mutate still runs"). Any mutation hook needs explicit error handling for every failure mode, and must abort the mutation if the backup step fails.
  8. **Upstream change detection**: Detect Claude Code version at SessionStart. If upstream support for per-repo scope (e.g., #12962) is present in the running version, no-op the cortex mutation layer and emit a one-time deprecation notice.
  9. **Nested repos**: Directory change mid-session does not fire any hook. Document the limitation or wrap `claude` in a launcher that re-resolves config on `cd`.
  10. **Not a new `cortex-sync-permissions.py` extension**: A clean implementation should be a new, clearly-named hook (e.g., `cortex-swap-global-settings.py`) — not an extension of the existing permissions-merge script. Reusing the existing hook smuggles a very-different-safety-profile operation into a file users have categorized as "merges permission strings."
- **True effort**: With these requirements, the work is closer to XL than L. Anyone estimating Option D at L is almost certainly underestimating one or more of items 1–10.
- **Status**: Not pursued. Preserved here so that a future "we need Option D after all" decision is made with eyes open.

---

## Open Questions

- **Q1: Should `/setup-merge` prompt per-component, per-cluster, or both?** DR-3 drops named bundles, but clusters (§1.A, §1.B) are still useful groupings for display. Is the right ergonomics: "one prompt per component" (high friction, max control), "one prompt per cluster with bulk enable/disable" (lower friction, less control), or "cluster-level prompt with an optional 'customize' drill-in" (best of both, highest complexity)? User call.

- **Q2: Should `bin/cortex-shadow-config` generate the shadow scope at the generator's run time, or at SessionStart?** Generate-at-run-time is simpler and deterministic but goes stale when the user's `~/.claude/` changes. Generate-at-SessionStart is fresh but adds hook complexity and load time. Probably generate-at-run-time with a "regenerate when stale" check on SessionStart — but the exact split needs implementation design.

- **Q3: Should `cortex doctor` read `lifecycle.config.md` and report configured-vs-installed drift, or just report installed state?** The former is more useful; the latter is simpler. Lean toward drift detection if DR-2's schema extension ships first.

- **Q4: What's the concrete DR-7 audit schedule?** One-shot at the start of implementation work, or periodic (every release cycle) to catch upstream drift after shipping? Recommend: one-shot before implementation, plus a line in `cortex doctor` that re-checks the issues on each run and warns if activity has picked up.

- **Q5: For users who don't use direnv, what's the fallback mechanism for `CLAUDE_CONFIG_DIR`?** Options: (a) shell wrapper alias (`alias claude='CLAUDE_CONFIG_DIR=... claude'`), (b) a `just launch` recipe from the repo root, (c) document manual `export` per session. All work; the question is which we recommend in docs. Probably (a) with (b) as an alternative.

- **Q6: Upgrade path for existing cortex-command users.** When this ships, existing installs should continue working identically. `/setup-merge` extension must detect existing deployments and treat their current state as the default answer to new prompts (no forced migration).

- **Q7: Does `/setup-merge`'s existing settings.json merge logic interact correctly with a `CLAUDE_CONFIG_DIR`-pointed shadow scope?** If a user has `CLAUDE_CONFIG_DIR=~/.cortex/repo-shadows/foo` set and runs `/setup-merge`, does the skill merge into the shadow or into `~/.claude/`? Probably into whatever Claude Code is currently using — but needs verification during implementation.

- **Q8: Is there a reasonable way to surface DR-7's audit results in the repo itself** (e.g., a dated note in `docs/`) so that future contributors can see what the upstream landscape looked like at decision time? Recommend yes, but shape is open.

---

## Artifact Summary

The research converged on three load-bearing findings:

1. **The agentic layer has 80+ opt-in-able units across 4 distinct component types** (skills, hooks, settings entries, heavy components like overnight runner/dashboard), with dependencies forming three bands: cleanly optional, moderately coupled, and an install floor. Above the install floor, per-component enable is sufficient — no named bundles needed.

2. **Claude Code's `CLAUDE_CONFIG_DIR` environment variable delivers the commissioned per-repo permissions use case without any settings mutation.** Combined with direnv (or equivalent per-directory env-var scoping), it gives users "in this repo, use a different Claude Code user scope entirely" — which is strictly cleaner than any layering workaround. The initial draft of this research recommended a SessionStart mutation hook instead, based on sunk-cost reasoning about existing cortex infrastructure; critical review established that (i) the existing infrastructure is architecturally unsuited, (ii) the true effort of a correctness-first mutation implementation is XL not L (see DR-8), and (iii) the `CLAUDE_CONFIG_DIR` approach inherits upstream Claude Code evolution automatically while the mutation approach fights it.

3. **A tight shipping plan delivers the topic without a phased rollout.** The recommended stack is: (1) upstream activity audit on #12962 et al. (DR-7) as a gating prerequisite; (2) extend `lifecycle.config.md` schema with `skills:`/`hooks:` sections (DR-2); (3) extend `/setup-merge` for per-skill and per-hook prompts (Feasibility Row H, S effort); (4) ship `bin/cortex-shadow-config` and direnv integration docs (DR-1 Option (c)); (5) ship `cortex doctor` read-only diagnostic CLI. Each item is independently shippable and none forces schema commitments on the others. DR-8 preserves the "what it would really take" scope for Option D in case anyone ever reconsiders it.

Next: decompose into an epic with child tickets following DR-5's tight shipping plan, with the upstream audit as the first ticket.
