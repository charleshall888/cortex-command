# Specification: Lifecycle implement — config-defaulted branch mode (Approach C)

## Problem Statement

When `/cortex-core:lifecycle implement` runs on a `main`/`master` checkout, today's three-option branch picker (`Implement on current branch` / `Implement on feature branch with worktree` / `Create feature branch`) fires as a conscious re-decision per feature. The ticket names this re-decision as the *primary* friction (the literal `cd` keystroke is secondary). The observed behavior shift is concrete: feature #246's 25-commit removal sweep ran entirely on trunk because the worktree path felt heavier than the work warranted — undermining the design intent of #237's daytime-autonomous retirement (the worktree-interactive flow exists to protect trunk and give parallel batches index-safe isolation; if the replacement gets skipped, the retirement bought less than intended). This lifecycle externalizes the picker default to a per-repo `lifecycle.config.md::branch-mode` field so the worktree flow is the path of least resistance for the common case, with the picker remaining as fallback under a documented set of carve-outs (uncommitted changes; concurrent live interactive worktree for this feature).

This is the **planned next phase** of the multi-step interactive worktree lifecycle per ADR-0004 (proposed). Variant A/B was the deliberately-scoped first cut (epic #240's "T10 ships only the create + handoff step"); this lifecycle adds the per-repo default. The companion deferred work — auto-entering the worktree mid-session via `EnterWorktree(path=...)` (Approach A) — is captured as a follow-up backlog ticket. One of A's blockers is a genuine Anthropic platform constraint (`ExitWorktree` cross-session no-op interacting with the multi-step Complete phase's same-session re-invocation pattern); the other elements of A's deferred design surface (consumer-repo authorization via `cortex init`, the WorktreeCreate-hook bypass interaction) are cortex-side scoping decisions the follow-up ticket will address.

## Phases

- **Phase 1: Config schema + minimal parser** — add `branch-mode` to `lifecycle.config.md`; introduce a minimal `cortex_command/lifecycle_config.py` primitive returning the raw `branch-mode` value (no typed surface, no closed-set normalization in the primitive).
- **Phase 2: implement.md short-circuit + carve-outs** — picker suppression when `branch-mode` is set, working tree is clean, AND no concurrent live worktree exists for this feature; picker fires under any carve-out condition.
- **Phase 3: Conditional pause sentinel** — extend the parity test with a `conditional pause` rationale tag that checks for the structural marker (`read_lifecycle_config` invocation); update `SKILL.md:199` to match. The runtime gate is enforced by R3 + R4's unit tests; R5 is documentation parity.
- **Phase 4: ADR-0004 amendment + Approach A follow-up ticket** — record the C/A split framing in the existing proposed ADR; file the follow-up ticket capturing A's deferred design surface (one platform constraint + cortex-side scoping decisions).

## Requirements

1. **`branch-mode` field added to `lifecycle.config.md` schema.** The frontmatter accepts an optional `branch-mode` field with the closed-set values `worktree-interactive | trunk | feature-branch | prompt`. When absent, behavior equals `prompt`. Match is **case-sensitive**, **whitespace-stripped** (leading/trailing whitespace ignored), and **last-wins** on duplicate keys (per `yaml.safe_load` default). Commented value (`branch-mode: #...`) parses as null → treated as unset. The body of `cortex/lifecycle.config.md` gains a `## Branch Mode` section documenting the field, valid values, the carve-outs, and the normalization semantics. **Acceptance**: `grep -c '^## Branch Mode$' cortex/lifecycle.config.md` = 1. `grep -c 'branch-mode:' cortex/lifecycle.config.md` ≥ 1 (the example value committed in the file). **Phase**: 1. **Priority**: must.

2. **Minimal parser primitive `cortex_command/lifecycle_config.py`.** Public function `read_branch_mode(repo_root: pathlib.Path) -> str | None` returns the **raw** `branch-mode` frontmatter value (whitespace-stripped) or `None`. Behavior: missing file → `None`; malformed YAML frontmatter → `None` + stderr warning naming the file and the parse error; field absent → `None`; field present → the raw value as a string. The primitive does **not** validate against the closed set — that validation is the caller's responsibility (so that future fields can be added without re-shaping this primitive). Unit tests in `tests/test_lifecycle_config.py` cover: missing file, malformed YAML, field absent, field present with each closed-set value, field present with a duplicate key, field present with whitespace padding, field present with a commented-out value. The primitive is intentionally narrow; migration of the five existing ad-hoc `lifecycle.config.md` parsers (cli_handler.py:58, critical-review SKILL.md:38, complete.md:9, walkthrough.md:88, plan.md:17) is **deferred to a separate backlog ticket** which will survey those consumers' needs and decide the right primitive shape. This spec does not pre-commit to an API on their behalf. **Acceptance**: `just test tests/test_lifecycle_config.py` exits 0. `python3 -c "from cortex_command.lifecycle_config import read_branch_mode; v = read_branch_mode('.'); assert v is None or isinstance(v, str)"` exits 0. **Phase**: 1. **Priority**: must.

3. **`implement.md` §1 short-circuits picker when `branch-mode` set + clean tree + no concurrent worktree.** §1 invokes `read_branch_mode()` once at phase entry, applies the caller-side closed-set check (closed set = `{"worktree-interactive", "trunk", "feature-branch", "prompt"}`; values outside the set log a stderr warning and are treated as `None`), then runs the carve-out preflight (per R4 below). When all gates pass:
   - `worktree-interactive` → skip picker, proceed directly to §1a (worktree-interactive path)
   - `trunk` → skip picker, proceed on current branch
   - `feature-branch` → skip picker, proceed to feature-branch path
   - `prompt` or `None` → picker fires as today
   
   The skill prose explicitly names the `read_branch_mode` invocation as the structural marker that gates the dispatch (parity test R5 looks for this marker). **Acceptance**: `grep -c 'read_branch_mode\|lifecycle_config' skills/lifecycle/references/implement.md` ≥ 1 (the structural marker). `grep -c 'worktree-interactive\|^- *trunk\b\|feature-branch\|prompt' skills/lifecycle/references/implement.md` ≥ 4 (the four closed-set values documented in §1 prose). **Phase**: 2. **Priority**: must.

4. **Carve-out preflight: picker fires under documented hazardous states.** The picker fires regardless of `branch-mode` value when **any** of these conditions hold:
   - (a) `git status --porcelain` is non-empty (uncommitted-changes hazard — preserves the demote-and-warn affordance at `implement.md:22` with the warning prefix `Warning: uncommitted changes in working tree — this will mix them into the commit on main.`)
   - (b) `cortex/lifecycle/sessions/{slug}.interactive.pid` exists AND its PID is live (per `kill -0`) — a concurrent interactive worktree session is active for this slug; suppressing the picker on this state would route commits onto main concurrent with the sibling worktree's diverging history, exactly the shared-index hazard the worktree-interactive flow was built to prevent. The existing liveness check at `implement.md:78–82` is **lifted out of §1a into a shared §1 preflight** so it runs on all three short-circuit branches (`trunk`, `feature-branch`, `worktree-interactive`) — not only the worktree-interactive path.
   
   Skill prose names both carve-outs explicitly. When either carve-out fires, the picker re-presents the three options as today, and the user sees the relevant cue (warning prefix for (a), liveness rejection at §1a for (b) if they then pick worktree-interactive). **Acceptance**: Test fixture in `tests/test_lifecycle_implement_branch_mode.py` covering: (a1) `branch-mode: trunk` + clean tree + no live worktree → picker suppressed; (a2) `branch-mode: trunk` + simulated dirty tree → picker fires with warning prefix; (a3) `branch-mode: trunk` + simulated live `{slug}.interactive.pid` → picker fires; (a4) `branch-mode: worktree-interactive` + clean tree + no live worktree → picker suppressed, routes to §1a; (a5) `branch-mode` unset → picker fires. `just test tests/test_lifecycle_implement_branch_mode.py` exits 0. **Phase**: 2. **Priority**: must.

5. **Conditional-pause sentinel in `tests/test_lifecycle_kept_pauses_parity.py`.** Add support for a `conditional pause` rationale tag, analogous to the existing `phase-exit pause` tag handling (lines 137–164 of current file). For an inventory entry whose rationale contains the literal phrase `conditional pause`:
   - Direction 1 validation passes when (a) an `AskUserQuestion` reference exists within ±35 lines of the anchor AND (b) the **structural marker** `read_branch_mode` (or, more permissively, `lifecycle_config`) appears within ±35 lines of the anchor — this marker is the actual control-flow gate emitted by R3
   - Direction 2 validation behaves unchanged
   - On direction 1 (b) failure, surface `conditional pause at {anchor} lacks structural marker (read_branch_mode or lifecycle_config) within ±35 lines`
   
   This is **documentation parity enforcement**, not structural enforcement of the runtime gate. The runtime gate is enforced separately by R3 (presence of `read_branch_mode` invocation in skill prose) + R4 (unit-test coverage of the dispatch + carve-outs). R5's role is to keep the inventory rationale's `conditional pause` tag honest with the existence of the structural marker — together with R3, this prevents the regression path where short-circuit and tag are removed in lockstep (R3's grep fails because the marker is gone, regardless of R5's state). **Acceptance**: `grep -c 'conditional pause' tests/test_lifecycle_kept_pauses_parity.py` ≥ 1. `just test tests/test_lifecycle_kept_pauses_parity.py` exits 0 after R6 lands. **Phase**: 3. **Priority**: must (documentation parity; R3 + R4 carry the structural enforcement).

6. **`SKILL.md:199` inventory entry tagged conditional.** The kept-pauses inventory entry for `skills/lifecycle/references/implement.md:22` is updated to: `skills/lifecycle/references/implement.md:22` — conditional pause: branch selection on main (trunk vs feature-branch-with-worktree vs feature branch). Suppressed when `lifecycle.config.md::branch-mode` is set AND the working tree is clean AND no concurrent live interactive worktree exists for the feature slug. The new rationale matches R5's sentinel literal-phrase requirement. **Acceptance**: `grep -c 'conditional pause' skills/lifecycle/SKILL.md` ≥ 1. The parity test (R5) passes against the updated inventory. **Phase**: 3. **Priority**: must.

7. **ADR-0004 amendment records C/A split framing.** `cortex/adr/0004-multi-step-complete-and-interactive-worktree-lifecycle.md` gains a new section (heading `## branch-mode default (Approach C) + Approach A deferred design surface`) recording: (a) Variant A/B was the deliberately-scoped first cut per epic #240; (b) this lifecycle adds the per-repo `branch-mode` default; (c) Approach A's deferred design surface comprises one platform-side constraint (`ExitWorktree`'s documented cross-session scope clause makes it a no-op for worktrees created outside the current session — when the multi-step Complete phase re-invokes in the same session that auto-entered, the Step 8 hard guard requires an out-of-worktree CWD that `ExitWorktree` cannot provide programmatically) plus cortex-side scoping decisions (consumer-repo authorization via `cortex init` opt-in clause, interaction with the WorktreeCreate-hook bypass documented in ADR-0004); (d) forward reference to the follow-up backlog ticket from R8. The ADR's `Status:` field remains `Proposed` (this amendment does not promote it to Accepted). **Acceptance**: `grep -c '^## branch-mode default' cortex/adr/0004-multi-step-complete-and-interactive-worktree-lifecycle.md` = 1. `grep -c 'Approach A' cortex/adr/0004-multi-step-complete-and-interactive-worktree-lifecycle.md` ≥ 1. **Phase**: 4. **Priority**: should (institutional memory; ships independently of the user-facing feature).

8. **Follow-up backlog ticket filed for Approach A's deferred design surface.** A new backlog ticket at `cortex/backlog/NNN-lifecycle-implement-auto-enter-worktree-deferred.md` (numeric slug assigned at filing time) with frontmatter: `status: backlog`, `priority: medium`, `type: feature`, `tags` including `lifecycle`, `worktree-interactive`. Body documents:
   - The one platform-side constraint (`ExitWorktree` cross-session no-op interacting with same-session Complete-phase re-invocation)
   - The cortex-side scoping decisions (`cortex init` opt-in clause for consumer-repo authorization; WorktreeCreate-hook bypass interaction with auto-enter)
   - The acceptance criteria for `status: refined`: a cortex-only project decision documenting the cross-session-exit interaction model (e.g., "auto-enter only on same-session implement→complete; explicit user-relaunch on cross-session resume documented in the handoff message"), plus a decision on consumer-repo authorization shape
   - Cross-references to this lifecycle's spec, ADR-0004 amendment (R7), and the underlying Anthropic schema documentation
   
   The ticket's framing is "decompose A's design surface and ship," not "wait for upstream." **Acceptance**: `ls cortex/backlog/*lifecycle-implement-auto-enter-worktree-deferred*.md` returns exactly one file. `grep -c 'ExitWorktree' cortex/backlog/*lifecycle-implement-auto-enter-worktree-deferred*.md` ≥ 1. The new ticket appears in `just backlog-index` regenerated output. **Phase**: 4. **Priority**: should (forward reference for future work).

## Non-Requirements

- **Approach A (`EnterWorktree(path=...)` mid-session auto-enter) is NOT in scope.** Captured as a follow-up backlog ticket (R8) with one platform constraint + cortex-side scoping decisions documented.
- **Migration of the five existing ad-hoc `lifecycle.config.md` parsers is NOT in scope.** Each existing consumer continues using its inline parser. A separate backlog ticket will survey those consumers and decide whether to extend `lifecycle_config.py` (and what shape) or migrate them piecemeal. This lifecycle does **not** pre-commit to a multi-field API on their behalf.
- **Per-feature `branch-mode` override via backlog frontmatter is NOT in scope.** Per-repo defaults only; the simplicity defaults favor deferring per-feature override until a concrete need surfaces.
- **`docs/internals/sdk.md:216` row changes are NOT in scope.** No `EnterWorktree` or `ExitWorktree` is introduced.
- **Consumer-repo CLAUDE.md authorization for `EnterWorktree` is NOT in scope.** The `cortex init` opt-in step is a deliverable of the deferred Approach A ticket (R8).
- **Variant B handoff message text changes are NOT in scope beyond what R3 requires.** This lifecycle does not rewrite the Variant A/B narrative.
- **Pre-existence check on `feature-branch` short-circuit (avoiding silent `git checkout` over another feature's branch state) is NOT in scope.** This is an inherited gap from the existing §1 feature-branch path; out of scope for this lifecycle. Noted in Edge Cases as a candidate follow-up.
- **Sandbox preflight failure re-prompt behavior change is NOT in scope.** Under `branch-mode: worktree-interactive` suppression, a preflight failure inside §1a still halts via the existing `sys.exit(2)` path. This is accepted behavior; users who want explicit picker context unset `branch-mode`.

## Edge Cases

- **`branch-mode` set to an invalid value (typo, unsupported value).** Caller-side closed-set validation in §1 (R3) treats invalid values as `None`, writes a stderr warning naming the file and the rejected value, and falls through to picker. Verified by R2's unit-test coverage (the primitive returns the raw value; the caller validates).
- **`branch-mode: TRUNK` (case mismatch) / `branch-mode: ' trunk '` (whitespace padding).** R2 whitespace-strips but is case-sensitive. `TRUNK` falls through to `None` with a stderr warning; user sees the picker. The warning is the failure signal; users who want the suppression they expected can correct the casing.
- **`branch-mode:` appears twice in frontmatter.** `yaml.safe_load` returns the last value (standard semantics). R2 documents this as last-wins.
- **`branch-mode: # commented out`.** YAML parses this as null; R2 treats null as unset; picker fires.
- **`branch-mode: trunk` + clean tree + concurrent live interactive worktree for this feature.** R4 carve-out (b) fires: picker is presented. If user picks worktree-interactive, §1a's liveness check at lines 78–82 still fires with the existing rejection. (No shared-index hazard.)
- **`branch-mode: worktree-interactive` + concurrent live worktree.** R4 carve-out (b) fires same as above: picker fires; user re-decides.
- **`branch-mode: worktree-interactive` + overnight runner active for this repo.** R4 doesn't list this carve-out (no `runner.pid` check at §1 preflight today). The existing overnight guard at `implement.md:84–90` lives inside §1a and runs after the picker short-circuit routes there — the rejection happens inside §1a, not §1. Net effect: under `branch-mode: worktree-interactive` suppression with overnight active, §1a fires the overnight-guard sidecar and exits §1a with the existing diagnostic. No silent regression; the rejection surface is one step deeper than today's picker context, but still surfaces.
- **`branch-mode: feature-branch` on a checkout already on `feature/{this-slug}`.** Picker isn't triggered today on non-main; the spec's behavior is unchanged here.
- **`branch-mode: feature-branch` on a checkout already on `feature/{other-slug}`.** Today's behavior (when invoked from non-main): picker doesn't fire; the feature-branch path's `git checkout feature/{this-slug}` runs without pre-existence checks. This spec inherits that gap. **Out of scope** for this lifecycle (see Non-Requirements); a follow-up backlog ticket can address it.
- **Sandbox preflight fails inside §1a after `branch-mode: worktree-interactive` short-circuit.** Existing `sys.exit(2)` path runs without user-initiated context. Accepted per Non-Requirements; documented in the `## Branch Mode` section of `lifecycle.config.md`.
- **Worktree exists from prior session under `branch-mode: worktree-interactive`.** Existing idempotency in `create_worktree()` returns the existing worktree info; no behavior change.
- **Two parallel claude sessions both reading `lifecycle.config.md` simultaneously.** Read-only access; no race.

## Changes to Existing Behavior

- ADDED: `lifecycle.config.md::branch-mode` frontmatter field (`worktree-interactive | trunk | feature-branch | prompt`).
- ADDED: `cortex_command/lifecycle_config.py` minimal parser (`read_branch_mode()`).
- ADDED: `tests/test_lifecycle_config.py` unit tests for the parser.
- ADDED: `tests/test_lifecycle_implement_branch_mode.py` integration test for R3/R4 carve-outs.
- ADDED: `conditional pause` sentinel branch in `tests/test_lifecycle_kept_pauses_parity.py` (checks for structural marker `read_branch_mode` / `lifecycle_config`).
- ADDED: `## Branch Mode` documentation section in `cortex/lifecycle.config.md` body.
- MODIFIED: `skills/lifecycle/references/implement.md` §1 — picker short-circuits when `branch-mode` set AND carve-out preflight (R4) passes; liveness check lifted out of §1a into shared §1 preflight.
- MODIFIED: `skills/lifecycle/SKILL.md:199` — inventory entry retagged as `conditional pause` with full suppression-condition prose.
- MODIFIED: `cortex/adr/0004-multi-step-complete-and-interactive-worktree-lifecycle.md` — new section recording C/A split framing.
- ADDED: One new backlog ticket capturing Approach A's deferred design surface.

## Technical Constraints

- **ADR-0003 (per-repo sandbox registration)**: unchanged.
- **ADR-0004 (multi-step Complete + interactive worktree lifecycle)**: status remains `Proposed`. This lifecycle amends the ADR body but does not promote it.
- **`docs/internals/sdk.md:216`**: row unchanged. No `EnterWorktree` introduced.
- **`docs/overnight-operations.md` overnight tool allowlist**: unchanged.
- **`cortex/requirements/project.md` "Defense-in-depth for permissions"**: honored. No permission surface changes.
- **`cortex/requirements/project.md` "Prefer structural separation over prose-only enforcement"**: the structural gate IS R3 + R4 (the runtime dispatch and its unit tests). R5 is documentation parity; the spec frames it as such honestly rather than overselling.
- **`CLAUDE.md` MUST-escalation policy**: no new MUST/CRITICAL/REQUIRED statements; soft positive routing throughout.
- **`cortex/requirements/project.md` "Skill / phase authoring guidelines"**: R5 + R6 ship in the same commit per "update both the SKILL.md inventory and the parity test together."
- **`cortex/requirements/project.md` complexity principle**: this lifecycle introduces three durable surfaces (config field, minimal parser, conditional-pause sentinel — sized for one consumer each). R7 + R8 add institutional memory. The scope is earned by the named primary friction (#246's behavior shift); the parser primitive is intentionally minimal and does not pre-commit to API decisions on behalf of the deferred five-consumer migration.
- **`cortex/requirements/multi-agent.md` worktree placement rule**: `$TMPDIR/cortex-worktrees/` default unchanged.
- **SKILL.md size cap (500 lines)**: `skills/lifecycle/SKILL.md` and `skills/lifecycle/references/implement.md` are both within budget after the edits.

## Open Decisions

None. Implementation-level decisions (exact call-site placement of `read_branch_mode()` in `implement.md`; exact format of the stderr warning string; whether to fold the lifted liveness preflight into the existing §1a check or duplicate-and-update both sites; fixture shape in `tests/test_lifecycle_implement_branch_mode.py`) are deferred to plan/implement-phase code-time choices.

## Proposed ADR

None considered. The C/A split framing is recorded as an amendment to the existing proposed ADR-0004 (per R7), not as a new ADR. The amendment captures the deferral as a routine multi-phase continuation of ADR-0004's stated lifecycle; the surprising / hard-to-reverse decisions (WorktreeCreate-hook bypass, `$TMPDIR` placement) are already recorded there.
