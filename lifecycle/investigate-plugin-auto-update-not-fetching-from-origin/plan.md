# Plan: investigate-plugin-auto-update-not-fetching-from-origin

## Overview

Two-phase spike. Phase 1 runs six small empirical experiments that append findings to a single `findings.md` artifact, ending in a classification verdict (bug / config gap / expected behavior). Phase 2 ships a small `cortex-refresh-plugins` bash helper plus its plugin mirror, wired through a new "Keeping plugins fresh" subsection in `docs/setup.md` to satisfy the SKILL.md-to-bin parity gate. The helper itself is conditional only on Q6 (whether `installed_plugins.json` needs rewriting); the rest of the script body is determined by spec requirements regardless of Phase 1 outcome.

## Outline

### Phase 1: Empirical verification (tasks: 1, 2, 3, 4, 5, 6)
**Goal**: Produce `lifecycle/investigate-plugin-auto-update-not-fetching-from-origin/findings.md` with one section per forensic question (Q1–Q6), each populated with raw values and a one-line verdict.
**Checkpoint**: `findings.md` contains six `## Q<n>:` sections matching the spec's acceptance grep patterns; one or more `## Q3` / `## Q4` verdicts read `fetches` or `does-not-fetch` / `works` or `fails-with: <reason>`.

### Phase 2: Ship the refresh helper + docs (tasks: 7, 8, 9, 10)
**Goal**: Land `bin/cortex-refresh-plugins` + plugin mirror, wired via a "Keeping plugins fresh" subsection in `docs/setup.md`, with the classification synthesis recorded in `findings.md`.
**Checkpoint**: `cortex-check-parity` clean; `diff bin/cortex-refresh-plugins plugins/cortex-core/bin/cortex-refresh-plugins` empty; `findings.md` contains `## Classification` with one of {`bug`, `config gap`, `expected behavior`}.

## Tasks

### Task 1: Record `autoUpdate` values (Q1) [x] complete
- **Files**: `lifecycle/investigate-plugin-auto-update-not-fetching-from-origin/findings.md`
- **What**: Read `~/.claude/plugins/known_marketplaces.json` and `~/.claude/settings.json`. Append a `## Q1: autoUpdate values` section to `findings.md` containing the raw values of `marketplaces["cortex-command"].autoUpdate` (from known_marketplaces.json) and the top-level `autoUpdate` field (from settings.json), plus a one-sentence verdict on whether the third-party-default-false hypothesis explains the staleness.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `findings.md` does not yet exist — this task creates it. Both source JSON files live under `~/.claude/plugins/` and `~/.claude/`. Read-only reads (no write to `~/.claude/`). The expected schema is documented in the Web Research section of `research.md` (look for `known_marketplaces.json`); per Claude Code docs, third-party marketplaces default `autoUpdate: false`.
- **Verification**: (b) Two content patterns in `lifecycle/investigate-plugin-auto-update-not-fetching-from-origin/findings.md`: `grep -c "## Q1: autoUpdate values" findings.md` = 1 AND `grep -cE "(known_marketplaces\\.json|settings\\.json)" findings.md` ≥ 2 (both source paths must appear in the recorded observation). Pass if both conditions hold.
- **Status**: [ ] pending

### Task 2: Record Claude Code version (Q2) [x] complete
- **Files**: `lifecycle/investigate-plugin-auto-update-not-fetching-from-origin/findings.md`
- **What**: Run `claude --version`, append a `## Q2: Claude Code version` section to `findings.md` with the version string and a one-line classification: `>= 2.1.98` (post-fix) or `< 2.1.98` (pre-fix, expected to be buggy).
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Per Web Research, changelog entry 2.1.98 (Apr 9, 2026) fixes the canonical "already at the latest version" staleness bug. Sequential append to `findings.md`.
- **Verification**: (b) Section presence + recorded version pattern in `lifecycle/investigate-plugin-auto-update-not-fetching-from-origin/findings.md`: `grep -c "## Q2: Claude Code version" findings.md` = 1 AND `grep -cE "[0-9]+\\.[0-9]+\\.[0-9]+" findings.md` ≥ 1 (a semver-shaped string must appear in the section). Pass if both conditions hold.
- **Status**: [ ] pending

### Task 3: Record `/plugin marketplace update` behavior (Q3) [x] complete
- **Files**: `lifecycle/investigate-plugin-auto-update-not-fetching-from-origin/findings.md`
- **What**: Capture `git -C ~/.claude/plugins/marketplaces/cortex-command/ rev-parse origin/main` as the before-SHA. Prompt the user to run `/plugin marketplace update cortex-command` inside Claude Code. After they confirm, capture the post-SHA. Append a `## Q3: /plugin marketplace update behavior` section to `findings.md` with both SHAs and a verdict `fetches` (if advanced) or `does-not-fetch` (if unchanged).
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: Interactive — the `/plugin marketplace update` command is not invokable from a shell; it must be run inside the user's Claude Code session. Use `AskUserQuestion` to coordinate the hand-off ("Run `/plugin marketplace update cortex-command` now and confirm done"). The marketplace clone is at `~/.claude/plugins/marketplaces/cortex-command/`.
- **Verification**: (c) Interactive/session-dependent: the `/plugin marketplace update` command is only invokable inside the user's Claude Code session and the verdict turns on the operator's pre/post SHA capture. Structural check: `grep -c "## Q3: /plugin marketplace update behavior" findings.md` = 1 AND `grep -cE "(fetches|does-not-fetch)" findings.md` ≥ 1 (one of the verdict tokens must appear). Pass if both conditions hold.
- **Status**: [ ] pending

### Task 4: Verify proposed helper recipe (Q4) [-] descoped

> **Descoped 2026-05-12**: After Tasks 1–3 + a versioning cross-check (Q6) established that the auto-update mechanism works end-to-end, the user re-scoped to drop the helper and close the spike. Q4's premise (that we need a helper recipe at all) is moot. See `findings.md` § Q4, Q5: descoped and § Classification.

(original task body retained for audit trail)

- **Files**: `lifecycle/investigate-plugin-auto-update-not-fetching-from-origin/findings.md`
- **What**: Run the sequence `git -C ~/.claude/plugins/marketplaces/cortex-command/ fetch origin && git -C ~/.claude/plugins/marketplaces/cortex-command/ reset --hard origin/main && rm -rf ~/.claude/plugins/cache/cortex-command/`. Prompt the user to start a fresh Claude Code session and report the new cache dir path under `~/.claude/plugins/cache/cortex-command/cortex-core/<sha>/`. Append a `## Q4: helper recipe verification` section to `findings.md` with the post-session cache dir SHA, the current `origin/main` SHA for comparison, and a verdict `works` (SHAs match) or `fails-with: <reason>`.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: Interactive — requires the user to start a new Claude Code session for the cache to rebuild. Hand-off via `AskUserQuestion` ("Start a fresh Claude Code session in another window, then paste the new cache dir SHA from `ls ~/.claude/plugins/cache/cortex-command/cortex-core/`"). This task validates approach E directly; if it fails, the spec's recommended approach is invalidated and Task 7's classification should reflect that.
- **Verification**: (c) Interactive/session-dependent: starting a fresh Claude Code session and reading back the cache dir SHA requires operator action; the verdict depends on the operator's empirical observation. Structural check: `grep -c "## Q4: helper recipe verification" findings.md` = 1 AND `grep -cE "(works|fails-with)" findings.md` ≥ 1 (one of the verdict tokens must appear). Pass if both conditions hold.
- **Status**: [ ] pending

### Task 5: Verify disputed Anthropic issue numbers (Q5) [-] descoped — see Task 4 note
- **Files**: `lifecycle/investigate-plugin-auto-update-not-fetching-from-origin/findings.md`
- **What**: For each of issues `#36317`, `#37252`, `#46081`, `#29071`, `#17361` (cited by the Tradeoffs research agent without independent verification), WebFetch `https://github.com/anthropics/claude-code/issues/<n>` and record title + status + whether content matches the cited claim. Append a `## Q5: disputed issue numbers` section to `findings.md` with one row per issue and a verdict column: `confirmed`, `mismatched`, `nonexistent`, or `unreachable`.
- **Depends on**: [4]
- **Complexity**: simple
- **Context**: Use the WebFetch tool. The `api.github.com` and `*.anthropic.com` hosts are in the sandbox allowlist; `github.com` itself is allowed via WebFetch. If a URL is unreachable, record `unreachable` rather than fabricate content. This task informs Task 7's classification confidence — if all 5 issues are `confirmed`, the "consumption-side bug" hypothesis hardens; if all 5 are `nonexistent`, the Tradeoffs agent likely hallucinated.
- **Verification**: (b) Section presence + all five issue numbers recorded: `grep -c "## Q5: disputed issue numbers" findings.md` = 1 AND `grep -cE "#(36317|37252|46081|29071|17361)" findings.md` ≥ 5 (every cited issue number appears in the section, in any order). Pass if both conditions hold.
- **Status**: [ ] pending

### Task 6: Record `installed_plugins.json` drift (Q6) [x] complete (rolled forward as versioning check; see findings.md § Q6)
- **Files**: `lifecycle/investigate-plugin-auto-update-not-fetching-from-origin/findings.md`
- **What**: Read `~/.claude/plugins/installed_plugins.json`. Locate the cortex-core entry and extract its `installPath` value. Compare the path's embedded SHA segment to the actual current cache dir SHA at `~/.claude/plugins/cache/cortex-command/cortex-core/<sha>/`. Append a `## Q6: installed_plugins.json drift` section to `findings.md` with the recorded `installPath`, the current cache dir path, a verdict (`drift-detected` / `in-sync` / `cortex-core-not-installed`), and a directive for the helper (`must-rewrite` / `no-rewrite-needed`).
- **Depends on**: [5]
- **Complexity**: simple
- **Context**: Per Web Research, Anthropic issue #52218 is open and confirms that `autoUpdate` does not refresh `installed_plugins.json`'s `installPath`, leaving bundled hooks pinned. Q6's directive output drives Task 9's edge-case branch (whether `cortex-refresh-plugins` must include the `installed_plugins.json` rewrite step). The file structure is a JSON object keyed by plugin name; cortex-core's entry has `installPath` and `gitCommitSha` fields.
- **Verification**: (b) Section presence + verdict token + directive token: `grep -c "## Q6: installed_plugins.json drift" findings.md` = 1 AND `grep -cE "(drift-detected|in-sync|cortex-core-not-installed)" findings.md` ≥ 1 AND `grep -cE "(must-rewrite|no-rewrite-needed)" findings.md` ≥ 1. Pass if all three conditions hold.
- **Status**: [ ] pending

### Task 7: Write classification synthesis section [x] complete (findings.md § Classification)
- **Files**: `lifecycle/investigate-plugin-auto-update-not-fetching-from-origin/findings.md`
- **What**: Synthesize Q1–Q5 outcomes into a `## Classification` section. The verdict must be one of: `bug` (Q5 issues confirmed + Q3 says `does-not-fetch`), `config gap` (Q1 reveals `autoUpdate: false` on the cortex-command marketplace entry, OR Q2 reveals `< 2.1.98`), or `expected behavior` (Q3 says `fetches` + Q1 confirms `autoUpdate: true` is honored). Include one paragraph of reasoning and a one-sentence "Evidence:" line citing the load-bearing Q-outcomes.
- **Depends on**: [6]
- **Complexity**: simple
- **Context**: This is the spike's primary investigation deliverable. Re-read `findings.md`'s Q1–Q6 sections in full before drafting the synthesis — do not paraphrase from memory. The decision tree above is the spec's acceptance shape; if outcomes don't cleanly map to one verdict, pick the most-conservative (`config gap`) and explain.
- **Verification**: `grep -c "^## Classification" lifecycle/investigate-plugin-auto-update-not-fetching-from-origin/findings.md` = 1 AND `grep -E "^(bug|config gap|expected behavior)$|: (bug|config gap|expected behavior)\\b" lifecycle/investigate-plugin-auto-update-not-fetching-from-origin/findings.md` count ≥ 1 (pass if both conditions hold).
- **Status**: [ ] pending

### Task 8: Add "Keeping plugins fresh" subsection to `docs/setup.md` (wiring first) [-] descoped — see Task 4 note
- **Files**: `docs/setup.md`
- **What**: Insert a new subsection titled `### Keeping plugins fresh` under `## Upgrade & maintenance` in `docs/setup.md`. The subsection (≈10–15 lines) explains the cache-staleness symptom in one paragraph, presents `cortex-refresh-plugins` as the resolution (named at least twice in the body), links to `lifecycle/investigate-plugin-auto-update-not-fetching-from-origin/findings.md` for the empirical evidence, and notes that the helper becomes a no-op when/if Anthropic fixes the upstream behavior. This task lands the parity reference BEFORE the script exists per the Wiring Co-Location rule — `cortex-check-parity` flags `deployed-but-unreferenced` (W003), not `referenced-but-undeployed`.
- **Depends on**: [7]
- **Complexity**: simple
- **Context**: `docs/setup.md` already has a `## Upgrade & maintenance` section starting at line 186. Read it first to match tone and existing structure (it references the `cortex-overnight` plugin's `CLI_PIN` mechanism and discusses the `/plugin update` story). The new subsection should slot in as a peer subsection under `## Upgrade & maintenance`, after the existing CLI_PIN paragraph.
- **Verification**: `grep -c "Keeping plugins fresh" docs/setup.md` ≥ 1 AND `grep -c "cortex-refresh-plugins" docs/setup.md` ≥ 2 (pass if both counts hold).
- **Status**: [ ] pending

### Task 9: Create canonical `bin/cortex-refresh-plugins` [-] descoped — see Task 4 note
- **Files**: `bin/cortex-refresh-plugins`
- **What**: Create the executable bash script. Required body shape: `#!/usr/bin/env bash` shebang; `set -euo pipefail`; constant `MARKETPLACE_DIR="$HOME/.claude/plugins/marketplaces/cortex-command"`; constant `CACHE_DIR="$HOME/.claude/plugins/cache/cortex-command"`; constant `INSTALLED_PLUGINS_JSON="$HOME/.claude/plugins/installed_plugins.json"`; expected remote URL pattern matched against `git -C "$MARKETPLACE_DIR" remote get-url origin`. Behavior: (a) verify `MARKETPLACE_DIR` is a git repo and the remote URL matches; (b) verify `git -C "$MARKETPLACE_DIR" status --porcelain` is empty (abort with clear message if not, preserving uncommitted state); (c) capture `OLD_SHA=$(git -C "$MARKETPLACE_DIR" rev-parse HEAD)`; (d) `git -C "$MARKETPLACE_DIR" fetch origin`; (e) `git -C "$MARKETPLACE_DIR" reset --hard origin/main`; (f) capture `NEW_SHA`; (g) if `CACHE_DIR` exists, `rm -rf` it; (h) if Q6's directive was `must-rewrite`, also update `INSTALLED_PLUGINS_JSON`'s cortex-core `installPath` to embed `NEW_SHA` (use `python3 -c` or `jq` if available; fallback to a logged warning + skip if neither is); (i) print one summary line `cortex-refresh-plugins: $OLD_SHA → $NEW_SHA`. Make executable with `chmod +x`. Closely mirror error-handling style of `bin/cortex-jcc`.
- **Depends on**: [8, 6]
- **Complexity**: simple
- **Context**: Q6's output (read from `findings.md` Task 6 section) determines whether step (h) is included as live code or as a documented `# no rewrite needed` comment. Use `bin/cortex-jcc` as the pattern reference (similar pattern: bash script that operates against a known path under `~/.claude/` or repo root, with clear-error-on-misconfiguration discipline). The script must NOT modify `MARKETPLACE_DIR` if it is not a clone of the expected remote (edge case: forked repo). The script must NOT proceed if `MARKETPLACE_DIR/.git` is dirty (edge case: user iteration in the clone).
- **Verification**: `test -x bin/cortex-refresh-plugins` (pass if exit 0) AND `bash -n bin/cortex-refresh-plugins` (pass if exit 0, no syntax errors) AND `grep -c 'fetch origin' bin/cortex-refresh-plugins` ≥ 1 AND `grep -c 'reset --hard' bin/cortex-refresh-plugins` ≥ 1 AND `grep -c 'status --porcelain' bin/cortex-refresh-plugins` ≥ 1.
- **Status**: [ ] pending

### Task 10: Regenerate plugin mirror + verify parity gate clean [-] descoped — see Task 4 note
- **Files**: `plugins/cortex-core/bin/cortex-refresh-plugins`
- **What**: Run `just build-plugin` to regenerate the plugin's `bin/` mirror from the canonical source written in Task 9. Then run `diff bin/cortex-refresh-plugins plugins/cortex-core/bin/cortex-refresh-plugins` and confirm no output. Then run `bin/cortex-check-parity` (or `python3 bin/cortex-check-parity`, depending on how it's invoked in the repo) and confirm no W003 (orphan: deployed but not referenced) findings — the wiring reference in `docs/setup.md` from Task 8 should satisfy the parity gate.
- **Depends on**: [9]
- **Complexity**: simple
- **Context**: `just build-plugin` is documented in CLAUDE.md and regenerates `plugins/cortex-core/` from canonical `skills/`, `hooks/`, `bin/` sources. The pre-commit hook `.githooks/pre-commit` enforces parity between canonical and mirrored copies. `bin/cortex-check-parity` is the static gate (documented in `requirements/project.md` Architectural Constraints). If parity fails, the canonical source needs adjustment — do not edit the plugin mirror directly.
- **Verification**: `diff bin/cortex-refresh-plugins plugins/cortex-core/bin/cortex-refresh-plugins` exits 0 with no stdout output (pass if both conditions hold) AND running the project's parity check produces no `W003` finding for `cortex-refresh-plugins` (pass if `bin/cortex-check-parity` (or its python module form) exits 0 with no W003 mention in stderr/stdout).
- **Status**: [ ] pending

## Risks

- **Task 3 and Task 4 require the user to interact with their Claude Code session mid-implementation.** If the user is not present or the session has terminated, both tasks block. The plan does not offer a non-interactive fallback for these — the empirical experiments require live Claude Code execution by design.
- **Task 5 hallucination risk**: the Tradeoffs research agent cited specific issue numbers (#36317, #37252, #46081, #29071, #17361) without independent verification. If WebFetch confirms most of them are `nonexistent`, the entire "consumption-side bug" hypothesis loses support and the classification (Task 7) should pivot toward `config gap` or `expected behavior`. This is the spike's most likely point of recommendation reversal.
- **Task 9 `installed_plugins.json` rewrite is conditional on Q6 outcome.** If Q6 says `must-rewrite` but the user lacks `jq` AND a workable `python3`, the helper must skip the rewrite step with a logged warning rather than fail outright. The plan's spec lists this as an edge case; the script must not require the rewrite to succeed.
- **`just build-plugin` may have unrelated drift** in `plugins/cortex-core/` from any unstaged canonical-source changes elsewhere in the repo. If Task 10's diff shows unrelated changes, stop and surface them rather than committing the noise. This is a typical pre-existing-drift hazard, not specific to this feature.

## Acceptance

`bin/cortex-refresh-plugins` is executable, byte-identical to `plugins/cortex-core/bin/cortex-refresh-plugins`, and named (≥2 occurrences) in a "Keeping plugins fresh" subsection of `docs/setup.md`. `bin/cortex-check-parity` passes with no W003 findings for the new script. `lifecycle/investigate-plugin-auto-update-not-fetching-from-origin/findings.md` contains seven sections (Q1, Q2, Q3, Q4, Q5, Q6, Classification) and the Classification section's verdict is one of `bug`, `config gap`, or `expected behavior` with one-paragraph reasoning and an evidence line citing the load-bearing Q-outcomes.
