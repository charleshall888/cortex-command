---
schema_version: "1"
uuid: ab06b8e4-de55-4fca-92d3-0a62634ce663
title: "Wire cortex-check-contract into CI: run contract fixtures + --audit (source mode) in validate.yml"
status: complete
priority: medium
type: chore
created: 2026-06-02
updated: 2026-06-02
complexity: simple
criticality: medium
spec: cortex/lifecycle/wire-cortex-check-contract-into-ci/spec.md
areas: ['tests']
---
**Why:** CI (`.github/workflows/validate.yml`) runs only two skill-metadata validators — no `pytest`, no `cortex-check-*` gates, no `just test`. Every pre-commit gate and the entire Python test suite are enforced only by the local `.githooks/pre-commit` hook, which requires `just setup-githooks` (opt-in) and is absent on fresh clones, the overnight runner, and CI checkouts. So a contract-checker regression (or any gate regression) can reach `main` via a direct push or external PR with no automated signal. #279 fixes the contract false positives, but without CI that fix has no backstop and will rot. A CI `--audit` step additionally compensates for the `--staged` membership drift, since `--audit` scans the full corpus regardless of `Path.match` semantics.

**Role:** Give the contract gate and its fixtures an automated CI signal on every push and PR, executing working-tree source rather than a stale wheel.

**Integration:** Add a step to the existing `validate.yml` job (keep the push+PR trigger). Run `pytest tests/test_check_contract.py` — wheel-immune by construction, since it invokes `python3 -m cortex_command.lint.contract` with `PYTHONPATH` set to the checkout — and optionally `CORTEX_COMMAND_FORCE_SOURCE=1 cortex-check-contract --audit` against the repo. Run via source (`-m` / `FORCE_SOURCE`), never an installed wheel, to avoid the #279 stale-wheel hazard. This is the concrete, platform-agnostic, network-free instance that justifies reopening #280's "Linux-only non-blocking signal job" path (#280 is `wont-do` but documents that reopen-condition).

**Edges:** Must land after #279's code fix — `--audit` exits 1 on the current tree (the 8 false positives are still present), so wiring it before #279 lands makes CI red on arrival. The step needs only `pip install pytest` (CI already provisions Python 3.12); it does not need `uv`, `just`, or the wheel. Decide whether the step blocks the build or runs as a non-blocking signal per #280's framing.

**Touch-points:** `.github/workflows/validate.yml`, `tests/test_check_contract.py`, `bin/cortex-check-contract` (`CORTEX_COMMAND_FORCE_SOURCE` source mode). Related: #279 (source of this follow-up), #280 (the `wont-do` test-suite-in-CI ticket whose reopen-condition this satisfies).