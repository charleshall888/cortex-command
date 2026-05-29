# Research: cortex-init-scope-reduction

## Recommendation

**`cortex init --ensure` (the in-session entry point) MUST NOT write to `~/.claude/`. Terminal `cortex init` keeps its current behavior unchanged.**

The flag itself encodes the user-vs-AI consent boundary: a write the user explicitly typed in their terminal can touch their Claude Code settings; a write an in-session AI helper performs cannot. This matches how new adopters reason about trust at install time and eliminates the `dangerouslyDisableSandbox` retry pattern that motivated the discovery.

This recommendation withdraws two earlier framings: round 1's pre-declaration of "Approach D" before the evidence supported one, and round 2's theatrical symmetric presentation of four approaches when the evidence supported one. The current recommendation is grounded in the EP/EF/CO load-bearing audit (gap 2), the verified plugin-install infeasibility (gap 1), the empirical modal-first-contact-path finding (gap 3), and the user's stated principle ("users don't expect a tool to touch their Claude settings automatically").

## What changes

### `cortex init --ensure` (in-session)

`_run_ensure()` at `cortex_command/init/handler.py:129-247` drops two calls:

1. Remove `settings_merge.validate_settings(home)` at line 163 (the host-scope pre-flight that acquires `~/.claude/.settings.local.json.lock`).
2. Remove `settings_merge.register(repo_root, cortex_target, home=home)` at line 240 (the host-scope additive write).
3. Remove the `unregister_matching_in_place("cortex-worktrees", home=home)` migration step at line 245 (host-scope; this migration window can close on terminal `--update` instead).

Behavior becomes refresh-only for marker-present cases:

- **Case (i) marker-present + hash-matches**: unchanged. Silent pass. Exit 0.
- **Case (ii) marker-present + hash-mismatch**: refresh `cortex/` content + `.gitignore` + CLAUDE.md fence (all repo-scope, sandbox-allowed) + write marker. Exit 0.
- **Case (v) R8 recovery (marker-present + missing-hash + cortex_version-present)**: same as (ii). Exit 0. (My recent v2.14.1 fix is preserved.)

For marker-absent cases, `--ensure` no longer bootstraps:

- **Case (iii) marker-absent + cortex/ absent-or-empty**: emit stderr `cortex init --ensure: this repo isn't initialized for cortex. Run \`cortex init\` in your terminal to bootstrap.` Exit 2. No repo-scope writes either.
- **Case (iv) marker-absent + cortex/-has-content**: unchanged (R19 content-decline, exit 2).

The argument for refusing to scaffold even repo-scope state in case (iii): scaffolding cortex/ in a fresh repo without the host-scope registration leaves the user with a partial setup (cortex/ exists; sub-agents writing under it will prompt-storm because there's no allowWrite entry). Cleaner to refuse atomically and direct the user to terminal init, which sets up everything consistently with full consent.

### `cortex init` (terminal)

Unchanged. Default invocation still does the full scaffold + .gitignore + CLAUDE.md fence + `~/.claude/settings.local.json` registration. `--update` still touches `~/.claude/` to refresh registration. `--force` unchanged.

### Lifecycle skill wire-up

`plugins/cortex-core/skills/lifecycle/SKILL.md:15, 128` calls `cortex-lifecycle-init-ensure` at Step 2. Today it expects exit 0 to proceed; exit 2 means user-correctable gate failure. The skill must surface the "run cortex init in your terminal" stderr message to the user and halt before any further phase work. Small wire-up change, coupled to this fix.

## Why not the alternatives

**Why not Approach A (status quo + post-write narration).** Narration after a write the user didn't consent to doesn't satisfy "we don't touch your settings automatically." It documents the touching, but the touching still happens via `dangerouslyDisableSandbox` retry. Distribution concern unaddressed.

**Why not Approach B (declare-preview-confirm at terminal `cortex init` only).** The preview UX at terminal install is a separate, smaller question (worth considering as a follow-up). But it doesn't fix the in-session problem — `--ensure` still tries to write `~/.claude/` and still gets sandbox-blocked. B is necessary but insufficient; this recommendation is what's *sufficient*.

**Why not pure Approach C (lazy EF creation in-session).** Critical review's R1 surfaced a real implementation concern: `atomic_write` has no flock around the read-decide-write triplet in `ensure_claude_md_authorization`. Concurrent first-use triggers race on the CLAUDE.md fence splice. Pure-C would need to build a sibling-lockfile around the splice. Possible but adds complexity. The recommended design avoids this — `--ensure` doesn't splice CLAUDE.md in marker-absent case (it refuses), and marker-present cases run on already-bootstrapped repos where the race window is narrower (refresh writes are bounded by `--update` and `--ensure` paths the current flock discipline already covers via terminal `cortex init`'s lock).

**Why not pure Approach D (drop spec.md:5 promise + lazy EF).** Pure D dropped the auto-bootstrap promise *and* introduced lazy-EF machinery. This recommendation only does the first. The lazy-EF surface area (G fence splice + E5 auth template + F1/F2 marker-related gitignore lines triggered on first feature use) is unnecessary if `--ensure` refuses to bootstrap atomically — the splice happens once at terminal init for terminal-first users, and never at all for plugin-first users (who must run terminal init before lifecycle work). Smaller diff, smaller test surface.

**Why not route host-scope writes through `/plugin install`.** Verified in gap 1: no install-time execution handler exists in Claude Code's plugin model. Plugin SessionStart hooks *could* mechanically do it (hooks run unsandboxed), but no surveyed plugin does so, and the silent-write-from-hook pattern relocates rather than solves the opacity problem.

## Contract change: spec.md:5 auto-bootstrap promise

The `auto-apply-cortex-init-at-lifecycle` spec.md:5 promised: "Brand-new clean repos (no `cortex/` directory) also bootstrap automatically on first `/lifecycle` invocation." That promise was made during refine on 2026-05-27 (commit `8bb1bc2e` landed APPROVED that day), before the relevance of the Feb 2026 sandbox lockdown to the `~/.claude/.settings.local.json.lock` write path was understood.

This recommendation drops that promise. Bootstrap is a deliberate terminal action.

The honest characterization: the original refine phase modeled the in-session host-scope write as feasible because spec R4(1)'s acceptance criterion ("`cortex init --ensure` in a clean scratch repo (no `cortex/`) exits 0 and writes `cortex/.cortex-init`") would have required it. The acceptance test passed against in-process pytest invocations that bypass sandbox; the in-session sandbox-blocked path wasn't exercised. The discovery is that the promise was made on incomplete evidence.

This is closer to a "deliberate contract revision based on new evidence" than to an unplanned-redo of the auto-init-and-update lifecycle. The replacement contract is smaller and clearer: `--ensure` is refresh-only; bootstrap is terminal.

Documentation updates required:

- `README.md:27`: change `cortex init` from `# 3. OPTIONAL` to required.
- `docs/index.html` (landing page): change "Start here" path to include `cortex init` before `/lifecycle`.
- `docs/setup.md`: already correct (lines 20-22, 94-96).
- `auto-apply-cortex-init-at-lifecycle/spec.md`: amend R4(1) acceptance criterion to "marker-absent + cortex/-absent in-session: exits 2 with terminal-directive message" (or note the contract revision via a new lifecycle).

## Codebase Analysis

### Three-way load-bearing decomposition (per gap 2)

| # | Action | Class | Citation | Status under recommendation |
|---|--------|-------|----------|------------------------------|
| A | Repo-root resolution + submodule refusal | **EP** | `handler.py:74-99` | Unchanged |
| B | Symlink-safety gate | **EP** | `scaffold.py:207-267` | Unchanged |
| C | Malformed-settings pre-flight | **EP** for terminal; **dropped** for `--ensure` | `settings_merge.py:422-446` | Removed from `_run_ensure` |
| D | Decline gates (R6, R19) | **EP** | `scaffold.py:162-204` | Unchanged |
| E1 | Scaffold `cortex/lifecycle.config.md` | **EP** | 7+ runtime readers | Unchanged; terminal-only when bootstrapping |
| E2 | Scaffold `cortex/requirements/project.md` | **EP path / CO body** | `requirements-write` target | Unchanged |
| E3 | Scaffold `cortex/backlog/README.md` | **CO** | No runtime reader | Drop (template removal) |
| E4 | Scaffold `cortex/lifecycle/README.md` | **CO** | No runtime reader | Drop (template removal) |
| E5 | `claude_md_authorization.md` template | **EF** | Required by G | Unchanged; terminal-only when bootstrapping |
| F1 | `.gitignore` `cortex/.cortex-init` | **EF** | Required by `--ensure` | Unchanged; written by terminal init |
| F2 | `.gitignore` `cortex/.cortex-init-backup/` | **EF** | Required by `--force` | Unchanged; written by terminal init |
| F3 | `.gitignore` `.claude/worktrees/` | **EP** | Default sub-agent isolation | Unchanged; written by terminal init |
| G | CLAUDE.md fence splice | **EF** | `EnterWorktree` auto-enter | Unchanged; written by terminal init |
| H | `~/.claude/settings.local.json` allowWrite | **EP** | Interactive parallel sub-agent dispatch | Written by terminal init only; `--ensure` never touches |
| I | Stale "cortex-worktrees" expunge | **CO** | Migration dead-code | Drop from `--ensure`; keep on terminal `--update` |

The recommendation drops E3 and E4 (the README stubs with no runtime reader) and removes H + C + I from the `--ensure` path. Everything else is unchanged.

### Sandbox semantics confirmed

The Claude Code sandbox allowOnly list includes "." (the current working directory) by default. Writes within the working directory — including `<repo>/CLAUDE.md`, `<repo>/.gitignore`, `<repo>/cortex/...` — are sandbox-permitted without any `~/.claude/settings.local.json` allowWrite entry. The host-scope grant is needed for *parallel sub-agent worktree dispatch* (which writes under `.claude/worktrees/{task}/` relative to a sub-agent's own working directory, not the user's session CWD) and to prevent prompt storms on the same paths across many sessions.

This is why H stays load-bearing for parallel-dispatch but is *not* load-bearing for sequential repo-scope writes: the latter would work with prompts; the former is uninhabitable with prompts.

## Web & Documentation Research

### Live `EnterWorktree` schema (May 2026)

Unchanged: "Use this tool ONLY when explicitly instructed to work in a worktree — either by the user directly, or by project instructions (CLAUDE.md / memory)." Source: `github.com/Piebald-AI/claude-code-system-prompts/blob/main/system-prompts/tool-description-enterworktree.md`.

### Claude Code plugin install model (verified May 2026, gap 1)

`/plugin install` is clone-and-register with no install handler. SessionStart hooks run unsandboxed but no surveyed plugin uses them for settings mutations. The hybrid plugin-shells-to-wheel pattern (Pattern C, already used in `cortex-worktree-create.sh:34-37`) is the validated industry shape. The wheel-as-write-actor for `~/.claude/settings.local.json` is structurally necessary.

Sources: `https://code.claude.com/docs/en/plugins`, `https://code.claude.com/docs/en/plugins-reference`, `https://code.claude.com/docs/en/discover-plugins`, `https://code.claude.com/docs/en/sandboxing`.

### Project documentation contradictions (gap 3)

- `README.md:27`: `cortex init` marked `# 3. OPTIONAL`. **Wrong; needs fix as part of this recommendation.**
- `docs/setup.md:20-22, 94-96`: `cortex init` marked required. Correct.
- `docs/index.html:6659-6671` (landing page): "Start here" path is `/plugin install cortex-core` + `/lifecycle`; mentions `cortex init` only on the overnight card. **Misleading; needs fix.**

## Domain & Prior Art

### Hybrid plugin + companion CLI pattern (validated)

`cortex-worktree-create.sh:34-37` already does plugin-shells-to-wheel. This recommendation extends the existing pattern: the lifecycle skill (plugin-resident) shells out to the wheel-resident `cortex-lifecycle-init-ensure`, which performs only repo-scope writes. The host-scope write remains the wheel's terminal-init responsibility.

### Industry alignment

`/plugin install` Will-install preview, ccstatusline TUI install, and VS Code Workspace Trust (folder-scoped) all share the property that host-state mutations happen at moments of explicit user intent. This recommendation aligns: terminal `cortex init` is explicit user intent; `cortex init --ensure` from inside Claude Code is implicit AI delegation. The host-state mutation belongs to the former, not the latter.

## Feasibility Assessment

| Aspect | Cost | Risk |
|--------|------|------|
| Code change in `_run_ensure` | 3 method calls dropped from handler.py | None — removing optional ceremony |
| Tests | Update `test_handler_ensure.py` case (iii) expectation: rc=2 + stderr message instead of rc=0 + scaffold | Small; existing test scaffolding accommodates |
| Lifecycle skill wire-up | One stanza addition in `plugins/cortex-core/skills/lifecycle/SKILL.md` Step 2 to surface exit-2 message and halt | Small; existing exit-code handling pattern |
| Migration | None — existing v2.14.x users have their entries; `--ensure` will pass-through silently | None |
| Docs | README.md line edit; docs/index.html landing-page edit | Small |
| Spec amendment | `auto-apply-cortex-init-at-lifecycle/spec.md` R4(1) acceptance criterion needs revision | Small; either inline amendment with rationale or a follow-on lifecycle |

Effort estimate: **S** (≤1 day's work to land in cortex-command + supporting docs).

## Architecture

### Pieces

- **Terminal `cortex init` write surface (EP-complete)**: 6 actions + 1 template + 3 empty cortex subdirs + .gitignore + CLAUDE.md fence + `~/.claude/settings.local.json` registration. Unchanged.
- **In-session `cortex init --ensure` write surface (refresh-only, repo-scope)**: refresh cortex/ content + marker on hash drift. Refuse on marker-absent. Never touches `~/.claude/`.
- **Lifecycle skill Step 2**: invoke `cortex-lifecycle-init-ensure`; on exit 0, proceed; on exit 2 with stderr message, halt and surface the message.
- **Docs**: README.md + docs/index.html updated to make `cortex init` the explicit first step.

### How they connect

A new adopter installs cortex-command via `uv tool install` (terminal, no sandbox). Follows the corrected README/landing-page guidance to run `cortex init` in their terminal — full scaffold + host-scope registration happens, all with explicit user intent. Subsequent Claude Code sessions in that repo invoke `/lifecycle`; Step 2's `cortex-lifecycle-init-ensure` finds the marker present and refreshes content if drifted, never touching `~/.claude/`. No sandbox-bypass retry, ever.

A plugin-first adopter (who skipped the README) installs `cortex-core` via `/plugin install`, runs `/lifecycle` in a fresh repo. `cortex-lifecycle-init-ensure` finds no marker, exits 2 with stderr saying "run `cortex init` in your terminal." The lifecycle skill surfaces this to the user, who runs the terminal command and re-invokes `/lifecycle`. One-time friction; never an opaque sandbox retry.

## Decision Records

**The recommendation is grounded.** The four-approach symmetric framing of round 2 was theater; the evidence pointed to a single recommendation and the artifact's own machinery eliminated three of the four. This rewrite names the recommendation and stops pretending the choice is open.

**The recommendation is smaller than what either round's "preferred" approach proposed.** Round 1's D included declare-preview-confirm UX + lazy EF creation. Round 2's nominal symmetry surfaced even more variations. This recommendation does *just* the `_run_ensure` host-scope-write removal + the docs fix + the lifecycle skill wire-up. Preview UX is a defensible follow-up but not necessary; lazy EF machinery is unnecessary because `--ensure` refusing to bootstrap means EF triggers always run from terminal init.

**The contract change is explicit, not buried.** spec.md:5's auto-bootstrap promise is being revised. The recommendation says so plainly and proposes the amendment path (either inline rationale or a follow-on lifecycle). The Philosophy of Work principle ("a scoped phase of a multi-phase lifecycle is not a stop-gap") is honored by treating this as a deliberate spec revision based on post-ship evidence, not as a silent re-do.

**Memory/ alternative remains dead.** Verified in gap 1 and prior failure-of-alternative.

**`/plugin install` routing remains infeasible.** No install handler exists; SessionStart-hook silent-writes are unprecedented and architecturally regressive.

**The atomic_write race in `ensure_claude_md_authorization`** (critical-review R1-#2, downgraded to B) is a real implementation concern but is bounded by the terminal-only execution of CLAUDE.md fence splices under this recommendation. Concurrent terminal `cortex init` invocations on the same repo are already serialized by the existing flock on `_acquire_lock` in `settings_merge.py`. No additional locking needed.

## Open Questions

These are genuine implementation-time decisions for the spec phase, not unresolved research questions:

1. **Lifecycle skill exit-2 handling.** When `cortex-lifecycle-init-ensure` returns exit 2 with the terminal-directive message, should the lifecycle skill halt at Step 2 and emit the message to stdout for the user, or also AskUserQuestion-prompt the user to confirm they'll run terminal init and then re-invoke? Likely the simpler stdout-and-halt pattern.

2. **Migration of stale "cortex-worktrees" expunge.** Currently fires on `--update`. Under the recommendation, it stays there but is no longer attempted from `--ensure`. Existing users get the expunge whenever they next run terminal `cortex init --update`; new users never had the stale entries. Acceptable as-is.

3. **Spec amendment venue.** Inline amendment to `auto-apply-cortex-init-at-lifecycle/spec.md` with rationale + commit-message linkage, vs. opening a follow-on lifecycle that explicitly retracts spec.md:5. Inline is faster; lifecycle is more aligned with the project's solution-horizon principle. Recommend lifecycle if implementation lands in a new release cycle; inline if amendment happens in the same release as this fix.

4. **README + landing-page edit scope.** Beyond `cortex init` correctness, the landing-page "Start here" path could surface the wheel install command as well. That's a docs polish question separable from this recommendation.
