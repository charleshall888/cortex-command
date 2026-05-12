# Specification: Lifecycle skill gracefully degrades autonomous-worktree option when runner absent

> Epic context: see `research/overnight-layer-distribution/research.md` (DR-2 establishes that `lifecycle` ships in `cortex-interactive` and degrades when the runner CLI isn't installed). This spec defines the runtime-probe mechanism that makes that split safe.

## Problem Statement

When a user installs only the `cortex-interactive` plugin (without the `cortex_command` CLI tier) and reaches the lifecycle skill's Implement-phase branch-selection menu, the "Implement in autonomous worktree" option dispatches to `python3 -m cortex_command.overnight.daytime_pipeline` — a module that ships with the CLI tier, not the interactive plugin. The result is a `ModuleNotFoundError` traceback the user did not ask for. This spec makes the lifecycle skill detect the missing module at runtime and remove the autonomous-worktree option from the menu, so the interactive-only install path produces a clean two-option menu instead of a crashing three-option one. The probe runs each time the §1 Pre-Flight Check menu is rendered, including on resume to `main`/`master` — accepted scope: a user who picked option 1 ("Implement on current branch") in a prior session, then uninstalled the runner, will see a two-option menu on the next §1 render where they previously saw three. That degradation is the right outcome for an unsupported install state; persisting probe results across sessions is out of scope (it would violate the simplicity bar without preventing any concrete user harm).

## Requirements

> All 10 numbered requirements below are must-have for this scope. There are no should-have items; deferred or out-of-scope items live in `## Non-Requirements`.

1. **Runtime probe runs in `references/implement.md` §1 Pre-Flight Check, immediately before the `AskUserQuestion` call.** Acceptance criteria — observable state: `grep -nE "import importlib\\.util|find_spec\\('cortex_command'\\)" skills/lifecycle/references/implement.md` returns at least one match within §1 (above the `AskUserQuestion` invocation) and zero matches outside §1 in that file.

2. **Probe form is a single Bash call invoking `python3 -c` with an explicit try/except, mapping exit codes to three distinct outcomes** — exit 0: module present; exit 1: module absent; exit 2 (or any other non-zero from `python3` itself): probe failed. The `try/except` ensures that exceptions during `find_spec` (e.g., a corrupt finder, a broken `importlib.util` import on an unusual interpreter) exit with code 2 rather than colliding with the absence-signaling exit 1. Acceptance criteria — observable state: the source file `skills/lifecycle/references/implement.md` contains the literal probe command as documented prose, including the substring `try:` and the substring `sys.exit(2)` within the §1 probe block. Verifiable via:

    ```bash
    awk '/^### 1\\. Pre-Flight Check/,/^### 1a\\./' skills/lifecycle/references/implement.md \
      | grep -F "find_spec('cortex_command')" | wc -l   # ≥ 1
    awk '/^### 1\\. Pre-Flight Check/,/^### 1a\\./' skills/lifecycle/references/implement.md \
      | grep -F "sys.exit(2)" | wc -l                    # ≥ 1
    ```

   Both `wc -l` outputs must be ≥ 1.

3. **Probe target is the top-level `cortex_command` package, not the full `cortex_command.overnight.daytime_pipeline` submodule path.** Acceptance criteria — observable state: `grep -F "find_spec('cortex_command.overnight.daytime_pipeline')" skills/lifecycle/references/implement.md` returns 0 matches; only the top-level form is present. Rationale (informational, not part of the check): probing the top-level package costs ~80ms vs ~476ms for the full submodule import; partial installs are not a supported state, so top-level presence is sufficient.

4. **On probe exit 0 (module present), the menu shows all three options unchanged** — "Implement on current branch (recommended)" / "Implement in autonomous worktree" / "Create feature branch". Acceptance criteria — interactive/session-dependent: verified by manual exercise with the runner installed; this preserves the post-#097 baseline behavior.

5. **On probe exit 1 (module absent — the only exit code that means "module absent"), the "Implement in autonomous worktree" option is removed from the `AskUserQuestion` options array before the call, and no diagnostic is surfaced** (silent hide). Acceptance criteria — observable state: the procedural prose in `skills/lifecycle/references/implement.md` §1 explicitly identifies exit 1 as the absence signal that triggers option removal, and explicitly states that no diagnostic is rendered on exit 1. Verifiable via:

    ```bash
    awk '/^### 1\\. Pre-Flight Check/,/^### 1a\\./' skills/lifecycle/references/implement.md \
      | grep -nE "exit 1.*(remove|omit|hide).*autonomous|autonomous.*(remove|omit|hide).*exit 1" | wc -l   # ≥ 1
    ```

6. **Fail-open on probe error: when the probe exits with any code that is neither 0 nor 1 (i.e., exit 2 from the try/except, exit 127 from the shell when `python3` is not on PATH, or any other non-{0,1} exit), the guard does not fire — the menu shows all three options unchanged, and a single-line diagnostic is surfaced alongside the prompt: `runtime probe skipped: import probe failed`.** Acceptance criteria — observable state: the procedural prose in `implement.md` §1 enumerates the exit-code routing rule (exit 0 → all options; exit 1 → autonomous-worktree removed, no diagnostic; any other exit → fail-open with diagnostic) and contains the literal diagnostic string. Verifiable via two greps:

    ```bash
    awk '/^### 1\\. Pre-Flight Check/,/^### 1a\\./' skills/lifecycle/references/implement.md \
      | grep -F "runtime probe skipped: import probe failed" | wc -l   # ≥ 1
    awk '/^### 1\\. Pre-Flight Check/,/^### 1a\\./' skills/lifecycle/references/implement.md \
      | grep -nE "exit 0.*all|exit 1.*remove|fail-open|fail open" | wc -l   # ≥ 1
    ```

   Both must be ≥ 1. The first verifies the diagnostic literal exists; the second verifies the exit-code routing rule is described in prose so the implementer cannot satisfy R6 by inserting only the diagnostic string while leaving the disambiguation logic implicit.

7. **No telemetry, no nag, no events.log entry per probe.** Acceptance criteria — observable state: the spec'd implementation does not introduce a new event-name. Verified via `grep -rnE "runtime_probe|probe_check|graceful_degrade" cortex_command/ skills/lifecycle/ plugins/cortex-interactive/skills/lifecycle/ --exclude-dir=lifecycle-skill-gracefully-degrades-autonomous-worktree-option-when-runner-absent --exclude="implement.md"` returning 0 matches. The two excluded scopes (this lifecycle directory and `implement.md` itself) are the only places these strings may appear, since `implement.md` documents the probe in procedural prose. The fail-open diagnostic in Requirement 6 is the only user-facing signal; the silent-hide path produces no diagnostic.

8. **Two-option menu degrade respects the `AskUserQuestion` contract** (`minItems: 2` on options). Acceptance criteria — observable state: within `skills/lifecycle/references/implement.md` §1's degrade-path block, exactly the two option labels "Implement on current branch" and "Create feature branch" are enumerated, and "Implement in autonomous worktree" does not appear in that block. Verifiable via two greps over the §1 degrade-path region:

    ```bash
    awk '/^### 1\\. Pre-Flight Check/,/^### 1a\\./' skills/lifecycle/references/implement.md \
      | grep -cE "Implement on current branch|Create feature branch"    # ≥ 2
    awk '/^### 1\\. Pre-Flight Check/,/^### 1a\\./' skills/lifecycle/references/implement.md \
      | grep -E "Implement on current branch.*Create feature branch|Create feature branch.*Implement on current branch" | wc -l   # ≥ 1
    ```

   Both must be satisfied: total label count ≥ 2 in §1, AND at least one line co-locates both labels in the documented degrade path.

9. **Both copies of `implement.md` are updated together: the source `skills/lifecycle/references/implement.md` and the regenerated plugin copy `plugins/cortex-interactive/skills/lifecycle/references/implement.md`.** Acceptance criteria — command + expected output: from a clean working tree after the change, `just build-plugin` exits 0, then a content-equality check between the source and each plugin copy that the build recipe regenerates exits 0:

    ```bash
    just build-plugin
    git diff --no-index --quiet -- skills/lifecycle/references/implement.md \
                                    plugins/cortex-interactive/skills/lifecycle/references/implement.md
    ```

   `git diff --no-index --quiet -- pathA pathB` compares the two files byte-for-byte (exit 0 = identical, exit 1 = different). The earlier `git diff --quiet -- pathA pathB` form was wrong: with two pathspecs and no commit operand, that command compares working tree vs index restricted to those paths and exits 0 whenever both files are clean against the index — including when the source and plugin copy differ from each other. Use `--no-index` to actually compare the two files.

   Authoritative gate (broader than the standalone command above): the four-phase policy-aware drift-enforcement pre-commit hook (introduced in commit `79390c7`, installed via `just setup-githooks`) iterates `BUILD_OUTPUT_PLUGINS` (currently `cortex-interactive` and `cortex-overnight-integration` per `justfile:403`) and refuses commits where any plugin's regenerated tree differs from its staged copy. The standalone command above is the spec's binary check for ticket 123's two specific files; the hook is the durable enforcement net for the whole plugin-tree contract. The two are not equivalent — the hook covers all plugins and runs the rebuild step the standalone command omits — but on this ticket's scope, both must succeed.

10. **The probe does not interfere with the existing uncommitted-changes guard at `implement.md:17`.** Acceptance criteria — command + expected output: the three ordering markers in §1 appear in the prescribed order (uncommitted-changes guard line < runtime-probe line < `AskUserQuestion` *call site* line), captured into named variables and compared with shell arithmetic. The earlier `grep -n | head -3 | sort -c -n` form was tautological (`grep -n` always emits ascending line numbers, so `sort -c -n` cannot fail) and sampled off-target matches (line 11's preamble "prompt the user via AskUserQuestion" and line 17's combined "git status --porcelain ... AskUserQuestion call" both polluted the head). Use anchored greps scoped to the §1 region instead:

    ```bash
    SECTION=$(awk '/^### 1\\. Pre-Flight Check/,/^### 1a\\./' skills/lifecycle/references/implement.md)
    GUARD=$(echo "$SECTION" | grep -nF "git status --porcelain" | head -1 | cut -d: -f1)
    PROBE=$(echo "$SECTION" | grep -nF "find_spec('cortex_command')" | head -1 | cut -d: -f1)
    # AskUserQuestion call site is the LAST AskUserQuestion mention in §1
    # (the first is in the §1 preamble narrative; the call site comes after both guards):
    ASK=$(echo "$SECTION" | grep -nF "AskUserQuestion" | tail -1 | cut -d: -f1)
    [ -n "$GUARD" ] && [ -n "$PROBE" ] && [ -n "$ASK" ] \
      && [ "$GUARD" -lt "$PROBE" ] && [ "$PROBE" -lt "$ASK" ]
    ```

    Pass: the final `[ ... ]` chain exits 0, meaning all three markers were found in the §1 region and their line numbers are strictly increasing in the prescribed order. Fail: any marker missing, or any pair out of order, exits non-zero. The uncommitted-changes guard's mutation of "Implement on current branch" (demote-in-place: prepend warning, strip `(recommended)`) and the runtime probe's mutation of "Implement in autonomous worktree" (remove from options) compose cleanly without one undoing the other; both checks complete before the `AskUserQuestion` call.

## Non-Requirements

- **No re-probing inside a single render path.** The probe runs once per §1 Pre-Flight Check entry; if the probe were re-run later in §1a or elsewhere within the same render, that would be redundant — the §1 result is the authoritative signal. (See "No defensive probe at `§1a` entry" below.) This is distinct from "no persistence across sessions" — the probe re-runs every time §1 renders, which is the right behavior; an uninstall between sessions is reflected on the next render.
- **No persistence of probe results across sessions.** Each §1 render runs a fresh probe; no probe outcome is cached to disk or in events.log. Consequence: a user who picked option 1 in session A, then uninstalled the runner, then resumes in session B with the menu re-rendering on `main`, will see two options where they previously saw three. This is the documented and accepted runtime behavior — see Edge Cases below.
- **No `cortex --version` PATH check.** The §1a Daytime Dispatch path invokes `python3 -m cortex_command.overnight.daytime_pipeline` directly — it never shells out to the `cortex` binary, so a PATH check would be a redundant second subprocess. One probe (the Python import) is the answer.
- **No telemetry.** No `runtime_probe` event, no metrics, no log line per probe (only the fail-open diagnostic in Requirement 6).
- **No upgrade hint.** No "install cortex-overnight-integration to unlock autonomous worktree" message in the menu, in the diagnostic, or anywhere else. The plugin description owns user education about the upgrade path.
- **No probing of sibling skills' runner dependencies.** `critical-review`, `morning-review`, and any other skill with `cortex_command.*` imports are out of scope — handled by ticket 120's codebase-import-graph audit.
- **No probe in worker subprocesses.** The overnight runner's worker dispatch does not invoke the lifecycle skill (workers' `_ALLOWED_TOOLS` excludes Agent/Task), so no defensive probe is added for worker contexts.
- **No automated test for the probe's runtime behavior.** No prior art exists in `tests/` for testing markdown skills' conditional behavior. Verification is manual: install state-toggling (with/without `cortex_command` importable) and observation of the menu. A skill-runtime test framework is a separate concern (not 123).
- **No defensive probe at `§1a` entry.** §1a is reachable only via the §1 menu, where the probe just ran; the §1 probe's result is fresh by definition. A second probe at §1a entry would re-run the same check immediately and add no protection.

## Edge Cases

- **Resume in implement phase after uninstalling the runner.** A user starts a lifecycle on `main`, picks option 1 ("Implement on current branch (recommended)"), commits land on main, the session ends, and later the user uninstalls the runner. On resume (`/cortex:lifecycle <slug>`), the user is **still on `main`** — option 1 is the trunk-based path that intentionally keeps the user there — so `implement.md:24`'s branch-name gate does not skip the menu, the §1 prompt re-renders, the probe runs, and the autonomous-worktree option silently disappears from a menu the user previously saw with three options. **Expected behavior**: this is acceptable degradation. The alternative — persisting probe results across sessions and suppressing the option that previously appeared — would require a new on-disk state surface and violates the simplicity bar without preventing any concrete user harm. The user's recovery path (if surprised) is to reinstall `cortex-overnight-integration` + the CLI tier; the option will reappear on the next §1 render. (For users who picked option 3 ("Create feature branch") instead, the resume path lands on the feature branch — `implement.md:24`'s gate fires and the menu is skipped entirely; no probe, no surprise.)
- **`python3` shadowing.** User has a system `python3` that lacks `cortex_command` and a separate `uv tool`-installed Python that has it. The probe runs against system `python3`, `find_spec` returns None, exit 1 is produced — option silently hidden per Requirement 5. Expected behavior: silent hide. This is an accepted false-negative; the user's recovery path is to alias `python3` to the uv-tool Python or install `cortex_command` in their system Python. The fail-open path (Requirement 6) does **not** apply here because the probe completed cleanly with the absence-signaling exit 1, not with a probe-broken exit code (2 or 127). The spec accepts this trade-off rather than building stderr-content heuristics that would never be fully reliable.
- **No `python3` on PATH at all.** The Bash call returns exit 127 (command-not-found) from the shell. Per Requirement 6's exit-code routing rule, exit 127 is neither 0 nor 1 → fail-open: all three options shown, diagnostic surfaced. The user's recovery path is to install Python 3.
- **Probe interpreter raises before reaching `find_spec`.** If `import importlib.util` itself fails, or any other top-level statement in the probe raises, the `try/except` in Requirement 2's probe form catches it and exits with code 2. Per Requirement 6, exit 2 is neither 0 nor 1 → fail-open. This is the structural mitigation that prevents exit 1 from colliding with "module absent."
- **`cortex_command` partially installed.** Hypothetical: the package is on disk but its `__init__.py` raises during import. `find_spec("cortex_command")` does **not** execute the target module's body — it locates the module and returns its spec without running its top-level code. So a broken `cortex_command/__init__.py` still reports present (probe exits 0). The dispatch at §1a would then fail at import time, surfacing a real error. Expected behavior: this is treated as the user's broken install, not the skill's responsibility to mask. (Unsupported state.)
- **Two-option menu boundary.** `AskUserQuestion` requires `minItems: 2` on options. Degrade leaves two options ("Implement on current branch" / "Create feature branch"). In bounds — Requirement 8.
- **Probe ordering vs uncommitted-changes guard.** Both run before `AskUserQuestion`. Probe runs after the uncommitted-changes guard (Requirement 10) — the guard's mutation of "Implement on current branch" (demote-in-place: prepend warning, strip `(recommended)`) is preserved on the degrade path; a user with uncommitted changes sees the warning prefix on a two-option menu.

## Changes to Existing Behavior

- **MODIFIED**: `skills/lifecycle/references/implement.md` §1 Pre-Flight Check gains a runtime probe step between the existing uncommitted-changes guard and the `AskUserQuestion` call. The exact ordering becomes: (1) uncommitted-changes guard (demote-in-place if `git status --porcelain` produces output), (2) runtime probe (`python3 -c` with try/except, mapping module-present → exit 0 → all options; module-absent → exit 1 → autonomous-worktree removed, no diagnostic; any other exit → fail-open with diagnostic), (3) `AskUserQuestion` with the resulting options array.
- **MODIFIED**: `plugins/cortex-interactive/skills/lifecycle/references/implement.md` mirrors the source file change after `just build-plugin`.
- **ADDED**: A new failure mode for the Pre-Flight Check — if the probe exits with any code that is neither 0 nor 1, a one-line diagnostic `runtime probe skipped: import probe failed` is surfaced alongside the prompt and all three menu options remain available (fail-open).
- **ADDED**: A new visible behavior on resume to `main`/`master` after a runner uninstall — a user who previously saw three options now sees two without warning. Documented in Edge Cases as acceptable degradation; called out here so anyone reading the changelog of behavior changes does not miss it.

No changes to: `SKILL.md`, the `§1a` Daytime Dispatch path, the `§2`–`§4` Task Dispatch / Rework / Transition sections, `events.log` schema, or any other reference file in the lifecycle skill.

## Technical Constraints

- The probe is a model-dispatched Bash call (the markdown skill describes the action; the model executes it via the Bash tool). This matches the existing uncommitted-changes guard's execution model.
- Probe target: top-level `cortex_command` package via `importlib.util.find_spec` — chosen for a measured ~80ms cost vs ~476ms for the full `cortex_command.overnight.daytime_pipeline` import. Cost is paid once per implement-phase invocation.
- Probe form: a single `python3 -c` call with an explicit `try/except` that maps three exit codes:

    ```python
    import sys
    try:
        import importlib.util
        sys.exit(0 if importlib.util.find_spec('cortex_command') is not None else 1)
    except Exception:
        sys.exit(2)
    ```

  The `try/except` is the load-bearing structural choice — it is what prevents an uncaught exception inside `find_spec` (or during `import importlib.util`) from colliding with the absence-signaling exit 1. With the `try/except`, the only path to exit 1 is the explicit "spec is None" branch; everything else lands in exit 2 (or, for shell-level failures like missing `python3`, exit 127). The implementer must preserve this `try/except` shape — collapsing it to `sys.exit(0 if find_spec(...) else 1)` re-introduces the exit-1 ambiguity called out in critical review.

- Exit-code routing contract: exit 0 → module present → all three options; exit 1 → module absent → autonomous-worktree removed, no diagnostic (silent hide); any other exit (2, 127, or other) → probe failed → all three options + diagnostic `runtime probe skipped: import probe failed` (fail-open). The model implementing this skill reads the exit code from the Bash tool's result and branches accordingly. No stdout/stderr inspection is required.
- Drift enforcement: the four-phase policy-aware drift-enforcement pre-commit hook from commit `79390c7` regenerates the plugin tree from source via `just build-plugin` and refuses commits where the staged plugin copy diverges. Spec workflow: edit source, run `just build-plugin`, stage both files, commit. The standalone equality check in Requirement 9 (`git diff --no-index --quiet`) is the spec's local binary acceptance check; the hook is the durable enforcement net across all `BUILD_OUTPUT_PLUGINS`.
- Fail-open semantics match the uncommitted-changes guard's precedent (`implement.md:17` documents `git status --porcelain` failure handling identically): an errored guard does not fire; a one-line diagnostic accompanies the prompt; the pre-flight continues normally. The new exit-code routing contract is a strictly more granular version of that same shape — exit 0 / exit 1 are the success paths (module-present and module-absent respectively), and any other exit is the fail-open path.
- The probe affects the interactive Claude Code context only. Overnight-runner workers do not invoke the lifecycle skill (worker `_ALLOWED_TOOLS` excludes Agent/Task) — no probe runs in worker subprocesses, and no spec'd behavior changes on that path.

## Open Decisions

None. All design questions surfaced in research and critical review were resolved with inline answers in `research.md` §Open Questions and in this spec's Requirements / Technical Constraints. The critical review's six fix-invalidating objections are addressed: Requirement 9 uses `git diff --no-index --quiet` for true content equality; Requirement 10 uses anchored named-variable arithmetic comparison instead of the tautological `sort -c -n`; Requirements 5/6 differentiate exit codes 0/1/other through an explicit `try/except`-based probe form; the resume-on-main path is documented as accepted runtime behavior in Problem Statement, Edge Cases, and Changes to Existing Behavior rather than dismissed via a misreading of `implement.md:24`.
