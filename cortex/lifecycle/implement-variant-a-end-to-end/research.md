# Research: Implement Variant A end-to-end (interaction model + PR-creation hook)

Implement Variant A of the worktree-interactive lifecycle mode end-to-end: wire `cd $(cortex-worktree-resolve interactive/{slug})` mid-session after worktree creation (with a per-tool-call CWD-refresh mechanism), refactor cwd-relative writer sites to target the worktree post-`cd`, and add a worktree-aware PR-creation hook in the Complete phase. Siblings #239 (worktree lifecycle) and #241 (`interactive.pid` concurrency guards) are already shipped — #240 builds on those primitives.

## Codebase Analysis

### The eight named writer sites — verified state

The ticket's Touch points enumerate eight cwd-relative writer sites. Direct inspection (cited file:line) shows mixed status:

- `cortex_command/refine.py:117` — events.log append. **Bare `Path("cortex/lifecycle")`** (relative to process CWD). Needs refactor.
- `cortex_command/critical_review.py:340-349,375-416,318-322` — events.log append. **Uses private `_git_toplevel()` resolver** (`git rev-parse --show-toplevel`), which from a worktree returns the worktree path. Worktree-correct today but inconsistent with shared resolver.
- `bin/cortex-complexity-escalator:265,296` — events.log path. **argparse `--lifecycle-dir cortex/lifecycle` default** (relative to process CWD). Needs refactor.
- `cortex_command/discovery.py:189-197` — events.log resolution helper. **Bare `Path("cortex/lifecycle")` and `Path("cortex/research")`** (relative). Needs refactor.
- `cortex_command/backlog/update_item.py:445` — backlog dir. **Already calls `_resolve_user_project_root()`** (worktree-aware via env or walk-up).
- `cortex_command/backlog/update_item.py:169` — sidecar `events.jsonl`. **Relative to `item_path.parent`** (worktree-correct if `item_path` is correct).
- `claude/statusline.sh:244-247` — lifecycle-dir lookup. **Reads `workspace.current_dir` from statusline payload** (not process CWD); update-on-`cd` behavior is unverified and platform-dependent.
- `cortex_command/overnight/report.py:52,125` — morning report. **Already calls `_resolve_user_project_root()`**.

### Additional bare-path writer sites (NOT in ticket's Touch points)

Adversarial review surfaced ~30 bare `Path("cortex/...")` literals in `cortex_command/` that the ticket's inventory missed:

- `cortex_command/overnight/report.py:658,674,768,1716` — additional bare `Path("cortex/lifecycle/...")` and `Path("cortex/backlog")` writes.
- `cortex_command/overnight/runner.py:2114` — `Path("cortex/lifecycle/seatbelt-probe.log")`.
- `cortex_command/overnight/daytime_pipeline.py:216-401` — ~5 sites using `cwd / Path("cortex/lifecycle")`. Note: daytime_pipeline is slated for removal in #246, so these may be no-op for #240.
- `cortex_command/overnight/interrupt.py:158`.
- `cortex_command/overnight/smoke_test.py:30-143`.

Many of these are in overnight-runner paths that may not be exercised by interactive-mode flow. **The actual reachable-from-Variant-A surface needs call-graph audit, not grep.**

### The canonical resolver — current contract

`cortex_command/common.py:55-103` is the canonical `_resolve_user_project_root()`:
- Line 81-83: env-first (`os.environ.get("CORTEX_REPO_ROOT")`) — short-circuits without validation.
- Line 86: falls back to `Path.cwd().resolve()` walk-up.
- Line 91-92: stops on `.git` (worktree file or main `.git/` directory) or `cortex/` directory presence.

`cortex_command/tests/test_common.py:55-56` and `tests/test_common_utils.py:486` explicitly assert "Returns `Path(CORTEX_REPO_ROOT)` verbatim when that env var is set." Any change to env-var precedence reverses this assertion. The lifecycle ticket `add-upward-walking-project-root-detection-in-resolve-user-project-root/spec.md` is the source of the current contract.

### SessionStart env injection

`hooks/cortex-scan-lifecycle.sh:15-26` writes `CORTEX_REPO_ROOT=$CWD` into `CLAUDE_ENV_FILE` once at session start (guarded on `$CWD/.git` exists and env unset). **One-shot semantics** — does not re-fire mid-session.

### Sibling primitives — current contracts

**#239 (worktree lifecycle, shipped):**
- `cortex_command/pipeline/worktree.py` exports `resolve_worktree_root(name, session_id)`, `create_worktree(feature, base_branch="main", repo_path, session_id)`, `cleanup_worktree(feature, *, branch, force, repo_path, worktree_path)`.
- `interactive-{slug}` sentinel routes branch to `interactive/{slug}` and path to `$TMPDIR/cortex-worktrees/interactive-{slug}/` (worktree.py:307-312).
- `create_worktree` copies `.claude/settings.local.json` and symlinks `.venv` (worktree.py:336-344).
- Idempotent: returns existing worktree info if already present (worktree.py:260-305).
- `skills/lifecycle/references/implement.md` §1a (lines 73-118) is already wired by #239 to **create** the worktree but does not yet wire the `cd` handoff for Variant A.
- `cortex_command/pipeline/dispatch.py:555-560` deliberately pins `CORTEX_REPO_ROOT` per-dispatch to the worktree (#198 fast-path optimization).
- `cortex_command/overnight/runner.py:2020-2024` sets env from runner's own `repo_path` (defensive against operator-shell drift).

**#241 (concurrency guards, shipped):**
- `cortex_command/interactive_lock.py` writes `interactive.pid` at `_resolve_user_project_root() / "cortex" / "lifecycle" / {slug} / "interactive.pid"`. Docstring (lines 5-7): "Path is always resolved against the main repo root (never CWD-relative)... The CWD ... may be a git worktree under the Variant A interactive model."
- JSON schema: `{magic, session_id, pid, start_time, acquired_at}`. Session_id is `CLAUDE_CODE_SESSION_ID`.
- Liveness: eight-row branch table (env-var authoritative, PID-check fallback). Defaults to LIVE on ambiguity. Session_id rotation on `/clear` is not handled.
- Public API: `acquire_lock`, `release_lock`, `read_lock`, `scan_live_locks`. Console script `cortex-interactive-lock`.
- Already-registered events: `interactive_lock_acquired`, `interactive_lock_rejected_concurrent`, `interactive_lock_stale_recovered`, `interactive_lock_released`, `interactive_overnight_active_rejected`, `feature_skipped_interactive_active`.

### PR-creation today

- `skills/pr/SKILL.md` has **no `-C` or `--worktree` affordance** and explicitly constrains "No `git -C`" (line 92). Inherits session CWD. Uses `git push -u origin HEAD` + `gh pr create`.
- `skills/lifecycle/references/complete.md` §3 invokes `/cortex-core:pr` after pushing branch (line 25); no worktree-aware routing today.
- `skills/lifecycle/references/complete.md` Step 8 (line 159-163) already has a **`realpath "$PWD" == worktree` hard guard** that bails if cleanup is invoked from inside the worktree. This guard composes badly with naive "`cd` in before pr" — the post-merge re-invocation must already be `cd`-ed out.

### Sandbox registration today

`cortex_command/init/handler.py:194-198` (Step 7): `cortex init` registers `<repo>/cortex/` as a single umbrella entry in `~/.claude/settings.local.json`'s `allowWrite`. **`$TMPDIR/cortex-worktrees/` is NOT registered** in either the project or user `settings.local.json`. Tests at `cortex_command/init/tests/test_settings_merge.py:954` confirm "the dual-registration test was structurally tied to a step being retired." A Variant-A session that `cd`s into the worktree and issues a Write tool call to a worktree file may sandbox-fail on first write.

### Sub-agent dispatch — orthogonal CWD

`skills/lifecycle/references/implement.md:146,160` shows §2 uses `Agent(isolation: "worktree")` for per-task sub-agent dispatch. Each sub-agent gets its own `$TMPDIR/cortex-worktrees/{task-name}/`. The orchestrator's `cd` into `interactive/{slug}` does NOT propagate to sub-agents — they are independently rooted. The "interactive/{slug}" worktree is the *merge target* for sub-agent work, not the work surface itself.

### Precedent tickets (#126, #130, #208)

Brief inspection confirms these landed code-layer refactors of writer sites (route through `_resolve_user_project_root()` or thread a `worktree_path` parameter), not prose-only fixes. #130 specifically introduced `backlog_dir` parameter threading in `update_item.py` after report.py writes landed in the home repo as untracked files. Precedent supports a code-layer approach over skill prose.

### Conventions

- Events.log entries are JSONL; helper `_emit_event` exists in `cortex_command/interactive_lock.py:92-102`; other modules write JSON inline.
- New event names must be registered in `bin/.events-registry.md` before backlog `grep -c` gates can reference them.
- Commits use `/cortex-core:commit` skill only (never `git commit` manually).

## Web Research

### Claude Code mid-session `cd` semantics — the decisive finding

**Per official tools-reference docs:**

> "When Claude runs `cd` in the main session, the new working directory carries over to later Bash commands as long as it stays inside the project directory or an additional working directory you added with `--add-dir`, `/add-dir`, or `additionalDirectories` in settings. **Subagent sessions never carry over working directory changes.**" — code.claude.com/docs/en/tools-reference

> "**Environment variables do not persist. An `export` in one command will not be available in the next.**"

Implications:
- Main-session Bash `cd` *does* carry over, but only inside the project dir or registered `additionalDirectories`. The repo's worktree base at `$TMPDIR/cortex-worktrees/` is **outside** the project dir and is **not registered** today (see Codebase Analysis: Sandbox registration).
- Sub-agent Bash `cd` is reset every call.
- `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` is opt-in and would defeat Variant A.

### CwdChanged hook — the documented refresh mechanism

`code.claude.com/docs/en/hooks` documents `CwdChanged`:
- Fires asynchronously on every `cd`.
- Has `CLAUDE_ENV_FILE` access (PreToolUse does not).
- Receives `{old_cwd, new_cwd}` on stdin.
- **`CLAUDE_ENV_FILE` updates take effect on the *next* Bash command** — one-tool-call latency.
- Compound commands like `cd <worktree> && cortex-update-item ...` run the second command *before* CwdChanged's snapshot is sourced. Race condition by design.
- Not currently registered in `plugins/cortex-core/hooks/hooks.json`.

This is the canonical Anthropic mechanism for env-refresh on `cd`. The "per-tool-call CWD-refresh mechanism" framing in #240 has a *documented* upstream answer that the ticket text does not mention.

### Per-tool-call hook capabilities

- `PreToolUse` fires before every tool call. **Cannot mutate env vars for subsequent calls** — outputs only `permissionDecision` / `updatedInput` / `additionalContext`. Confirmed by absence of `CLAUDE_ENV_FILE` in PreToolUse's documented env. Issue #42229 corroborates: env-mutation hooks are SessionStart-class only.
- No `PreBash` or per-Bash hook exists.
- The documented refresh path is `CwdChanged` + `CLAUDE_ENV_FILE`.

### `gh pr create` and worktree semantics

- **`gh pr create` has NO `-C` or `--directory` flag.** Only `-R, --repo` (targets a remote repo, not local directory). The wrapper must either subprocess with `cwd=` or `cd` before invoking.
- `git -C <path>` is standard and reliable; `skills/pr/SKILL.md` explicitly forbids it (line 92).
- `gh pr merge --delete-branch` does NOT clean local worktrees — confirmed by cli/cli#13380 (closed as duplicate of cli/cli#3442, **still OPEN** as of May 2026). From within a worktree, `gh pr merge --delete-branch` partial-fails.

### Sandbox semantics — Seatbelt pinning

- Sandbox profile (Seatbelt on macOS) is computed at process spawn — pinned per-subprocess, not re-evaluated on `cd`.
- `sandbox.filesystem.allowWrite` is merged across managed/user/project/local settings scopes at spawn.
- Issue #29048 reports allowWrite enforcement gaps in bypass mode; #51303/#53891 report sandbox blocking `git worktree add` for `.claude/`-rooted worktrees (mitigated in this repo by routing through `$TMPDIR`).

### Industry pattern: "one task → one branch → one worktree → one agent"

Convergent pattern across Cursor (`/apply-worktree`), Claude Code (`claude --worktree`), OpenCode (`opencode-worktree-session`). Cursor and OpenCode both pivot the agent's CWD to the worktree at session start, not mid-session. The "fresh `claude --worktree` session" pattern (Variant B in upstream research) maps directly to industry convention; mid-session `cd` (Variant A) does not have a documented industry analog.

### Source URLs

- code.claude.com/docs/en/worktrees, hooks, tools-reference, env-vars, sandboxing
- anthropics/claude-code issues: #47017 (no `--cwd`), #22343 (CWD-drift hooks; closer cite is #3583), #25322 (`/cd` request, mid-session unsupported), #19903 (similar), #42229 (direnv via hooks), #39277 (claude -w bypasses EnterWorktree)
- cli/cli issues: #13380, #3442

## Requirements & Constraints

### Lifecycle / Complete phase

- `cortex/requirements/project.md:25` — multi-step lifecycle phases. Complete phase is multi-step with PR open → user-merges-on-GitHub pause → re-invocation finalizes. `feature_complete` event carries `merge_anchor: "review" | "merge"`. Re-invocation routing is state-aware and idempotent.
- `cortex/requirements/project.md:27` — kept user pauses inventory must be updated in `skills/lifecycle/SKILL.md` and `tests/test_lifecycle_kept_pauses_parity.py` when phase sequencing changes.

### Worktree isolation

- `cortex/requirements/multi-agent.md:30,77` — `$TMPDIR/cortex-worktrees/{feature}/` (default repo) with `interactive/{slug}` prefix per #239. Single chokepoint `resolve_worktree_root()`.
- `cortex/requirements/multi-agent.md:23` — per-spawn `--settings <tempfile>` carrying `sandbox.filesystem.{denyWrite,allowWrite}` JSON dict; dispatch allows worktree plus six risk-targeted out-of-worktree writers.
- `cortex/requirements/multi-agent.md:32-34` — worktree creation idempotent; cleanup idempotent and removes branch after merge.

### Observability / path resolution

- `cortex/requirements/observability.md:16,30` — statusline and dashboard inputs include `cortex/lifecycle/*/events.log`, `cortex/lifecycle/overnight-state.json`, per-feature `events.log` and `plan.md`. Path resolution must remain correct post-`cd`.
- `cortex/requirements/observability.md:93` — statusline/dashboard/notifications are read-only with respect to session state files.

### File-based state + sandbox registration

- ADR-0001 (`cortex/adr/0001-file-based-state-no-database.md`, accepted) — all lifecycle state lands under `cortex/`. Writers must resolve to the correct repo root for diffability in PRs.
- ADR-0003 (`cortex/adr/0003-per-repo-sandbox-registration.md`, accepted) — additive `sandbox.filesystem.allowWrite` registration via `fcntl.flock`. Multi-repo coexistence.

### ADR-0004 (proposed) — multi-step Complete and interactive worktree lifecycle

`cortex/adr/0004-multi-step-complete-and-interactive-worktree-lifecycle.md` (status: PROPOSED) is **directly load-bearing for this ticket**:

- Complete phase progresses through sequential steps: tests → lifecycle-artifact commit → PR creation → `pr.json` write → `pr_opened` emission → merge-wait handoff → re-invocation → post-merge cleanup → backlog write-back → `feature_complete` emission.
- "WorktreeCreate-hook bypass is intentional and permanent." Lifecycle skills create `interactive/{slug}` worktrees via direct `git worktree add` (in `create_worktree()`), not via Claude Code's `WorktreeCreate` hook.
- PATH bootstrap migrated to `claude/hooks/cortex-session-start-path-bootstrap.sh` (cortex-shape gate).
- Rejected R2 (Bimodal Complete): uniform multi-step protocol applied to all features; non-interactive path skips cleanup silently.
- Rejected R3 (PR creation in Review tail): Review has read-only contract. "Complete phase is the correct owner of GitHub-side state changes."
- Consumer rule (`cortex/adr/README.md`): ADR-0004 is `status: proposed` — skills/hooks must NOT treat it as binding without human confirmation; surface it to the user at decision points.

### Events registry

- `bin/.events-registry.md` — gate-enforced. New event names must be registered before backlog `grep -c` gates can reference them.
- Existing events relevant to Variant A: `pr_opened` (gate-enforced), `feature_complete` (with `merge_anchor`), `interactive_lock_*` family, `interactive_overnight_active_rejected`, `feature_skipped_interactive_active`.
- No `interactive_worktree_*` or `worktree_cd` family is registered today — additions would be new commitments.

### Design principles (CLAUDE.md)

- "Prescribe What and Why, not How" — skill prose describes decisions and intent. Argparse-style flags on prose skills are awkward.
- MUST-escalation policy — soft positive-routing phrasing by default; new MUSTs require evidence + `effort=high` dispatch first.
- Solution horizon — Variant A is a deliberately-scoped phase of multi-phase epic #237 (not a stop-gap).

### Quality attributes

- `cortex/requirements/project.md:46` — destructive operations preserve uncommitted state. Worktree cleanup SKIPS on uncommitted state.
- `cortex/requirements/pipeline.md:126` — state writes use tempfile + `os.replace()` (atomicity invariant).

## Tradeoffs & Alternatives

The tradeoffs survey identified four pieces (CWD-refresh mechanism, writer-site refactor, PR-creation hook, detection) plus the commit-slicing question. **All four pieces have multiple non-equivalent shapes; the adversarial review below shows that some of the simplest-sounding fixes have load-bearing regressions.**

### Piece A — CWD-refresh mechanism

- **A1 (PreToolUse env-mutation)**: REJECTED. PreToolUse cannot mutate env vars (Web Research).
- **A2 (`cortex-cd` wrapper + state file)**: parallel state-of-truth, maintenance debt magnet. REJECTED.
- **A3a (demote CORTEX_REPO_ROOT to "hint", validate against `Path.cwd()`)**: Lowest-LOC option (~20 lines), restores walk-up. But — see Adversarial Review FM1/FM2/FM3 — **regresses #241 (`interactive_lock.py`), `pipeline/dispatch.py:555-560` (#198 pin), and `overnight/runner.py:2020-2024` (telemetry routing)**. Reverses an existing test contract (FM12). **REJECTED in present form.**
- **A3b (eliminate SessionStart pinning of CORTEX_REPO_ROOT entirely; pay walk-up cost)**: removes the staleness origin. But statusline.sh pays the cost on every refresh; #198's optimization rationale must be re-litigated. Similar regression surface to A3a in #241/dispatch.py.
- **A1' (`CwdChanged` hook + `CLAUDE_ENV_FILE`)**: documented Claude Code mechanism. **One-Bash-call latency** — compound `cd && cmd` evades the refresh (Web Research, Adversarial FM7). Not currently registered in `hooks.json`. Viable as a **best-effort backstop**, not primary mechanism.
- **A5 (per-callsite `worktree_root` parameter)**: M2 from adversarial mitigations. Mechanically larger diff, zero regression risk for callers that don't pass the parameter. Matches the existing pattern in `common.py:453,526` (`lifecycle_base: Path = Path("cortex/lifecycle")`).

### Piece B — Writer-site refactor

- **B1 (explicit worktree-root parameter via signature)**: large diff surface; threading parameter through call chain. Highest explicit-correctness; highest cost.
- **B2 (single-chokepoint via `_resolve_user_project_root()`)**: tradeoffs agent's pick. Adversarial review shows this is **wildly understated** in diff size (FM4 — 30+ sites, not 8). And depends on Piece A landing safely (which it cannot per FM1/2/3). PARTIAL ACCEPT — pattern is right but inventory must be redone by call-graph reachability, not grep.
- **B3 (new env var `CORTEX_LIFECYCLE_ROOT`)**: parallel mechanism, inherits the same staleness vulnerability. REJECTED.
- **B4 (per-site judgment)**: re-introduces the mental burden #126/#130 specifically eliminated. REJECTED.

### Piece C — PR-creation hook

- **C1 (`/cortex-core:pr --worktree <slug>` flag)**: pr-skill explicitly constrains "No `git -C`" (line 92); skills are prose-only per project design principles. Adding flag-style API to a prose skill is awkward.
- **C2 (lifecycle Complete `cd` before invoking `/cortex-core:pr`)**: tradeoffs pick. Adversarial FM8 surfaces the composition risk: `complete.md` Step 8 has an existing `realpath "$PWD" == worktree` **cd-out-or-bail** guard. Variant A's `cd-in-before-pr` requires `cd-out-before-cleanup`, encoded explicitly in the spec. **PARTIAL ACCEPT with explicit `cd-in-then-out` semantics**.
- **C3 (both)**: pays C1's cost without C1's benefit if cd works for the lifecycle path. REJECTED.

### Piece D — Detection ("running in an interactive worktree")

- **D1 (read `interactive.pid` from #241)**: authoritative file written by #241. Adversarial FM10 surfaces stale-PID and `/clear`-rotated session_id edge cases. **ACCEPT as advisory**, not as a blocking gate. Mitigation M6: corroborate with `git rev-parse --show-toplevel`.
- **D2 (path-prefix pattern match)**: fragile under custom `CORTEX_WORKTREE_ROOT`. Use as corroborator only.
- **D3 (new `.interactive-worktree` marker file)**: sentinel sprawl with no advantage. REJECTED.

### Cross-cutting — multi-commit landing slice

- **Slice 1 (per-writer-site, 8+ commits)**: overcounting; many no-op once Piece A lands cleanly. REJECTED.
- **Slice 2 (per-cluster)**: same overcounting issue.
- **Slice 3 (ticket's sketch: cd + refresh + minimal writers → refactor → PR-hook)**: middle layer is artifact of misdiagnosis.
- **Slice 4 (one PR, three commits)**: tradeoffs agent's pick. Adversarial DP6: bundles resolver-semantics change with prose, hiding regression risk. REJECTED in current form.
- **Slice 7 (adversarial DP6)**: PR 1 = inventory audit + tests for current behavior (no behavior change); PR 2 = per-callsite `worktree_root` parameter additions, backward-compatible; PR 3 = lifecycle prose changes (implement.md §1a `cd` handoff + complete.md `cd-in-then-out` around `/cortex-core:pr`); PR 4 = sandbox-registration of worktree base if DP3 lands. **ACCEPT as the safer landing shape**.

## Adversarial Review

The adversarial pass disconfirmed the tradeoffs agent's central reframing. Key challenges, with verifying file:line citations:

**FM1 — A3a regresses #241**. `cortex_command/interactive_lock.py:5-7,72-78` writes `interactive.pid` via `_resolve_user_project_root() / "cortex" / "lifecycle" / ... / "interactive.pid"`. Docstring: "Path is always resolved against the main repo root (never CWD-relative)." Demoting CORTEX_REPO_ROOT to a CWD-validated hint would route lock writes into the worktree, defeating `scan_live_locks()` and the inverse-direction overnight guard.

**FM2 — pipeline dispatch deliberately pins to worktree per #198**. `cortex_command/pipeline/dispatch.py:555-560` documents: "Pin CORTEX_REPO_ROOT to this dispatch's worktree (#198) so the bin/cortex-log-invocation shim's fast path skips git rev-parse." A `Path.cwd()` validation would falsely accept this case and corrupt downstream resolver assumptions.

**FM3 — overnight runner sets env from runner's own repo_path**. `cortex_command/overnight/runner.py:2020-2024`: "Set from runner's own resolved repo_path, not propagated from the operator's parent shell, so a stale shell value cannot misroute telemetry." Spawned children rely on env-inheritance as authoritative.

**FM4 — "eight writer sites" is severely undercounted**. `grep -c Path."cortex/"` in `cortex_command/` returns ~30 matches. The codebase agent listed 8. Notable misses: `overnight/report.py:658,674,768,1716`, `overnight/runner.py:2114`, `overnight/daytime_pipeline.py:216-401`, `overnight/interrupt.py:158`, `overnight/smoke_test.py:30-143`. Refine must redo the inventory by call-graph reachability from Variant-A flows.

**FM5 — `$TMPDIR/cortex-worktrees/` is NOT registered in `allowWrite`**. `cortex_command/init/handler.py:194-198` (Step 7): umbrella registration is `<repo>/cortex/` only. `cortex_command/init/tests/test_settings_merge.py:954` confirms "dual-registration test was structurally tied to a step being retired." The user's actual `~/.claude/settings.local.json` shows `allowWrite: [.../cortex-command/cortex/, .../wild-light/cortex/]` — nothing under `$TMPDIR`. **Variant A may sandbox-deny on first Write tool call inside the worktree.**

**FM6 — sub-agent isolation defeats Variant A's premise for the actual implementation work**. `skills/lifecycle/references/implement.md:146,160` shows §2 uses `Agent(isolation: "worktree")` — each task gets its own `$TMPDIR/cortex-worktrees/{task-name}/`. The orchestrator's `cd` into `interactive/{slug}` does NOT propagate. The "interactive/{slug}" worktree is the merge target, not the work surface. Variant A changes where the *orchestrator* writes events.log, not where implementation happens.

**FM7 — CwdChanged has one-Bash-call latency**. `cd <worktree> && cortex-update-item ...` runs `cortex-update-item` *before* CwdChanged's snapshot is sourced. Mid-session `cd` is unsupported per issues #25322/#19903 — `CwdChanged` is an undocumented side-effect path.

**FM8 — `complete.md` Step 8 hard guard composes badly with Variant A**. `skills/lifecycle/references/complete.md:159-163` has `realpath "$PWD" == worktree` cd-out-or-bail. Variant A's cd-in-before-pr requires explicit cd-out-before-cleanup in spec.

**FM10 — `interactive.pid` detection edge cases**. `cortex_command/interactive_lock.py:23-31` enumerates an 8-row liveness table. Session_id is `CLAUDE_CODE_SESSION_ID` — rotates on `/clear`. Migration in `hooks/cortex-scan-lifecycle.sh:46-72` handles `.session` files but **not `interactive.pid` session IDs**.

**FM11 — statusline `workspace.current_dir` update-on-cd is unverified**. `claude/statusline.sh:111-118` extracts from JSON payload; whether the payload tracks mid-session `cd` is upstream contract this repo does not control.

**FM12 — A3a reverses a previously-specified contract**. `cortex_command/tests/test_common.py:55-56` and `tests/test_common_utils.py:486` both assert "Returns Path(CORTEX_REPO_ROOT) verbatim when set." A3a reverses this. The original lifecycle ticket `add-upward-walking-project-root-detection-in-resolve-user-project-root/spec.md` is the source of the current contract.

### Adversarial mitigations (M1–M7)

- **M1**: Add `_resolve_user_project_root_from_cwd()` as a NEW helper for the narrow set of call sites that semantically belong to the active worktree CWD. Leave `_resolve_user_project_root()` semantically unchanged. Preserves #241, dispatch.py, runner.py.
- **M2**: Per-caller `worktree_root: Path | None = None` parameter pattern (matches existing `common.py:453,526` shape).
- **M3**: Extend `cortex init` to register `$TMPDIR/cortex-worktrees/` in `allowWrite` (or add a new `cortex init --register-worktree-base` step). Without this, Variant A's first Write may sandbox-deny.
- **M4**: Spec must explicitly script `cd-in-then-out` around `/cortex-core:pr`. Capture `_origin_pwd=$(pwd)` before cd, restore after pr-skill returns.
- **M5**: Spec must explicitly state Variant A's cd affects only orchestrator-session Bash, not sub-agent dispatch.
- **M6**: Detection of "in Variant A" reads `interactive.pid` AND corroborates with `git rev-parse --show-toplevel` against `pwd`. Advisory, not blocking.
- **M7**: Any resolver-semantics change updates `cortex_command/tests/test_common.py:55-56` and `tests/test_common_utils.py:486` in the same commit with a clear deprecation rationale.

## Open Questions

User-resolved at the research-exit gate (refine §4): proceed to Spec with **narrowed Variant A scope + adversarial mitigations M1–M7**. Each open question below is annotated with its resolution (inline answer) or explicit deferral (will be settled inside the Spec phase).

1. **CWD-refresh shape**. **Resolved**: M1+M2 path — new helper `_resolve_user_project_root_from_cwd()` for the narrow set of orchestrator-session writer sites that must follow CWD; keep existing `_resolve_user_project_root()` untouched (preserves #241, dispatch.py, runner.py contracts). M2 (per-caller `worktree_root` parameter) is the secondary pattern. CwdChanged hook is NOT registered in scope — held as a documented future backstop if a real failure mode emerges post-ship.

2. **Sandbox registration of `$TMPDIR/cortex-worktrees/` (M3)**. **Resolved (in-scope)**: extend `cortex init` (or add a `cortex init --register-worktree-base` action) to register `$TMPDIR/cortex-worktrees/` in `~/.claude/settings.local.json`'s `sandbox.filesystem.allowWrite`. Without this, Variant A's first Write inside the worktree may sandbox-deny.

3. **Variant A scope clarification — orchestrator-only vs. sub-agent-too**. **Resolved**: spec must explicitly state that Variant A's `cd` affects only orchestrator-session Bash. Sub-agent dispatch (`Agent(isolation: "worktree")` in `implement.md` §2) remains independently rooted at `$TMPDIR/cortex-worktrees/{task-name}/`. The "interactive/{slug}" worktree is the merge target for sub-agent work, not the work surface. What Variant A buys: orchestrator events.log writes land in the worktree (visible in the PR), user's CWD/statusline reflect the worktree, lifecycle state inspectable post-`cd`. What it does NOT buy: sub-agent code execution is unaffected.

4. **Writer-site inventory — call-graph audit**. **Deferred to Spec**: spec author enumerates the reachable-from-Variant-A surface by tracing call graph from `skills/lifecycle/references/implement.md` §1a-§4 and `skills/lifecycle/references/complete.md`. Daytime-pipeline sites are out of scope (slated for #246 removal). Output: a definitive list of sites that need refactor, with each annotated by reachability from Variant-A flows.

5. **PR-creation `cd-in-then-out` pattern (M4)**. **Resolved**: spec encodes `_origin_pwd=$(pwd); cd $(cortex-worktree-resolve interactive/{slug}); /cortex-core:pr; cd "$_origin_pwd"` semantics in `complete.md` Step 3 prose. Step 8's existing `realpath "$PWD" == worktree` cd-out-or-bail guard composes correctly because of the restore.

6. **`interactive.pid` detection edge cases (M6)**. **Deferred to Spec**: spec commits to advisory-not-blocking detection (read `interactive.pid` AND corroborate via `git rev-parse --show-toplevel` against `pwd`). Whether to extend `hooks/cortex-scan-lifecycle.sh:46-72`'s `.session` migration to also rewrite `interactive.pid` session_id on `/clear` is a follow-up — surface as Open Decision in spec.

7. **Worktree cleanup ownership**. **Resolved (status-quo + carve-out)**: today's path — user re-invokes `/cortex-core:lifecycle complete <slug>` after merging the PR; `complete.md` Step 8 calls `cleanup_worktree()`. Confirm in spec as the in-scope answer. Automation (PostToolUse-style hook detecting merge events) is downstream of #240.

8. **Commit slicing**. **Resolved**: Slice 7 — four PRs: (1) inventory audit + characterization tests (no behavior change); (2) new `_resolve_user_project_root_from_cwd()` helper + per-callsite `worktree_root` parameter additions, backward-compatible; (3) lifecycle prose changes (`implement.md` §1a `cd` handoff + `complete.md` `cd-in-then-out` around `/cortex-core:pr`); (4) sandbox registration of worktree base via `cortex init`.

9. **Statusline behavior post-`cd`**. **Deferred to Spec**: 2-minute empirical probe inside the spec phase — drop a Bash `cd`, inspect `workspace.current_dir` in statusline payload. Spec author documents the verified behavior.

10. **Existing test contract reversal (M7)**. **Resolved**: not applicable under M1+M2 path. The new helper does not touch `_resolve_user_project_root()`; the per-caller parameter is additive. Existing tests at `cortex_command/tests/test_common.py:55-56` and `tests/test_common_utils.py:486` remain green.

11. **`additionalDirectories` registration for Bash `cd` carry-over**. **Deferred to Spec**: confirm during spec whether `cortex init`'s extension (M3) for `allowWrite` also handles `additionalDirectories`, or whether they are separate registration steps. Spec encodes the answer.

12. **CwdChanged registration**. **Resolved (out of scope)**: not registered in #240. Documented as a future backstop in research.md; revisited only if a real failure mode surfaces post-ship.
