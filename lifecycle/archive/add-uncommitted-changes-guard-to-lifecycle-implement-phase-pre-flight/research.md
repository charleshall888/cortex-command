# Research: Add uncommitted-changes guard to lifecycle implement-phase pre-flight

## Codebase Analysis

### Files that will change

- **`skills/lifecycle/references/implement.md`** — the sole implementation surface. All demotion interpretations (warning prefix, recommended-flag strip, ordering) operate inside §1, lines 11–26. No helper code, no Python, no tests need touching.

Also touched by `update-item` during `/lifecycle` flow (not manual):
- `backlog/096-add-uncommitted-changes-guard-to-lifecycle-implement-phase-preflight.md` — status/lifecycle_phase write-backs.

### Current pre-flight structure (implement.md §1, lines 11–26)

Options are **prose bullets**, not a structured schema. Each bullet has:

1. A **bold name** (acts as label) — e.g., `**Implement in worktree**`
2. An optional inline parenthetical marker — `(recommended)` appears only on option 1 (line 13)
3. An em-dash prose description — mechanism + "**When to pick**" sub-clause

Only one `(recommended)` marker exists in the file (line 13). There is no structured `recommended: true` field; "recommended" is pure prose. So "demotion" for the recommended-flag component = editing the bold-name line to strip `(recommended)` and prepending a one-line warning to the description.

Option ordering is preserved in the "Dispatch by selection" routing block (lines 20–24); routing uses the **name string** (e.g., `"Implement on main"`), not a position index. Reordering or relabeling changes the prompt but routing match strings must stay in sync — any label edit that changes the canonical substring will silently break dispatch.

### Precedent guard: "Worktree-agent context guard" (implement.md:18)

Exact wording to mirror:

> Immediately before the `AskUserQuestion` call, check the current branch with `git branch --show-current`. If it matches `^worktree/agent-` (the dispatcher is itself running inside a worktree agent context), exclude the **Implement in autonomous worktree** option from the list presented to the user and note "autonomous worktree unavailable from within a worktree agent context" alongside the prompt. The remaining three options (worktree, main, feature branch) are still presented.

Pattern elements to mirror:
- Positioned immediately before the `AskUserQuestion` call
- Runs a single shell check
- Surfaces a short "note" alongside the prompt rather than blocking
- Explicitly enumerates the remaining options

Structural distinction: this is a **removal** guard. The new guard is a **demotion** (modify) guard — similar prose position, different mechanic (edit strings rather than drop an entry).

### Reused pattern from skills/pr/SKILL.md

`skills/pr/SKILL.md:9` declares the precondition `"No uncommitted changes in working tree"`. The workflow at `skills/pr/SKILL.md:24` step 4 states: *"If there are uncommitted changes, warn the user and stop — they should `/commit` first."* The detection command is `git status`; the disposition is **blocking**.

The reuse here is limited to the **detection** (non-empty `git status --porcelain`), not the **disposition** (block vs demote). This ticket deliberately diverges on disposition per its acceptance: "The guard does not block selection — the user can still pick the current-branch option knowingly."

### Existing `git status --porcelain` call sites

1. `skills/overnight/SKILL.md:168` — pre-flight with path filter: `git status --porcelain -- lifecycle/ backlog/`; offers `/commit` and re-checks. Blocking with guided remediation.
2. `claude/statusline.sh:156` — `[ -n "$(GIT_OPTIONAL_LOCKS=0 git status --porcelain 2>/dev/null)" ]` — dirty-tree detection for the statusline dot.
3. `lifecycle/audit-skill-prompts.../plan.md:101–111` — three-state scope compliance (working tree + staged + committed). Best in-repo documentation of status-code interpretation (`??` untracked, ` M` unstaged-modified, `M ` staged-modified, `A ` staged-added).
4. `claude/pipeline/tests/test_merge_recovery.py:59, 529` — expected "clean working tree" test assertions.
5. `lifecycle/agent-driven-demoability.../research.md:249–276` — safety check before `git worktree add --force`.

**Convention**: `git status --porcelain` with **no path filter** is the "whole-tree" dirty check. Path filtering is used when the subset is semantically scoped (overnight path-filters to `lifecycle/ backlog/`). No call site in the repo filters by state category; all treat non-empty porcelain as "dirty."

### #097 composition

`backlog/097-remove-single-agent-worktree-dispatch-and-flip-recommended-default.md`:
- Removes option 1 (**Implement in worktree** via Agent) entirely, deletes §1a.
- Promotes **Implement on current branch** (renamed from "Implement on main") to the recommended default.
- #097 is blocked-by #096 per the decomposition graph (`research/revisit-lifecycle-implement-preflight-options/decomposed.md:15`).

**Composition path**: phrase #096's guard generically ("demote the option that keeps the user on the current branch: strip `(recommended)` if present; prepend warning prefix to the description"). That wording survives both pre-#097 and post-#097 prompts without #097 needing to re-edit the guard.

### AskUserQuestion schema

No skill in the repo uses a structured `recommended: true` option field — "recommended" is always the prose suffix `(recommended)` in the label. This confirms the "demote recommended flag" component is a **label-string edit**, not a schema field toggle.

### Conventions to follow

1. **Guard placement**: Immediately before the `AskUserQuestion` call, mirroring the worktree-agent context guard at `implement.md:18`.
2. **Prose style**: Bold-label introduction (e.g., `**Uncommitted-changes guard**:`) followed by a single paragraph explaining the check, what changes in the option list, and what note accompanies the prompt.
3. **Detection**: `git status --porcelain` with no path filter; non-empty stdout = trigger.
4. **Demotion semantics in prose**: strip `(recommended)` suffix if present, prepend a short warning sentence to the option's description; keep the option selectable.
5. **Forward-compat phrasing**: refer to the option abstractly ("the option that keeps the user on the current branch") rather than by current name.
6. **No side effects**: do not offer `/commit`, do not re-check, do not reorder other options. Overnight's "offer /commit and re-check" is a block-then-remediate shape — not the non-blocking demote shape this ticket wants.

### Integration points and dependencies

- **Hard dependency**: none. Single-file text edit.
- **Ordering dependency**: #096 must land before #097.
- **No tests to update**: no test suite exercises the pre-flight prompt flow.
- **No symlink sync**: `skills/` symlinks to `~/.claude/skills/` — edits propagate automatically.

## Web Research

### `git status --porcelain` semantics

- `??` untracked (shown by default; suppress with `-uno` or `--untracked-files=no`)
- First char = index (staged), second char = working tree (unstaged)
- Index codes: `M A D R C T`; working-tree codes: `M T D R C`
- Unmerged pairs: `DD AU UD UA DU AA UU`
- `!!` ignored (only shown with `--ignored`)

Key behaviors relevant to the guard:
- Untracked files DO appear by default — "non-empty" includes untracked-only.
- Stashes do NOT appear in porcelain v1 (requires `--show-stash`, v2 only).
- Alternative clean-tree check `git diff-index --quiet HEAD --` (exit 0 = clean) MISSES untracked — so `git status --porcelain` is the correct primitive for "anything uncommitted, including untracked."

### AskUserQuestion tool schema

Official schema (Anthropic Agent SDK docs):

```json
{
  "questions": [{
    "question": "...",
    "header": "Format",
    "options": [
      { "label": "Summary", "description": "Brief overview" },
      { "label": "Detailed", "description": "Full explanation" }
    ],
    "multiSelect": false
  }]
}
```

Key facts for the demote pattern:
- Each option has only `label` and `description` (TS SDK adds `preview`). No `recommended: true`, no `disabled`, no dynamic-value hook.
- `(Recommended)` is a label-suffix convention — stripping it is the only way to de-recommend.
- Every option the model emits is selectable — no way to make an option un-selectable.
- Descriptions are static strings in the tool call payload; the skill composes the payload at runtime based on its own git check.
- Constraints: 1–4 questions per call, 2–4 options each, 60s timeout.
- AskUserQuestion is NOT available inside Agents spawned via the Agent tool.

### Prior art for "demote but keep selectable" in CLI wizards

- **Inquirer.js `disabled` field** (npm `@inquirer/select`): closest UI prior art, but makes the option non-selectable. Issue [terkelg/prompts#96](https://github.com/terkelg/prompts/issues/96) evidences community demand for "grey out but still selectable" — rarely native in CLI libraries.
- **Block-style precedents**: cargo/cargo-release, pnpm publish, npm version all hard-abort on dirty tree (bypass flag opt-in).
- **Warn-style precedents**: gh CLI's `gh pr create` prints `"Warning: X uncommitted changes"` and proceeds.
- **git-town**: auto-stashes by default (v14 added `--stash` flag).

Dominant pattern in publish/release tooling is block-then-bypass-flag; the warn-and-proceed pattern (gh CLI) is less common but real.

### "Dirty tree" warning language in adjacent tools

- `"working tree is dirty"` (cargo, Nix)
- `"Git working directory not clean"` (npm)
- `"Unclean working tree"` (pnpm)
- `"uncommitted changes"` (gh CLI, git-town)
- `"Please commit or stash your changes"` (git native, checkout conflict)

Common phrasing candidate: `"Warning: uncommitted changes — …"` or `"Not recommended: working tree is dirty. …"`.

### Key links

- [git-status docs (porcelain v1/v2)](https://git-scm.com/docs/git-status)
- [AskUserQuestion — Handle approvals and user input](https://code.claude.com/docs/en/agent-sdk/user-input)
- [Piebald-AI AskUserQuestion system prompt dump](https://github.com/Piebald-AI/claude-code-system-prompts/blob/main/system-prompts/tool-description-askuserquestion.md)
- [Inquirer select (disabled pattern)](https://www.npmjs.com/package/@inquirer/select)
- [gh CLI "uncommitted changes" #5848](https://github.com/cli/cli/issues/5848)
- [cargo --allow-dirty #9398](https://github.com/rust-lang/cargo/issues/9398)

### Anti-patterns / gotchas

- Don't use `git diff-index --quiet HEAD` alone — misses untracked.
- Don't try to encode "recommended" as a structured flag — schema has no such field.
- Don't expect visual styling — demotion signal must live in the text itself.
- Don't rely on AskUserQuestion in inner Agents — unavailable there.

## Requirements & Constraints

### requirements/project.md (governing philosophy)

- **Complexity earns its place** (line 19): "Complexity: Must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct."
- **Daytime work quality** (line 17): "Research before asking. Don't fill unknowns with assumptions."
- **ROI** (line 21): "ROI matters — the system exists to make shipping faster, not to be a project in itself."
- **Iterative improvement** (line 31): "Maintainability through simplicity: Complexity is managed by iteratively trimming skills and workflows."

No lifecycle-area or skills-area requirements doc exists; `project.md` is the only governing file.

### requirements/pipeline.md

No direct coverage. Tangential signals:
- **Atomicity convention** (lines 21, 123): "All state writes are atomic." Not binding here — guard is read-only.
- **Rationale convention** (line 127): non-obvious decisions should record reasoning.

### requirements/multi-agent.md, observability.md, remote-access.md

Nothing relevant to git-state guards or skill pre-flight UX.

### Related backlog items

- `backlog/093-modernize-lifecycle-implement-phase-preflight-options.md` — parent epic. Defines 4-children dependency graph (094, 095 parallel; 096 → 097). End state: 3 options with #096 guard on option 1.
- `backlog/097-remove-single-agent-worktree-dispatch-and-flip-recommended-default.md` — blocked-by #096. Flips recommended default to "Implement on current branch" behind the guard.
- `backlog/079-integrate-autonomous-worktree-option-into-lifecycle-pre-flight.md` — completed. Established the 4-option layout this ticket modifies.

### Retros

No retros mention trunk-safety incidents or failed "implement on main" runs. Closest adjacent:
- `retros/2026-04-12-2038-lifecycle-implement-worktree-dispatch.md` — "substantive `implement.md` changes must go through `/lifecycle`."
- `retros/2026-04-07-0938-lifecycle-037-and-skill-improvements.md` — touches `implement.md` P5 handling; unrelated.

### Project rules

`CLAUDE.md` and global rules do not specify AskUserQuestion option structuring, warning text tone, or git-state guard conventions. Precedent is set by adjacent skills (`skills/pr`, `skills/overnight`), both of which **block**.

### Architectural constraints

- **Only runs when current branch is `main`/`master`** — the pre-flight `AskUserQuestion` is itself gated by `implement.md:11`. Outside that branch the guard is moot.
- **Guard must coexist with #097's default-flip** — acceptance explicitly says "even after #097 lands."
- **Reversible-decision epistemic standard** — silence in retro corpus cannot support a one-way-door change; guards (reversible) are fine; hard blocks on thin evidence are not — reinforces the "warn/demote, don't block" choice.

### Explicit scope boundaries

Out of scope (per backlog/096):
- Plan-complexity gate (rejected in research DR-3).
- Criticality-aware demotion (deferred).
- Flipping the recommended default (that's #097).
- Modifying the other three options.

Ticket-declared spec-phase decisions:
- Exact warning text surfaced when guard fires.
- Whether "demote" means reordering in AskUserQuestion list, changing recommended flag, or both.

## Tradeoffs & Alternatives

### Alternative 1: Suggested approach — non-blocking demotion (warning prefix + strip recommended flag)

Run `git status --porcelain` before `AskUserQuestion`; if non-empty, prepend a one-line warning to the description of the current-branch option and strip its `(recommended)` label suffix. Keep the option selectable at its original position.

- Implementation complexity: **very low**. One Bash call, one conditional, two string rewrites. ~10–15 lines of prose in `implement.md §1`, zero new files, no scripts. Conditional depth: one.
- Reversibility: **high**. Misfire costs at most a noisier prompt; the user can still select the now-unrecommended option.
- Consistency: sits next to the existing Worktree-agent context guard. Reuses `git status --porcelain` idiom from `skills/pr` and `skills/overnight`. Diverges from their **blocking** disposition deliberately, per ticket.
- UX on fire: low friction; inline warning, still selectable, no second prompt.

### Alternative 2: Block instead of demote

Hard-refuse the current-branch option when dirty (exclude from list like worktree-agent guard, or halt with error).

- Complexity: low, slightly simpler than Alt 1.
- Consistency: maximally consistent with `skills/pr` — but **explicitly rejected by the ticket** ("demote, not block") and research DR-3.
- UX: high friction; forces worktree/feature-branch even when dirty state is intentional.
- **Conflicts with #097**: #097 wants current-branch recommended; blocking inverts that whenever tree is dirty (common at lifecycle-start).

### Alternative 3: Auto-stash and proceed

If dirty and user picks current-branch, `git stash push -u` before dispatch, `git stash pop` after.

- Complexity: **high**. New machinery across §1, §2, §4. Must handle stash-pop conflicts with task output, partial-failure semantics, avoid stashing on worktree/daytime paths.
- Reversibility: low — stash-pop conflict after task success leaves merged code plus un-poppable stash.
- Consistency: **none**. No lifecycle phase currently runs `git stash`. First such automation.
- UX: best when it works; worst when it doesn't.

### Alternative 4: Demote via reordering only

Move current-branch option to last position when dirty; no description edit, no flag strip.

- Complexity: trivial.
- Consistency: weak — positional de-emphasis has no precedent.
- UX: **minimal signal**. Users scanning quickly won't notice. Fails acceptance criterion ("description prefix includes a one-line warning").
- **Conflicts with #097**: #097 foregrounds option 3; Alt 4 backgrounds it — the two act at cross purposes.

### Alternative 5: Warning prose without stripping recommended flag

Prepend warning to description but keep `(recommended)` label.

- Complexity: very low.
- UX: **ambiguous signal**. Badge says "pick this"; description says "but probably don't." Fails acceptance "it is not the recommended default for this invocation."

### Alternative 6: Do nothing / defer

Drop #096, rely on user judgment.

- Complexity: zero.
- **Blocks #097**: `blocked-by: [96]` — dropping #096 blocks #097 indefinitely or forces #097 to flip default without a guard, which research DR-3 explicitly rejected.

### Uncommitted-state subset verdict

For any alternative where it matters, the relevant subset is "work that would contaminate a main-branch implementation commit":

| State | Count toward guard? | Reasoning |
|-------|---------------------|-----------|
| Untracked (`??`) | YES | Task sub-agents may `git add .` these unintentionally |
| Unstaged (` M`) | YES | Same |
| Staged (`M `, `A `) | YES | Already prepared for commit — would land on main |
| Unmerged (`UU` etc.) | YES | Shouldn't dispatch into an active merge conflict |
| Stashed | NO | Intentionally set aside |
| Ignored (`!!`) | NO | Never enter commits; excluded by porcelain default |

**Verdict**: plain `git status --porcelain` (no flags) is the exact right subset. Do NOT pass `--untracked-files=no`, `--ignored`, or consult `git stash list`.

### Recommended approach: Alternative 1

1. Minimal complexity — ~15 lines of prose, no code, no tests.
2. Alignment with existing patterns — reuses porcelain detection; sits next to existing Worktree-agent context guard.
3. Non-blocking UX honored per ticket's deliberate choice.
4. Composes cleanly with #097 (acts on disjoint surfaces — strip flag when set, prepend warning independently).
5. Plain porcelain subset is correct by default.

## Adversarial Review

### Failure modes and edge cases

- **Precedent mismatch**: The Worktree-agent context guard is a **removal** pattern (excludes the option); #096 is a **mutation** pattern (edits label/description of a still-present option). No existing guard in the skill does label-text surgery, so the implementer is inventing a pattern, not reusing one. Risk: label edits that change the canonical routing-match substring (`"Implement on current branch"` / `"Implement on main"`) will silently break dispatch at lines 20–24.

- **Guard never fires on resumed feature-branch sessions**: `implement.md:11` only presents the AskUserQuestion when current branch is `main`/`master`. If the user resumes on a feature branch with a dirty tree, implementation dispatches immediately with no demotion signal. The guard is silently inoperative for half of reachable pre-flight states.

- **Dirt carried to a new feature branch is unprotected**: If the user is on dirty main and picks "Create feature branch", `git checkout -b feature/{slug}` carries the dirty working tree across (git does not refuse uncommitted-but-unstaged changes unless the switch would overwrite). Foreign dirt lands on the feature-branch's first lifecycle commit. Guard only demotes current-branch; selecting any other option with dirt is arguably worse because the dirt pollutes a branch named after the lifecycle slug.

- **Worktree paths silently strand uncommitted work**: "Worktree" and "Autonomous worktree" options create a new worktree from HEAD. Overnight at `skills/overnight/SKILL.md:168` blocks explicitly because "the overnight worktree is created from HEAD, so these files will not be visible to the runner." This implement-phase guard only demotes current-branch, leaving worktree options presented normally even though they silently discard the user's uncommitted work. The exact failure mode overnight blocks, this guard permits.

- **Submodule false positives**: Since git 2.13, default `diff.ignoreSubmodules` and `status.submoduleSummary` settings surface a submodule at a non-registered commit as ` M submodulename` in porcelain output. Repos with vendored submodules false-positive on every invocation. The "porcelain is the exact right subset" claim assumed a submodule-free repo without verification.

- **cwd anchor unspecified**: If the user invoked `/lifecycle implement` from a subdirectory or from within `.claude/worktrees/{task-name}`, `git status --porcelain` returns the status of the current worktree rather than the main repo. The precedent guard at line 18 uses `git branch --show-current`, which has the same cwd sensitivity — no prior art fixes the root.

- **Flag-strip is dead code pre-#097**: `(recommended)` appears on implement.md:13 (option 1), not on the current-branch option. Until #097 lands, the "strip `(recommended)`" half of the demotion is a no-op on its target. The acceptance criterion's "(even after #097 lands)" disguises that the entire flag-flip half of the demotion is inert for the current release window.

- **Label-vs-description placement ambiguity**: Ticket says "description prefix includes a one-line warning" but doesn't bar placing the warning in the label for visibility. A zealous implementer writing `label: "[WARNING] Implement on current branch"` would silently break routing's prose match against `"Implement on current branch"`. Routing-safety discipline is not enforced by schema.

- **Race between check and selection**: AskUserQuestion has a 60s timeout. The user's editor autosave, a background process, or a parallel Claude session can modify the tree between porcelain check and dispatch. The guard reports prompt-time state, not dispatch-time state. No re-check is specified.

- **High false-positive rate on lifecycle artifacts**: Users frequently enter `/lifecycle implement` with intentional uncommitted work — edits to `lifecycle/{feature}/plan.md` or `spec.md` from earlier phases. Overnight's analogous guard **path-filters to `lifecycle/ backlog/` and blocks** precisely because those paths matter. This ticket proposes the opposite filter (unfiltered) with non-blocking demotion — meaning the lifecycle's own in-progress artifact demotes the lifecycle's recommended flow. Training users to ignore a warning that fires every time they run the skill degrades the guard's value.

- **Error handling for porcelain failure unspecified**: If `git status --porcelain` fails (bisect in progress, corrupt index, cd'd out of repo), ticket/research provide no fallback. Overnight's analogous check documents the predicate that prevents this at SKILL.md:185; implement.md has no such predicate.

### Security concerns

- **Filename injection via porcelain output**: `--porcelain=v1` quotes special-char paths in backslash-escaped form but is not entirely byte-safe in default mode. If the guard surfaces porcelain text verbatim in the warning prose (overnight's precedent does list paths), a filename with newline/backtick/`$()` content can mangle the prompt. Injection becomes reachable if any later step pipes porcelain into a shell context (e.g., `/commit` handoff staging the paths).

### Assumptions that may not hold

- **"Zero trunk-safety incidents in retros" is a negative-signal inference**: Absent events can mean never-happened, not-retro'd, or not-classified-under-that-heading. The measurement was taken under the pre-#097 regime where worktree was default — it has zero predictive value for the post-#097 regime the guard is meant to protect.

- **#096/#097 overnight sequencing**: If both tickets are queued in the same overnight session, the runner might merge in wrong order (or in parallel if the scheduler loosens blocked-by). #097 landing before #096 means a regression window: users see `"Implement on current branch (recommended)"` on a dirty tree with no guard. Nothing in either ticket asserts runner-level dependency enforcement.

- **Non-interactive paths**: AskUserQuestion is explicitly forbidden inside `Agent(isolation: "worktree")` per implement.md:64–66 and unavailable in the daytime pipeline. The guard therefore fires only in the "user on main, live-steered, pre-dispatch" case. Overnight and daytime-pipeline paths — the exact contexts where a human can't evaluate the warning — have no dirty-tree protection.

- **Acceptance criterion is not independently testable**: No schema-level assertion. Prose in a label/description string evaluated by a language model at prompt time. A unit test can check "if porcelain non-empty, the option text contains 'warning'" but cannot assert correct perception of demotion. Correctness rests on prose re-interpreted by each model version at each invocation.

- **Single defense on a newly exposed surface**: Before #097, worktree default self-mitigated dirty-tree risk. After #097, the guard is the **only** defense between a dirty tree and a trunk-based dispatch. A non-blocking prose warning that users are conditioned to ignore (via the high false-positive rate on lifecycle artifacts) is a thin defense for a newly-exposed high-impact failure mode.

## Open Questions

The following questions remain open for the Spec phase to resolve.

1. **Lifecycle-artifact false-positive mitigation**: Should the guard path-filter to exclude `lifecycle/` and `backlog/`, or fire on the whole tree? Whole-tree is simpler and consistent with skills/pr, but triggers on every implement invocation that follows plan without an interstitial commit — training users to ignore the warning. Path-filtering complicates the guard but keeps warning frequency meaningful. (Note: the adversarial review flagged this as a likely operational issue; it is not addressed by the ticket.)

2. **Warning placement: label vs description**: Ticket acceptance says "description prefix includes a one-line warning." Is the description-only placement a hard requirement, or may the implementer mirror part of the warning into the label for visibility? Label edits risk breaking the routing match at `implement.md:20–24`. Deferred: will be resolved in Spec by committing to description-only placement OR specifying a routing-safe label format.

3. **Exact warning text**: One concise sentence. Candidates surfaced by research: `"Warning: working tree has uncommitted changes — …"` (gh CLI style), `"Not recommended while working tree is dirty …"`, `"Uncommitted changes present — this will mix into trunk commits."`. Deferred: will be resolved in Spec by selecting the final text.

4. **Pre-#097 behavior of flag-strip**: `(recommended)` does not exist on the current-branch option today; the strip is a no-op until #097 lands. Is the guard description written to document the strip unconditionally (correct under both regimes but inert pre-#097), OR only to take effect after #097, OR some other composition? Deferred: will be resolved in Spec by the generic-phrasing approach (strip `(recommended)` **if present** + always prepend warning), which is the recommended composition path from the Codebase agent.

5. **Error handling for porcelain failure**: If `git status --porcelain` exits non-zero or returns an unexpected state, what should the guard do — fall through unguarded, surface error, halt pre-flight? Deferred: will be resolved in Spec by specifying "fall through unguarded and surface a one-line diagnostic alongside the prompt" or similar.

6. **cwd anchor**: Should the guard explicitly cd to the repo root or invoke `git -C <root> status --porcelain`? Precedent (line 18) doesn't anchor either. Deferred: will be resolved in Spec — likely "run from cwd; document that implement.md's existing branch check at line 11 already assumes cwd = repo root, and the guard inherits that assumption."

7. **Submodule false positives**: Verify whether this repo's submodule configuration causes false positives. If yes, add `--ignore-submodules=all` or equivalent; if no, document "no-op" and move on. Deferred: will be resolved in Spec (quick verification task).

8. **Scope boundary with adversarial "other options" concerns**: The adversarial review surfaced legitimate dirty-tree risks for "Create feature branch" (dirt carries across) and the two worktree options (dirt silently stranded). These are out-of-scope per the ticket ("Modifying the other three options"). Confirm in Spec that this scope boundary holds and queue a follow-up ticket (or defer) for the broader protection.

9. **Non-interactive-path inertness**: The guard fires only in the live-steered-on-main path. Daytime-pipeline and worktree-dispatch paths have no equivalent protection. Is that the intended scope — "daytime live interaction only"? Deferred: will be resolved in Spec by documenting the scope and either accepting inertness elsewhere or queueing a follow-up.

10. **Filename injection**: Will the guard surface porcelain output verbatim in the prompt (overnight precedent) or only a boolean "working tree has uncommitted changes" signal? The latter avoids injection risk entirely. Deferred: will be resolved in Spec by choosing boolean-only messaging in the warning prefix.

None of these questions block research — each has a clear preferred resolution that Spec will commit to. Items 1 and 8 are the highest-impact and should be explicit in the spec's acceptance criteria.
