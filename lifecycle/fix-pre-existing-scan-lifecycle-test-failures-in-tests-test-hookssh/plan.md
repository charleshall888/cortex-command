# Plan: fix-pre-existing-scan-lifecycle-test-failures-in-tests-test-hookssh

## Overview

Remove the dead `${AGENT:-}` env-var gate from `hooks/cortex-scan-lifecycle.sh` so the canonical SessionStart shape (`hookSpecificOutput.additionalContext`) is emitted unconditionally; bundle three precise dead-code deletions in `tests/test_lifecycle_phase_parity.py`; regenerate the plugin mirror via the dual-source `just build-plugin` recipe so the pre-commit drift gate passes; then run the full acceptance command set from spec.md. Tasks 1 and 2 are independent and edit different files; Task 3 depends only on Task 1's canonical edit; Task 4 runs after all edits land.

## Tasks

### Task 1: Remove dead AGENT env-var gate from canonical hook
- **Files**: `hooks/cortex-scan-lifecycle.sh`
- **What**: Replace the `if [[ "${AGENT:-}" == "claude" ]]` / `else` branch at lines 459–471 with a single unconditional `jq -n` invocation that emits the canonical `hookSpecificOutput.additionalContext` shape. The outer `if [[ -n "$context" ]]` guard at line 459 is preserved verbatim so the empty-context path still emits nothing.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The existing block at lines 459–471 reads (verbatim, paraphrased for the implementer):
  ```
  if [[ -n "$context" ]]; then
    if [[ "${AGENT:-}" == "claude" ]]; then
      jq -n --arg ctx "$context" '{ hookSpecificOutput: { hookEventName: "SessionStart", additionalContext: $ctx } }'
    else
      jq -n --arg ctx "$context" '{ additional_context: $ctx }'
    fi
  fi
  ```
  Replace with the single Claude form — keep the outer guard, drop the inner if/else, retain the same `jq -n --arg ctx "$context" '{ hookSpecificOutput: { hookEventName: "SessionStart", additionalContext: $ctx } }'` invocation. Pattern reference: `plugins/cortex-core/hooks/cortex-validate-commit.sh` and `plugins/cortex-overnight/hooks/cortex-tool-failure-tracker.sh` already emit this exact shape unconditionally — match their structure. Do NOT hand-edit `plugins/cortex-overnight/hooks/cortex-scan-lifecycle.sh`; Task 3 regenerates it from the canonical.
- **Verification**: From a working directory containing `lifecycle/test-feature/research.md`, run `AGENT= bash hooks/cortex-scan-lifecycle.sh <<<'{"hook_event_name":"SessionStart","session_id":"x","cwd":"'$PWD'"}'  | jq -r 'has("hookSpecificOutput")'` — pass if output is `true`. Set up the fixture with `mkdir -p lifecycle/test-feature && touch lifecycle/test-feature/research.md` in a `$TMPDIR` scratch directory, run the hook from that directory, then remove the scratch directory.
- **Status**: [x] done

### Task 2: Delete dead defensive code from `test_lifecycle_phase_parity.py`
- **Files**: `tests/test_lifecycle_phase_parity.py`
- **What**: Apply three precise edits per spec.md R5: (a) delete the entire line `    env["AGENT"] = "claude"` at line 511; (b) collapse the `if "hookSpecificOutput" in payload:` / `else: ctx = payload.get("additional_context", "")` block at lines 543–546 so only the Claude-shape access (`ctx = payload["hookSpecificOutput"].get("additionalContext", "")`) remains (the conditional and the fallback `else` are deleted together); (c) replace the substring `additional_context` with `additionalContext` in the docstring at line 490 (the line reads "`raw_context`: the full additional_context for diagnostic surfacing." — change to "`raw_context`: the full additionalContext for diagnostic surfacing.").
- **Depends on**: none
- **Complexity**: simple
- **Context**: Verified line numbers: 490 (docstring), 511 (assignment), 545 (fallback parser within the if/else around 543–546). The parser block currently looks like:
  ```
  if "hookSpecificOutput" in payload:
      ctx = payload["hookSpecificOutput"].get("additionalContext", "")
  else:
      ctx = payload.get("additional_context", "")
  ```
  After the edit, the four lines collapse to a single line: `ctx = payload["hookSpecificOutput"].get("additionalContext", "")`. The hook can no longer emit the snake_case shape (Task 1), so the conditional is dead code per spec.md R5 and Edge Case framing. The `env` dict at line 511 is otherwise used to set `PYTHONPATH`; only the AGENT assignment line is deleted, the dict variable is retained.
- **Verification**: Three sub-checks, all must pass: (a) `grep -nE '^[[:space:]]*env\["AGENT"\][[:space:]]*=' tests/test_lifecycle_phase_parity.py` returns no matches; (b) `grep -nE 'payload\.get\("additional_context"' tests/test_lifecycle_phase_parity.py` returns no matches; (c) `grep -c 'additional_context' tests/test_lifecycle_phase_parity.py` returns `0`.
- **Status**: [x] done

### Task 3: Regenerate plugin mirror from canonical and verify byte-equality
- **Files**: `plugins/cortex-overnight/hooks/cortex-scan-lifecycle.sh` (regenerated, not hand-edited)
- **What**: Run `just build-plugin` to regenerate every build-output plugin tree from the canonical sources (including `plugins/cortex-overnight/hooks/cortex-scan-lifecycle.sh` from `hooks/cortex-scan-lifecycle.sh`). Then run the byte-equality acceptance check from spec.md R4(b) to confirm the canonical and mirror `jq -n` emission blocks match. This task must run AFTER Task 1 lands so the canonical source the build copies is already fixed.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: The `build-plugin` justfile recipe iterates over `BUILD_OUTPUT_PLUGINS` and copies the canonical `hooks/cortex-scan-lifecycle.sh` into each plugin's `hooks/` directory. The pre-commit drift hook in `.githooks/pre-commit` runs `just build-plugin` automatically when staged paths match the canonical-source pattern (`hooks/cortex-`), so this task ALSO serves as a pre-commit dry-run — if the staged canonical differs from the staged mirror at commit time, the drift hook fails the commit. Running `just build-plugin` first lets the implementer fix the divergence proactively. Do not hand-edit `plugins/cortex-overnight/hooks/cortex-scan-lifecycle.sh` — the recipe is the only legitimate writer.
- **Verification**: Three sub-checks, all must pass per spec.md R4: (a) `git diff --name-only` includes both `hooks/cortex-scan-lifecycle.sh` and `plugins/cortex-overnight/hooks/cortex-scan-lifecycle.sh` (both files have unstaged changes from Task 1 + the regeneration); (b) `diff <(awk '/jq -n/,/^}$/' hooks/cortex-scan-lifecycle.sh) <(awk '/jq -n/,/^}$/' plugins/cortex-overnight/hooks/cortex-scan-lifecycle.sh)` produces no output (jq emission block is byte-equal); (c) `grep -c 'additional_context' plugins/cortex-overnight/hooks/cortex-scan-lifecycle.sh` returns `0`.
- **Status**: [x] done

### Task 4: Run full acceptance verification command set
- **Files**: (none — verification-only)
- **What**: Run the complete spec.md acceptance command set against the post-edit working tree to confirm every requirement (R1–R6) passes before commit. This is the consolidated gate that combines per-task verifications into a single end-to-end check; it does not modify any files.
- **Depends on**: [1, 2, 3]
- **Complexity**: simple
- **Context**: The spec defines six requirements with binary-checkable acceptance commands. This task runs all of them in sequence and surfaces any failure before the commit step. The command list comes directly from spec.md's Requirements section — no new verification is invented here. Out of scope per spec.md Technical Constraints: the broader `pytest tests/` sweep is NOT a gate (pre-existing red test in unrelated lifecycle artifact at `lifecycle/migrate-gate-1-.../plan.md`). Run only the targeted modules.
- **Verification**: All four commands exit 0 and produce expected output: (a) `bash tests/test_hooks.sh` exits 0 and reports `14 passed, 0 failed`; (b) `pytest tests/test_lifecycle_phase_parity.py` exits 0; (c) the R1 manual hook check from Task 1's Verification (`AGENT= bash hooks/cortex-scan-lifecycle.sh ... | jq -r 'has("hookSpecificOutput")'` returns `true`); (d) the R3 empty-context check (`bash hooks/cortex-scan-lifecycle.sh <<<'{"hook_event_name":"SessionStart","session_id":"x","cwd":"/tmp"}' | wc -c` returns `0` from a CWD with no incomplete `lifecycle/` features).
- **Status**: [x] done

## Verification Strategy

End-to-end verification is consolidated in Task 4 and reproduces every binary-checkable acceptance command from spec.md R1–R6. After all four tasks complete and Task 4 reports green, the working tree is ready for the lifecycle Implement phase's standard `/cortex-core:commit` step. The commit then triggers the pre-commit drift gate (`.githooks/pre-commit`), which re-runs `just build-plugin` and `git diff --quiet plugins/*/` for every build-output plugin — providing a second-layer check that the canonical and mirror remain in sync. Test_hooks.sh exercises the canonical hook; combined with Task 3's byte-equality check and the drift gate, the plugin mirror is held to the same emission contract without needing a separate plugin-mirror test for this file.

## Veto Surface

- **Bundled cleanup of `test_lifecycle_phase_parity.py`** (Task 2): R5 bundles three dead-code edits in a "fix failing tests" ticket. Critical-review dismissed scope-creep objections on the grounds that project.md's "Workflow trimming" principle endorses hard-deletion when zero runtime consumers exist. If the operator wants this split into a separate hygiene ticket, Task 2 can be lifted and the spec re-cut. Doing so leaves `env["AGENT"] = "claude"` as a regression-detection canary in the parity test — fail-soft rather than fail-loud.
- **Reliance on `just setup-githooks` being installed** (Task 3): the pre-commit drift gate only fires if the contributor has run `just setup-githooks`. Task 3 includes a manual `just build-plugin` invocation to make mirror regeneration explicit rather than implicit on commit, partially mitigating this. If the operator wants a CI-layer safety net for this specific file, it would require adding `plugins/cortex-overnight/hooks/cortex-scan-lifecycle.sh` to the mirror-parity test (`tests/test_plugin_mirror_parity.py`) — currently scoped to three lifecycle reference markdown files only. That is out of scope for this plan.

## Scope Boundaries

- **Do NOT** add `AGENT=claude` to test invocations in `tests/test_hooks.sh`.
- **Do NOT** delete `hooks/cortex-scan-lifecycle.sh` or any scan-lifecycle test.
- **Do NOT** change `tests/fixtures/hooks/scan-lifecycle/*.json` fixtures.
- **Do NOT** introduce a runtime mechanism for selecting alternate hook output shapes (per-Cursor, per-Gemini, etc.).
- **Do NOT** update the backlog ticket's "all 16 PASS" line.
- **Do NOT** modify the documented hook contract in `docs/agentic-layer.md`.
- **Do NOT** attempt to fix the pre-existing red test `tests/test_lifecycle_references_resolve.py::test_every_lifecycle_reference_resolves` (stale citation in an unrelated lifecycle artifact); it is out of scope per spec.md R6.
- **Do NOT** hand-edit `plugins/cortex-overnight/hooks/cortex-scan-lifecycle.sh` — Task 3's `just build-plugin` is the only legitimate writer.
