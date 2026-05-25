# Research: Decompose Approach A's deferred design surface — settling (1) cross-session ExitWorktree interaction with the Complete-phase hard guard, (2a) consumer-repo EnterWorktree authorization shape, (2b) WorktreeCreate-hook bypass interaction with auto-enter — and wire the auto-enter behavior into the lifecycle skill's implement phase so the interactive-worktree branch-mode selection automatically enters the new worktree via `EnterWorktree(path=...)`.

## Codebase Analysis

### Files that will change

**SKILL/reference layer (auto-enter wiring, the implement-phase deliverable):**

- `skills/lifecycle/references/implement.md` (currently 340 lines; references/ files are exempt from the 500-line cap that applies to SKILL.md). The branch picker / branch-mode dispatch lives here.
  - **Line 49** — `AskUserQuestion` picker call site cited by the kept-pauses inventory.
  - **§1a step iii (lines 122–130)** — existing `create_worktree(...)` call site; the `EnterWorktree(path=...)` call lands immediately after this.
  - **§1a step v "Cd handoff" (lines 184–198)** — current `cd $(cortex-worktree-resolve interactive/{slug})` shim. ADR-0004 names this as the deferred-`EnterWorktree` site. The block does three things: capture `_origin_pwd`, `cd`, emit `interactive_worktree_entered` event from the worktree CWD. `EnterWorktree` replaces only the `cd`; the event emission must be re-ordered so it runs after the tool call (so `_resolve_user_project_root_from_cwd()` lands the row in the worktree's events.log).
  - **§1a step vi "Handoff" (lines 200–212)** — current "Variant A active / Variant B rejected" narrative. With auto-enter wired, this prose needs a full re-author; the message currently asserts "cd'd into the worktree" which becomes misleading once the operation is `EnterWorktree` (different semantics: cache-clearing, session-tracking, must-not-already-be-in-a-worktree precondition).
  - **Routing prose at lines 42–48** — lists the four closed-set `branch-mode` values; the `worktree-interactive` branch is the one this ticket wires.
  - **Out-of-date path text (F1/A4 from Adversarial)**: §1a step iii text references `$TMPDIR/cortex-worktrees/interactive-{slug}/`, but `cortex_command/pipeline/worktree.py::resolve_worktree_root` returns `<repo>/.claude/worktrees/<feature>` and `init/handler.py` Step 7b actively expunges `cortex-worktrees`-prefixed entries from `settings.local.json`. The drift must be reconciled before specifying `EnterWorktree(path=...)` — or the spec must mandate that the path comes from `cortex-worktree-resolve interactive/{slug}`, never a hardcoded literal.

- `skills/lifecycle/SKILL.md` (231/500 lines, ~269 lines of headroom). Kept-pauses inventory entry at **line 203** anchors `implement.md:49` (the picker pause). Auto-enter is non-interactive (no new pause), so the existing entry stays valid; its rationale tag `conditional pause` + `read_branch_mode | lifecycle_config` marker remain accurate.

- `skills/lifecycle/references/complete.md` (253 lines) — **Step 8 hard guard at lines 175–181** ("Do not auto-cd. The user must exit the worktree and re-invoke"). For Decision (1)'s recommended hybrid, Step 8 prologue calls `ExitWorktree(action="keep")` first; the no-op cross-session case falls through to the existing hard guard unchanged. Step 3 Variant A detection (lines 27–43) is the existing cd-in/cd-out precedent.

- `cortex/adr/0004-multi-step-complete-and-interactive-worktree-lifecycle.md` — append an amendment recording the three resolved decisions. Status: `proposed` (current) → must promote to `accepted` before the auto-enter wiring lands (see Adversarial S2 / ADR-README consumer rule).

- `cortex_command/init/handler.py` `_run()` (lines 114–213) and `cortex_command/init/scaffold.py` `ensure_gitignore()` (lines 374–443) — the additive-idempotent consumer-write precedent. **Only invoked if Decision (2a) chooses a consumer-mutation shape** — see "Recommended alternative authorization shapes" below; the Adversarial review surfaces an option that requires no `cortex init` change at all.

- `cortex/lifecycle/lifecycle-implement-auto-enter-worktree-via/` — this lifecycle's artifacts: `spec.md`, `plan.md`, plus the `research.md` you are reading.

### Relevant existing patterns

**Picker site (`implement.md:49`):** the three-option `AskUserQuestion` at line 22 with "Implement on feature branch with worktree" as Option 2. The `read_branch_mode` preflight (lines 22–47) routes `worktree-interactive` (and `trunk`, `feature-branch`) to "skip the picker" and proceed straight into §1a.

**Complete-phase hard guard (`complete.md:175–181`, verbatim):**

> **Hard guard**: before running cleanup, compare `realpath "$PWD"` with the worktree path. If the session is running from inside the target worktree, exit with:
> > cd out of the worktree before running cleanup; current PWD is the worktree being removed.
> Do not auto-cd. The user must exit the worktree and re-invoke.

**WorktreeCreate-hook bypass (ADR-0004, line 11, verbatim):**

> **WorktreeCreate-hook bypass is intentional and permanent.** Lifecycle skills create `interactive/{slug}` worktrees via a direct `git worktree add` call inside `create_worktree()`, bypassing Claude Code's native `--worktree` flag and its associated `WorktreeCreate` hook. […] This bypass is permanent: a future refactor that re-routes lifecycle worktree creation through the hook would require updating all hook responsibilities and all callers, and would introduce a dependency on Claude Code's internal `--worktree` launch flow that the overnight runner cannot use.

**No existing `EnterWorktree` / `ExitWorktree` callsites** in `skills/`, `hooks/`, `bin/`, or `cortex_command/`. The only mentions are in docs (`docs/internals/sdk.md:216`) and the ADR/backlog artifacts. **This ticket sets the precedent for authorization shape, fallback handling, and event ordering.**

**`cortex init` consumer-mutation idiom**: today the handler touches `cortex/` scaffold, `cortex/.cortex-init` marker, `.gitignore`, and `~/.claude/settings.local.json::sandbox.filesystem.allowWrite` + `additionalDirectories`. **It does NOT touch consumer `CLAUDE.md`.** Extending it to do so is unprecedented per ADR-0003.

**`ensure_gitignore()`** is the closest precedent for any additive consumer-repo file mutation (read-mutate-atomic_write with line-exact membership and orphan-prefix repair). `settings_merge.register()` is the flock-protected pattern for user-home writes.

### Integration points and dependencies

- **Parity test** at `tests/test_lifecycle_kept_pauses_parity.py` — accepts `conditional pause` rationale tag and requires `read_branch_mode | lifecycle_config` marker within ±35 lines of the anchor. Auto-enter on the `worktree-interactive` branch preserves the existing marker; it does not require an inventory edit. **But** the parity test **cannot** catch a regression in a non-`AskUserQuestion` `EnterWorktree` callsite — see Mitigation 9 in Adversarial Review.
- **Skill size-budget test** at `tests/test_skill_size_budget.py` (cap 500 per `requirements/project.md:30`) applies only to SKILL.md. SKILL.md sits at 231/500. `implement.md` has no cap.
- **Complete phase Step 3 `cd-in-then-out`** pattern at `complete.md:27–43` — pre-existing precedent for restoring `_origin_pwd` around a sub-command. Auto-enter composes with or supersedes this.
- **Step 8 prefix check** at `complete.md:183` matches `cortex-worktrees/interactive-{slug}` in `git worktree list --porcelain`. This must be reconciled with the migrated `<repo>/.claude/worktrees/` convention (Adversarial F1/A4).
- **`cortex-lifecycle-event log --event interactive_worktree_entered`** at `implement.md:193` — downstream readers may key on this event.
- **`cortex/lifecycle/sessions/{slug}.interactive.pid`** liveness file (per-feature, not per-session-CWD) — the structural marker that R3/R4 of the parent C lifecycle protect.

### Conventions to follow

- **Two Bash calls, no compound commands** for paired probes; **single Bash call** for primitives.
- **Spec section ordering**: Problem Statement → Phases → Requirements (numbered R1..RN with Acceptance/Phase/Priority footers) → Non-Requirements → Edge Cases → Changes to Existing Behavior → Technical Constraints → Open Decisions → Proposed ADR. The parent C lifecycle's spec (`lifecycle-implement-auto-enter-worktree-drop`) is the model.
- **Acceptance criteria with literal `grep` / `just test` commands** — pattern from the parent spec's R3–R8.
- **`cortex init` writes are additive + idempotent** (`ensure_gitignore` + `settings_merge.register` precedents).
- **ADR amendments append a new `## section`, keep `Status: proposed`** — per parent spec R7's pattern (C/A split amendment landed without promoting ADR-0004).
- **MUST-escalation policy**: default soft positive-routing. Any new MUST requires the documented evidence-artifact ritual.

### Size-cap headroom assessment

| File | Current | Cap | Headroom |
|---|---|---|---|
| `skills/lifecycle/SKILL.md` | 231 | 500 | 269 |
| `skills/lifecycle/references/implement.md` | 340 | — | unlimited (references/ exempt) |
| `skills/lifecycle/references/complete.md` | 253 | — | unlimited |

Auto-enter wiring fits comfortably. SKILL.md needs at most a one-line rationale touch-up. `implement.md` will absorb the bulk (~20–40 lines for the EnterWorktree call + handoff prose re-author).

### Notes on the parent lifecycle's R7/R8

- **R7** records the ADR amendment shipped in commit `93654e07`.
- **R8** defines this ticket's frontmatter shape: `status: backlog, priority: medium, type: feature, tags: [lifecycle, worktree-interactive]`. Body documents platform constraint + the two cortex-side scoping decisions + acceptance criteria for `status: refined`.
- **Non-Requirements line 61** of the parent spec: "Consumer-repo CLAUDE.md authorization for `EnterWorktree` is NOT in scope. The `cortex init` opt-in step is a deliverable of the deferred Approach A ticket (R8)." This is the seam this ticket fills.

## Web Research

### Authoritative tool documentation (verbatim where possible)

- Official Anthropic docs ([code.claude.com/docs/en/tools-reference](https://code.claude.com/docs/en/tools-reference)):
  - `EnterWorktree`: "Creates an isolated git worktree and switches into it. Pass a `path` to switch into an existing worktree of the current repository instead of creating a new one." Permission Required: **No** (gating lives in the tool prose).
  - `ExitWorktree`: "Exits a worktree session and returns to the original directory." Permission Required: **No**.

- `EnterWorktree` description (Piebald-AI mirror): authorization gate — *"Use this tool ONLY when explicitly instructed to work in a worktree — either by the user directly, or by project instructions (CLAUDE.md / memory)."* Parameters: `name` (optional) for fresh creation; `path` (optional) to enter an existing worktree; mutually exclusive. Precondition: "Must not already be in a worktree."

- `ExitWorktree` description (Piebald-AI / p0 / anasfik mirrors): **cross-session scoping, verbatim** — *"This tool ONLY operates on worktrees created by EnterWorktree in this session. It will NOT touch: manually created worktrees, worktrees from previous sessions, or the current directory if EnterWorktree was never called."* Outside an active session it's a no-op and reports the session as inactive. Side effects on `keep`: "restores original CWD" and "Clears CWD-dependent caches (system prompt sections, memory files, plans directory)."

- **Note on the "not available to subagents" claim**: Agent 2 cited this constraint; Agent 5 (Adversarial) could not re-confirm it in the Piebald mirror. **Treated as unverified in the Open Questions section below — the spec must cite the actual source line or test the constraint empirically before relying on it.**

### Prior-art callsites (real skills that call `EnterWorktree(path=...)`)

1. **`VeryGoodOpenSource/vgv-wingspan` `skills/create-branch/SKILL.md`** — closest analog. Calls `EnterWorktree` after `git status --porcelain` + uncommitted-changes check; on error (already-in-worktree, etc.) **falls back to standard branch creation and notifies the user**. The fall-back-and-notify pattern is what this spec should mirror.

2. **`juan294/cc-rpi` `.claude/commands/implement.md`** — direct `"Enter a worktree for implementation (EnterWorktree tool)"` step. The `/implement` slash-command invocation is treated as the authorization.

3. **`HendrikGC02/Astroray` `.claude/skills/pkg-ship/SKILL.md`** — calls `EnterWorktree path="<abs-path>"` immediately after creating the worktree. Authorization derives from cross-reference to a CLAUDE.md section ("per CLAUDE.md §Build & Verification").

4. **`XinheLIU/human-leverage` `.claude/skills/spec/SKILL.md`** — declarative: "Session is switched into the worktree (via `EnterWorktree path=...`) so follow-on commands run there."

5. **`lugassawan/swe-workbench` `skills/workflow-cleanup-merged/SKILL.md`** — **the working analog of Decision (1)'s hybrid**: "If the session is currently inside a worktree (e.g. entered via `EnterWorktree path=…`), call `ExitWorktree action=keep` now — *before* deriving `$MAIN_REPO` and *before* `git pull`." Three stated rationales: returns session to prior dir; releases harness's session lock; ensures removal won't execute from a deleted working dir.

6. **`seokan-jeong/team-shinchan` `agents/midori.md`** — probes the EnterWorktree schema via `ToolSearch` as a pre-flight, with graceful fallback to standard parallel Task dispatch when unavailable.

7. **`tim-hub/powerball-harness` `harness/agents/ralph-worker.md`** — articulates the orchestrator-owns-worktree vs subagent-owns-worktree tradeoff explicitly: "Runs in the orchestrator-managed worktree (no `isolation: worktree` frontmatter — the orchestrator owns the worktree via `EnterWorktree`)." Iterative-refinement workers need cross-spawn visibility, which `isolation: worktree` would wipe.

### Authorization-clause patterns in CLAUDE.md (verbatim where found)

1. **Denial clause** (`tixl3d/tixl`): *"Never use git worktrees. They break Rider builds and cause permission issues."* / *"Never use `git worktree add`, `EnterWorktree`, or any worktree-related commands."* — the inverse polarity exists in published prior art.

2. **Cross-reference-via-skill** (Astroray) — skill body says "per CLAUDE.md §Build & Verification," and CLAUDE.md's named section establishes worktree isolation as a critical invariant. Audit-friendly named-section pattern.

3. **Hook-enforced authorization** (`richardbowman/agent-skills` `hooks/require-worktree.sh`) — PreToolUse hook that blocks Edit/Write when not in a linked worktree. Block reason includes the canonical recipe `EnterWorktree path=~/projects/<repo>/.claude/worktrees/<branch>`. Inverse of opt-in.

4. **`iplweb/bpp` CLAUDE.md** — the gh-search snippet shows `EnterWorktree path=~/Programowanie/bpp-<slug>` invocation embedded in a documented workflow (raw fetch returned 404; index confirms the pattern).

5. **Per-skill `allowed-tools` frontmatter** — the official skills doc confirms skills can list `allowed-tools` in YAML frontmatter to scope what they may call.

### Sub-agent vs in-session worktree-isolation tradeoffs

- **`isolation: worktree`** (subagent frontmatter): declarative, automatic per-dispatch, fresh worktree each spawn, auto-cleans on no-change exit. Cons: subagent returns only a final text result, parent doesn't see intermediates; cannot iteratively refine across spawns. Known silent-failure bug ([anthropics/claude-code#39886](https://github.com/anthropics/claude-code/issues/39886) per `cortex/requirements/multi-agent.md:94`). [#33045](https://github.com/anthropics/claude-code/issues/33045) reports no-effect for team agents.
- **`EnterWorktree` mid-session**: imperative, in-session, full intermediate visibility, can be paired with `ExitWorktree` for round-trip; required when an orchestrator does multi-step work IN the worktree.
- For Approach A's use case (implement phase orchestrates multi-step builder work inside the worktree), `EnterWorktree` is the right primitive — `isolation: worktree` would lose orchestrator visibility.

### Known bugs / anti-patterns

- [claude-code#48967](https://github.com/anthropics/claude-code/issues/48967) — EnterWorktree creates worktrees inside `.claude/` by default, breaking skill discovery. Cortex sidesteps via `$TMPDIR` / `<repo>/.claude/worktrees/` (path-dependent — see Adversarial F1).
- [claude-code#37611](https://github.com/anthropics/claude-code/issues/37611) — When a `WorktreeCreate` hook is defined in `.claude/settings.json`, the worktree-cleanup-on-exit prompt is skipped. Cortex's Python-helper path sidesteps this; if Approach A added a `WorktreeCreate` hook, it would inherit the bug.
- [claude-code#39281](https://github.com/anthropics/claude-code/issues/39281) — `--worktree --tmux` skips WorktreeCreate/WorktreeRemove hooks.
- [claude-code#41314](https://github.com/anthropics/claude-code/issues/41314) — `GIT_INDEX_FILE` env var can leak across process boundaries. Defensive `unset GIT_INDEX_FILE` recommended for any Bash wrapping EnterWorktree.

### Cross-session CWD restoration (analog patterns)

The shell-trap convention (`pushd`/`popd`/`trap … EXIT`) does **not** transfer cleanly because EnterWorktree's CWD mutation is not in a child shell — it's in the parent agent session itself. The platform constraint (cross-session no-op) is fundamental; there is no shell-trap equivalent the cortex skill can install in a separate session to restore CWD. The implication: Complete-phase same-session re-invocation must call `ExitWorktree` from inside the same session that called `EnterWorktree`, before the hard guard runs. swe-workbench's `workflow-cleanup-merged` is the working example.

### Prior cortex-command framing

- **Commit `93654e07`** — "Amend ADR-0004 with branch-mode default + Approach A deferral framing." Forward-references this ticket. No public PR thread surfaced (the C lifecycle appears to have shipped via direct push or via an overnight session).
- **Parent ticket 249** explicitly raised the Complete-phase question and stated "today's complete-phase Step 8 cleanup runs from outside the worktree." Web research direction: swe-workbench's pattern → skill should orchestrate `ExitWorktree action=keep`.
- **`docs/internals/sdk.md`** notes EnterWorktree/ExitWorktree as "not used; `isolation: \"worktree\"` on Agent is the safe path in sandbox." This guidance is now superseded by Approach A's wiring; the doc needs an update.

## Requirements & Constraints

### Relevant requirements from `cortex/requirements/`

**`cortex/requirements/project.md` — Philosophy of Work, Multi-step lifecycle phases (lines 25–27, verbatim):**

> **Multi-step lifecycle phases**: A lifecycle phase may be multi-step with a user-driven re-invocation point. The Complete phase is the canonical example — it creates a PR, exits with a handoff message, and finalizes only on re-invocation after the PR is merged on GitHub. Merge (not PR-open) is the terminal event for "Done" […]
>
> **Kept user pauses come in two kinds**: (a) `AskUserQuestion`-site pauses […]; (b) phase-exit pauses where a phase exits cleanly and waits for the user to re-invoke after performing an out-of-band action (e.g., merging a PR on GitHub).

**Architectural Constraints (lines 32, 34, verbatim):**

> - **Per-repo sandbox registration**: → ADR-0003: Per-repo sandbox registration
> - **SKILL.md size cap**: 500 lines (`tests/test_skill_size_budget.py`). Exceptions via in-file `<!-- size-budget-exception: ... -->`. Default fix: extract to `skills/<name>/references/`.

**Solution horizon (line 21, verbatim):**

> A scoped phase of a multi-phase lifecycle is not a stop-gap (stop-gap means unplanned-redo). Test: current knowledge, not prediction.

**`cortex/requirements/multi-agent.md` (line 77, verbatim):**

> Worktrees for the default repo are created at `$TMPDIR/cortex-worktrees/{feature}/`; cross-repo worktrees go to `$TMPDIR/overnight-worktrees/{session_id}/{feature}/`. […] Same-repo worktrees therefore live under the per-user `$TMPDIR` carve-out, resolved through a single chokepoint (`resolve_worktree_root()` in `cortex_command/pipeline/worktree.py`).

**Edge Cases — silent-isolation-failure (line 94, verbatim):**

> **Silent isolation failure of `Agent(isolation: "worktree")`**: `anthropics/claude-code` issue #39886 reports that `Agent(isolation: "worktree")` may silently fail to create the isolated worktree, returning "success" while the agent in fact runs against the parent CWD.

multi-agent.md does **not** mention `EnterWorktree`/`ExitWorktree` directly; it covers only path-resolution chokepoint, isolation-flag failures, branch-collision detection, cross-repo TMPDIR carve-out.

**`cortex/requirements/pipeline.md`** — no constraints on auto-enter or skill CWD mutation; only mentions worktrees in integration-branch persistence (line 22) and conflict-resolution repair (line 51). Atomic state writes (NFR line 126): "All session state writes use tempfile + `os.replace()` — no partial-write corruption."

**`cortex/requirements/observability.md`, `cortex/requirements/remote-access.md`** — no mention of worktrees or EnterWorktree (verified by grep).

**`cortex/requirements/glossary.md` — does NOT exist.** Named in project.md's Global Context (line 81) but no file backs it. **Open requirements gap.** No glossary entries for "worktree," "interactive worktree," "branch-mode," "hard guard," or "auto-enter."

### Architectural constraints that apply

- **ADR-0001 (file-based state)**: any per-session entry marker or sentinel uses the existing file surface.
- **ADR-0003 (per-repo sandbox registration), verbatim line 7**: *"`cortex init` additively registers the current repo's `cortex/` umbrella path into the `sandbox.filesystem.allowWrite` array of `~/.claude/settings.local.json` — the only write cortex-command makes outside its own tree."* The rejected "Machine-wide setup script" alternative (line 11) closes the door on globally pre-authorizing path patterns. **ADR-0003 does not mention consumer-repo CLAUDE.md.** Extending `cortex init` to mutate consumer CLAUDE.md is unprecedented and likely requires a new ADR under the three-criteria gate.
- **Worktree path chokepoint** (`resolve_worktree_root()` in `cortex_command/pipeline/worktree.py`) is the only sanctioned producer of worktree paths.
- **Atomic state writes** (tempfile + `os.replace()`) inherit to any per-session entry marker.

### ADR-level prior decisions

**ADR-0004**, Status: `proposed`. C/A split section (lines 27–41) records the deferral framing — three sub-items: platform-side `ExitWorktree` cross-session no-op + (i) `cortex init` opt-in clause + (ii) WorktreeCreate-hook bypass interaction.

**WorktreeCreate-hook permanent-bypass clause (ADR-0004, line 11, verbatim):**

> Lifecycle skills create `interactive/{slug}` worktrees via a direct `git worktree add` call inside `create_worktree()`, bypassing Claude Code's native `--worktree` flag and its associated `WorktreeCreate` hook. […] The hook's responsibilities (path resolution, `.venv` symlink, settings copy) are handled inside `create_worktree()` directly […]. This bypass is permanent.

**ADR-README — three-criteria emission gate (lines 19–27, verbatim):**

> 1. **Hard to reverse** — reversing the decision later would require coordinated changes across multiple call sites, data migrations, or external contracts.
> 2. **Surprising without context** — a reasonable contributor encountering the code or configuration for the first time would not predict the decision from the surrounding conventions.
> 3. **Result of a real trade-off** — at least one credible alternative was considered and rejected for stated reasons.
> **All three required.**

**ADR-README — consumer rule for `proposed` ADRs (lines 66–68, verbatim, critical):**

> - **MUST NOT automatic.** A skill **MUST NOT automatic**-ally treat a `proposed` or `deprecated` ADR as binding. `proposed` ADRs are still under review and may be rejected; `deprecated` ADRs no longer reflect the current decision. Acting on either without human confirmation would propagate stale or unratified guidance into downstream artifacts.

This is a hard gate on the spec: ADR-0004 must be promoted to `accepted` (or this spec must explicitly gate the implementation on promotion landing in the same PR train) before the auto-enter wiring lands.

### Scope boundaries

- **In scope (project.md line 59)**: "Multi-agent: parallel dispatch, worktrees, Haiku/Sonnet/Opus selection." Auto-enter is inside this in-scope area.
- **Approach A bounded by three sub-problems** (ADR-0004 (c)): platform-side ExitWorktree cross-session no-op + (i) cortex init authorization + (ii) WorktreeCreate-hook bypass interaction. These map 1-to-1 onto this ticket's decisions (1) / (2a) / (2b).
- **Out of scope**: dotfiles/machine config; application code; reusable packages.
- **Deferred**: "Cross-repo work in one overnight session" — interactive worktree auto-enter is in-session, not cross-repo overnight, so this carve-out doesn't apply.

### Authorship/style constraints from CLAUDE.md

- **Skill / phase authoring guidelines (verbatim)**: "Prefer structural separation over prose-only enforcement for sequential gates. A gate encoded in skill control flow is harder to accidentally bypass than one that relies on the model reading and following a prose instruction."
- **Solution horizon**: "A deliberately-scoped phase of a multi-phase lifecycle is not a stop-gap."
- **Design principle (verbatim)**: "When authoring skills, hooks, lifecycle templates, or any harness instruction, describe decisions to be made, gates to enforce, output shapes required, and the intent behind each (the What and Why). Resist prescribing step-by-step method (the How)."
- **MUST-escalation policy**: default soft positive-routing; new MUST requires the documented evidence-artifact ritual.

### Open requirements gaps

- **No glossary entry** for EnterWorktree/ExitWorktree/interactive-worktree/auto-enter/hard-guard. `glossary.md` does not exist; spec should either introduce terms inline or create the glossary.
- **No requirements-level statement** on "consumer-repo CLAUDE.md authorization." ADR-0004 (c)(i) is the only mention and is intentionally underspecified.
- **No prior decision** on whether `cortex init` may write outside `~/.claude/settings.local.json`. Extending it to consumer-repo CLAUDE.md is unprecedented.
- **No requirements coverage** of "mid-session CWD mutation by a skill." The behavioral contract for `EnterWorktree(path=...)` invoked from a skill has no precedent in this codebase.
- **No documented test** for the WorktreeCreate-hook bypass × `EnterWorktree` interaction.

## Tradeoffs & Alternatives

### Decision (1) — Cross-session-exit interaction model

The core constraint: `ExitWorktree` only operates on worktrees the *current session* entered. The Complete-phase Step 8 hard guard refuses to run from inside the worktree being removed. With auto-enter, the implement → review → complete sequence runs in one session; the multi-step Complete *re-invokes after merge wait*, and the user typically returns hours later (often in a fresh session).

- **(1A) Restructure Complete-phase teardown to not require an out-of-worktree CWD.** High implementation cost; erodes a structural safety rail; conflicts with CLAUDE.md's "structural separation over prose-only enforcement." **Rejected.**
- **(1B) Document a session-boundary at which the user exits before Complete fires.** Trivial implementation; preserves the structural guard; sacrifices the no-cd handoff *only* at the Complete boundary (implement → review window stays cd-free).
- **(1C) Hybrid: Complete-phase Step 8 prologue calls `ExitWorktree(action="keep")`; cross-session no-op falls through to 1B's hard-guard message.** Same-session: seamless. Cross-session: identical to 1B. Keeps structural guard; uses platform tool semantics at the right layer.

**Recommendation: 1C** — but the Adversarial F4 caveat applies. The "same-session common case" assumption is unsupported; the modal Complete re-invocation is cross-session. Treat 1C as cheap insurance for a same-session optimization, not a perf-critical path. Test coverage must weight cross-session as primary; same-session is additive.

### Decision (2a) — Consumer-repo EnterWorktree authorization shape

Backdrop: the EnterWorktree gating rule is verbatim *"explicitly instructed […] either by the user directly, or by project instructions (CLAUDE.md / memory)."*

- **(2a-α)** `cortex init` writes a clause into consumer `CLAUDE.md` (additive-idempotent fenced block, like `ensure_gitignore`). Has rollback story (`cortex init --revoke-worktree-auth`). Requires a new ADR (extends consumer-write surface beyond ADR-0003).
- **(2a-β)** Picker selection itself carries authorization. Near-zero implementation. **Load-bearing gap**: the per-repo `branch-mode: worktree-interactive` default suppresses the picker — the very path Approach A delivers most value — so the per-invocation authorization disappears for the high-value path.
- **(2a-γ as originally proposed)** Hybrid: picker-as-authorization when picker fires; cortex-managed sibling file (e.g. `.claude/cortex-authorizations.md`) for suppressed-picker path. **Adversarial F5 rejects this**: the platform recognizes only CLAUDE.md or memory (`~/.claude/projects/<project>/memory/`) — a sibling file at `.claude/cortex-authorizations.md` is *neither* and would silently fail closed.
- **(2a-δ, surfaced by Adversarial)** Authorization carried inline in `skills/lifecycle/SKILL.md` description text. The skill itself constitutes "project instructions" for any repo that has the cortex-core plugin installed. No consumer write; no new ADR; no rollback machinery; closes the suppressed-picker gap automatically (skill is loaded regardless of branch-mode setting). **Risk**: requires the platform to treat skill descriptions as "project instructions" for the purposes of the EnterWorktree gate — needs empirical confirmation that loaded-skill-description satisfies the rule.
- **(2a-ε, fallback)** 2a-α with the managed-section landing in CLAUDE.md proper (additive-idempotent fenced block).

**Recommendation: 2a-δ as primary, 2a-ε as fallback if 2a-δ fails the platform's interpretation of "explicit instruction."** Decided by the Open Question test below.

### Decision (2b) — WorktreeCreate-hook bypass interaction with auto-enter

Backdrop: WorktreeCreate hook fires only on Claude Code's own `--worktree` launch; cortex's `create_worktree()` calls `git worktree add` directly. There is **no registered `EnterWorktree` hook event** in `plugins/cortex-core/hooks/hooks.json`.

- **(2b-α)** Bypass inherits cleanly because there is no EnterWorktree hook to bypass. Zero implementation cost.
- **(2b-β)** Expand ADR-0004's bypass clause to explicitly cover the auto-enter call. Pre-fortifies against a hook that doesn't exist; documentation pollution.
- **(2b-γ)** Same as 2b-α + explicit one-line verification in the spec: "grep `plugins/cortex-core/hooks/hooks.json` for `EnterWorktree`, find nothing; if added later, revisit." Records the assumption so a future hook-add prompts a revisit.

**Recommendation: 2b-γ.**

### Recommended bundle composition

**1C + 2a-δ + 2b-γ**, with the Adversarial mitigations layered in. If 2a-δ fails the platform's "explicit instruction" interpretation, fall back to 2a-ε.

## Adversarial Review

### Failure modes and edge cases

- **F1 — Worktree path divergence**: implement.md text references `$TMPDIR/cortex-worktrees/interactive-{slug}/`, but `resolve_worktree_root` returns `<repo>/.claude/worktrees/<feature>` and `init/handler.py` Step 7b expunges `cortex-worktrees`-prefixed entries. Reconcile the doc drift first or specify that auto-enter calls `cortex-worktree-resolve interactive/{slug}` and passes the resolved path — never a hardcoded literal.
- **F2 — Step v event-ordering**: `_origin_pwd` capture must happen *before* `EnterWorktree`; `interactive_worktree_entered` event must be emitted *after* (subprocess inherits the post-tool CWD); `ExitWorktree(action="keep")` makes `_origin_pwd` redundant for same-session restore; cross-session can't restore.
- **F3 — Variant A/B prose contradiction**: `implement.md:204-209` currently says "Variant A (active): cd'd into the worktree" with Variant B explicitly rejected. Auto-enter requires a full re-author of this prose — `EnterWorktree` has different semantics (cache-clear, session-tracking, must-not-already-be-in-a-worktree).
- **F4 — 1C inverts in practice**: there's no data supporting "same-session is the common case" for Complete re-invocation. The natural workflow (open GitHub, wait, merge, come back hours later) is cross-session. Treat 1C as additive optimization; weight tests toward cross-session.
- **F5 — 2a-γ's sibling file is invisible to platform** (already folded into the (2a) recommendation above).
- **F6 — Picker-as-authorization** depends on the model interpreting an `AskUserQuestion` answer as "explicit instruction." The Piebald examples are imperative natural language. Needs empirical verification; spec should include a fallback to surface a clear "manually add 'use a worktree for this lifecycle' to CLAUDE.md" message if the tool is refused.
- **F7 — Background-session / `worktree.bgIsolation` interaction**: the overnight runner is background-style (`bypassPermissions`). Auto-enter must explicitly NOT fire in overnight context.
- **F8 — Concurrent-session contention**: `EnterWorktree` requires "Must not already be in a worktree" per-session. If a session was launched inside a worktree (e.g., `claude --worktree=<path>`), the precondition fails. Spec must add a CWD-side precondition (`git rev-parse --git-common-dir` vs `--git-dir`) and route around gracefully (skip auto-enter, surface diagnostic).
- **F9 — Cache-clear race during `ExitWorktree`**: cache-clear ("system prompt sections, memory files, plans directory") is in-process for the orchestrator; subprocess CWD inheritance is OS-level. Spec must order operations: `ExitWorktree(action="keep")` first in Step 8 prologue, before any reference-file load or event emission; re-load any needed skill state after.
- **F10 — Overnight runner branch missed**: overnight orchestrator dispatches plan-gen → implement; if `branch-mode=worktree-interactive` is in overnight-target's `lifecycle.config.md`, suppressed-picker path leads into §1a. `EnterWorktree` "Not available to subagents" (if true — see A1) means sub-agent refuses the tool. Spec must add explicit "in overnight context, skip auto-enter" branch.
- **F11 — Worktree-removal-on-EXIT side effect**: EnterWorktree-tracked worktrees may have additional cleanup hooks on session exit that interact with cortex-managed artifacts. Acceptance criterion: after session exit, `interactive/{slug}` branch and worktree are NOT removed unless `ExitWorktree(action="remove")` was explicitly called.

### Security concerns and anti-patterns

- **S1 — One-time consent permission-drift**: a consumer repo that ran `cortex init` six months ago could see `EnterWorktree` fire on a task they didn't intend to authorize. Add `cortex init --revoke-worktree-auth` (only relevant under 2a-ε; under 2a-δ the authorization is skill-loaded and reverts by uninstalling the plugin).
- **S2 — Acting on a `proposed` ADR**: ADR-0004 promotion is a hard gate. Spec must include either an explicit "promote ADR-0004 in commit 1 of this lifecycle" task OR a "wired but flag-gated, flag flips when ADR-0004 promotes" mechanism. Recommended: promote in commit 1; ADR landed in this same PR train.
- **S3 — ADR-0003 surface extension**: if 2a-ε is chosen (writes to consumer CLAUDE.md), a new ADR is required per the three-criteria gate. If 2a-δ is chosen (no consumer write), ADR-0003 surface is preserved.

### Assumptions that may not hold

- **A1 — "Not available to subagents"** (Agent 2's claim): not re-confirmed in the Piebald mirror. Spec must cite the actual source line or test empirically before relying on it.
- **A2 — "Same-session Complete re-invocation is the common case"**: not data-backed; natural workflow suggests cross-session is modal.
- **A3 — Picker selection counts as "explicit instruction"**: behavioral interpretation, not contractually guaranteed.
- **A4 — `cortex-worktrees`-prefixed path convention still applies**: it doesn't; migration to `<repo>/.claude/worktrees/` is complete. Doc drift in `implement.md` must be fixed as prerequisite.
- **A5 — `ExitWorktree(action="keep")` idempotent in cross-session case**: yes (no-op), but it produces a "no session active" diagnostic. Spec must specify the Complete-phase prologue ignores that diagnostic and proceeds.

## Open Questions

1. **Does the platform recognize a loaded skill's description as "project instructions" for the EnterWorktree gate?** This decides 2a-δ vs 2a-ε. **Deferred: will be resolved in Spec by either an empirical test (record-and-replay against current Opus 4.7) or by explicit user choice between 2a-δ (no consumer write) and 2a-ε (consumer CLAUDE.md write + new ADR).**

2. **Are `EnterWorktree` / `ExitWorktree` actually "Not available to subagents"?** Agent 2 cited this; Agent 5 could not re-confirm in the Piebald mirror. **Deferred: spec must cite the source line or test empirically. If true, the overnight-runner branch (F10) is critical; if false, the overnight path may be safer than assumed but still needs explicit handling because of `bypassPermissions` and background-session semantics.**

3. **How often is the Complete phase re-invoked in the same session that called EnterWorktree?** Agent 4 assumed common; Agent 5 challenged. **Deferred: will be resolved by the test-weighting decision in Spec; treat cross-session as primary, same-session as additive.**

4. **ADR-0004 promotion gating**: should it promote as commit 1 of this lifecycle, or should the implementation be flag-gated pending promotion in a separate PR? **Deferred: will be resolved in Spec by recording the chosen sequencing decision.**

5. **Doc-drift fix for `cortex-worktrees` → `<repo>/.claude/worktrees/` in `implement.md`**: is this a prerequisite commit landing before the spec ships, or is it folded into the spec's first task? **Deferred: will be resolved in Spec by recording it as Task 0 or a separate cleanup commit.**

6. **CLAUDE.md surface for 2a-ε (fallback)**: if 2a-δ fails, the fallback writes to consumer CLAUDE.md — but what's the fenced-block sigil shape and how does `cortex init --revoke-worktree-auth` work? **Deferred: spec phase will design the shape only if Open Question 1 resolves to 2a-ε.**

7. **Variant B (`claude --worktree=<path>` fresh session) re-evaluation**: does it still serve a purpose Approach A doesn't cover, or should the Variant A/B narrative collapse to "Interactive Worktree Auto-Entry"? **Deferred: spec phase decision based on whether users have stated need for the fresh-session variant.**
