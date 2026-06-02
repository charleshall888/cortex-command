# Plan: wire-cortex-check-contract-into-ci

## Overview
Append two steps to the single `validate` job in `.github/workflows/validate.yml`: a *blocking* `pytest tests/test_check_contract.py` gate (with `pytest` added to the existing install line) that fails the build on any contract-checker regression, and a *non-blocking* `CORTEX_COMMAND_FORCE_SOURCE=1 bin/cortex-check-contract --audit` signal step (`continue-on-error: true`, output routed to `$GITHUB_STEP_SUMMARY`) that surfaces repo-wide contract drift without failing the build. Working-tree source only — no wheel, no `just`/`uv`.

## Outline

### Phase 1: Wire contract checks into validate.yml (tasks: 1, 2, 3)
**Goal**: Give the contract gate and its fixtures an automated, wheel-immune CI signal on every push and PR — blocking on the checker's own tests, non-blocking on repo-wide audit drift.
**Checkpoint**: `validate.yml` parses as valid YAML, retains its two pre-existing validators, and contains both the blocking pytest step and the non-blocking source-mode audit step with step-summary output.

## Tasks

### Task 1: Add pytest dependency + blocking contract-test step
- **Files**: `.github/workflows/validate.yml`
- **What**: Add `pytest` to the existing `Install dependencies` step (`pip install pyyaml pytest`) and append a new blocking step `run: pytest tests/test_check_contract.py` (no `continue-on-error`), so any contract-checker regression fails the build.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Current install line is `.github/workflows/validate.yml:20` (`run: pip install pyyaml`). Append the new step after the existing last step (the `Call-graph guard` block ending at line 36), matching the existing `- name: <Title-case>` + single-line `run:` convention with 2-space step indent. `tests/test_check_contract.py` is wheel-immune by construction — it invokes the checker as a subprocess `python3 -m cortex_command.lint.contract` with `PYTHONPATH` set to the checkout, and `pyproject.toml`'s `[tool.pytest.ini_options] pythonpath = ["."]` puts the checkout on the path when run from repo root. pytest exits non-zero on any failure/collection error → blocking is the default (do NOT add `continue-on-error`). The step is green on the current tree (the test passes today, independent of #279).
- **Verification**: `grep -Ec 'pip install .*pytest' .github/workflows/validate.yml` ≥ 1 AND `grep -c 'pytest tests/test_check_contract.py' .github/workflows/validate.yml` ≥ 1 — pass if both counts ≥ 1. Confirm the pytest step block carries no `continue-on-error:` key by inspecting the step.
- **Status**: [x] done

### Task 2: Add non-blocking source-mode audit signal step with step-summary output
- **Files**: `.github/workflows/validate.yml`
- **What**: Append a second new step that runs `CORTEX_COMMAND_FORCE_SOURCE=1 bin/cortex-check-contract --audit` carrying `continue-on-error: true`, capturing the audit output and appending it to `$GITHUB_STEP_SUMMARY` so findings render on the run summary page even when the audit exits non-zero.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Invoke the binstub by **relative path** `bin/cortex-check-contract` — `bin/` is not on PATH in a fresh `actions/checkout@v4` checkout and no wheel is installed (precedent: `auto-release.yml` calls `bin/cortex-auto-bump-version` by relative path). The binstub honors `CORTEX_COMMAND_FORCE_SOURCE=1` (`bin/cortex-check-contract:16-18`, execs `python3 -m cortex_command.lint.contract` against the checkout). `--audit` is a real flag (`cortex_command/lint/contract.py:1447`). **Key pitfall**: GitHub's default `run:` shell is `bash -eo pipefail`, and `--audit` exits 1 when violations exist (today: 8 E101 + 2 E104). Structure the run block so the audit output is captured and appended to `$GITHUB_STEP_SUMMARY` *before* the non-zero exit would abort the script — i.e. capture the command's output and exit code without letting `-e` short-circuit the summary write. Keep `continue-on-error: true` at the **step level** (not job level) so the step resolves to `conclusion: success` (job/run stay green, required checks unblocked) while `outcome: failure` remains inspectable — this is the canonical documented mechanism; do NOT replace it with `|| true`, which discards the exit code. Match existing block-`run: |` style with 2-space indent.
- **Verification**: A single step block in `.github/workflows/validate.yml` contains all of `CORTEX_COMMAND_FORCE_SOURCE=1`, `bin/cortex-check-contract --audit`, `continue-on-error: true`, and `GITHUB_STEP_SUMMARY` — verified by inspecting that step. Aggregate counts: `grep -c 'continue-on-error: true' .github/workflows/validate.yml` ≥ 1 AND `grep -c 'CORTEX_COMMAND_FORCE_SOURCE=1' .github/workflows/validate.yml` ≥ 1 AND `grep -c 'GITHUB_STEP_SUMMARY' .github/workflows/validate.yml` ≥ 1 — pass if all three ≥ 1.
- **Status**: [x] done

### Task 3: Acceptance sweep — YAML validity, preserved steps, no wheel/just/uv
- **Files**: `.github/workflows/validate.yml`
- **What**: Verify the final workflow against the full spec acceptance set — parses as valid YAML, retains both pre-existing validators (`validate-skill.py`, `validate-callgraph.py`), preserves the `push` + `pull_request` triggers, and introduces no wheel/`just`/`uv` provisioning lines.
- **Depends on**: [1, 2]
- **Complexity**: simple
- **Context**: This is a whole-file consistency check over the edits from Tasks 1–2, using the spec's pre-defined acceptance commands (Requirements 5 & 6) — not an artifact created for verification. No new edits expected unless a check fails, in which case fix the offending line in `validate.yml`.
- **Verification**: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/validate.yml'))"` exits 0 AND `grep -c 'validate-callgraph.py' .github/workflows/validate.yml` ≥ 1 AND `grep -c 'validate-skill.py' .github/workflows/validate.yml` ≥ 1 AND `grep -Ec 'uv tool install|pip install +git\+|cortex-command@|setup-just' .github/workflows/validate.yml` = 0 — pass if YAML loads, both validator greps ≥ 1, and the wheel/just/uv grep = 0.
- **Status**: [x] done

## Risks
- **Audit step renders ~green in the GitHub UI** despite finding violations (a documented `continue-on-error` limitation, community discussion #15452) — mitigated by routing findings to `$GITHUB_STEP_SUMMARY`. If higher visibility is later wanted, problem-matchers/annotations are the upgrade path (deliberately deferred as overkill for this repo).
- **Audit is red-on-arrival today**: until #279 lands and the 2 E104 hits are ledgered, the audit surfaces 8 E101 + 2 E104 findings. This is expected and acceptable precisely because the step is non-blocking; the spec's Non-Requirements explicitly defer both the #279 fix and the E104 ledger entries.
- **Two-mode convention deviation**: the documented pattern is `just check-contract-audit`, but the ticket constrains CI to `pip install pytest` only (no `just`/`uv`), so CI invokes the binstub directly with `CORTEX_COMMAND_FORCE_SOURCE=1 --audit`. Intentional and bounded per the spec's Technical Constraints.
