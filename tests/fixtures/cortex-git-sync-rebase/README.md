# cortex-git-sync-rebase fixtures

Fixture set for `tests/test_cortex_git_sync_rebase_parity.py`. Each case has
five files: `<case>.argv`, `<case>.stdin`, `<case>.stdout`, `<case>.stderr`,
`<case>.exitcode`.

## Determinism harness

- jq version: N/A (no jq output produced by this script)
- LC_ALL=C set during capture: yes
- TZ=UTC set during capture: yes
- Determinism notes: All fixtures are authored against synthetic git repos
  constructed in `tmp_path` by the parity test itself. The stderr contains
  `[git-sync-rebase]` log lines; path-variable content (allowlist file
  paths, tmp_path locations) is excluded from byte-identical comparison
  — the parity test uses `error-formatter-shape` tolerance for stderr and
  asserts structural properties (prefix present, exit code correct) rather
  than byte-identical stderr content. stdout is always empty (all output
  goes to stderr); stdout comparison is byte-identical.

## Cases

| Case | Description | Exit code |
|------|-------------|-----------|
| `noop` | HEAD already up to date with origin/main — fetch succeeds, zero commits behind, nothing to rebase | 0 |
| `clean_rebase` | One commit behind origin/main — `git pull --rebase` completes without conflicts, push succeeds | 0 |
| `conflict_non_allowlist` | One commit behind, rebase produces a conflict on a file not in the allowlist — rebase aborted | 1 |

## Fixture file format

- `.argv` — one argument per line (argv[1..]) passed to the module's `main()`. Empty = no args (uses default allowlist path).
- `.stdin` — raw bytes sent to stdin. Always empty for this script.
- `.stdout` — expected stdout bytes. Always empty; the script writes only to stderr.
- `.stderr` — reference stderr content used for structural assertions (not byte-identical).
- `.exitcode` — decimal exit status followed by a newline.
