# Research: Build `cortex setup` subcommand and retire shareable-install scaffolding

## Epic Reference

This ticket implements DR-5 of the [overnight-layer-distribution epic](../../research/overnight-layer-distribution/research.md) — canonical `~/.claude/` + `~/.local/bin/` deployment via a CLI subcommand rather than an external build tool. DR-9 is the context for the optional `--with-extras` marketplace-registration flag. All other epic scope (bootstrap installer 118, per-repo init 119, plugin tickets 120–122, migration 124) is explicitly out of scope here.

Scoped intent: replace today's `just setup` + `/setup-merge` Claude-session skill with a single `cortex setup` CLI subcommand that (a) deploys symlinks into `~/.claude/` + `~/.local/bin/` additively (no user files overwritten), (b) opt-in `--merge-settings` flag runs additive-only skip-conflict deep-merge of `~/.claude/settings.json` against the shipped template, (c) opt-in `--verify-symlinks` re-checks deployed state for drift (used by `cortex upgrade`), (d) opt-in `--with-extras` registers the `cortex-command-plugins` marketplace as a convenience. Retire `just deploy-*` recipes, `just setup-force`, `just setup` modes, and the `/setup-merge` skill. Preserve the apiKeyHelper-removal state from shareable-install #004.

---

## Codebase Analysis

### Current install footprint

Today's `just setup` touches these host paths:

**`~/.local/bin/*` (10 symlinks)** — from `justfile:132-143` (`deploy-bin`):
- `bin/count-tokens`, `bin/audit-doc`, `bin/jcc`, `bin/overnight-start`, `bin/overnight-status`, `bin/overnight-schedule`, `bin/git-sync-rebase.sh` → `~/.local/bin/`
- `backlog/update_item.py` → `~/.local/bin/update-item`
- `backlog/create_item.py` → `~/.local/bin/create-backlog-item`
- `backlog/generate_index.py` → `~/.local/bin/generate-backlog-index`

Note: `justfile:47-55` (`setup-force`) omits `overnight-status` and `git-sync-rebase.sh` — existing drift between `deploy-bin` (authoritative) and `setup-force` (stale). `bin/validate-spec` exists in the repo but is NOT deployed — the justfile's `validate-spec` recipe (line 724) invokes it from the repo directly.

**`~/.claude/reference/*` (5 symlinks listed, 4 actually exist)** — from `justfile:183-188`: `claude/reference/{verification-mindset,parallel-agents,context-file-authoring,claude-skills,output-floors}.md`. Live drift: `claude/reference/verification-mindset.md` is listed but does NOT exist in the repo; `ln -sf` silently succeeds on missing sources, so `~/.claude/reference/verification-mindset.md` is a dangling symlink that neither `just setup` nor `check-symlinks` surfaces.

**`~/.claude/skills/*` (17 directory symlinks)** — dynamic glob over `skills/*/SKILL.md`. Uses `ln -sfn` (the `-n` matters — prevents descending into an existing dir symlink). Current deployed: backlog, commit, critical-review, dev, diagnose, discovery, evolve, fresh, lifecycle, morning-review, overnight, pr, refine, requirements, research, retro, skill-creator.

**`~/.claude/hooks/*` + `~/.claude/notify.sh` (special-cased)**:
- From `hooks/cortex-*.sh` (4 files): `cortex-cleanup-session.sh`, `cortex-scan-lifecycle.sh`, `cortex-validate-commit.sh` → `~/.claude/hooks/<same name>`. `hooks/cortex-notify.sh` → **`~/.claude/notify.sh`** (special-case rename — `justfile:274-276` — because `claude/settings.json` references this literal path in hook entries).
- From `claude/hooks/*` (10 files via glob): includes `cortex-output-filter.sh`, `cortex-permission-audit-log.sh`, `cortex-skill-edit-advisor.sh`, `cortex-sync-permissions.py`, `cortex-tool-failure-tracker.sh`, `cortex-worktree-create.sh`, `cortex-worktree-remove.sh`, and also `bell.ps1`, `output-filters.conf`, `setup-github-pat.sh` (non-cortex-prefixed but deployed by the glob). The `/setup-merge` skill uses `claude_hooks_dir.glob("cortex-*")` — a subtle divergence: the two paths cover different file sets.

**`~/.claude/rules/*` (2 symlinks)** — renames: `claude/rules/global-agent-rules.md` → `~/.claude/rules/cortex-global.md`; `claude/rules/sandbox-behaviors.md` → `~/.claude/rules/cortex-sandbox.md`.

**`~/.claude/statusline.sh`** — `claude/statusline.sh` → `~/.claude/statusline.sh`.

**`~/.claude/settings.json`** — **copied, not symlinked** (`justfile:341-352`). On first install: `cp claude/settings.json ~/.claude/settings.json.tmp && mv ...`. On re-run with regular file: prints `[ok]` and defers to `/setup-merge`. On re-run with symlink: prints `[migrate]` warning.

**`~/.claude/settings.local.json`** — directly written (`justfile:390-408`). Adds `$(pwd)/lifecycle/sessions/` to `sandbox.filesystem.allowWrite`. Uses `jq` to preserve other keys if available; falls back to full overwrite with warning if `jq` absent.

### Live drift in the current install

Spot-check of `~/.claude/hooks/` revealed **15+ stale unprefixed symlinks** alongside the `cortex-*` set — e.g., `~/.claude/hooks/scan-lifecycle.sh` links to `hooks/scan-lifecycle.sh` (no cortex prefix), orphans from before the DR-3 `cortex-` rename. Neither `just setup` nor `/setup-merge` cleans them up; `check-symlinks` only verifies expected targets exist and does not scan for orphans. `merge_settings.py:154,171` globs only `cortex-*`, so unprefixed orphans are invisible to detect/verify.

### `just setup` flow in detail

`just setup` (`justfile:10-34`) chains 6 steps:
1. Creates `CONFLICTS_FILE=$(mktemp ...)` tempfile with cleanup trap.
2. Invokes 5 deploy-* recipes sequentially: `deploy-bin`, `deploy-reference`, `deploy-skills`, `deploy-hooks`, `deploy-config`.
3. Invokes `python-setup` (`uv sync`).
4. If `CONFLICTS_FILE` non-empty, prints count + list and instructs user to run `/setup-merge`.
5. Prints `export CORTEX_COMMAND_ROOT=$(pwd)` instruction for shell profile.

**Per-symlink classification** (identical in every `deploy-*` recipe):
```
if target does not exist and is not a link:    [new]       ln -sf source target
elif target is a link and readlink == source:  [update]    ln -sf source target  (re-create)
elif target does not exist but is a link:      [conflict]  broken symlink
elif target is a link but readlink != source:  [conflict]  wrong symlink
else:                                          [conflict]  regular file
```

Matches `merge_settings.py:73-97 classify()` exactly.

**Conflicts flow**: each recipe appends `"$target (reason)"` to `$CONFLICTS_FILE`; if unset (recipe invoked directly), prints the list inline.

**Failure modes**:
- Worktree refusal: `setup-force` and `deploy-bin` check `git rev-parse --git-dir == --git-common-dir`; other recipes do NOT. A deploy from a worktree creates symlinks to the worktree path that break on worktree removal.
- `set -euo pipefail` — single ln failure aborts the recipe.
- No retry or rollback: partial install possible if `python-setup` fails after symlinks placed.
- `jq` missing: `settings.local.json` fallback is destructive (full overwrite with warning).

### `/setup-merge` skill algorithm

Lives at `.claude/skills/setup-merge/SKILL.md` (566 LOC prompt) + `.claude/skills/setup-merge/scripts/merge_settings.py` (1083 LOC helper). **Project-local skill** — only available when a Claude session is opened inside the cortex-command checkout.

**Helper modes** (`merge_settings.py:1000-1078`): `detect` (discover + diff → JSON in `$TMPDIR`), `merge` (apply approved changes atomically with mtime guard), `migrate` (convert settings.json from symlink to regular file).

**Detect output** (`merge_settings.py:471-522`):
- `mtime` — file stat for optimistic concurrency
- `user_settings_path`
- `symlinks` — array of `{source, target, ln_flag, status}` from `discover_symlinks()`
- `hooks_required.{present, absent}` — 10 required hooks (`REQUIRED_HOOK_SCRIPTS`, lines 17-28): sync-permissions.py, scan-lifecycle.sh, cleanup-session.sh, validate-commit.sh, output-filter.sh, tool-failure-tracker.sh, skill-edit-advisor.sh, permission-audit-log.sh, worktree-create.sh, worktree-remove.sh
- `hooks_optional.{present, absent}` — 1 optional (`OPTIONAL_HOOK_SCRIPTS:36`): cortex-notify.sh
- `allow.absent`, `deny.absent` — list-set diff preserving repo ordering (357-373)
- `sandbox.absent` — subkeys `allowedDomains`, `allowUnixSockets`, `excludedCommands`, `autoAllowBashIfSandboxed` (376-416)
- `statusLine.absent` — full object if `.command` differs (419-434)
- `plugins.absent` — keys missing from `enabledPlugins` (437-447); only checks `context7@claude-plugins-official` and `claude-md-management@claude-plugins-official`
- `apiKeyHelper.{status, value}` — **dead code**: `claude/settings.json` no longer has `apiKeyHelper` (verified — `grep apiKeyHelper claude/settings.json` returns nothing), so `detect_apikey_helper()` always returns `{status: "not_in_repo"}`.

**Merge contract** (`run_merge()`, lines 715-898): per-category Y/n approval, then strictly additive merge.
- Hooks: find entry in `settings.hooks[event_type]` by `matcher`; append command (dedup) or create new entry.
- permissions.allow/deny: concat with forward/reverse contradiction detection via `fnmatch.fnmatch()` on `extract_cmd()` (strips `Bash()` wrapper). Contradictions reported but non-blocking.
- sandbox: list-extend for `allowedDomains`/`allowUnixSockets`/`excludedCommands`; scalar set for `autoAllowBashIfSandboxed` (815-852).
- statusLine: full object overwrite (858).
- plugins: per-key add, does NOT overwrite existing (862-872).
- apiKeyHelper: scalar set if absent (874-881) — dead code now.

**Atomic write** (`atomic_write()`, 658-712):
- mtime guard: if `stat(settings.json).st_mtime != expected`, returns `{"error": "mtime_changed"}`.
- JSON roundtrip validation before write.
- `tempfile.mkstemp(dir=settings_dir)` + `fsync()` + `os.replace()`.

**Edge cases**:
- Settings as symlink: Step 1 converts via `migrate` subcommand.
- Worktree: refused.
- Sandbox `TMPDIR` starts with `/private/tmp/claude` or `/tmp/claude`: warning only, not halt.
- Broken symlinks: `conflict-broken`, prompt Y/n.
- Directory at symlink target: `conflict-file` subtype, special flow: `rm -r` (not `-rf` — deny rules block it) then `ln`.

### Shipped `settings.json` shape

376 lines. Top-level keys classified:

**Cortex-mandatory** (must be wired up for the project to function):
- `hooks` (223-336) — 8 event types wired to `~/.claude/hooks/cortex-*.sh` and `~/.claude/notify.sh`. Hook paths are **literal strings** — load-bearing.
- `statusLine` (337-341) — points at `~/.claude/statusline.sh`.
- `enabledPlugins` (342-346) — context7 + claude-md-management enabled; code-review disabled.

**Strongly-recommended** (safety baseline):
- `permissions.deny` (130-209) — safety rules (sudo, rm -rf, force push, read secrets).
- `permissions.allow` (12-129) — cortex-specific allows + 100+ general-purpose allowlist.
- `sandbox` (347-371) — `enabled: true`, `autoAllowBashIfSandboxed: true`, `allowedDomains`, `allowWrite`, `excludedCommands: ["gh:*", "git:*", "WebFetch", "WebSearch"]`.

**Personal preference** (risky to clobber):
- `cleanupPeriodDays`, `env.{CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS,teammateMode}`, `attribution.commit`, `permissions.ask`, `permissions.defaultMode`, `model: "opus[1m]"`, `enableAllProjectMcpServers`, `alwaysThinkingEnabled`, `effortLevel`, `skipDangerousModePermissionPrompt`, `skipAutoPermissionPrompt`.

**apiKeyHelper verification**: NOT in `claude/settings.json`. Shareable-install #004 fix is complete. Two residual mentions in `bin/count-tokens:68` and `bin/audit-doc:73` are benign error-message strings.

**`notify.sh` path-sensitivity**: `claude/settings.json` lines 275 and 289 invoke `~/.claude/notify.sh` as a literal string — the deployment path is load-bearing in settings.json, which is why `cortex-notify.sh` is symlinked to `~/.claude/notify.sh` (not `~/.claude/hooks/cortex-notify.sh`).

**Latent path inconsistency**: `claude/settings.json:359-364` has `sandbox.filesystem.allowWrite` including `~/cortex-command/lifecycle/sessions/` (hard-coded tilde path). `justfile:100-117, 390-408` write `$(pwd)/lifecycle/sessions/` into `settings.local.json`. These are two different paths for the same logical thing; cortex ships an inconsistency today.

**Worktree hooks** (316-335): `WorktreeCreate` and `WorktreeRemove` invoke `bash -c` scripts that read `CWD` from stdin JSON and shell out to `$CWD/claude/hooks/cortex-worktree-{create,remove}.sh`. Project-scoped by design.

### Files that will change

**New**:
- `cortex_command/setup/__init__.py` (or `cortex_command/setup.py`) — subcommand implementation.
- `cortex_command/setup/symlinks.py`, `cortex_command/setup/merge.py`, `cortex_command/setup/verify.py` (suggested split).
- `cortex_command/tests/test_setup.py`.

**Modified**:
- `cortex_command/cli.py:68-70` — replace `setup.set_defaults(func=_make_stub("setup"))` with dispatch, add argparse flags.
- `justfile` — delete `setup` (10-34), `setup-force` (37-118), `deploy-bin` (122-175), `deploy-reference` (178-221), `deploy-skills` (224-261), `deploy-hooks` (264-331), `deploy-config` (334-408). Optionally retain a thin `setup` delegating to `cortex setup` for one transition release. `check-symlinks` (727-773) and `verify-setup` (776-831) need review.
- `.claude/skills/setup-merge/SKILL.md` — delete.
- `.claude/skills/setup-merge/scripts/merge_settings.py` — delete or port helpers (classify, detect_*_delta, check_*_contradictions, atomic_write) into the new setup module.
- `claude/reference/verification-mindset.md` — either create or remove from justfile (drift fix).
- `docs/setup.md`, `README.md` (lines 76-88, 117-119, 170, 186), `docs/backlog.md:205-215`, `skills/morning-review/references/walkthrough.md:614`, `skills/overnight/SKILL.md:307` — rewrite instructions referencing `just deploy-*`.

**Unchanged**:
- `hooks/*`, `claude/hooks/*`, `claude/reference/*`, `claude/rules/*`, `claude/statusline.sh`, `bin/*`, `skills/*` (except the deleted setup-merge).

### Integration points and dependencies

**CLI entry**: `pyproject.toml:17-18` → `cortex = "cortex_command.cli:main"`. Installed via `uv tool install -e <repo>`. EPILOG contract: changes to `[project.scripts]` require `uv tool install -e . --force`.

**Repo root resolution** — three candidates:
1. `CORTEX_COMMAND_ROOT` env var (set in user shell profile per `justfile:31`; hard requirement in `bin/jcc:4-11` and `skills/overnight/SKILL.md:46-296`).
2. Package-relative: `Path(cortex_command.__file__).parent.parent` — works without env var because `uv tool install -e .` keeps the repo editable.
3. `git rev-parse --show-toplevel` of CWD — requires invocation from inside the repo.

**Env vars consumed**: `CORTEX_COMMAND_ROOT`, `TMPDIR`, `HOME`.

**Python deps** (`pyproject.toml`): `claude-agent-sdk`, `fastapi`, `uvicorn[standard]`, `jinja2`, `markdown`; dev: `pytest>=8.0`. No `click`/`typer`/`filelock`/`deepmerge` today — CLI uses stdlib `argparse`.

**Tests**: ticket 114 added no CLI-specific tests; `cortex_command/tests/` has only `_stubs.py` + `__init__.py`. `pytest.ini_options.testpaths` in `pyproject.toml:24` is where new tests need to be picked up. `justfile:882-908 test` runs `test-pipeline`, `test-overnight`, and `tests/` pytest.

### Conventions to follow

- **argparse**: `cli.py:39-84` shape. `RawDescriptionHelpFormatter` for multi-line help. Handlers return `int` (exit code); `main()` returns `args.func(args)`.
- **Stub exit code**: 2 (reserved for "not implemented" / "no subcommand").
- **Type annotations**: `def handler(_args: argparse.Namespace) -> int:`.
- **Atomic file writes**: `tempfile → fsync → os.replace`. Never `open(path, 'w').write()`.
- **Symlink classification**: preserve the 5-state rubric exactly (new / update / conflict-broken / conflict-wrong-target / conflict-file).
- **`ln -sf` vs `ln -sfn`**: file symlinks use `-sf`; directory symlinks (skill dirs) use `-sfn`. The `-n` prevents "ln follows existing dir symlink and creates *inside* it."
- **Worktree guard**: refuse to deploy from a git worktree (`git rev-parse --git-dir != --git-common-dir`).
- **Output format**: `[new] / [update] / [conflict] <target> — <reason>`.
- **Idempotency**: every deploy-* path must be safely re-runnable.

---

## Web Research

### Claude Code marketplace registration — authoritative

`claude plugin marketplace add <source> --scope user|project|local` is a **first-class non-interactive CLI command**. Per the official docs ([code.claude.com/docs/en/plugin-marketplaces](https://code.claude.com/docs/en/plugin-marketplaces)):

> Claude Code provides non-interactive `claude plugin marketplace` subcommands for scripting and automation. These are equivalent to the `/plugin marketplace` commands available inside an interactive session.

Supported sources: GitHub `owner/repo`, git URLs, local paths, remote `marketplace.json` URLs. `--scope` defaults to `user`.

**State storage**: `~/.claude/plugins/known_marketplaces.json` (per-user, not per-project). Layout:
```
~/.claude/plugins/
  known_marketplaces.json
  marketplaces/<name>/...
  cache/<marketplace>/<plugin>/<version>/...
```

**Alternative**: `.claude/settings.json`'s `extraKnownMarketplaces` key can pre-declare marketplaces that prompt on first use.

**Recommendation for `--with-extras`**: shell out to `claude plugin marketplace add charleshall888/cortex-command-plugins --scope user` with `shutil.which("claude")` guard. Don't write `known_marketplaces.json` directly — the CLI is stable and validates the manifest during add.

### Python CLI patterns for $HOME deployment

- **pre-commit** (gold standard): `pre-commit install` copies a generated shim into `.git/hooks/pre-commit`. Existing-hook behavior: **backup to `.legacy` by default**, opt-in `--overwrite`/`-f`. `pre-commit uninstall` restores the legacy file.
- **dotbot**: YAML manifest with `link`, `create`, `shell`, `clean`, `defaults` directives. Tiered conflict flags per link: `relink` (replace if symlink), `force` (replace any file/dir), `backup` (save as `.dotbot-backup.<timestamp>`), `create` (mkdir parents).
- **llm**: plugin system = `llm install <pkg>` into llm's own venv. Writes state to `~/Library/Application Support/io.datasette.llm/` — owned exclusively, no merge semantics. (Cortex can't take this path — `~/.claude/` is shared with Claude Code.)
- **pipx ensurepath**: appends to bottom of `~/.bashrc` / `~/.zshrc`. No explicit consent prompt; subcommand invocation IS the opt-in.

**Pattern to steal**: tiered conflict handling (non-destructive default, explicit opt-in for destructive replacement, reversible where possible).

### Python JSON deep-merge libraries

| Library | Strategies | Skip-on-conflict? | List dedup? | Verdict |
|---|---|---|---|---|
| **deepmerge** | Per-type strategy list + user-defined functions | **Yes via custom fn** (`lambda config, path, base, nxt: base` keeps destination) | `union` for sets; custom fn trivial for list dedup | **Recommended** for cortex semantics |
| **mergedeep** | `REPLACE`, `ADDITIVE`, `TYPESAFE_*` | No "keep destination" | `ADDITIVE` appends without dedup | Minimalist; wrong semantics for this use |
| **jsonmerge** | Schema-aware | Yes via schema | Yes via `arrayMergeById` | Overkill; requires schema definition |
| **Hand-rolled** | Whatever you write | Yes | Yes | ~30 LoC, dependency-free, full control |

**Recommendation**: hand-rolled 30-LoC recursive walker OR deepmerge with custom strategy tuple. The cortex requirement ("add keys the user doesn't have, skip conflicting scalars, dedup-append lists") is unusually specific.

**Gotcha**: list-of-dicts has no obvious dedup key. Permission lists are lists-of-strings (trivial), but `hooks.PostToolUse[].hooks[]` is list-of-dicts — needs content-hash dedup or custom equality. Existing `merge_settings.py:525-566` handles this for hooks; port it.

### Manifest-driven vs. imperative

Ecosystem posture: declarative manifests dominate dotfile managers (dotbot, stow, chezmoi); imperative Python dominates install scripts (pre-commit, pipx, llm, aider).

Declarative wins when: users customize what's deployed; third parties extend the tool; contributors add "deploy this new thing" without changing code.

Imperative wins when: install set is fixed and tool-owner-controlled; deploy logic is tightly coupled to internals; there are many conditional cases (rename, glob+parent-link, copy-once, post-install mutation).

For cortex, imperative is the better fit — see Tradeoffs section.

### `uv tool install -e .` + $HOME writes

- **Editable install supported** (initially missing per GH #5436; added and documented at [docs.astral.sh/uv/concepts/tools/](https://docs.astral.sh/uv/concepts/tools/)).
- **No sandboxing**: uv does not sandbox tool processes. The CLI runs with full user privileges — reads and writes `$HOME` freely.
- **`uv tool upgrade` does NOT touch `$HOME`**: anything cortex wrote to `~/.claude/` or `~/.local/bin/` survives upgrade untouched. **No post-install hook exists** — users must re-run `cortex setup` after a meaningful upgrade.
- **Editable mode**: `-e .` adds a `.pth` file pointing at the repo source. Edits to `cortex_command/` are reflected instantly.

### Python symlink idempotency pattern

Canonical pathlib pattern:

```python
def ensure_symlink(source: Path, target: Path, *, force: bool = False) -> None:
    source = source.resolve()
    if target.is_symlink():
        if target.readlink() == source:
            return  # already correct
        target.unlink()
        target.symlink_to(source)
        return
    if target.exists():
        if not force:
            raise FileExistsError(f"{target} is a real file/dir, not a symlink.")
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(source)
```

**Gotchas**:
- `Path.exists()` follows symlinks — a broken symlink returns `False`. Use `is_symlink()` FIRST.
- `Path.readlink()` (3.9+) is non-resolving; `resolve()` recurses and errors on broken links.
- `symlink_to` has no `exist_ok` / `overwrite` param ([CPython #105900](https://github.com/python/cpython/issues/105900)) — unlink manually first.
- Race: `unlink → symlink_to` isn't atomic. For robust replacement use `os.replace(tmp, target)`.

⚠️ **Adversarial caveat**: do not use this pattern naively. The justfile's `[conflict-file]` branch handles the case where target is a real file/dir and the user wants to preserve it (prompt Y/n before `rm -r`). Agent 2's pattern collapses that into `force=True → rmtree` — which silently deletes user data when the caller forgets to check. Port `classify()` from `merge_settings.py:73-97` verbatim instead of rewriting.

---

## Requirements & Constraints

### Project-level distribution requirements

From `requirements/project.md`:

> **Out of Scope**: Published packages or reusable modules for others — the `cortex` CLI ships as a local editable install (`uv tool install -e .`) for self-hosted use; publishing to PyPI or other registries is out of scope.

> **In Scope**: Global agent configuration (settings, hooks, reference docs). Observability (statusline, notifications, metrics, cost tracking).

> **Architectural Constraints**: File-based state — lifecycle artifacts, backlog items, pipeline state, and session tracking all use plain files. No database or server. May evolve if complexity warrants it, but simplicity is preferred.

> **Quality Attributes**: Graceful partial failure. Maintainability through simplicity. Iterative improvement.

### Permissions architecture constraints

From `requirements/project.md`:

> The global `settings.json` template ships conservative defaults — minimal allow list, comprehensive deny list, sandbox enabled. For sandbox-excluded commands (git, gh, WebFetch), the permission allow/deny list is the sole enforcement layer; keep global allows read-only and let write operations fall through to prompt. The overnight runner bypasses permissions entirely (`--dangerously-skip-permissions`), making sandbox configuration the critical security surface for autonomous execution.

From `claude/rules/sandbox-behaviors.md`:

> The `settings.json` allow list applies across ALL projects on this machine — don't auto-allow write operations that other projects' users may not want.

From `requirements/observability.md`:

> `settings.local.json` arrays replace (not merge with) `settings.json` arrays. The setup recipe must write a self-contained array containing all required sockets.

### Symlink architecture discipline

From project `CLAUDE.md`:

> Files in this repo are symlinked to system locations — always edit the repo copy (the symlink target), never create files at the destination.

> `settings.json` — defaults template (copied on first install, updated via `/setup-merge`). [Explicitly NOT symlinked.]

> New global utilities follow the deploy-bin pattern: logic goes in `bin/`, deployed to `~/.local/bin/` via `just deploy-bin`, skills invoke the binary by name (not a relative path).

### Scope boundaries vs. adjacent tickets

- **114 (CLI skeleton, done)**: argparse scaffold, `[project.scripts]`, stub `setup` subparser. 117 fills in the handler.
- **118 (bootstrap installer, blocked-by 117)**: `curl | sh` script, `git clone ~/.cortex`, `uv tool install -e ~/.cortex`, `cortex upgrade`. Bootstrap calls `cortex setup` at the end. 117 does NOT run the clone or install uv.
- **119 (cortex init)**: per-repo scaffolding of `lifecycle/`, `backlog/`, `retros/`, `requirements/`. 117 owns `~/.claude/` + `~/.local/bin/` (machine-wide), not per-repo dirs.
- **120-122 (plugin tier)**: plugins ship via Claude Code plugin marketplace. 117 retires `just deploy-*` and `/setup-merge` but does NOT install plugins — users run `/plugin install` themselves.
- **124 (migration guide + script)**: owns `docs/migration-to-plugins.md` and the migration script. 117 delivers the new surface; 124 migrates existing users.

### EPILOG constraints from `cortex_command/cli.py`

> The `cortex` command invokes `uv run` against the user's current project, not the tool's own virtualenv. Run it from inside the project whose dependencies you want resolved.

> Adding or changing `[project.scripts]` entries requires reinstalling the tool with `uv tool install -e . --force` so the console scripts are regenerated.

> First-time setup also requires running `uv tool update-shell` once so the uv-managed bin directory is on PATH.

### Deprecation convention — none exists today

Searched `requirements/`, `docs/`, `claude/reference/` for "deprecat", "transitional", "shim", "retire". No hits. Ticket 117 itself sets the precedent: "one-transition-release delegating shim" per its scope text. No formal banner/warning convention exists.

---

## Tradeoffs & Alternatives

### Alt A — Single `cortex setup` with flags (ticket's proposal)

Flags on one subcommand: `--merge-settings`, `--verify-symlinks`, `--with-extras` (and per adversarial: also `--dry-run`, `--yes`, `--prune-orphans`).

**Complexity**: Medium. ~400-600 LoC, primarily porting existing merge_settings.py into `cortex_command/setup/`. Argparse wiring mirrors ticket 114's pattern. No new deps required.

**Maintainability**: Good. "Add a new symlink" = one entry in a Python list literal. All deploy-* logic converges on one dispatch function vs. five parallel justfile recipes with duplicated bash.

**Alignment**: Strong. Matches the existing `cortex_command/cli.py` argparse pattern. Preserves symlink-from-repo discipline. Preserves file-based-state invariant.

**UX**: Fresh install = one command (`cortex setup --merge-settings --with-extras` composes cleanly). `cortex upgrade && cortex setup --verify-symlinks` is a natural health check.

**Recovery**: Re-run safe. Partial failure leaves well-defined state.

### Alt B — Split into subcommands

`cortex setup`, `cortex setup merge-settings`, `cortex setup verify`, `cortex setup extras`.

Composition suffers: "install symlinks AND merge settings AND register extras" = three invocations vs. one. Argparse boilerplate 2× of Alt A. No per-operation args today justify separate namespaces.

### Alt C — Manifest-driven declarative install

A `cortex_command/setup/install.toml` listing `(source, target, kind)` triples.

**Rejected**: today's install has 4+ special cases (notify.sh rename, skill parent-link, settings.json copy-once, settings.local.json jq-merge). A manifest schema that handles these is nearly as complex as Python. Debugging is one hop further removed (error in runtime + manifest entry vs. straight Python traceback). The repo has no other declarative-manifest pattern — cortex ethos is small auditable Python.

### Alt D — Thin delegation to `just`

`cortex setup` shells out to `just setup`. ~5 LoC.

**Rejected**: contradicts the ticket's retirement goal. `just` becomes a permanent runtime dep. Fails scope.

### Alt E — Split settings merge entirely out of `cortex setup`

`cortex setup` = symlinks only; settings merge lives in `cortex settings sync` or similar.

Cleaner separation (Alt E's pitch). Loses one-command fresh install UX. **The opt-in `--merge-settings` flag in Alt A preserves most of Alt E's safety property** (settings merge never runs unless explicitly requested), without sacrificing single-command install.

### Transitional `just setup` handling

Four options (X delete / Y error-out / Z silent delegate / W banner+delegate):

- **X**: premature. The justfile has 945 lines; only ~400 are deploy-*. `overnight-*`, `dashboard`, `backlog-index`, `test*`, `validate-*`, `check-symlinks`, `verify-setup`, `setup-tmux-socket`, `setup-github-pat*` stay.
- **Y**: abrupt. Users on `just setup` muscle memory hit a hard fail.
- **Z**: confusing. Silent aliasing prevents retirement, hides the change.
- **W** (recommended): `just setup` prints `⚠️  'just setup' is deprecated — use 'cortex setup' instead` then `exec cortex setup`. One release, then delete the setup/deploy-* recipes. **Use `exec cortex setup` (literal delegation), not a wrapper that pre-computes paths** — the CLI must own the path logic end-to-end (adversarial caveat).

### Flag-vs-subcommand (Alt A vs B)

Flags win for composition. `cortex setup --merge-settings --with-extras` is natural; the subcommand equivalent requires two invocations or a compound `cortex setup all`. Discoverability roughly a wash.

### Imperative vs. manifest (Alt A vs C)

Adding a new symlink: one line either way. Conditional install (Darwin-only, jq-present-only, worktree-guard): natural in Python, requires a DSL in TOML. Debugging: Python traceback > manifest indirection.

### `--with-extras` — keep or drop

**Keep** (adversarial override of Agent 4's "drop" recommendation). Agent 2 confirmed `claude plugin marketplace add` is a first-class non-interactive CLI command. Bootstrap (118) is a one-command install from `curl | sh`; dropping `--with-extras` means a brand-new user has to run a second command *inside Claude* after install. Shell out with `shutil.which("claude")` guard and graceful degradation if `claude` isn't on PATH yet.

### Shipped `settings.json` template size

**Do NOT trim in this ticket** (adversarial override of Agent 4's "trim" recommendation). Reasons:
1. Scope creep — distribution refactor ≠ content cleanup.
2. Blast radius: existing users got personal-preference keys (`model`, `effortLevel`, `env.teammateMode`, `alwaysThinkingEnabled`) copied on first install; trimming removes them from the repo template but merge is additive — existing installs keep the old values, silently diverging from the template.
3. Trimming requires also fixing the latent `claude/settings.json:361` path inconsistency (`~/cortex-command/lifecycle/sessions/` hardcoded) vs. `$(pwd)/lifecycle/sessions/` in justfile — separate concern.
4. File a separate chore ticket.

### Recommended approach (post-adversarial)

1. **`cortex setup`** (default, no flags) — symlinks only, additive, skip-conflict, idempotent-reinstall semantics. Re-runnable. Worktree guard. ~200 LoC.
2. **`cortex setup --merge-settings`** — after symlinks, run additive deep-merge of shipped `settings.json` into user's. Port `merge_settings.py`'s detect/merge logic into `cortex_command/setup/merge.py` as plain Python (no Claude-session dependency). Preserve mtime guard, symlink guard (`~/.claude/settings.json` as symlink → migrate first), contradiction detection. ~400 LoC.
3. **`cortex setup --verify-symlinks`** — read-only drift check; reports missing/wrong/orphaned symlinks; no writes. ~50 LoC.
4. **`cortex setup --with-extras`** — shell out to `claude plugin marketplace add charleshall888/cortex-command-plugins --scope user` with `shutil.which("claude")` guard; graceful degradation if claude CLI isn't installed yet. ~30 LoC.
5. **`cortex setup --dry-run`** — emit the exact plan (every ln, rm -r, cp, write op) as structured output to stdout. Only mode exercised in most tests. ~20 LoC.
6. **`cortex setup --yes` / `--auto-resolve=skip|backup`** — required for non-TTY contexts to suppress interactive prompts. Without it, non-TTY invocations of a destructive branch (`conflict-file`) abort with a structured error report. ~20 LoC.
7. **`cortex setup --prune-orphans`** — opt-in flag. Enumerates `~/.claude/{hooks,skills,reference,rules}` + `~/.local/bin/` and removes symlinks whose target resolves into a cortex-command clone but isn't in the current inventory. Fixes the live stale-unprefixed-hook drift and future renames. Report-only by default in `--verify-symlinks`; removal requires explicit `--prune-orphans`. ~40 LoC.
8. **Transitional `just setup`**: `exec cortex setup` with a deprecation banner. One release, then delete.
9. **Do NOT trim `claude/settings.json`** in this ticket.
10. **Fix the `claude/settings.json:361` + `justfile:390-408` path inconsistency** — separate concern; defer unless it blocks. Research flags it but this ticket's scope is the CLI, not the template content.

---

## Adversarial Review

Challenges to the synthesis above (findings that override or constrain Agent 4's recommendations):

### 1. Non-interactive CLI silently loses contradiction signal

The `/setup-merge` protocol assumes a Claude session for per-category Y/n prompts, `conflict-file` destructive-path approval, and mtime-guard halt messages. Porting to Python `input()` breaks under: `curl | sh → cortex setup` (stdin not TTY), CI contexts, `--dangerously-skip-permissions` wrapped sessions.

**Mitigation**: spec must require `cortex setup` to detect non-TTY and either refuse destructive operations OR default to `--auto-resolve=skip` with a structured JSON report of skipped items. Bootstrap (118) must run `cortex setup` (no merge) on first install — `--merge-settings` is a second TTY-required step.

### 2. Trim-the-template breaks latent state

Agent 4 recommended trimming `claude/settings.json` to a minimal baseline. This is out of scope for this ticket. Existing users who got `model: opus[1m]` + personal scalars copied on first install still have them; trimming the repo template doesn't remove them (merge is additive). The `claude/settings.json:361` hardcoded `~/cortex-command/lifecycle/sessions/` vs. `justfile`'s `$(pwd)`-derived path is a latent bug that trimming would expose but not fix.

**Mitigation**: separate chore ticket for template cleanup. This ticket keeps the template as-is.

### 3. Repo root resolution fragility (editable install + worktree)

`uv tool install -e <clone>` + running `cortex setup` from a different clone → `__file__`-derived resolution points at the installation clone (stale). If the editable install was from a worktree, symlinks point into the worktree; `git worktree remove` breaks every symlink.

**Mitigation**: spec must pin order: `CORTEX_COMMAND_ROOT` > `git rev-parse --show-toplevel` of CWD (with worktree-guard) > `__file__`. Reject worktree paths. `--verify-symlinks` should detect symlinks pointing into a path in `git worktree list --porcelain` output and warn.

### 4. Dropping `--with-extras` breaks bootstrap-new-user UX

Agent 4 recommended dropping. Adversarial and Agent 2 override: `claude plugin marketplace add` is a first-class non-interactive CLI. Bootstrap (118) is a one-command install; user hasn't opened Claude. Dropping the flag = user has to open Claude, run an extra command.

**Mitigation**: keep `--with-extras`. Shell out with `shutil.which("claude")` guard. Graceful degrade if `claude` not on PATH.

### 5. `just setup → cortex setup` delegation must be literal

Agent 4's option W works only if delegation is `exec cortex setup "$@"`. A wrapper that pre-computes `$(pwd)`-based paths, calls `jq`, or rewrites the `CONFLICTS_FILE` pattern will lose behavior (e.g., the settings.local.json allowWrite path-injection). The CLI must own path logic end-to-end.

**Mitigation**: `just setup` = banner + `exec cortex setup`.

### 6. `cortex upgrade` + `--verify-symlinks` flag-name mismatch

Ticket 118 spec for `cortex upgrade = git -C ~/.cortex pull && cortex setup --verify-symlinks`. If `--verify-symlinks` is read-only, it won't install new symlinks introduced by the pull. If it's verify-and-fix, the name lies.

**Mitigation**: rename to `--dry-run` (read-only plan generation) and make default `cortex setup` idempotent-reinstall. `cortex upgrade` runs `cortex setup` (not `--dry-run`). Update 118's spec before 117 lands.

### 7. No cleanup of 15+ stale unprefixed hook symlinks

Live drift: `~/.claude/hooks/scan-lifecycle.sh` (unprefixed) exists alongside `cortex-scan-lifecycle.sh`. Neither `check-symlinks` nor `merge_settings.py` surfaces these orphans (glob is `cortex-*`).

**Mitigation**: `--verify-symlinks` reports orphans (symlinks pointing into the cortex-command repo but not in current inventory). `--prune-orphans` (opt-in) removes them. Report-only default.

### 8. Test coverage gap

No existing CLI tests in ticket 114. `merge_settings.py` (1083 LoC) has zero tests in the repo. Moving destructive operations to Python without tests is unsafe.

**Mitigation**: `--dry-run` flag emits structured plan; primary test surface is plan generation. Integration tests with `HOME=tmpdir`. Unit tests for `classify()`, detect/merge helpers. Golden-file test for plan output.

### 9. Python `symlink_to` must use `classify()` three-branch logic

Agent 2's canonical pattern collapses three branches (symlink replace / real dir error / real file prompt) into one `force=True → rmtree`. Naïve port will silently nuke user-authored `~/.claude/skills/<mine>/` directories.

**Mitigation**: port `merge_settings.py:73-97 classify()` verbatim. Preserve the three-branch behavior. Destructive paths gated behind explicit opt-in (not silent default).

### 10. Shell-out security — `shell=False`, argv list, PATH resolution

Shelling out to `claude plugin marketplace add`: use `subprocess.run(list_argv, check=False, shell=False)`. Resolve `claude` via `shutil.which("claude")` — if absent, printable-copy-paste fallback, exit 0. Never interpolate untrusted data into argv strings. Pin marketplace name in code with no env-var override. Document supply-chain risk in `--with-extras`'s `--help` text.

### Assumptions flagged

- **Nothing deletes `.claude/skills/setup-merge/`**: the retired skill dir is not in the repo's `skills/` walker, so the source walk doesn't see it. Unless 117 or 124 explicitly removes it, it orphans forever.
- **`~/.claude/get-api-key.sh` stub**: `merge_settings.py:311-331` checks for this. If the stub isn't deployed but detection still asks about it, dead code.
- **Plugin migration path (ticket 124) may reuse 117's `classify()`/detect functions**: export them in a stable module path, not inline in the CLI file.

### Security concerns

1. **`shell=True` risk** in the `claude plugin marketplace add` shell-out. Mandate list-argv.
2. **`settings.local.json` mtime unguarded**: `cortex setup` + a live Claude session writing `_globalPermissionsHash` via `cortex-sync-permissions.py` could collide. Add mtime guard for both settings files, not just `settings.json`.
3. **Destructive `rm -r` in `conflict-file` branch**: comment says "not `rm -rf` — the deny rules block it." Outside Claude context, deny rules don't apply. `shutil.rmtree()` has no deny protection. Gate behind explicit opt-in.
4. **Marketplace source hardcoded to `charleshall888/cortex-command-plugins`**: single point of supply-chain concern. Document risk in `--with-extras`'s `--help`.

---

## Open Questions

Resolved during research (inline answers):

1. **Q: What does today's `just setup` do per-symlink?**
   A: Explicit 5-state classification (new / update / conflict-broken / conflict-wrong-target / conflict-file). `ln -sf` only invoked for new/update; conflicts appended to `$CONFLICTS_FILE` and surfaced to user to resolve via `/setup-merge`. Nothing clobbered by `just setup`. `setup-force` is the clobber path.

2. **Q: `/setup-merge` algorithm?**
   A: Per-category Y/n approval → additive merge. 8 categories. mtime guard. Contradiction detection (forward + reverse via fnmatch). Atomic write via tempfile + fsync + os.replace.

3. **Q: Where's the marketplace registration API?**
   A: `claude plugin marketplace add <source> --scope user` non-interactive CLI. State: `~/.claude/plugins/known_marketplaces.json`.

4. **Q: apiKeyHelper state?**
   A: Removed from `claude/settings.json` (shareable-install #004). Detection code in `merge_settings.py` is dead.

5. **Q: What does `cortex-command-plugins` marketplace scaffolding look like?**
   A: Separate repo at `~/Workspaces/cortex-command-plugins/` with `.claude-plugin/marketplace.json` listing 4 plugins. `--with-extras` adds this marketplace to the user's `known_marketplaces.json`.

Deferred to spec phase (require user or design decision):

6. **Q: Default `cortex setup` semantics — idempotent-reinstall or read-only verify?**
   Deferred: affects `--verify-symlinks` flag name and `cortex upgrade` design. Adversarial recommends `cortex setup` = idempotent-reinstall, `--dry-run` = read-only.

7. **Q: Non-TTY behavior — require `--yes` / `--auto-resolve=skip`?**
   Deferred: tradeoff between "safe-by-default refusal" and "works in bootstrap pipeline." Adversarial recommends: non-TTY + destructive branch → abort with structured error unless `--yes` or `--auto-resolve` passed.

8. **Q: Repo root resolution order?**
   Deferred: user should confirm `CORTEX_COMMAND_ROOT > git rev-parse > __file__` ordering, and whether worktree guard rejects or warns.

9. **Q: `claude/settings.json` trim in this ticket?**
   Deferred: will be resolved in Spec by asking the user. Adversarial recommends OUT of scope; Agent 4 recommended IN scope.

10. **Q: `--with-extras` in this ticket?**
    Deferred: will be resolved in Spec by asking the user. Adversarial + Agent 2 recommend KEEP; Agent 4 recommended DROP.

11. **Q: What deletes `.claude/skills/setup-merge/`?**
    Deferred: spec must decide — does `cortex setup` detect and remove the symlink (with confirmation) on first run, does 124's migration handle it, or is it manual?

12. **Q: Orphan cleanup via `--prune-orphans` or not?**
    Deferred: spec must decide — is orphan pruning in scope for this ticket (fixes 15+ stale unprefixed hook symlinks from pre-DR-3 rename), or a separate ticket? Adversarial recommends in scope.

13. **Q: Transitional `just setup` = exec delegation vs. wrapper vs. immediate delete?**
    Deferred: will be resolved in Spec by asking the user. Adversarial + Tradeoffs recommend option W (banner + `exec cortex setup`) for one release then delete.

14. **Q: Fix `claude/settings.json:361` path inconsistency in this ticket?**
    Deferred: will be resolved in Spec — hardcoded `~/cortex-command/lifecycle/sessions/` vs. `$(pwd)/lifecycle/sessions/` in justfile. Out-of-scope recommendation aligns with "don't conflate distribution refactor with content cleanup" but the inconsistency surfaces during this ticket's work.

15. **Q: Test surface — `--dry-run` + tempdir-HOME integration test + golden-file for plan output?**
    Deferred: spec must define minimum viable test plan. Research recommends all three.
