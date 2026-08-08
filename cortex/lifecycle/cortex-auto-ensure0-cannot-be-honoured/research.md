# Research: Reconcile the R11 attached-worktree refusal with the `CORTEX_AUTO_ENSURE=0` opt-out so lifecycle entry and the test suite work inside a worktree

Scope anchor (Clarify's clarified intent): make `cortex-lifecycle-init-ensure`'s R11 refusal stop blocking legitimate work inside a git worktree while keeping the F9 data-loss protection intact, and make the gate ordering agree with the `cortex init --ensure` mirror it declares itself to be. Symptoms 1 (lifecycle entry blocked) and 2 (19 test failures) are in scope; symptom 3 (`cortex-load-requirements` reporting the primary checkout) is not — see Non-Requirements guidance in Open Questions.

Tier `moderate`, criticality `high`. Angles: Codebase, Requirements & Constraints, Adversarial.

## Codebase

### The probe sites

Two independent copies of the same check:

- `cortex_command/lifecycle/init_ensure.py:29-84` (`_check_not_attached_worktree`) — guards the skill-helper entry point, called at `init_ensure.py:115` before `handler.main` is reached.
- `cortex_command/init/handler.py:243-291` — guards the `cortex init --ensure` CLI surface, called at `handler.py:150`.

Both shell out to `git rev-parse --is-inside-work-tree` / `--git-common-dir` / `--git-dir` with **no `cwd=`** (`init_ensure.py:36-57`, `handler.py:254-267`), so both read the process's ambient CWD, never the repo `--ensure` would write to. No third copy exists in `cortex_command/pipeline/` or `cortex_command/overnight/`.

`handler._resolve_repo_root(args.path)` (`handler.py:44-90`, `git rev-parse --show-toplevel` with `cwd=path_arg or os.getcwd()`) runs only at `handler.py:157` — *after* the probe. It is read-only and raises a caught `ScaffoldError`, so nothing prevents it running earlier.

### Order of writes in `enter` — the guard fires after the damage

`cortex_command/lifecycle/enter.py` calls `create_index(feature, backlog_file, root)` at `:321` and `sync(...)` at `:322`, and only then `init_ensure.main([])` at `:330`. `root` comes from `_resolve_user_project_root()` (`enter.py:402`), which returns the **worktree** root from a worktree CWD (`cortex_command/interactive_lock.py:152-155`). So on the blocked path the session has already written `cortex/lifecycle/{feature}/index.md` into the worktree and mutated the backlog item; the guard's only net effect is to withhold `.session` (`enter.py:333`), leaving a half-applied phase.

### The overnight path reaches this

`skills/build/references/parallel-execution.md:3-7` runs the whole `/cortex-core:build` skill — including the Step 2 `cortex-lifecycle-enter` — via `Agent(isolation: "worktree")`, so CWD is inside a worktree from the start. `enter.py:330` calls `init_ensure.main([])` unconditionally. The ticket's Edges question ("verify whether it hits this path today or bypasses it") is answered: **it hits it.**

### Blast radius of `blocked`

One external consumer: `skills/build/SKILL.md:40` ("`blocked` → a user-correctable gate refused and `.session` is unwritten; halt, fix, re-run (idempotent)"), mirrored into `plugins/cortex-core/skills/build/SKILL.md`. `enter.py:114` (`KNOWN_STATES`) and `enter.py:335` are the producer. `cortex_command/lifecycle/tests/test_enter.py` monkeypatches `en.init_ensure.main` (`test_enter.py:47`), so it never exercises the probe and is unaffected by any fix here. Other `"blocked"` hits across `skills/` are backlog `blocked-by` dependency semantics, not this state.

### Existing resolvers

`cortex_command/lifecycle/log_resolver.py:76` (`resolve_events_log`) builds on `resolve_main_repo_root()` (`log_resolver.py:59-73`), an alias of `cortex_command/interactive_lock.py:149`. Algorithm: honor `CORTEX_REPO_ROOT` verbatim; else walk up from `Path.cwd()` for a `.git` **file**, parse its `commondir` pointer to reach the main repo root, guarded by a `cortex/`-existence check; else fall back to `common._resolve_user_project_root()`. This is the resolver `cortex/requirements/lifecycle.md:40` pins for `events.log`.

It is **not** reusable inside the probe: it deliberately redirects a worktree CWD to the main root, which would make the probe never detect the worktree case at all. `cortex_command/pipeline/worktree.py:55-79` (`_main_worktree_root`) already accepts an explicit `repo` parameter and threads it as `cwd=` — the direct precedent for how a probe *would* take a target path, if one survives.

### Test inventory

- `cortex_command/lifecycle/tests/test_init_ensure.py:301` (R11(a)) and `:376` (R11(b)) spawn the helper as a subprocess with explicit `cwd=`, so their process CWD already equals the intended target; both pass today and are unaffected by target-anchoring.
- `cortex_command/init/tests/test_handler_ensure.py` builds `Namespace(path=str(path), ...)` (`:68-77`) and calls in-process, so the ambient-CWD probe is disconnected from the `tmp_path` target. **This is the file that produces 19 failed / 3 passed when pytest is launched from inside a worktree** (22 passed from the primary checkout).
- R11(a)'s `base_env = dict(_os.environ)` (`:316`) never deletes `CORTEX_AUTO_ENSURE`, making it ambient-environment-dependent under an opt-out-first reordering. R11(b) sets the variable at `:402` and its docstring at `:380` relies on the current ordering, so its pass would become vacuous under a reorder. `:194` is the only site that does `monkeypatch.delenv`.

### Mirrors

`plugins/` mirrors only `skills/`, `hooks/`, and `bin/cortex-*`. Neither `init_ensure.py` nor `handler.py` is a mirror source (`.githooks/pre-commit` trigger lists at `:82`, `:107`, `:157`, `:210`, `:237` never name them). Only a `skills/build/SKILL.md` edit would pull in the Phase 3 staged-blob mirror rebuild.

### The diagnostic arithmetic

`worktree_root = git_dir.parent.parent.parent` (`init_ensure.py:77`, `handler.py:305`) walks up from `<main>/.git/worktrees/<name>`, which yields `<main>` **by construction, in every layout** — `--git-dir` in a worktree points into the primary's `.git` and carries no information about where the worktree lives. Live repro printed `invoked inside a git worktree (.../primary); run from the primary worktree (.../primary)` — the same path twice — for a sibling-layout worktree. The only correct sources are `git rev-parse --show-toplevel` or `git worktree list`.

## Requirements & Constraints

### Governing clauses

- **`cortex/requirements/project.md:52`** — "`CORTEX_AUTO_ENSURE=0` opt-out … Silences `cortex init --ensure` (and `cortex-lifecycle-init-ensure`) without disabling manual init verbs. Foreign-content protection for unanticipated misfires is structural (R19 gate) rather than reliant on this opt-out." The parenthetical is **false today** for the helper. This clause is the one requirement the current code contradicts.
- **Worktree containment invariant** (`project.md:57`) — governs `create_worktree`/`resolve_worktree_root` in `cortex_command/pipeline/worktree.py`, i.e. where same-repo worktrees are *created*. It does not govern R11's attached-worktree *detection*. No overlap, no contradiction either way.
- **Install-state shared-constant contract** (`project.md:51`) — pins the install-in-progress marker path only; the R6 lock-check sits after R11 in the dispatch order. Untouched by this work.
- **Enforcement gates carry named evidence** (`project.md:41`) — scoped by its own opening words to "a **pre-commit/CI** gate", and every survivor and retiree it lists is a hook or lint. **It does not reach R11**, a runtime CLI refusal. (Clarify cited this clause and withdrew it.)
- **Deletion bias** (`project.md:23`) — does reach this work: it puts the burden of proof on *keeping* a safeguard, and requires named, specific evidence rather than a hypothetical. This is the clause under which the Adversarial finding below bites.

### Lifecycle constraints

- `cortex/requirements/lifecycle.md:37` — `enter` "stays a dumb arg-actor with every discriminant caller-passed." `cortex-lifecycle-init-ensure` is not a served verb (`lifecycle.md:101` confirms the carve-out "does not reopen ADR-0019 … for other helper verbs"), so this neither mandates nor forbids anything about the probe. It does forbid `enter` growing its own phase-classification logic — which rules out the ticket's candidate 2 ("give `cortex-lifecycle-enter` its own way to proceed when ensure is not required for the phase being entered").
- `lifecycle.md:40` — the "one pinned, worktree-aware resolver" rule is scoped to `events.log` resolution and its flock domain, not repo-root resolution.
- `lifecycle.md:119` — records CWD-anchoring as sanctioned legacy behavior for typed subcommands, contrasted with machine verbs' "main-repo-anchored resolution". Background precedent, not a rule naming `init_ensure.py`.
- `lifecycle.md` Open Questions (`:122-126`) — none name R11, F9, or worktree anchoring. One of them *is* symptom 3's remedy ("whether the review phase's no-area-doc warning should also fire when a listed requirements path is reported absent"), which is why symptom 3 stays out of scope here.

### Origin of R11 and F9 — the decisive documentary finding

F9 was named in `cortex/lifecycle/auto-apply-cortex-init-at-lifecycle/research.md:189`:

> "`git rev-parse --show-toplevel` in a `git worktree add` worktree returns the worktree root, not the primary. **First-init via `--ensure` writes into the feature worktree; worktree removal silently destroys the cortex/ data.** Required mitigation: detect worktree-attached … refuse `--ensure` with a diagnostic pointing to the primary worktree."

`spec.md:44` codifies it and mandates the helper run the check "Before any other check" — so the helper's ordering is **spec text, not drift**. But `plan.md:60` and `review.md:35` specify the CLI mirror's order as opt-out first, worktree-refusal second. The originating spec therefore states two mutually inconsistent orderings for what it calls one mirror relationship, and **no artifact anywhere states a rationale for the difference**. Nothing anywhere requires the detection to read raw process CWD.

`cortex/lifecycle/rescope-cortex-init-ensure-to-never/spec.md:6` item 6 froze R11 explicitly out of that ticket's scope ("behave exactly as today") — deliberately left alone, not re-examined.

### ADRs

ADR-0005 (accepted) governs worktree placement, not detection. ADR-0008 (accepted) establishes that running build phases inside a worktree is the **sanctioned steady-state path**, which is what makes a blanket refusal a live obstacle rather than a dead branch. ADR-0019 is *proposed* (non-binding) and scoped to `--backend` flags. ADR-0006 is superseded.

### Missing area docs

`cortex/requirements/install.md` and `cortex/requirements/tests.md` do not exist, and neither `install` nor `tests` appears as a key in `project.md`'s Conditional Loading map (`:99-109`). Two of the ticket's three declared areas resolve to nothing, which is why Clarify's alignment rating is `partial` rather than `aligned` — a structural absence, not a search failure. `grep -rn R11 cortex/requirements/` returns zero matches.

## Adversarial Review

### F9's data-loss scenario is already unreachable — the guard protects nothing it claims to

`--ensure` can no longer bootstrap `cortex/` from nothing. #273 turned the only branch that did (case (iii)) into a refusal: `handler.py:217-225` raises `ScaffoldError` ("this repo is not yet initialized for cortex (no `cortex/`)…") **before any write**. Every other arm requires pre-existing state — cases (i)/(ii)/(v) require a marker (`handler.py:168`, `:181`), case (iv) requires `cortex/` to already have content (`handler.py:226`). *Verified directly against HEAD.* The exact harm F9 names — "first-init via `--ensure` writes into the feature worktree" — is structurally impossible on the current code path.

Compounding it: `enter` already writes into the worktree before the guard runs (see Codebase, "Order of writes"). *Verified directly against HEAD.* The guard withholds `.session` after the worktree writes it exists to prevent have landed.

### What ensure actually writes in a worktree

Measured in this repo's real attached worktree: the marker `cortex/.cortex-init` is absent (gitignored at `.gitignore:39`, so it never checks out), `cortex/` is fully populated, and all signature templates (`scaffold.py:84-90`) are present — selecting **case (iv), adoption** (`handler.py:226-245`). Missing-template count: 0. Both `_GITIGNORE_TARGETS` are already in `.gitignore:39-40`, so `ensure_gitignore` returns without writing (`scaffold.py:585-587`). **The sole write is `cortex/.cortex-init` via `write_marker(refresh=False)`** (`handler.py:245`) — a gitignored provenance file whose destruction on `git worktree remove` costs nothing, re-derived by the next `--ensure` in the primary checkout.

Two consequences: the ticket's candidate 3 ("narrow the guard to refuse only when ensure would write") does **not** unblock the interactive case, because ensure genuinely writes. And there is no data to lose when it does.

### Main-repo anchoring should not ship

The option Clarify was leaning toward fails four ways:

1. **Inert in the overnight path.** `cortex_command/pipeline/dispatch.py:700` sets `_env["CORTEX_REPO_ROOT"] = str(worktree_path)` for every per-feature dispatch, and `resolve_main_repo_root()` honors it verbatim as branch (a) (`interactive_lock.py:177-179`). *Verified directly against HEAD.* So "anchor to main" resolves **to the worktree** exactly where the parallel-worktree concern lives.
2. **Sandbox-illegal if the pin were removed.** `cortex_command/overnight/sandbox_settings.py:66-73` lists six `OUT_OF_WORKTREE_ALLOW_WRITERS`; the main repo root is not among them, and `:163-171` builds the per-feature allow-list as worktree + integration base + those six.
3. **Fails open to the worktree.** If branch (b)'s `cortex/`-existence guard trips (`interactive_lock.py:186`), it falls through to `_resolve_user_project_root()` (`:198`), which terminates on `.git` as file *or* directory (`common.py:97`) and returns the worktree root.
4. **Crashes on the first-init case F9 was written for.** From an attached worktree of a never-initialized repo, `resolve_main_repo_root()` raises `CortexProjectRootError` (`common.py:52`, a `RuntimeError`), which `handler.main` does not catch (`handler.py:494` catches only `ScaffoldError`/`SettingsMergeError`) — converting today's clean exit-2 into a traceback.

It would also split one verb's writes across two roots: `index.md` into the worktree (`enter.py:321`), the marker into main.

### Landmine in the target-anchoring fix

`git rev-parse --git-common-dir` returns a **relative** path whenever CWD is not the repo root, while `--git-dir` returns absolute. Today this is accidentally safe because the subprocess and the `Path(...).resolve()` at `init_ensure.py:66-67` share the same base. Adding `cwd=repo_root` breaks that invariant while `.resolve()` stays anchored to the process CWD — demonstrated to produce a **false worktree refusal in the primary checkout**, and plausibly not even fixing the 19 tests (bare `.git` from a `tmp_path` root resolves against pytest's CWD). The correct primitive is `git rev-parse --path-format=absolute --git-common-dir --git-dir` (git ≥ 2.31, verified on 2.55). Any surviving probe must use it.

### Recommendation

**Delete `_check_not_attached_worktree()` from `cortex_command/lifecycle/init_ensure.py` and from `_run_ensure`, and let case (iii) be the guard.** Case (iii) already refuses exactly the situation F9 describes, before any write, with a message naming the correct remedy. In an initialized repo the worst a worktree `--ensure` does is write a gitignored marker. One deletion removes: two duplicated probes, the fixed-depth diagnostic bug, the `spec.md:44`-vs-`plan.md:60` ordering inconsistency, the false claim at `project.md:52`, and all 19 test failures — because the probe that reads ambient CWD stops existing. This is the **Deletion bias** answer: R11's named evidence was killed by #273, and a defense retained without named evidence is complexity.

Stated cost: it contradicts spec R11 as written, so it needs an explicit supersede note in `cortex/lifecycle/auto-apply-cortex-init-at-lifecycle/`; `test_init_ensure.py:301` and `:376` get deleted or inverted; and case (iii)'s message should gain the primary-worktree path so a worktree user is still told where to go. The minimum defensible fallback, if a guard is required: refuse only in case (iii) *and* only when attached — i.e. move the probe below the dispatch, where it can see whether a write would create a new `cortex/`.

## Open Questions

- **Does the `handler.py:243-291` CLI-surface probe go too, or only the helper's?** Resolved: both. They are one mechanism duplicated as "intentional structural defense-in-depth" (`handler.py:145-147`), and the justification for the mechanism is what died. Leaving the CLI copy would preserve the 19 test failures, since `test_handler_ensure.py` exercises `handler.main` in-process. Spec must state this explicitly so it is not read as helper-only.
- **Does the ordering question survive the deletion?** Resolved: no. With the helper's probe gone, `CORTEX_AUTO_ENSURE=0` reaches `handler.py:141` on both surfaces and `project.md:52` becomes true as written, with no reordering and no `project.md` amendment. The `spec.md:44`-vs-`plan.md:60` inconsistency dissolves rather than being adjudicated. Spec should still record the supersede.
- **What replaces R11(a)/R11(b) as tests?** Deferred to Spec with a stated direction: the behavior worth pinning is no longer "refuses in a worktree" but "`cortex init --ensure` succeeds from an attached worktree of an initialized repo, and still refuses via case (iii) on an uninitialized one." A regression test that pytest passes from inside a worktree is the executable form of symptom 2.
- **`enter`'s pre-ensure writes leave a half-applied phase** (index written, backlog synced, `.session` absent) on any `blocked`/`ensure-failed` outcome. Deferred: this is a latent ordering bug in `enter` independent of which fix lands here, it survives the deletion (other `ensure_code == 2` paths remain reachable via case (iii) and R19), and folding it in would widen a bug ticket into a state-machine change. File separately.
- **Symptom 3 (`cortex-load-requirements` reporting the primary checkout).** Deferred with rationale: `lifecycle.md:119` documents the worktree/main-repo resolution divergence as intended, and `lifecycle.md`'s own Open Questions already defers the remedy. Belongs to that question, not to this ticket. Record in the spec's Non-Requirements.
