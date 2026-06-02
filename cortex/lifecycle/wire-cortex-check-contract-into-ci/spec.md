# Specification: wire-cortex-check-contract-into-ci

## Problem Statement

`.github/workflows/validate.yml` currently runs only two skill-metadata/call-graph validators — no `pytest`, no `cortex-check-*` gates. Every pre-commit gate and the Python test suite are enforced only by the opt-in local `.githooks/pre-commit` hook, which is absent on fresh clones, the overnight runner, and CI checkouts. So a contract-checker regression (or any gate regression) can reach `main` via a direct push or external PR with no automated signal. This feature gives the `cortex-check-contract` gate and its fixtures an automated, wheel-immune CI signal on every push and PR: a *blocking* `pytest tests/test_check_contract.py` step that guards the checker's logic, plus a *non-blocking* `--audit` step that surfaces repo-wide contract drift as a visible signal without failing the build. It backstops #279's contract false-positive fix so that fix cannot silently rot.

## Phases
- **Phase 1: Wire contract checks into validate.yml** — add a blocking pytest gate and a non-blocking, source-mode `--audit` signal step (with step-summary visibility) to the existing `validate` job.

## Requirements

1. **Blocking contract-test step**: `validate.yml` runs `pytest tests/test_check_contract.py` as a blocking step (no `continue-on-error`), so any contract-checker regression fails the build. Acceptance: `grep -c 'pytest tests/test_check_contract.py' .github/workflows/validate.yml` ≥ 1, and that step carries no `continue-on-error:` key (verified by inspecting the step block). Grounded in `tests/test_check_contract.py` (exists; pytest-based; wheel-immune via `python3 -m cortex_command.lint.contract` subprocess with `PYTHONPATH` set to the checkout). **Phase**: Wire contract checks into validate.yml

2. **pytest installed in CI**: the workflow installs `pytest` (the only added dependency beyond the existing `pyyaml`). Acceptance: `grep -Ec 'pip install .*pytest' .github/workflows/validate.yml` ≥ 1. **Phase**: Wire contract checks into validate.yml

3. **Non-blocking source-mode audit step**: `validate.yml` runs `CORTEX_COMMAND_FORCE_SOURCE=1 bin/cortex-check-contract --audit` (relative-path binstub, working-tree source — never an installed wheel) as a step carrying `continue-on-error: true`. Acceptance: a single step block in `.github/workflows/validate.yml` contains all three of `CORTEX_COMMAND_FORCE_SOURCE=1`, `bin/cortex-check-contract --audit`, and `continue-on-error: true`; verified by inspecting that step. (`grep -c 'continue-on-error: true' .github/workflows/validate.yml` ≥ 1 and `grep -c 'CORTEX_COMMAND_FORCE_SOURCE=1' .github/workflows/validate.yml` ≥ 1.) Grounded in `bin/cortex-check-contract` (honors `CORTEX_COMMAND_FORCE_SOURCE=1`; `--audit` is a real flag at `cortex_command/lint/contract.py:1447`). **Phase**: Wire contract checks into validate.yml

4. **Audit signal routed to step summary**: the audit step writes its output to `$GITHUB_STEP_SUMMARY` so findings render on the run summary page (the non-blocking step otherwise renders ~green and hides the signal). Acceptance: `grep -c 'GITHUB_STEP_SUMMARY' .github/workflows/validate.yml` ≥ 1, located within the audit step block. **Phase**: Wire contract checks into validate.yml

5. **No wheel / no `just`/`uv` install added**: CI executes working-tree source only; the workflow does not install the cortex-command wheel or add `just`/`uv`. Acceptance: `grep -Ec 'uv tool install|pip install +git\+|cortex-command@|setup-just' .github/workflows/validate.yml` = 0 (no wheel/just/uv provisioning lines introduced). **Phase**: Wire contract checks into validate.yml

6. **Workflow stays valid and existing steps preserved**: `validate.yml` remains valid YAML and the two pre-existing steps (skill validation, call-graph guard) are retained alongside the new steps. Acceptance: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/validate.yml'))"` exits 0, and `grep -c 'validate-callgraph.py' .github/workflows/validate.yml` ≥ 1 and `grep -c 'validate-skill.py' .github/workflows/validate.yml` ≥ 1. **Phase**: Wire contract checks into validate.yml

## Non-Requirements

- **Does NOT make the audit blocking.** The `--audit` step is `continue-on-error: true`; contract drift surfaces as signal, never fails the build (matches #280's sanctioned "Linux-only, non-blocking signal" reopen-condition).
- **Does NOT clean up the 2 current E104 hits** (`cortex-auth` in `docs/overnight-operations.md`, `cortex-report` in `skills/morning-review/references/walkthrough.md`). These have no `bin/.contract-lint-exceptions.md` entry and fall outside #279's scope; they will appear in the non-blocking audit signal until separately ledgered or fixed. Adding ledger entries is explicitly deferred.
- **Does NOT add a macOS runner or enforce the full `just test` suite in CI.** That is #280 (status `wont-do`); only the single platform-agnostic `test_check_contract.py` file is wired here.
- **Does NOT block on #279.** The pytest step is independent of #279 and green today; the audit is non-blocking, so #279's 8 unfixed `cortex-worktree-create` E101 false positives appearing in the signal is acceptable until #279 lands.
- **Does NOT change the workflow triggers.** The existing `push` + `pull_request` triggers are preserved.

## Edge Cases

- **Audit exits 1 (current tree: 8 E101 + 2 E104 violations)**: `continue-on-error: true` yields step `conclusion: success`; the job and run stay green and required-status checks are not blocked; findings appear in the step summary.
- **#279 not yet merged when this lands**: the audit signal displays #279's false positives plus the 2 E104 hits — expected and acceptable because the step is informational/non-blocking.
- **Contract-checker regression or test-file rename/collection error**: the blocking pytest step exits non-zero and fails the build — the intended backstop behavior.
- **`bin/cortex-check-contract` not on PATH in CI**: invoked by relative path `bin/cortex-check-contract` (binstub has a `#!/usr/bin/env bash` shebang and the executable bit), matching the `auto-release.yml` relative-binstub precedent.
- **Audit produces no output (clean tree, e.g. after #279 + E104 cleanup)**: the step summary is empty/clean and the job is green — no false signal.

## Changes to Existing Behavior

- **ADDED**: `.github/workflows/validate.yml` gains a blocking `pytest tests/test_check_contract.py` gate and a non-blocking `CORTEX_COMMAND_FORCE_SOURCE=1 bin/cortex-check-contract --audit` signal step (with `$GITHUB_STEP_SUMMARY` output) on every push and PR.
- **MODIFIED**: the `Install dependencies` step installs `pytest` in addition to `pyyaml`.

## Technical Constraints

- **Source-mode execution** (`cortex/requirements/project.md:38`): `CORTEX_COMMAND_FORCE_SOURCE=1` makes `bin/cortex-*` wrappers skip the wheel-import branch and run the working-tree module — the load-bearing mechanism for the wheel-immune requirement. `bin/cortex-check-contract` already honors it.
- **Step-level `continue-on-error`** (not job-level): yields `conclusion: success`, keeps the job green, and does not block required status checks (per GitHub contexts/branch-protection docs). Job-level would paint the job red in the PR UI.
- **Relative-path binstub invocation**: `bin/` is not on PATH in a fresh `actions/checkout@v4` checkout and no wheel is installed, so the binstub is called as `bin/cortex-check-contract`.
- **Two-mode gate convention deviation, bounded** (`cortex/requirements/project.md:92`): the documented convention is `just <recipe>-audit`, but the ticket's Edges constrain CI to `pip install pytest` only (no `just`/`uv`), so CI invokes the binstub directly with `--audit`. Intentional and scoped.
- **Valid YAML**: per `cortex/lifecycle.config.md` review criteria (settings/config files must remain valid after changes), `validate.yml` must parse as valid YAML.
- **No events-registry / lifecycle-gate obligation**: editing `.github/workflows/` is not in the lifecycle skill's required-file list and emits no lifecycle/overnight event, so no `bin/.events-registry.md` row is required.

## Open Decisions

None — the audit invocation form (relative-path binstub with `CORTEX_COMMAND_FORCE_SOURCE=1`), signal visibility (`$GITHUB_STEP_SUMMARY`), and pytest install placement (folded into the existing install step) were all resolved during research and the spec interview.

## Proposed ADR

None considered.
