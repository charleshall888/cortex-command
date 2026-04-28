"""Unit tests for ``bin/cortex-commit-preflight``.

Covers the preflight probe used by ``/cortex-interactive:commit`` Step 1.
The script runs three deterministic git probes and emits a single-line
JSON envelope on stdout. See spec.md R14 and plan.md Task 6 for the
contract.

Cases covered:
  - Normal repo: emits valid JSON with the four-key schema, ``notes==[]``.
  - Bare repo: exits 3 with ``"bare"`` in stderr.
  - Empty repo: exits 0 with ``notes`` containing ``"empty_repo"`` and
    ``diff``/``recent_log`` empty strings.
  - Binary diff (invalid UTF-8 with no NUL bytes): script's
    ``errors="replace"`` produces ``U+FFFD`` rather than crashing, and
    the diff is NOT git's ``Binary files ... differ`` short-circuit
    output (which would let any decode strategy pass vacuously).
  - DR-7 invocation shim: each run appends exactly one JSONL record
    pinned to the tmp repo's ``lifecycle/sessions/<uuid>/`` directory
    (so the test cannot pollute the cortex-command repo and cannot pass
    vacuously when the shim is broken).
  - Git-env hardening: AST-walks the module to assert every git
    ``subprocess.run``/``check_output``/``Popen`` call uses the hardened
    six-element argv prefix and an ``env=`` keyword whose dict literal
    contains the two required env keys.
"""

from __future__ import annotations

import ast
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "bin" / "cortex-commit-preflight"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git_init_with_identity(repo: Path, *, bare: bool = False) -> None:
    """Initialize a git repo with deterministic user.name/user.email.

    Setting both is required because ``git commit`` will refuse with
    "Please tell me who you are" if the local config is missing.
    """
    if bare:
        subprocess.run(["git", "init", "--bare", str(repo)], check=True, capture_output=True)
        return
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Test User"],
        check=True,
        capture_output=True,
    )
    # Disable any inherited GPG / SSH commit-signing config from the
    # host's ~/.gitconfig so commits in tmp repos don't fail with
    # "gpg failed to sign the data". These are local overrides only.
    subprocess.run(
        ["git", "-C", str(repo), "config", "commit.gpgsign", "false"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "tag.gpgsign", "false"],
        check=True,
        capture_output=True,
    )
    # Ensure a stable default branch name regardless of the host's
    # init.defaultBranch setting.
    subprocess.run(
        ["git", "-C", str(repo), "symbolic-ref", "HEAD", "refs/heads/main"],
        check=True,
        capture_output=True,
    )


def _invoke(repo: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run ``bin/cortex-commit-preflight`` with ``cwd=repo``.

    Captures stdout/stderr as bytes and decodes here so callers can
    assert against text without each test needing to repeat the dance.
    """
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        cwd=str(repo),
        env=full_env,
        capture_output=True,
        check=False,
    )


# ---------------------------------------------------------------------------
# Behavioural tests (subprocess against tmp git repos)
# ---------------------------------------------------------------------------


def test_normal_repo_emits_valid_json(tmp_path: Path) -> None:
    """Normal repo with HEAD + a staged change emits the 4-key envelope."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init_with_identity(repo)

    # Initial commit so HEAD exists.
    seed = repo / "seed.txt"
    seed.write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "seed.txt"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "seed"],
        check=True,
        capture_output=True,
    )

    # Working-tree change so ``git diff HEAD`` has content.
    seed.write_text("seed\nmore\n", encoding="utf-8")

    proc = _invoke(repo)
    assert proc.returncode == 0, (
        f"non-zero exit: {proc.returncode!r}; stderr={proc.stderr!r}"
    )

    payload = json.loads(proc.stdout.decode("utf-8"))
    assert set(payload.keys()) == {"status", "diff", "recent_log", "notes"}
    assert isinstance(payload["status"], str)
    assert isinstance(payload["diff"], str)
    assert isinstance(payload["recent_log"], str)
    assert isinstance(payload["notes"], list)
    assert payload["notes"] == []
    # Sanity: the diff actually saw the working-tree change.
    assert "more" in payload["diff"]


def test_bare_repo_exits_3(tmp_path: Path) -> None:
    """A bare repo (no working tree) exits 3 with 'bare' in stderr."""
    bare = tmp_path / "bare.git"
    _git_init_with_identity(bare, bare=True)

    proc = _invoke(bare)
    assert proc.returncode == 3, (
        f"expected exit 3, got {proc.returncode!r}; stderr={proc.stderr!r}"
    )
    assert "bare" in proc.stderr.decode("utf-8", errors="replace").lower()


def test_empty_repo_emits_empty_repo_note(tmp_path: Path) -> None:
    """A fresh ``git init`` (no commits) emits the empty_repo note."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init_with_identity(repo)
    # Deliberately do NOT make any commit -- HEAD must not resolve.

    proc = _invoke(repo)
    assert proc.returncode == 0, (
        f"non-zero exit: {proc.returncode!r}; stderr={proc.stderr!r}"
    )

    payload = json.loads(proc.stdout.decode("utf-8"))
    assert "empty_repo" in payload["notes"]
    assert payload["diff"] == ""
    assert payload["recent_log"] == ""


def test_binary_diff_no_crash(tmp_path: Path) -> None:
    """Invalid-UTF-8 (no NUL) diff body decodes via ``errors='replace'``.

    Git's binary detection short-circuits on the first NUL byte in the
    first ~8KB and emits ``Binary files X and Y differ`` instead of the
    raw bytes. We deliberately use a NUL-free invalid-UTF-8 sequence
    (``\\xc3\\x28``) so git emits the bytes verbatim in the diff and the
    script's ``errors='replace'`` decode hardening must convert them
    to ``U+FFFD``. Negative assertion on ``"Binary files"`` defends
    against the short-circuit case (which would let any decode strategy
    pass vacuously).
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init_with_identity(repo)

    target = repo / "invalid.txt"
    # First commit a clean placeholder so ``invalid.txt`` is tracked.
    target.write_text("placeholder\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(repo), "add", "invalid.txt"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "placeholder"],
        check=True,
        capture_output=True,
    )

    # Overwrite with invalid-UTF-8 bytes that contain no NUL byte.
    # ``\xc3\x28`` is an invalid continuation byte sequence: ``\xc3``
    # starts a 2-byte UTF-8 sequence but ``\x28`` is not a valid
    # continuation byte.
    target.write_bytes(b"hello \xc3\x28 world\n")

    proc = _invoke(repo)
    assert proc.returncode == 0, (
        f"non-zero exit: {proc.returncode!r}; stderr={proc.stderr!r}"
    )

    payload = json.loads(proc.stdout.decode("utf-8"))
    assert isinstance(payload["diff"], str)
    # Positive: replacement char proves errors='replace' fired on the
    # invalid bytes.
    assert "�" in payload["diff"], (
        "expected U+FFFD replacement char in diff (errors='replace' did not "
        f"fire); diff={payload['diff']!r}"
    )
    # Negative: git did NOT short-circuit to the binary stub. If this
    # appears, the test would pass vacuously regardless of decode
    # behavior.
    assert "Binary files" not in payload["diff"], (
        "git short-circuited to binary-stub; test would pass vacuously. "
        f"diff={payload['diff']!r}"
    )


def test_shim_records_invocation(tmp_path: Path) -> None:
    """DR-7: invocation shim appends one JSONL record per run.

    The JSONL path is pinned to ``<tmp_repo>/lifecycle/sessions/<uuid>/``
    because ``cortex-log-invocation`` resolves ``$repo_root`` from
    ``git rev-parse --show-toplevel`` of the script's CWD. We invoke
    with ``cwd=tmp_repo`` so the shim writes inside the tmp repo, never
    the cortex-command repo.

    Asserts:
      - delta == 1 (exactly one new record this invocation)
      - record's ``script`` field == ``"cortex-commit-preflight"``
    """
    session_id = str(uuid.uuid4())

    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init_with_identity(repo)
    # Initial commit so the script reaches its happy-path (and so the
    # shim's ``git rev-parse --show-toplevel`` succeeds).
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "seed.txt"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "seed"],
        check=True,
        capture_output=True,
    )

    log_path = repo / "lifecycle" / "sessions" / session_id / "bin-invocations.jsonl"

    def _count_records() -> int:
        if not log_path.exists():
            return 0
        return sum(
            1 for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()
        )

    before = _count_records()
    proc = _invoke(repo, env={"LIFECYCLE_SESSION_ID": session_id})
    assert proc.returncode == 0, (
        f"non-zero exit: {proc.returncode!r}; stderr={proc.stderr!r}"
    )
    after = _count_records()

    delta = after - before
    assert delta == 1, (
        f"expected exactly 1 new JSONL record at {log_path}, got delta={delta} "
        f"(before={before}, after={after})"
    )

    # The new record is the last one (append-only file).
    last_line = log_path.read_text(encoding="utf-8").splitlines()[-1]
    record = json.loads(last_line)
    assert record["script"] == "cortex-commit-preflight", (
        f"expected script='cortex-commit-preflight', got {record!r}"
    )


# ---------------------------------------------------------------------------
# AST-level test: every git subprocess call must use the hardened argv
# prefix and an env= keyword whose dict literal contains the required
# keys. This defends against future refactors that bypass ``_run_git``.
# ---------------------------------------------------------------------------


_GIT_PREFIX_EXPECTED = [
    "git",
    "-c",
    "color.ui=never",
    "-c",
    "log.decorate=auto",
    "--no-pager",
]


def _is_subprocess_run_call(node: ast.Call) -> bool:
    """True iff ``node`` is a call to ``subprocess.{run,check_output,Popen}``.

    Matches both attribute-style (``subprocess.run(...)``) and
    name-style (``run(...)``) invocations to be robust against
    ``from subprocess import run`` style imports.
    """
    target_names = {"run", "check_output", "Popen"}
    func = node.func
    if isinstance(func, ast.Attribute):
        return (
            isinstance(func.value, ast.Name)
            and func.value.id == "subprocess"
            and func.attr in target_names
        )
    if isinstance(func, ast.Name):
        return func.id in target_names
    return False


def _list_literal_starts_with_git(node: ast.AST) -> bool:
    """True iff ``node`` is a list literal whose first element is ``"git"``."""
    if not isinstance(node, ast.List):
        return False
    if not node.elts:
        return False
    first = node.elts[0]
    return isinstance(first, ast.Constant) and first.value == "git"


def _list_literal_prefix_strings(node: ast.List, n: int) -> list[str | None]:
    """Return the first ``n`` elements of ``node`` as strings (or ``None``).

    Non-string-constant elements (including a leading ``*args``) become
    ``None`` so the caller can detect mismatches.
    """
    out: list[str | None] = []
    for elt in node.elts[:n]:
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
            out.append(elt.value)
        else:
            out.append(None)
    return out


def _find_env_dict_assignment(tree: ast.Module, name: str) -> ast.Dict | None:
    """Find a module-level ``Assign`` for ``name = {...}`` and return the dict.

    Walks ``Assign`` and ``AugAssign`` nodes. Only returns a dict
    literal; other RHS shapes (calls, comprehensions) yield ``None``.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    if isinstance(node.value, ast.Dict):
                        return node.value
        elif isinstance(node, ast.AugAssign):
            if (
                isinstance(node.target, ast.Name)
                and node.target.id == name
                and isinstance(node.value, ast.Dict)
            ):
                return node.value
    return None


def _dict_literal_keys(d: ast.Dict) -> set[str]:
    """Return string-constant keys from a dict literal."""
    out: set[str] = set()
    for k in d.keys:
        if isinstance(k, ast.Constant) and isinstance(k.value, str):
            out.add(k.value)
    return out


def test_git_env_hardening() -> None:
    """Every git subprocess call uses the hardened argv prefix + env dict.

    Walks the AST of ``bin/cortex-commit-preflight`` and:
      1. Finds every ``subprocess.run``/``check_output``/``Popen`` call
         whose first positional arg is a list literal starting with
         ``"git"``.
      2. Asserts each such call has an ``env=`` keyword AND the argv
         literal begins with the six-element prefix.
      3. For each ``env=NAME`` reference, finds the module-level
         ``NAME = {...}`` dict and asserts it contains both
         ``GIT_OPTIONAL_LOCKS`` and ``LC_ALL`` keys.
      4. Asserts AT LEAST ONE git argv literal exists (defends against
         vacuous pass when zero list literals match).
    """
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(SCRIPT_PATH))

    git_argv_matches: list[tuple[ast.Call, ast.List]] = []
    env_names_seen: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not _is_subprocess_run_call(node):
            continue
        if not node.args:
            continue
        first_arg = node.args[0]
        if not _list_literal_starts_with_git(first_arg):
            continue

        # (1) found a git argv literal -- now verify env= and prefix.
        assert isinstance(first_arg, ast.List)
        git_argv_matches.append((node, first_arg))

        env_kw = next((kw for kw in node.keywords if kw.arg == "env"), None)
        assert env_kw is not None, (
            f"git subprocess call at line {node.lineno} is missing env= keyword"
        )

        # Record env-name references for downstream dict-source check.
        if isinstance(env_kw.value, ast.Name):
            env_names_seen.add(env_kw.value.id)
        elif isinstance(env_kw.value, ast.Dict):
            # Inline env dict -- assert keys directly.
            keys = _dict_literal_keys(env_kw.value)
            assert "GIT_OPTIONAL_LOCKS" in keys, (
                f"inline env dict at line {env_kw.value.lineno} missing "
                f"GIT_OPTIONAL_LOCKS; keys={keys!r}"
            )
            assert "LC_ALL" in keys, (
                f"inline env dict at line {env_kw.value.lineno} missing "
                f"LC_ALL; keys={keys!r}"
            )

        # Argv prefix check: first six elements must match exactly.
        actual_prefix = _list_literal_prefix_strings(
            first_arg, len(_GIT_PREFIX_EXPECTED)
        )
        assert actual_prefix == _GIT_PREFIX_EXPECTED, (
            f"git argv at line {first_arg.lineno} does not start with the "
            f"hardened six-element prefix.\n"
            f"  expected: {_GIT_PREFIX_EXPECTED!r}\n"
            f"  actual  : {actual_prefix!r}"
        )

    # (4) vacuous-pass defense: at least one match must exist.
    assert len(git_argv_matches) >= 1, (
        "no git argv list literals found in bin/cortex-commit-preflight; "
        "AST walker would pass vacuously. Refactor must keep at least one "
        "list literal beginning with 'git' visible to ast.walk."
    )

    # (3) env-dict source check: every env=NAME reference must resolve
    # to a module-level dict with the two required keys.
    for env_name in env_names_seen:
        env_dict = _find_env_dict_assignment(tree, env_name)
        assert env_dict is not None, (
            f"could not find module-level dict assignment for env={env_name}"
        )
        keys = _dict_literal_keys(env_dict)
        assert "GIT_OPTIONAL_LOCKS" in keys, (
            f"env dict {env_name!r} missing GIT_OPTIONAL_LOCKS; keys={keys!r}"
        )
        assert "LC_ALL" in keys, (
            f"env dict {env_name!r} missing LC_ALL; keys={keys!r}"
        )
