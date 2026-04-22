# Research: Route Python-layer backlog writes through worktree checkout

## Epic Reference

This ticket is scoped from [research/orchestrator-worktree-escape/research.md](../../research/orchestrator-worktree-escape/research.md) — epic 126, which catalogs the broader class of overnight-runner bugs where operations meant for the per-session worktree execute against the home repo and local `main` instead. This ticket covers ONLY the Python-layer backlog-write component of that epic; sibling tickets cover orchestrator prompt disambiguation, a git pre-commit hook, morning-report commit un-silence, and PR-creation gating (each as an independent fix with its own mechanism).

## Codebase Analysis

### The two mutation-site contexts

**`create_followup_backlog_items()` at `claude/overnight/report.py:272-360`**
- Signature: `(data: ReportData, backlog_dir: Path = Path("backlog"))`
- Writes new backlog items via `atomic_write(backlog_dir / filename, content)` at line 350
- Hardcodes `session_id: null` for every new item at line 345
- Callers: `report.py:1435` (nominal: `generate_and_write_report()`), `report.py:1525` (CLI main), and `runner.sh:507-521` (SIGINT/SIGTERM trap)
- All callers use the default `Path("backlog")` — no worktree path is threaded in

**`session_id` frontmatter mutations — actual site is NOT `backlog.py:321,365`**
The ticket cites `backlog.py:321,365`, but those are **parse/read** operations. The real mutation chain is:
- `claude/overnight/outcome_router.py:382-427` — `_write_back_to_backlog()` is the dispatch site; called 18 times from within outcome_router (lines 489, 516, 543, 575, 596, 647, 674, 692, 712, 731, 859, 902, 919, 973, 1049, 1068, 1095)
- The `_OVERNIGHT_TO_BACKLOG` mapping at lines 327–347 assigns the sentinel `_CURRENT_` to `session_id`, which is replaced at line 409 by `os.environ.get("LIFECYCLE_SESSION_ID", "manual")`
- The actual file mutation happens in `backlog/update_item.py:377` via `atomic_write(item_path, text)`

### Complete audit of Python-layer backlog-write sites

| File:Line | Function | Write call | Path resolution | Currently writes to |
|-----------|----------|------------|-----------------|----------------------|
| `report.py:350` | `create_followup_backlog_items()` | `atomic_write(backlog_dir / filename, ...)` | `backlog_dir` argument, default `Path("backlog")` (cwd-relative) | Whatever cwd is at call time |
| `update_item.py:377` | `update_item()` | `atomic_write(item_path, text)` | `item_path` is absolute, produced by `_find_item()` which searches `BACKLOG_DIR` | Wherever `_find_item` resolves |
| `update_item.py:251` | `_remove_uuid_from_blocked_by()` (cascade) | `atomic_write(p, updated)` per blocker | Glob `BACKLOG_DIR / "*.md"` | `BACKLOG_DIR` (import-time-bound) |
| `update_item.py:328` | `_check_and_close_parent()` (cascade) | `atomic_write(parent_path, parent_text)` | Lookup by UUID/ID in `BACKLOG_DIR` | `BACKLOG_DIR` (import-time-bound) |
| `create_item.py:132` | `create_item()` | `atomic_write(item_path, ...)` | `BACKLOG_DIR / filename` where `BACKLOG_DIR = Path.cwd() / "backlog"` | cwd at import time |
| `generate_index.py:235` | Index regeneration | `atomic_write(BACKLOG_DIR / "index.json", ...)` | `Path.cwd() / "backlog"` at module import | cwd at spawn time |
| `generate_index.py:236` | Index regeneration | `atomic_write(BACKLOG_DIR / "index.md", ...)` | Same | Same |

The audit surfaces TWO distinct cwd-dependent global bindings: `outcome_router._backlog_dir` (mutable, set by `set_backlog_dir`) and `update_item.BACKLOG_DIR` (immutable, bound at `update_item.py:38` at IMPORT time). They must stay in sync for the primary write and cascade writes to target the same tree — but the cascade global is not resettable, so any drift at import time persists for the process's lifetime.

### The orchestrator bug at `orchestrator.py:143`

`orchestrator.py:137-143` does:
```python
overnight_state = load_state(config.overnight_state_path)
integration_branches = overnight_state.integration_branches
...
if integration_branches:
    set_backlog_dir(Path(next(iter(integration_branches))) / "backlog")
```

Per `plan.py:394`, `integration_branches` is a dict `{repo_path → branch_name}`, and for a home-repo session the first key is `project_root` (the home repo). So `set_backlog_dir` is explicitly pointed at `{home_repo}/backlog`, not at the worktree. This is a latent bug in the current runtime: `_write_back_to_backlog` calls resolve `item_path` via `_find_backlog_item_path` that searches the HOME repo — the mutation then writes the home-repo file, and the worktree's copy of the file is updated only by the post-loop cp at `runner.sh:986` (which overwrites whatever was there).

The correct source for the worktree path is the scalar `state.worktree_path` (`state.py:244`), which is always populated for any session (home-repo or cross-repo). The dict `integration_worktrees` (`state.py:246`) is only populated for cross-repo sessions.

### Runner ordering and the artifact-commit window

`runner.sh` relevant ordering:
- **line 243-247**: `WORKTREE_PATH` resolved from `state.worktree_path` (shell variable, not exported to Python)
- **line 526**: `trap cleanup SIGINT SIGTERM SIGHUP` installed
- **line 595**: `cd "$WORKTREE_PATH"` — cwd is now worktree for subsequent commands
- **line 635**: `export LIFECYCLE_SESSION_ID="$SESSION_ID"`
- **(round loop executes; outcome_router calls fire per feature transition)**
- **line 986**: `cp -r "$REPO_ROOT/backlog/"* "$WORKTREE_PATH/backlog/"` — POST-LOOP mirror (not pre-loop)
- **line 1001-1014**: subshell runs `git add backlog/` and commits — captures state AS OF this moment
- **line 1207**: `generate_and_write_report()` is called — this is where `create_followup_backlog_items()` runs
- **line 1221-1226**: subshell `( cd "$REPO_ROOT" ... )` for the morning-report commit on main

Key consequence: **`create_followup_backlog_items()` writes land AFTER the artifact commit at line 1001-1014.** Routing those writes into the worktree (even correctly) is necessary but not sufficient — they will still not be captured by the integration-branch commit unless the commit is re-ordered, a second commit is added, or the function runs before line 1001.

The SIGINT trap at line 507-521 fires with cwd = caller's cwd (before line 595 has run). At trap time the worktree DOES exist on disk (created by `plan.py:bootstrap_session` before `runner.sh` starts), but Python's `Path("backlog")` resolves to the home-repo backlog because cwd hasn't been changed yet. `LIFECYCLE_SESSION_ID` is only exported at line 635 — so if the trap fires before the round loop even starts, the env var is unset.

### Integration points and dependencies

- `lifecycle/overnight-state.json` schema (`state.py:186-247`) carries `worktree_path: str` (absolute), `integration_branches: dict[str, str]`, `integration_worktrees: dict[str, str]`, and `project_root: Optional[str]`. The scalar `worktree_path` is the reliable source of truth.
- `atomic_write` at `claude/common.py:382-395` uses `path.parent` as the tempfile dirname; requires parent dir to exist (`create_followup_backlog_items` does `mkdir(parents=True, exist_ok=True)` at `report.py:292`, but cascade writes do not).
- `update_item.py:412` spawns `generate_index.py` as a subprocess — the subprocess's own `Path.cwd() / "backlog"` binding is independent of the parent's `BACKLOG_DIR`.
- `~/.local/bin/update-item` is a symlink to `backlog/update_item.py`; interactive invocations outside the overnight session write to whatever cwd the operator is in.

### Conventions to follow

- Atomic writes via `atomic_write()` helper (tempfile + `os.replace()`) — never write directly.
- Index regeneration is non-fatal: failures are logged but don't abort the mutating call.
- Session identity is passed via the `LIFECYCLE_SESSION_ID` env var for writers; when new items are created, they should carry this session id, not `null`.
- The `OvernightState` dataclass is the single source of truth for per-session paths; code that needs worktree paths should `load_state()` and read `state.worktree_path` rather than reconstructing paths.

## Web Research

### Git worktree + subprocess coordination

The ecosystem's dominant pattern is **explicit function argument** over env-var signaling. Popular multi-agent worktree writeups (Augment Code, Nick Mitchinson, AppxLab) all rely on launching the agent with cwd inside the worktree — none describe env-var-based signaling for this purpose. `git rev-parse --show-toplevel` is the canonical primitive for "which worktree am I in" given a cwd, but it depends on cwd being correct, which the `pre-commit/pre-commit#2295` issue shows can be corrupted by earlier env-var manipulation.

### `GIT_DIR` / `GIT_WORK_TREE` are a documented footgun

- [lefthook#1265](https://github.com/evilmartians/lefthook/issues/1265): git sets `GIT_DIR` when running hooks inside a linked worktree; hook subprocesses inherit it, and `git -C <tempdir> commit` silently mutates the real repo because the inherited `GIT_DIR` wins over `-C`. The reporter called the outcome "devastating."
- [GitPython#2022](https://github.com/gitpython-developers/gitpython/issues/2022): `Repo()` fails inside a worktree when `GIT_DIR` is set; fix is to pass `Repo(os.getcwd())` explicitly or unset `GIT_DIR`.
- Conclusion: env-var signaling is a coordination channel that leaks into every child process by default. Project-specific env vars (e.g., `INTEGRATION_WORKTREE_PATH`) have the same mechanism and should not be preferred over an explicit function argument when the call chain is tractable.

### The worktree+branch is already the rollback primitive

- DVC's `.dvc/tmp/exps/<id>/` pattern: isolate experiment writes to a subtree; discard on failure by deleting the directory. The isolation boundary IS the rollback mechanism — no separate rollback logic required.
- [Claude Code#22945](https://github.com/anthropics/claude-code/issues/22945): cwd was correctly set to the worktree, but a downstream helper still wrote to repo root because it had cached or computed an absolute path. Lesson: cwd isolation is necessary but not sufficient — downstream helpers must derive their write target from a parameter/context, not from a cached constant.

### Key takeaways

1. Prefer explicit function argument over env-var signaling when the call chain is tractable (it is, for the two sites in scope here).
2. The integration worktree IS the discard primitive — if writes land in the worktree and the branch is abandoned, no explicit rollback is needed. BUT see Open Question 3 about whether "abandoned" is automatic.
3. Don't trust "cwd is worktree" as the single safeguard; pass the path explicitly.

(Sources: [git-scm book Environment Variables](https://git-scm.com/book/en/v2/Git-Internals-Environment-Variables), [git-worktree docs](https://git-scm.com/docs/git-worktree), [git-rev-parse docs](https://git-scm.com/docs/git-rev-parse), [DVC Running Experiments](https://doc.dvc.org/user-guide/experiment-management/running-experiments), [Bazel Sandboxing](https://bazel.build/docs/sandboxing).)

## Requirements & Constraints

### From `requirements/pipeline.md`

- **Session Orchestration acceptance criterion** (§Session Orchestration, line 23): "Artifact commits (lifecycle files, backlog status updates, session data) land on the integration branch, not local `main` — they travel with the PR." This is the exact invariant this ticket enforces.
- **Morning-report exception** (line 24): "The morning report commit is the only runner commit that stays on local `main`." Out of scope for this ticket.
- **Integration branch persistence** (architectural, line 133): "Integration branches (`overnight/{session_id}`) are not auto-deleted after session completion. They persist for manual PR creation and review." Relevant to Open Question 3 on the "discarded cleanly on failed branch" premise.
- **Atomicity** (non-functional, line 123; architectural, line 131): All state writes MUST use tempfile + `os.replace()`. This ticket's changes must preserve that discipline.

### From `requirements/multi-agent.md`

- Worktree locations: `.claude/worktrees/{feature}/` (default repo) or `$TMPDIR/overnight-worktrees/{session_id}/{feature}/` (cross-repo). Fix must handle both layouts.

### From `requirements/project.md` and `CLAUDE.md`

- "Complexity must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct." → prefer explicit-argument fix over introducing a new env-var surface.
- Symlink architecture: `~/.local/bin/update-item` is a symlink to the repo's `backlog/update_item.py`. Any change must keep `update-item` usable in interactive contexts.

### Scope boundaries

In scope: routing `create_followup_backlog_items()` and `_write_back_to_backlog()` (plus cascade helpers they trigger) through the active session's worktree checkout so mutations land on the integration branch.

Out of scope (belong to sibling tickets in epic 126 or to standalone work):
- `runner.sh` orchestrator-prompt disambiguation, pre-commit hook, morning-report un-silence, PR-creation gating.
- Modifying the worktree-creation mechanism in `plan.py`.
- Auto-deleting integration branches on session failure (implied by the ticket's "discarded cleanly" framing but not achievable without separate infra — see Open Question 3).

### Invariants to preserve

- Atomic write discipline.
- Worktree-location choice (`.claude/worktrees/` vs `$TMPDIR/...`) is set by `plan.py`; downstream code consumes, not overrides.
- `update-item` binary remains usable in interactive (non-session) contexts — its behavior outside an overnight session must continue to resolve to the user's cwd-relative backlog.
- `session_id` frontmatter semantics: dashboard and morning-report readers correlate items to sessions via this field.

## Tradeoffs & Alternatives

### Approach A — Route Python writes through the worktree path (ticket's prescription)

Thread an explicit worktree-scoped backlog directory through the call chain, rather than relying on cwd. Sub-variants:

- **A1 — Env var from runner**: `runner.sh` exports `OVERNIGHT_WORKTREE_BACKLOG_DIR`; Python reads it. Web research flags env-var leakage as an anti-pattern (lefthook#1265, GitPython#2022); adds a third source-of-truth global alongside the two already present (`outcome_router._backlog_dir`, `update_item.BACKLOG_DIR`).
- **A2 — Function argument**: Pass `backlog_dir` explicitly from `runner.sh` invocation sites to `create_followup_backlog_items()` (already in signature but never used by callers). For outcome_router, fix `orchestrator.py:143` to source from `state.worktree_path` and thread the dir through `_write_back_to_backlog` and its cascade helpers.
- **A3 — `git rev-parse --show-toplevel`**: Brittle; depends on cwd inside worktree. Fails in the SIGINT trap path where cwd hasn't yet been changed.
- **A4 — Session-state lookup**: Python reads `overnight-state.json` to discover `state.worktree_path`. Works wherever `STATE_PATH` env var is exported (already exported from runner).

**A2 recommended for `create_followup_backlog_items()`**: the callers are in `runner.sh` (2 sites) and `report.py` main (1 site); all of them can trivially pass the worktree path. The argument already exists in the signature.

**A2 + A4 hybrid for outcome_router chain**: fix `orchestrator.py:143` to use `state.worktree_path / "backlog"` (A4 mechanism — already loads state in this function), AND replace the import-time `BACKLOG_DIR` global in `update_item.py` with a call-time argument threaded through `_write_back_to_backlog` → `update_item` → cascades (A2 mechanism). The orchestrator already loads `overnight_state` at line 137; routing it correctly is a one-line fix plus cascade plumbing.

### Approach B — Extend or re-order the runner's git-add staging

Agent 4 initially suggested B was "already partly done" via `runner.sh:986`'s cp. Adversarial finding invalidated this: the cp runs AFTER the round loop, not before, and the artifact commit at `runner.sh:1001-1014` happens BEFORE `create_followup_backlog_items()` at `runner.sh:1207` — so followup items are never captured by the integration-branch commit regardless of where they're written. B in isolation does not fix anything new.

HOWEVER, an ordering change IS required even under Approach A: if Python correctly writes followups into the worktree's backlog directory, the artifact commit must be re-ordered (or a second commit block added) to capture them. Otherwise they sit in the worktree's working tree uncommitted, and on worktree cleanup they're lost entirely.

### Approach C — Event-log replay at commit time

Python appends mutations to `lifecycle/sessions/{sid}/backlog-mutations.jsonl`; runner replays against worktree at commit time. Heavy complexity: new log schema, replay module, cascade replay (`_remove_uuid_from_blocked_by`, `_check_and_close_parent`), serialization of `null` vs absent field. Breaks mid-session reads — anything that currently reads `session_id` off frontmatter live during the session sees stale state.

### Approach D — Skip `session_id` writes during session

Rely on `overnight-state.json` as source of truth for session ownership. Dashboard, `/status`, and the "is it my session?" checks all plausibly read `session_id` frontmatter live; removing mid-session writes would break observability silently.

### Approach E — Hybrid (session_id via event log, followups via worktree)

Worst of both worlds: two mechanisms to maintain when one suffices. Rejected.

### Comparison table

| Dimension | A2+A4 | B (re-order only) | C | D | E |
|-----------|-------|--------------------|---|---|---|
| Implementation complexity | Medium | Low | High | Medium | High |
| Correctness coverage (both modes) | Yes | Partial | Yes | No | Yes |
| Lifecycle-phase correctness (incl. SIGINT trap) | Yes | No (trap still writes home-repo) | Yes | Partial | Yes |
| Cwd-independence | Yes | N/A | Yes | N/A | Yes |
| Alignment with existing patterns | High (reuses `OvernightState`) | Medium | Low (new surface) | Low | Low |
| Maintainability | Good (removes drift global) | Keeps drift | New surface | Simplifies if safe | Worst |
| Observability of failure | Explicit fail-loud on missing `worktree_path` | Silent | Mixed | Silent | Mixed |

### Recommended approach

**A2 + A4 hybrid**, plus an ordering fix in `runner.sh` (either re-ordering the artifact-commit block to after `generate_and_write_report`, or adding a second artifact-commit block after it).

Primary changes:
1. Fix `orchestrator.py:143`: source backlog directory from `state.worktree_path`, not `integration_branches`.
2. Replace `update_item.py`'s import-time `BACKLOG_DIR` global with a call-time argument threaded through `update_item()`, `_remove_uuid_from_blocked_by()`, `_check_and_close_parent()`, and the `generate_index.py` subprocess invocation. `outcome_router._write_back_to_backlog` passes the directory at each call.
3. Pass an explicit `backlog_dir` argument to `create_followup_backlog_items()` from both nominal callers (`report.py:1435`, `runner.sh:1207`) and the SIGINT trap caller (`runner.sh:507-521`), resolved from `state.worktree_path`.
4. Fix `report.py:345`: set `session_id` to `os.environ.get("LIFECYCLE_SESSION_ID", "manual")` instead of hardcoded `null`, consistent with existing pattern in `outcome_router.py:409` and `update_item.py:358`.
5. Re-order `runner.sh:1001-1014` (artifact commit) to run after `runner.sh:1207` (report generation), or add a second artifact-commit block after report generation to capture newly-created followup items.
6. For the existing latent fallback at `outcome_router.py:307` (`_PROJECT_ROOT` derived from `__file__` when `_backlog_dir is None`): replace the silent fallback with a fail-loud error (or explicit log event) — state-file corruption currently misdirects writes to the cortex-command repo regardless of project_root.

### Fallback

If cross-repo followup routing proves too complex in this ticket, scope it out and defer per-feature routing to a follow-up ticket. The core `session_id` mutation fix (A2+A4 + ordering) should land first; cross-repo followups may default to the home-repo worktree as a known limitation documented in the spec.

## Adversarial Review

### Verified failure modes

1. **Post-commit write ordering**: `create_followup_backlog_items()` (`runner.sh:1207`) runs AFTER the artifact commit (`runner.sh:1001-1014`). Routing followups to the worktree path alone does not fix the capture problem — the commit must be re-ordered or supplemented. This invalidates the ticket's acceptance-criterion assumption that "writing to a path that the runner's worktree-scoped `git add` at `runner.sh:1002-1008` picks up" is sufficient for followup items.

2. **`integration_worktrees` empty for home-repo sessions**: `plan.py:415-492` only populates `integration_worktrees` for cross-repo items. The universally-populated field is the scalar `state.worktree_path` (`plan.py:504`, `state.py:244`). Any state-lookup mechanism must prefer the scalar.

3. **Cascade drift**: `update_item.py:38` binds `BACKLOG_DIR = Path.cwd() / "backlog"` at MODULE IMPORT time. Primary writes (via absolute `item_path`) can target worktree, but `_remove_uuid_from_blocked_by()` (line 251) and `_check_and_close_parent()` (line 328) cascades use the import-time global. They write to whichever directory was cwd when the module first loaded — which may differ from the call-time primary-write target.

4. **`orchestrator.py:143` is an active misdirection, not a coincidence**: `next(iter(integration_branches))` returns `project_root` (home repo) per `plan.py:394`. `set_backlog_dir(Path(home_repo) / "backlog")` explicitly points outcome_router at home repo. This is a real load-bearing bug, not latent.

5. **State-corruption fallback misdirects**: The try/except at `orchestrator.py:137-156` silently sets `_backlog_dir` to `None` if `load_state` raises. `outcome_router.py:307`'s fallback is `_PROJECT_ROOT / "backlog"` — where `_PROJECT_ROOT` is derived from `__file__`, i.e., the cortex-command repo. For cross-repo sessions, this writes to the WRONG REPO entirely on any state-read error.

6. **`session_id: null` hardcode at `report.py:345`**: Followup items lose session attribution, breaking morning-report and dashboard correlation — even after the worktree-path fix.

7. **"Discarded cleanly on a failed/closed branch" is not automatic**: Integration branches persist per `requirements/pipeline.md:133`. There is no existing cleanup step that deletes them on session failure. The ticket's framing assumes automatic discard which does not exist — it's an operator-driven workflow.

### Claims invalidated or revised

- Agent 1's "pre-round mirror cp at `runner.sh:986`" is wrong: the cp runs after the round loop, inside the post-loop block.
- Agent 4's "runner does `cd "$REPO_ROOT"` at line 1222 before report generation" is wrong: line 1222 is inside a subshell for the morning-report commit, not before report generation. Report generation at line 1207 runs with cwd = worktree. This means `create_followup_backlog_items()` with default `Path("backlog")` currently writes to the worktree's backlog in the NOMINAL path; only the SIGINT trap path is broken.
- Agent 4's A1 recommendation (env-var) contradicts web-research's leakage warnings and adds a third global alongside the two existing drift surfaces. A2 (function argument) is preferred.

### Security / anti-patterns

- Three shared-mutable-state globals (`outcome_router._backlog_dir`, `update_item.BACKLOG_DIR`, and the proposed env var) are a maintenance hazard. The fix should REMOVE globals, not add one.
- Silent fallbacks (`_PROJECT_ROOT` on state-corruption) misdirect writes across repos. Fail-loud is required.

## Open Questions

- **Cross-repo followup routing**: When a cross-repo session generates followups, which repo's worktree should receive them — the home-repo worktree, the specific feature's integration worktree (per-feature routing), or the first cross-repo worktree? The ticket does not specify. Options: (a) per-feature routing via `data.features[slug].repo_path` lookup against `state.integration_worktrees`; (b) home-repo worktree for all followups; (c) defer cross-repo routing to a separate ticket with a documented "home-repo-only" limitation for this ticket. Deferred: will be resolved in Spec by asking the user which option fits the scope.

- **Artifact-commit ordering**: The simplest fix re-orders `runner.sh:1001-1014` to run after `runner.sh:1207` so followups are captured. Alternative: add a second `git add backlog/; git commit` block after line 1207. The re-order changes the commit content (now includes followups); the second-commit approach is additive and easier to roll back. Deferred: will be resolved in Spec by asking the user which fits their rollback preferences.

- **"Discarded on failed branch" premise**: The ticket claims mutations "discard cleanly on a failed/closed branch," but integration branches persist by design (`requirements/pipeline.md:133`). Is the ticket's framing accurate — i.e., is the "discard" referring to the operator's manual branch deletion workflow, or is the ticket implying new auto-cleanup behavior? Auto-cleanup is out of scope per epic 126's decomposition. Deferred: will be resolved in Spec by clarifying whether this ticket's acceptance criteria should reword "discarded cleanly" to "does not pollute local main while the branch remains unmerged."

- **Fail-loud on state-corruption**: Currently, `orchestrator.py:137-156`'s try/except silently falls through to `_PROJECT_ROOT`. Should this ticket add explicit fail-loud behavior (raising an exception, or logging a distinct event and transitioning the session to paused), or is that a separate hardening ticket? Deferred: will be resolved in Spec by scoping decision.

- **`session_id: null` hardcode fix scope**: The hardcode at `report.py:345` is strictly adjacent to the worktree-path fix (same function, different correctness issue). Include in this ticket or split? The decomposition note in the backlog item consolidated followup-persistence and frontmatter-rollback; the `session_id: null` issue is a third related defect in the same function. Deferred: will be resolved in Spec.

- **Update-item binary from interactive contexts**: The `update-item` binary at `~/.local/bin/update-item` must continue to work interactively (cwd-relative to the user's working directory). The fix to remove `update_item.BACKLOG_DIR` import-time global must preserve this: when called with no explicit `backlog_dir` argument, it should still fall back to `Path.cwd() / "backlog"`. Deferred: Spec should state this backward-compat requirement explicitly so implementation doesn't regress it.
