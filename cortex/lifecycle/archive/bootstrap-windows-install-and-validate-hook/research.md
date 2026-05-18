# Research: Bootstrap Windows install and validate hook execution

## Epic Reference

This ticket is one of four in epic [[215-add-native-windows-host-support-for-the-agentic-harness]] (Windows v1). Broader epic-level research at `cortex/research/windows-support/research.md` covers the full Windows port; this lifecycle scopes specifically to the install bootstrap and the hook empirical validation, not the platform-abstraction package (216), the scheduler port (217), or the posture surface (219).

## Headline Finding

The ticket's framing of `.sh` hooks as "wrappers around `cortex-*` Python entry points" is largely incorrect. Of the 9 cortex-shipped hooks under `hooks/` and `claude/hooks/`, only **one** (`cortex-scan-lifecycle.sh:424`) calls a `cortex-*` entry point, and only as a fire-and-forget side call. The other 8 hooks contain substantive bash logic (jq parsing, regex matching, JSON construction, file I/O) that would require a meaningful rewrite — not a deletion — to migrate to direct entry-point invocation.

Independently, the upstream surface (Claude Code's hook execution on native Windows) is **known-broken as of 2026-05-12** via active issue [anthropics/claude-code#21468](https://github.com/anthropics/claude-code/issues/21468). Two related issues filed today (2026-05-15, #59513 and #59496) confirm the hook subsystem is not stabilizing. The empirical W6 test on a Windows VM is likely to surface degraded behavior rather than a clean pass/fail, and any hook strategy that depends on hooks-fire-correctly on Windows is built on shifting ground.

The combined evidence collapses the ticket's framing. The implementable scope for this lifecycle is:

1. **Install path**: ship `install.ps1` as a sibling to `install.sh` with the same three-step structure, harden against five known uv-on-Windows gotchas, and add a Windows-troubleshooting subsection to `docs/setup.md`.
2. **Hook strategy**: keep canonical `.sh` hooks for Windows v1 (require Git for Windows; document hooks as best-effort on native Windows pending #21468 upstream resolution). Defer the cross-platform hook rewrite (Python or Node.js entry points) to a follow-on ticket whose scope is "rewrite cortex-shipped hooks as cross-platform entry points" — decoupled from the Windows port.
3. **Empirical W6 test**: run on a Windows VM **after** ticket 216 lands; gate is "hooks-don't-crash-Claude-Code and cortex CLI works without hooks," not "hooks-fire-successfully."

The implications for epic 215's "Ship 216 + 218 + 219 together as Windows v1" sequencing decision are surfaced under Open Questions — the bundling is incompatible with 218 having an empirical gate that may reveal upstream-broken behavior.

## Codebase Analysis

### `install.sh` (the macOS installer to mirror)

`install.sh` is 67 lines with three logical steps:

1. **Repo URL normalization** (lines 24-37): `normalize_repo_url()` accepts `git@github.com:owner/repo`, `ssh://...`, `https://...`, or plain `owner/repo`, normalizing to canonical `https://github.com/owner/repo.git`. Reads from `$CORTEX_REPO_URL`, defaults to `charleshall888/cortex-command`.
2. **Tag resolution** (lines 39-44): `resolve_latest_tag(url)` runs `git ls-remote --tags --refs <url>`, awk-extracts the tag name, filters to semver `^v[0-9]+\.[0-9]+\.[0-9]+$`, sorts with `sort -V`, takes the last (highest). Overridable via `$CORTEX_INSTALL_TAG`.
3. **uv installation and `uv tool install`** (lines 46-64): checks `command -v uv`; if missing, runs `install_uv()` which `curl -LsSf https://astral.sh/uv/install.sh | sh` into a `mktemp` file then runs it. Sets `UV_PYTHON_DOWNLOADS=automatic`. Runs `uv tool install git+"${resolved_url}"@"${tag}" --force`. Prints three-line next-steps message: "cortex CLI installed", "plugin auto-registration is not yet automated", "if 'cortex' is not on your PATH, run 'uv tool update-shell'".

Bash-isms requiring translation to PowerShell: `set -eu` → `$ErrorActionPreference = 'Stop'`; `mktemp` → `New-TemporaryFile`; `command -v` → `Get-Command -ErrorAction SilentlyContinue`; `grep -E` → `Select-String -Pattern`; `sort -V` → `Sort-Object { [version]($_ -replace '^v','') }`; `awk -F/` → `-split '/'`; heredocs → `@"..."@`.

### Hook inventory (corrected from ticket framing)

Of the 9 hooks the ticket enumerates, **only one** (`cortex-scan-lifecycle.sh:424`) calls a `cortex-*` entry point. The other eight contain substantive bash logic. Detailed classification:

| File | Lines | Body | Classification | Registered |
|------|-------|------|----------------|-----------|
| `hooks/cortex-validate-commit.sh` | 111 | Pure bash regex validation (no entry-point call) | Self-contained bash | `plugins/cortex-core/hooks/hooks.json` PreToolUse |
| `hooks/cortex-scan-lifecycle.sh` | 477 | Inline `python3 -c "..."` blocks + 1 fire-and-forget `cortex-pipeline-metrics` call at :424 | Mixed | `plugins/cortex-overnight/hooks/hooks.json` SessionStart |
| `hooks/cortex-cleanup-session.sh` | 36 | Pure bash (no entry-point call) | Self-contained bash | `plugins/cortex-overnight/hooks/hooks.json` SessionEnd |
| `claude/hooks/cortex-tool-failure-tracker.sh` | 105 | Pure bash + jq | Self-contained bash | `plugins/cortex-overnight/hooks/hooks.json` PostToolUse |
| `claude/hooks/cortex-skill-edit-advisor.sh` | 99 | Calls `just`, not cortex | Self-contained bash | **Not registered as a hook** |
| `claude/hooks/cortex-permission-audit-log.sh` | 89 | Pure bash + jq | Self-contained bash | `plugins/cortex-overnight/hooks/hooks.json` Notification |
| `claude/hooks/cortex-worktree-create.sh` | 66 | Pure bash + git | Self-contained bash | `plugins/cortex-core/hooks/hooks.json` WorktreeCreate |
| `claude/hooks/cortex-worktree-remove.sh` | 24 | Calls `~/.claude/notify.sh` (external) | Self-contained bash | `plugins/cortex-core/hooks/hooks.json` WorktreeRemove |

Hook registration files use `${CLAUDE_PLUGIN_ROOT}/hooks/<name>.sh` pattern (`plugins/cortex-core/hooks/hooks.json:9-19`, `plugins/cortex-overnight/hooks/hooks.json:3-44`). Neither `claude/settings.json` nor `.claude-plugin/plugin.json` files contain hook wiring — hooks are plugin-local via `hooks.json`.

### Plugin hook tree inventory (alignment-finding scope check)

Only two plugin hook trees are in scope under the dual-source enforcer:

- `plugins/cortex-core/hooks/` — mirrors `hooks/cortex-validate-commit.sh`, `claude/hooks/cortex-worktree-create.sh`, `claude/hooks/cortex-worktree-remove.sh`
- `plugins/cortex-overnight/hooks/` — mirrors `hooks/cortex-scan-lifecycle.sh`, `hooks/cortex-cleanup-session.sh`, `claude/hooks/cortex-tool-failure-tracker.sh`, `claude/hooks/cortex-permission-audit-log.sh`

Not in scope: `plugins/cortex-pr-review/skills/pr-review/scripts/evidence-ground.sh` is a skill utility, not a Claude Code hook; `plugins/cortex-ui-extras/` and `plugins/cortex-dev-extras/` ship no hook trees.

### Dual-source pre-commit drift enforcer

`.githooks/pre-commit` Phase 1.5 (lines 72-92) triggers SKILL-to-bin parity on staged paths matching `hooks/cortex-*|claude/hooks/cortex-*`. Phase 2 (lines 256-272) detects build necessity from path patterns; Phase 3 (lines 277-283) runs `just build-plugin`. Phase 4 (lines 286-313) detects drift via `git diff --quiet -- "plugins/$p/"`.

`justfile:662` contains the build-plugin orchestration's deletion logic: `rm -f plugins/$p/hooks/cortex-*.sh`. **This pattern is `.sh`-extension-pinned.** If a future rewrite ticket produces `.py` or `.ps1` files under the canonical hook trees, the deletion glob silently fails to clean stale files and the drift-detection in Phase 4 only catches content drift, not orphaned files. The deletion glob should be widened to `cortex-*` (no extension pin) regardless of whether this ticket touches it.

Note that `claude/hooks/cortex-skill-edit-advisor.sh` does not appear in the build-plugin recipe at `justfile:646,652` — it's repo-local and is not a Claude Code hook. The 9-hook count Agent 1 produced is misleading; 8 hooks are actually wired through `hooks.json`.

### `pyproject.toml` — `[project.scripts]` and wheel force-include

`pyproject.toml` lines 20-42 declare 22+ console-script entries (`cortex`, `cortex-batch-runner`, `cortex-update-item`, `cortex-create-backlog-item`, `cortex-generate-backlog-index`, `cortex-build-epic-map`, `cortex-auth`, `cortex-common`, `cortex-critical-review`, `cortex-dashboard-seed`, `cortex-daytime-dispatch-writer`, `cortex-daytime-pipeline`, `cortex-daytime-result-reader`, `cortex-discovery`, `cortex-integration-recovery`, `cortex-interrupt`, `cortex-morning-review-complete-session`, `cortex-pipeline-metrics`, `cortex-report`, `cortex-smoke-test`). On Windows, uv produces a `.exe` shim for each in `%USERPROFILE%\.local\bin\`. The high entry-point count amplifies the risk of `astral-sh/uv#10030` ("access denied" mid-multi-shim install) — see Adversarial Review F11.

Wheel force-include at `[tool.hatch.build.targets.wheel.force-include]` ships `cortex_command/overnight/scheduler/launcher.sh` inside every wheel. Ticket 217 (Windows scheduler port) adds `launcher.ps1` to this list; 218 does not modify wheel-include behavior.

### `docs/setup.md` structure

Existing sections: Prerequisites (lines 11-17), Install (lines 20-100), Plugin prerequisites (lines 73-78), Troubleshooting plugin install (lines 84-92), Per-repo setup (lines 95-100). The Windows additions slot as: (a) Windows Quickstart paralleling the bash install snippet at lines 26-38; (b) Windows-troubleshooting subsection enumerating uv gotchas; (c) Git for Windows requirement documented as a Windows-only prerequisite.

### Platform-conditional code dependencies (216 dependency surface)

Hooks that shell out to Python entry points indirectly exercise these `cortex_command` modules: `cortex_command/overnight/runner.py` (fcntl.flock, killpg, start_new_session, SIGHUP); `cortex_command/overnight/ipc.py` (fcntl.flock); `cortex_command/overnight/scheduler/lock.py` (fcntl.flock); `cortex_command/init/settings_merge.py` (fcntl.flock on ~/.claude/.settings.local.json.lock); `cortex_command/overnight/runner_primitives.py` (SHUTDOWN_SIGNALS includes SIGHUP); `cortex_command/overnight/cli_handler.py` (start_new_session, killpg); `cortex_command/overnight/sandbox_settings.py` (event-log lock); `cortex_command/pipeline/worktree.py` (TMPDIR fallback, lsof-based stale-lock cleanup); `cortex_command/dashboard/app.py` (XDG_CACHE_HOME resolution); `plugins/cortex-overnight/server.py` (lock + ps-probe via psutil).

These are ticket 216's surface. Until 216 lands, modules that `import fcntl` at top level fail to import on Windows — meaning any `cortex-*` entry point whose call graph reaches them crashes immediately. **The W6 empirical hook test cannot meaningfully run until 216 is complete** (user-decided per the lifecycle gate above).

### `claude/statusline.sh` + `claude/statusline.ps1` (dual-artifact precedent)

The existing `.sh` + `.ps1` sibling pattern at `claude/statusline.{sh,ps1}` is documented as the fallback model for hooks. The wiring (in Claude Code's native statusline selection) is shell-aware; no explicit JSON-side conditional is required. The `.sh` is ~28KB (cc-statusline npm output) and the `.ps1` is ~5KB (hand-authored). Pattern lessons for hooks: if `.ps1` siblings are ever needed, they live adjacent to the `.sh`, Claude Code's resolver picks per shell, and the build-plugin orchestrator must mirror both files (which the `cortex-*.sh`-pinned glob does not currently support).

## Web Research

### Claude Code hook execution on Windows — documented behavior

[Hooks docs](https://code.claude.com/docs/en/hooks) verbatim:

> "Exec form runs when `args` is present. Claude Code resolves `command` as an executable on `PATH` and spawns it directly with `args` as the argument vector. There is no shell..."
>
> "Shell form runs when `args` is absent. The `command` string is passed to a shell: `sh -c` on macOS and Linux, **Git Bash on Windows, or PowerShell when Git Bash isn't installed**."
>
> "On Windows, exec form requires `command` to resolve to a real executable such as a `.exe`. The `.cmd` and `.bat` shims that npm, npx, eslint, and other tools install in `node_modules/.bin` are not executables and cannot be spawned without a shell..."

[Setup docs](https://code.claude.com/docs/en/setup) verbatim:

> "On native Windows, Git for Windows is recommended; Claude Code falls back to PowerShell when Git Bash is absent."
>
> "When Git Bash is installed, Claude Code uses it internally to execute commands regardless of where you launched it. If Claude Code can't find your Git Bash installation, set the path in your settings.json file: `CLAUDE_CODE_GIT_BASH_PATH`."

The docs explicitly bless `.exe` for exec-form invocation; the carve-out is for `.cmd`/`.bat` shims, not `.exe`. uv's `uv tool install` produces real `.exe` shims (not `.cmd`), so the docs predict exec-form should work. However, the documented behavior diverges from the observed behavior — see the Adversarial Review and Open Questions.

### Claude Code Windows hook-execution bug surface — active

- **[#21468](https://github.com/anthropics/claude-code/issues/21468)** — "Plugin SessionStart hook fails on Windows" — **state: OPEN, last updated 2026-05-12 (3 days before today, 2026-05-15)**. Root canonical issue documenting: WSL `bash.exe` chosen over Git Bash `bash.exe`; stdin-as-TTY; file-association prompts; `shell` setting silently ignored; `CLAUDE_CODE_GIT_BASH_PATH` only partially mitigating each. Community workaround: rewrite hooks in Node.js (`https://github.com/Del53303/claude-code-windows-hook`).
- **[#22700](https://github.com/anthropics/claude-code/issues/22700)** — closed 2026-03-03 for inactivity, **not fixed**. Claude Code detects `D:\Program Files\Git\bin\bash.exe` correctly at startup but executes hooks with bare `bash`. Bot-closure.
- **[#29560](https://github.com/anthropics/claude-code/issues/29560)** — "Bug: Hook commands not executing on Windows Desktop App" — Windows Desktop App v2.1.51; every command form silently fails. Closed-as-duplicate of #21468.
- **[#59513](https://github.com/anthropics/claude-code/issues/59513)** — filed **today, 2026-05-15**: VSCode extension v2.1.142 PostToolUse Bash hook does NOT fire for LLM-initiated Bash tool calls.
- **[#59496](https://github.com/anthropics/claude-code/issues/59496)** — filed **today, 2026-05-15**: Disabled plugins still execute SessionStart hooks.

Two regressions filed today and a root canonical issue updated three days ago — the hook subsystem is **not stabilizing**. Any W6 test pinned to one Claude Code version becomes stale within weeks. Bot-driven duplicate-closures mean the issue tracker undercounts the true bug surface.

`cortex-scan-lifecycle.sh` (cortex's most complex hook, 477 lines) is registered as `SessionStart` per `plugins/cortex-overnight/hooks/hooks.json:3-13` — exactly the event class where #21468 reproduces. The W6 test walks into the worst-case event/hook combination.

### uv on Windows — installer + shim mechanics + known gotchas

[uv concepts/tools](https://docs.astral.sh/uv/concepts/tools/):

> "Tool executables are symlinked into the [executable directory] on Unix and **copied on Windows**."
>
> "The [executable directory] must be in the `PATH` variable for tool executables to be available from the shell. If it is not in the `PATH`, a warning will be displayed."
>
> "The `uv tool update-shell` command can be used to add the executable directory to the `PATH`."

Windows executable directory: `%USERPROFILE%\.local\bin`. Canonical PowerShell bootstrap: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`. `UV_NO_MODIFY_PATH=1` opts out of PATH modification.

Shim mechanics: pip/uv-generated console-script `.exe` files are real PE32+ executables that `CreateProcessW(python.exe, embedded-script)`. The Python path is baked into the shim's resource section — **no system `python.exe` on PATH is required**. This is the strongest evidence for "exec-form `.exe` shim invocation should work in principle"; the residual risk is Claude Code's resolver itself (not the shim).

Known uv-Windows issues:

| Issue | Status | Workaround |
|-------|--------|------------|
| [#17331](https://github.com/astral-sh/uv/issues/17331) — PATH `WM_SETTINGCHANGE` not broadcast | Fixed in uv **0.9.25** (2026-01-13) via PR #17404 | Pre-fix: open Environment Variables and click OK. On 0.9.25+, install broadcasts automatically. |
| [#14693](https://github.com/astral-sh/uv/issues/14693) — Conflicting PATH info on Windows | **Open**, no fix | Manually prepend: `$env:PATH = "C:\Users\<you>\.local\bin;$env:PATH"`. |
| [#15011](https://github.com/astral-sh/uv/issues/15011) → [#17344](https://github.com/astral-sh/uv/issues/17344) — Defender flags `uvw.exe` as `Trojan:Script/Phonzy.A!ml` | Closed-as-dup; affected 0.9.22 specifically | Downgrade to 0.9.21, OR add install dir to Defender exclusions, OR restore quarantined `uvw.exe`. Root cause: Defender heuristic. |
| [#10030](https://github.com/astral-sh/uv/issues/10030) — "Access denied" mid-multi-shim install | Closed, no specific fix version | Retry; close all terminals; disable AV scanning of AppData mid-write. **cortex installs 22+ shims**, raising this risk. |
| [#16877](https://github.com/astral-sh/uv/issues/16877) — symlink admin requirement | Fixed | Cortex uses copy-mode (uv's Windows default); N/A. |

### Reference PowerShell installer patterns

[pydevtools.com handbook](https://pydevtools.com/handbook/how-to/how-to-distribute-internal-python-cli-tools-with-uv/) provides the canonical mirror pattern:

```powershell
$ErrorActionPreference = "Stop"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
}
uv tool install "package==version"
```

[microsoft/conductor #115](https://github.com/microsoft/conductor/issues/115) — "install.ps1 missing `uv tool update-shell`": the lesson for cortex is that install.ps1 **must** call `uv tool update-shell` after `uv tool install`, and the next-steps message must explicitly mention "re-open your terminal" for users on uv <0.9.25 where the PATH broadcast is missing.

Synthesized composite for cortex install.ps1 (subject to spec-phase refinement per the security caveats below):

```powershell
$ErrorActionPreference = 'Stop'
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    irm https://astral.sh/uv/install.ps1 | iex
    $env:Path = [Environment]::GetEnvironmentVariable('Path','User') + ';' + $env:Path
}
$tag = (git ls-remote --tags --refs https://github.com/charleshall888/cortex-command.git |
        ForEach-Object { ($_ -split '/')[-1] } |
        Where-Object { $_ -match '^v\d+\.\d+\.\d+$' } |
        Sort-Object { [version]($_ -replace '^v','') } | Select-Object -Last 1)
uv tool install "git+https://github.com/charleshall888/cortex-command.git@$tag"
uv tool update-shell
Write-Host "cortex installed. Next: run ``cortex init`` in your project root."
```

## Requirements & Constraints

### Distribution and CLI contract

From `cortex/requirements/project.md`:

> "Ships CLI-first as a non-editable wheel: `uv tool install git+<url>@<tag>`." (Overview)
>
> "The cortex CLI wheel and the cortex-overnight plugin ship via independent channels (wheel via `uv tool install`; plugin via Claude Code marketplace). They couple through (a) `plugins/cortex-overnight/server.py`'s `CLI_PIN` tuple..." (Architectural Constraints)

Implication: install.ps1 must produce the same CLI wheel and PATH-registered `cortex.exe` as install.sh; the CLI/plugin version contract is unaffected (this ticket does not touch `pyproject.toml`'s entry-point declarations).

### Per-repo sandbox registration

From `cortex/requirements/project.md`:

> "`cortex init` additively adds the repo's `cortex/` umbrella to `~/.claude/settings.local.json` `sandbox.filesystem.allowWrite` — the only write cortex-command makes in `~/.claude/`. `fcntl.flock` serialized."

Implication: `cortex init` requires `cortex_command/init/settings_merge.py`'s `fcntl.flock` call to succeed. This is the strongest signal that **218 cannot run its `cortex init` smoke-test until 216 has shipped the platform-abstraction lock substitute** — `fcntl` does not import on Windows. The forward-compatible JSON write is currently inert on Windows (sandbox isn't enforced natively yet, per DR-2 in the epic research) and becomes live once Anthropic ships native-Windows sandboxing.

### Hook executable bit

From `cortex/lifecycle.config.md`:

> "Hook/notification scripts must be executable (`chmod +x`)"

Implication: applies to `.sh` files only; irrelevant under the Q1=C recommendation (no `.sh` deletions). If `.ps1` siblings are ever authored, Windows has no Unix permission bit and this constraint becomes a no-op there.

### Dual-source drift enforcement

From `cortex/requirements/project.md`:

> "SKILL.md-to-bin parity enforcement: `bin/cortex-*` scripts wire through an in-scope SKILL.md/requirements/docs/hooks/justfile/tests reference. `bin/cortex-check-parity` blocks drift; exceptions at `bin/.parity-exceptions.md`."

The hook trees are mirrored from `hooks/` and `claude/hooks/` to `plugins/cortex-core/hooks/` and `plugins/cortex-overnight/hooks/` via the `.githooks/pre-commit` orchestrator. Any change to hook invocation patterns (e.g., changing `command:` strings from `${CLAUDE_PLUGIN_ROOT}/hooks/foo.sh` to `cortex-foo`) must update both the canonical sources and the mirror-side `hooks.json` files; the enforcer compares both.

### Sibling ticket boundaries

From `cortex/backlog/216-add-platform-abstraction-package-for-windows.md`: 216 provides `cortex_command/platform/{lock.py,process.py,WINDOWS flag}`, the dashboard XDG-path substitute, and the TMPDIR fallback. **218's empirical hook test requires 216's deliverables on disk.**

From `cortex/backlog/219-add-windows-posture-surface-and-advisory-ci.md`: 219 provides the `cortex init`/runner startup sandbox warning, the README/setup.md "best-effort Windows" caveat, and the advisory Windows-smoke CI job. **218 does not duplicate these surfaces** — 218 ships only the install path and the hook strategy; the posture text and runtime warning are 219's scope.

From the epic at `cortex/backlog/215-add-native-windows-host-support-for-the-agentic-harness.md:37`: "Ship 216 + 218 + 219 together as 'Windows v1'... The dependency order is 216 first, then 218 (needs cortex on PATH via installer)." This sequencing is the explicit framing — and the Open Questions below challenge whether it survives the W6 empirical outcome.

### CLAUDE.md conventions

> "New hooks/notification scripts must be executable (`chmod +x`)" — applies only to `.sh` artifacts.
>
> "Solution horizon: long-term project — fixes reflect that." — the Q1=C ("keep `.sh` hooks for now, defer cross-platform rewrite") recommendation must justify itself against this principle. The justification: the rewrite is genuinely large (8 substantive bash hooks, not thin wrappers), bundling it with the Windows port couples two unrelated motivations, and the cross-platform endpoint is correct but deserves its own ticket scope.
>
> "MUST-escalation policy: default to soft positive-routing phrasing." — applies to spec authoring; not implementation-shaping.

## Tradeoffs & Alternatives

### Q1 — Hook strategy

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A — Exec-form entry points** | Delete `.sh` wrappers; `command: "cortex-foo"` | Cross-platform symmetric JSON; eliminates bash-on-Windows; eliminates CRLF risk; aligns with cortex-* CLI canonical surface | Front-loads rewrite of 8 substantive-bash hooks (not thin wrappers); empirically unvalidated; cold-start Python heavier than bash+jq |
| **B — `.ps1` siblings** | Author `.ps1` next to every `.sh` (statusline precedent) | No rewrite; bash logic stays; per-platform independently editable | Doubles file count; doubles dual-source mirror surface; no parity enforcement between `.sh` and `.ps1`; CRLF risk persists |
| **C — Keep `.sh`, require Git for Windows** | Zero file changes; document Git Bash routing as the Windows hook execution path | Zero work; aligns with user's "require certain tools" steer and existing `.githooks/pre-commit`/test-script posture; no cross-platform deletion risk | bash+jq+curl per hook is slow on Windows; CRLF risk needs per-hook `tr -d '\r'` or a `.gitattributes` fix; users following Anthropic's docs (which no longer hard-require Git for Windows since Claude Code v2.1.120) may not install Git Bash → silent hook failure |
| **D — Pure-Python `python -m cortex_command.hooks.foo`** | Equivalent to A but explicit about the rewrite | All A pros; avoids `.exe` shim dependency entirely (no Claude-Code-resolver-on-Windows risk) | Same rewrite cost as A; wordier `command:` strings |

**Recommended: C for this ticket; A or D (Python rewrite) for a follow-on ticket.** Rationale: the ticket title's premise that `.sh` hooks are thin wrappers is wrong — 8 of 9 hooks contain substantive bash logic that takes real work to migrate. The user's clarify steer ("require certain tools") and the project's existing Git-for-Windows requirement for `.githooks/pre-commit` and test scripts make C the cheapest aligned-with-current-posture option. C lets the empirical hook validation succeed (hooks fire under Git Bash exactly as on POSIX) without bundling a multi-hook rewrite that's larger than the Windows port itself. The cross-platform-deletion-on-macOS risk the clarify-critic surfaced is eliminated under C because nothing gets deleted. A/D remains the correct long-term endpoint — defer to a dedicated rewrite ticket where the scope is "rewrite cortex-shipped hooks as cross-platform entry points," decoupled from the Windows port. B is rejected: it has all of A's costs (doubled artifacts) with none of the simplification benefits, and the user's stated simplicity bias actively pushes against it.

The discovery's DR-3 recommended "B if exec-form shim test passes, A as fallback." The inversion here is informed by: (a) inspecting the actual hook bodies (not thin wrappers), (b) the user's clarify steer arriving after the discovery completed, and (c) the upstream Claude Code Windows hook bug surface (#21468) being far more active than the discovery captured.

### Q2 — Installer authoring

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A — `install.ps1` sibling** | Top-level sibling to install.sh, three-step mirror | Exact macOS mirror; preserves tag resolution and URL normalization; symmetric signal to readers | Two scripts to keep aligned as install evolves |
| **B — Docs two-liner** | No script; document `irm | iex` + `uv tool install` in `docs/setup.md` | Zero new artifacts; maximum simplicity per user steer | Breaks symmetry with macOS; loses tag-resolution/normalization/error-handling that install.sh encodes; forks/pins get a worse experience than macOS |
| **C — `cortex bootstrap` subcommand** | Python subcommand inside CLI | One canonical install flow | Chicken-and-egg: can't run cortex to install cortex; useful only post-install (which `uv tool upgrade` already covers) |

**Recommended: A — `install.ps1` sibling.** The macOS pattern is install.sh and the discovery already named install.ps1 as the natural sibling. The user's clarify steer pushes simplicity, but B's simplicity is purchased by losing the tag-resolution and URL-normalization logic that install.sh encodes — users who fork or pin will hit the difference. C is structurally wrong for the install-time use case. B's two-liner can additionally appear in `docs/setup.md` as a "no-script" fallback for users who prefer copy-paste — that's complementary, not a substitute. The install.ps1 deliverable additionally needs hardening per the Adversarial Review's security findings (S1, F12, F13).

### Q3 — Empirical validation surface

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A — One-shot Windows VM session** | Capture commands + outputs in `events.log`; close ticket on pass | Lowest cost; matches discovery's W6-within-piece framing | No recurring signal; future regressions caught by users in the wild |
| **B — Fold into 219's CI** | Add a hook-fires step to `.github/workflows/windows-smoke.yml` | Recurring signal on every PR; regressions surface within a CI cycle | Requires Claude Code on `windows-latest` runner (feasible via WinGet but adds a moving dependency); CI flakiness risk |
| **C — Skip validation** | Document "validated locally" in changelog | Lowest cost | Contract-incompatible with ticket title ("validate hook execution") |

**Recommended: A for 218; B as a follow-on under 219.** The ticket's role is one-shot empirical validation; capturing it in `events.log` makes it reproducible and discoverable later. 219's CI is advisory anyway, so the gating signal is roughly equivalent either way. The split avoids a hidden dependency: CI hookup requires Claude Code installed on the runner to test resolver behavior end-to-end, which is non-trivial CI surface to design separately. A first answers the empirical question definitively; B then becomes "regression-detect this same test forever" rather than "discover this for the first time."

**Critical revision per Adversarial F1**: the gate should be **"hooks-don't-crash-Claude-Code and cortex CLI works without hooks"** — not "hooks fire successfully." The upstream evidence (issue #21468) makes a clean pass unlikely; Windows v1 must remain shippable even if hooks are degraded on Windows pending Anthropic's upstream fix.

### Q4 — Hook command registration mechanism

Moot under Q1=C: the existing `${CLAUDE_PLUGIN_ROOT}/hooks/<name>.sh` pattern in `plugins/cortex-{core,overnight}/hooks/hooks.json` already works cross-platform under Git Bash; no change needed. Q4 only becomes live if Q1 picks A/D in the future rewrite ticket, at which point A (entry-point name on PATH) is the right answer — cross-platform symmetric JSON; the explicit-path option (B) breaks the mirror; the env-var option (C) depends on Claude-Code-resolver behavior that's not documented.

## Adversarial Review

### Failure modes the recommendations miss

**F1 — Issue #21468 is OPEN; Windows hook execution is known-broken upstream.** The canonical issue is `anthropics/claude-code#21468`, last updated 2026-05-12. Documented failures: WSL `bash.exe` chosen over Git Bash; stdin-as-TTY; file-association prompts; `shell` setting silently ignored; `CLAUDE_CODE_GIT_BASH_PATH` partial mitigation. The community workaround in the thread is to rewrite hooks in Node.js. The Q1=C recommendation rests on the assumption that Git Bash hook routing works — public evidence says it often doesn't.

**F2 — `cortex-scan-lifecycle.sh` is SessionStart**, exactly the event class #21468 reproduces on. Our most complex 477-line hook is registered at `plugins/cortex-overnight/hooks/hooks.json:3-13`. Worst-case combination.

**F3 — Hook regressions filed today (2026-05-15).** Two issues filed today on hook subsystem regressions (#59513, #59496). The surface is not stabilizing; a W6 test pinned to one Claude Code version becomes stale within weeks.

**F4 — No `.gitattributes`.** Verified absent at repo root. Every developer who clones on Windows silently corrupts hook files via CRLF on next commit. `hooks/cortex-validate-commit.sh:59,64` is the canonical breakage point (`SUBJECT =~ \.$` becomes `SUBJECT =~ \r$` after CRLF tainting). The fix is one line: ship `.gitattributes` with `* text=auto eol=lf` and `*.sh text eol=lf` AS PART OF #218.

**F5 — `justfile:662`'s deletion glob is `.sh`-pinned**: `rm -f plugins/$p/hooks/cortex-*.sh`. If a future rewrite produces `.py` or `.ps1` files, the glob silently fails to clean stale files. Should be widened to `cortex-*` (no extension pin) **regardless of which Q1 option ships**.

**F6 — `cortex-skill-edit-advisor.sh` is not registered as a hook** and is not in the build-plugin recipe. Repo-local utility. Spec should clarify whether it's in scope (it isn't, per hooks.json absence).

**F7 — `command -v cortex-pipeline-metrics` fire-and-forget on Windows**: `hooks/cortex-scan-lifecycle.sh:424` silently no-ops if PATH wasn't refreshed since `uv tool install`. Pipeline metrics intermittently empty on Windows.

**F8 — `command -v python3` won't resolve on Windows**: `hooks/cortex-scan-lifecycle.sh:34` checks `python3`, but Windows installs expose `python.exe`, `py.exe`, or uv-managed `python` — not `python3`. Lifecycle scanning silently disabled on Windows even when Python is fully functional. **Fix in this ticket**: change to `command -v python3 || command -v python`.

**F9 — `git diff --quiet` is not LF-normalized**: the pre-commit drift comparator at `.githooks/pre-commit:296` fails on every commit if rsync/copy under Git Bash changes line endings. Out-of-218 long-term, but the moment cortex-command is developed *on* Windows it's broken.

**F10 — `uvx` and `pipx` produce different shim layouts than `uv tool install`**: ephemeral installs in `%LOCALAPPDATA%\uv\cache\environments-v2\<hash>\Scripts\` (uvx) or `%APPDATA%\Python\Python3x\Scripts\` (pipx). Spec should reject these as supported install paths — only `uv tool install` is blessed.

**F11 — `uv tool install` with 22+ shims has elevated #10030 risk** ("access denied" mid-multi-shim install). install.ps1 should retry once on access-denied, or document the "close all terminals and re-run" remediation.

**F12 — PowerShell ExecutionPolicy "Restricted" by default on corporate Windows.** A naïve `.\install.ps1` invocation fails. The install command must be documented as `powershell -ExecutionPolicy Bypass -File install.ps1` (or piped through `irm | iex` in setup.md).

**F13 — `git ls-remote` may pop corporate-credential auth UI mid-install.** install.ps1 should use the GitHub REST API (`/repos/<owner>/<repo>/tags`) for tag resolution rather than `git ls-remote`, accepting the unauthenticated rate-limit trade-off (60 req/hr — acceptable for one-shot install).

**F14 — Bot-driven duplicate-closures undercount the true bug surface.** 3 of 4 traced Windows-hook bugs were closed by `github-actions[bot]`, not human-validated fixes. Anthropic's issue tracker is not a reliable "fixed" signal. The W6 test must **reproduce the failure manually** rather than trusting issue state.

### Security concerns

**S1 — `irm | iex` over the wire has no integrity check.** The uv install pattern (`irm https://astral.sh/uv/install.ps1 | iex`) trusts TLS + DNS exclusively. install.ps1 should pin to a specific uv release URL (e.g., `https://github.com/astral-sh/uv/releases/download/0.9.25/uv-installer.ps1`) rather than the rolling `astral.sh/uv/install.ps1`. install.sh has the same property today but it's grandfathered; install.ps1 should not import the same defect.

**S2 — `.exe` shim attack surface is materially wider than `.sh` under Git Bash.** Under Q1=C this is moot for now, but the future rewrite ticket (A/D) must address: a compromised cortex release (PyPI supply chain) or a uv-cache poisoning attack can replace `cortex-*.exe` and gain SessionStart-level hook execution on every new Claude Code conversation. Mitigation belongs in the rewrite ticket.

**S3 — DLL-hijack risk for uv-produced `.exe` shims.** `CreateProcessW` searches the CWD before system PATH unless `SafeProcessSearchMode` is set. If Claude Code spawns hooks with the project directory as CWD, an attacker dropping `python.dll` into the project gains code execution. uv's shim source needs audit; if it doesn't call `SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_SYSTEM32)`, every hook fire is a planting opportunity.

### Assumptions that may not hold

**A1 — "216 + 218 + 219 ship together as Windows v1" is incompatible with 218 having an empirical gate.** If 218's W6 test reveals upstream-broken hook execution (likely per F1), the team faces a fork: ship Windows v1 with broken hooks (unacceptable) or hold the bundle. The only sound sequence is serial: 216 → 218-validation → 218-implementation (Q1 decision depends on validation outcome) → 219. Surface to Open Questions for the operator.

**A2 — "Claude Code Windows Desktop App vs CLI is the same code path"** is implicit but untested. Issue #29560's reporter ran on the Desktop App, not the CLI. Cortex's W6 test plan must specify both clients; validating only the CLI may green-light a deliverable that's broken for the majority of users.

**A3 — "Future hook rewrites can defer until evidence accumulates"** without an authored telemetry signal means "defer indefinitely." Q1=C's honest framing is "ship `.sh` for Windows v1 because the alternative is too much work for one ticket, accepting that some Windows users will see silent hook breakage" — that framing belongs in 218's spec and in 219's user-facing posture text.

### Recommended mitigations (for the spec)

1. **Reframe the W6 gate.** Don't gate Windows v1 on hooks-fire-successfully. Gate on (a) hooks-don't-crash-Claude-Code, (b) cortex CLI works without hooks. Document hook execution as known-degraded on Windows pending #21468 upstream resolution.
2. **Ship `.gitattributes` (`* text=auto eol=lf`; `*.sh text eol=lf`) as part of 218.** Unblocks Windows-host development.
3. **Fix `command -v python3` → `command -v python3 || command -v python`** in `hooks/cortex-scan-lifecycle.sh:34`.
4. **Update `justfile:662` deletion glob to `cortex-*`** (no extension pin) even under Q1=C — unblocks the future rewrite ticket.
5. **install.ps1 uses pinned uv release URLs** rather than `astral.sh/uv/install.ps1` (addresses S1).
6. **install.ps1 uses GitHub REST API for tag resolution** rather than `git ls-remote` (addresses F13).
7. **W6 test runs against the Windows Desktop App, not just CLI.**
8. **Decouple 216/218/219.** Sequence serially. The Review Criteria in `cortex/lifecycle.config.md` should add: "If W6 reveals hook execution is broken upstream (per #21468), document the limitation in 219's posture surface and ship Windows v1 with hooks marked best-effort."
9. **Document `pipx` and `uvx` as unsupported install paths.** Only `uv tool install` produces PATH-registered persistent shims.
10. **Audit `cortex-validate-commit.sh` for `\r`-resilience** and add a CR-stripping idiom to a single shared utility sourced by all `.sh` hooks. Durable over scattered `tr -d '\r'` calls.

## Open Questions

The recommendations above are conditional on these decisions. None are blockers for spec authoring; surfacing them now so the spec author resolves with the user before drafting.

- **Sequencing of 216/218/219 in Windows v1.** Epic 215 says "ship together," but 218 has an empirical gate (W6) that may surface upstream-broken hook execution per #21468. Adversarial A1 recommends decoupling to a serial 216 → 218-validation → 218-implementation → 219 sequence. **Deferred to spec**: this decision affects 215's release framing and is operator-shaped, not research-resolvable.
- **W6 gate semantics.** Should "validate hook execution" mean "hooks fire correctly" (the ticket title's literal reading) or "hooks don't crash Claude Code AND cortex CLI works without hooks" (the Adversarial F1-revised reading)? **Deferred to spec**: the choice shapes whether 218 can close in Windows v1 or whether it carries forward.
- **W6 test substrate.** Claude Code CLI vs Windows Desktop App vs VSCode extension. Issue #29560 reproduces only on the Desktop App. **Deferred to spec**: pick the test substrate the project's user base predominantly uses.
- **Cross-platform hook rewrite ticket.** Q1=C punts the rewrite to a follow-on. **Deferred to follow-on ticket creation**: who files it, when, and with what scope? Suggested scope: "rewrite cortex-shipped hooks as cross-platform entry points (Python or Node.js)" — independent of Windows port.
- **`.gitattributes` ownership.** F4 surfaces a missing repo-level file. **Resolved (in scope for 218)**: ship `.gitattributes` as part of this ticket; the cost is one file and one commit.
- **`hooks/cortex-scan-lifecycle.sh:34` Python detection.** F8 surfaces a Windows-incompatible check. **Resolved (in scope for 218)**: fix in 218.
- **`justfile:662` deletion glob.** F5 surfaces a load-bearing future-incompatibility. **Resolved (in scope for 218)**: widen the glob to `cortex-*`.

## Considerations Addressed

- **Inventory all plugin hook trees** — Codebase analysis confirmed only `plugins/cortex-core/hooks/` and `plugins/cortex-overnight/hooks/` are in scope under the dual-source enforcer; `evidence-ground.sh` in `cortex-pr-review` is a skill utility (not a hook), and `cortex-ui-extras`/`cortex-dev-extras` ship no hook trees. Scope boundary holds.
- **Hook dependency on ticket 216's platform-abstraction surface** — Codebase analysis enumerated 13 cortex_command modules using `fcntl.flock`/`start_new_session`/`killpg`/`SIGHUP`. Hooks reaching `cortex_command.init.settings_merge`, `cortex_command.overnight.*`, `cortex_command.pipeline.*`, or `cortex_command.auth.bootstrap` exercise 216's surface. The W6 empirical test is sequenced after 216 lands; the dependency is explicit and documented above.
