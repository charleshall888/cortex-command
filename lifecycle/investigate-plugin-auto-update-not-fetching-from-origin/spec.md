# Specification: investigate-plugin-auto-update-not-fetching-from-origin

## Problem Statement

The cortex-core plugin cache fell ~30 commits behind `origin/main` despite `autoUpdate: true` in `~/.claude/settings.json` and `~/.claude/plugins/known_marketplaces.json`. Explicit `/plugin update cortex-core` updated `lastUpdated` but did not advance the marketplace clone's `origin/main` ref. This silently undermines every iteration on skill prose, hooks, and bin scripts shipped via the cortex-core plugin: changes that land on main are invisible to anyone whose marketplace clone has not been manually fetched. The fix surface is twofold — first, definitively determine whether `/plugin update`/`autoUpdate` is silently failing to `git fetch` (contradicting docs) or whether a configuration gap explains the staleness; second, ship a one-line refresh helper (`cortex-refresh-plugins`) that subscribers can run to force the marketplace clone to advance, regardless of upstream behavior. Beneficiaries: every contributor who edits skill/hook/bin content and expects their changes to be exercised on next session.

## Phases

- **Phase 1: Empirical verification** — Run the 6 deferred experiments from research.md against the current environment and record observations.
- **Phase 2: Ship the refresh helper + docs** — Implement `cortex-refresh-plugins` (canonical + plugin mirror), update `docs/setup.md`, and document the empirical findings + classification in lifecycle/.

## Requirements

1. **Read and record the marketplace `autoUpdate` field**: Inspect `~/.claude/plugins/known_marketplaces.json` and record the value of `marketplaces["cortex-command"].autoUpdate` (or analogous nested path) along with the value of `autoUpdate` in `~/.claude/settings.json`. Acceptance: `lifecycle/{feature}/findings.md` contains a section "## Q1: autoUpdate values" with both raw values quoted and a one-sentence note on whether the third-party-default-false hypothesis explains the staleness. `grep -c "## Q1: autoUpdate values" lifecycle/investigate-plugin-auto-update-not-fetching-from-origin/findings.md` = 1. **Phase**: Empirical verification

2. **Record Claude Code version and compare to 2.1.98 fix line**: Run `claude --version`, record the value, and classify as `>= 2.1.98` or `< 2.1.98`. Acceptance: `findings.md` contains a section "## Q2: Claude Code version" with the version string and the classification verdict. `grep -c "## Q2: Claude Code version" lifecycle/investigate-plugin-auto-update-not-fetching-from-origin/findings.md` = 1. **Phase**: Empirical verification

3. **Test whether `/plugin marketplace update cortex-command` advances `origin/main`**: Before invocation, record `git -C ~/.claude/plugins/marketplaces/cortex-command/ rev-parse origin/main` and `git -C ~/.claude/plugins/marketplaces/cortex-command/ log --oneline -1 origin/main`. The user runs `/plugin marketplace update cortex-command` inside Claude Code. After, record the same values. If `origin/main` advanced, the docs are accurate. If not, the community bug reports are accurate. Acceptance: `findings.md` contains a section "## Q3: /plugin marketplace update behavior" with the before/after SHA pair and a verdict — `fetches` or `does-not-fetch`. `grep -c "## Q3: /plugin marketplace update behavior" lifecycle/investigate-plugin-auto-update-not-fetching-from-origin/findings.md` = 1. **Phase**: Empirical verification

4. **Test whether the proposed helper recipe actually causes Claude Code to pick up new content**: Run the proposed sequence — `git -C ~/.claude/plugins/marketplaces/cortex-command/ fetch origin && git -C ~/.claude/plugins/marketplaces/cortex-command/ reset --hard origin/main && rm -rf ~/.claude/plugins/cache/cortex-command/`. Then start a fresh Claude Code session and inspect whether `~/.claude/plugins/cache/cortex-command/cortex-core/<sha>/` rebuilds at a SHA matching the new `origin/main`. Acceptance: `findings.md` contains a section "## Q4: helper recipe verification" with the post-session cache dir SHA and a verdict — `works` or `fails-with: <reason>`. `grep -c "## Q4: helper recipe verification" lifecycle/investigate-plugin-auto-update-not-fetching-from-origin/findings.md` = 1. **Phase**: Empirical verification

5. **Spot-verify the disputed Anthropic issue numbers**: For each of issues #36317, #37252, #46081, #29071, #17361 (cited by the Tradeoffs agent without independent verification), open `https://github.com/anthropics/claude-code/issues/<n>` via WebFetch and record (a) whether the issue exists, (b) its title and status if so, (c) whether its content matches the cited claim ("/plugin update doesn't `git fetch`"). Acceptance: `findings.md` contains a section "## Q5: disputed issue numbers" with one row per issue numbered #36317–#17361 and a verdict column (`confirmed`, `mismatched`, `nonexistent`, `unreachable`). `grep -c "## Q5: disputed issue numbers" lifecycle/investigate-plugin-auto-update-not-fetching-from-origin/findings.md` = 1. **Phase**: Empirical verification

6. **Decide whether `installed_plugins.json` needs touching**: Read `~/.claude/plugins/installed_plugins.json`, locate the cortex-core entry, and compare its `installPath` against the actual current cache dir at `~/.claude/plugins/cache/cortex-command/cortex-core/<sha>/`. If the recorded path's SHA lags the actual cache SHA, issue #52218 applies and the helper must rewrite `installed_plugins.json`. Acceptance: `findings.md` contains a section "## Q6: installed_plugins.json drift" with the recorded `installPath` value, the current cache dir path, a one-line verdict (`drift-detected` / `in-sync` / `cortex-core-not-installed`), and a directive for the helper (`must-rewrite` / `no-rewrite-needed`). `grep -c "## Q6: installed_plugins.json drift" lifecycle/investigate-plugin-auto-update-not-fetching-from-origin/findings.md` = 1. **Phase**: Empirical verification

7. **Implement `cortex-refresh-plugins` in canonical `bin/`**: Create `bin/cortex-refresh-plugins` as an executable bash script that: (a) runs `git -C "$HOME/.claude/plugins/marketplaces/cortex-command/" fetch origin`, (b) runs `git -C "$HOME/.claude/plugins/marketplaces/cortex-command/" reset --hard origin/main`, (c) prints a single-line summary of the SHA delta `old-sha → new-sha`, (d) clears `~/.claude/plugins/cache/cortex-command/` so Claude Code rebuilds on next session, (e) if Q6 returned `must-rewrite`, also updates `installed_plugins.json`'s cortex-core `installPath` to match the new SHA. The script must `set -euo pipefail` and fail loudly if the marketplace clone path doesn't exist (no silent skip). Acceptance: `test -x bin/cortex-refresh-plugins && bash -n bin/cortex-refresh-plugins` exits 0; `grep -c 'fetch origin' bin/cortex-refresh-plugins` ≥ 1 and `grep -c 'reset --hard' bin/cortex-refresh-plugins` ≥ 1. **Phase**: Ship the refresh helper + docs

8. **Mirror `cortex-refresh-plugins` to `plugins/cortex-core/bin/` via `just build-plugin`**: Run `just build-plugin` and verify the regenerated mirror at `plugins/cortex-core/bin/cortex-refresh-plugins` exists and is byte-identical to the canonical `bin/` source. Acceptance: `diff bin/cortex-refresh-plugins plugins/cortex-core/bin/cortex-refresh-plugins` exits 0 (no output); pre-commit dual-source parity hook (`.githooks/pre-commit`) does not flag drift when staging both files. **Phase**: Ship the refresh helper + docs

9. **Wire `cortex-refresh-plugins` into the parity allowlist or hook reference**: Per the project's "SKILL.md-to-bin parity enforcement" constraint, the new script must be referenced from at least one of: SKILL.md, requirements, docs, hooks, justfile, tests. The natural reference is docs/setup.md (covered by Requirement 10). Acceptance: `bin/cortex-check-parity` (run as `python3 bin/cortex-check-parity` or equivalent) exits 0 with no drift findings on staged state. **Phase**: Ship the refresh helper + docs

10. **Extend `docs/setup.md` § Upgrade & maintenance with a "Keeping plugins fresh" subsection**: Add a subsection that (a) explains the staleness symptom in one paragraph (cache dir SHA lags origin/main), (b) presents `cortex-refresh-plugins` as the resolution, (c) links to the lifecycle/{feature}/findings.md as the source of truth for the empirical evidence, and (d) notes the upstream-bug hypothesis as a contingency (in case Anthropic's behavior changes the helper becomes a no-op). Acceptance: `grep -c "Keeping plugins fresh" docs/setup.md` ≥ 1 AND `grep -c "cortex-refresh-plugins" docs/setup.md` ≥ 2. **Phase**: Ship the refresh helper + docs

11. **Classify the staleness as bug / config gap / expected behavior** based on Q1–Q5 outcomes. Write the classification verdict into `findings.md`'s `## Classification` section with one-paragraph reasoning and one-sentence "evidence" line citing which Q-outcome drives the verdict. Acceptance: `grep -c "^## Classification" lifecycle/investigate-plugin-auto-update-not-fetching-from-origin/findings.md` = 1 AND the section body contains one of the strings `bug`, `config gap`, or `expected behavior` as the verdict. **Phase**: Ship the refresh helper + docs

## Non-Requirements

- **Filing an upstream issue at anthropics/claude-code** — explicitly out of scope per user direction. Document any contradictions locally only.
- **SessionStart hook auto-refresh** — out of scope. The helper is manual-invocation only. A future ticket may wire it into a hook.
- **`just refresh-plugins` recipe** — out of scope unless natural-fit during implementation. `cortex-refresh-plugins` directly on PATH (via `cortex-jcc` analogue) is sufficient.
- **Touching `marketplace.json` or `plugin.json` version fields** — explicitly excluded by the original ticket's Out of Scope. cortex-core stays version-less per Claude Code docs' recommendation for actively-developed plugins.
- **Modifying Claude Code internals or building a workaround for issue #52218 beyond writing the recorded `installPath`** — the helper updates the one value if drift is detected (Q6) and stops there.
- **Cross-platform support beyond macOS/Linux** — Windows path handling for `~/.claude/plugins/` is not covered. The script assumes POSIX path conventions.
- **Auto-detection of the marketplace name** — the script hard-codes `cortex-command`. If users have renamed the marketplace, they must edit the script. Generalization deferred.

## Edge Cases

- **Marketplace clone path does not exist** (user has never run `/plugin marketplace add charleshall888/cortex-command`): the script fails loudly with a non-zero exit and a message pointing to setup.md. No silent skip.
- **Marketplace clone has local uncommitted changes** (e.g., user was hacking on it directly): `git reset --hard origin/main` would discard those. The script must check `git status --porcelain` first and abort with a clear message if non-empty — preserving user state per the project's "Destructive operations preserve uncommitted state" quality attribute.
- **`~/.claude/plugins/cache/cortex-command/` does not exist** (clean install or already cleared): `rm -rf` is a no-op; proceed.
- **`installed_plugins.json` is missing or malformed**: log a warning, skip the `installPath` rewrite, do not fail the whole run. (Plugin still gets updated content via marketplace clone refresh; the only loss is bundled-hook freshness per #52218.)
- **`~/.claude/plugins/marketplaces/cortex-command/` is not a git clone of cortex-command** (e.g., user pointed at a fork): the script verifies `git remote get-url origin` matches the expected URL pattern and aborts on mismatch, to avoid `reset --hard`-ing a fork the user is iterating on.
- **Claude Code is currently running** while the script executes: cache rebuilds happen on next session start, so concurrent use is safe. Document this explicitly.
- **Empirical experiments contradict each other** (e.g., Q3 says "fetches" but the cache still lags): record both observations in findings.md and pick the most-conservative classification (config gap) — the helper still works regardless.

## Changes to Existing Behavior

- **ADDED**: New executable `bin/cortex-refresh-plugins` + plugin-mirror at `plugins/cortex-core/bin/cortex-refresh-plugins`. Available on PATH when the cortex-core plugin is installed.
- **MODIFIED**: `docs/setup.md` § Upgrade & maintenance gains a "Keeping plugins fresh" subsection documenting the helper and the staleness symptom.
- No skill prose change. No hook change. No CI workflow change.
- `marketplace.json` and `plugin.json` are untouched.

## Technical Constraints

- **Dual-source enforcement**: `bin/cortex-refresh-plugins` and `plugins/cortex-core/bin/cortex-refresh-plugins` must be byte-identical post-`just build-plugin`. Pre-commit hook enforces.
- **Parity gate**: `bin/cortex-*` scripts must be referenced from in-scope SKILL.md / requirements / docs / hooks / justfile / tests; the natural reference is `docs/setup.md` (Requirement 10).
- **Advisory-only posture**: post-ticket-141, cortex-command moved away from auto-installing things in user environments. The helper is opt-in (manual invocation), matching that posture.
- **Plugin byte-identity requirement**: any change to the plugin mirror must be reproducible via `just build-plugin` from canonical source.
- **POSIX-only paths**: `~/.claude/plugins/` paths assume Unix shell expansion. Windows users (if any exist for cortex-command) will need separate guidance.
- **Time-boxed scope**: spike is single-session; Phase 2 implementation must fit in the same session as Phase 1 verification.

## Open Decisions

(None — all open decisions resolved at spec time. The empirical experiments in Phase 1 produce data that informs Phase 2 implementation details — e.g., whether Requirement 7e fires depends on Q6's outcome — but the spec captures both branches.)
