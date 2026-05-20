# cortex-load-parent-epic golden-replay fixtures

This directory holds captured outputs of `bin/cortex-load-parent-epic` (the
original PEP 723 script) used by the parity test that guards its wheel-tier
Python port (`cortex_command.backlog.load_parent_epic`).

Each test case is stored as five flat sibling files:

```
<case>.argv      one argv element per line (line 1 is argv[1] of the script)
<case>.stdin     literal bytes piped to stdin (empty for all current cases)
<case>.stdout    literal bytes captured from stdout
<case>.stderr    literal bytes captured from stderr
<case>.exitcode  the exit status as a single decimal integer + trailing newline
```

## Cases captured

| Case              | Scenario                                            | Child slug                                          | Parent | Status     | Exit | stdout JSON?     |
|-------------------|-----------------------------------------------------|-----------------------------------------------------|--------|------------|------|------------------|
| `valid_parent`    | Child with a valid epic parent; body extracted      | `004-prep-hooks-and-apikey-for-sharing`             | 003    | `loaded`   | 0    | yes              |
| `no_parent`       | Child has no `parent:` field; silent exit 0         | `001-fix-overnight-watchdog-to-kill-entire-process-group-on-stall` | — | `no_parent` | 0 | yes (status only)|
| `broken_parent`   | Parent file has malformed YAML frontmatter; exit 1  | `100-child-item` (synthetic)                        | 999    | `unreadable` | 1  | yes (status+reason)|

### Status branches covered

The script's closed-set status contract is:
`{no_parent, missing, non_epic, loaded, unreadable}`.

These three fixtures cover the three operationally significant branches:

- **`loaded`** — parent is a valid epic; body + title extracted and JSON-emitted on stdout. exit 0.
- **`no_parent`** — child has no `parent:` field (or field is null / UUID-shaped). exit 0.
- **`unreadable`** — parent file's YAML frontmatter is malformed. JSON with `reason` on stdout. exit 1.

The remaining branches (`missing`, `non_epic`) are exercised by the parity test's
parametric edge-case suite using synthetic backlog fixtures (via `tmp_path`), not
pre-deletion golden-replay targets.

### Backlog context

`valid_parent` and `no_parent` use the live backlog under `cortex/backlog/`:

- **Item 004** (`004-prep-hooks-and-apikey-for-sharing.md`): `parent: 003`; parent
  item 003 (`003-shareable-install-epic.md`) has `type: epic`. The `## Context`
  section of the epic body is extracted and token-capped.
- **Item 001** (`001-fix-overnight-watchdog-to-kill-entire-process-group-on-stall.md`):
  has no `parent:` field in its frontmatter.

`broken_parent` uses a **synthetic backlog** created by the parity test at runtime
in `tmp_path`. The test creates:

- `tmp_path/backlog/100-child-item.md` — frontmatter with `parent: 999`
- `tmp_path/backlog/999-broken-epic.md` — frontmatter with a YAML mapping collision
  that causes `yaml.safe_load` to raise `yaml.YAMLError`

The parity test points `CORTEX_BACKLOG_DIR` at `tmp_path/backlog` for this case.

## Determinism harness

The fixtures were captured under a controlled environment so the parity test
can replay them deterministically. The Python port must run under the same
environment when compared.

- **jq version**: `jq --version` reported `jq-1.8.1` at capture time. The
  script does not invoke `jq` (it uses Python's `json.dumps`), but jq is
  pinned here to match the harness contract established for sibling fixtures
  (Tasks 2, 9) and to prevent cross-test drift.
- **`LC_ALL=C`**: set during capture; forces byte-deterministic collation.
  The script reads backlog filenames via `sorted(glob(...))`, which Python sorts
  lexicographically; `LC_ALL=C` ensures stable ordering across locales.
- **`TZ=UTC`**: set during capture; the script does not emit timestamps, but
  pinning UTC prevents any future clock-aware extensions from drifting.
- **`CORTEX_BACKLOG_DIR`**: set to the repo's `cortex/backlog/` at capture time
  for `valid_parent` and `no_parent`. The parity test sets this override so the
  Python port resolves against the same backlog snapshot rather than whatever the
  test environment's cwd happens to walk up to. For `broken_parent`, the parity
  test creates a synthetic backlog at `tmp_path/backlog/`.
- **No PIDs, hostnames, or wall-clock timestamps**: the script's stdout and
  stderr are derived from frontmatter content only and never emit non-deterministic
  data. No freeze/filter wrappers are needed.

## Named-tolerance categories the parity test consumes

The parity test imports the `@pytest.mark.structural_equivalence` decorator from
`tests/test_parity_contract.py` and declares an explicit, opt-in tolerance set per
stream.

- **`unicode-escape`** — ASCII-escape form (`\uXXXX`) vs raw UTF-8 byte form.
  The script uses Python's `json.dumps` with default `ensure_ascii=True`, so
  non-ASCII characters (e.g., the em-dash `—` in the epic body) are escaped.
  Either rendering is accepted by the parity test.
- **`trailing-newline`** — presence or absence of a single trailing `\n` on stdout.
  The script uses `print(json.dumps(...))` which appends a newline. Either form
  is accepted.
- **`key-reorder`** — intra-object JSON key reordering. Python `dict` insertion
  order may differ between versions. Either ordering is accepted on stdout for the
  JSON-bearing cases.

`error-formatter-shape` is NOT opted into for this fixture set: the stderr stream
is empty for all three captured cases.

## How to recapture

If the original PEP 723 script is restored and re-captured, run from the repo
root with `LC_ALL=C TZ=UTC` set and `CORTEX_BACKLOG_DIR` pointing to the repo
backlog:

```bash
REPO_ROOT="$(pwd)"
BACKLOG_DIR="${REPO_ROOT}/cortex/backlog"
PYTHON=/Users/charlie.hall/Workspaces/cortex-command/.venv/bin/python3

# valid_parent
LC_ALL=C TZ=UTC CORTEX_BACKLOG_DIR="${BACKLOG_DIR}" PYTHONPATH="${REPO_ROOT}" \
  "${PYTHON}" -m cortex_command.backlog.load_parent_epic \
  004-prep-hooks-and-apikey-for-sharing \
  > tests/fixtures/cortex-load-parent-epic/valid_parent.stdout \
  2> tests/fixtures/cortex-load-parent-epic/valid_parent.stderr
echo $? > tests/fixtures/cortex-load-parent-epic/valid_parent.exitcode

# no_parent
LC_ALL=C TZ=UTC CORTEX_BACKLOG_DIR="${BACKLOG_DIR}" PYTHONPATH="${REPO_ROOT}" \
  "${PYTHON}" -m cortex_command.backlog.load_parent_epic \
  001-fix-overnight-watchdog-to-kill-entire-process-group-on-stall \
  > tests/fixtures/cortex-load-parent-epic/no_parent.stdout \
  2> tests/fixtures/cortex-load-parent-epic/no_parent.stderr
echo $? > tests/fixtures/cortex-load-parent-epic/no_parent.exitcode

# broken_parent: set up synthetic backlog first, then run
TMPDIR_SYNTH="$(mktemp -d)"
mkdir -p "${TMPDIR_SYNTH}"
cat > "${TMPDIR_SYNTH}/100-child-item.md" <<'CHILD'
---
id: 100
title: "Child item"
type: chore
status: active
parent: 999
---
CHILD
printf -- "---\nid: 999\ntitle: broken\ntype: epic\nbad: :\n  - broken: yaml\n    :\n---\n" \
  > "${TMPDIR_SYNTH}/999-broken-epic.md"

LC_ALL=C TZ=UTC CORTEX_BACKLOG_DIR="${TMPDIR_SYNTH}" PYTHONPATH="${REPO_ROOT}" \
  "${PYTHON}" -m cortex_command.backlog.load_parent_epic \
  100-child-item \
  > tests/fixtures/cortex-load-parent-epic/broken_parent.stdout \
  2> tests/fixtures/cortex-load-parent-epic/broken_parent.stderr
echo $? > tests/fixtures/cortex-load-parent-epic/broken_parent.exitcode
rm -rf "${TMPDIR_SYNTH}"
```

Note: `jq --version` must report `jq-1.8.1` and `LC_ALL=C`, `TZ=UTC` must be set
in the capture environment to satisfy the determinism contract above.
