# Research: Lifecycle implement — auto-enter worktree, drop the cd handoff

## Codebase Analysis

### Current worktree-interactive flow

`skills/lifecycle/references/implement.md` §1 (lines 16–22): three-option branch picker fires on `main`/`master` via `AskUserQuestion`:
- **Implement on current branch** (demoted in place via prefix warning when `git status --porcelain` is non-empty — the uncommitted-changes guard at line 22)
- **Implement on feature branch with worktree** — proceeds to §1a
- **Create feature branch** — runs `git checkout feature/{slug}` on the main session

§1a (lines 73–186) is the worktree-interactive path:

1. **Liveness check** (78–82): read `cortex/lifecycle/sessions/{slug}.interactive.pid`, run `kill -0` on PID
2. **Overnight guard** (84–90): sidecar `_interactive_overnight_check.sh` — exit 0/1/2 routing
3. **Worktree creation** (92–99): direct Python call `create_worktree(feature="interactive-{slug}", base_branch="main")`
4. **Pre-flight settings check** (103–153): verify worktree base in `~/.claude/settings.local.json::sandbox.filesystem.allowWrite` and `additionalDirectories`
5. **Variant A active** (155–169): capture `_origin_pwd=$(pwd)`, then `cd $(cortex-worktree-resolve interactive/{slug})`; emit `interactive_worktree_entered` event via `cortex-lifecycle-event log`
6. **Handoff message** (171–183): announces worktree path, branch, "Variant A active — orchestrator session has cd'd into the worktree." Variant B (`claude --worktree={path}` fresh session) documented as "considered but not taken"
7. Continue to §2 (185): lifecycle does not exit; task dispatch proceeds from inside the worktree

### Worktree creation chokepoint

`cortex_command/pipeline/worktree.py`:

- `create_worktree(feature, base_branch="main", repo_path=None, session_id=None)` (226–346) — returns `WorktreeInfo(feature, path, branch, exists)`. Idempotent: returns existing valid worktree without error
- Same-repo default: `$TMPDIR/cortex-worktrees/interactive-{slug}/` via `resolve_worktree_root()` (163–224). Path priority: `CORTEX_WORKTREE_ROOT` env > sentinel-suffix entry `<path>#cortex-worktree-root` in `settings.local.json::sandbox.filesystem.allowWrite` > `$TMPDIR` default
- Branch resolution: `_resolve_branch_name(slug, repo, prefix="interactive")` → `interactive/{slug}` (collision-suffixed)
- Post-creation (333–344): copies `.claude/settings.local.json` into worktree; symlinks `.venv`
- `cleanup_worktree(feature, branch, force=False)` (349–418) — idempotent removal; `force=False` is the interactive path's hard rule

### Kept-pauses inventory + parity test

`skills/lifecycle/SKILL.md` lines 189–201, inventory entry `skills/lifecycle/references/implement.md:22` — "branch selection on main: trunk vs feature-branch-with-worktree vs feature branch."

`tests/test_lifecycle_kept_pauses_parity.py`:
- **Direction 1** (lines 121–164): every inventory entry resolves to a real `AskUserQuestion` call within ±35 lines (or, for `phase-exit pause` entries, a step heading within ±35 lines)
- **Direction 2** (lines 193–253): every `AskUserQuestion` site in `skills/lifecycle/` and `skills/refine/` has a matching inventory entry within ±35 lines
- Assertion shape: `assert not violations, "\n".join(violations)` (190)

### Complete-phase teardown

`skills/lifecycle/references/complete.md`:
- Step 3 (27–43): Variant A advisory detection — `cd-in-then-out` pattern around `/cortex-core:pr` calls when the lifecycle is running from inside the worktree
- Step 8 (175–196): Cleanup hard guard at 177–181 — refuses to run when `realpath "$PWD"` matches the worktree path: "cd out of the worktree before running cleanup; current PWD is the worktree being removed. Do not auto-cd. The user must exit the worktree and re-invoke."
- Cleanup gate (185–196): prefix check (`interactive/` only), dirty-state guard via `git status --porcelain --ignored=traditional`, non-ancestor guard via `git merge-base --is-ancestor`, then `cleanup_worktree(slug, branch=f"interactive/{slug}", force=False)`

### `lifecycle.config.md`

Current schema (frontmatter only): `type`, `test-command`, `skip-specify`, `skip-review`, `commit-artifacts`, `synthesizer_overnight_enabled`, `demo-commands`. Only `synthesizer_overnight_enabled` is actively read (by `cortex_command/overnight/cli_handler.py:57–97`). No per-feature override field exists. Multiple ad-hoc parsers consume the file: `cli_handler.py:58`, `skills/critical-review/SKILL.md:38`, `complete.md:9`, `skills/morning-review/references/walkthrough.md:88`, `plan.md:17` — no shared `read_lifecycle_config()` primitive.

### Backlog frontmatter

`cortex/backlog/*.md` schema includes `complexity`, `criticality`, `lifecycle_phase`, `lifecycle_slug`, `spec`, `areas`, `tags`. Update helper `cortex_command/backlog/update_item.py` handles arbitrary field insertion via atomic tempfile + `os.replace`. A per-feature `branch_mode: trunk-only` override field would be a one-line addition to the schema with no code changes to the update helper.

### `EnterWorktree`/`ExitWorktree` mentions

`docs/internals/sdk.md:207–222` — "SDK Primitives Not Used" table. Row 216: `EnterWorktree` / `ExitWorktree` | `isolation: "worktree"` on Agent is the safe path in sandbox. **No other references** to `EnterWorktree` or `ExitWorktree` in `*.md` or `*.py` files. The rationale is framed in the surrounding section's context of overnight Agent dispatch.

### Sandbox + sentinel-suffix registration

`cortex init` (`cortex_command/init/handler.py:194–234`) registers `cortex/` umbrella in `sandbox.filesystem.allowWrite`. The sentinel-suffix scheme `<path>#cortex-worktree-root` is a structural marker parsed by `_registered_worktree_root()` (119–160).

### Subagent worktree creation hook

`claude/hooks/cortex-worktree-create.sh`:16 reads `cwd` from JSON input. Line 58: `(cd "$CWD" && git worktree add "$WORKTREE_PATH" -b "$BRANCH" HEAD)`. The `HEAD` resolution is CWD-relative — if main session is inside `interactive/{slug}` when this fires, sub-agents branch from the in-progress feature branch, not main.

### Files that would change under each approach

- **Approach A (`EnterWorktree`)**: `implement.md` §1v (155–185); `complete.md` Step 3 (27–43) Variant A detection becomes always-true; Step 8 hard-guard interaction needs new contract; `sdk.md:216` row flipped; `CLAUDE.md` authorization clause; subagent hook `cortex-worktree-create.sh:58` needs base-branch override
- **Approach C (`branch-mode` config)**: `lifecycle.config.md` schema addition; `implement.md` §1 short-circuit; `SKILL.md:199` inventory entry (conditional); `tests/test_lifecycle_kept_pauses_parity.py` conditional-pause sentinel; centralized parser `cortex_command/lifecycle_config.py` (recommended)

## Web Research

### `EnterWorktree` and `ExitWorktree` — Anthropic's framing

[Official tools reference](https://code.claude.com/docs/en/tools-reference) classifies both tools as built-in, permission-required = `No`, and **explicitly "Not available to subagents"**. This is the load-bearing fact: Anthropic positions `EnterWorktree` / `ExitWorktree` as the *interactive main-session counterpart* to `Agent({isolation: "worktree"})`. The sdk.md:216 "Not Used" rationale ("isolation: 'worktree' on Agent is the safe path in sandbox") is therefore genuinely overnight-Agent-specific — there is no documented Anthropic concern about interactive use.

### `EnterWorktree` tool description (verbatim, ccVersion 2.1.133)

Source: [Piebald-AI/claude-code-system-prompts mirror](https://raw.githubusercontent.com/Piebald-AI/claude-code-system-prompts/main/system-prompts/tool-description-enterworktree.md):

- **Gating rule**: "Use this tool ONLY when explicitly instructed to work in a worktree — either by the user directly, or by project instructions (CLAUDE.md / memory)."
- **When to use**: literal "worktree" word in user input OR a CLAUDE.md/memory directive
- **When NOT to use**: "Never use this tool unless 'worktree' is explicitly mentioned by the user or in CLAUDE.md / memory instructions"
- **Requirements**: must be in a git repository OR have `WorktreeCreate`/`WorktreeRemove` hooks configured; **"Must not already be in a worktree"** (precondition)
- **Behavior — default**: creates worktree inside `.claude/worktrees/`, branches from `origin/<default-branch>` (or local HEAD via `worktree.baseRef: "head"` setting), switches CWD
- **Behavior — `path=` mode** (added in v2.1.105): "switches into a worktree that already exists (e.g., one you just created with `git worktree add`). The path must appear in `git worktree list` for the current repository — paths that are not registered worktrees of this repo are rejected"

### `ExitWorktree` tool description (verbatim, ccVersion 2.1.72)

Source: [Piebald-AI mirror](https://raw.githubusercontent.com/Piebald-AI/claude-code-system-prompts/main/system-prompts/tool-description-exitworktree.md):

- **Behavior**: "Restores the session's working directory to where it was before EnterWorktree. **Clears CWD-dependent caches (system prompt sections, memory files, plans directory) so the session state reflects the original directory**. If a tmux session was attached to the worktree: killed on `remove`, left running on `keep`. Once exited, EnterWorktree can be called again to create a fresh worktree."
- **Scope clause (critical)**: "This tool ONLY operates on worktrees created by EnterWorktree in this session. It will NOT touch: Worktrees you created manually with `git worktree add`, **Worktrees from a previous session (even if created by EnterWorktree then)**"

The scope clause is the load-bearing constraint: a worktree created by `cortex_command.pipeline.worktree.create_worktree()` (programmatic `git worktree add`) is excluded from `ExitWorktree` even if the current session entered it via `EnterWorktree(path=...)`. Cross-session resumes are excluded a fortiori.

### Sandbox / CWD interaction

The [official sandboxing doc](https://code.claude.com/docs/en/sandboxing) **does NOT mention** `EnterWorktree`, `--worktree`, or worktrees. Documented behaviors:

- Default `allowWrite` set includes CWD + descendants + `getClaudeTempDir()` (community source-code analysis at `cablate/claude-code-research`, [phase-06](https://github.com/cablate/claude-code-research/blob/2c5df191/source-code-analysis/phase-06-security-permissions/06-sandbox-mechanism.md))
- Settings array semantics: `allowWrite` entries from managed/user/project/local scopes are **merged**, not replaced
- The cortex `cortex/` umbrella `allowWrite` entry covers descendants — including a default-location worktree (under repo root) but NOT a `$TMPDIR/cortex-worktrees/` placement

**Critical undocumented behavior**: whether the sandbox set is **recomputed mid-session** when CWD changes via `EnterWorktree`. No Anthropic doc addresses this. Empirical verification required.

### Known issues bounding the design space

- [#48967](https://github.com/anthropics/claude-code/issues/48967) — `EnterWorktree` default placement at `.claude/worktrees/<name>/` breaks slash-command and skill discovery (Claude Code misidentifies the project root). **Workaround**: use `EnterWorktree(path=<outside-.claude>)`. Direct hit on cortex's skill-heavy framework — auto-enter must use `path=` mode pointing outside `.claude/`
- [#27881](https://github.com/anthropics/claude-code/issues/27881) — Closed not-planned. `EnterWorktree` from a CWD-drifted state creates nested worktrees
- [#39277](https://github.com/anthropics/claude-code/issues/39277) — `PostToolUse: EnterWorktree` hook doesn't fire when worktree is created via `claude -w`. Confirms `--worktree` flag and in-session `EnterWorktree` are different code paths
- [#30906](https://github.com/anthropics/claude-code/issues/30906) — `claude --resume` resets CWD to repo root regardless of prior worktree CWD. Auto-re-enter on resume requires explicit detection
- [#28287](https://github.com/anthropics/claude-code/issues/28287) — Deletion of worktree CWD mid-session breaks session permanently
- [#15776](https://github.com/anthropics/claude-code/issues/15776) + [#27678](https://github.com/anthropics/claude-code/issues/27678) — Session history keyed by filesystem path; `/resume` fragments across worktrees. In-session conversation history survives `EnterWorktree`; cross-session resume does not

### `--worktree` (`-w`) flag — verified

[Official worktrees doc](https://code.claude.com/docs/en/worktrees): supported. Branches from `origin/<default-branch>` by default; `worktree.baseRef: "head"` setting flips to local HEAD. Does NOT support arbitrary base branches (issues #27876, #35730 still open). `path=` parameter is exclusive to in-session `EnterWorktree`. Trust-dialog acceptance required first-time per repo.

### Community prior art

- [auto-worktree](https://github.com/kaeawc/auto-worktree), [claude-worktree (PyPI)](https://pypi.org/project/claude-worktree/), [claude-worktree-hooks](https://github.com/tfriedel/claude-worktree-hooks) — all replace the `claude` invocation; none auto-enter mid-session
- **No prior art found** for auto-`EnterWorktree` from within a running Claude Code session. The pattern would be novel

### Memory and CLAUDE.md across `EnterWorktree`

- Auto-memory: "all worktrees and subdirectories within the same git repository share one auto memory directory" — persists across the boundary
- CLAUDE.md: re-walks upward from new CWD on `EnterWorktree`; same root CLAUDE.md hits, plus any new ones in worktree subtree
- `CLAUDE.local.md` does NOT transfer; use `@~/.claude/...` import

### Changelog timeline

- v2.1.49: `--worktree`/`-w` flag + subagent worktree isolation
- v2.1.50: `WorktreeCreate`/`WorktreeRemove` hook events
- v2.1.69: `workspace.git_worktree` in statusline JSON
- v2.1.72: `ExitWorktree` tool
- v2.1.105: `path=` parameter on `EnterWorktree`
- v2.1.125 / .128 / .133: `worktree.baseRef` setting

## Requirements & Constraints

### ADR-0003: Per-repo sandbox registration (accepted)

`cortex/adr/0003-per-repo-sandbox-registration.md`: `cortex init` registers the repo's `cortex/` umbrella into `~/.claude/settings.local.json::sandbox.filesystem.allowWrite` using `fcntl.flock`. Establishes that the sandbox boundary is **per-repo, additive, centered on `cortex/`**.

### ADR-0004: Multi-step Complete + interactive worktree lifecycle (proposed)

`cortex/adr/0004-multi-step-complete-and-interactive-worktree-lifecycle.md` — **proposed, not yet accepted**. Two load-bearing clauses:

- **"WorktreeCreate-hook bypass is intentional and permanent."** Lifecycle's `create_worktree()` calls `git worktree add` programmatically, bypassing Claude Code's `--worktree` launch flow. This is by design because the overnight runner cannot use `--worktree`. "A future refactor that re-routes lifecycle worktree creation through the hook would require updating all hook responsibilities and all callers, and would introduce a dependency on Claude Code's internal `--worktree` launch flow that the overnight runner cannot use."
- **PATH bootstrap migrated to `SessionStart` hook** (`claude/hooks/cortex-session-start-path-bootstrap.sh`)

### project.md philosophy

- **Multi-step lifecycle phases**: re-invocation is state-aware and idempotent (lines 25–27); the Complete phase is the canonical example
- **Kept user pauses come in two kinds**: (a) `AskUserQuestion` sites; (b) phase-exit re-invocation gates. Enforced by `SKILL.md` inventory + parity test (27–28)
- **Complexity must earn its place**; "When in doubt, simpler wins" (19)
- **Defense-in-depth for permissions**: `settings.json` ships minimal allow; sandbox is the critical surface (48). Interactive sessions inherit parent permission model — no `--dangerously-skip-permissions`
- **Destructive operations preserve uncommitted state** (49) — cleanup scripts SKIP on uncommitted state
- **CLAUDE.md "Skill / phase authoring guidelines"**: "Prefer structural separation over prose-only enforcement for sequential gates. A gate encoded in skill control flow is harder to accidentally bypass than one that relies on the model reading and following a prose instruction. Prose-only enforcement is appropriate only for guidelines where the cost of occasional deviation is low."
- **MUST-escalation policy**: requires evidence artifact for any new MUST/CRITICAL/REQUIRED phrasing

### multi-agent.md: Seatbelt `.mcp.json` deny

Same-repo worktrees live under `$TMPDIR/cortex-worktrees/` because "the Seatbelt mandatory deny on `.mcp.json` (enforced by Anthropic's `sandbox-runtime`, below user-level `sandbox.filesystem.allowWrite`) blocks `git worktree add` from checking out `.mcp.json` into any path under the `.claude/` deny scope" (74–77). This is the hard technical reason behind `$TMPDIR` placement.

### Overnight tool allowlist

`docs/overnight-operations.md` lines 116–133: overnight task agents receive `allowed_tools = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]`. `Agent`, `Task`, `EnterWorktree`, `ExitWorktree`, `AskUserQuestion`, `WebFetch`, `WebSearch` are absent — cannot be invoked. Any auto-enter design is therefore interactive-only by construction; the overnight path retains the current `Agent(isolation: "worktree")` mechanism.

### Parity test contract

`tests/test_lifecycle_kept_pauses_parity.py`:
- Phase-exit pauses are validated via step-heading lookup when the inventory rationale contains `"phase-exit pause"` (137–164)
- All other inventory entries are validated against `AskUserQuestion` call sites within ±35 lines
- **No "conditional pause" sentinel exists today** — a pause that fires only when a config flag is unset cannot be expressed under the current contract

## Tradeoffs & Alternatives

Four mechanisms weighed across implementation complexity, maintainability, performance, and alignment.

### Approach A — `EnterWorktree(path=...)` mid-session

The ticket's proposed mechanism. After `create_worktree()` materializes the worktree, the skill invokes `EnterWorktree(path=<resolved-path>)` instead of `cd`. Same session continues; conversation history persists; CWD-dependent caches reload (system prompt, memory files, plans dir).

- **Implementation complexity**: medium. Rewrite `implement.md` §1v–§1vi to drop the cd-and-handoff form. Retire Variant A/B narrative. `sdk.md:216` row flipped from "Not Used" to "Used (interactive-only)". `CLAUDE.md` authorization clause needed to satisfy the tool's gating rule
- **Maintainability**: couples to a platform primitive whose gating language may harden. The `path=` parameter is recent (v2.1.105); platform-evolution risk
- **Performance**: best of the four — no subprocess fork, no re-onboarding, same SDK process
- **Alignment**: requires updating sdk.md; introduces a primitive dependency the project's own internals doc currently disclaims

### Approach B — Honor sdk.md, keep `cd`, smooth the handoff

Keep §1v's cd; ship a `cortex-lifecycle-resume <slug>` console script that the handoff message asks the user to paste. The mid-session cd is unchanged; only Variant B's relaunch ergonomics improve.

- **Implementation complexity**: lowest. Console script + handoff copy rewrite
- **Maintainability**: highest. Zero coupling to platform primitives
- **Performance**: unchanged (Variant A already preserves the session)
- **Alignment**: honors sdk.md verbatim. **But does not address the ticket's stated primary friction** (picker re-decision, A/B variant copy) — only touches Variant B ergonomics

### Approach C — `lifecycle.config.md` `branch-mode` default

Add `branch-mode: worktree-interactive | trunk | feature-branch` field. When set, the picker is suppressed at runtime; the configured mode is used. Picker remains in code as fallback when the field is unset.

- **Implementation complexity**: low–medium. Schema addition + short-circuit in skill prose + parity-test work
- **Maintainability**: high. Uses existing config surface; no platform coupling
- **Performance**: unchanged
- **Alignment**: passes complexity-earns-its-place; externalizes a known need the ticket itself surfaces. **Touches kept-pauses inventory** — the load-bearing risk: the picker's call site stays but the user no longer experiences the pause. The current parity test cannot detect this semantic-vs-syntactic drift

### Approach D — `claude --worktree=` wrapped console script

Collapses to Approach B once the actual `--worktree` flag semantics are checked: the flag only branches from `origin/HEAD` (or local HEAD), cannot enter an arbitrary existing worktree at an arbitrary path. `path=` is exclusive to in-session `EnterWorktree`. Approach D therefore reduces to `cd <existing-worktree> && claude` — identical to B.

### Approach 4-agent recommendation

**C first (low-risk, contained), then A (drops handoff fully).** Together they ship all four UX wins the ticket enumerates: no picker re-decision, no cd/relaunch, no A/B copy, trunk-safe override preserved. C is standalone-valuable; A subsumes the Variant A/B narrative and the cd-in-then-out gymnastics in complete.md.

### Cross-cutting kept-pauses constraint

Both C and A touch the kept-pauses inventory at `SKILL.md:199`. Under C the picker is conditionally suppressed; under A the picker survives but the cd handoff narrative below it is rewritten. Per CLAUDE.md "Skill / phase authoring guidelines": "Prefer structural separation over prose-only enforcement for sequential gates" — conditionally-suppressed pauses are precisely the prose-only failure mode the principle warns against unless the parity test gains a "conditional pause" sentinel.

## Adversarial Review

The adversarial agent loaded the actual `EnterWorktree` / `ExitWorktree` schemas and surfaced three platform-level constraints the tradeoffs framing did not adequately address.

### Schema-level constraints (load-bearing)

**C-1: "Must not already be in a worktree" precondition.** `EnterWorktree`'s requirements include this clause. Re-invocation paths must detect whether the current session is already in the target worktree; a blind call from a resumed session whose user manually `cd`'d in via a separate tmux pane is rejected by the platform. The current §1a liveness check (PID file) does not test "current session is already inside the worktree" — it tests "another session holds the lock."

**C-2: `ExitWorktree` cross-session no-op.** "This tool ONLY operates on worktrees created by EnterWorktree **in this session**. It will NOT touch: Worktrees you created manually with `git worktree add`, **Worktrees from a previous session (even if created by EnterWorktree then)**." The §1a `create_worktree()` path uses `git worktree add` programmatically. So even when `EnterWorktree(path=...)` enters successfully, **`ExitWorktree` is documented as a no-op for that worktree**. Cross-session resume cannot programmatically exit the worktree. The complete-phase hard guard at `complete.md:177` ("cd out of the worktree before running cleanup") becomes structurally unreachable under Approach A — only the user can `cd` out, and the same-session continuation is the design's stated goal.

**C-3: Gating-rule applicability in foreign repos.** "Use this tool ONLY when explicitly instructed by the user OR by CLAUDE.md / memory instructions." cortex-command ships to consumer repos via `plugins/cortex-core/`. The consumer repo's CLAUDE.md does not authorize `EnterWorktree`. cortex-command's own CLAUDE.md authorizes the call only inside cortex-command's own repo. The skill silently no-ops or surfaces a model-level refusal in consumer repos.

### Failure modes

**FM-1: Sandbox CWD-recomputation gap.** No Anthropic doc states the sandbox set is recomputed on CWD change. By symmetry with `ExitWorktree`'s documented cache-clearing (system prompt, memory, plans), the sandbox `allowWrite` array is likely **not** recomputed mid-session. Concrete consequence: §1a's preflight (`implement.md` 103–153) verifies the worktree base is registered at *session-start* but the registered set may not be re-read post-`EnterWorktree`. Write attempts fail at execution time with opaque "Operation not permitted." Material: `cortex_command/init/handler.py:194–234` is the registration chokepoint; if a divergent `CORTEX_WORKTREE_ROOT` is in effect, the operator only learns mid-implementation.

**FM-2: Interactive PID lock concurrency hazard worse than stated.** `cortex_command/interactive_lock.py:_verify_live_owner_with_reason` defaults to **LIVE on every ambiguous case** (R4 rows 3, 4, 8). PID reuse on macOS within ~10-minute windows + SIGKILL'd prior session = false-positive lock collision. Auto-enter increases mean-time-in-worktree, multiplying the exposure. Material: `interactive_lock.py:295` is the silent escalator. Operator must run `cortex-interactive-lock force-release <slug>` manually.

**FM-3: Parity test passes a semantic regression silently under C.** Approach C suppresses the picker at runtime; the call site remains in code. Direction 2 of the parity test still passes (every `AskUserQuestion` site has an inventory entry). Direction 1 still resolves. **The test cannot detect that the user no longer experiences the pause.** The inventory rationale at `SKILL.md:199` describes a pause that no longer fires when `branch-mode` is set — prose-only enforcement of a structurally-removed gate, exactly the failure mode CLAUDE.md "Skill / phase authoring guidelines" warns against.

**FM-4: `branch-mode: trunk` lost-warning footgun under C.** The uncommitted-changes guard at `implement.md:22` demotes the on-current-branch option *in place* with a warning prefix. With the picker suppressed entirely, the demotion never runs. A user with uncommitted changes on main silently lands on trunk implementation with no `"Warning: uncommitted changes in working tree — this will mix them into the commit on main."` prefix. Behavioral regression. The right shape: the picker fires regardless of `branch-mode` when `git status --porcelain` is non-empty.

**FM-5: Complete-phase cleanup structurally trapped under A.** Under Approach A the session is *always* inside the worktree at Complete phase. Complete.md Step 3 (27–43) tries to restore `_origin_pwd`, but on cross-session resume after merge-wait, the variable is lost. Step 8's hard guard (177) fires. The only documented escape (`ExitWorktree`) is a no-op for cross-session worktrees (C-2). User is structurally trapped — they cannot programmatically exit, and the hard guard refuses to auto-cd.

**FM-6: Subagent inherits wrong base under A.** `claude/hooks/cortex-worktree-create.sh:58` runs `(cd "$CWD" && git worktree add "$WORKTREE_PATH" -b "$BRANCH" HEAD)`. Under Approach A the main session's CWD is the `interactive/{slug}` worktree, so `HEAD` resolves to the in-progress feature branch. Sub-agent worktrees branch from in-progress work, not main. Sub-agents inherit half-implemented WIP they were not supposed to see. The implement.md merge-back step still works mechanically but the diff base changes.

**FM-7: Event log writes diverge from lock-file writes under A.** `cortex-lifecycle-event log` uses `_resolve_user_project_root_from_cwd()` — resolves to the worktree's tree from inside it. Lock files use `_resolve_user_project_root` — always resolves to the main repo. Under Variant A this divergence is brief (a single cd); under auto-enter the entire implement phase writes events to the worktree-local `cortex/lifecycle/{slug}/events.log`, which is **deleted with the worktree on cleanup**. Material: implementation events disappear on merge.

**FM-8: Novel-pattern migration risk.** No prior art for auto-enter mid-session. Anthropic's gating language is hardening, not softening, in 2026 platform releases. If they later interpret "explicitly instructed by ... CLAUDE.md" more literally, every cortex auto-enter call silently no-ops. The skill cannot inspect the model's current gating interpretation.

### Security concerns

**SC-1: Sentinel-suffix privilege expansion.** `_registered_worktree_root` (worktree.py 119–160) is a single-string-match gate (`#cortex-worktree-root` suffix). A malicious or buggy config installer could redirect worktree creation to a sensitive directory; auto-enter moves the live session into it without a confirmation step. The current cd handoff at least surfaces the path in the handoff message; auto-enter does not.

**SC-2: `.claude/worktrees/` default conflict.** Even with `path=` mode, mid-session entry may re-detect the project root. Issue #48967 documents that `.claude/worktrees/` placement breaks skill discovery; if `path=` mode triggers the same re-detection path, **the session bricks itself for further skill invocations**, including `/cortex-core:lifecycle complete <slug>`.

**SC-3: Lock leak under SIGKILL multiplied by auto-enter.** The session-time inside the worktree increases; SIGKILL-stranded locks become more frequent in the operator workflow.

### Adversarial verdict

**Ship C alone first; defer A until upstream constraints relax or are negotiated.** The C-then-A sequence is correct in principle but A's three platform-level constraints (C-1, C-2, C-3) plus FM-5 (cleanup trapped) substantially weaken the Approach A spec until either:
- Anthropic extends `ExitWorktree` scope to cross-session `path=` worktrees, or
- cortex-command files the upstream issue and operates with `claude` relaunch as the documented escape, or
- The complete-phase cleanup design changes to not require an inside→outside transition

C alone delivers two of the four UX wins (no picker re-decision, trunk-safe override preserved). A delivers the other two but trades them for a structural trap on cleanup. The right call is C now, with the conditional-pause parity-test work as a first-class deliverable, and a backlog ticket capturing the upstream-coordination work A needs before it can ship safely.

### Recommended mitigations carrying into Spec

- **M-1**: Order is C alone; defer A pending upstream coordination
- **M-2**: Conditional kept-pause inventory entry + parity-test sentinel (load-bearing)
- **M-3**: Uncommitted-changes guard runs BEFORE config suppression — `branch-mode` does not override the guard
- **M-4**: Centralize `lifecycle.config.md` parsing via `cortex_command/lifecycle_config.py` (recommended; companion follow-up backlog item migrates the five existing ad-hoc parsers)
- **M-6**: Session-already-in-worktree detector (`git rev-parse --show-toplevel` vs. worktree path) before any `EnterWorktree(path=...)` call — defensive guard for any future Approach A work
- **M-7**: If Approach A is later pursued, `cortex init` opt-in step appends an authorization clause to consumer CLAUDE.md
- **M-8**: Parity-test update ships in the same commit as inventory change (CLAUDE.md "update both the SKILL.md inventory and the parity test together")

## Open Questions

These are unresolved after research and surfaced for Spec:

- **Q1 — Scope of this lifecycle.** Does this ticket cover (a) Approach C only (config-defaulted picker + uncommitted-changes carve-out + conditional kept-pause + centralized parser), with a follow-up backlog ticket for upstream-coordination + Approach A; (b) C plus a thin slice of A scoped to cortex-command's own repo only (with consumer-repo coverage deferred); or (c) C plus full A including consumer-repo authorization via `cortex init`? The adversarial review surfaced enough A-specific risks that this scope decision drives the entire spec.

- **Q2 — Conditional kept-pause encoding.** What is the right shape for the inventory entry under C? Options: (a) modify `SKILL.md:199` to read "branch selection on main when `lifecycle.config.md::branch-mode` is unset" and extend `tests/test_lifecycle_kept_pauses_parity.py` with a `conditional pause` sentinel that requires the suppression branch to be reachable in the prose; (b) leave the inventory entry as-is and add a separate test asserting that the suppression path is documented in `implement.md`. The user-visible-pause invariant requires (a) to remain meaningful.

- **Q3 — Uncommitted-changes carve-out.** Confirm: with `branch-mode` set in `lifecycle.config.md`, the picker MUST still fire when `git status --porcelain` is non-empty, preserving the demote-and-warn affordance for the uncommitted-changes hazard. (The adversarial FM-4 makes this normative.)

- **Q4 — Centralized `lifecycle.config.md` parser scope.** Does this lifecycle introduce `cortex_command/lifecycle_config.py` as a centralized primitive (with migration of the five existing ad-hoc parsers as a follow-up ticket), or does it add a sixth ad-hoc parser? The "long-term project / Solution horizon" principle favors centralization; the simplicity defaults favor minimal scope. Pick one and articulate the rationale in the spec.

- **Q5 — Solution-horizon framing.** Was Variant A/B (#240 / #238) deliberately scoped as a first-phase implementation to be followed by auto-enter / config-defaults, or is this lifecycle redesigning recently-shipped work? The user deferred this to research's critical judgment. Research's read: the evidence pattern (Variant A/B shipped + #246's behavior shift naming friction as the lever) is consistent with both framings. The spec should articulate the chosen framing explicitly and update `cortex/adr/0004-*.md` (currently proposed) accordingly — ADR-0004 owns the multi-step Complete + interactive worktree lifecycle and is the right place to record the framing.

- **Q6 — `branch-mode` field schema.** Per-repo only via `lifecycle.config.md`, or also per-feature override via backlog frontmatter? The adversarial review didn't surface a hazard with per-feature override; the simplicity defaults favor per-repo-only as a first cut, with per-feature deferred until a concrete need surfaces.

- **Q7 — sdk.md row treatment.** If C ships alone (no `EnterWorktree` use), the sdk.md:216 row stays unchanged. If a future A work flips it, what's the right rationale text? Suggested: split into two rows — one for overnight Agent dispatch (rationale unchanged) and one for interactive lifecycle (with a forward pointer to the eventual ADR-0004 update).
