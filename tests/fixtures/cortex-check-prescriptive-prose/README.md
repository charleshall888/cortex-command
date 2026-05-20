# cortex-check-prescriptive-prose golden-replay fixtures

This directory holds the pre-promotion capture of `bin/cortex-check-prescriptive-prose`
(Python script, 409 lines) for the parity test that guards its wheel-tier Python port
(`cortex_command.lint.prescriptive_prose`).

Each test case is stored as five flat sibling files plus a companion `.md` fixture document:

```
<case>.argv      one argv element per line (line 1 is argv[1] of the script)
<case>.stdin     literal bytes piped to stdin (empty for all current cases)
<case>.stdout    literal bytes captured from stdout
<case>.stderr    literal bytes captured from stderr
<case>.exitcode  the exit status as a single decimal integer + trailing newline
<case>.md        the markdown file that is scanned (passed as the positional file arg)
```

The `.argv` files contain the repo-relative path to the companion `.md` file
(e.g., `tests/fixtures/cortex-check-prescriptive-prose/with_violations.md`).
The parity test invokes the module with `cwd=REPO_ROOT` so these relative paths
resolve correctly and the output paths in stderr are stable repo-relative strings.

## Cases captured

| Case                 | Scenario                                                   | Violations? | Exit |
|----------------------|------------------------------------------------------------|-------------|------|
| `clean`              | No LEX-1 violations in any forbidden section               | no          | 0    |
| `with_violations`    | path:line and section-index hits in ## Why, ## Role, ## Edges | yes      | 1    |
| `with_fenced_block`  | Multi-line fenced code block (≥2 non-empty lines) in ## Why | yes        | 1    |

### Exit-code surface

The scanner's exit-code contract is:

- **0** — No violations found.
- **1** — One or more LEX-1 violations found; violation lines on stderr.
- **2** — No mode selected (no `--staged` and no positional file arg).

### Violation output format

Each violation is emitted to stderr in the form:

```
<path>:<line>: PRESCRIPTIVE_PROSE section=<section> pattern=<pattern> -- <snippet>
```

Where `<pattern>` is one of:
- `path:line` — a file path with a line-number citation (e.g., `skills/foo.md:42`)
- `section-index` — a `§N` or `RN` section-index reference (e.g., `§3`, `R2`)
- `quoted-prose-patch` — a multi-line fenced code block (≥2 non-empty lines)

## Fixture details

### `clean`

A well-formed markdown file with narrative-only content in all forbidden sections
(`## Why`, `## Role`, `## Integration`, `## Edges`). The `## Touch points` section
contains path:line and section-index tokens to confirm they are not flagged there.

### `with_violations`

Contains:
- A `path:line` reference in `## Why` (line 8): `skills/some-skill/SKILL.md:42`
- A `section-index` reference in `## Why` (line 9): `R3`
- A `section-index` reference in `## Role` (line 13): `§2`
- A `path:line` range reference in `## Edges` (line 21): `docs/spec.md:10-15`

### `with_fenced_block`

Contains a multi-line fenced Python code block (```` ```python ... ``` ````)
in `## Why` with 2 non-empty content lines, triggering the Pattern 3
`quoted-prose-patch` violation.

## Determinism harness

The fixtures were captured by running the original Python module directly with
the companion `.md` files as positional arguments, invoked from the repo root.
The Python port must produce identical output.

- **jq version**: `jq --version` reported `jq-1.8.1` at capture time. The
  script itself does not invoke `jq` (it uses Python's regex scanner), but jq
  is pinned here to match the harness contract established for sibling fixtures.
- **`LC_ALL=C`**: set during capture; forces byte-deterministic collation.
- **`TZ=UTC`**: set during capture; the script does not emit timestamps, but
  pinning UTC prevents any future clock-aware extensions from drifting.
- **No PIDs, hostnames, or wall-clock timestamps**: the scanner's output is
  purely derived from file content (line numbers, section names, snippet text)
  and never emits non-deterministic data.
- **Path determinism**: the `.argv` files contain repo-relative paths. The
  parity test invokes with `cwd=REPO_ROOT` so the paths and their counterparts
  in stderr output are stable across environments.

## Named-tolerance categories the parity test consumes

The parity test imports `assert_byte_identical` from `tests/test_parity_contract.py`
(Task 5). For this fixture set:

- **stdout**: always empty; byte-identical comparison applies.
- **stderr**: violation lines are plain text (no JSON). Byte-identical comparison
  applies; the stable repo-relative paths eliminate any env-dependency.

`unicode-escape`, `number-format`, `key-reorder`, `trailing-newline`, and
`error-formatter-shape` structural-equivalence tolerances are NOT opted into for
this fixture set: the scanner never emits JSON output and the stderr content is
fully deterministic.

## How to recapture

If the original Python module is restored and re-captured, run from the repo root with:

```bash
LC_ALL=C TZ=UTC python3 -m cortex_command.lint.prescriptive_prose \
  tests/fixtures/cortex-check-prescriptive-prose/clean.md \
  > tests/fixtures/cortex-check-prescriptive-prose/clean.stdout \
  2> tests/fixtures/cortex-check-prescriptive-prose/clean.stderr
echo $? > tests/fixtures/cortex-check-prescriptive-prose/clean.exitcode

LC_ALL=C TZ=UTC python3 -m cortex_command.lint.prescriptive_prose \
  tests/fixtures/cortex-check-prescriptive-prose/with_violations.md \
  > tests/fixtures/cortex-check-prescriptive-prose/with_violations.stdout \
  2> tests/fixtures/cortex-check-prescriptive-prose/with_violations.stderr
echo $? > tests/fixtures/cortex-check-prescriptive-prose/with_violations.exitcode

LC_ALL=C TZ=UTC python3 -m cortex_command.lint.prescriptive_prose \
  tests/fixtures/cortex-check-prescriptive-prose/with_fenced_block.md \
  > tests/fixtures/cortex-check-prescriptive-prose/with_fenced_block.stdout \
  2> tests/fixtures/cortex-check-prescriptive-prose/with_fenced_block.stderr
echo $? > tests/fixtures/cortex-check-prescriptive-prose/with_fenced_block.exitcode
```
