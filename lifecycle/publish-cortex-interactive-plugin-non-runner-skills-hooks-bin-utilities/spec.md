# Specification: publish-cortex-interactive-plugin-non-runner-skills-hooks-bin-utilities

> Epic context: `research/overnight-layer-distribution/research.md` (DR-2 — two-plugin split at runner boundary; this is the non-runner plugin).

## Problem Statement

Post-117, cortex-command has no distribution mechanism. The pre-117 `just deploy-*` symlink architecture is retired; the CLI tier (#114, #117) deploys `~/.claude/{notify.sh,statusline.sh,rules,reference}` and installs the runner, but skills and bin utilities for the interactive workflow surface need a plugin. Ticket #120 publishes the `cortex-interactive` Claude Code plugin — a self-contained bundle of the 13 non-runner skills plus `critical-review`, the seven bin utilities used by those skills (four existing + three new shims), and a namespace migration across the repo — so users can install interactive cortex workflows via `/plugin install cortex-interactive@<source>` without taking on the overnight runner. This is the first of two plugins in epic 113's plugin tier; `cortex-overnight-integration` (#121) ships alongside for users who also want the runner.

## Requirements

All 17 requirements below are **must-have** for #120 to ship, with two candidate should-have demotions if scope pressure requires: **R13** (`just build-plugin` idempotency) is a developer-ergonomics convenience — the plugin still works if the plugin directory is maintained manually, so this could drop to should-have without blocking release; and **R14** (plugin-install smoke test) is good-practice verification but not strictly blocking if all 17 mechanical acceptance checks already pass. All other requirements (R1–R12, R15–R17) are hard gates. Won't-do items are enumerated in the Non-Requirements section below via explicit ticket references (#121, #122, #123, #124) rather than repeated here.

1. **Plugin manifest exists** at `plugins/cortex-interactive/.claude-plugin/plugin.json` with `name: "cortex-interactive"` and minimal metadata (name, description, author); no `version` field (git-SHA versioning, per research).
   - Acceptance: `jq -r '.name' plugins/cortex-interactive/.claude-plugin/plugin.json` = `cortex-interactive`, pass if output matches.

2. **14 skills shipped** at `plugins/cortex-interactive/skills/<name>/SKILL.md` with complete `references/` subdirectories preserved: `commit`, `pr`, `lifecycle`, `backlog`, `requirements`, `research`, `discovery`, `refine`, `retro`, `dev`, `fresh`, `diagnose`, `evolve`, `critical-review`.
   - Acceptance: `ls plugins/cortex-interactive/skills/ | sort` = the 14 names above; `find plugins/cortex-interactive/skills -name SKILL.md | wc -l` = 14.

3. **`critical-review` remediated**: the unguarded `from cortex_command.common import atomic_write` at `skills/critical-review/SKILL.md:255` is replaced by an inline atomic-write implementation (~6 lines) inside the same `python3 -c` snippet, so critical-review runs standalone without the CLI tier.
   - Acceptance: `grep -c "from cortex_command.common import atomic_write" plugins/cortex-interactive/skills/critical-review/SKILL.md` = 0; `grep -c "tempfile\|os.replace" plugins/cortex-interactive/skills/critical-review/SKILL.md` ≥ 1 (the inlined implementation).

4. **Cross-skill `${CLAUDE_SKILL_DIR}/../lifecycle/references/` traversal in `refine` is eliminated** by duplicating the referenced content (`clarify.md`, `specify.md` sections refine reads) into files under `skills/refine/references/` at the **top-level source tree** (from which `just build-plugin` copies into `plugins/cortex-interactive/skills/refine/references/`) and rewriting the four read-sites in the top-level `skills/refine/SKILL.md` (lines 26, 60, 81, 130) to reference the co-located copies.
   - Acceptance: `grep -c 'CLAUDE_SKILL_DIR' skills/refine/SKILL.md` = 0 AND `grep -c 'CLAUDE_SKILL_DIR' plugins/cortex-interactive/skills/refine/SKILL.md` = 0; `test -f skills/refine/references/clarify.md && test -f skills/refine/references/specify.md`.

5. **Hardcoded `~/.claude/skills/...` paths are rewritten** in the five reference files that use them: `skills/lifecycle/references/clarify.md:49`, `skills/lifecycle/references/plan.md:237`, `skills/lifecycle/references/research.md:187`, `skills/lifecycle/references/specify.md:145`, `skills/discovery/references/research.md:130`. Each path is rewritten to be plugin-layout-aware — replace `~/.claude/skills/<skill>/references/<file>` with `${CLAUDE_PLUGIN_ROOT}/skills/<skill>/references/<file>` in hook/MCP/JSON contexts where substitution is reliable, and with co-located relative references (`references/<file>`) in SKILL.md prose where #9354 makes substitution unreliable.
   - Acceptance: `grep -rn '~/.claude/skills' plugins/cortex-interactive/skills/` produces 0 matches.

6. **`/evolve` repo-root resolution reworked** so it no longer depends on a `readlink`-resolvable symlink at its own SKILL.md path. Replace `readlink`-based derivation (lines 54–58) with `$PWD`-based resolution or a user-confirmed repo-root marker file (e.g., presence of `backlog/` or `.git/`).
   - Acceptance: `grep -c 'readlink' plugins/cortex-interactive/skills/evolve/SKILL.md` = 0. Interactive/session-dependent: a manual test invocation of `/cortex:evolve` from a cortex-command working directory verifies repo-root resolution end-to-end — this exercises an installed-plugin slash command inside a live Claude Code session, which cannot be scripted as a headless command.

7. **Seven bin utilities shipped** at `plugins/cortex-interactive/bin/` with `cortex-` prefix: `cortex-jcc`, `cortex-count-tokens`, `cortex-audit-doc`, `cortex-git-sync-rebase`, `cortex-update-item`, `cortex-create-backlog-item`, `cortex-generate-backlog-index`. Every file is `chmod +x` with a valid shebang.
   - Acceptance: `ls plugins/cortex-interactive/bin/ | grep -c '^cortex-'` = 7; `find plugins/cortex-interactive/bin/ -type f ! -perm -u+x | wc -l` = 0.

8. **Three new bin shims are functional**: `cortex-update-item`, `cortex-create-backlog-item`, `cortex-generate-backlog-index` are shell scripts that resolve their Python sources in this order: (a) probe `python3 -c "import cortex_command.backlog.<module>" 2>/dev/null` — if exit 0, invoke via the packaged module path; (b) else if `CORTEX_COMMAND_ROOT` is set AND `$CORTEX_COMMAND_ROOT/pyproject.toml` contains `name = "cortex-command"` (validity predicate, enforced by a grep in the shim), invoke `python3 "$CORTEX_COMMAND_ROOT/backlog/<module>.py"`; (c) else emit `"cortex-command CLI not found — run 'cortex setup' or point CORTEX_COMMAND_ROOT at a cortex-command checkout"` to stderr and exit 2. The probe in (a) explicitly tests the packaged form (`cortex_command.backlog.<module>`) rather than the ambient namespace-package form (`backlog.<module>`) to avoid shadow-imports of the top-level `backlog/` user-data directory that resolves as a PEP 420 namespace package today.
   - Acceptance (non-destructive probes only — do not invoke `--help` on these scripts because `generate_index.py` has destructive side effects via `main()`):
     - `env -u CORTEX_COMMAND_ROOT cortex-update-item` (no args, no env) exits with code 2 and stderr contains the documented "cortex-command CLI not found" message.
     - `CORTEX_COMMAND_ROOT=/tmp/does-not-exist cortex-update-item` exits with code 2 and the documented error (invalid-root path fails the validity predicate).
     - `CORTEX_COMMAND_ROOT=$(pwd) cortex-update-item nonexistent-slug` (from a cortex-command checkout) exits non-zero with "Item not found: nonexistent-slug" on stderr (confirms delegation reached `backlog/update_item.py`).
     - The shim's probe in branch (a) MUST literally be `python3 -c "import cortex_command.backlog.<module>"` — not `python3 -m <form>` — verified by `grep -F "import cortex_command.backlog" plugins/cortex-interactive/bin/cortex-update-item` producing at least one match.

9. **Bin call sites in shipped skills are rewritten** from bare names to `cortex-` prefixed. Affected skills include (but are not limited to) `backlog`, `lifecycle`, and any skill that invokes `update-item`, `jcc`, or the other six utilities by name.
   - Acceptance: `grep -rnE '(^| |`|\()(update-item|create-backlog-item|generate-backlog-index|jcc|count-tokens|audit-doc|git-sync-rebase)( |$|"|`|\))' plugins/cortex-interactive/skills/` = 0 matches (all replaced by the `cortex-` prefixed form).

10. **Namespace migration — Part A (plugin-shipped files)** rewrites every bare `/commit`, `/pr`, `/lifecycle`, `/backlog`, `/requirements`, `/research`, `/discovery`, `/refine`, `/retro`, `/dev`, `/fresh`, `/diagnose`, `/evolve`, `/critical-review` reference to the `/cortex:*` form. The rewrite happens at the **top-level source tree** (`skills/<shipped-skill>/` for each of the 14 shipped skills) FIRST; `just build-plugin` then regenerates `plugins/cortex-interactive/skills/` from the migrated source. This ordering prevents the drift hole where plugin-tree edits get silently overwritten by the next rebuild.
    - Acceptance: Both of the following grep commands produce 0 matches — (i) against the top-level source: `grep -rnE '(^| |\x60|\()(\/commit|\/pr|\/lifecycle|\/backlog|\/requirements|\/research|\/discovery|\/refine|\/retro|\/dev|\/fresh|\/diagnose|\/evolve|\/critical-review)( |$|"|\x60|\))' skills/commit/ skills/pr/ skills/lifecycle/ skills/backlog/ skills/requirements/ skills/research/ skills/discovery/ skills/refine/ skills/retro/ skills/dev/ skills/fresh/ skills/diagnose/ skills/evolve/ skills/critical-review/` = 0; (ii) against the plugin build-output: same regex against `plugins/cortex-interactive/skills/` = 0.

11. **Namespace migration — Part B (non-shipped files)** rewrites bare `/skill-name` references in all files outside `plugins/cortex-interactive/` and outside `skills/` (which is Part A's domain) that are "live" documentation: `docs/`, `CLAUDE.md`, `README.md`, `justfile`, `pyproject.toml`, `hooks/*.sh`, `claude/hooks/*.sh`, `tests/`. The tool skips: `retros/`, `lifecycle/sessions/`, `lifecycle/*/events.log`, `.claude/worktrees/`, `research/`, any file under `backlog/` (historical tickets), and any path matching URL patterns. URL-skip patterns are explicit: `://` anywhere, `github.com/`, `gitlab.com/`, `bitbucket.org/`, relative path segments matching `/<skill-name>/` (e.g. `./commit/hook.sh`, `src/pr/util.py`). Word-boundary regex is `(^| |\x60|\(|\[|,|;|:)/<skill-name>( |$|"|\x60|\)|\]|,|;|:)` — explicitly including comma, semicolon, colon, square bracket as delimiters beyond whitespace and backticks.
    - Acceptance, all must pass:
      - (a) Completeness across all 14 names × all 8 target categories. Run this shell loop and assert zero total matches:
        ```bash
        for skill in commit pr lifecycle backlog requirements research discovery refine retro dev fresh diagnose evolve critical-review; do
          grep -rnE "(^| |\`|\(|\[|,|;|:)/$skill( |\$|\"|\`|\)|\]|,|;|:)" docs/ CLAUDE.md README.md justfile pyproject.toml hooks/ claude/hooks/ tests/ 2>/dev/null
        done | wc -l
        # expected: 0
        ```
      - (b) Tool idempotence: a second invocation of the scoped rewrite tool produces zero additional changes (`git diff --quiet` exits 0 after the second run).
      - (c) Skip-list enforcement verified by seeded fixture: a test fixture with a known-good bare-name inside `retros/`, `research/`, `backlog/`, `lifecycle/sessions/`, `.claude/worktrees/` survives the rewrite untouched (content bytes identical post-run).
      - (d) Positive test via seeded fixture: a test fixture with a known-bad bare-name inside a `docs/` subdirectory IS rewritten to the `/cortex:*` form (proves the tool actually rewrites what it should, not just that it skips what it should).
      - The self-certification "review pass before commit" clause from the prior spec is removed — acceptance (a)-(d) together form the enforcement.

12. **`morning-review` is explicitly NOT shipped in this plugin.** Its `$CORTEX_COMMAND_ROOT` coupling and overnight-report semantics make it a natural citizen of #121.
    - Acceptance: `test ! -d plugins/cortex-interactive/skills/morning-review`; AFTER ticket 120 implementation lands, the conditional phrasing in `backlog/121-cortex-overnight-integration-plugin.md` must be rewritten to a committed inclusion — specifically, `grep -cE 'if the codebase check.*morning-review|morning-review.*if.*import' backlog/121-cortex-overnight-integration-plugin.md` = 0 (no conditional phrasing left) AND `grep -cE '(ships|includes|includes the following skills).*morning-review|morning-review.*(ships|included)' backlog/121-cortex-overnight-integration-plugin.md` ≥ 1 (committed inclusion). The bare-substring count is insufficient because the pre-existing conditional line already satisfies a substring-only check.

13. **Skills source of truth remains at top-level `skills/<name>/`**; `plugins/cortex-interactive/skills/` is build-output from a `just build-plugin` (or equivalent) recipe that copies files from `skills/` and `bin/` into the plugin directory preserving file mode bits (so `chmod +x` is maintained across builds). The plugin directory is committed to the repo (so `/plugin install <git-url>` works), but `just build-plugin` regenerates it from sources.
    - Acceptance: `just --list` shows `build-plugin`; running it from a clean repository state produces `git status --porcelain plugins/cortex-interactive/` = empty output (captures both content changes AND file-mode changes, including `chmod +x` preservation); running it a second time without editing sources also produces empty `git status --porcelain` (idempotent across consecutive runs).

14. **Plugin enables successfully** from a test session via `/plugin install cortex-interactive@<local-path>` and exposes `/cortex:*` commands; a smoke test invocation of `/cortex:commit` (or another low-side-effect skill) runs without `ModuleNotFoundError` or `$CORTEX_COMMAND_ROOT` unset errors in a plugin-only install (no CLI tier symlinks present).
    - Acceptance: Interactive/session-dependent: manual smoke test per the implementation checklist.

15. **No `settings.json` files** or cortex-specific permission blocks are shipped inside the plugin.
    - Acceptance: `find plugins/cortex-interactive/ -name 'settings*.json'` = 0 results.

16. **Dual-source drift enforcement** ships as part of this ticket: a pre-commit hook (in `.githooks/` or wired via `core.hooksPath`) and/or a CI job runs `just build-plugin && git diff --quiet plugins/cortex-interactive/` and fails the commit/build on any drift between top-level sources and the committed plugin build-output. Choice between pre-commit hook vs. CI job vs. both is Plan-phase.
    - Acceptance: (a) a pre-commit hook script OR a CI workflow file exists that, when invoked with clean (just-built) sources, exits 0; (b) the same hook/CI, when invoked after editing `skills/commit/SKILL.md` without running `just build-plugin`, exits non-zero with a message identifying the drifted files; verify both paths with a scripted test that seeds the drift deliberately and asserts the failure mode.

17. **`cortex-validate-commit.sh` ships as a plugin hook** so plugin-only users invoking `/cortex:commit` in their own repos retain commit-message validation. Plugin declares a `hooks/hooks.json` manifest that registers `cortex-validate-commit.sh` on the appropriate event (`UserPromptSubmit` for `/cortex:commit` invocations, or the PreToolUse event that fires before `git commit`, per the hook's current trigger shape). Other project-scope hooks (`cortex-skill-edit-advisor.sh`) remain excluded — they have no meaning outside the cortex-command checkout itself.
    - Acceptance: `test -f plugins/cortex-interactive/hooks/hooks.json`; `jq -r '.hooks | keys[]' plugins/cortex-interactive/hooks/hooks.json` includes at least one event entry; `jq -r '.hooks | values[] | .[] | .hooks[] | .command' plugins/cortex-interactive/hooks/hooks.json | grep -c 'cortex-validate-commit.sh'` ≥ 1; `test -x plugins/cortex-interactive/hooks/cortex-validate-commit.sh`; the hook script at that path references `${CLAUDE_PLUGIN_ROOT}` and has no repo-absolute paths.

## Non-Requirements

- **Plugin marketplace manifest** (`.claude-plugin/marketplace.json` at repo root) — ticket #122.
- **`requirements/project.md` DR-8 update** (removing "Published packages" Out-of-Scope line; adding plugin-distribution In-Scope line) — ticket #122.
- **Migration guide + script for existing symlinked users** — ticket #124.
- **Lifecycle autonomous-worktree graceful-degrade** (hiding the "Implement in autonomous worktree" option when runner CLI is absent) — ticket #123.
- **Overnight skill, runner-required hooks, and `cortex-overnight-integration` plugin** — ticket #121. This plugin explicitly does NOT ship `overnight`, `morning-review`, `cortex-scan-lifecycle.sh`, `cortex-skill-edit-advisor.sh`, `cortex-cleanup-session.sh`, `cortex-tool-failure-tracker.sh`, `cortex-permission-audit-log.sh`, `cortex-notify.sh`. (Note: `cortex-validate-commit.sh` IS shipped here per R17 — commit validation is a universal need for plugin-only users, not a runner-specific concern.)
- **`cortex-output-filter.sh` hook in this plugin.** Output filtering is a cross-project Claude Code productivity feature, not cortex-specific — it belongs in machine-config (user's `~/.claude/hooks/`) where it applies to all projects, not only when the plugin is active. (Contrast with `cortex-validate-commit.sh`, which IS shipped here because it validates the `/cortex:commit` skill specifically — a plugin-scoped concern.)
- **`cortex-skill-edit-advisor.sh` hook in this plugin.** Advises on edits to cortex-command's own `skills/` directory layout — has no meaning when invoked in a user's own repo outside cortex-command. Stays project-scope.
- **`${CLAUDE_PLUGIN_DATA}` declaration** in plugin.json or speculative state directory. No skill or bin utility currently needs persistent per-update state. If a future utility does, it is added when the use case appears.
- **`cortex doctor` preflight** for bin PATH collision detection — out of scope; a future optional ticket.
- **Full Python repackaging of `backlog/*.py` into `cortex_command.backlog.*`** — deferred. Shim resolution order (see R8) is forward-compatible if a future ticket does this.
- **Bin collision opt-out mechanism** — upstream Claude Code does not offer one; defensive `cortex-` prefix is the only mitigation available.

## Edge Cases

- **Plugin-only install without CLI tier.** User runs `/plugin install cortex-interactive@...` but has not installed the cortex CLI (`uv tool install -e .`) or run `cortex setup`. Skills that invoke cortex-prefixed bin shims hit the R8 fallback: a clean stderr message identifying the missing CLI tier. Critical-review runs standalone (after R3). No cryptic Python tracebacks. The graceful-degradation mechanism for lifecycle's "Implement in autonomous worktree" is #123's responsibility — this ticket satisfies the precondition (no crashes) but does not implement the menu-hiding.

- **Plugin cache wipe on update.** `${CLAUDE_PLUGIN_ROOT}` contents are replaced by upstream Claude Code on every plugin update. Bins and skills never write state to this directory — all state continues to live in the user's working repository (`lifecycle/`, `backlog/`, `retros/`, `requirements/`). Plugin updates are transparent to user state.

- **Plugin PATH collision.** Another plugin installs a same-named bin. The `cortex-` prefix makes syntactic collision impossible with anything not also using that prefix. Any other plugin that also uses `cortex-` namespace is assumed cooperative (Claude Code provides no ordering guarantee — users who install competing `cortex-` plugins are responsible for resolving).

- **`${CLAUDE_SKILL_DIR}` and `${CLAUDE_PLUGIN_ROOT}` substitution failures (upstream #9354).** Plugin SKILL.md bodies avoid relying on substitution entirely: cross-skill content is duplicated into the invoking skill's `references/` directory (R4) or replaced with co-located relative paths (R5). If upstream fixes the substitution, the plugin still works — the changes degrade gracefully in both directions.

- **Namespace migration false matches.** Rewrite tool (R11) uses regex with explicit word boundaries (`(^| |\x60|\()/skill( |$|"|\x60|\))`) and an explicit skill-name allowlist (only the 14 shipped skills). It skips: `retros/`, `lifecycle/sessions/`, `.claude/worktrees/`, `research/`, URL patterns (`://`), and file extensions that aren't markdown, shell, Python, or JSON. A manual review pass catches anything the regex misses before commit.

- **`/cortex:evolve` in a non-cortex working directory.** After R6, evolve resolves repo root via `$PWD` or marker-file detection. If the user invokes `/cortex:evolve` from a directory without `backlog/` or `.git/`, the skill emits a clear error naming the missing marker rather than silently operating on an unexpected tree.

- **`uv run --script` cold cache on first bin invocation.** `cortex-count-tokens` and `cortex-audit-doc` use `uv run --script`; first invocation after plugin install cold-resolves the `anthropic` SDK from the internet, adding multi-second latency. `UV_CACHE_DIR` defaults to `~/.cache/uv` (user-global), so the cache survives plugin updates — subsequent invocations are fast.

- **Committed plugin dir vs. `just build-plugin` regeneration drift.** Developers edit a skill's top-level `SKILL.md` but forget to rebuild. Mitigation: the build recipe is idempotent; a pre-commit hook or CI check can run `just build-plugin && git diff --exit-code plugins/cortex-interactive/` to catch drift. The hook itself is outside this ticket; the idempotent build recipe is in scope (R13).

## Changes to Existing Behavior

- **ADDED** — 14 namespaced slash commands available after plugin install: `/cortex:commit`, `/cortex:pr`, `/cortex:lifecycle`, `/cortex:backlog`, `/cortex:requirements`, `/cortex:research`, `/cortex:discovery`, `/cortex:refine`, `/cortex:retro`, `/cortex:dev`, `/cortex:fresh`, `/cortex:diagnose`, `/cortex:evolve`, `/cortex:critical-review`.
- **REMOVED** — bare `/commit`, `/pr`, `/lifecycle`, `/backlog`, `/requirements`, `/research`, `/discovery`, `/refine`, `/retro`, `/dev`, `/fresh`, `/diagnose`, `/evolve`, `/critical-review` no longer resolve in plugin-installed environments. Users must update muscle memory; historical references in `retros/` and `research/` remain for context.
- **MODIFIED** — seven bin utilities renamed with `cortex-` prefix: `jcc` → `cortex-jcc`, `count-tokens` → `cortex-count-tokens`, `audit-doc` → `cortex-audit-doc`, `git-sync-rebase.sh` → `cortex-git-sync-rebase`, plus three new shims (`cortex-update-item`, `cortex-create-backlog-item`, `cortex-generate-backlog-index`). All skill call sites updated.
- **MODIFIED** — `critical-review` inlines atomic-write (no longer imports `cortex_command.common`).
- **MODIFIED** — `refine`, `lifecycle/references/*`, `discovery/references/research.md`, `evolve` no longer rely on `~/.claude/skills/...` hardcoded paths or `${CLAUDE_SKILL_DIR}/../` cross-skill traversal; content is relocated or replaced with co-located relative references.
- **MODIFIED** — documentation and scripts (`docs/`, `CLAUDE.md`, `README.md`, `justfile`, `pyproject.toml`, live `hooks/*.sh`, `tests/`) reflect `/cortex:*` command forms.
- **ADDED** — `just build-plugin` recipe that regenerates `plugins/cortex-interactive/` from `skills/` and `bin/` sources.
- **ADDED** — `plugins/cortex-interactive/hooks/hooks.json` manifest registering `cortex-validate-commit.sh` as a plugin-scoped hook, so plugin-only users invoking `/cortex:commit` in their own repos retain commit-message validation (R17).
- **ADDED** — pre-commit hook (or CI job) that enforces the dual-source invariant by running `just build-plugin && git diff --quiet plugins/cortex-interactive/` (R16).
- **REMOVED** — `morning-review` skill is excluded from this plugin and will ship in #121's `cortex-overnight-integration`. The top-level `skills/morning-review/` directory remains in the repo (source of truth for #121 to consume).

## Technical Constraints

- Plugin commands are always namespaced as `/plugin-name:command-name` (upstream issue #15882 closed by docs correction); unprefixed commands from plugins are not possible.
- `${CLAUDE_PLUGIN_ROOT}` substitution in SKILL.md markdown bodies is unreliable per open upstream issue #9354 — plugin skills avoid relying on it; JSON configs (hook/MCP/LSP/monitor) may use it freely.
- `${CLAUDE_PLUGIN_ROOT}` contents are wiped on every plugin update; persistent state must live in user repo files or `${CLAUDE_PLUGIN_DATA}`.
- Plugin cache copy does not preserve symlinks to files outside the plugin directory — source-of-truth duplication must happen at build time, not via filesystem symlinks. (Informs R13's build-recipe design.)
- Plugins cannot distribute `~/.claude/settings.json` permission blocks; plugin `settings.json` supports only `agent` and `subagentStatusLine` keys. (Informs R15.)
- Bin/ PATH injection has no documented ordering/conflict rules; `cortex-` prefix is the only defensive pattern. (Informs R7.)
- Upstream #9444 (plugin dependency sharing) remains open; `cortex-interactive` is self-contained — no cross-plugin code sharing. Any shared-code need is resolved by duplication or the CLI tier's `cortex_command` Python package.
- Bash PATH auto-injection of `bin/` requires executables + shebangs — standard shell conventions.
- The plugin depends on the CLI tier (#114, #117) having run `cortex setup` for shared infrastructure (`~/.claude/{notify.sh,statusline.sh,rules,reference}`), but `cortex-interactive` itself remains functional for commit, pr, lifecycle, backlog, requirements, research, discovery, refine, retro, dev, fresh, diagnose, evolve, and critical-review *even without* the CLI tier — the fallback path in R8 makes bin-invocation failure clean rather than cryptic.

## Open Decisions

None. All scope-shaping decisions were resolved during the structured interview; implementation-level details (the exact shell syntax of the shim fallback logic, the exact regex of the Part-B rewrite tool, the specific marker-file logic for evolve's repo-root resolution) are Plan-phase concerns and are intentionally left for the implementer.
