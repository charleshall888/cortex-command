# Research: Fix claude/pipeline/worktree.py::create_worktree — orphan-branch atomicity + stderr surfacing

## Codebase Analysis

### Files that will change

- `/Users/charlie.hall/Workspaces/cortex-command/claude/pipeline/worktree.py` — specifically `create_worktree` (lines 65–164). The single `subprocess.run(..., check=True)` call at **lines 142–148** runs `git worktree add -b` and is the only call the ticket requires wrapping. Two other `check=True` calls exist in the module (lines 31, 104, 274) but are outside `create_worktree` and outside ticket scope per events.log dismissal of finding #2.
- `/Users/charlie.hall/Workspaces/cortex-command/tests/test_worktree.py` — the existing unit test file for `create_worktree` (currently only three `.venv` symlink tests at lines 61–105). Failure-path tests belong here.

### Callers (behavior unchanged; contracts verified)

- `claude/overnight/daytime_pipeline.py:287` — `worktree_info = create_worktree(feature)` at top of `run_daytime`, **outside** the `try/except Exception` at lines 307–320. A raised exception propagates out of `run_daytime` entirely; `asyncio.run(run_daytime(...))` at `_run` (line 369) lets the exception reach the interpreter, producing the traceback captured in `daytime.log`. This is why `lifecycle/suppress-internal-narration-in-lifecycle-specify-phase/daytime.log:34` shows `CalledProcessError: … returned non-zero exit status 128.` with zero git stderr: `CalledProcessError.__str__` excludes `stderr` by default.
- `claude/overnight/orchestrator.py:162` — called in the feature loop, no try/except. An exception aborts the whole batch.
- `claude/overnight/smoke_test.py:250` — inside `_run_smoke_test`'s outer try/except.
- Sibling pattern (adversarial found this, agents 1/4 missed): `claude/overnight/plan.py:381, 472` catches `subprocess.CalledProcessError` from sibling worktree-creation subprocess calls. `claude/pipeline/merge.py:349` documents `CalledProcessError` as part of related raise contracts. Module-level pattern is "raise `CalledProcessError` or `RuntimeError`-from-it."

### Exception-enrichment precedent (in-repo)

Same-function direct precedent: `claude/pipeline/conflict.py:119–128` runs `git worktree add -b` itself, drops `check=True`, checks `result.returncode != 0`, raises `ValueError(f"worktree_creation_failed: {add_result.stderr.strip()}")`. Other examples in `conflict.py:584, 607, 632` and `merge.py:251, 270` follow the same pattern: `{token}: {stderr.strip()}`.

No `raise ... from e` pattern exists anywhere in `claude/pipeline/`. The established style is capture-without-`check=True` + manual returncode check + raise with f-string.

### Cleanup primitives already in worktree.py

- `cleanup_worktree(feature, repo_path=None, worktree_path=None)` (line 167) — `git worktree remove` (with `--force` fallback), `git worktree prune`, `git branch -d <branch>`. **Hardcodes `branch = f"pipeline/{feature}"` (line 213); cannot clean up `-2`/`-N`-suffixed branches** — separate issue flagged in `lifecycle/integrate-autonomous-worktree-option-into-lifecycle-pre-flight/research.md:86`. Not directly reusable from the error path because the orphan-branch name is the `_resolve_branch_name`-resolved name, which may include a suffix.
- `cleanup_stale_lock` (line 223) — removes `.git/worktrees/{feature}/index.lock` with `lsof` check. Not applicable.
- `list_worktrees` (line 259) — read-only.

### Branch-delete flag: `-d` vs `-D`

`cleanup_worktree` uses `-d` (safe) at line 216. For an orphan just created by a failed `git worktree add -b`, the branch has zero commits beyond `base_branch`, so `-d` would succeed. **But** `-D` is safer for this cleanup: if the failure left the branch pointing somewhere unexpected, `-d` would refuse and leave the orphan. Nearby code uses `-D` for provenance-known cleanup: `hooks/cortex-cleanup-session.sh:55`, `claude/overnight/runner.sh:1335/1357`. Operator-facing guidance also recommends `-D`: `skills/overnight/SKILL.md:403`, `skills/lifecycle/SKILL.md:404`.

### Test patterns

- `tests/test_worktree.py:61–105` — real `tempfile.TemporaryDirectory` + `_init_git_repo()` helper + `patch("claude.pipeline.worktree._repo_root", return_value=tmppath)`. No subprocess mocking.
- `claude/pipeline/tests/test_trivial_conflict.py:63–68, 184–195` — `_make_subprocess_result()` returns MagicMock with `.returncode`, `.stderr`, `.stdout`; `side_effect` list drives sequential calls for partial-success simulation.
- `claude/pipeline/tests/test_merge_recovery.py:26–31` — `_make_proc()` helper returning `CompletedProcess`.
- For `CalledProcessError` simulation: stdlib pattern is `subprocess.CalledProcessError(returncode=128, cmd=[…], stderr="fatal: …")` as a `side_effect`.

**Real-git trigger available**: pre-existing non-worktree directory at `worktree_path` deterministically makes `git worktree add` fail with "fatal: `<path>` already exists" — adversarial flagged this as a viable real-git test trigger, contradicting Agent 4's claim that monkey-patching was unavoidable.

### Daytime.log mechanics

`daytime.log` is the redirected stdout/stderr of `python3 -m claude.overnight.daytime_pipeline --feature {slug}` (launched by `skills/lifecycle/references/implement.md:133`). There is no structured logger writing to it; uncaught exception tracebacks land there as stderr. Enriching the exception message (or using `add_note` — notes render in tracebacks) is what causes stderr to appear in `daytime.log`.

### Conventions to follow

- Exception-surfacing: match `conflict.py:127`'s f-string style — `{token}: {stderr.strip()}`. Exception chain via `from exc` adds structural info at minor cost (no in-module precedent).
- Cleanup inside the except block: best-effort, mirror `cleanup_worktree`'s style — `capture_output=True`, no `check=True`, swallow errors rather than shadow the original.
- No hook, logger, or schema change. Narrow fix inside one function + tests.

## Web Research

### `git worktree add -b` is not atomic

Official git-scm docs (https://git-scm.com/docs/git-worktree) are silent on atomicity guarantees and exit codes on partial failure. Real-world reports confirm: when `git worktree add -b` fails after creating the branch, git does **not** roll back the branch. Cleanup is the caller's responsibility.

### Reference implementation: opencode PR #14649

https://github.com/anomalyco/opencode/pull/14649 — "fix: clean up orphaned worktrees on bootstrap failure." Tears down four artifacts in order: (1) worktree directory (fs remove with retry), (2) `git worktree remove --force`, (3) `git worktree prune`, (4) `git branch -D`. Key design notes:
- Cleanup is **best-effort**: each step catches its own errors so partial cleanup failure doesn't mask the original bootstrap error.
- Helper invoked from **every failure path**.
- Worktree path captured into a local variable before async boundaries.

### `CalledProcessError` stderr surfacing

cpython issue #130261 (https://github.com/python/cpython/issues/130261) confirms: by default `str(CalledProcessError)` shows only command + exit code — stderr is captured into `.stderr` but never rendered in the default traceback or `__str__`. This is exactly the ticket's pain point.

Three idiomatic patterns:

1. **Custom-wrapper re-raise** (dominant in sampled wrappers):
   ```python
   except subprocess.CalledProcessError as e:
       raise RuntimeError(
           f"git … failed (exit {e.returncode})\nstderr: {(e.stderr or '').strip()}"
       ) from e
   ```
2. **`stderr=subprocess.STDOUT`**: simpler but conflates streams; doesn't solve the logged-exception problem.
3. **`e.add_note()` (Python 3.11+, PEP 678, https://peps.python.org/pep-0678/)**:
   ```python
   except subprocess.CalledProcessError as e:
       if e.stderr:
           e.add_note(f"stderr: {e.stderr.strip()}")
       raise
   ```
   Notes appear in the standard traceback immediately after the exception message. Adversarial review corrected Agent 2's framing: Agent 2 claimed "notes don't appear in `str(exc)`" rules `add_note` out — but the failure surface for this ticket is the uncaught-exception **traceback** in `daytime.log`, and `traceback.TracebackException.format` renders notes (cpython #89839). `add_note` IS viable here and has the advantage of preserving exception type identity.

### Alternatives to try/except cleanup

| Approach | Atomicity guarantee | Simplicity | Handles stderr surfacing |
|---|---|---|---|
| (A) try/except + `git branch -D` cleanup | Same as today; cleanup on failure only | High — minimal diff | Orthogonal — handled in same except block |
| (B) Decoupled `git branch` then `git worktree add` (no `-b`) | Slightly tighter per-step semantics but branch cleanup still required | Medium — 2 subprocesses | Same |
| (C) `git worktree add --detach` then `git checkout -b` inside worktree | Trades orphan branch for orphan worktree dir | Medium/low — novel idiom | Same |
| (D) `contextlib.ExitStack` + `pop_all()` rollback | Explicit commit-on-success; LIFO multi-resource cleanup | Medium — requires literacy; no precedent in `claude/pipeline/` | Same |

**Sources**:
- [git-worktree documentation](https://git-scm.com/docs/git-worktree)
- [opencode PR #14649 — orphaned worktree cleanup](https://github.com/anomalyco/opencode/pull/14649)
- [cpython #130261 — stderr in CalledProcessError.__str__](https://github.com/python/cpython/issues/130261)
- [PEP 678 — Enriching Exceptions with Notes](https://peps.python.org/pep-0678/)
- [Python contextlib.ExitStack](https://docs.python.org/3/library/contextlib.html)
- [subprocess.check_output: Show stdout/stderr on Failure — tutorialpedia.org](https://www.tutorialpedia.org/blog/subprocess-check-output-show-output-on-failure/)

## Requirements & Constraints

### Failure-handling alignment

- `requirements/project.md:29` (Quality Attributes): *"Graceful partial failure: Individual tasks in an autonomous plan may fail. The system should retry, potentially hand off to a fresh agent with clean context, and fail that task gracefully if unresolvable — while completing the rest."*
- `requirements/project.md:15` (Philosophy): *"Failure handling: Surface all failures in the morning report. Keep working on other tasks. Stop only if the failure blocks all remaining work in the session."*
- `requirements/pipeline.md:37`: *"One feature's failure does not block other features in the same round (fail-forward model)."*
- `requirements/pipeline.md:125` (NFR): *"Graceful degradation: Budget exhaustion and rate limits pause the session rather than crashing it."*

### Worktree-specific requirements (direct hit)

`requirements/multi-agent.md:26-36` (Worktree Isolation) is the primary requirements anchor:
- *"Each feature executes in an isolated git worktree."*
- *"Git worktree at `.claude/worktrees/{feature}/` … branch `pipeline/{feature}` (with collision suffix `-2`, `-3` if needed)."*
- *"Worktree creation is idempotent (returns existing valid worktree if already present)."*
- *"Feature branch naming follows `pipeline/{feature}` convention with automatic collision detection."*
- *"Stale index locks (`.git/worktrees/{feature}/index.lock`) are removed if no process holds them."*
- *"Worktree cleanup is idempotent and removes both the worktree directory and the branch after merge."*
- Edge case (`multi-agent.md:86`): *"Worktree already exists at target path: Create handles 'already exists' git error and returns existing path."*
- Edge case (`multi-agent.md:87`): *"Branch collision: `pipeline/{feature}-2`, `-3` suffixes used when the primary name is taken."*

The codebase already models stateful-leftover failure families (`cleanup_stale_lock`); the atomicity fix extends that modeling to orphan branches after failed `worktree add`.

### Atomicity NFR does NOT directly cover this

`requirements/pipeline.md:123` atomicity NFR is scoped to session state file writes ("tempfile + `os.replace()`") — not git subprocess side effects. Word-match is reaching; don't cite as primary requirements alignment.

### Architectural constraints invoked

- `claude/rules/sandbox-behaviors.md:26-31`: git subprocess calls bypass the Seatbelt sandbox. The stderr surfaced IS real git stderr (not sandbox-rejection text).
- `requirements/multi-agent.md:70-75`: parallelism decisions are made by the overnight orchestrator, not individual agents. Tier-based concurrency (1–3 workers) is a hard limit.
- `requirements/project.md:25`: file-based state; no database or server.

### Scope boundaries

No requirement explicitly bounds what pipeline worktree code does vs. doesn't do beyond the `multi-agent.md:26-36` functional criteria. The ticket's "Out of scope" list (no `_resolve_branch_name` changes, no `implement.md` pre-flight changes, no root-cause diagnosis for lifecycle 69) is self-imposed and consistent with requirements.

## Tradeoffs & Alternatives

### Approach A — try/except with explicit cleanup (ticket's suggestion)

**Sketch** (replaces `claude/pipeline/worktree.py:142–148`):

```python
try:
    subprocess.run(
        ["git", "worktree", "add", str(worktree_path), "-b", branch, base_branch],
        capture_output=True, text=True, check=True, cwd=str(repo),
    )
except subprocess.CalledProcessError as exc:
    # git worktree add -b creates the branch before checkout; clean up the orphan
    if _branch_exists(branch, repo):
        subprocess.run(
            ["git", "branch", "-D", branch],
            capture_output=True, text=True, cwd=str(repo),
        )
    stderr = (exc.stderr or "").strip() or "(no stderr)"
    raise RuntimeError(
        f"git worktree add failed for {feature} on base {base_branch} "
        f"(exit {exc.returncode}): {stderr}"
    ) from exc
```

- **LOC**: ~15 lines. Single call site touched.
- **Test complexity**: Real-git trigger is available (pre-existing non-worktree dir at `worktree_path` → fatal: already exists). Monkey-patching is a fallback, not a requirement.
- **Alignment**: Matches `claude/pipeline/conflict.py:119–128`'s sibling pattern in style (differs only in keeping `check=True` + except vs. dropping `check=True` + returncode inspection).

**Pros**: Minimum change, obvious intent, one-file. Matches ticket wording. Memory `feedback_minimal_fixes.md` alignment.

**Cons**: Changes exception type `CalledProcessError → RuntimeError` (adversarial flagged as potential caller-compat break for callers catching `CalledProcessError` specifically; sibling code at `claude/overnight/plan.py:381,472` does this). Adversarial also flagged that `git worktree remove --force` in the except block (not in the sketch above, but in Agent 4's original assembly) may touch paths the call didn't create — dropped from the recommended assembly.

### Approach B — decoupled create-branch-then-add-worktree

`git branch <branch> <base>` then `git worktree add <path> <branch>`. Doubles subprocess round-trips on the happy path. Doesn't eliminate cleanup need — only relocates it. Adversarial and Agent 4 both rejected; scope creep against "Out of scope."

### Approach C — `--detach` then `git checkout -b`

Trades orphan branch for orphan worktree dir; net complexity gain without net correctness gain. Downstream code expects `WorktreeInfo.branch` to be set on return; `--detach` requires a read-back or equivalent plumbing.

### Approach D — `contextlib.ExitStack` + `pop_all()`

No precedent in `claude/pipeline/`. Over-engineered for single call site with two cleanup steps. Memory `feedback_minimal_fixes.md` steers against "redundant safety layers."

### stderr-surfacing options

| Option | Preserves exception type | Renders in daytime.log traceback | In-repo precedent |
|---|---|---|---|
| `raise RuntimeError(...) from exc` | No | Yes (as the raised exception message) | None in `claude/pipeline/` (common elsewhere) |
| Drop `check=True`, raise `ValueError(f"token: {stderr}")` (conflict.py style) | No | Yes (as the raised exception message) | Yes — `conflict.py:119-128` |
| `exc.add_note(f"stderr: {stderr}"); raise` (PEP 678, 3.11+) | **Yes** | Yes (rendered by `traceback.TracebackException.format` via cpython #89839) | None in-repo |
| Custom `WorktreeCreateError(CalledProcessError)` | Subclass | Yes | None in-repo; YAGNI |

Adversarial corrected a key Agent 2 assertion: `add_note` IS viable for this ticket because `daytime.log` captures tracebacks (not `str(exc)`), and tracebacks render notes.

### Recommended approach

**Approach A structurally, with the following spec-phase decisions flagged for user resolution**:

1. Exception type: `CalledProcessError` preserved (via `add_note`) vs. `RuntimeError from exc` vs. `ValueError` (conflict.py style).
2. Whether to include `git worktree remove --force` in the except block for partial-worktree-dir cleanup.
3. Whether cleanup-failure should be surfaced in the re-raised exception (second note) or silently swallowed.
4. Branch-delete flag: `-d` vs `-D`.

## Adversarial Review

### Failure modes (concerns that must be resolved or explicitly accepted in Spec)

1. **Provenance of the deleted branch is NOT provable.** Agent 1's claim that `_resolve_branch_name` makes the cleanup "provably the one this call just created" assumes single-writer. Concurrent callers racing on suffix climbing could both resolve to `pipeline/{feature}-2` and the loser's except block could delete the winner's branch.
2. **`_resolve_branch_name` is TOCTOU**. No lock, no atomic check-and-create. The ticket scopes `_resolve_branch_name` changes out — so the fix cannot repair the race, only avoid making it worse.
3. **`git worktree add` "already exists on path" → `_branch_exists` True only if branch pre-existed this call** → cleanup would delete pre-existing orphan. Arguably correct (cleans accumulated state) but contradicts "only delete what this call created" framing. Spec should acknowledge.
4. **`git worktree remove --force` in except block may touch pre-existing paths**. The path may exist from prior user/run state; `--force`-removing it is overreach. Recommend dropping from the assembly unless a specific failure mode requires it.
5. **Exception-type change breaks sibling-module precedent**. `claude/overnight/plan.py:381,472` catches `subprocess.CalledProcessError` from sibling worktree-creation calls. Switching `create_worktree` alone to `RuntimeError` creates subtle inconsistency. `add_note` option preserves type and avoids this.
6. **Best-effort cleanup that silently fails regresses to unbounded-orphan-accumulation** — the very thing the ticket is meant to fix. Spec should either (a) accept and document, (b) add a counter, or (c) surface cleanup failure in the re-raised exception.
7. **Monkey-patched tests don't verify cleanup invariants**. Real-git tests are feasible (pre-existing non-worktree dir triggers real "already exists" failure). Prefer real-git where possible.
8. **stderr log-injection**: git stderr may include absolute paths with usernames, URLs with embedded auth, `.git/` internals. Risk surface is low for this call but spec should scope stderr to exception-message-only — no additional log-file writes or downstream forwarding.
9. **"Existing callers continue to work" is ambiguous**. Weak interpretation: signature unchanged (permits type change). Literal: exception-type preserved. Per `feedback_follow_defined_procedure.md`, spec should commit to an interpretation and carry it forward.
10. **`finally` + sentinel doesn't add value** — branch-create and checkout happen in the same subprocess call, no Python-side boundary to split on. **But** `KeyboardInterrupt` mid-subprocess is not caught by `except CalledProcessError`; handling it adds meaningful scope. Spec should decide: explicitly document "SIGINT during `git worktree add` can leave partial state; operator cleans on next run" OR add reconciliation logic.

### Security notes (low-risk but spec should acknowledge)

- Broad `except Exception` at `daytime_pipeline.py:314` flattens worktree-creation errors with other pipeline bugs. Pre-existing; not in scope; but enriched messages may mislead operators about general diagnosability.
- Best-effort cleanup without counters is a known anti-pattern in production systems; acceptable here only with explicit acknowledgment.

### Corrected assumptions

- "`_resolve_branch_name` picks uniquely" — true only single-writer.
- "No caller discriminates `CalledProcessError`" — true in this repo today, but `plan.py` sibling code does so for similar operations.
- "`add_note` renders only in tracebacks, not `str(exc)`" — correct but irrelevant for this ticket; `daytime.log` captures tracebacks.
- "Monkey-patching is unavoidable" — false; real-git triggers exist.

## Open Questions

The following questions surfaced during research and are best resolved by asking the user during the Spec phase (preference/design decisions, not things to investigate further).

- **Deferred: will be resolved in Spec by asking the user.** Which stderr-surfacing path should the fix take? Options: (a) `exc.add_note(f"git stderr: {...}")` then `raise` — preserves `CalledProcessError` type, minimal change, relies on Python 3.11+ traceback rendering; (b) `raise RuntimeError(...) from exc` — type change but straightforward; (c) drop `check=True` + returncode inspection + `raise ValueError(f"token: {stderr}")` — matches `conflict.py:119-128` in-module precedent but also changes type. The user previously chose "Enrich exception message" (over structured log line) — (a), (b), and (c) all satisfy that choice, so this is a sub-choice.
- **Deferred: will be resolved in Spec by asking the user.** Should the except block also attempt to clean up partial worktree directory state (`git worktree remove --force`)? Adversarial flagged risk of touching pre-existing paths; codebase precedent supports narrow branch-only cleanup.
- **Deferred: will be resolved in Spec by asking the user.** Should cleanup-step failure be surfaced (e.g., second note, or appended to exception message) or silently swallowed?
- **Deferred: will be resolved in Spec by asking the user.** Branch-delete flag: `-d` (safe; what `cleanup_worktree` uses) or `-D` (force; what hook/runner-shell cleanup uses, and what operator-facing docs recommend)?
- **Deferred: will be resolved in Spec by asking the user.** Exception-type stability interpretation of "existing callers continue to work" — weak (signature only) vs. literal (type preserved)?
