# cortex-auto-bump-version golden-replay fixtures

This directory holds the pre-deletion capture of `bin/cortex-auto-bump-version`
(Python script, 220 lines) for the parity test that guards its Python module port
(`cortex_command.auto_bump_version`).

Each test case is stored as five flat sibling files:

```
<case>.argv      one argv element per line (line 1 is sys.argv[0] of the script)
<case>.stdin     literal bytes piped to stdin (empty for all current cases)
<case>.stdout    literal bytes captured from stdout
<case>.stderr    literal bytes captured from stderr
<case>.exitcode  the exit status as a single decimal integer + trailing newline
```

The script is deterministic given a git repository state: it emits `no-bump\n`
when HEAD equals the latest tag, `vX.Y.Z\n` for a computed bump, or `v0.1.0\n`
as the default when no tags exist. All cases exit 0. stderr is empty for all
cases.

## Cases captured

| Case                  | Scenario                                           | Expected stdout |
|-----------------------|----------------------------------------------------|-----------------|
| `no_bump`             | HEAD == latest tag → no new commits since tag      | `no-bump\n`     |
| `patch_bump`          | Two commits since tag, no markers → patch bump     | `v1.2.4\n`      |
| `minor_bump`          | Commit with `[release-type: minor]` body → minor   | `v1.3.0\n`      |
| `major_bump_breaking` | Commit with `BREAKING:` footer → major bump        | `v2.0.0\n`      |
| `no_tags_default`     | No tags in repo, one commit → DEFAULT_TAG          | `v0.1.0\n`      |
| `patch_bump_dry_run`  | `--dry-run` flag: same output as plain invocation  | `v2.0.1\n`      |

Cases cross-cut all five distinguishable code paths in the script (no-bump,
patch, minor, major via BREAKING fallback, no-tags) plus the dry-run flag.

## Determinism harness

Fixtures were captured against synthetic git repositories created in temporary
directories, so no external state affects the output. The following controls
were applied:

- **`LC_ALL=C`**: forces byte-deterministic collation and number formatting.
- **`TZ=UTC`**: pins any clock-dependent behavior (the script itself does not
  emit timestamps, but the control is applied for consistency with the
  shared fixture harness convention).
- **`GIT_CONFIG_GLOBAL=/dev/null` and `GIT_CONFIG_SYSTEM=/dev/null`**: prevent
  user-level or system-level git config (signing, hooks) from interfering.
- **Commit signing disabled**: `commit.gpgsign=false` and `tag.gpgsign=false`
  set in each synthetic repo.
- **Synthetic git repo with `pyproject.toml`**: each fixture uses a fresh
  `tmp_path` repo; the `CORTEX_COMMAND_FORCE_SOURCE=1` env var (with
  `CORTEX_COMMAND_ROOT` pointing at the real worktree) was used at capture
  time to invoke the module directly via working-tree Python, bypassing any
  installed wheel.

## Named-tolerance categories the parity test consumes

The parity test (`tests/test_cortex_auto_bump_version_parity.py`) uses the
`@pytest.mark.structural_equivalence` decorator from `tests/test_parity_contract.py`
and declares an explicit, opt-in tolerance set per stream. For this fixture set:

- **`trailing-newline`** — presence or absence of a single trailing `\n` on
  stdout/stderr. The script always emits a trailing newline; the Python module
  does the same via `sys.stdout.write("...\n")`. Either form is accepted.
- **`unicode-escape`** — ASCII-escape form (`\uXXXX`) vs raw UTF-8 byte form.
  The script output contains only ASCII; this tolerance is declared for
  forward-compatibility in case non-ASCII branch names are introduced.

`error-formatter-shape` and `number-format` are NOT opted into: the script
emits plain text (`no-bump` or `vX.Y.Z`), not JSON. `key-reorder` does not
apply for the same reason.

## jq version

The script does not invoke `jq` (it emits plain text, not JSONL). For
consistency with the shared fixture harness convention, the `jq` version
at capture time was `jq-1.8.1`.

## How to recapture

If the module is modified and the fixtures need to be regenerated, run from
a clean worktree with `CORTEX_COMMAND_FORCE_SOURCE=1`:

```bash
LC_ALL=C TZ=UTC python3 << 'EOF'
# For each case, create a synthetic git repo, populate commits/tags,
# then:
#   CORTEX_COMMAND_FORCE_SOURCE=1 CORTEX_COMMAND_ROOT=$(pwd) \
#     bin/cortex-auto-bump-version [args] \
#     > tests/fixtures/cortex-auto-bump-version/<case>.stdout \
#     2> tests/fixtures/cortex-auto-bump-version/<case>.stderr
#   echo $? > tests/fixtures/cortex-auto-bump-version/<case>.exitcode
EOF
```
