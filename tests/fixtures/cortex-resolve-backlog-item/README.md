# cortex-resolve-backlog-item golden-replay fixtures

This directory holds the pre-deletion capture of `bin/cortex-resolve-backlog-item`
(Python/uv script) for the parity test that guards its wheel-tier Python port
(`cortex_command.backlog.resolve_item`).

Each test case is stored as five flat sibling files:

```
<case>.argv      one argv element per line (line 1 is argv[1] of the script)
<case>.stdin     literal bytes piped to stdin (empty for all current cases)
<case>.stdout    literal bytes captured from stdout
<case>.stderr    literal bytes captured from stderr
<case>.exitcode  the exit status as a single decimal integer + trailing newline
```

## Cases captured

| Case                      | Scenario                                         | Input            | Exit | JSON on stdout? | Candidates on stderr? |
|---------------------------|--------------------------------------------------|------------------|------|-----------------|-----------------------|
| `numeric_unambiguous`     | Numeric ID with exactly one match                | `252`            | 0    | yes             | no                    |
| `title_phrase_ambiguous`  | Title-phrase with more than one match            | `lifecycle`      | 2    | no              | yes (31 matches)      |
| `no_match`                | Input that matches zero items across all strategies | `nonexistent-item-xyz-123` | 3 | no        | no (stderr message)   |

### Exit-code surface

The script's closed-set exit-code contract is `{0, 2, 3, 64, 70}`. These three
fixtures cover the three operationally-common values:

- **0** — Unambiguous match; JSON object on stdout.
- **2** — Ambiguous match; candidate list on stderr.
- **3** — No match; single-line diagnostic on stderr.

The remaining values (64 = usage error, 70 = software/IO error) are
exercised by the parity test's edge-case suite and are not pre-deletion
golden-replay targets.

### Backlog snapshot

Fixtures were generated against the backlog state at HEAD at capture time
(256 items, `cortex/backlog/001-*.md` through `cortex/backlog/259-*.md`).
The numeric fixture uses item 252 (`installation-integrity-layer-bash-to-entry`)
because that item has a `lifecycle_slug` frontmatter field that exercises the
slug-resolution priority chain (frontmatter wins over title-slugify derivation).

## Determinism harness

The fixtures were captured under a controlled environment so the parity test
can replay them deterministically. The Python port must run under the same
environment when compared.

- **jq version**: `jq --version` reported `jq-1.8.1` at capture time. The
  script itself does not invoke `jq` (it uses Python's `json.dumps`), but jq
  is pinned here to match the harness contract established for sibling fixtures
  (Tasks 2, 11–21) and to prevent cross-test drift if downstream test helpers
  shell out to `jq` for comparison or pretty-printing.
- **`LC_ALL=C`**: set during capture; forces byte-deterministic collation in
  any subprocesses. The script reads backlog filenames via `sorted(glob(...))`,
  which Python sorts lexicographically; `LC_ALL=C` ensures the glob ordering
  is stable across locales.
- **`TZ=UTC`**: set during capture; the script does not emit timestamps, but
  pinning UTC prevents any future clock-aware extensions from drifting.
- **`CORTEX_BACKLOG_DIR`**: set to the repo's `cortex/backlog/` at capture
  time. The parity test must set this override so the Python port resolves
  against the same fixture-pinned backlog snapshot rather than whatever backlog
  the test environment's cwd happens to walk up to.
- **No PIDs, hostnames, or wall-clock timestamps**: the script's stdout and
  stderr are purely derived from backlog frontmatter content and never emit
  non-deterministic data. No freeze/filter wrappers are needed.

## Named-tolerance categories the parity test consumes

The parity test (Task 9) imports the `@pytest.mark.structural_equivalence`
decorator from `tests/test_parity_contract.py` (Task 5) and declares an
explicit, opt-in tolerance set per stream. For this fixture set the relevant
named categories are:

- **`unicode-escape`** — ASCII-escape form (`\uXXXX`) vs raw UTF-8 byte form.
  The current script uses Python's `json.dumps` with default `ensure_ascii=True`,
  so non-ASCII title characters are escaped. The wheel-tier port must preserve
  this behavior. Either rendering is accepted on JSON stdout by the parity test,
  but the fixture captures the `ensure_ascii=True` form.
- **`trailing-newline`** — presence or absence of a single trailing `\n` on
  stdout. The script uses `print(json.dumps(...))` which appends a newline;
  the fixture's `numeric_unambiguous.stdout` ends with `\n`. Either form is
  accepted by the parity test's tolerance layer, but the fixture records the
  canonical output.
- **`key-reorder`** — intra-object JSON key reordering. The bash-era script
  (replaced by this Python script at an earlier phase) used `json.dumps` with
  dict insertion order; the wheel-tier port's `dict` insertion order may
  differ. The structural-equivalence decorator is applied to the stdout stream
  for `numeric_unambiguous` so that key-reordered JSON is accepted without a
  parity failure.

`error-formatter-shape` is NOT opted into for this fixture set: the stderr
messages in cases 2 and 3 are fixed-format strings from the script's
`_format_candidates` and `"no match for ..."` branches. The wheel-tier port
must reproduce these byte-for-byte (subject to `trailing-newline` tolerance).

## How to recapture

If the script is restored from history and re-captured, run from the
repo root with:

```bash
LC_ALL=C TZ=UTC CORTEX_BACKLOG_DIR="$(pwd)/cortex/backlog" uv run --script bin/cortex-resolve-backlog-item 252 \
  > tests/fixtures/cortex-resolve-backlog-item/numeric_unambiguous.stdout \
  2> tests/fixtures/cortex-resolve-backlog-item/numeric_unambiguous.stderr
echo $? > tests/fixtures/cortex-resolve-backlog-item/numeric_unambiguous.exitcode

LC_ALL=C TZ=UTC CORTEX_BACKLOG_DIR="$(pwd)/cortex/backlog" uv run --script bin/cortex-resolve-backlog-item lifecycle \
  > tests/fixtures/cortex-resolve-backlog-item/title_phrase_ambiguous.stdout \
  2> tests/fixtures/cortex-resolve-backlog-item/title_phrase_ambiguous.stderr
echo $? > tests/fixtures/cortex-resolve-backlog-item/title_phrase_ambiguous.exitcode

LC_ALL=C TZ=UTC CORTEX_BACKLOG_DIR="$(pwd)/cortex/backlog" uv run --script bin/cortex-resolve-backlog-item nonexistent-item-xyz-123 \
  > tests/fixtures/cortex-resolve-backlog-item/no_match.stdout \
  2> tests/fixtures/cortex-resolve-backlog-item/no_match.stderr
echo $? > tests/fixtures/cortex-resolve-backlog-item/no_match.exitcode
```

Note: `jq --version` must report `jq-1.8.1` and `LC_ALL=C`, `TZ=UTC` must be
set in the capture environment to satisfy the determinism contract above.
