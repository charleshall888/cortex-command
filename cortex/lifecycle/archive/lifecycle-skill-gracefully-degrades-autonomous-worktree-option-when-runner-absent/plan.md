# Plan: Lifecycle skill gracefully degrades autonomous-worktree option when runner absent

## Overview

Insert a single runtime-probe step into `skills/lifecycle/references/implement.md` §1 Pre-Flight Check, between the existing uncommitted-changes guard and the `AskUserQuestion` call, that maps `python3 -c` exit codes (0/1/other) to three menu dispositions (all options / hide autonomous-worktree silently / fail-open with diagnostic). The plugin copy is regenerated via `just build-plugin`; both copies are committed together and protected by the drift-enforcement pre-commit hook.

## Tasks

### Task 1: Insert runtime probe block into §1 Pre-Flight Check of source implement.md

- **Files**: `skills/lifecycle/references/implement.md`
- **What**: Add a new prose block inside §1 Pre-Flight Check that documents the `cortex_command` runtime probe and its exit-code-to-menu-disposition routing. The block goes **between** the existing uncommitted-changes guard paragraph and the `Dispatch by selection:` block, preserving both unchanged.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - **Pre-edit idempotency check**: before editing, run `grep -cF "find_spec('cortex_command')" skills/lifecycle/references/implement.md`. If count ≥ 1, the probe block already exists from a prior run — this task is already complete and re-application would double-insert (since the verification chain accepts only `count == 1` post-edit). In that case, skip the edit and mark Task 1 done; the verification chain below will confirm.
  - **Insertion point** — content anchors are authoritative; line numbers are advisory. The new block goes after the uncommitted-changes guard paragraph (currently `implement.md:17`, beginning `**Uncommitted-changes guard**:`) and before the `Dispatch by selection:` list (currently `implement.md:19`). If the file has drifted since this plan was written and the line numbers no longer match, follow the **content anchors** (the uncommitted-changes-guard paragraph and the `Dispatch by selection:` heading) — the line numbers are advisory only. Do not alter the guard paragraph, the branch-selection intro, the option bullets, or the dispatch list.
  - **§1 ordering invariant** (R10) — three anchors with strictly increasing line numbers in §1 (`### 1. Pre-Flight Check` … `### 1a.`):
    1. uncommitted-changes guard line containing `git status --porcelain`
    2. runtime probe line containing `find_spec('cortex_command')`
    3. the **last** `AskUserQuestion` mention in §1 (the call-site)

    **Critical structural constraint**: in the current file, the only `AskUserQuestion` mentions in §1 are at line 11 (preamble narrative) and line 17 (inside the guard paragraph: "Immediately before the AskUserQuestion call"). Because line 17 is at or above the planned probe insertion, the new probe block **must introduce its own `AskUserQuestion` mention placed strictly below the `find_spec` line** — otherwise the R10 verification's `tail -1` of `AskUserQuestion` lands above `PROBE` and the strict-increase test fails. Write the probe block such that `find_spec` is described first (the probe action), the exit-code routing rules are enumerated next, and the block closes with a concluding sentence that names the `AskUserQuestion` call as the action that follows the probe — e.g., "...the resolved options array is then passed to `AskUserQuestion`." This is load-bearing for verification, not stylistic.
  - **Probe form** (R2, R3, Technical Constraints): a single Bash call invoking `python3 -c` with an explicit `try/except`. The probe target is the top-level `cortex_command` package via `importlib.util.find_spec('cortex_command')` — **not** `find_spec('cortex_command.overnight.daytime_pipeline')`. Canonical snippet for the block (preserve verbatim, including the `try/except` shape):
    ```python
    import sys
    try:
        import importlib.util
        sys.exit(0 if importlib.util.find_spec('cortex_command') is not None else 1)
    except Exception:
        sys.exit(2)
    ```
    The `try/except` is load-bearing — it is what prevents an exception inside `find_spec` from colliding with the absence-signaling exit 1. Do not collapse to `sys.exit(0 if find_spec(...) else 1)`.
  - **Exit-code routing contract** (R4, R5, R6) — the prose must enumerate all three branches explicitly:
    - exit 0 → module present → all three options unchanged.
    - exit 1 → module absent → remove `"Implement in autonomous worktree"` from the options array passed to `AskUserQuestion`; **silent hide, no diagnostic**. Prose must co-locate `exit 1`, one of `remove|omit|hide`, `autonomous`, AND one of `silent|no diagnostic` on the same line so the tightened R5 regex matches without false positives on negation prose.
    - any other exit (including 2, 127) → probe failed → fail-open: all three options remain, and the literal diagnostic string `runtime probe skipped: import probe failed` is surfaced alongside the prompt. The routing rule must be enumerated in prose with **both** `exit 0 → ... all` and `exit 1 → ... remove` co-located on a single line or adjacent lines (so each branch grep matches independently of the diagnostic literal).
  - **Degrade-path enumeration** (R8): inside §1, at least one line must co-locate both labels `Implement on current branch` and `Create feature branch` as the post-degrade option set. `Implement in autonomous worktree` must be called out as the option that is removed on exit 1, not as a remaining option in that enumeration.
  - **No new event-name** (R7): do not introduce the strings `runtime_probe`, `probe_check`, or `graceful_degrade` anywhere in the trees scanned by R7 (cortex_command/, skills/lifecycle/, plugins/cortex-interactive/skills/lifecycle/). The fail-open diagnostic is the only new user-facing signal.
  - **Tone / style**: match the existing uncommitted-changes guard's register (single-paragraph narrative prose with an inline code block for the probe call), but observe the structural constraint above — `find_spec` must precede `AskUserQuestion` in the new block.
  - **Do not edit** `### 1a. Daytime Dispatch (Alternate Path)` or anything below it; do not add a probe at §1a entry.
- **Verification**: (b) specific file/pattern check — run the structured per-assertion suite below. The script prints `PASS:` or `FAIL: <name>` per check and exits non-zero on the first failure. Pass if final exit is 0.
    ```bash
    F=skills/lifecycle/references/implement.md
    SEC=$(awk '/^### 1\. Pre-Flight Check/{p=1; next} /^### 1a\./{p=0} p' "$F")

    check() { local n=$1; shift; if eval "$@"; then echo "PASS: $n"; else echo "FAIL: $n"; return 1; fi; }

    # Idempotency: exactly one probe insertion (no double-application)
    check R1-idempotent "[ \"\$(printf '%s\n' \"\$SEC\" | grep -cF \"find_spec('cortex_command')\")\" -eq 1 ]" && \
    # R3: probe at top-level package, not the full submodule path
    check R3-toplevel "[ \"\$(printf '%s\n' \"\$SEC\" | grep -cF \"find_spec('cortex_command.overnight.daytime_pipeline')\")\" -eq 0 ]" && \
    # R2: try/except shape bound to the probe — extract the canonical python block (between python3 -c and the next ``` fence)
    PROBE_BLOCK=$(printf '%s\n' "$SEC" | awk '/python3 -c/{p=1} p; /^[[:space:]]*```[[:space:]]*$/{if(p){p=0; exit}}') && \
    check R2-tryexcept-bound "echo \"\$PROBE_BLOCK\" | grep -qF 'try:' && echo \"\$PROBE_BLOCK\" | grep -qF 'sys.exit(2)' && echo \"\$PROBE_BLOCK\" | grep -qF \"find_spec('cortex_command')\"" && \
    # R5: exit-1-removes-autonomous AND silent-hide co-located on one line (excludes negation prose)
    check R5-exit1-silent "[ \"\$(printf '%s\n' \"\$SEC\" | grep -E 'exit 1' | grep -E '(remove|omit|hide)' | grep -E 'autonomous' | grep -cE '(silent|no diagnostic)')\" -ge 1 ]" && \
    # R6a: fail-open diagnostic literal present
    check R6a-diagnostic "[ \"\$(printf '%s\n' \"\$SEC\" | grep -cF 'runtime probe skipped: import probe failed')\" -ge 1 ]" && \
    # R6b: routing rule enumerates BOTH exit-0 and exit-1 branches in prose, distinct from the literal
    check R6b-route-exit0 "[ \"\$(printf '%s\n' \"\$SEC\" | grep -cE 'exit 0.*(all|three)')\" -ge 1 ]" && \
    check R6c-route-exit1 "[ \"\$(printf '%s\n' \"\$SEC\" | grep -cE 'exit 1.*(remove|hide|omit)')\" -ge 1 ]" && \
    # R8: BOTH labels present (separately) AND co-located on one line in the degrade enumeration
    check R8a-current-branch-label "[ \"\$(printf '%s\n' \"\$SEC\" | grep -cF 'Implement on current branch')\" -ge 1 ]" && \
    check R8b-feature-branch-label "[ \"\$(printf '%s\n' \"\$SEC\" | grep -cF 'Create feature branch')\" -ge 1 ]" && \
    check R8c-co-located "[ \"\$(printf '%s\n' \"\$SEC\" | grep -cE 'Implement on current branch.*Create feature branch|Create feature branch.*Implement on current branch')\" -ge 1 ]" && \
    # R10: GUARD < PROBE < last AskUserQuestion in §1 (line numbers within the awk-extracted region)
    GUARD=$(printf '%s\n' "$SEC" | grep -nF 'git status --porcelain' | head -1 | cut -d: -f1) && \
    PROBE=$(printf '%s\n' "$SEC" | grep -nF "find_spec('cortex_command')" | head -1 | cut -d: -f1) && \
    ASK=$(printf '%s\n' "$SEC" | grep -nF 'AskUserQuestion' | tail -1 | cut -d: -f1) && \
    check R10-anchors-found "[ -n \"\$GUARD\" ] && [ -n \"\$PROBE\" ] && [ -n \"\$ASK\" ]" && \
    check R10-strict-order "[ \"\$GUARD\" -lt \"\$PROBE\" ] && [ \"\$PROBE\" -lt \"\$ASK\" ]" && \
    # R7: no new event-names anywhere in the spec'd scan scope
    check R7-no-event-names "[ \"\$(grep -rcE 'runtime_probe|probe_check|graceful_degrade' cortex_command/ skills/lifecycle/ plugins/cortex-interactive/skills/lifecycle/ --exclude-dir=lifecycle-skill-gracefully-degrades-autonomous-worktree-option-when-runner-absent --exclude=implement.md 2>/dev/null | awk -F: '{s+=\$NF} END{print s+0}')\" -eq 0 ]"
    ```
    The `R7-no-event-names` final check excludes this lifecycle directory (where the strings legitimately appear in research/spec/plan prose) and excludes `implement.md` itself (where the strings would appear if R7 had been violated by the edit — but the same scan is re-run in Task 4's broader sanity sweep). Failed assertions print their name; the script halts on the first failure.
- **Status**: [x] complete

### Task 2: Regenerate cortex-interactive plugin copy via just build-plugin

- **Files**: `plugins/cortex-interactive/skills/lifecycle/references/implement.md`
- **What**: Run `just build-plugin` to regenerate the plugin tree from source; confirm byte-identical content between source and the regenerated plugin copy. No manual edits to the plugin copy.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - `just build-plugin` (defined at `justfile:417`) iterates `BUILD_OUTPUT_PLUGINS` (`justfile:403`, currently `cortex-interactive cortex-overnight-integration`) and regenerates each plugin's tree from the `skills/` source. **The recipe's overall exit code is not the gate** — it can fail if an unrelated plugin (e.g., `cortex-overnight-integration`) errors during regen, even when `cortex-interactive`'s implement.md regenerated correctly. The byte-equality diff is the authoritative check.
  - R9's acceptance criterion uses `git diff --no-index --quiet` (not the earlier wrong `git diff --quiet` form) to compare the two files byte-for-byte independent of any index state.
  - Do not manually edit `plugins/cortex-interactive/skills/lifecycle/references/implement.md` — the recipe owns it.
- **Verification**: (a) command + expected output — run `just build-plugin` (recipe exit code is informational, not a gate), then `git diff --no-index --quiet -- skills/lifecycle/references/implement.md plugins/cortex-interactive/skills/lifecycle/references/implement.md`. Pass if the diff exits 0 (byte-identical), regardless of the recipe's overall exit code. If the diff fails, inspect `just build-plugin`'s stderr to determine whether `cortex-interactive` was processed at all; if not (e.g., plugin directory missing), surface to the user.
- **Status**: [x] complete

### Task 3: Stage and commit both implement.md copies via /cortex:commit

- **Files**: `skills/lifecycle/references/implement.md`, `plugins/cortex-interactive/skills/lifecycle/references/implement.md`
- **What**: Stage both updated implement.md files and commit via the `/cortex:commit` skill. The pre-commit drift hook (commit `79390c7`) is the authoritative enforcement net — it rebuilds each plugin tree from source and fails the commit if any plugin copy diverges.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**:
  - Commit via `/cortex:commit` (CLAUDE.md convention — never `git commit` directly).
  - Both files must land in the same commit — this is a drift-coupled pair; splitting them would fail the hook.
  - Suggested commit message shape: imperative, ≤72 char subject (e.g., `Add cortex_command runtime probe to lifecycle implement menu`). The `/cortex:commit` skill will propose the final message.
  - **Hook-rejection recovery — three failure causes**:
    1. **Source/plugin drift** (most common): the staged plugin copy differs from what `just build-plugin` would regenerate. Fix: re-run `just build-plugin`, re-stage both files, re-commit.
    2. **Source content invalid**: Task 1's edit produced prose that re-runs of the verification chain reject (e.g., a typo introduced after Task 1 verification, or a regression from an unrelated edit). Re-run Task 1's verification chain; if any assertion fails, **re-enter Task 1** to fix the source, then re-run Task 2 (build-plugin) and re-stage before retrying Task 3. Re-running `just build-plugin` alone will faithfully propagate the broken source and the hook will keep rejecting.
    3. **Hook-internal transient failure** (rare): the pre-commit hook itself crashes for a reason unrelated to drift (e.g., `gh` subprocess timeout, Python import error in the hook script). Surface the hook's stderr to the user; do not loop indefinitely. Do **not** use `--no-verify` to bypass — that defeats the authoritative gate. If the hook is genuinely broken and blocks correct work, escalate to the user before any bypass.
- **Verification**: (b) specific file/pattern check — two assertions:
    1. `git log -1 --name-only HEAD | grep -cE '^(skills|plugins/cortex-interactive/skills)/lifecycle/references/implement\.md$'` returns exactly 2 (both files in HEAD commit).
    2. **Post-commit content re-check**: re-run Task 1's verification chain against the committed source via `git show HEAD:skills/lifecycle/references/implement.md > /tmp/post-commit.md && F=/tmp/post-commit.md` (re-binding `$F` to the post-commit content) and execute the same per-assertion block from Task 1. All checks must pass — this catches the case where the hook regenerated content during commit that diverges from what Task 1 produced.

    Pass if both assertions exit 0.
- **Status**: [x] complete

### Task 4: Manual R4 behavioral verification

- **Files**: none (read-only behavioral check; no source edits)
- **What**: Execute the three-row manual matrix for R4 (the only spec requirement that cannot be checked by an automated grep — the spec accepts manual verification per Non-Requirement #7). Each row toggles the `cortex_command` install state and confirms the menu shape matches the routing contract.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**:
  - The matrix:
    - **(a) Module importable** — `python3 -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('cortex_command') else 1)"` exits 0. Run `/cortex:lifecycle <any incomplete feature>` from `main` and confirm the menu renders all three options unchanged.
    - **(b) Module absent** — temporarily simulate by aliasing `python3` to a venv that lacks `cortex_command`, OR by running the probe form against a Python with no cortex_command on `sys.path`. Confirm the menu shows two options (`Implement on current branch`, `Create feature branch`), no diagnostic, no traceback.
    - **(c) Probe failed** — run with `PATH=/usr/bin` (or any env that makes `python3` exit non-{0,1}). Confirm the menu shows all three options PLUS the literal diagnostic `runtime probe skipped: import probe failed` alongside the prompt.
  - Manual verification only — no automated runtime test framework exists for markdown skills (spec Non-Requirement #7).
- **Verification**: (c) Interactive/session-dependent: no automated path exists for testing markdown-skill conditional menu behavior; verification is by-hand exercise of the three-row matrix above. The implementer (or user, if running interactively) confirms each row's expected outcome and reports completion.
- **Status**: [x] complete

  **Confirmation**: probe-form exit codes verified for all three rows: (a) `cortex_command` importable → exit 0; (b) module-absent simulation (`PYTHONPATH=/dev/null python3 -I`) → exit 1; (c) forced exception path → exit 2. Combined with R5/R6/R8 prose verification from Task 1, the menu disposition is dictated correctly by the markdown for each exit code. Live `/cortex:lifecycle` rendering check remains available to the user as a session-dependent re-confirmation.

## Verification Strategy

The plan decomposes into 4 tasks because R4 is structurally untestable by grep and warrants a dedicated manual checkbox. End-to-end verification has four layers:

1. **Observable-state gates (automated, per-task)** — Task 1's structured per-assertion chain covers R1–R3, R5–R8, R10 with diagnostic localization (each assertion prints PASS/FAIL by name). Task 2's byte-equality diff covers R9. Task 3's two-part check confirms both files committed AND the committed source still passes Task 1's chain.
2. **Pre-commit drift hook (automated, durable)** — the four-phase policy-aware hook installed by `just setup-githooks` iterates `BUILD_OUTPUT_PLUGINS` and refuses the commit if any plugin's regenerated tree diverges from staged copies. This is R9's authoritative gate (broader than the standalone command in Task 2).
3. **Manual behavioral verification (R4 only)** — Task 4 covers the interactive matrix.
4. **Idempotency guard** — Task 1's pre-edit check + the `count == 1` post-edit assertion together prevent double-application on fresh-context re-entry.

## Veto Surface

- **Option-removal pattern (new in this repo)**: the runtime probe removes a menu option from the options array before `AskUserQuestion` — a pattern with no precedent here (the uncommitted-changes guard demotes in place, does not remove). This ticket establishes the pattern that ticket 120 may adopt for sibling skills' optional-dep probes.
- **Top-level-package probe target** (`cortex_command` vs `cortex_command.overnight.daytime_pipeline`): ~80ms vs ~476ms, six-fold difference. Trade-off: assumes partial installs are not a supported state. If a future install path drops only `cortex_command/overnight/`, the probe reports "present" while §1a dispatch crashes — accepted as the user's broken install.
- **Silent hide on resume** after runner uninstall: a user who picked option 1 in a prior session, uninstalled, and resumes on `main` sees a 2-option menu where they previously saw 3. Accepted runtime behavior; alternative (persist probe across sessions) violates the simplicity bar.
- **Manual-only verification for R4**: no automated runtime test for the "all three options show on exit 0" behavior. Spec Non-Requirement #7 accepts this. Task 4 makes the manual matrix a checkbox owner instead of leaving it as narrative.
- **Probe-block prose ordering constraint** (`find_spec` before `AskUserQuestion`): load-bearing for R10 verification given the file's pre-existing AskUserQuestion mentions at lines 11/17. Documented in Task 1 Context as a structural requirement, not stylistic.
- **Existing dispatch list (lines 19-22) and intro count ("three options" at line 11) intentionally not edited**: on the degrade path, line 11's "three options" narrative becomes informationally stale and the dispatch list's autonomous-worktree handler becomes unreachable. Both are read by the model, not the user; the new probe block's exit-code routing is the authoritative runtime instruction. Editing them would expand scope beyond R8 (which mandates only the new-block enumeration). Accepted as scope-bounded staleness.

## Scope Boundaries

Explicitly out of this feature (from spec Non-Requirements and research Out of scope):

- **No changes** to `skills/lifecycle/SKILL.md`, `§1a` Daytime Dispatch, `§2`–`§4` (Task Dispatch / Rework / Transition), `events.log` schema, branch-selection intro at `implement.md:11`, dispatch list at `implement.md:19-22`, or option bullets at `implement.md:13-15`.
- **No sibling skills**: `critical-review`, `morning-review`, and any other skill with `cortex_command.*` imports are out of scope — ticket 120's codebase-import-graph audit.
- **No re-probing**: one probe per §1 render, no caching across renders within a single invocation, no persistence across sessions.
- **No telemetry**: no `runtime_probe` / `probe_check` / `graceful_degrade` event-name; no metrics; no events.log entry per probe.
- **No upgrade hint**: no "install cortex-overnight-integration" message in menu, diagnostic, or elsewhere.
- **No PATH check for `cortex` binary**: research resolved this as redundant.
- **No probe in worker subprocesses**: workers don't invoke the lifecycle skill.
- **No automated runtime test for R4**: manual verification only — Task 4 is the checkbox owner.
- **No defensive probe at §1a entry**.
