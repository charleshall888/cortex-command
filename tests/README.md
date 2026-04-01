# Tests

Test suites for hooks, skills, and lifecycle infrastructure.

## Running Tests

Run all suites:

```
just test-skills
```

Run all Python tests (pipeline, overnight, and infrastructure):

```
just test
```

Run an individual suite:

```
just test-skill-contracts     # Validate SKILL.md frontmatter for all skills
just test-hook-commit         # Commit hook regression tests
just test-hooks               # All other hook regression tests
just test-lifecycle-state     # Lifecycle phase detection
just test-skill-behavior      # Behavioral tests for the commit skill hook
just test-skill-pressure <skill>  # Pressure scenario runner for a specific skill
just failure-matrix           # Run the transition failure matrix across all skills
```

## Output Format

Individual test scripts print one line per test case:

```
PASS validate-commit/valid-simple
FAIL validate-commit/invalid-lowercase: expected 'deny', got 'allow'
```

Each script ends with a summary line:

```
9 passed, 0 failed (out of 9)
```

The `test-skills` master runner wraps each sub-suite:

```
[PASS] test-skill-contracts
[FAIL] test-hook-commit
       FAIL validate-commit/cursor-valid-simple: expected 'allow', got 'null'
       1 passed, 1 failed (out of 2)

Test suite: 4/5 passed
```

## Directory Structure

```
tests/
  fixtures/
    hooks/         Hook input fixtures, organized by hook name
      cleanup-session/
      validate-commit/
    contracts/     Skill contract fixture directories (each contains SKILL.md)
    state/         Lifecycle events.log fixtures, one per phase
      research/
      specify/
      plan/
      implement/
      review/
      complete/
      escalated/
    readiness/     Backlog item YAML fixtures for readiness gate testing
  scenarios/       Pressure scenario YAML files, organized by skill
    commit/        Scenarios for the commit skill
    lifecycle/     Scenarios for the lifecycle skill
  test_hook_commit.sh        Commit hook regression tests
  test_hooks.sh              All other hook regression tests
  test_lifecycle_state.py    Lifecycle phase detection tests (pytest)
  test_skill_contracts.py    Skill contract fixture assertion runner (pytest)
  test_skill_behavior.sh     Behavioral tests for the commit skill hook
  pressure_runner.py         Pressure scenario runner (dispatches claude -p subagents)
  failure_matrix.py          Transition failure matrix script

claude/overnight/tests/      Overnight runner module tests (pytest)
  test_overnight_readiness.py  Backlog readiness gate tests
  test_overnight_state.py      OvernightFeatureStatus tests
  test_report.py               render_completed_features tests
  test_strategy.py             load/save strategy tests

claude/pipeline/tests/       Pipeline module tests (pytest)
  test_conflict_classifier.py  classify_conflict() tests
  test_trivial_conflict.py     resolve_trivial_conflict() and execute_feature() tests
  test_repair_agent.py         dispatch_repair_agent() tests
  test_recovery_log.py         write_recovery_log_entry() tests
```

## Fixture Naming Conventions

### Hook fixtures (`fixtures/hooks/<hook-name>/`)

JSON files fed to the hook via stdin. Filename prefix determines expected outcome:

- `valid-*` — hook should allow/succeed (exit 0, `permissionDecision: "allow"`)
- `invalid-*` — hook should deny/fail (exit 0, `permissionDecision: "deny"`)
- `cursor-valid-*` — Cursor-format valid input
- `cursor-invalid-*` — Cursor-format invalid input

### Contract fixtures (`fixtures/contracts/<case-name>/`)

Each case is a directory containing a `SKILL.md` file. The directory name determines
expected outcome:

- `valid-*` — `validate-skill.py` must exit 0 (no `[ERROR]` in output)
- `invalid-*` — must exit 1 OR output must contain a `[WARN]` line

### State fixtures (`fixtures/state/<phase>/`)

An `events.log` file in each subdirectory. The directory name is the expected phase
string returned by the lifecycle state detector.

### Readiness fixtures (`fixtures/readiness/`)

YAML frontmatter markdown files. The filename encodes the expected outcome:

- `eligible.yaml` — passes all 6 readiness gates
- `rejected-<reason>.yaml` — rejected at the named gate

## Pressure Scenario Format

Pressure scenarios are YAML files that test skill and hook rule compliance under
adversarial prompting. Each scenario dispatches a fresh `claude -p` subagent with a
prompt designed to pressure the agent into breaking a rule, then checks the response
against pass and fail signal patterns.

Key fields in each scenario file:

| Field               | Description                                                          |
|---------------------|----------------------------------------------------------------------|
| `skill`             | Matches the `tests/scenarios/` subdirectory name                     |
| `name`              | Kebab-case identifier for this scenario                              |
| `description`       | What rule this scenario tests and why                                |
| `pressures`         | List of adversarial pressure strings woven into the task (at least 3)|
| `task`              | Full prompt given to the subagent (multi-line block scalar)          |
| `expected_behavior` | Plain-English description of what the agent must do to pass          |
| `pass_threshold`    | Number of consecutive runs that must pass (default: 1)               |
| `pass_signals`      | Case-insensitive regexes; at least one must match to pass            |
| `fail_signals`      | Case-insensitive regexes; any match causes immediate failure         |

See `tests/scenarios/README.md` for the full schema, pass/fail logic, authoring
guidelines, and a complete example scenario.

## Adding New Tests

**New hook test cases**: Add a JSON fixture file to `tests/fixtures/hooks/<hook-name>/`
following the `valid-*` / `invalid-*` naming convention. The existing test section in
`tests/test_hooks.sh` picks it up automatically (if the section iterates the directory).

**New hook test section**: Add a section to `tests/test_hooks.sh` following the pattern
of existing sections. Register the suite in `just test-skills` by adding a `run_test`
line (~line 233 of `justfile`).

**New Python test for `claude.*` modules**: Add a `def test_*()` function in the
appropriate `claude/*/tests/` directory; pytest collects it automatically.

**New Python test for infrastructure** (lifecycle state, skill contracts): Add a
`@pytest.mark.parametrize`d function in `tests/` following the pattern in
`test_lifecycle_state.py`; register in `pyproject.toml` testpaths if a new directory
is needed.

**New skill contract fixtures**: Add a subdirectory under `tests/fixtures/contracts/`
with a `SKILL.md` file. `test_skill_contracts.py` discovers all subdirectories
automatically.

**New pressure scenario**: Add a `.yaml` file to `tests/scenarios/<skill>/` following
the schema in `tests/scenarios/README.md`.
