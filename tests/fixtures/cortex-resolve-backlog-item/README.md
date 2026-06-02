# cortex-resolve-backlog-item golden-replay fixtures

This directory holds the pre-deletion capture of `bin/cortex-resolve-backlog-item`
(Python/uv script) for the parity test that guards its wheel-tier Python port
(`cortex_command.backlog.resolve_item`).

Each test case is stored as flat sibling files (the byte-exact `no_match` case
carries the full five; the two structurally-asserted cases omit their de-pinned
snapshot — see "Structural assertions" below):

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
| `numeric_unambiguous`     | Numeric ID with exactly one match                | `252`            | 0    | yes (shape asserted) | no               |
| `title_phrase_ambiguous`  | Title-phrase with more than one match            | `lifecycle`      | 2    | no              | yes (count read live) |
| `no_match`                | Input that matches zero items across all strategies | `nonexistent-item-xyz-123` | 3 | no        | no (stderr message)   |

**Structural assertions (two cases):** `title_phrase_ambiguous` (stderr) and
`numeric_unambiguous` (stdout) embed live backlog data — the ambiguous match
count plus candidate listing, and item 252's live title — so the parity test
asserts their **format/shape** against live resolver output rather than
byte-comparing a pinned snapshot. Their de-pinned snapshot files were deleted
(the ambiguous case's stderr and the numeric case's stdout); the remaining
sibling files keep the cases discovered. This kills the recurring `just test`
failures that fired whenever a "lifecycle"-titled item was added or removed, or
item 252 was retitled. `no_match` stays fully byte-exact.

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

Only `no_match` carries a backlog-content-independent byte snapshot (its stderr
echoes the input argument). The two structurally-asserted cases read the **live**
`cortex/backlog/` at test time, so they have no pinned backlog snapshot and do
not drift as the backlog grows. The numeric case targets item 252
(`installation-integrity-layer-bash-to-entry`) because it carries a
`lifecycle_slug` frontmatter field that exercises the slug-resolution priority
chain (frontmatter wins over title-slugify derivation); the parity test pins the
`252-` id prefix and JSON key set, not the live title text.

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

> **Historical.** These named tolerance categories applied to the numeric case's
> JSON stdout while it was byte-snapshotted. That stdout is now asserted by JSON
> *shape* (`_assert_numeric_stdout_structure`), which is inherently
> reorder-/escape-/newline-agnostic, so no tolerance category is opted in for any
> current case. The descriptions below are retained as background.

The parity test historically imported a structural-equivalence helper from
`tests/test_parity_contract.py` and declared an explicit, opt-in tolerance set
per stream. The relevant named categories were:

- **`unicode-escape`** — ASCII-escape form (`\uXXXX`) vs raw UTF-8 byte form.
  The current script uses Python's `json.dumps` with default `ensure_ascii=True`,
  so non-ASCII title characters are escaped. The wheel-tier port must preserve
  this behavior. Either rendering is accepted on JSON stdout by the parity test,
  but the fixture captures the `ensure_ascii=True` form.
- **`trailing-newline`** — presence or absence of a single trailing `\n` on
  stdout. The script uses `print(json.dumps(...))` which appends a newline;
  the numeric case's captured stdout ended with `\n`. Either form was accepted
  by the parity test's tolerance layer.
- **`key-reorder`** — intra-object JSON key reordering. The bash-era script
  (replaced by this Python script at an earlier phase) used `json.dumps` with
  dict insertion order; the wheel-tier port's `dict` insertion order may
  differ. The structural-equivalence decorator is applied to the stdout stream
  for `numeric_unambiguous` so that key-reordered JSON is accepted without a
  parity failure.

`error-formatter-shape` is NOT opted into for this fixture set. `no_match`'s
stderr (`no match for '<input>'`) echoes only the input argument, is independent
of backlog content, and is reproduced byte-for-byte. The ambiguous case's stderr
(`_format_candidates`) embeds the live match count and listing, so it is asserted
**structurally** against live output (`_assert_ambiguous_stderr_structure`), not
byte-compared. Likewise the numeric case's stdout is asserted by JSON shape
(`_assert_numeric_stdout_structure`: key set + `252-` id prefix), so the
`key-reorder` / `unicode-escape` / `trailing-newline` categories listed above no
longer apply to it — they are retained as historical context from the
byte-snapshot era.

## How to recapture

**Do NOT regenerate the de-pinned snapshots.** The two structurally-asserted
streams (the ambiguous case's stderr and the numeric case's stdout) were deleted
as drift sources and the test asserts the live format instead — re-capturing them
would silently resurrect the drift the structural assertions exist to prevent.
The recipe below regenerates only the byte-exact / stable streams.

If the script is restored from history and re-captured, run from the
repo root with:

```bash
# no_match — the only fully byte-exact case
LC_ALL=C TZ=UTC CORTEX_BACKLOG_DIR="$(pwd)/cortex/backlog" cortex-resolve-backlog-item nonexistent-item-xyz-123 \
  > tests/fixtures/cortex-resolve-backlog-item/no_match.stdout \
  2> tests/fixtures/cortex-resolve-backlog-item/no_match.stderr
echo $? > tests/fixtures/cortex-resolve-backlog-item/no_match.exitcode

# numeric — regenerate only the (empty) stderr + exit code; stdout is asserted structurally, not snapshotted
LC_ALL=C TZ=UTC CORTEX_BACKLOG_DIR="$(pwd)/cortex/backlog" cortex-resolve-backlog-item 252 \
  > /dev/null \
  2> tests/fixtures/cortex-resolve-backlog-item/numeric_unambiguous.stderr
echo $? > tests/fixtures/cortex-resolve-backlog-item/numeric_unambiguous.exitcode

# title_phrase_ambiguous — regenerate only the exit code; stderr is asserted structurally, not snapshotted
LC_ALL=C TZ=UTC CORTEX_BACKLOG_DIR="$(pwd)/cortex/backlog" cortex-resolve-backlog-item lifecycle \
  > /dev/null 2> /dev/null
echo $? > tests/fixtures/cortex-resolve-backlog-item/title_phrase_ambiguous.exitcode
```

Note: `LC_ALL=C`, `TZ=UTC`, and `CORTEX_BACKLOG_DIR` must be set in the capture
environment to satisfy the determinism contract above.
