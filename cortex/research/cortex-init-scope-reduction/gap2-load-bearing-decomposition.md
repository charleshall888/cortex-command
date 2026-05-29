# Gap 2: Load-bearing decomposition

Re-audit of every `cortex init` write action using a three-way classification (Essential-to-Product / Essential-to-Feature / Convenience-Only). The prior research's binary "load-bearing vs convenience" collapse hid the fact that several writes that *appear* load-bearing only support an opt-in feature path the user may never exercise.

## Audit methodology

**Essential-to-Product (EP).** Cortex's *core* user value — the lifecycle skill writing artifacts under `cortex/lifecycle/{slug}/`, the backlog being readable/writable as files, the overnight runner being able to execute — does not work without the write. A new adopter who only does `cortex init` then runs `/cortex-core:lifecycle my-feature` hits a correctness failure (sandbox prompt-storm, crash, missing read target) without it.

**Essential-to-Feature (EF).** A specific, named, *opt-in* feature requires the write. Removing the write disables that feature only; the user may not have opted into it. Test: would a user who uses only the lifecycle picker's default "Implement on current branch" option ever hit this code path? If not, the write is EF for whichever opt-in path consumes it.

**Convenience-Only (CO).** No feature requires the write — it's a discoverability or friction-reduction artifact (template stubs the user is meant to edit, README files no skill reads, migration cleanup for a deprecated path). Removing it does not disable any feature; users discover the missing scaffolding via the next prompt, hook, or skill error and recover by reading docs.

**Steel-man discipline.** For every EF/CO verdict, I argue the case for the adjacent stronger category and reject only after the steel-man fails on evidence. The prior audit's failure mode was charity in one direction (toward EP); this re-audit applies it both ways.

The rubric per write: (1) what is the consumer (`[file:line]`)? (2) lifecycle/backlog/overnight critical path or opt-in branch? (3) what happens at the consumer site if the write is missing (crash, fallback, skip)? (4) for EF: estimated user fraction touching the opt-in path.

## Per-action audit

| # | Action | Category | Dependent feature (if EF) | Steel-man of opposite | Citation |
|---|--------|---------|---------------------------|------------------------|----------|
| A | Repo-root resolve + submodule refusal | **EP** | n/a | EF could argue "users could `cd` to the repo manually" — but every downstream step needs the canonical path. Reject: this is plumbing, not a feature. | `handler.py:74-99` |
| B | Symlink-safety gate (R13) | **EP** (defensive) | n/a | CO ("users could read docs about adversarial symlinks") — but the gate is silent and free; its job is to prevent a real attack class. | `scaffold.py:207-267` |
| C | Malformed-settings pre-flight (R14) | **EF** | host-scope `allowWrite` registration (action H) | EP: "settings.local.json corruption affects all Claude Code workflows" — but the gate's *purpose* is to bail before action H mutates settings. If H were dropped, C would be dead code. | `settings_merge.py:422-446` |
| D | Decline gates (R6 marker, R19 content) | **EP** | n/a | CO ("users could just rm cortex/ and retry") — but R19 prevents catastrophic overwrite of a foreign repo's pre-existing `cortex/` contents. Reject: foreign-repo protection is product-essential safety. | `scaffold.py:162-204` |
| E1 | `cortex/lifecycle.config.md` template | **EP** | n/a | EF ("only lifecycle uses it") — but lifecycle IS the core product, and 6+ skills read this config including the overnight critical-tier path. | `skills/lifecycle/SKILL.md:41`, `skills/critical-review/SKILL.md:38`, `skills/morning-review/references/walkthrough.md:88,108,144,187,607-609`, `skills/lifecycle/references/{complete,plan,specify,implement,post-refine-commit}.md`, `cortex_command/lifecycle_config.py:22`, `cortex_command/overnight/cli_handler.py:58` |
| E2 | `cortex/requirements/project.md` template | **CO** | n/a (path is EP, body is CO) | EF: "lifecycle's requirements-loader reads it." The path IS load-bearing; but the *template body* is a TODO stub the user must edit. Could be created on demand by `/cortex-core:requirements` when the user actually opts into the requirements system. | `skills/lifecycle/references/load-requirements.md:9,13`; `skills/requirements-write/SKILL.md:16`; template body at `cortex_command/init/templates/cortex/requirements/project.md:1-48` is 100% `TODO` placeholders |
| E3 | `cortex/backlog/README.md` template | **CO** | n/a | EF ("backlog tooling needs it") — `grep -rn "backlog/README"` returns only test fixtures. No runtime reader. The directory creation itself is what matters for `cortex-generate-backlog-index`, not the README. | `grep` returns `NOT_FOUND` for any non-test reader in skills/, hooks/, cortex_command/, plugins/ |
| E4 | `cortex/lifecycle/README.md` template | **CO** | n/a | EF ("lifecycle skill needs it") — same `NOT_FOUND` outside test fixtures. The `test -d cortex/lifecycle` precondition needs the *directory*, not the README. | `skills/lifecycle/SKILL.md:15` precondition checks dir existence only |
| E5 | `claude_md_authorization.md` template | **EF** | EnterWorktree auto-enter in lifecycle implement phase | EP: "the lifecycle skill requires it." But the lifecycle skill's `references/implement.md:193` *explicitly defines* a fallback path: when `--verify-worktree-auth` returns non-zero, fall back to `cd $(cortex-worktree-resolve …)`. The feature is the auto-enter affordance, not the lifecycle itself. | `scaffold.py:624-634` reads template; `skills/lifecycle/references/implement.md:173,193` consumes — explicit cd-shim fallback |
| F1 | `.gitignore` += `cortex/.cortex-init` | **EF** | `--ensure` hash-drift detection (the marker itself, not the gitignore) | EP: "the marker is product-critical." The marker IS critical for `--ensure`. The gitignore *entry* is convenience: the user may want to commit the marker (and many will, by accident). Without the ignore, the marker shows up in `git status` — annoying, not broken. | `scaffold.py:71-72`; marker consumed at `handler.py:166-167,467`; no consumer requires it to be gitignored |
| F2 | `.gitignore` += `cortex/.cortex-init-backup/` | **EF** | `--force` backup behavior (action H side effect) | EP: "backup directories should never be committed." Steel-man holds if the user runs `--force`. Most users never will (the only `--force` path is overwriting a marked repo). For users who never run `--force`, the entry is dead config. | `scaffold.py:73`; created by `backup_existing` at `scaffold.py:368-412`, only via `--force` at `handler.py:478-482, 493-496` |
| F3 | `.gitignore` += `.claude/worktrees/` | **EF** | Interactive worktree auto-entry (lifecycle picker option 2) AND `Agent(isolation: "worktree")` sub-agent dispatch | EP: "any cortex workflow uses worktrees." The `Agent(isolation: "worktree")` is used by lifecycle implement Step 2 dispatch, which is core. But trunk-mode (picker option 1) skips interactive worktrees; sub-agent worktrees ARE created at `.claude/worktrees/{task}/` even in trunk mode. Without this gitignore entry, sub-agent worktree filesystems get committed to git. **This one survives the steel-man — EP for any user who runs implement at all.** Reclassify F3 to **EP**. | `scaffold.py:74`; `skills/lifecycle/references/implement.md:195`, `skills/overnight/SKILL.md:133`, `cortex_command/pipeline/worktree.py:5-11` |
| G | CLAUDE.md fence splice | **EF** | EnterWorktree auto-enter | EP: "every interactive session needs it." No — lifecycle's `references/implement.md:193` defines a `cd`-shim fallback when verify-worktree-auth fails. The fence only enables the auto-enter path; the cd-shim path is the documented, supported fallback. | `handler.py:514`, `scaffold.py:678-757`; consumer is `--verify-worktree-auth` at `handler.py:416-436` called from `implement.md:173` |
| H | settings.local.json allowWrite registration | **EF** | Interactive lifecycle write-through (writing under `cortex/lifecycle/{slug}/` from Claude Code sessions) | EP: "lifecycle is the core feature." Steel-man: any user running `/cortex-core:lifecycle` from inside Claude Code (the dominant entry point per `skills/lifecycle/SKILL.md`) will hit a sandbox prompt on every write to `cortex/lifecycle/{slug}/`. Without the umbrella grant, the lifecycle UX is "approve permission prompt on every artifact write." The overnight runner has its own per-spawn allow-list (`overnight/sandbox_settings.py:75,181-208`) and does NOT depend on H. **For the in-Claude-Code interactive case, the lifecycle feature is unusable without H.** This one survives the steel-man — reclassify to **EP** for the interactive-lifecycle case, EF for overnight-only users. | `settings_merge.py:136-205`; consumer is sandbox enforcement at every cortex/ write site; overnight independence at `overnight/sandbox_settings.py:75` |
| I | Stale "cortex-worktrees" expunge | **CO** | n/a (migration window) | EF: "users with v2.14 installs need cleanup." Steel-man holds for the migration window only. The expunge runs only on `--update` (`handler.py:528-529`), is a substring filter for a now-defunct registration shape, and a stranded entry granting access to a path that no longer exists is harmless. After ~1 minor-version cycle, this is dead code. | `handler.py:522-529`; `settings_merge.py:296-357`; expunge target documented at `handler.py:522-525` |

## Detailed analysis of contested classifications

### F1, F2, F3: the three `.gitignore` entries

The prior audit lumped all three under "load-bearing — `.claude/worktrees/` is non-cosmetic." Disaggregated:

- **F1** (`cortex/.cortex-init`): the marker is product-critical for `--ensure` hash-drift detection. But the gitignore entry is secondary — committing the marker just makes git track it, not break any feature. EF is generous; CO is defensible.
- **F2** (`cortex/.cortex-init-backup/`): only created by `--force` at `scaffold.py:368-412`. Users who never run `--force` never create a backup dir, so the entry is dead. For users who do, committing the backup dir is wasteful but not catastrophic.
- **F3** (`.claude/worktrees/`): the genuine load-bearing one. Both lifecycle's worktree-interactive picker AND `Agent(isolation: "worktree")` sub-agent dispatch in lifecycle implement Step 2 create worktrees here. `Agent(isolation: "worktree")` is the *default* sub-agent dispatch path (`skills/lifecycle/references/parallel-execution.md:12-14`), not opt-in. Without F3, sub-agent worktree filesystems get committed to the main repo — real data corruption. **F3 is EP** for any user who runs lifecycle implement.

### E5 + G + H: the worktree auto-enter triad

Three writes (auth-template, fence splice, settings registration) form a triad supporting `EnterWorktree` auto-enter. The prior audit treated them as load-bearing because the lifecycle skill reads `--verify-worktree-auth` exit code and uses the fence to enable auto-entry.

Steel-man for EP: every user running `/cortex-core:lifecycle implement` will hit the picker at `skills/lifecycle/references/implement.md:16-20`, see "Implement on feature branch with worktree" as one of three options, and a non-trivial fraction will pick it. If the fence is missing, those users get a degraded experience (cd-shim instead of EnterWorktree's cache-clear semantics).

Rejection: the cd-shim fallback IS the documented graceful-degradation path (`implement.md:193`). The lifecycle skill defines exactly what happens when verify-worktree-auth returns non-zero, including a structured stderr diagnostic. **The feature being protected is the auto-enter affordance, not the lifecycle itself.** A user who never picks worktree-interactive (e.g., a trunk-development workflow on a small repo) literally never exercises this code path.

E5+G remain EF (worktree-interactive auto-enter is opt-in). H is contested:

### H: the settings.local.json registration

Two scenarios:

1. **Interactive-in-Claude-Code lifecycle (dominant entry point).** Without H, every Bash write to `cortex/lifecycle/{slug}/research.md`, `spec.md`, `plan.md`, etc. triggers a sandbox prompt. The user can approve "yes, and don't ask again," which writes a permission entry to `.claude/settings.local.json` — but the entry is per-path, so the prompt fires on every new lifecycle slug. **This is the prompt-storm failure mode ADR-0003 was designed to suppress.** For interactive users, H is EP — without it, the lifecycle UX is broken even though "technically" each prompt resolves the issue.

2. **Overnight-only or terminal-cortex-tooling-only users.** `cortex_command/overnight/sandbox_settings.py:75,181-208` constructs per-spawn `--settings` JSON that includes the needed allowWrite paths. The user's `~/.claude/settings.local.json` is NOT load-bearing for overnight. Terminal CLI invocations (`cortex-update-item`, `cortex-generate-backlog-index`) are not sandboxed — they run outside Claude Code.

So H is EP for the interactive case (which the SKILL.md describes as primary) and EF for overnight-only users. Since the user-facing default is interactive, the *worst-case classification that respects the audit's "minimal-config new adopter" framing* is EP. Net: **H is EP**.

### C: the malformed-settings pre-flight

If H is dropped, the pre-flight gate at `settings_merge.py:422-446` becomes dead code — it exists to bail before H mutates settings. Therefore C is properly classified as EF, with H as the dependent feature. If the decision elsewhere is to drop H, C goes with it. If H stays (it should — see above), C is also kept.

### I: the migration expunge

The substring-match expunge for "cortex-worktrees" entries (`handler.py:528-529`) exists because a prior version of cortex registered worktree-base paths in `~/.claude/settings.local.json`. The current architecture (`#260` reverted same-repo worktrees to `.claude/worktrees/` under the project's trust scope) doesn't need those entries. Stale entries grant access to paths that may no longer exist — harmless.

This is CO. The steel-man for EF: "users who used the prior architecture have stale entries; cleanup matters." Holds for the migration window. After ~6 months, this code path is dead. Could be removed in a future release.

## Summary: revised load-bearing picture

Per-category counts after re-audit:

- **EP (Essential-to-Product) — 6 actions + 1 template:** A (repo-root resolve), B (symlink gate), D (decline gates), F3 (`.claude/worktrees/` gitignore), H (allowWrite registration, for interactive case), I think nothing else. E1 (`lifecycle.config.md` template) is the one EP scaffold template. That's 6 actions + 1 template.

- **EF (Essential-to-Feature) — 3 actions + 1 template:** C (malformed-settings pre-flight; depends on H, so technically rides along with EP-H), E5 (auth-template; EnterWorktree auto-enter), F1+F2 (marker + backup gitignore entries; depend on `--ensure`/`--force` features), G (CLAUDE.md fence splice; EnterWorktree auto-enter).

- **CO (Convenience-Only) — 1 action + 2 templates:** I (stale "cortex-worktrees" expunge; migration-window dead code), E3 (`backlog/README.md`; no runtime consumer), E4 (`lifecycle/README.md`; no runtime consumer), E2 (`requirements/project.md`; path is EP-as-target but body is 100% TODO stubs and could be lazy-created).

**The EP set for a minimal-config new adopter doing nothing but `cortex init` then `/cortex-core:lifecycle my-feature` (trunk mode):**

- Resolve repo root + refuse submodule (A).
- Symlink safety on `cortex/` (B).
- R6/R19 decline gates (D).
- `.gitignore` += `.claude/worktrees/` (F3).
- `~/.claude/settings.local.json` += `<repo>/cortex/` allowWrite (H).
- Pre-flight malformed-settings check (C, rides with H).
- The `cortex/lifecycle.config.md` template (E1).
- Plus the `cortex/` directory itself (creating `cortex/lifecycle/`, `cortex/backlog/`, `cortex/requirements/` as directories for skills' `test -d` preconditions).

Everything else — both READMEs, the requirements TODO stub, the auth-template + fence splice, the marker/backup gitignore lines, the migration expunge — is *not* essential to the minimal-config user. It supports `--ensure`, `--force`, EnterWorktree auto-enter, or migration cleanup, all of which are opt-in.

## Implications for discovery scope

The prior research preferred Approach D (declare-preview-confirm + sandbox-clean ensure), keeping all four write surfaces intact and adding install-time consent UX. This re-audit doesn't reject D, but reveals a legitimate intermediate option the prior audit's binary collapse hid:

**A "minimal-init" mode** that writes only the EP set (~6 actions + 1 template + 3 empty directories) would still let a user run `/cortex-core:lifecycle my-feature` on trunk mode without prompt storms. The CLAUDE.md fence and the auth-template would be deferred to *first use of the worktree-interactive picker option* — written then, on demand, by the lifecycle skill itself rather than by `cortex init`. The two README stubs are dropped outright. The requirements TODO stub is lazy-created by `/cortex-core:requirements` on first run.

This is a meaningful narrowing of the user-visible install surface that the prior audit's "load-bearing in 7 of 9 actions" framing made invisible. The discovery's C-vs-D comparison should be reopened with this option:

- **A revised:** Status quo + post-write narration + drop the 2 unused READMEs.
- **B revised:** Same as A revised + declare-preview-confirm at terminal `cortex init`.
- **C revised:** Minimal-init mode (EP-only on first run) + opt-in verb / lazy-creation for EF writes when the dependent feature first fires + terminal preview.
- **D revised:** Approach D as before, but with the EP/EF/CO axis informing which writes the preview enumerates as essential vs. optional.

The C-vs-D tradeoff changes when C is "lazy-create the EF writes when their feature is first used" instead of "user runs a separate verb." Lazy creation respects the principle of least surprise (the write happens at the moment the user opts into the feature) and eliminates the "users skip the verb, feature dies, user thinks tool is broken" risk in C.

## Open questions

1. **Lazy auth-template + fence on first worktree-interactive use.** Feasible if the lifecycle skill is given write authority to splice the CLAUDE.md fence on demand. Open: does invoking `cortex init --ensure-worktree-auth` from inside Claude Code work post-Feb-2026 sandbox lockdown? CLAUDE.md is *not* in the same category as `~/.claude/settings.json` — it's a repo-root file that the user's editor and Claude Code both can write. Probably workable; needs verification.

2. **Lazy `requirements/project.md` creation.** If `/cortex-core:requirements` lazy-creates the file with the TODO template on first invocation, the install surface drops. Open: any consumer that reads `requirements/project.md` *before* the user has invoked `/cortex-core:requirements`? `skills/lifecycle/references/load-requirements.md:9` reads it but treats absence as "record as `(skipped: file absent)`" — graceful. So yes, lazy creation works for this template.

3. **Empirical fraction of users picking worktree-interactive.** The EP-vs-EF distinction for E5+G hinges on whether worktree-interactive is "default and most users pick it" vs. "advanced option a minority use." `NOT_FOUND` — no usage telemetry surfaced in the codebase. If 90% of users pick it, the EP steel-man strengthens; if 10% do, EF is correct. Needs user-facing data.

4. **F1/F2 gitignore entries dead in practice?** F1 protects the marker; F2 protects the backup dir. Worth confirming via `grep` of consumer repos whether the marker is *ever* committed (which would suggest F1 is doing work) and how often `--force` is invoked (which would suggest F2 is doing work). `NOT_FOUND` for this repo.

5. **C survives if H is dropped?** If a future minimal-init mode drops H entirely, C becomes dead code. Worth noting in the spec phase: keep C only as long as H is alive.

6. **Migration expunge sunset.** I (cortex-worktrees expunge) has a finite useful life. Open: should there be an explicit version threshold (e.g., "remove after v2.18") rather than carrying it indefinitely? `NOT_FOUND` — no sunset marker in the code.
