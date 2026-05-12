# Research: No-clone install for cortex CLI via MCP auto-install

Topic: Migrate cortex CLI to a no-clone install path via `uv tool install git+https://github.com/charleshall888/cortex-command.git` (non-editable wheel install), with the `cortex-overnight-integration` plugin's MCP server auto-installing the CLI on first tool call when missing. Validation gate: non-editable wheel install correctness — smoke test that builds the wheel and exercises `cortex overnight start --dry-run`; `Path(__file__)` audit across 19 sites; `cortex upgrade` rewrite from git-pull-and-reinstall to `uv tool upgrade`. Update `requirements/project.md` to deprecate forkability-primary stance. Out of scope: PyPI publication (deferred); Homebrew tap (125 wontfix).

## Codebase Analysis

### Path(__file__) site-by-site classification

19 references in `cortex_command/` cataloged. Classification:

| File:line | Pattern | Class | Action |
|---|---|---|---|
| `init/scaffold.py:45` | `Path(__file__).resolve().parent / "templates"` | package-internal | → `importlib.resources.files("cortex_command.init.templates")` |
| `pipeline/conflict.py:29` | `parents[1] / "overnight/prompts/repair-agent.md"` | package-internal | → `importlib.resources.files("cortex_command.overnight.prompts").joinpath("repair-agent.md")` |
| `pipeline/review_dispatch.py:86` | `parent / "prompts" / "review.md"` | package-internal | → `importlib.resources.files("cortex_command.pipeline.prompts").joinpath("review.md")` |
| `overnight/brain.py:103` | `parent / "prompts/batch-brain.md"` | package-internal | → `importlib.resources.files("cortex_command.overnight.prompts").joinpath("batch-brain.md")` |
| `overnight/feature_executor.py:63` | `parents[1] / "pipeline/prompts/implement.md"` | package-internal | → `importlib.resources.files("cortex_command.pipeline.prompts").joinpath("implement.md")` |
| `dashboard/app.py:49` | `parent / "templates"` (Jinja2) | package-internal | → `importlib.resources.files("cortex_command.dashboard.templates")` |
| `overnight/plan.py:25` | `parents[2] / "lifecycle"` (`_LIFECYCLE_ROOT`) | **user-data** | → explicit injection (see Open Question 3) |
| `overnight/events.py:25` | `parents[2] / "lifecycle"` (`_LIFECYCLE_ROOT`) | **user-data** | → explicit injection |
| `overnight/orchestrator.py:53` | `parents[2] / "lifecycle"` (`_LIFECYCLE_ROOT`) | **user-data** | → explicit injection |
| `overnight/state.py:28` | `parents[2] / "lifecycle"` (`_LIFECYCLE_ROOT`) | **user-data** | → explicit injection |
| `overnight/outcome_router.py:307` | `parent.parent.parent` (`_PROJECT_ROOT`) | **user-data** + `sys.path.insert` | → explicit injection (security-sensitive — see Adversarial #5) |
| `overnight/report.py:493` | `parent.parent.parent.name` (home-repo name) | user-data | → explicit injection |
| `dashboard/seed.py:25` | `parents[2]` (`REPO_ROOT`) | user-data (dev seed) | → explicit injection or remove (dev-only utility) |
| `dashboard/app.py:42` | `parents[2]` (`root`) | user-data | → explicit injection |
| `dashboard/app.py:184` | `parent / ".pid"` | dev-runtime | → `${XDG_RUNTIME_DIR}/cortex-dashboard.pid` or similar |
| `pipeline/tests/test_metrics.py:15` | `parent / "fixtures"` | dev-only (test fixtures) | keep |
| `backlog/tests/test_telemetry_byte_equivalence.py:28` | `parent.parent.parent.parent` | dev-only (test) | keep |
| `overnight/tests/test_orchestrator_round_telemetry.py:34` | `parent / "fixtures"` | dev-only (test) | keep |
| `overnight/tests/test_auth.py:28` | `parents[3]` (`REPO_ROOT`) | dev-only (test) | keep |

**Summary**: 6 package-internal → `importlib.resources`; 8 user-data → explicit injection (mechanism TBD per Open Question 3); 4 dev-only → keep; 1 dev-runtime (`.pid` file) → relocate to `XDG_RUNTIME_DIR`.

### `cortex upgrade` rewrite surface

Current implementation at `cortex_command/cli.py:251-296` (`_dispatch_upgrade`):
1. `check_in_flight_install()` guard (keep)
2. Reads `CORTEX_COMMAND_ROOT` env or defaults to `~/.cortex` (remove)
3. `git status --porcelain` dirty-tree check (remove)
4. `git -C $cortex_root pull --ff-only` (remove)
5. `uv tool install -e $cortex_root --force` (remove)
6. Migration notice for stale `.mcp.json` (keep during transition)

New implementation: replace steps 2–5 with `subprocess.run(["uv", "tool", "install", "git+<url>@<ref>", "--reinstall"], timeout=60)` — see Open Question 2 for ref strategy.

### CORTEX_COMMAND_ROOT consumers

Becomes unused after migration. Consumers to remove:
- `cortex_command/cli.py:107, 184, 204, 260` — `_resolve_cortex_root()` discovery chain + upgrade cwd
- `tests/test_cli_upgrade.py:49, 146` — env-var override tests
- `tests/test_build_epic_map.py:41` — fixture sets it; update to use explicit injection

### MCP auto-install integration point

`plugins/cortex-overnight-integration/server.py` lines 195–223 currently emit a stderr warning at startup if `cortex` is missing. Auto-install hook lands at `_resolve_cortex_argv()` (lines 245–253) — before each tool handler delegates. Pattern:

```python
def _ensure_cortex_installed() -> None:
    """First-install gate — runs before each tool handler delegates.
    
    Reuses 146's flock + skip-predicates + NDJSON pattern. Lock at
    ${XDG_STATE_HOME:-$HOME/.local/state}/cortex-command/install.lock
    (NOT $cortex_root/.git/cortex-update.lock — that path doesn't exist
    pre-install).
    """
```

Critical context (from Adversarial #1): the plugin's `.mcp.json` is `{"command": "uv", "args": ["run", "${CLAUDE_PLUGIN_ROOT}/server.py"]}`. If `uv` is not findable when Claude Code launches the MCP, the MCP never starts at all — by the time `server.py` is executing, `uv` was already on PATH. The auto-install can rely on `subprocess.run(["uv", ...])` resolving the same way.

### pyproject.toml wheel build

Already correct. `[tool.hatch.build.targets.wheel] packages = ["cortex_command"]` ships all `.md` files under `cortex_command/` by default (hatchling's default behavior). No `package-data` or `include` directives needed. Verify with `python -m zipfile -l <wheel.whl> | grep -E '(prompts|templates)' | grep .md` post-build.

### Patterns to reuse from 146 and elsewhere

1. **Flock pattern** (146 R11, also in `init/settings_merge.py:69-85`): `fcntl.flock(LOCK_EX)` with 30s timeout; release in try/finally; re-verify after acquire.
2. **Skip-predicate pattern** (146 R9, server.py:443-497): `CORTEX_DEV_MODE=1` + dirty-tree + non-main-branch checks. **Note: predicates (b) and (c) do not apply pre-install** — only `CORTEX_DEV_MODE=1` is meaningful.
3. **NDJSON error log** (146 R14, server.py:374-428): `_append_error_ndjson(stage="cortex_install", error=..., context=...)`.
4. **importlib.resources pattern** (already used in `runner.py:33` + `fill_prompt.py:13-34`): `files("pkg.subpkg").joinpath("name.md").read_text(encoding="utf-8")`.
5. **Subprocess test mocking** (`tests/test_cli_upgrade.py:37-84`): `patch("subprocess.run", MagicMock(side_effect=[...]))`.

### Files that will change (summary)

| File | Change |
|---|---|
| `cortex_command/cli.py:251-296` | Rewrite `_dispatch_upgrade` to `uv tool install --reinstall git+<url>@<ref>` |
| `cortex_command/cli.py:168-209` | Delete `_resolve_cortex_root()` |
| `cortex_command/install_guard.py` | Update error messages; remove `~/.cortex` references |
| 6 package-internal `Path(__file__)` sites | Convert to `importlib.resources` |
| 8 user-data `Path(__file__)` sites | Convert to explicit injection (mechanism TBD) |
| `plugins/cortex-overnight-integration/server.py` | Add `_ensure_cortex_installed()`; integrate into tool handlers |
| `install.sh` | Deprecate or rewrite to use `uv tool install git+...` |
| `requirements/project.md` (L7-8, L26, L55) | Deprecate forkability-primary stance |
| `CLAUDE.md` (L5, L22) | Reflect new install model |
| `pyproject.toml` | No change (build config already correct) |
| `.claude-plugin/marketplace.json` | No change |

## Web Research

### `uv tool install` semantics with git URL — VERIFIED

**Non-editable install from git URL: confirmed.** `uv tool install git+https://github.com/<org>/<repo>.git` performs non-editable install: clones repo, builds wheel, installs console scripts. Editable mode rejected for git URLs. ([uv docs](https://docs.astral.sh/uv/guides/tools/), [astral-sh/uv #5442](https://github.com/astral-sh/uv/issues/5442))

**Ref pinning: confirmed.** Branch (`@master`), tag (`@v3.0.0`), commit SHA (`@2843b87`) all supported. `uvx --from git+...@<ref>` accepts the same syntax.

**⚠ CRITICAL GOTCHA — Branch refs don't auto-refresh on `uv tool upgrade`.** This is the most load-bearing finding for the migration. uv pins to a resolved commit hash at install time; `uv tool upgrade` respects that pin. There is **no `@latest` shortcut for git installs**. Recommended workflow: `uv tool install "git+<url>@<ref>" --reinstall` (force re-clone). Branch HEAD-tracking is buggy (uv [#4317](https://github.com/astral-sh/uv/issues/4317), [#9146](https://github.com/astral-sh/uv/issues/9146), [#14954](https://github.com/astral-sh/uv/issues/14954)); tags and SHAs are reliable. **Practical implication**: prefer tag-pinned releases (`@v0.1.0`); `cortex upgrade` should be `uv tool install --reinstall`, not `uv tool upgrade`. (See Open Question 2.)

**Console scripts on reinstall: regenerated automatically** — uv places shims at install time; any `--reinstall` refreshes them.

**Dependency drift on reinstall: re-resolved** — `--reinstall` re-resolves `pyproject.toml` deps fresh.

### `importlib.resources` under non-editable wheel — VERIFIED

**Universal Traversable API** (works on unpacked wheel + zipapp + editable):
- `.is_file()`, `.is_dir()`, `.read_text(encoding=...)`, `.read_bytes()`, `.iterdir()`, `.joinpath(*parts)`, `.open(mode, ...)`, `.name`

**Does NOT work under zipapp** (use `importlib.resources.as_file()` to materialize a tempfile): `pathlib.Path`-only methods like `.stat()`, `.chmod()`, `.glob()`, `.resolve()`, `.absolute()`. Pattern:
```python
from importlib.resources import files, as_file
with as_file(files("cortex_command.templates").joinpath("foo.md")) as p:
    # p is a real pathlib.Path here
```

**Editable-install caveat (relevant since migrating AWAY from editable):** known bugs with `MultiplexedPath` validation rejecting `__editable__.*finder.__path_hook__` pseudo-path ([importlib_resources #311](https://github.com/python/importlib_resources/issues/311), [#287](https://github.com/python/importlib_resources/issues/287), [cpython #106614](https://github.com/python/cpython/issues/106614)). Migration to non-editable **fixes** a class of latent bugs.

### MCP-server-installs-CLI prior art — NONE FOUND

**No mature self-bootstrap pattern exists in the wider ecosystem.** The dominant idiom is the inverse: the MCP server itself is the `uvx`/`uv tool install` target, not a self-installer.

Closest patterns:
- **`uvx <pkg>` as MCP `command`** in `.mcp.json` — uvx handles install ephemerally on first call (default for `aider-mcp`, `mcp-background-job`).
- **`uv --directory <path> run <module>`** — chess-mcp pattern, MCP bootstraps deps from `pyproject.toml`.
- **PEP 723 single-file MCP servers** — uv resolves inline `# /// script` deps on first invocation.

**Anti-pattern: explicit `subprocess.run(["uv","tool","install",...])` from inside an MCP server tool handler.** Zero published examples. Likely reasons (search-derived): uvx already gives ephemeral install for free; PATH inheritance issues; first-call latency surfaces as tool timeout. **The cortex pattern is novel.** (See Adversarial #3 for full critique.)

### Sandbox / permission for MCP subprocesses — VERIFIED

**Sandbox scope: Bash tool only.** Per [Claude Code sandboxing docs](https://code.claude.com/docs/en/sandboxing): "The sandbox isolates Bash subprocesses. Other tools operate under different boundaries." MCP servers launch outside the bash sandbox; their subprocesses inherit the shell environment Claude Code itself was launched with.

**PATH inheritance: known footgun** ([builder.io guide](https://www.builder.io/blog/claude-code-mcp-servers)): "Claude Code launches MCP server subprocesses with a different shell environment than your terminal, so tools like node and npx may not be found." Applies to `uv` too. Mitigation: probe `shutil.which("uv")` at MCP start; surface structured error with PATH-fix pointer (see Adversarial #1 — macOS GUI-app + Homebrew + `.zshrc`-only is a known misconfiguration).

**Permission prompts for MCP-spawned `uv tool install`: NONE.** MCP isn't sandboxed; install writes to `~/.local/share/uv/tools/`, `~/.local/bin/cortex` happen freely with no prompt. This is a defense-in-depth asymmetry vs. the Bash tool path (see Adversarial #9).

### Comparable tools

- **aider** — dual: `pip install` + `curl|sh`. MCP plugin (`aider-mcp`) independently distributed, assumes aider on PATH.
- **opencode / goose** — separate CLI + MCP-via-uvx. No bundled-CLI-in-MCP pattern.
- **mcp-background-job** — MCP IS the product, no separate CLI.

**No comparable tool ships a Python CLI that auto-installs itself from inside an MCP server.** Cortex's design is novel.

Sources:
- [docs.astral.sh/uv: Using tools](https://docs.astral.sh/uv/guides/tools/)
- [docs.astral.sh/uv: Tools concepts](https://docs.astral.sh/uv/concepts/tools/)
- [pydevtools: distributing internal CLI tools with uv](https://pydevtools.com/handbook/how-to/how-to-distribute-internal-python-cli-tools-with-uv/)
- [docs.python.org: importlib.resources](https://docs.python.org/3/library/importlib.resources.html)
- [code.claude.com: Sandboxing](https://code.claude.com/docs/en/sandboxing)
- [code.claude.com: Plugins](https://code.claude.com/docs/en/plugins)
- [astral-sh/uv #4317, #9146, #14954, #5442](https://github.com/astral-sh/uv/issues)
- [python/importlib_resources #311, #287](https://github.com/python/importlib_resources/issues)

## Requirements & Constraints

### From `requirements/project.md`

- **L7** — "Primarily personal tooling, shared publicly for others to clone or fork." Update to deprecate clone/fork as primary identity.
- **L26 — Architectural constraint (still applies):** "Per-repo sandbox registration: `cortex init` additively registers the repo's `lifecycle/` path in `~/.claude/settings.local.json`'s `sandbox.filesystem.allowWrite` array." → `cortex init` must remain available under no-clone install.
- **L27** — SKILL.md-to-bin parity enforcement: any new bootstrap scripts must pass `bin/cortex-check-parity`.
- **L34 — Quality attribute (intersects this work):** "Defense-in-depth for permissions... For sandbox-excluded commands, the permission allow/deny list is the sole enforcement layer." MCP-orchestrated auto-install bypasses interactive permission prompts entirely (see Adversarial #9).
- **L55 — DIRECTLY AFFECTED, FLAG FOR UPDATE:** "Published packages or reusable modules for others — the `cortex` CLI ships as a local editable install (`uv tool install -e .`) for self-hosted use; publishing to PyPI or other registries is out of scope." Replace with non-editable wheel install via git URL; PyPI remains out of scope.

### From `requirements/observability.md`

- **L122-146 — Install-mutation invocations** are tracked; new no-clone install path is a new entry point that must:
  - Call `cortex_command.install_guard.check_in_flight_install` explicitly.
  - Update L141 classification text (currently lists `uv tool install -e ... --force` — `-e` flag goes away).
  - Update L142: MCP-spawned auto-install becomes a new install-mutation orchestrator; classification text needs the first-install pattern.
- **L57** — Runtime telemetry error log at `~/.cache/cortex/log-invocation-errors.log` (pattern reference for first-install failure logging).

### From `requirements/pipeline.md`

- **L153** — MCP control-plane contract (5 stdio tools wrapping `cli_handler`); pre-dates 146 (post-146, MCP is plugin-bundled, not `cortex mcp-server`).
- **L154 — Pre-install in-flight guard:** `cortex` aborts when an active overnight session is detected; bypass via `CORTEX_ALLOW_INSTALL_DURING_RUN=1`. Auto-install on first MCP call must compose with this guard.
- **L155 — `lifecycle/sessions/{session_id}/runner-bootstrap.log`** captures runner stdout/stderr on the MCP-spawned start path. Pattern reference for first-install failures.
- **L150 — Smoke test gate** (`cortex_command/overnight/smoke_test.py`) — post-merge verification pattern; could extend to first-install verification.

### From `CLAUDE.md`

- **L5 / L22 — DIRECTLY AFFECTED:** Both reference `uv tool install -e .` as ship mode. Update.
- **L36** — confirms `uv` is the assumed install vehicle.
- **L40** — commit via `/cortex-interactive:commit`; imperative mood, ≤72 chars.
- **L48** — `just setup-githooks` is maintainer-only; non-clone install users don't need it.

### From 146's spec (most load-bearing — first-install extends 146's auto-update)

- **R3 (`cortex --print-root` JSON contract):** Returns `{"version": "1.0", "root": ..., "remote_url": ..., "head_sha": ...}`. **First-install can't run R3 — `cortex` doesn't exist yet.** Discovery chain on `cortex` not on PATH must be revised (see Edge Cases L123 — today hard-fails; this ticket restructures into auto-install).
- **R8 (throttle cache):** `git ls-remote <remote-url> HEAD` cached for MCP server lifetime. Cache key includes `cortex_root absolute path` — but that path doesn't exist pre-install. Cache key forms must handle absent CLI.
- **R9 (skip predicates):** `CORTEX_DEV_MODE=1`, dirty tree, non-main branch. **Predicates (b) and (c) assume a local clone — neither applies pre-install.** Skip-predicate semantics differ between first-install and subsequent upgrade.
- **R10 (orchestration):** Spawns `cortex upgrade`. **First-install can't spawn `cortex upgrade` because `cortex` doesn't exist.** First-install needs separate `uv tool install --reinstall git+...` invocation.
- **R11 (concurrency-safe via flock):** Lock at `$cortex_root/.git/cortex-update.lock`. **First-install has no `$cortex_root/.git/`.** First-install needs alternate lock path — `${XDG_STATE_HOME:-$HOME/.local/state}/cortex-command/install.lock`.
- **R12 (verification probe):** `cortex --help` + `cortex overnight status --format json`. **Both require a working install.** Same probe pattern fits first-install; "fall through to on-disk CLI" doesn't apply (there is no on-disk CLI on first-install).
- **R14 (NDJSON failure surface):** `${XDG_STATE_HOME}/cortex-command/last-error.log` with `{ts, stage, error, context}`. First-install errors use the same surface; new `stage` value `"first_install"`.
- **R18 (sandbox empirical probe):** Probe operations included `uv tool install -e ... --force`. **First-install changes operation 3 to `uv tool install --reinstall git+...` (non-editable).** R18 probe outcome must be re-validated for the no-clone install path.
- **R19 (notice-only fallback):** When sandbox probe fails, surface "cortex update available — run `cortex upgrade`" notice in tool response. Equivalent fallback for first-install: "cortex CLI not installed — run `uv tool install git+...`".
- **R22 / Threat Model (spec.md:97-106) — DIRECTLY AMPLIFIED:** "MCP-orchestrated auto-update is auto-RCE." First-install **expands** the threat surface — predicates that limit auto-update don't apply pre-install. (See Adversarial #2.)
- **Edge Cases L123 — DIRECTLY RELEVANT:** "`cortex` not on PATH" today hard-fails; this ticket restructures into auto-install. Discovery chain must be revised — editable-install `.pth` and `$HOME/.cortex` legs become irrelevant.
- **Non-Requirements L113-115:** "PEP 723 + uvx is the deps mechanism. No vendored deps... No multi-version compatibility between MCP and CLI." Constrains: first-install must produce a CLI version compatible with bundled MCP (see Adversarial #12 / Open Question 5).

### From 113's discovery research (`research/overnight-layer-distribution/research.md`)

- **DR-4** — reasoned about `uv tool install` + `curl|sh` bootstrap + editable install. This migration is a strict simplification of DR-4 — eliminates the curl bootstrap and editable clone in favor of direct git install.
- **DR-5** — `cortex setup` separation: explicit user action for `~/.claude/` deployment. (Note: 117 retired `cortex setup` per 115's review note; not blocking.)
- **DR-7** — `cortex init` per-repo scaffolder must remain available to non-clone-install users.
- **DR-8** — proposed update to `project.md` to remove "Published packages..." from Out-of-scope. The migration extends DR-8 with non-editable wheel as the primary install path.
- **Three upgrade verbs called out as a regression** (L225, L387): `cortex upgrade`, `/plugin update`, `cortex init --update`. Migration doesn't fix this; acknowledged upstream gap.

## Tradeoffs & Alternatives

User chose `uv tool install git+<url>` (non-editable) + MCP-orchestrated auto-install on first tool call during Clarify. Research validates this against four alternatives.

### Alternative A — Bundle CLI inside the plugin tree

`plugins/cortex-overnight-integration/cli/` ships the `cortex_command` package directly; MCP invokes `uv run --from ${CLAUDE_PLUGIN_ROOT}/cli cortex <args>`. Updates flow through Claude Code's plugin auto-update.

- **Complexity**: Medium-high. ~17K LOC mirror surface (extends existing dual-source pattern ~10×). Reworks `_resolve_cortex_argv()` and `cortex --print-root`.
- **Maintainability**: Worse. Couples CLI release cadence to plugin release cadence.
- **Performance**: Worst. `uv run --from <plugin-root>` resolves dep tree per call (~3-8s cold) vs. persistent shim (~50ms).
- **Alignment**: Poor — back-couples MCP runtime and CLI, defeating 146's deliberate decoupling.
- **Verdict**: REJECT.

### Alternative B — uvx ephemeral execution from the MCP

MCP invokes `uvx --from git+<url>@<ref> cortex <args>` per tool call. No persistent install.

- **Complexity**: Lowest. ~50 LOC removed (no flock, no install detection, no probe).
- **Maintainability**: Mixed. Removes install-orchestration surface but shifts failure to "first-call-after-restart is slow." uvx git-ref cache semantics fight 146's observable orchestration.
- **Performance**: First-call-after-restart ~5-15s. Subsequent ~200-500ms. **Restart tax compounds for long overnight sessions.**
- **Alignment**: Poor — hides upgrade behind cache-key opacity vs. 146's observable orchestration. Breaks bare-shell access.
- **Verdict**: REJECT.

### Alternative C — Hybrid PyPI + git URL

Publish to PyPI in addition to git URL. Both paths coexist.

- **Complexity**: Medium-low. ~1 day for publish pipeline (GitHub Actions, OIDC, version source).
- **Maintainability**: Adds release-discipline burden. Permanent versioning commitment on PyPI.
- **Performance**: Equivalent to chosen path.
- **Alignment**: Compatible with 122 + 146. Discoverability + version-pinning gain.
- **Verdict**: DEFER (user's explicit choice). Net-additive — doesn't break git URL path; can ship later.

### Quickly dismissed alternatives

- **PEP 723 single-file**: dismissed (CLI is 17K LOC across 8+ subpackages).
- **PEX/zipapp**: dismissed (interpreter lock + infra cost; no improvement on user's "no-clone" goal vs. uv git URL).
- **Anthropic official marketplace listing**: orthogonal; recommend filing as separate ticket.

### Recommended approach (validated)

User's chosen path holds:
1. **Composes with 146's already-shipped infrastructure** (flock, NDJSON, throttle cache, schema gate).
2. **Preserves bare-shell forker access** (`cortex` on PATH after install) — A and B break this.
3. **Performance profile matches MCP-primary usage** (one-time install amortizes across thousands of sub-100ms calls).
4. **Avoids re-litigating rejected alternatives** (PyPI deferred; Homebrew wontfix; bootstrap deprecating).

### Trade-offs accepted by the recommended path

- Network dependency on first MCP call when CLI is missing.
- Concurrent-install coordination (lock at `${XDG_STATE_HOME}/cortex-command/install.lock`).
- No version pinning with `git+<url>@main` (HEAD at install time; see Open Question 2).
- 19-site `Path(__file__)` audit is real and load-bearing.
- Pre-install vs post-install skip-predicate semantics differ.

## Adversarial Review

12 substantive challenges to the proposed approach. Numbered for reference in Open Questions.

### 1. PATH inheritance for MCP-launched `uv` is a real macOS GUI-app footgun

The MCP itself is launched via `command: "uv"` in `.mcp.json`; if `uv` is not findable when Claude Code launches the MCP, the MCP never starts at all. The `uv` chain inside `server.py` is therefore safe in nominal cases. **However**, on macOS, Claude Code as a `.app` may run with a non-interactive shell environment that doesn't read `~/.zshrc`; users who installed `uv` via Homebrew without `~/.zshenv` will silently lose `/opt/homebrew/bin` from PATH. This is a known misconfiguration. **Mitigation**: probe `shutil.which("uv")` at server start; on miss, surface structured error pointing at the Homebrew/PATH fix.

### 2. Auto-install AMPLIFIES 146's auto-RCE blast radius

146 accepted "MCP-orchestrated upgrade is auto-RCE" against an attacker who has compromised an upstream repo a user has already vetted. **First-install auto-RCE has strictly larger surface**: a user who installs the plugin (which itself is git-SHA-pinned) implicitly trusts whatever URL the plugin points at, with **no clone-time inspection opportunity**. Worse, 146's skip predicates (CORTEX_DEV_MODE, dirty tree, non-main branch) all assume a local checkout exists — pre-install, none apply. **First auto-install is unconditional.** This is a defense-in-depth regression vs. 146.

**Recommended mitigation**: First-install path SHOULD require a one-time interactive opt-in, surfaced as a structured MCP tool error ("CLI not installed. Set `CORTEX_AUTO_INSTALL=1` to enable auto-install."). Subsequent upgrades use 146's throttle. (See Open Question 1.)

### 3. The "novel pattern" is novel because it's an anti-pattern

Web agent found zero prior art for an MCP server that self-bootstraps a separate CLI tool via `subprocess.run(["uv","tool","install"...])`. This is a warning, not a green field. The standard pattern is to **bundle the binary inside the plugin** (uvx-delivered) or **declare it as a user dependency**. Self-bootstrapping mixes concerns:
- Privilege model: MCP servers are tool servers, not package managers.
- Failure recovery: half-failed installs (network drop mid-download) become MCP's responsibility to clean up.
- Audit trail: tool calls are logged separately from install operations; folding install into a tool handler obscures both.
- Cascading updates: plugin refresh revs MCP, which auto-rebootstraps CLI — version churn.

This isn't a fatal objection but the design must be *explicit* about why cortex is doing this novel thing.

### 4. Branch-ref upgrades are silently broken; project has zero release discipline

`pyproject.toml` shows `version = "0.1.0"`, hand-set, no version-bump commits in git log, no GitHub Actions release workflow, no `git tag` discipline. The proposed migration depends on `uv tool install git+<url>@<ref>`. If `<ref>` is `main`, uv pins to a resolved commit hash and `uv tool upgrade` doesn't re-fetch. If `<ref>` is a tag, the project doesn't produce them.

**This is a hidden prerequisite the migration spec must surface**: introducing tag-based releases (CI tag-on-merge, version-bump discipline) is implicit infrastructure work, larger than the migration itself. **Otherwise `cortex upgrade` becomes `uv tool install --reinstall` — full re-clone and rebuild on every upgrade**, which is heavyweight and conceals what changed. (See Open Question 2.)

### 5. `Path.cwd()` is silent corruption; explicit env-var injection is the only honest replacement

Codebase agent's `Path.cwd()` recommendation collapses two distinct semantic intents:
- `dashboard/seed.py:25`, `dashboard/app.py:42` — "the cortex-command dev repo" (dev-only)
- `overnight/plan.py:25`, `events.py:25`, `orchestrator.py:25`, `state.py:28` — "the user's cortex-command project root" (where lifecycle/ lives)
- `outcome_router.py:307` — `_PROJECT_ROOT` is appended to `sys.path` for plugin discovery (security-sensitive)

`Path.cwd()` would silently produce different behavior for each:
- User running `cortex overnight start` from `~/projects/foo/` would have cortex try to read `~/projects/foo/lifecycle/` — wrong if foo is a target project, not the cortex repo.
- `outcome_router`'s `sys.path.insert` would insert user's CWD into import path — **CWD-as-import-root is a classic Python foot-gun (cf. CVE-2015-5652).**

**Honest replacement: `CORTEX_REPO_ROOT` env-var-injection populated by `cortex init`** at per-project setup time, read with clear error message on miss. Making this implicit-via-CWD will create silent corruption — running from the wrong directory writes lifecycle artifacts to a CWD-derived path and the user won't know until they wonder where session state went. (See Open Question 3.)

### 6. Existing maintainer's editable install creates a console-script collision

Tradeoffs agent dismissed migration-for-existing-users as out of scope. **This is wrong.** Maintainer's current install:
- `~/.local/share/uv/tools/cortex-command/` editable install pointing at `/Users/charlie.hall/Workspaces/cortex-command`
- `~/.local/bin/cortex` shim resolving to working tree

After migration, running `uv tool install git+<url>` errors: "tool already installed" unless `--force` or `--reinstall` is passed. **Every existing user's first install attempt fails** with a confusing error. The dual-source pre-commit hook continues to reference the working tree, but the CLI now shells out to a wheel-install version that doesn't know about the working tree — hooks may invoke the wrong cortex.

**Migration MUST**: (a) include documented `uv tool uninstall cortex-command && uv tool install git+...` runbook; (b) auto-install path must use `--reinstall` (not bare install) to be idempotent against any prior install state.

### 7. uv version skew between MCP launch and auto-install

The plugin's `.mcp.json` says `command: "uv"` — whatever's on PATH. If user has uv 0.4.x (`uv tool` stable) the auto-install behaves correctly. If older uv 0.2.x (different `uv tool install` semantics), the auto-install can silently emit a different layout. **Migration must declare a minimum uv version** (`uv --version` probe at MCP start; refuse below the pin).

### 8. Concurrent first-install fails into corruption-then-confusion, not deadlock

Lock at `${XDG_STATE_HOME}/cortex-command/install.lock` solves acquisition. But what happens to the LOSER on timeout?

- Session A acquires lock → `uv tool install` → network drops at 95% → 30s lock held → `uv tool install` returns nonzero → NDJSON-logs error → releases lock.
- Session B times out at 30s waiting → "MCP available, CLI absent."
- Both sessions report "CLI not found." User retries from B → `uv tool install` runs again on possibly-corrupt partial install dir.

**Mitigation**: First-install lock release MUST signal install-failure to subsequent waiters (sentinel file alongside lock indicating "last attempt failed at <ts>; manual `uv tool install --reinstall` required"). Otherwise users fall into a retry loop where each session both (a) sees missing CLI and (b) attempts reinstall on partial state.

### 9. Sandbox-write surface for first-install bypasses Bash permission prompts entirely

CLAUDE.md confirms `cortex init` writes one entry per repo to `~/.claude/settings.local.json`'s `allowWrite` array. But `uv tool install` writes to:
- `~/.local/share/uv/tools/cortex-command/`
- `~/.local/bin/cortex`
- `~/.cache/uv/`
- `~/.local/state/cortex-command/`

**None of these are in default `allowWrite`.** MCP servers run outside Bash sandbox — but Claude Code's filesystem permission prompts are enforced at the SDK level for the Bash tool. **MCP-spawned subprocess of `uv tool install` triggers ZERO permission prompts.** User gets system mutation (binary install + package install) with no prompting.

This isn't a bug — MCP servers are trusted by design — but it's an **asymmetry users may not expect**: Bash tool requires permission to run `uv tool install`; MCP-spawned subprocess of the same command does not. Document this in the spec or accept as known regression.

### 10. Test design is skin-deep for the cross-process scenarios that are the actual delta from 146

Proposed smoke test (build wheel, install in tmpdir, invoke MCP, run dry-run) is happy-path integration only. Does not cover:
- Concurrent two-session first-install race (requires `multiprocessing` + ~2 minutes of real `uv tool install` per test — not standard CI).
- Half-failed install (network drop mid-download — needs fault injector around `subprocess.run`).
- "`cortex --help` returns 0 but real tool call fails" (needs round-trip through `overnight start --dry-run` AND `overnight status`).
- Skip-predicate asymmetry pre-install vs post-install (only `CORTEX_DEV_MODE=1` applies pre-install).

The smoke test catches "wheel install layout breaks `importlib.resources`." It does NOT catch the cross-process / concurrent / failure-injection scenarios that are the actual delta from 146.

### 11. `cortex --help` post-verification has known false-pass modes

146 R12's `cortex --help` (timeout=10) catches "shim missing" and "shim points at non-existent path." Does NOT catch:
- "Shim resolves to a Python with different deps than what cortex needs" (deps mismatch).
- "Wheel install succeeded but `importlib.resources.files()` doesn't find prompts."
- "cortex CLI works but `cortex --print-root` fails."

**Stronger probe: `cortex --print-root`** (which 146 already uses as discovery handshake). Exercises JSON contract, install_guard import, and at least one `Path(__file__)` resolution. Free signal — recommend strengthening.

### 12. Plugin/CLI version skew under SHA-pinned plugins is unbounded

Plugins are git-SHA-pinned (122). Plugin embeds a hardcoded URL like `git+https://github.com/charleshall888/cortex-command.git`. Two users on different plugin SHAs:
- Plugin SHA A says `MCP_REQUIRED_CLI_VERSION = "1.0"`.
- Plugin SHA B (newer) says `MCP_REQUIRED_CLI_VERSION = "2.0"`.
- Both auto-install HEAD of cortex repo (currently `version: "1.0"`).
- Plugin B's MCP rejects every payload with `SchemaVersionError: major-version mismatch`. No clear resolution path.

The 146 schema gate is **forward** compatibility check, not coordination mechanism. Under no-clone, plugin and CLI are decoupled in install graph but coupled in schema contract. Realistic mitigations:
- **Plugin embeds CLI git tag in URL**: `git+<url>@v1.2.0`. Requires tag discipline (#4).
- **Auto-install uses plugin's pinned CLI tag** — but `uv tool install` is global per name; second install with `--reinstall` overwrites first; doesn't compose across plugins.
- **Document mismatch resolution**: surface "downgrade plugin OR upgrade cortex" in error.

Migration's silence on plugin-CLI coupling is a significant gap. (See Open Question 5.)

## Open Questions

All 9 items below were resolved at Research Exit Gate (2026-04-29). Q1, Q2, Q3, Q5 resolved by user; Q4, Q6, Q7, Q8, Q9 deferred to Spec with documented defaults.

### Q1. First-install opt-in vs zero-friction — RESOLVED: zero-friction

User chose strict zero-friction: auto-install runs unconditionally on first MCP call. Spec must include a security section documenting that first-install **expands** 146's auto-RCE blast radius (no skip predicates apply pre-install; user has no clone-time inspection opportunity). Trade-off accepted because the trust model already includes the maintainer's GitHub repo and the project ships as personal tooling. Mitigation: structured NDJSON failure log on every install attempt (146 R14 pattern) gives an audit trail.

### Q2. Tag-based releases vs --reinstall-only — RESOLVED: tag-based releases now

User chose to commit to tag-based releases. Ticket scope expands to include:
- Semver discipline starting at `v0.1.0` (matches current pyproject.toml literal).
- GitHub Actions release pipeline: tag-on-merge or manual tag-trigger that builds the wheel and creates a GitHub release.
- Release notes / CHANGELOG discipline.
- `cortex upgrade` rewrite uses `uv tool upgrade cortex-command` against the tag-pinned install (or `uv tool install --reinstall git+<url>@<tag>` if upgrade-on-tag-pin doesn't auto-bump — confirm in Spec).
- Plugin's auto-install URL embeds the matching tag (couples Q5).

### Q3. User-data Path(__file__) replacement — RESOLVED: Path.cwd() with vestigial-code deletion

User clarified design intent: most users don't clone the cortex repo; they run `cortex` (via MCP) from inside their own project repo. Therefore CWD = user's project root = where `lifecycle/` and `backlog/` should live. `Path.cwd()` is the correct semantic anchor for this use case, not silent corruption.

Resolution per code inspection:
- **All 7 user-data sites** (`overnight/plan.py:25`, `events.py:25`, `orchestrator.py:25`, `state.py:28`, `report.py:493`, `dashboard/seed.py:25`, `dashboard/app.py:42`) → replace with `Path.cwd() / "lifecycle"` (or equivalent).
- **`outcome_router.py:307-309`** (`sys.path.insert(0, _PROJECT_ROOT)`) → **DELETE entirely.** Vestigial — under both editable and non-editable installs, `cortex_command` is already on `sys.path` because the package is installed. The `sys.path.insert` was a defensive scaffold from a pre-installed-package era. Deleting it removes the security concern (CWD-as-import-root).
- **`outcome_router.py:360, 417`** (`_PROJECT_ROOT / "backlog"` fallback for `_backlog_dir`) → replace with `Path.cwd() / "backlog"`.
- **Optional `CORTEX_REPO_ROOT` env var override** — for advanced users who want to invoke cortex from a non-CWD location, the env var (when set) supersedes `Path.cwd()`. When unset (default), CWD is used.
- **Sanity check** — when CWD doesn't contain a recognizable cortex project (no `lifecycle/`, no `backlog/`, no `cortex.toml` or similar), surface a clear error: "cortex: no cortex project detected at <CWD>. Run from your project root, set CORTEX_REPO_ROOT, or run `cortex init` to scaffold a new project here." (Spec phase finalizes the precise check.)

### Q4. Existing maintainer migration — DEFERRED to Spec with default

Default: documented runbook at `docs/migration-no-clone-install.md` (`uv tool uninstall cortex-command && uv tool install git+<url>@<tag>`). Auto-install path uses `uv tool install --reinstall git+<url>@<tag>` unconditionally, handling the existing-install case implicitly. No `cortex migrate` subcommand needed for current user count (effectively 1 maintainer). Spec confirms this is sufficient.

### Q5. Plugin/CLI version coupling — RESOLVED: plugin embeds CLI tag

User confirmed plugin embeds CLI git tag in auto-install URL. Specifically:
- Plugin's source contains a hardcoded URL like `git+https://github.com/charleshall888/cortex-command.git@<TAG>`.
- The TAG is bumped whenever the plugin is updated; it tracks the plugin's `MCP_REQUIRED_CLI_VERSION`.
- When the plugin auto-updates (Claude Code plugin manager pulls the new SHA from the marketplace), the embedded URL points at the new CLI tag → MCP's auto-install detects schema mismatch on next tool call → re-runs `uv tool install --reinstall git+<url>@<new-tag>` → CLI is now at the matching version.
- Users with plugin auto-update **disabled**: stale plugin → embeds old CLI tag → CLI stays at matching old version → no schema mismatch → works fine. They explicitly opted out of updates; that's their choice.
- Manual override escape hatch: `uv tool install --reinstall git+<url>@<other-ref>` works at the CLI level; user accepts schema-mismatch risk.

User's key insight: *"Most changes to the plugin or to the CLI shouldn't cause issues if the CLI and plugin are not in sync... but occasionally changes to the CLI or MCP may be breaking to the other and it is very important they are in sync for those times."* The tag-coupling design is precisely calibrated for this — auto-update users are protected; opt-outs accept the trade-off.

### Q6. PATH probe for `uv` at MCP start — DEFERRED to Spec with default

Default: yes, MCP server probes `shutil.which("uv")` on startup; on miss, emits structured stderr error pointing at the macOS GUI-app + Homebrew + `~/.zshenv` fix path. Cheap; failure is otherwise opaque. Spec includes this in the MCP server changes scope.

### Q7. Sandbox-write asymmetry — DEFERRED to Spec with default

Default: document as accepted regression in spec security section (overlaps with Q1's auto-RCE acceptance). MCP-spawned `uv tool install` writes to `~/.local/share/uv/tools/cortex-command/`, `~/.local/bin/cortex`, `~/.cache/uv/`, `~/.local/state/cortex-command/` without permission prompts. Bash tool path would prompt; MCP path doesn't. This is consistent with how MCP servers operate by design. No mitigation required beyond documentation.

### Q8. Test design depth — DEFERRED to Spec with default

Default test matrix:
- **Required for merge**: (i) Wheel-install + `importlib.resources` smoke test; (ii) `cortex --print-root` post-install probe (stronger than `cortex --help` per Adversarial #11); (iii) Tag-based release pipeline smoke test (build wheel from tag, install, run dry-run).
- **Slow-tier opt-in**: (iv) Concurrent two-session first-install via `multiprocessing`; (v) Half-failed install via `subprocess.run` fault injection (sentinel-file-on-failure semantics from Adversarial #8).

Spec confirms the merge gate set.

### Q9. Bootstrap installer (118) treatment — DEFERRED to Spec with default

Default: keep `install.sh` as a fallback for users without `uv` installed. Single purpose: install `uv` if absent, then `uv tool install git+<url>@<tag>`. Drop the clone-and-editable-install body. Lead documentation with `uv tool install git+<url>@<tag>` as the primary path; document the `curl | sh` fallback secondarily for users who don't yet have `uv`.
