# Review: remove-claude-agent-sdk-dependency (cycle 2)

Scope: the rework range `657cb824..HEAD` (5 commits, HEAD 0bce90a6), plus the files the checklist points to. The cycle-1 review is archived at `review-cycle-1.md`.

Test baseline came from the orchestrator and I did not re-run it. At 0bce90a6, `just test` passed 7 of 8 recipes. The `tests` recipe had 6 failures, 2605 passes and 19 skips. The 6 failures are the same ones already present at 562179bb: 4 in `test_cli_background_install_hook.py` plus the two `.venv`-symlink tests. I confirmed this list in the log.

I also ran these targeted checks:
- `classify_failure` called directly on three inputs.
- An import of `integration_recovery` in the repo venv.
- `sandbox_preflight`, which exited 0.
- Greps for leftover SDK wording and extras wording outside the history trees.

## Prior-Cycle Checklist

1. **Both `install_core.py` rationale docstrings made a false extras claim — resolved.**
   - Both docstrings now say `[all]` is declared empty under ADR-0039, and that the extra name is kept so the version-locked argv stays byte-identical. This matches the ADR's Decision.
   - The diff touches only the docstring lines. The argv return values are unchanged, which keeps R23.
   - None of the three R23 tests is among the baseline failures.

2. **Other surfaces still described the SDK as the live mechanism — resolved for all four named sites.**
   - `sandbox_settings.py`: the module docstring now names `--settings <tempfile>` for both spawn sites, with dispatch going through `claude_stream.build_argv`.
   - `runner.py:110`: now says `--max-budget-usd` on the dispatched `claude`.
   - `dispatch.py` (the resolver comment, now at line 826): now says "PATH, then known install locations". This matches `cli_resolver.py`, which no longer compares versions.
   - `integration_recovery.py`: the `try/except ImportError` guard, the `_DISPATCH_AVAILABLE` flag and the "(SDK not installed)" string are all gone, and `dispatch_task` is now imported directly. The module imports cleanly, and `INTEGRATION_RECOVERY_FAILED` and `sys` are still used elsewhere in the file. The test's `patch.object(..., "_DISPATCH_AVAILABLE", True)` wrapper was dropped. The test still asserts that `dispatch_task` is invoked, so it still checks what it checked before.
   - A sibling comment with the same stale claim remains in `runner.py:1589-1590`, and a doc page repeats the extras claim from item 1. Both are listed under Out-of-Scope Findings. Neither is one of the sites cycle 1 named.

3. **R18: stale dashboard app and extras wording — resolved.**
   - `docs/dashboard.md:23` now reads "The first `cortex dashboard` run adds **Cortex Dashboard** to `~/Applications`". That is accurate:
     - The only non-test caller of `ensure_app()` is the dashboard verb, at `cli.py:543`.
     - `macapp.py:19` says the same.
     - ADR-0039's Trade-off says the app moved behind the first `cortex dashboard` run.
   - The `projects.py` docstring now attributes the stdlib-only constraint to `cortex init` importing the module without the dashboard's dependencies. It no longer mentions a "dashboard extra".

4. **R25: no recorded `--run-slow` pass — resolved.**
   - `live-verification.md` now has an "Opt-in live test (spec R25)" section, dated 2026-09-16, against `claude` 2.1.273 on an authenticated machine.
   - It records two runs: `1 skipped` without the flag, and `1 passed in 4.14s` with it.
   - That covers both halves of R25's acceptance.

5. **Recommendation: the corpus rate-limit phrase check ran before the keyword checks — resolved.**
   - The phrase scan moved out of step 4. It now runs after the timeout, test, refusal and confused scans, and before the `--effort` hard-reject check.
   - Step 4 keeps only the structured signals: `api_error_status == 429` and a non-`allowed*` rate-limit frame.
   - I checked the results directly:
     - `"I cannot proceed, rate limit concerns."` with no result frame → `agent_refusal`. At 657cb824 this input returned `api_rate_limit`, because the phrase check ran first. So the new test `test_rate_limit_phrase_in_assistant_text_yields_to_earlier_keywords` is not vacuous.
     - `"429 Too Many Requests"` with no other keyword → `api_rate_limit`. The phrase fallback still works.
     - A structured 429 on the result frame, even with a refusal keyword → `api_rate_limit`.
   - The docstring's step list matches the new order.
   - The phrase-only path is still covered by `tests/test_dispatch.py:78` and `:95`, and both pass in the baseline.

## Requirement ratings

| Req | Rating | Evidence |
|---|---|---|
| R1–R9, R11–R17, R19, R20, R22, R26 | PASS | Carried forward from cycle 1. These ratings hold while `claude_stream.py`, `cli_resolver.py`, `pyproject.toml`/`uv.lock` and the CI workflow are unchanged, and none of them is in the rework range. For R12 in particular, `_SESSION_HALT_ERROR_TYPES` and the runner's halt path are also untouched. |
| R10 taxonomy preserved | PASS | Re-verified because `classify_failure` changed. Every `ERROR_RECOVERY` key is still reachable, and the `test_dispatch_spawn.py` set-equality and per-key retry tests pass in the baseline. The reorder only moves the phrase-only `api_rate_limit` path to after the keyword scans. |
| R18 dead guards gone, no app at init | PASS | Re-rated. See checklist item 3. |
| R21 SDK surfaces corrected | PARTIAL | Re-rated. All five cycle-1 sites are fixed, and both acceptance greps stayed empty (the rework adds no "agent sdk" or "SDK exception" text). Two surfaces of the same kind remain; see Out-of-Scope Findings. |
| R23 install argv unchanged | PASS | Re-verified because both `install_core.py` files were touched. Only docstring lines changed, and the three named tests pass in the baseline. |
| R24 sandbox gate re-pointed | PASS | Re-verified because `sandbox_settings.py` (a watched file) was edited. `preflight.md` was re-recorded with `pass: true` at `commit_hash` 43fb88ba, the parent of the commit that edited the watched file. That is the same shape cycle 1 accepted. `uv run python3 -m cortex_command.sandbox_preflight` exits 0 at HEAD. |
| R25 opt-in live test | PASS | Re-rated. See checklist item 4. |

## Out-of-Scope Findings

1. **`cortex_command/overnight/runner.py:1589-1590` still describes the removed resolver and the SDK.** The orchestrator-spawn comment reads:

   ```
   # #313: spawn the resolved best-available CLI (newer of system-vs-bundled)
   # so the orchestrator and SDK workers run an identical claude; ...
   ```

   Both claims are now false:
   - 5e50c91a dropped the SDK-bundled branch, so there is no system-vs-bundled comparison.
   - There are no SDK workers.

   This is the same stale claim the rework fixed in `dispatch.py`. R21 requires correcting every surface that describes the SDK as the live mechanism, so R21 stays PARTIAL.

   A related point to consider while editing that comment:
   - The comment's own `or "claude"` falls back to the bare name.
   - The `cli_resolver.py` docstring says a `None` makes "the caller fail loudly rather than silently falling back to a bare `"claude"`".
   - So the comment should at least not contradict the resolver's contract. The behavior predates this lifecycle.

2. **`docs/internals/auto-update.md:88` repeats the false extras claim from checklist item 1.** It says "the `[all]` extra keeps the dashboard + overnight stacks that live behind optional extras". Under ADR-0039 those extras are empty. `docs/setup.md:78` and `CLAUDE.md` already give the corrected wording, so this page now contradicts both.

I found nothing else. The rework introduced no regressions I could see:
- The `integration_recovery` import is now unconditional, and the module imports without an import cycle.
- The classifier change narrows session halts and does not widen them.
- The baseline failures are unchanged.

## Stage 2: Code quality (rework only)

- **Pattern consistency**: the `integration_recovery` change removes a dead branch and does not replace it with anything, in line with deletion bias. The test simplification follows from that.
- **Error handling**: the classifier order is now structured signals first, then keyword scans, then the phrase fallback. The docstring explains why.
- **Verification recorded**: the R25 run is recorded, and the preflight re-record states its reason in `preflight.md`'s scope section.
- **Carried from cycle 1, still open, non-blocking**: the `cli_resolver.py` docstring says the path is "memoized … once found", but the code also memoizes `None`. The rework did not touch this. It was a docstring note in cycle 1, not a checklist item.

## Requirements Drift

**State**: none

**Findings**: None. Cycle 1's two drift lines are now in `cortex/requirements/multi-agent.md:65` and `cortex/requirements/pipeline.md:151`, and they match the implementation. The rework's only behavior change is the classifier reorder. It changes which failures classify as `api_rate_limit`, but the requirements only specify what `api_rate_limit` does (pause the session), not how it is detected.

**Update needed**: None

## Verdict

```json
{"verdict": "CHANGES_REQUESTED", "cycle": 2, "issues": ["R21 PARTIAL: cortex_command/overnight/runner.py:1589-1590 orchestrator-spawn comment still says the resolver picks the 'newer of system-vs-bundled' CLI 'so the orchestrator and SDK workers run an identical claude' — both false since 5e50c91a (same stale claim the rework fixed in dispatch.py)", "R21 PARTIAL: docs/internals/auto-update.md:88 still says 'the [all] extra keeps the dashboard + overnight stacks that live behind optional extras' — the same false claim fixed in both install_core.py docstrings; the extras are empty under ADR-0039"], "requirements_drift": "none"}
```
