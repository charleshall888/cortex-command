# Research: overnight-layer-distribution

> Explore distribution mechanisms (local MCP, remote MCP, standalone CLI, bootstrap
> installer) for the cortex-command agentic layer. Modularity is first-class:
> users must be able to install lifecycle skills without the overnight process,
> or the full bundle, or pieces in between.

## Research Questions

1. **What can ship as a Claude Code plugin today, and what can't?**
   → **Skills, hooks, MCP servers, subagents, output styles, statuslines, monitors, and `bin/` executables ship cleanly as plugins. `claude/Agents.md`-style global rules, `settings.json` permissions allow/deny, and long-running daemons do not.** Plugins GA'd after Oct 2025 beta; `bin/` is auto-added to the Bash-tool PATH; `${CLAUDE_PLUGIN_DATA}` is the persistent store for Python venvs / caches that survive plugin updates.

2. **Is the overnight runner really unshippable as MCP?**
   → **Mostly yes, and the user's intuition is correct.** MCP's protocol primitives are request/response; SEP-1686 "Tasks" proposes long-running operations but is not yet in a released MCP version. Plugin monitors (v2.1.105+) run background processes but die when the session ends — fatal for multi-hour runs. Stdio MCP servers aren't auto-restarted. **Viable workaround**: ship the runner as a standalone binary (invoked independently) with a thin MCP *control-plane* server that exposes `start_run`/`status`/`logs`/`cancel` tools, modeled on [`dylan-gluck/mcp-background-job`](https://github.com/dylan-gluck/mcp-background-job).

3. **Can a Cloudflare-hosted remote MCP deliver zero-local-install?**
   → **Not for the overnight runner. Yes, for a slice.** Cloudflare Workflows supports 365-day sleeps, Durable Objects hold per-user state, `workers-oauth-provider` handles OAuth 2.1, BYOK patterns are well-documented. But a remote server **physically cannot see the user's local `lifecycle/`, `backlog/`, `.git`**. GitHub-as-intermediary (like `github-mcp-server`) works for markdown artifacts but breaks the runner's live-edit + worktree-atomicity contract. **Realistic slice**: backlog + lifecycle *markdown operations* as a remote MCP via GitHub App token; runner stays local.

4. **Which CLI packaging fits a Python+bash codebase that needs editability?**
   → **`curl | sh` bootstrap → installs `uv` → `git clone` → `uv tool install -e .` → `cortex setup`.** Preserves fork/edit north star, leverages the fact that `uv` is already a hard dep (runner shells `uv run`). Homebrew tap as thin wrapper for discoverability. Prior art: aider moved to this exact shape in Jan 2025 and reported dependency conflicts dropped sharply.

5. **How do the runner (CLI) and skills (plugin) find each other and share state?**
   → **Shared state is always files in the user's working repo** (`lifecycle/`, `backlog/`, `retros/`). This is the stable contract. The runner CLI reads/writes those paths via `$CORTEX_COMMAND_ROOT` + absolute paths; plugin skills read/write the same paths via the user's cwd. No runtime linkage needed — both components point at the same filesystem substrate. The runner does NOT re-invoke skills during overnight execution (workers have `_ALLOWED_TOOLS = [Read, Write, Edit, Bash, Glob, Grep]` only; Agent/Task omitted).

6. **What can other AI coding frameworks teach us about modular distribution?**
   → **Three patterns converge: (a) shadcn-style "you own the code" for content packs, (b) Goose-style "custom distributions" for runtimes, (c) Continue-style "hub slug" for composition.** No surveyed project ships all of these together. Crucially: **no prior-art project ships an autonomous overnight runner as a user-installable artifact**, and **no prior-art project treats the user's git repo as the destination for agent-managed content**. cortex-command would solve both.

7. **What's the upgrade story when components ship via different channels?**
   → **Each channel has its own verb, and binaries auto-update while content does not** (industry-wide gap). Proposed: `cortex upgrade` for the runner tier (git pull + re-link); plugin marketplace has no auto-update (Claude Code ships this gap unsolved); `cortex init --update` scaffolds new lifecycle templates. Users on forks survive upgrades because their customizations are committed — git handles merges, not a package manager's blind overwrite.

---

## Codebase Analysis

### The overnight bundle is an inseparable unit (~92 files, 5.3 MB)

Must ship together:
- `claude/overnight/runner.sh` (600+ lines) + `claude/overnight/*.py` (~10K LOC): state, events, backlog, plan, strategy, batch_runner, brain, integration_recovery, interrupt, deferral, throttle, report, status, map_results
- `claude/overnight/prompts/*.md`: orchestrator-round, batch-brain, repair-agent
- `claude/pipeline/dispatch.py` + `claude/pipeline/*.py`: merge, conflict, merge_recovery, review_dispatch, events
- `claude/pipeline/prompts/*.md`: implement, review
- `claude/common.py` (imported by 15+ modules)
- Python venv (`uv.lock`, `pyproject.toml`)

**Why inseparable**: the runner directly imports `claude.overnight.*` and `claude.pipeline.*`; the orchestrator prompt has hardcoded references to `overnight-strategy.json`/`escalations.jsonl` paths; `batch_runner` expects pipeline artifacts in specific locations. Separating any piece breaks the round loop.

### Plugin-splittable components (no runner dependency)

**Skills** that run standalone: `lifecycle`, `commit`, `pr`, `research`, `discovery`, `refine`, `backlog`, `requirements`, `retro`, `dev`, `fresh`, `diagnose`, `evolve`, `critical-review`, `morning-review` (the last two call `claude.overnight.report` when invoked from the runner but also run interactively without it).

**Hooks** that ship independently: `cortex-skill-edit-advisor.sh`, `cortex-permission-audit-log.sh`, `cortex-output-filter.sh`, `cortex-cleanup-session.sh` (optional), `cortex-sync-permissions.py` (optional).

**Skills/hooks required by the runner** (must ship with it): `skills/overnight` (entry point), `hooks/cortex-scan-lifecycle.sh` (injects `LIFECYCLE_SESSION_ID`), `hooks/cortex-validate-commit.sh` (validates worker commits), `hooks/cortex-tool-failure-tracker.sh`, `hooks/cortex-notify.sh`.

### Shared state contract

All coordination between components happens through files in the user's working repo:

| Path | Writers | Readers |
|------|---------|---------|
| `lifecycle/overnight-state.json` | runner.sh, state.py | dashboard, CLI status tools |
| `lifecycle/sessions/{id}/*` | runner.sh, batch_runner | dashboard, morning-report |
| `lifecycle/{feature}/{spec,plan}.md` | lifecycle skill + orchestrator | worker agents |
| `lifecycle/{feature}/events.log` | batch_runner.py | metrics, morning-report |
| `lifecycle/{feature}/agent-activity.jsonl` | dispatch.py | dashboard |
| `lifecycle/escalations.jsonl` | deferral.py | morning-report |
| `backlog/*.md` + `backlog/index.{json,md}` | user, backlog skill, overnight | selection |

All writes use atomic `tempfile + os.replace()` on same filesystem — concurrent readers never see partial records. This is a **permanent architectural constraint** from `requirements/pipeline.md`.

### Host touchpoints (current install footprint)

- `~/.claude/settings.json` (copied, not symlinked)
- `~/.claude/settings.local.json` (per-machine overrides)
- `~/.claude/{hooks,skills,rules,reference}/*` (symlinks from repo)
- `~/.claude/notify.sh` (symlink, referenced literally in settings.json)
- `~/.local/bin/{overnight-start,overnight-status,overnight-schedule,jcc,...}` (symlinks)
- `CORTEX_COMMAND_ROOT` env var + `REPO_ROOT/.venv` (Python deps)

### Hard constraints that block naive repackaging

1. **Hardcoded path expansion** in ~20 inline Python snippets throughout `runner.sh` — paths come from state file fields and feed into shell subcommands
2. **Process group management** (`set -m`, lines 644-650, 714-730) — watchdog kills entire PGID on timeout
3. **Signal handling** (`trap cleanup SIGINT SIGTERM SIGHUP`, line 526) — graceful shutdown writes state atomically
4. **Atomic file ops** — 15+ call sites using tempfile + os.replace()
5. **Prompt template substitution** (line 379-393) — runner reads `orchestrator-round.md` and replaces `{state_path}`, etc. with absolute paths
6. **`settings.json` deep-merge** in `/setup-merge` — plugin distribution mechanisms can't do this; only `agent` and `subagentStatusLine` keys are supported in plugin settings

---

## Web & Documentation Research

### Claude Code plugins (GA, April 2026)

**What a plugin contains:**

| Component | Location | Notes |
|---|---|---|
| Skills | `skills/<name>/SKILL.md` | Namespaced `/plugin-name:skill-name` |
| Slash commands | `commands/*.md` | |
| Subagents | `agents/*.md` | `hooks`, `mcpServers`, `permissionMode` **disallowed** |
| Hooks | `hooks/hooks.json` | Full event set; registered from manifest |
| MCP servers | `.mcp.json` | Auto-start on enable |
| Monitors | `monitors/monitors.json` | Background processes (v2.1.105+) |
| **Executables** | `bin/` | **Auto-added to Bash tool PATH** |
| Output styles | `output-styles/` | |
| LSP servers | `.lsp.json` | |

Two key env vars: `${CLAUDE_PLUGIN_ROOT}` (install dir, changes on update) and `${CLAUDE_PLUGIN_DATA}` (`~/.claude/plugins/data/{id}/`, **survives updates** — correct place for Python venv, node_modules, caches).

**Install UX**: `/plugin install github@claude-plugins-official` (auto-registered marketplace); third-party marketplaces via `/plugin marketplace add owner/repo`. Four scopes (user/project/local/managed). `userConfig` supplies `${user_config.KEY}` substitution and `CLAUDE_PLUGIN_OPTION_*` env vars at enable-time; sensitive values → keychain (~2 KB limit).

**MCP limits**: default **25K token cap on MCP tool output** (warning at 10K); override with `MAX_MCP_OUTPUT_TOKENS`. Tool schemas cost 100-500 tokens per tool per turn.

**Long-running operations in MCP**: SEP-1686 "Tasks" proposal accepted but **not yet in a released MCP version**. Plugin monitors die when session ends. Working pattern today: `mcp-background-job` registry + client polling.

**Pitfalls**:
- No sandboxing; plugins run with full user privileges
- Official marketplace auto-updates; third-party default is no-auto-update
- No plugin dependency sharing (5 plugins sharing an agent = 5× duplication)
- Rules / `CLAUDE.md` are NOT plugin-distributable today (upstream gap)
- Removing a hook script leaves a dangling manifest entry

### Cloudflare remote MCP

Concrete pieces that ship:
- `McpAgent` class (Agents SDK) — Durable Object per session, SSE + Streamable HTTP
- `workers-oauth-provider` — OAuth 2.1 library
- Template repos (`remote-mcp-authless`, `remote-mcp-github-oauth`)
- `mcp-remote` adapter — bridges stdio clients to remote servers
- Cloudflare's own `mcp.cloudflare.com` (dogfood at scale)

**Limits that matter**:
- Workers CPU: 5 min (Paid) / 10 ms (Free)
- Durable Object alarms / Queues / cron: 15 min wall clock
- **Cloudflare Workflows** is the durable-execution answer: 365-day sleeps, 25k steps, 30-day state retention, 1 GB persistent state. CPU per step still 5 min.
- Subprocess spawning requires Containers / Sandbox SDK (Paid-plan only)

**The blocker**: a remote MCP cannot see the user's local `~/Workspaces/cortex-command/lifecycle/`. Three patterns attempted, none fits cleanly for a full-dev-workflow use case:
1. Git-as-medium (like `github-mcp-server`) — works for markdown, breaks live-edit atomicity
2. Sandbox SDK — has virtual FS but it's the *sandbox's* FS, not the user's laptop
3. Local bridge agent — re-introduces the local install

### CLI packaging options

| Format | Editable | Deploys to $HOME | Example |
|---|---|---|---|
| `uv tool install -e .` | Yes | No (use `cortex setup`) | aider (2025+) |
| pipx | Yes | No | pre-commit, llm, mitmproxy (legacy) |
| Homebrew formula | No | `post_install` fights sandbox | llm tap |
| npm global | N/A | postinstall OK | claude-code |
| PyInstaller/shiv | **No** | Any at runtime | mitmproxy binary |
| Docker | Mount source | Volume mounts painful | devcontainers |

**Sharp edges**:
- `uv sync` removes editable installs if `[build-system]` missing ([#9518](https://github.com/astral-sh/uv/issues/9518))
- Homebrew `post_install` re-runs on every `brew upgrade` — clobbers user customizations if you deploy symlinks there; stick to `caveats`
- PyInstaller kills forkability — wrong shape for clone/fork/edit north star

---

## Domain & Prior Art

### No surveyed project solves cortex-command's exact problem

| Problem | Prior art |
|---------|-----------|
| Skills + hooks as installable packs | **Solved** — shadcn, Superpowers, Antigravity, Claude Code plugins |
| Long-running unattended runner as shippable artifact | **Unsolved** — no project ships one |
| Bundled localhost web dashboard | **Unsolved** — Goose has native desktop, Continue has cloud Mission Control |
| File-state in user's own git repo | **Only shadcn/ui** — every AI-agent framework writes to `~/.continue/`, `~/.config/opencode/` etc. |
| Selective sub-install ("A without B") | **Unsolved** — Antigravity's `--category` filters after full install |
| Content upgrade UX | **Unsolved industry-wide** — reinstall is the only verb |

### Three most instructive analogues

**Continue.dev** — cleanly separates *identity* (hub slug), *composition* (YAML), *materialization* (on-disk). Borrowable: slug-based composition. Not borrowable: cloud hub (contradicts cortex's local-file value).

**Goose (Block)** — most transferable idea is "custom distributions": third parties ship preconfigured Goose binaries. Splits runtime (binary) from capabilities (MCP) from distro (opinionated wrapper).

**shadcn/ui** — `npx shadcn add <component>` writes source into user's repo. User owns the code. This is the correct pattern for `lifecycle/`, `backlog/`, `retros/` scaffolding.

### Cross-cutting patterns

- `curl | bash` is the default terminal install; nobody ships primarily via Homebrew
- **MCP is winning as the extension ABI** for non-IDE agents
- "Marketplace = git repo with a manifest" is the dominant content-distribution shape
- Binaries self-update; content does not (universal friction)
- Modularity via named, composable units (blocks, extensions, skills, components)
- Config is hierarchical and merged, not replaced (org → user → project)

---

## Feasibility Assessment

| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|
| **A: Full remote MCP (Cloudflare-hosted, zero-install)** | XL | Architectural mismatch — can't touch user's local repo; violates live-edit + atomicity contract | Would require redesigning file-state to live in cloud or git-as-medium; breaks north-star |
| **B: Plugin for skills/hooks + CLI for runner (recommended)** | L | Skills renamed under `cortex:` namespace (breaking change); **plugin tier has hard prerequisite on CLI tier** — plugins alone don't deploy `notify.sh`, `statusline.sh`, rules, reference; **migration cost** for existing symlink-based installs is not small (rm symlinks + reinstall + namespace rename propagated to user's muscle memory); **plugin dependency chain** — `cortex-lifecycle` and `cortex-overnight-integration` both transitively need `claude.overnight.*` Python modules that only ship via the CLI, so the three plugins are in practice a dependency chain, not independent units (see DR-2 dependency matrix); `settings.json` permissions can't ship via plugin | uv-based CLI packaging; plugin `bin/` PATH mechanism (already shipped); `${CLAUDE_PLUGIN_DATA}` venv pattern; clear sequencing doc |
| **C: Single `curl | sh` bootstrap wrapping current `just setup`** | M | Doesn't solve modularity ("skills without runner"); still clone-based | Bootstrap script + `cortex` entry point |
| **D: Hybrid — plugin for skills, CLI for runner+dashboard, remote MCP for GitHub-shaped artifacts** | XL | Most ambitious; three moving parts with their own upgrade verbs; remote MCP slice has limited value | B + Cloudflare Worker + GitHub App |
| **E: Homebrew-primary install** | L | `post_install` re-runs on every upgrade → clobbers user customizations; Python formula sharp edges | Tap repo, formula authoring |
| **F: PyInstaller standalone binary** | M | **Kills forkability** — directly contradicts north-star "shared publicly for others to clone or fork" | Binary signing for macOS |
| **G: MCP control-plane over background runner** (the `mcp-background-job` pattern applied to overnight) — **now folded into B per DR-1** | L (absorbed into B) | Runner IPC contract designed upfront; no retrofit risk | Ships together with B |

**Recommendation rationale**: B is the minimum-viable path that solves the *runtime/content split* (the pattern every surveyed analogue uses). It does **not** strictly reduce step-count against today's `just setup` — see the walkthrough below — and it inherits two structural gaps: upstream plugin-dependency-sharing (#9444) and upstream rules-distribution. B's value is modularity, editability, and alignment with the plugin ecosystem — not raw friction reduction. A and D fight the architecture. C provides the single-verb UX at the cost of the modularity the user explicitly asked for. E and F have structural problems. G is a genuine open question (see Ask at end).

### Setup walkthrough: today vs. recommended

| Step | Today (`just setup`) | Recommended (approach B) |
|-|-|-|
| 1 | Install prereqs (`brew install just uv python3`) | Install prereqs (`brew install uv` — `just` no longer needed) |
| 2 | `git clone` | `curl -fsSL https://cortex.sh/install \| sh` — which internally does steps 3–6 |
| 3 | `just setup` (one verb, deploys everything) | `uv tool install -e ~/.cortex` |
| 4 | — | `cortex setup` (deploys `~/.claude/{hooks,rules,reference,notify.sh,statusline.sh}` + `~/.local/bin/*`) |
| 5 | — | Open Claude Code |
| 6 | — | `/plugin marketplace add owner/cortex-command` |
| 7 | — | `/plugin install cortex-core` |
| 8 | — | `/plugin install cortex-lifecycle` (if wanted) |
| 9 | — | `/plugin install cortex-overnight-integration` (if wanted) |
| 10 | — | (per target repo) `cortex init` |

**Net**: the curl bootstrap collapses steps 3–4 to one visible command, but the plugin enablement (6–9) and per-repo scaffolder (10) are new user-visible verbs. For a user who wants "the whole thing," the recommended path is **more steps, not fewer**. The friction benefit is entirely in the modularity — a user who wants *only* the lifecycle skill pack skips steps 4, 9, and 10.

**Upgrade verbs** under approach B: (i) `cortex upgrade` (git pull + `cortex setup`), (ii) `/plugin update <name>` (manual per plugin; no auto-update in third-party marketplaces), (iii) `cortex init --update` per target repo. Three channels, three verbs — this is a real regression against today's single `git pull && just setup`, and the research does not solve it.

---

## Decision Records

### DR-1: Ship the overnight runner as an `uv tool install`-able CLI + an MCP control-plane server

- **Context**: The runner is a long-running (multi-hour) Python process that spawns `claude` subprocesses, manages process groups, handles signals atomically, and operates on the user's local git repo. A *native* MCP server can't host the runner itself (SEP-1686 Tasks isn't released, plugin monitors die with session, stdio MCP servers aren't auto-restarted). But an MCP *control-plane* server — modeled on `dylan-gluck/mcp-background-job` — can expose tools that shell out to the CLI and poll its state files.
- **Options**: (a) CLI only, defer MCP server; (b) CLI + MCP control-plane built concurrently; (c) CLI + reserve-IPC-only.
- **Decision**: **(b) CLI + MCP control-plane concurrent.** The CLI ships with a `cortex mcp-server` subcommand exposing `start_run` / `status` / `logs` / `cancel` tools. Runner's IPC contract is designed upfront, not retrofit.
- **IPC contract the runner must expose** (prerequisite for the MCP control plane):
  - Versioned state-file schema in `lifecycle/overnight-state.json` — `schema_version` field; external consumers can detect compat breaks
  - Explicit subcommands: `cortex overnight start`, `cortex overnight status <id>`, `cortex overnight cancel <id>`, `cortex overnight logs <id> [--tail]`
  - PID + PGID record at `lifecycle/sessions/{id}/runner.pid` written atomically on start, removed on clean exit; `cancel` sends signal to PGID
  - `events.log` / `agent-activity.jsonl` gain a cursor protocol (byte offset or line number) so `logs --since <cursor>` is idempotent and cheap
- **Rationale**: The north star is "autonomous multi-hour development: send Claude to work with a plan, let it spin up its own teams." A CLI-only start forces the user out of Claude Code to initiate the very workflow that's supposed to be Claude-initiated. Building the MCP control plane now is the only path that actually realizes the north star; deferring it ships a CLI that locks its public contract before external consumers exist, making later retrofit more expensive than the upfront design.
- **Trade-offs**: L additional effort vs. CLI-only. In return: north-star-aligned UX, runner IPC is designed once and stable, no second release wave to add Claude-initiated starts.

### DR-2: Ship skills, hooks, and `bin/` utilities as two Claude Code plugins

- **Context**: Plugins are GA. `bin/` is auto-added to Bash PATH. `${CLAUDE_PLUGIN_DATA}` gives a stable venv location. Hook manifest supports the full event set. The existing `cortex-command-plugins` repo already demonstrates a working plugin marketplace for optional extras (`cortex-ui-extras`, `cortex-pr-review`, `android-dev-extras`, `cortex-dev-extras`); that repo stays separate.
- **Options**: (a) one mega-plugin, (b) two plugins split at the runner boundary, (c) three plugins, (d) keep symlink deploy.
- **Decision**: **(b) two plugins**:
  - **`cortex-interactive`** — all non-runner skills (commit, pr, lifecycle, backlog, requirements, research, discovery, refine, retro, dev, fresh, diagnose, evolve, critical-review, morning-review) + interactive-usable hooks (`cortex-validate-commit.sh`, `cortex-scan-lifecycle.sh`, `cortex-tool-failure-tracker.sh`). The lifecycle skill's "Implement in autonomous worktree" mode gracefully degrades when the runner CLI isn't installed (hides the menu item); other lifecycle modes still work.
  - **`cortex-overnight-integration`** — overnight skill + runner-only hooks. Installs on top of `cortex-interactive` for users who want Claude-initiated overnight starts and the integration bits that only make sense when the runner CLI is present.
- **Plugin dependency on the CLI tier** (explicit): both plugins depend on the CLI tier having run `cortex setup`. Plugins cannot fully function standalone — shared hooks (`notify.sh`), rules, reference, and statusline are not plugin-distributable today (upstream gap). `cortex setup` remains mandatory.
- **Trade-offs**: Skills get renamed to `/cortex:commit`, `/cortex:lifecycle`, etc. — breaking change for existing users but unavoidable for namespacing. `critical-review` / `morning-review` placement depends on one codebase verification (see Risks Acknowledged) — if those skills import `claude.overnight.*` at module load, they move to `cortex-overnight-integration`; if imports are conditional, they stay in `cortex-interactive`.

**Plugin dependency matrix** (revealed by critical review):

| Component | Required by | Can ship standalone? |
|---|---|---|
| `/commit` skill + `cortex-validate-commit.sh` hook | Every worker commit + every interactive commit | Yes — but the hook and the skill must ship in the *same* plugin. Correctly homed in `cortex-core` (interactive `/commit` is there), reused by the runner at worker-dispatch time. |
| `cortex-scan-lifecycle.sh` (SessionStart hook) | Runner (injects `LIFECYCLE_SESSION_ID`); lifecycle skill doesn't require it, but downstream analytics do | Yes — ships in `cortex-core` or `cortex-overnight-integration`. Put in `cortex-core` so interactive lifecycle work benefits from session correlation too. |
| `claude.overnight.report` Python module | `critical-review` and `morning-review` skills, when invoked via the runner. **Interactive standalone invocation must be verified** — if those skills import `claude.overnight.*` at module load, they break without the CLI installed. | Depends on verification. If they DO import unconditionally, `critical-review` and `morning-review` belong with `cortex-overnight-integration`. If imports are lazy/conditional, they can live in `cortex-interactive`. This is a codebase check the research did not complete — flagged as a prerequisite for the decomposition phase. |
| `claude.pipeline.*` Python package (`dispatch.py`, `merge.py`, `review_dispatch.py`) | Runner only — worker agents are spawned by `dispatch.py`. No skill invokes it directly. | Ships with the runner CLI, not with any plugin. |
| `claude/common.py` (imported by 15+ modules) | All runner Python + any skill that shells out to runner Python | Ships with the runner CLI via `uv tool install`. Plugins that need it must depend on the CLI being installed — they don't duplicate Python packages. |
| `~/.claude/notify.sh`, `statusline.sh`, `rules/*`, `reference/*` | Referenced literally in `~/.claude/settings.json`; hooks in plugin manifests that point to `${CLAUDE_PLUGIN_ROOT}` do NOT cover these | **Cannot ship via plugin** — plugin `settings.json` supports only `agent` and `subagentStatusLine` keys. Must be deployed by `cortex setup`. |

**Hard finding**: any plugin split leaves at least three components (`notify.sh`, `statusline.sh`, rules/) that must be deployed by the CLI tier. Plugins cannot be "independently installed" in any meaningful sense — they always require the CLI to have run `cortex setup` first. The "modular install" framing must be corrected to "modular *enablement*": a user who only wants interactive skills can install `cortex-interactive` and skip `cortex-overnight-integration`, but they still need the CLI installed for the shared hooks and rules to exist.

### DR-3: Remote MCP is the wrong architecture for the overnight runner

- **Context**: Cloudflare's hosted-MCP stack is real and productized, but a hosted server cannot see the user's local git worktree. Git-as-intermediary breaks the runner's live-edit + atomicity contract.
- **Options**: (a) full port to remote MCP, (b) remote MCP for a slice (backlog/lifecycle as GitHub-mediated markdown), (c) stay local.
- **Recommendation**: **(c) stay local** for the runner; optionally **(b)** for non-runner markdown operations, but treat as a separate, later project. Not blocking for the core distribution story.
- **Trade-offs**: Loses the "zero-local-install" fantasy. But preserving live-edit semantics is load-bearing for cortex-command's value — the runner's atomicity guarantees come from operating on the same filesystem where Claude Code and the user's editor also work.

### DR-4: Use `curl | sh` + `uv tool install -e .` as the primary install path

- **Context**: `uv` is already a hard dependency (runner shells `uv run`). `uv tool install -e .` preserves editability for users who want to fork. aider made this exact transition in Jan 2025.
- **Options**: (a) pipx, (b) `uv tool install`, (c) Homebrew primary, (d) PyInstaller binary, (e) npm, (f) Docker.
- **Recommendation**: **(b) `uv tool install`** wrapped in a `curl | sh` bootstrap (like `rustup`, `nvm`, `uv` itself). Homebrew tap as thin wrapper for discoverability (wraps the same curl script); Homebrew **does not own `~/.claude/` deployment**.
- **Trade-offs**: Requires `uv` on the user's system (the bootstrap installs it if absent). Homebrew users get a familiar discovery surface without the sandbox-hostile `post_install` problem.

### DR-5: `cortex setup` is the canonical `~/.claude/` deployment, not a package manager hook

- **Context**: No package manager on the shortlist can reliably write to `$HOME` in a user-respecting way. Homebrew's `post_install` re-runs on every upgrade → clobbers user customizations. npm's `postinstall` is a security smell and platform-variable. `uv tool install`'s sandboxed venv can't write outside itself.
- **Decision**: All `~/.claude/{skills,hooks,rules,reference,notify.sh,statusline.sh}` and `~/.local/bin/*` deployment happens in an explicit `cortex setup` subcommand. This is already what `just setup` does — just re-exposed through the CLI.
- **Rationale**: Separates *install the tool* (package manager's job) from *deploy config into my home* (explicit user action).
- **Relationship to #003 epic (honest)**: This **supersedes** parts of the in-flight shareable-install epic rather than matching it. Specifically: #006 ("make `just setup` additive") is largely obviated — if skills/hooks/bin ship via plugin, the `just deploy-*` recipes disappear; #007 (`/setup-merge` Claude-session skill) and `cortex setup` are two different commands in two different invocation contexts doing overlapping work. The overlap is real and must be resolved; see Ask at end. #004 (hook `cortex-` prefix rename) is still useful — plugin hook manifests benefit from consistent naming and the rename is mechanical. #005 (CLAUDE.md / rules strategy) is unchanged: plugins cannot distribute rules today, so the rules/ deployment remains `cortex setup`'s job (was `just setup`'s).
- **Cascade**: `cortex upgrade` = `git -C ~/.cortex pull && cortex setup --verify-symlinks`. Users on forks survive because their customizations are committed — git handles merges.

### DR-6: (folded into DR-1)

The MCP control plane is built concurrently with the CLI, not deferred. See DR-1 for the decision and the IPC contract.

### DR-7: Lifecycle/backlog/retros in the user's repo = shadcn-style scaffolding

- **Context**: cortex-command's `lifecycle/`, `backlog/`, `retros/`, `requirements/` directories live in the user's working repo, not in `~/.claude/`. Prior art only covers dotfile-destination content; user-repo destination is shadcn-only territory.
- **Decision**: Add a `cortex init` subcommand that scaffolds these directories (with templates) into the user's target repo — like `npx shadcn init`. Users can re-run `cortex init --update` to pull new templates.
- **Rationale**: Keeps the "user owns the code" model for content that's semantically part of their project. Avoids conflating machine-config deployment with project-content scaffolding.

### DR-8: Don't change the north-star yet; research informs a future decision

- **Context**: `requirements/project.md` lists "Published packages or reusable modules for others" as out-of-scope and frames sharing as clone/fork. This work would blur that line. The user answered "unsure — let research inform."
- **Decision**: The recommended path (plugin for skills + CLI for runner + `cortex init` scaffold) **does not fundamentally contradict clone/fork** — the runner CLI remains clone/fork-friendly via `uv tool install -e .`, and plugins are just git-repo-marketplaces. Publishing a Claude Code plugin is lighter-weight than "published package / reusable module" in the classical npm-or-PyPI sense.
- **Proposed update to `project.md`** (deferred to the epic that implements this):
  - Keep "clone or fork" as the primary sharing model.
  - Remove "Published packages or reusable modules for others" from Out of Scope.
  - Add to In Scope: "Plugin-based distribution of skills, hooks, and CLI utilities via Claude Code's plugin marketplace; `curl | sh`-installable runner CLI."
- **Rationale**: The recommended architecture lets a fork-first user keep forking *and* lets a casual user install via plugin + `uv tool install` without forking. The two models coexist.

### DR-9: `cortex-command-plugins` stays as the "extras" marketplace; this repo ships the core plugins

- **Context**: `~/Workspaces/cortex-command-plugins/` is an existing, working marketplace with `cortex-ui-extras`, `cortex-pr-review`, `android-dev-extras`, `cortex-dev-extras`. README frames it as "optional skills that not every project wants installed globally."
- **Decision**: Keep the split. `cortex-command-plugins` continues as the optional/per-project extras marketplace. `cortex-command` (this repo) publishes its own marketplace containing `cortex-interactive` and `cortex-overnight-integration` — the *core* agentic-layer plugins that replace the current `just deploy-skills` / `just deploy-hooks` architecture.
- **User UX**: adopters register both marketplaces (two `/plugin marketplace add` commands) and install packages from each as needed. Matches the shadcn precedent of multiple registries.
- **Rationale**: the two marketplaces have different audiences — core is "you need this to use cortex-command at all" while extras is "pick what's useful for your project." Absorbing extras into this repo would force global install of truly orthogonal skills (like `android-dev-extras`) on users who don't work on Android. Separate repos preserve that clean boundary.
- **Cascade**: the bootstrap installer may offer to register the extras marketplace at setup time (`cortex setup --with-extras`) as a convenience, but the default flow doesn't assume extras are wanted.

### DR-10: Distribution work goes first; #112 and #101 land on the new shape

- **Context**: Two in-flight backlog items touch the same surface as this work — #112 (LaunchAgent-based scheduler replacing `caffeinate+tmux` in `bin/overnight-schedule`), #101 (extract deterministic tool-call sequences into agent-invokable scripts, "both" invocation path per user decision).
- **Options**: (a) distribution first, (b) #112 first then distribution, (c) interleave.
- **Decision**: **(a) distribution first.** #112 and #101 both land on the new CLI shape (`cortex overnight schedule`, scripts in the CLI tier invoked from plugin skills and runner workers via PATH). Cleaner single migration; no re-pathing of plist `ProgramArguments` or script call-sites later.
- **Caveat**: #112 fixes a present-tense correctness defect (lid-close sleep breaks scheduled runs). If that starts actually biting — scheduled runs failing because laptop slept — ship #112 against the current `bin/overnight-schedule` as a correctness fix, then re-path when distribution lands. Path-update cost is mechanical.
- **Rationale**: the distribution work moves the entrypoints (`bin/overnight-*` → `cortex overnight *`) and establishes the scripts-home for #101. Landing #112 and #101 against the old shape and then migrating doubles the work for no architectural gain. User explicitly chose this ordering.

---

## Open Questions

- **Plugin namespace collisions**: once published, `/cortex:commit` is the address. Confirm as part of decomposition that this rename is acceptable to the user and callers are updated.
- **`Agents.md` / global rules distribution (clarified)**: plugins cannot distribute global rules today (upstream gap). `cortex setup` handles rules/ + reference/ deployment (it's what `just setup` does today, moved to the CLI). Permanent part of the CLI tier's scope, not a deferred unknown. #005 (non-destructive CLAUDE.md strategy, now complete) provided the user-scope rules verification that `cortex setup` depends on.
- **Dashboard packaging**: ship bundled with runner (recommended, FastAPI process co-installed with the runner CLI) — decomposition phase confirms.
- **`critical-review` / `morning-review` placement (one codebase check)**: do these skills import `claude.overnight.*` at module load (→ move to `cortex-overnight-integration`) or only when invoked through specific paths (→ stay in `cortex-interactive`)? Tractable check during decomposition; flagged as a gate.
- **Old installs migration**: existing users (the primary maintainer is currently the only one) have symlinked `~/.claude/skills/*`. Moving to plugins means `rm`ing those symlinks and `/plugin install cortex-interactive@...`. Migration path is a decomposition ticket — the migration is one-time and small since the user base is small.
- **Remote-MCP slice for backlog/lifecycle**: worth building *later* as a "manage your backlog from anywhere" feature, but not blocking. Flag for a future discovery.
- **Plugin `userConfig` for per-user settings**: could `cortex-overnight-integration` plugin prompt for `ANTHROPIC_API_KEY` / `CORTEX_COMMAND_ROOT` at enable-time via `userConfig`? Would reduce manual env-var setup. Decomposition decides.
- **Worktree constraint**: the runner uses `git worktree add`; a Dockerized version would need volume mounts for git state. If Docker is ever revisited, this is the sharp edge.

---

## Summary of Recommendations

**Core architecture:** Three-tier distribution.

1. **Plugin tier — two plugins in this repo's marketplace:**
   - `cortex-interactive` — non-runner skills + interactive-usable hooks + plugin `bin/` (auto-PATH). Self-sufficient for interactive use (lifecycle, backlog, commit, pr, research, discovery, refine, retro, dev, fresh, diagnose, evolve). Lifecycle's autonomous-worktree option gracefully degrades when the runner CLI isn't installed.
   - `cortex-overnight-integration` — overnight skill + runner-only hooks + MCP control-plane integration. Installed on top of `cortex-interactive` by users who want Claude-initiated overnight starts.
   - `cortex-command-plugins` (separate repo) continues to host optional per-project extras.
2. **CLI tier — the critical path.** `cortex` CLI installs via `curl | sh` bootstrap + `uv tool install -e .`. Owns: runner, dashboard, **MCP control-plane server** (`cortex mcp-server`), `cortex setup` (`~/.claude/` deployment), `cortex init` (per-repo scaffolder), agent-invokable scripts (epic #101's output), all Python modules plugins call into. Preserves fork/edit via `-e .`.
3. **Per-repo scaffold — `cortex init`** materializes `lifecycle/`, `backlog/`, `retros/`, `requirements/` into the user's target repo (shadcn-style). Users own the code.

**Realized value:**

- **Claude-initiated overnight starts** become possible (DR-1 merges the MCP control plane into the core work). A user inside Claude Code can say "start an overnight session" and have it fire without leaving the chat — the north-star UX that today requires a terminal context-switch.
- **Modular install** for users who only want interactive skills. Install `cortex-interactive`; skip `cortex-overnight-integration`. The lifecycle skill's autonomous-worktree mode hides itself when the runner isn't present.
- **Fork-friendly preservation**: `uv tool install -e .` keeps the runner editable; plugins are git-repo-marketplaces that accept forks; `cortex init` materializes templates the user can edit freely.

**Honest framing of friction**: the recommended path does **not** strictly reduce step-count vs today's `just setup` — see setup walkthrough. It introduces three upgrade verbs. The "minimal friction" win is for users who want a narrower install than everything; for users who want the full stack, it's roughly equal friction shaped differently, with the payoff of Claude-initiated overnight starts via the MCP server.

**Out:** Full remote-MCP port (architectural mismatch — DR-3); PyInstaller binary (kills forkability — approach F); Homebrew-primary (`post_install` sandbox hostility — approach E).

---

## Decision inventory (all resolved)

Every consequential call in the research is committed. Ready for Decomposition.

| # | Decision | Resolution | DR ref |
|---|----------|------------|--------|
| 1 | MCP control plane timing | **Build concurrently** with CLI. IPC contract specified upfront. | DR-1 (DR-6 folded in) |
| 2 | Plugin split shape | **Two plugins** at runner boundary (`cortex-interactive` + `cortex-overnight-integration`) | DR-2 |
| 3 | Autonomous-worktree handling | **Graceful degrade** — lifecycle hides the option when runner isn't installed | Risks Acknowledged |
| 4 | Epic #101 scripts placement | **CLI tier owns them**; plugin skills + runner workers both invoke via PATH | DR-2 + DR-10 |
| 5 | `cortex-command-plugins` repo | **Keep separate** as extras marketplace | DR-9 |
| 6 | Shareable-install epic (#003–#007) | **Already complete**; research builds on top, supersedes #006/#007 code which retires as part of this epic | Risks Acknowledged |
| 7 | Ordering with #112 and #101 | **Distribution first**; both later items land on new CLI shape (caveat: #112 may jump queue if scheduler correctness starts biting) | DR-10 |

---

## Risks Acknowledged

Surfaced by critical review. Each becomes a concrete decomposition input rather than a hidden assumption:

- **Plugin tier depends on CLI tier**. Both `cortex-interactive` and `cortex-overnight-integration` transitively need Python modules (`claude.overnight.*`, `claude.pipeline.*`, `claude/common.py`) that ship only with the CLI, plus `~/.claude/{notify.sh,statusline.sh,rules,reference}` that only `cortex setup` can deploy. The plugins promise modular *enablement* (pick interactive-only or add overnight-integration), not modular *install* — CLI is always required.
- **Migration cost is small but real**. The existing symlink-based install (primary maintainer's machine) needs a one-time migration: remove `~/.claude/skills/*` symlinks, run the new bootstrap installer, `/plugin install cortex-interactive` (+ optional `cortex-overnight-integration`), adjust muscle memory to `/cortex:*` slash-command names. Small user base (effectively one maintainer) keeps this tractable; migration script should be a decomposition ticket.
- **Shareable-install epic (#003–#007) is complete**, not in-flight — this research builds on top of those landed changes. Specifically: #005 (CLAUDE.md / rules strategy) gave `cortex setup` the user-scope rules behavior it relies on; #004 (hook `cortex-` prefix rename) gave plugin manifests consistent naming; #006 (additive `just setup`) and #007 (`/setup-merge` skill) are largely superseded by the CLI's `cortex setup` — their code can be retired as part of this epic rather than running both surfaces in parallel.
- **`apiKeyHelper` + OAuth token handling** is specific to the current install's `~/.claude/personal-oauth-token` / `~/.claude/work-api-key` pattern (see codebase report). `cortex setup` must port this cleanly; plugin `userConfig` could help but won't fully replace it (runner reads `~/.claude/settings.json` directly, not `settings.local.json`).
- **Three upgrade verbs** (`cortex upgrade` / `/plugin update` / `cortex init --update`) are a real regression vs. today's single `git pull && just setup`. Acknowledged upstream gap (plugin marketplace auto-update is not solved); no local mitigation.
- **"Interactive-only" skill import verification** is incomplete. `critical-review`/`morning-review` are claimed to run standalone without the runner; codebase analysis did not verify the import graph. Decomposition must run this check before assigning those skills to `cortex-interactive`.
- **Autonomous-worktree graceful degrade** is a new runtime behavior the lifecycle skill must learn. When `cortex` is not on PATH or `claude.overnight.daytime_pipeline` is not importable, the "Implement in autonomous worktree" menu option must be hidden (not errored). Decomposition ticket.
- **MCP control-plane + runner IPC contract** is additional scope vs a CLI-only release. L effort net — but removes the retrofit risk that would otherwise come due after users adopt the CLI's public interface.

---

*(All consequential decisions were resolved by user input during critical review; see Decision inventory above.)*
