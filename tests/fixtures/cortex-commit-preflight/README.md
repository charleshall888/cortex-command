# cortex-commit-preflight golden-replay fixtures

This directory holds the pre-promotion capture of `bin/cortex-commit-preflight`
(Python `#!/usr/bin/env python3` script) for the parity test that guards its
wheel-tier Python port (`cortex_command.commit.preflight`).

Each test case is stored as five flat sibling files:

```
<case>.argv      one argv element per line (empty for all current cases: no flags)
<case>.stdin     literal bytes piped to stdin (empty for all current cases)
<case>.stdout    literal bytes captured from stdout
<case>.stderr    literal bytes captured from stderr
<case>.exitcode  the exit status as a single decimal integer + trailing newline
```

## Cases captured

| Case             | Scenario                                        | Exit | JSON on stdout? | Notes field        |
|------------------|-------------------------------------------------|------|-----------------|--------------------|
| `valid_git_repo` | Valid git repo with one commit, clean state     | 0    | yes             | `[]`               |
| `empty_repo`     | Fresh `git init` with no commits yet            | 0    | yes             | `["empty_repo"]`   |
| `not_in_repo`    | CWD is outside any git repository               | 2    | no              | N/A (stderr only)  |

### Exit-code surface

The script's closed-set exit-code contract is `{0, 2, 3, 5}`. These three
fixtures cover:

- **0** — Success: JSON envelope on stdout with `status`, `diff`, `recent_log`, `notes`.
  The `valid_git_repo` case demonstrates a non-empty `recent_log`; the `empty_repo`
  case demonstrates `notes=["empty_repo"]` with empty `diff` and `recent_log`.
- **2** — Not inside a git repository: `"not inside a git repository\n"` on stderr.

The remaining values (3 = bare repo, 5 = partial git failure) are tested by the
parity test's edge-case suite and are not pre-deletion golden-replay targets.

## Determinism harness

The fixtures were captured under a controlled environment so the parity test
can replay them deterministically. The Python port must run under the same
environment when compared.

- **jq version**: `jq --version` reported `jq-1.8.1` at capture time. The
  script itself does not invoke `jq` (it uses Python's `json.dumps`), but jq
  is pinned here to match the harness contract established for sibling fixtures.
- **`LC_ALL=C`**: set during capture; forces byte-deterministic collation in
  any subprocesses. The script invokes git subprocesses; `LC_ALL=C.UTF-8`
  is set in the hardened git environment.
- **`TZ=UTC`**: set during capture; the script does not emit timestamps, but
  pinning UTC prevents any future clock-aware extensions from drifting.
- **No PIDs, hostnames, or wall-clock timestamps**: the script's stdout and
  stderr are purely derived from git output and never emit non-deterministic
  host-level data.
- **Deterministic git environment for `valid_git_repo`**: commit hash
  determinism requires GPG signing disabled (`commit.gpgsign false`) and
  fixed author/committer metadata. The parity test recreates the exact same
  git state using these parameters:
  - Branch: `main` (forced via `git checkout -b main`)
  - File: `hello.txt` with content `hello world\n`
  - Commit message: `Initial commit`
  - Author/committer: `Test <test@example.com>`
  - Author/committer date: `2024-01-15T10:00:00+0000`
  - GPG signing: disabled (`git config commit.gpgsign false`)
  The resulting commit hash is `2a9110f` (abbreviated form in `git log --oneline`).
- **Deterministic git environment for `empty_repo`**: fresh `git init` with
  branch renamed to `main` via `git checkout -b main`. No commits, so
  `git status` output is fixed ("No commits yet") and HEAD does not exist.
  The `notes` field contains `["empty_repo"]` in this case.
- **`not_in_repo` case**: CWD is a plain directory with no `.git` anywhere in
  the ancestor chain. Output is fully deterministic: empty stdout, fixed
  stderr line `"not inside a git repository\n"`, exit code 2.

## Named-tolerance categories the parity test consumes

The parity test imports the `@pytest.mark.structural_equivalence` decorator from
`tests/test_parity_contract.py` and declares an explicit, opt-in tolerance set
per stream. For this fixture set:

- **`key-reorder`** — intra-object JSON key reordering. The captured fixture
  records a specific key order (`status`, `diff`, `recent_log`, `notes`).
  The Python port uses `json.dumps` with default dict insertion order, which
  matches. Either ordering is accepted via structural equivalence.
- **`trailing-newline`** — presence or absence of a single trailing `\n` on
  stdout. The fixture captures the `json.dumps(...) + "\n"` form; either form
  is accepted.

`error-formatter-shape` is NOT opted into for the stderr stream: the
`not_in_repo` stderr message is a fixed string that the Python port must
reproduce byte-for-byte.

## How to recapture

If the module is modified and fixtures need refreshing, run from the repo root:

```bash
# Create a controlled git repo for valid_git_repo case
CAPTURE_DIR=$(mktemp -d)
cd "$CAPTURE_DIR"
git init -q
git config user.email "test@example.com"
git config user.name "Test"
git config commit.gpgsign false
git checkout -q -b main
printf 'hello world\n' > hello.txt
git add hello.txt
GIT_AUTHOR_DATE="2024-01-15T10:00:00+0000" \
GIT_COMMITTER_DATE="2024-01-15T10:00:00+0000" \
GIT_AUTHOR_NAME="Test" GIT_AUTHOR_EMAIL="test@example.com" \
GIT_COMMITTER_NAME="Test" GIT_COMMITTER_EMAIL="test@example.com" \
  git commit -q -m "Initial commit"
LC_ALL=C TZ=UTC python3 -m cortex_command.commit.preflight \
  > <repo>/tests/fixtures/cortex-commit-preflight/valid_git_repo.stdout \
  2> <repo>/tests/fixtures/cortex-commit-preflight/valid_git_repo.stderr
echo $? > <repo>/tests/fixtures/cortex-commit-preflight/valid_git_repo.exitcode

# Create a fresh empty repo for empty_repo case
EMPTY_DIR=$(mktemp -d)
cd "$EMPTY_DIR"
git init -q
git config commit.gpgsign false
git checkout -q -b main
LC_ALL=C TZ=UTC python3 -m cortex_command.commit.preflight \
  > <repo>/tests/fixtures/cortex-commit-preflight/empty_repo.stdout \
  2> <repo>/tests/fixtures/cortex-commit-preflight/empty_repo.stderr
echo $? > <repo>/tests/fixtures/cortex-commit-preflight/empty_repo.exitcode

# Capture not_in_repo case from a plain directory
PLAIN_DIR=$(mktemp -d)
cd "$PLAIN_DIR"
LC_ALL=C TZ=UTC python3 -m cortex_command.commit.preflight \
  > <repo>/tests/fixtures/cortex-commit-preflight/not_in_repo.stdout \
  2> <repo>/tests/fixtures/cortex-commit-preflight/not_in_repo.stderr
echo $? > <repo>/tests/fixtures/cortex-commit-preflight/not_in_repo.exitcode
```

Note: `jq --version` must report `jq-1.8.1` and `LC_ALL=C`, `TZ=UTC` must be
set in the capture environment to satisfy the determinism contract above.
