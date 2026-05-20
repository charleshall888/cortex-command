# cortex-complexity-escalator golden-replay fixtures

This directory holds golden-replay fixtures for the parity test that guards
the Python port of `bin/cortex-complexity-escalator`
(`cortex_command.lifecycle.complexity_escalator`).

Each test case is stored as a set of flat sibling files:

```
<case>.argv         one argument per line (feature slug on line 1,
                    then flag lines for --gate)
<case>.stdin        literal bytes piped to stdin (empty for all current cases)
<case>.stdout       literal bytes captured from stdout
<case>.stderr       literal bytes captured from stderr
<case>.exitcode     the exit status as a single decimal integer + trailing newline
<case>.research_md  (optional) content placed in research.md at invoke time
<case>.spec_md      (optional) content placed in spec.md at invoke time
<case>.events_log   (optional) pre-existing events.log content at invoke time
```

The parity test (`tests/test_cortex_complexity_escalator_parity.py`) injects
`--lifecycle-dir` dynamically: it creates a scratch lifecycle directory under
pytest's `tmp_path`, places the sidecar files in the appropriate feature
subdirectory (`cortex/lifecycle/<feature>/`), then runs the module and
compares stdout/stderr/exit-code byte-for-byte against these files.

## Cases captured

| Case              | Gate                      | Scenario                                             | Threshold met? | stdout                      | exit |
|-------------------|---------------------------|------------------------------------------------------|----------------|-----------------------------|------|
| `gate1_fires`     | `research_open_questions` | 2 bullets in `## Open Questions` (threshold = 2)     | yes            | escalation announcement     | 0    |
| `gate1_no_fire`   | `research_open_questions` | 1 bullet in `## Open Questions` (threshold = 2)      | no             | empty                       | 0    |
| `already_complex` | `research_open_questions` | Pre-existing `complexity_override` event; tier guard fires | n/a       | empty                       | 0    |

### Case details

**`gate1_fires`**: Covers fixture requirement (a) — escalation trigger met, `complexity_override` event emitted. The research.md has exactly 2 top-level bullets under `## Open Questions`, which meets Gate 1's threshold of ≥2. The module writes the event to events.log and prints the escalation announcement to stdout.

**`gate1_no_fire`**: Covers fixture requirement (b) — trigger not met, no event emitted. The research.md has 1 bullet (below the threshold of 2). The module exits 0 silently.

**`already_complex`**: Covers fixture requirement (c) — ambiguous-tier path. The events.log already contains a `complexity_override` event with `"to": "complex"`. Even though research.md has enough bullets to trigger escalation (3 bullets), the tier guard fires first and the module exits 0 silently without appending a second event.

### Exit-code surface

The closed-set exit-code contract is `{0, 2}`. These fixtures cover exit 0. Exit 2 (slug rejection, realpath failure, read/write IO error) is exercised by the behavioral test suite (`tests/test_complexity_escalator.py`), which monkeypatches internals.

## Determinism harness

The fixtures were captured under a controlled environment so the parity test
can replay them deterministically. The Python module must run under the same
environment when compared.

- **jq version**: `jq --version` reported `jq-1.8.1` at capture time. The
  module does not invoke `jq` (it uses Python's `json.dumps`/`json.loads`
  directly), but jq is pinned here to match the harness contract established
  for sibling fixtures (Tasks 2, 6, 11–22).
- **`LC_ALL=C`**: set during capture; forces byte-deterministic collation and
  number formatting in any subprocesses the module may shell out to.
- **`TZ=UTC`**: set during capture; pins the timezone for any wall-clock
  reads. The module emits a `ts` field in events.log via
  `datetime.now(timezone.utc).strftime(...)`, which is always UTC regardless
  of `TZ`. The `TZ=UTC` override is still set for consistency with the
  harness contract.
- **Timestamp handling**: The stdout escalation message does not contain
  timestamps. The events.log `ts` field is written but is NOT part of
  stdout/stderr — the parity test compares only stdout/stderr/exit-code,
  not the events.log side-effect. The `ts` field therefore does not need
  freezing in these fixtures.
- **Non-deterministic content**: The stdout and stderr surfaces for these
  fixture cases contain no wall-clock timestamps, PIDs, hostnames, or other
  non-deterministic content. The escalation message format is deterministic
  (the bullet count is fixed by the fixture input).

## Named-tolerance categories

The parity test uses byte-identical comparison for all three fixture cases. No
named tolerances (from `tests/test_parity_contract.py`) are opted in because:

- **stdout** is either empty or a plain fixed-format string
  (`"Escalating to Complex tier — research surfaced 2 open questions\n"`). No
  JSON serialization differences, no timestamps, no locale-dependent text.
- **stderr** is empty for all current cases.
- **exit-code** is always 0 for these fixture paths.

The `error-formatter-shape` tolerance would apply if stderr contained error
messages from path-rejection or IO-error paths, but those cases are exercised
by the behavioral test suite (not the golden-replay parity fixtures).

## How to recapture

If the Python module is modified and fixtures need to be updated, run from the
repo root with:

```bash
LC_ALL=C TZ=UTC python3 -c "
import sys, json, tempfile, os, subprocess
from pathlib import Path

FIXTURE_DIR = Path('tests/fixtures/cortex-complexity-escalator')
# For each case, set up the lifecycle dir, run the module, capture outputs.
# See the parity test source for the exact setup logic.
"
```

Alternatively, run the parity test with `--update-fixtures` if that flag is
added to the test harness in a future task.
