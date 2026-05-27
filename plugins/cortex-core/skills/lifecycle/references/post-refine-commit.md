# Post-Refine Commit

Canonical site for the commit lifecycle authors when `/cortex-core:refine` returns control to `/cortex-core:lifecycle` at the Specify → Plan boundary. Refine §5 explicitly delegates `commit-artifacts` to the caller; this reference is what the caller follows.

## Preconditions

Run only when the most recent significant event in `cortex/lifecycle/{feature}/events.log` is one of:

- `{"event": "phase_transition", "from": "specify", "to": "plan"}` — the approval path. Refine completed, the user approved the spec at the §4 approval surface, lifecycle's Step 3 §4 logged the `spec_approved` and `phase_transition` events, and control returned to lifecycle.
- `{"event": "lifecycle_cancelled"}` — the cancel path. The user selected Cancel at refine's spec-approval surface, refine emitted `lifecycle_cancelled`, and control returned to lifecycle.

**Detection algorithm**: scan `events.log` bottom-up; the first occurrence of either event determines the path. The "since the last commit" qualifier in spec R6 is satisfied by this rule operationally because `events.log` is append-only — a newer occurrence always lands later in the file than an older one, and any older occurrence of the same event has by construction either (a) been included in a prior commit (so it is not stranded), or (b) been left stranded by a failed prior commit (in which case the halt-before-Plan gate below should have prevented re-entry until the operator resolved the stranding). The bottom-up scan therefore picks the most recent occurrence, which is the one the current invocation owns.

## Flag Check

Run `cortex-read-commit-artifacts` to read the `commit-artifacts` flag from `cortex/lifecycle.config.md`. The binstub prints `true` or `false` on stdout.

- stdout `true` (the default, also fires when the file or field is absent): proceed to Staging.
- stdout `false`: skip the commit silently. Do not stage, do not invoke `/cortex-core:commit`. Return control to lifecycle Step 3.

## Staging

Stage the explicit path set below — do **not** use a directory glob (`cortex/lifecycle/{feature}/` would sweep up unrelated residue such as `.session` lock files, `.lock`, `critical-review-residue.json`, and scratch JSONs from sibling skills, none of which belong in the refine commit).

Approval path (most recent event is `phase_transition specify→plan`):

```
git add -- cortex/lifecycle/{feature}/research.md \
            cortex/lifecycle/{feature}/spec.md \
            cortex/lifecycle/{feature}/index.md \
            cortex/lifecycle/{feature}/events.log
```

Plus, when the feature has an originating backlog file (Context A — `cortex-resolve-backlog-item` returned exit 0 at Step 1), also stage that file:

```
git add -- cortex/backlog/{NNN}-{slug}.md
```

Cancel path (most recent event is `lifecycle_cancelled`): identical to the approval path **except** `spec.md` is omitted from staging — spec.md is absent on disk because the user cancelled before refine wrote it.

## No-Op Short-Circuit (Stage-First)

After running the targeted `git add` above, check whether anything was actually staged:

```
git diff --cached --quiet
```

- Exit 0 (nothing staged): nothing changed since the last commit. Exit silently without invoking `/cortex-core:commit`. Return control to lifecycle Step 3 so it auto-advances to Plan. This covers the spec edge case "Resume after a prior approved (and committed) refine" — refine's Step 2 saw both artifacts exist and skipped, no new events were logged, no new artifacts were written, and the targeted `git add` therefore stages nothing.
- Exit 1 (something staged): proceed to Commit.

The stage-first detector replaces an earlier `git status --porcelain -- cortex/lifecycle/{feature}/` form. The earlier form had two failure modes: (a) it fired the short-circuit when an operator committed source files out-of-band but left `events.log` uncommitted, silently orphaning the `phase_transition` row so the next branch commit (Plan) bundled it under a Plan-titled subject (recreating the original defect); (b) it refused to fire when only out-of-set residue (lock files, scratch JSONs) was dirty, producing either an empty commit or a commit failure. The stage-first form aligns the detector with the staging operator — both consult the same path set.

## Commit Subject

Compose the commit subject from the detected path:

- Approval path: `Refine {feature}: research and spec`
- Cancel path: `Refine {feature}: cancelled at spec approval`

The subject selection rule is unambiguous: the orchestrator inspects only the most recent significant event in `events.log` since the most recent commit on the current branch; if that event is `lifecycle_cancelled` the cancel subject fires, otherwise the approval subject fires. The "since the last commit" qualifier prevents historical `lifecycle_cancelled` rows from misclassifying later approval commits in multi-cycle cancel → resume → cancel flows — the bottom-up bottom-most-hit-wins scan operationally satisfies this constraint because the log is append-only.

Invoke `/cortex-core:commit` with the chosen subject and a one-line body summarizing the contents (e.g., `- Research and spec produced by /cortex-core:refine for {feature}`).

## Halt-Before-Plan Gate

If `/cortex-core:commit` exits non-zero (index lock, pre-commit hook rejection, working-tree conflict, etc.), the orchestrator **MUST** surface the error to the operator and HALT. Do not auto-advance to Plan. The stranded `phase_transition` row (or `lifecycle_cancelled` row) remains uncommitted in the working tree until the operator resolves the underlying failure — resolve the conflict, re-run `/cortex-core:commit`, or revert — and re-invokes `/cortex-core:lifecycle`. On re-invocation, lifecycle's resume routing detects the working state and continues from the current phase.

The halt gate is what prevents the failure path from re-creating the original "misnamed bundling" defect. Without the halt, the later `plan.md` §5 commit would sweep up the stranded refine row under a "Plan {feature}" subject, recreating exactly the dysfunction this reference exists to prevent.

## Constraints

- This reference does **not** introduce new event types (no `commit_authored`, `artifacts_committed`, `commit_failed` — see `bin/.events-registry.md`). Commit success is observable via `git log`; commit failure is surfaced by `/cortex-core:commit`'s own error path.
- This reference does **not** add a new `AskUserQuestion` site. The kept-pauses inventory at `skills/lifecycle/SKILL.md` and `tests/test_lifecycle_kept_pauses_parity.py` remain unchanged.
- Resume-and-edit assumption: if an operator manually edits `research.md`, `spec.md`, `index.md`, or the backlog file between session end and re-invocation, those edits will be staged and committed under the Refine subject (which may misdescribe the diff). The canonical workflow is to re-invoke `/cortex-core:lifecycle` (which routes through refine) rather than hand-edit refine artifacts.
