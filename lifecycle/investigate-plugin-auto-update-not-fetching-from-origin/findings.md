# Findings: investigate-plugin-auto-update-not-fetching-from-origin

## Q1: autoUpdate values

Source paths inspected: `~/.claude/plugins/known_marketplaces.json` and `~/.claude/settings.json`.

- `known_marketplaces.json`.`cortex-command`.`autoUpdate` = `true`
- `known_marketplaces.json`.`cortex-command`.`lastUpdated` = `"2026-05-12T02:36:08.044Z"`
- `settings.json`.`extraKnownMarketplaces`.`cortex-command`.`autoUpdate` = `true`
- `settings.json` has **no** top-level `autoUpdate` field (the third-party-default-false hypothesis from research turns on this field's presence at marketplace-entry scope, not at top level).

**Verdict on the "third-party-default-false" hypothesis**: invalidated. `autoUpdate: true` is explicitly set in both expected places (the live runtime `known_marketplaces.json` entry and the source-of-truth `settings.json` `extraKnownMarketplaces` entry). The staleness symptom must have a different root cause.

## Q2: Claude Code version

`claude --version` output: `2.1.139 (Claude Code)`.

Classification: **`>= 2.1.98`** (post-fix). Claude Code 2.1.98 (Apr 9, 2026) is the canonical fix line for the "`claude plugin update` reports 'already at the latest version'" bug; 2.1.139 is well past that. 2.1.101/2.1.126 (warning on failed marketplace refresh) and 2.1.128 (npm-source detection fix) are also included. The pre-2.1.98 bug hypothesis is **invalidated** for the observed staleness.

## Q3: /plugin marketplace update behavior

Approach: instead of running a controlled `/plugin marketplace update` invocation (the marketplace clone is already at `origin/main` so the command would be a no-op observation), the marketplace clone's `git reflog` provides direct historical evidence of the actual git operations Claude Code's auto-update mechanism has performed against it.

Reflog (`git -C ~/.claude/plugins/marketplaces/cortex-command/ reflog --date=iso`):

```
5342192 HEAD@{2026-05-11 22:36:08 -0400}: pull origin HEAD: Fast-forward
199fe13 HEAD@{2026-05-11 20:19:52 -0400}: pull origin HEAD: Fast-forward
d63a687 HEAD@{2026-05-11 20:08:41 -0400}: pull origin HEAD: Fast-forward
7ee2d9c HEAD@{2026-05-11 19:16:53 -0400}: pull origin HEAD: Fast-forward
a0e3a3e HEAD@{2026-05-07 10:02:21 -0400}: pull origin HEAD: Fast-forward
c7e5ac7 HEAD@{2026-05-06 17:48:51 -0400}: pull origin HEAD: Fast-forward
3c1f419 HEAD@{2026-05-06 14:58:59 -0400}: pull origin HEAD: Fast-forward
976038f HEAD@{2026-05-06 09:31:39 -0400}: pull origin HEAD: Fast-forward
16eb3cc HEAD@{2026-05-05 14:02:26 -0400}: clone: from github.com:charleshall888/cortex-command.git
```

**Verdict: `fetches`.** Every entry is `pull origin HEAD: Fast-forward`. `git pull` runs `git fetch` first, then merges (fast-forwarding when possible). The marketplace clone HAS been progressively advanced by 8 distinct `git pull` operations since initial clone at 16eb3cc on 2026-05-05. The Tradeoffs research agent's claim that `/plugin update` / `autoUpdate` does NOT run `git fetch` (citing issues #36317, #37252, #46081, #29071, #17361) is **contradicted by the reflog**.

**Key timing observation explaining the original ticket's symptom**: a 4-day gap between `2026-05-07 10:02` and `2026-05-11 19:16` shows no Claude Code session was started during that period. The cache fell behind because no auto-update ran. When the user resumed work on 2026-05-11, 4 catch-up pulls fired across that day's session starts, eventually advancing to `5342192`. The "30 commits behind" complaint was an artifact of the no-session gap, not a fetch-skip bug.

## Q6: installed_plugins.json drift (rolled forward as the versioning check)

Original Q6 asked whether `installed_plugins.json`'s `installPath` lags behind the actual cache dir SHA (per issue #52218). Mid-investigation, the user reframed this as a broader "is versioning working?" check. Recording both layers:

Source paths inspected: `~/.claude/plugins/installed_plugins.json` and `~/.claude/plugins/cache/cortex-command/cortex-core/`.

`installed_plugins.json` cortex-core entry (verbatim):

```json
{
  "scope": "user",
  "installPath": "/Users/charlie.hall/.claude/plugins/cache/cortex-command/cortex-core/5342192d842f",
  "version": "5342192d842f",
  "installedAt": "2026-05-05T18:02:40.997Z",
  "lastUpdated": "2026-05-12T02:36:08.075Z",
  "gitCommitSha": "16eb3ccb3f9bd19a11613fd9a5835be1c8adc487"
}
```

Cross-check against filesystem:

- Current marketplace clone HEAD: `5342192d842f65c5f6014a4364c4ba4a3056d926` — matches `installPath`/`version` (12-char prefix).
- `~/.claude/plugins/cache/cortex-command/cortex-core/` contains **9 versioned subdirectories**: `16eb3ccb3f9b` (initial install, 2026-05-06 09:31), `976038fac53a`, `3c1f419459a2`, `c7e5ac755e9a`, `a0e3a3e1649b`, `7ee2d9c8bf87`, `d63a6875eb63`, `199fe13e3247`, and `5342192d842f` (current, 2026-05-11 22:36). One per session-start pull since install.

**Verdict: `in-sync`. Directive: `no-rewrite-needed`.** The version-detection mechanism is working end-to-end: marketplace HEAD advances → new cache dir is created at the new SHA → `installPath` and `version` in `installed_plugins.json` are kept current. Issue #52218 (bundled-hook `installPath` staleness) does NOT apply to this install. The static field `gitCommitSha` is a historical record of the install-time origin/main SHA and is not used for cache-key lookup.

## Q4, Q5: descoped

After Q1–Q3 + Q6 collectively answered the spike's premise (auto-update works end-to-end; original symptom traces to a 4-day no-session gap, not a mechanism bug), the user re-scoped to "drop helper, document findings, close spike." Q4 (helper recipe verification) is moot since the helper is no longer being shipped. Q5 (verifying disputed Anthropic issue numbers #36317, #37252, #46081, #29071, #17361) is moot since the reflog evidence already contradicts the consumption-side-fetch-skip claim those issues purportedly described.

## Classification

**Verdict: `expected behavior`.**

The plugin auto-update mechanism works as documented:
- `autoUpdate: true` (set on the cortex-command marketplace entry — Q1) fires at Claude Code session start.
- Each session start runs `git pull origin HEAD: Fast-forward` against the marketplace clone (Q3 reflog: 8 successful pulls since initial clone on 2026-05-05).
- After the pull, Claude Code creates a new cache dir at the new SHA and updates `installed_plugins.json` `installPath` + `version` to point at it (Q6: 9 cache dirs matching the 8 pulls + initial install; `installPath` currently at HEAD).
- No background polling cadence — the cadence is "per Claude Code session start." Documented behavior, not a bug.

The original ticket's "30 commits behind" empirical observation has a benign explanation: a 4-day gap (`2026-05-07 10:02` → `2026-05-11 19:16`) without any new Claude Code session starts, during which time origin advanced by ~30 commits. When the user resumed work on 2026-05-11, 4 catch-up pulls fired across that day's session starts (19:16, 20:08, 20:19, 22:36) and the cache fully recovered to `5342192`.

**Evidence**: Q1 (autoUpdate=true on both surfaces) + Q2 (Claude Code 2.1.139, post-fix) + Q3 (reflog shows 8 successful `git pull origin HEAD: Fast-forward` operations across 6 days) + Q6 (`installPath` and `version` track marketplace HEAD; no #52218 drift).

The Tradeoffs research agent's claim that `/plugin update` / `autoUpdate` does NOT run `git fetch` (citing issues #36317, #37252, #46081, #29071, #17361) is contradicted by direct reflog evidence and was not independently verified before being cited. Treat that line of reasoning as a research-time hallucination; the cited issues may or may not exist, but the behavior they describe does not occur in this install.

## Workflow recommendation

For "how do we make plugin auto-publish on main push":

- **The push IS the publish.** Pushing to `origin/main` makes commits available on GitHub.
- **Subscribers refresh on next Claude Code session start.** `autoUpdate: true` at the marketplace level (`known_marketplaces.json`) triggers `git pull origin HEAD` against the marketplace clone, and a new cache dir is created at the new SHA. `installed_plugins.json` is updated to point at the new cache dir.
- **Mid-session freshness** (push something, want the current session to see it without restarting Claude Code): run `/plugin marketplace update cortex-command` inside Claude Code, then `/reload-plugins`.
- **No new tooling is needed.** The originally-proposed `cortex-refresh-plugins` shell helper is dropped — it would have been a workaround for a problem that doesn't exist on a system with `autoUpdate: true` and regular session starts.

The publish/subscribe latency floor is "next session start" — for someone who routinely starts new Claude Code sessions (multiple per day), this is on the order of minutes-to-hours. For someone away for days, it can be a multi-day catch-up batch, but the mechanism converges.

