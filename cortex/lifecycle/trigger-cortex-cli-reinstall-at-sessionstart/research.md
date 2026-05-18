# Research: Trigger cortex CLI reinstall at SessionStart on CLI_PIN drift

Clarified intent (from Clarify): add a SessionStart hook that closes the Bash-tool CLI-version-sync gap by probing `cortex --print-root` against the embedded `CLI_PIN[0]` and triggering `uv tool install --reinstall` synchronously on drift — honoring dev-mode skip predicates and defaulting to `exit 0` on probe failure so the hook can never brick Claude Code launch.

> **Note for Spec**: research surfaced two structural premise failures that the ticket body did not anticipate. The recommended approach diverges materially from the ticket's "Proposed direction." Both options remain on the table and must be resolved in the §2a confidence check / §4 user-approval surface in Spec. See `## Open Questions`.

## Codebase Analysis

### Files that will change

**New files (created):**
- `hooks/cortex-cli-version-sync.sh` (canonical source at top-level; mirrored into `plugins/cortex-overnight/hooks/` by `just build-plugin`, justfile:626–672). Goes into cortex-overnight because `CLI_PIN` lives there and `_ensure_cortex_installed` (the logic precedent) lives there. Bash trampoline + Python subprocess matches the inline-batch pattern at `cortex-scan-lifecycle.sh:252-264`.
- `tests/test_cli_version_sync_hook.py` (or `.sh`) — behavior + parity tests modeled on `tests/test_install_guard_parity.py` and `tests/test_hooks.sh`.
- **Likely** `plugins/cortex-overnight/cli_pin.py` — a side-effect-free sibling that holds `CLI_PIN`, so the hook can read it without paying `server.py`'s import cost (see Adversarial #3).

**Modified files:**
- `plugins/cortex-overnight/hooks/hooks.json:3-12` — append a second hook entry to the existing `SessionStart` array (currently only `cortex-scan-lifecycle.sh`).
- `plugins/cortex-overnight/server.py` — if `cli_pin.py` is introduced, `server.py:106` switches from inline tuple to `from cli_pin import CLI_PIN` re-export. If the hook ends up calling reinstall logic (Alt A), `_ensure_cortex_installed` (775–970), `_run_install_and_verify` (580–772), `_resolve_installed_cortex_path` (537–577), and `_evaluate_skip_predicates` (1195–1249) get refactored so a third caller can use them.
- `cortex_command/install_guard.py` and `plugins/cortex-overnight/install_guard.py` — byte-identical-vendoring may need extension if the hook needs the in-flight guard (only if the hook executes reinstall, not if it's detect-only).
- `justfile:626-672` — `build-plugin` HOOKS array for cortex-overnight (line 655) needs the new hook name; if a new vendor mirror is introduced, a new `sync-*` recipe pattern (precedent at justfile:677-751).
- `.githooks/pre-commit:227-252` — if new byte-identical vendor introduced, add a Phase-1.95 trigger block.
- `docs/internals/auto-update.md:17, 37-39, 47, 101` — Bash-tool carve-out section needs update: closes the gap (or surfaces it via `additionalContext`) per the chosen mechanism. Add new hook row to component map.
- `bin/cortex-rewrite-cli-pin:47, 64-91` — `DEFAULT_TARGET` may change to `cli_pin.py`; the single-declaration regex needs verification against the new location.
- `cortex/backlog/235-...` — status update via cortex-update-item on lifecycle entry.

### Relevant existing patterns

**(1) SessionStart hook contract** (from `plugins/cortex-overnight/hooks/cortex-scan-lifecycle.sh`):
- Bash, `set -euo pipefail`; reads JSON stdin via `INPUT=$(cat)`, parses `session_id` / `cwd` via `jq` (lines 5–13).
- Registered in `hooks.json` under `SessionStart` with `{type: "command", command: "${CLAUDE_PLUGIN_ROOT}/hooks/cortex-scan-lifecycle.sh"}`.
- Always exits 0 on every observed path including no-op (lines 29, 316, 476). The new hook MUST follow this defensive convention.
- Output contract: `jq -n --arg ctx "$context" '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $ctx}}'` (lines 465–474).
- GUI-launched Claude Code PATH bootstrap precedent at `claude/hooks/cortex-worktree-create.sh:18`: `~/.local/bin:~/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:$PATH`.

**(2) Probe + reinstall logic** (`_ensure_cortex_installed`, `plugins/cortex-overnight/server.py:775–970`):
- Carve-out: `CORTEX_AUTO_INSTALL=0` → return (line 821–827).
- Recent-failure sentinel: `_recent_install_failed_sentinel()` (lines 341–370, 60s window).
- Probe: `subprocess.run(["cortex", "--print-root", "--format", "json"], timeout=10s, capture_output=True, text=True)` (lines 859–865). On error → silent return.
- Version compare: `Version(payload["version"])` vs `Version(CLI_PIN[0].lstrip("v"))` (lines 884, 895–896). NB: current uses `!=` — see Adversarial #4 for the downgrade hazard.
- In-flight guard: `from install_guard import check_in_flight_install_core` (line 924), called with `_plugin_active_session_path()` + `_plugin_pid_verifier` (945–948); honors `CORTEX_ALLOW_INSTALL_DURING_RUN=1` (line 944).
- Reinstall: `_run_install_and_verify(stage=...)` (line 970), wraps `uv tool install --reinstall git+...@CLI_PIN[0]` (300s timeout, lines 625–639); verification via `<abs> --print-root --format json` (10s timeout, lines 705–710).
- Flock at `${XDG_STATE_HOME}/cortex-command/install.lock` with 60s wait budget (lines 286, 396–429). Non-blocking poll via `fcntl.flock(fd, LOCK_EX | LOCK_NB)`.
- NDJSON audit: `_NDJSON_ERROR_STAGES` allowlist (lines 1095–1108), `_append_error_ndjson` (lines 1126–1180). New stages would be `session_start_sync` and `session_start_sync_parse_failure`.

**(3) Skip predicates** (`_evaluate_skip_predicates`, server.py:1195–1249):
- (a) `os.environ.get("CORTEX_DEV_MODE") == "1"` → return reason (free).
- (b) `git -C <root> status --porcelain` non-empty → `"dirty_tree"` (~10–30ms).
- (c) `git -C <root> rev-parse --abbrev-ref HEAD != "main"` → `"non_main_branch"` (~10–30ms).
- `git_status_failed:<cls>` / `git_branch_failed:<cls>` are themselves skip reasons (failure-conservative).
- `cortex_root` resolved from `cortex --print-root` payload's `root` field; under wheel install with no `.git/` at `root`, server.py:1294 explicitly skips throttle path.

**(4) Byte-identical vendoring** (`cortex_command/install_guard.py:149-248` ↔ `plugins/cortex-overnight/install_guard.py`):
- `# BEGIN sync-install-guard:check_in_flight_install_core` / `# END sync-install-guard:check_in_flight_install_core` markers.
- Mirror file fully generated by `just sync-install-guard` (justfile:677–751): fixed `HEADER` + marker-extracted body. `--check` exits non-zero on drift.
- Pre-commit (`.githooks/pre-commit:227-252`) Phase 1.95 triggers `just sync-install-guard --check` when staged paths touch the relevant files.
- Parity test (`tests/test_install_guard_parity.py`):
  - Source-identity via `inspect.getsource(...)` byte-equality (lines 102–116).
  - Core-level decision parity across 8 scenarios (420–505).
  - Wrapper-level parity across 4 env carve-outs (512–643).

**(5) Schema-floor stderr surface** (`_schema_floor_violated`, server.py:1827–1870):
- Returns `True` when CLI `schema_version` major < `MCP_REQUIRED_CLI_VERSION` major.
- Under wheel install only (gated at server.py:1294 via `(Path(str(cortex_root)) / ".git").is_dir()`), emits to stderr:
  ```
  Schema-floor violation: installed CLI schema_version={cli_version}, required={CLI_PIN[1]}; run 'uv tool install --reinstall git+https://github.com/charleshall888/cortex-command.git@{CLI_PIN[0]}' to upgrade
  ```
- Returns `False` after emit so caller skips orchestration. Triggered by `_run_per_call_gates` (1997–2031) before R8 throttle. Bypasses skip-predicates.

**(6) CLI_PIN discovery from a hook** — current state: `CLI_PIN` declared exactly once at `plugins/cortex-overnight/server.py:106`. `bin/cortex-rewrite-cli-pin:64-91` rejects 0 or ≥2 declarations.
- **Adversarial blocker**: `from server import CLI_PIN` does NOT work from a SessionStart hook. `server.py:84` calls `_enforce_plugin_root()` at module-top-level which `sys.exit(1)` if `CLAUDE_PLUGIN_ROOT` is unset, and `server.py` imports `mcp.server.fastmcp` and `pydantic` at top level which are PEP 723 deps not available to a bare `python3 -c "..."` invocation.
- **Workable options**: (i) factor `CLI_PIN` into side-effect-free `plugins/cortex-overnight/cli_pin.py`; `server.py` re-exports. Hook reads `cli_pin.py` directly via stdlib regex or `importlib`. (ii) regex-parse `server.py` for the `CLI_PIN = (...)` declaration (fragile to refactoring). (iii) expose a console script (e.g., `cortex-overnight --emit-pin`) — adds an inter-process hop on every session.
- Recommended: (i). Preserves single-declaration invariant; trivial to keep `bin/cortex-rewrite-cli-pin` working; side-effect-free import.

**(7) `cortex --print-root` envelope** (`cortex_command/cli.py:181–259`):
- Emits `{"version": "<pkg>", "schema_version": "2.0", "root": "<abs>", "package_root": "<abs>", "remote_url": "...", "head_sha": "..."}`.
- `version` from `importlib.metadata.version("cortex-command")` (fallback `"0.0.0+source"`).
- Exits 2 only on `CortexProjectRootError` (lines 224–227) → hook should treat `exit_code == 2` as "not a cortex repo, return 0 silently."
- These six fields are forever-public-API per `docs/internals/mcp-contract.md:22-28`.

### Integration points and dependencies

- **Hook stdin**: `{hook_event_name, session_id, transcript_path, cwd, source, model, permission_mode, agent_type?}`. Hook needs `cwd` to gate "is this a cortex repo" before paying probe cost (precedent: `cortex-scan-lifecycle.sh:15-37`).
- **Hook output**: emit `hookSpecificOutput.additionalContext` for any user-visible message; on no-op, emit nothing. `additionalContext` is injected into Claude's first turn — meaning Claude (not the user directly) sees the drift report and can route accordingly.
- **Hook stdin/stdout limitations**: stdout from a SessionStart hook is parsed by Claude Code as JSON output contract, NOT streamed to user UI during execution. There is no progress channel visible to the user while the hook runs — the launcher appears frozen for the duration. This is the load-bearing structural finding that contradicts the ticket's "single user-facing status line" design constraint (see Adversarial #1).
- **In-flight guard reuse**: only applicable if the hook executes reinstall. If the hook is detect-only, the in-flight guard does not need a third caller.
- **Sentinel + log paths**: `${XDG_STATE_HOME}/cortex-command/install-failed.<ts>` (60s de-spam window). `${XDG_STATE_HOME}/cortex-command/last-error.log` for NDJSON audit.
- **`bin/cortex-rewrite-cli-pin`**: regex constraint at line 64-91 enforces single declaration in target file. Adapt to new location if `cli_pin.py` is introduced.

### Conventions to follow

- **Top-level source + plugin mirror**: hooks for build-output plugins live at top-level `hooks/cortex-*.sh` or `claude/hooks/cortex-*.sh`, mirrored into `plugins/<p>/hooks/` by `just build-plugin`. Edit the top-level source only.
- **Defensive `exit 0` in hooks**: precedent at `hooks/cortex-cleanup-session.sh:24,36` and `hooks/cortex-scan-lifecycle.sh:29,316,476`. Reinforced by ticket's design constraint.
- **Stage-string allowlist** (`_NDJSON_ERROR_STAGES`, server.py:1095-1108): new stages must register or get renamed to `"unknown"` with stderr complaint.
- **PEP 723 single-file scripts** are the convention for plugin-owned executable Python needing third-party deps (`plugins/cortex-overnight/server.py:1-9`). Pure-stdlib hooks should declare so explicitly.
- **No `check=True` on subprocess** (documented at server.py:1316-1322): always `capture_output=True, text=True, timeout=N`, branch on `returncode`.
- **Soft positive routing** (CLAUDE.md MUST-escalation policy): factual phrasing in user-visible text, not imperatives.
- **Plugin home**: cortex-overnight is the natural location — CLI_PIN, `_ensure_cortex_installed`, `install_guard.py` all live there. cortex-core does not currently know about CLI_PIN.

## Web Research

### Critical finding: the load-bearing premise is fragile

The ticket asserts (Proposed direction): "the marketplace fast-forward completes before SessionStart fires, so the hook sees the post-update `CLI_PIN`." Three primary sources contradict this as a stable guarantee:

- **anthropics/claude-code#19491** — "SessionStart hooks run before plugins are fully loaded": SessionStart observed firing ~40s *before* plugin hook registration completed in v2.1.12. Marked closed/duplicate, but the race was real in a shipped version.
- **anthropics/claude-code#52218** — `autoUpdate` hot-loads newer skills/commands into the running process but **leaves `installed_plugins.json` untouched**, pinning bundled hooks to the last-explicitly-installed version. Bundled hook updates require a manual `/plugin` → "Update now" or two full relaunches. This means the hook's *own code* may be from the prior plugin version when it runs.
- **anthropics/claude-code#26744** — Third-party marketplace plugins stopped auto-pulling on session start in some versions.

**Implication**: the design cannot bet on ordering. It must detect-and-correct on whatever state it sees, accept that some marketplace races will leave it reading the prior `CLI_PIN`, and frame the value as "compensates for whatever the marketplace did or didn't do" rather than "runs after marketplace fast-forward."

### SessionStart hook contract (Claude Code official docs, `code.claude.com/docs/en/hooks`)

- **stdin payload**: `{session_id, transcript_path, cwd, hook_event_name: "SessionStart", source: "startup"|"resume"|"clear"|"compact", model, permission_mode, agent_type?}`.
- **Exit codes**:
  - `0` = success (stdout parsed as JSON or added as context).
  - `2` = **non-blocking error** — stderr shown to user but session continues.
  - Other = non-blocking error, stderr shown only with `--verbose`.
  - **SessionStart cannot block startup via exit code.** Only `{"continue": false, "stopReason": "..."}` in JSON output halts — and that stops Claude entirely after the hook completes (heavy hammer).
- **JSON output contract**: `{continue, stopReason, suppressOutput, systemMessage, terminalSequence, hookSpecificOutput: {hookEventName, additionalContext}}`.
- **Default timeout**: 600 seconds (10 min); configurable via `timeout` field. Timeout is non-blocking — exceeded hooks are cancelled but session proceeds.
- **`CLAUDE_ENV_FILE` env var** allows persisting environment variables into subsequent Bash tool calls — relevant for refreshing PATH after a binary relocation.
- **Explicit Anthropic warning**: "SessionStart runs on every session, so keep these hooks fast to avoid slowing down startup."

### uv tool install semantics

- **Tag-cache footgun**: uv caches tag→commit mapping at the resolution layer; force-pushed tags need `--refresh` (https://docs.astral.sh/uv/concepts/cache/). The existing `_ensure_cortex_installed` invokes `uv tool install --reinstall git+...@v2.1.0` **without `--refresh`**, so under a warm cache a "reinstall" of a force-pushed tag pulls the prior SHA. The post-install verification probe reads the package `__version__` which was also bumped in the force-push — so the cached wheel still reports the right version and verification passes. **The current `_run_install_and_verify` has a latent stale-wheel bug** that this hook would inherit. (Issues astral-sh/uv#16196, #17261 document the cache invalidation gap.)
- **Recommended pattern for git-tagged tools**: `uv tool install --from git+URL@tag --force --reinstall --refresh <package-name>`.
- **Latency**: warm wheel reinstall is typically sub-second; cold path (full git fetch + wheel build + install) is multi-second. No official benchmark.

### Prior art for "tool-launch + version-check + auto-update" patterns

- **Homebrew autoupdate** (Homebrew/brew#6382, #7030): canonical synchronous-update-before-install UX pain. The community `homebrew-autoupdate` tap moves update to a background daemon precisely because blocking sync update at every action is a known UX antipattern. Standard pattern: 60s freshness budget (`HOMEBREW_AUTO_UPDATE_SECS`), accept eventual consistency, push slow work to background.
- **VS Code extensions**: auto-update runs **async after editor open**. Never blocks editor from opening. Drift surfaced via `[Unsupported]` title-bar tag — passive, not blocking. (`code.visualstudio.com/docs/supporting/faq`)
- **asdf**: shims are the cheap synchronous layer; version resolution + install happen lazily at tool invocation, not at shell start. (`asdf-vm.com/manage/core.html`)

### Hook reliability anti-patterns

- **pyenv shell-init**: `eval "$(pyenv init -)"` raises shell startup from 11.2ms → 111.7ms with **no** network call (pyenv/pyenv#2918). With network, the tax compounds badly. Lazy loading is the universally recommended fix; ~70% startup-time improvements are reported.
- **Claude-Code-specific failures**: 20s latency from misconfigured hooks documented (ruvnet/ruflo#1530). Anthropic docs explicitly call out "anything over 100ms adds noticeable latency."
- **The synchronous-network-call-at-launch anti-pattern is unanimously avoided in the broader shell-init community.**

### Patterns the design should consider

1. **Cheap local probe first; only do expensive work on drift detection** — the ticket's design has this.
2. **Freshness budget** — Homebrew's `AUTO_UPDATE_SECS=60s` floor. Even on drift detection, don't reinstall more than once per N-minute window via a sentinel file.
3. **Warn-and-continue by default**; block only on hard incompatibility (schema-floor violation). `continue: false` is for the unrecoverable case, not the recoverable-with-noise case.
4. **Use `additionalContext` to inform Claude that drift exists**; let Claude route Bash failures accordingly.
5. **Detect-and-correct, don't bet on ordering** — frame the hook as resilience, not lockstep enforcement.

### Key URLs

- SessionStart contract: https://code.claude.com/docs/en/hooks
- autoUpdate ordering + `installed_plugins.json` gap: https://github.com/anthropics/claude-code/issues/52218
- SessionStart-before-plugin-loading race: https://github.com/anthropics/claude-code/issues/19491
- Third-party marketplace autoUpdate gaps: https://github.com/anthropics/claude-code/issues/26744
- uv cache concepts (commit-hash keyed, `--refresh` escape hatch): https://docs.astral.sh/uv/concepts/cache/
- uv `--from` cache invalidation gap: https://github.com/astral-sh/uv/issues/16196
- Homebrew sync-update-before-install UX tradeoff: https://github.com/Homebrew/brew/issues/6382, https://github.com/Homebrew/brew/issues/7030
- pyenv shell-init cost anti-pattern: https://github.com/pyenv/pyenv/issues/2918

## Requirements & Constraints

### Aligned project.md Quality Attributes

- **Graceful partial failure** (line 38): the `exit 0`-on-probe-error design is the SessionStart-layer expression of this attribute.
- **Defense-in-depth for permissions** (line 41): hook runs at session-launch time — interacts with the sandbox/allow surface for `uv tool install` shell-outs.
- **Maintainability through simplicity** (line 39): argues against introducing a third byte-identical mirror unless it's the cleanest shape.
- **Destructive operations preserve uncommitted state** (line 42): maps directly onto the dirty-tree skip predicate.

### Philosophy of Work

- **Complexity** (line 19): "Must earn its place by solving a real problem now. When in doubt, simpler wins."
- **Solution horizon** (line 21): the ticket is the durable version of #145's wontfix — a different mechanism that didn't violate the plugin-imports-zero-cortex-modules contract (which #145's inline-CLI-gate would have). So this is not a stop-gap.

### ADR-0002 — CLI/plugin coupling contract

`plugins/cortex-overnight/server.py`'s `CLI_PIN` tuple `(<tag>, <schema_major.minor>)` and the `cortex --print-root --format json` envelope's `version` + `schema_version` fields. CLI/plugin evolve at independent cadences. The hook operates within this contract — it doesn't change the contract, it just adds a third callsite of the version-comparison logic.

### plugin-imports-zero-cortex-modules contract — precise terms

`docs/internals/mcp-contract.md:3`: "The MCP plugin imports zero `cortex_command.*` modules; its sole interface to the CLI is `subprocess.run(["cortex", ...])` plus parsing the versioned JSON the CLI emits on stdout."

`docs/internals/auto-update.md:33`: "The MCP server owns this layer end-to-end and does not import the cortex Python package — its sole interface to the CLI is the subprocess + JSON contract."

**The contract is plugin-scoped, not hook-scoped.** It governs `plugins/cortex-overnight/` ↔ `cortex_command/`. A SessionStart hook is a third entity. Where the hook lives (cortex-overnight, cortex-core, ~/.claude/hooks/) determines whether the contract applies. Within cortex-overnight, the hook is part of the plugin and inherits the contract: it MAY NOT import from `cortex_command.*`, but it MAY use `subprocess.run(["cortex", ...])` and MAY share code with the plugin via byte-identical vendoring (the existing precedent).

### ADR-0001 / ADR-0003 — file-based state, per-repo sandbox

`cortex init` registers the per-repo `cortex/` umbrella in `~/.claude/settings.local.json`'s `sandbox.filesystem.allowWrite`. Any new state path the hook writes (e.g., `${XDG_STATE_HOME}/cortex-command/last-version-check.<ts>`) must compose with this file-based posture and respect existing sandbox carve-outs.

### #145 wontfix context

#145's spec did propose a SessionStart hook (lines 47–66) but was closed wontfix because the *premise* — "users invoke `cortex` from a bare shell" — was rejected (users invoke via MCP, not bare shell). #145 was *not* rejected because SessionStart was the wrong hook point. The new topic differs in target: it closes drift against `CLI_PIN[0]` (Layer-2 gap), not upstream-of-main drift.

`docs/internals/auto-update.md:37-39` documents the Bash-tool gap as "wontfix per #145" because routing every CLI subprocess through MCP would require either Claude-Code-side instrumentation or a CLI-side phone-home — both violate plugin-imports-zero-cortex-modules. The new SessionStart hook is a *different* mechanism that does not route subprocess calls and does not violate the contract. It legitimately reopens the wontfix.

### #212 / #213 hygiene

#213's auto-release workflow rewrites `CLI_PIN[0]` automatically on every release, and `release.yml:28` CI lint hard-fails on drift between `CLI_PIN[0]` and the pushed tag. **The hook can trust `CLI_PIN[0]` as authoritative**; drift between pin and pushed tag is prevented upstream.

### `cortex --print-root` forever-public-API

Per `docs/internals/mcp-contract.md:22-28`, the six fields (`version`, `schema_version`, `root`, `package_root`, `remote_url`, `head_sha`) are stable forever. The hook can depend on this envelope shape.

## Tradeoffs & Alternatives

**Alternative A — SessionStart hook in `cortex-overnight` plugin that executes reinstall on drift** (ticket's proposed direction)

Bash trampoline at `plugins/cortex-overnight/hooks/cortex-cli-version-sync.sh`, invokes a Python script that reads `CLI_PIN[0]` from a side-effect-free `cli_pin.py` sibling, probes `cortex --print-root --format json`, and on drift calls into a factored `_check_version_drift()` helper to acquire flock + reinstall + verify.

- **Implementation complexity**: medium. Bash trampoline ~30 lines; Python script ~100 lines; refactor of server.py to extract a factored helper that's importable from a bare Python interpreter (no third-party deps).
- **Maintainability**: medium. Either a new third byte-identical mirror, or factor `_check_version_drift()` into a stdlib-only module that the hook can import without resolving the PEP 723 venv. The latter establishes a new internal API surface in cortex-overnight.
- **Performance** (no-op path): claimed ~50ms; **realistically 200ms–2s** given bash → Python cold start (~30–80ms per cortex-scan-lifecycle.sh:251 comment) + `cortex --print-root` cold-start + 2× git subprocess (each ~10–30ms) + cold-disk variance. With a freshness throttle (`${XDG_STATE_HOME}/cortex-command/last-version-check.<ts>` mtime + 300s budget), the typical no-op path drops to a single `stat(2)` (~10µs).
- **Performance** (drift path): 30s+ for full git fetch + wheel build + install. User sees frozen launcher with no UI feedback (see Adversarial #1 — SessionStart has no streaming output channel during hook execution).
- **Alignment**: strong (CLI_PIN, `_ensure_cortex_installed`, vendored `install_guard.py` all live in cortex-overnight). The hook is a third caller of existing patterns.

**Alternative B — SessionStart hook in `cortex-core` plugin** (cross-plugin coupling)

Cortex-core hook reads `CLI_PIN[0]` from cortex-overnight's `cli_pin.py` (cross-plugin file read), or cortex-overnight emits a JSON sidecar that cortex-core reads.

- **Implementation complexity**: medium-high (cross-plugin lookup with defensive fallback when cortex-overnight is absent).
- **Maintainability**: poor. Violates the spirit of plugin-imports-zero-cortex-modules at the plugin-↔-plugin layer. Adds a new dual-source enforcement surface.
- **Performance**: identical to A.
- **Alignment**: weak. Cortex-core hooks today are workspace-operations focused; CLI version sync is not its domain.
- **Possible reason to prefer B**: users who install cortex-core without cortex-overnight. But that configuration has no Layer-2 protection today (only cortex-overnight's MCP server runs `_ensure_cortex_installed`), so there's no real population to serve.

**Alternative C — `cortex --self-check` CLI verb invoked from a thin hook**

Plugin hook shells out to `cortex --self-check --expected-version vX.Y.Z`. CLI does the compare.

- **Implementation complexity**: medium. Adds a CLI verb; needs CLI_PIN to still live in the plugin and be passed via argv.
- **Maintainability**: poor. Chicken-and-egg on first-install (`cortex --self-check` doesn't exist if cortex isn't installed); inverts the layering (`docs/internals/auto-update.md:33` keeps the CLI dumb deliberately).
- **Alignment**: weak. The schema-floor pattern at server.py:1827 keeps version-comparison on the plugin side intentionally.

**Alternative D — Per-invocation preflight in `cortex_command/__init__.py` or wrapper script**

Run the check at module import-time or via a wrapper that replaces `cortex` on PATH.

- **Implementation complexity**: high (modifying `cortex_command/__init__.py` or shimming the console script).
- **Maintainability**: poor. **Explicitly contradicts** the architectural decision at `cortex_command/install_guard.py:6-16` ("removes the need for blanket import-time carve-outs").
- **Performance**: bad. Pays probe cost on every cortex invocation, not once per session. Compounds across statusline, hooks, bin scripts, skills.
- **Alignment**: weak.

**Alternative E — Sidestep with stricter per-entry-point diagnostics** (embrace the documented wontfix)

Make every cortex CLI entry point catch ImportError / no-such-command on version-mismatched calls and emit a one-line remediation. No hook; no SessionStart involvement.

- **Implementation complexity**: low. Per-entry-point catch + format.
- **Maintainability**: good. No new architectural surface.
- **Performance**: best. Zero per-session overhead.
- **Alignment**: strong. The documented `#145`-wontfix-plus-`implement.md §1a`-preflight pattern — fail-fast diagnostic over upstream prevention.
- **Cost**: user still hits the failure first; the diagnostic only helps if they read it. Schema-bumped JSON envelopes parsed outside MCP could still hit `KeyError` / `ValueError` before the diagnostic fires.

**Alternative F — SessionStart hook in `cortex-overnight` that *only detects drift and warns via `additionalContext`*** (Adversarial recommended restructure)

Same trampoline + Python as Alt A, but **does not execute reinstall**. On drift detection, emits `hookSpecificOutput.additionalContext` to inform Claude: "CLI is drifted (installed: X, expected: Y). Run `uv tool install --reinstall git+...@Y --refresh` to sync; Bash `cortex …` calls may fail until then." The reinstall pathway stays MCP-tool-call-gated via existing `_ensure_cortex_installed`.

- **Implementation complexity**: low. Bash trampoline + small Python (probe + version-compare + JSON emit). No reinstall logic, no flock, no in-flight guard, no NDJSON staging — all of those stay in `_ensure_cortex_installed`.
- **Maintainability**: best. No new vendoring; no `_ensure_cortex_installed` refactor; no in-flight-guard third caller. The hook is a thin information producer.
- **Performance** (no-op path): ~150–500ms cold without throttle; ~10µs with `stat(2)` freshness throttle.
- **Performance** (drift path): same as no-op (the hook only emits text). No 30s freeze.
- **Alignment**: strong. Mirrors VS Code's `[Unsupported]` tag pattern (passive surface, not blocking action). Honors the SessionStart-as-information-channel design (Anthropic's docs warn "keep these hooks fast"). Closes the *visibility* gap (Claude knows drift exists at session start and can route accordingly) without closing the *execution* gap.
- **Cost**: doesn't fully eliminate the user-visible failure path. Subsequent Bash `cortex` call still fails on drift; the hook's `additionalContext` ensures Claude has the breadcrumb to give a good remediation. Schema-bumped envelopes parsed outside MCP still hit raw `KeyError`.

**Recommended approach: F + E**

Ship Alternative F (SessionStart drift-detector that emits `additionalContext`) as the primary mechanism. Adopt Alternative E's diagnostic-quality improvements as belt-and-suspenders for the surfaces F doesn't cover (schema-bumped envelopes, ImportError in bin scripts).

Rationale:
1. **The "block on reinstall" design constraint is structurally infeasible at SessionStart** (Adversarial #1). There is no streaming UI channel during SessionStart hook execution. A 30s `uv tool install` blocks the launcher with no progress visible. The single-line user-facing status the ticket asks for cannot exist as designed.
2. **The probe-cost budget is ~10× optimistic** without a freshness throttle (Adversarial #2). A drift-detector with a 300s freshness sentinel typically pays `stat(2)` cost.
3. **The marketplace-fast-forward-before-SessionStart premise is fragile** (multiple shipped CC versions have observed the opposite race). Detect-and-correct is right; reinstall-on-drift bets on the ordering.
4. **The `from server import CLI_PIN` approach is broken at import** (Adversarial #3). `cli_pin.py` sibling is the durable fix and is independently desirable.
5. **The existing `_ensure_cortex_installed` already covers MCP-tool-call drift fixing.** F closes the *visibility* gap so the user/Claude knows drift exists at session start; the existing path closes the *execution* gap on the next MCP tool call. Bash-routed `cortex` calls between SessionStart and the next MCP call still benefit from the `additionalContext` warning, even though they won't have been auto-reinstalled.
6. **F is much smaller**: no new flock callers, no NDJSON allowlist additions, no in-flight-guard mirror extension, no PATH refresh edge cases, no force-pushed-tag cache hazard, no concurrent-session 60s flock hangs.

The ticket's stated value — "close the gap" — is partially preserved by F: Bash failures still happen, but they're explained (Claude has the breadcrumb to give a good remediation). The remaining residual is the 0-to-N Bash failures before the next MCP tool call refreshes the install, which can be mitigated by adding the same drift-check to `bin/cortex-cleanup-session` or any other interactive entry point (out of scope here).

**Note on the user's stated preference**: the ticket recommends "block." That preference was reasoned without knowledge of (a) SessionStart's no-streaming-UI constraint, (b) the `from server import CLI_PIN` import-side-effect problem, and (c) the 50ms→1s+ probe-cost gap. The Spec phase needs to surface this to the user and re-decide.

## Open Questions

The following items are unresolved by research and must be settled in the Spec phase. The decisions here are consequential — they change which alternative is chosen and what gets built.

1. **Detect-and-warn (F) vs detect-and-reinstall (A)** — this is the central scope decision. F is the research-recommended approach; A is the ticket's stated proposal. **Deferred to Spec**: this overturns the ticket body's stated preference ("Recommendation: block") based on three research findings the ticket did not anticipate (no streaming UI channel at SessionStart, `from server import CLI_PIN` is broken at import, 50ms→200ms+ probe cost). The user must re-decide A vs F in the Spec interview. The choice determines:
   - Whether the hook executes `uv tool install --reinstall` (A) or only emits `additionalContext` (F).
   - Whether new NDJSON stages, flock contention handling, in-flight-guard interactions, PATH-refresh handling, and downgrade-prevention logic are in scope (A) or out of scope (F).
   - Whether the design needs the `--refresh` flag on `uv tool install` (A — this is also a latent bug in `_ensure_cortex_installed`) or not (F).
   - Whether the "single-line user-facing status line" design constraint is feasible (it is not at SessionStart in either case — A would show a frozen launcher; F doesn't try to show progress).

2. **`CLI_PIN` location** — keep declaration inline at `server.py:106` and have the hook regex-parse the source (fragile), or extract to a side-effect-free `plugins/cortex-overnight/cli_pin.py` sibling that `server.py` re-exports (durable but a small refactor). The adversarial review identified `from server import CLI_PIN` as broken-at-import; one of these two paths is required regardless of A/F choice. Recommended: extract to `cli_pin.py`.

3. **Freshness throttle scope** — Homebrew uses 60s; the design could use 300s, 24h, or no throttle. Throttle scope affects how often the probe runs across rapid session restarts (common in IDE re-attach, tmux split). Recommended: 300s sentinel at `${XDG_STATE_HOME}/cortex-command/last-version-check` (mtime-based).

4. **Schema-floor parity gate** — should the hook mirror `_schema_floor_violated`'s wheel-install-only gate (`.git/` dir presence), or fire under all installs? Different gating creates inconsistent UX between session-start and MCP-call. Recommended: mirror the wheel-only gate.

5. **Downgrade prevention** — current `_ensure_cortex_installed` uses `!=` comparison; under the marketplace-race scenarios documented in #19491/#52218, an old plugin version's hook could "fix" the CLI install to its (older) `CLI_PIN[0]`, downgrading. Resolved in A only. Recommended: change to `<` for the hook (and arguably for `_ensure_cortex_installed` itself, separate ticket).

6. **`uv tool install --refresh` flag** — addresses force-pushed-tag stale-cache hazard documented in `astral-sh/uv` cache concepts. Currently missing from `_ensure_cortex_installed`. Resolved in A only. **Deferred to Spec**: pre-empted by Q1 (if F is chosen, this is out of scope; if A is chosen, the user must decide whether to bundle the existing-bug fix into #235's scope or file a separate ticket).

7. **PATH refresh on relocation** — if `uv` ever relocates the binary, the running session's PATH points at the deleted path. Resolved in A only. **Deferred to Spec**: pre-empted by Q1 (if F is chosen, this is out of scope; if A is chosen, the user must decide between "document as residual" and "include `CLAUDE_ENV_FILE` PATH injection").

8. **Concurrent-session flock contention** — multiple simultaneous SessionStart hooks. Resolved in A only. Recommended: non-blocking single-try flock acquisition; on contention, exit 0 with `flock_busy` skip (trust that another session is doing the work).

9. **Active-overnight-session interaction** — if the in-flight guard blocks reinstall, must surface via `additionalContext` so Claude knows Bash failures may follow. Resolved in A only.

10. **Bash trampoline test surface** — `tests/test_install_guard_parity.py` enforces function-level Python identity. Hooks are bash + Python subprocess. New test surface for the bash trampoline needed regardless of A/F. Recommended: behavior tests via `tests/test_hooks.sh` (precedent).

11. **`docs/internals/auto-update.md` update** — Bash-tool carve-out section's "wontfix per #145" language needs update. If F: "closed in part — drift is visible via SessionStart hook breadcrumb; execution gap remains intentional." If A: "closed per #235." Component map adds new hook row.

12. **`bin/cortex-rewrite-cli-pin` adaptation** — if `cli_pin.py` is introduced, `DEFAULT_TARGET` at line 47 changes. Regex constraints at lines 64-91 hold; just retarget.
