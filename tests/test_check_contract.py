"""End-to-end tests for ``cortex_command.lint.contract`` driven by mini-repo fixtures.

Each subdirectory of ``tests/fixtures/contract/`` is a self-contained mini-repo
exercising one wiring/violation scenario. The linter is invoked with that
directory as ``--root`` and its JSON output is asserted against expectations
keyed on the fixture name's prefix:

  - ``valid-*`` → exit 0, JSON is an empty array.
  - ``invalid-*`` → exit 1, JSON contains at least one violation whose ``code``
    appears in ``expected.json`` (a JSON array of expected violation codes, e.g.
    ``["E101"]``).

Each fixture is a mini-repo with:

  - ``pyproject.toml`` declaring ``[project.scripts]`` for
    ``cortex-create-backlog-item`` mapped to a stub module.
  - The stub module (``stub_create_backlog_item.py``) in the fixture root,
    providing a minimal argparse parser with ``--title`` (required),
    ``--status`` (required), ``--type`` (required), and ``--body`` (optional).
  - A ``skills/demo/SKILL.md`` containing the invocation under test.

The stub module must be importlib-visible so that ``extract_surface()`` can
resolve it. The test adds the fixture directory to ``PYTHONPATH`` when invoking
the subprocess, ensuring ``importlib.util.find_spec`` can locate the stub.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures" / "contract"


def _fixture_dirs() -> list[Path]:
    if not FIXTURES_ROOT.is_dir():
        return []
    return sorted(p for p in FIXTURES_ROOT.iterdir() if p.is_dir())


@pytest.mark.parametrize(
    "fixture",
    _fixture_dirs(),
    ids=lambda p: p.name,
)
def test_contract_fixture(fixture: Path) -> None:
    """Run the contract linter against ``fixture`` and assert outcome by prefix."""
    env = dict(os.environ)
    # Ensure the working-tree cortex_command module is used even when an
    # installed wheel points to a different worktree.
    existing_pythonpath = env.get("PYTHONPATH", "")
    path_entries = [str(REPO_ROOT), str(fixture)]
    if existing_pythonpath:
        path_entries.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(path_entries)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cortex_command.lint.contract",
            "--root",
            str(fixture),
            "--json",
        ],
        capture_output=True,
        text=True,
        env=env,
    )

    name = fixture.name
    stdout = result.stdout.strip()
    try:
        violations = json.loads(stdout) if stdout else []
    except json.JSONDecodeError as exc:  # pragma: no cover - diagnostic aid
        pytest.fail(
            f"{name}: linter stdout is not JSON: {exc}\n"
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        )

    if name.startswith("valid-"):
        assert result.returncode == 0, (
            f"{name}: expected exit 0, got {result.returncode}\n"
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        )
        assert violations == [], (
            f"{name}: expected empty violation array, got {violations}"
        )
        return

    if name.startswith("invalid-"):
        assert result.returncode == 1, (
            f"{name}: expected exit 1, got {result.returncode}\n"
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        )
        expected_path = fixture / "expected.json"
        assert expected_path.is_file(), (
            f"{name}: invalid-* fixtures must include expected.json "
            f"(JSON array of expected violation codes)"
        )
        expected_codes = json.loads(expected_path.read_text(encoding="utf-8"))
        actual_codes = [v["code"] for v in violations]
        # Assert multiset equality: the emitted codes must match expected
        # exactly (same codes, same multiplicity) so that over-firing fixtures
        # (spurious extra codes) are detected as failures.
        assert sorted(actual_codes) == sorted(expected_codes), (
            f"{name}: violation codes mismatch\n"
            f"expected (sorted)={sorted(expected_codes)}\n"
            f"actual   (sorted)={sorted(actual_codes)}\n"
            f"actual violations={violations}\n"
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        )
        return

    pytest.fail(
        f"{name}: unrecognized fixture-name prefix; "
        f"expected one of valid-*, invalid-*"
    )


# ---------------------------------------------------------------------------
# _in_scan_scope unit tests (R8 — membership across all glob shapes)
# ---------------------------------------------------------------------------


def test_in_scan_scope_imports() -> None:
    """_in_scan_scope is importable from the working-tree module."""
    import importlib
    mod = importlib.import_module("cortex_command.lint.contract")
    assert hasattr(mod, "_in_scan_scope"), "_in_scan_scope helper must be exported"


@pytest.mark.parametrize("rel,expected", [
    # skills/**/*.md — depth-1 (zero mid-dirs)
    ("skills/demo.md", True),
    # skills/**/*.md — depth-2
    ("skills/demo/SKILL.md", True),
    # skills/**/*.md — depth-3+ (the lifecycle/references case from spec)
    ("skills/lifecycle/references/implement.md", True),
    # docs/**/*.md — depth-1 (zero mid-dirs)
    ("docs/agentic-layer.md", True),
    # docs/**/*.md — depth-2
    ("docs/internals/pipeline.md", True),
    # tests/**/*.md — depth-2
    ("tests/fixtures/contract/README.md", True),
    # hooks/** — depth-1 file (no extension)
    ("hooks/my-hook", True),
    # hooks/** — depth-2 file
    ("hooks/subdir/my-hook", True),
    # exact-name — justfile
    ("justfile", True),
    # exact-name — CLAUDE.md
    ("CLAUDE.md", True),
    # cortex/requirements/**/*.md — depth-1 under that prefix
    ("cortex/requirements/project.md", True),
    # out-of-scope: .py file
    ("cortex_command/lint/contract.py", False),
    # out-of-scope: markdown outside declared roots
    ("README.md", False),
    # hooks/** matches ALL files under hooks/ (including .sh)
    ("hooks/my-hook.sh", True),
    # out-of-scope: non-md under skills
    ("skills/demo/SKILL.yaml", False),
])
def test_in_scan_scope(rel: str, expected: bool) -> None:
    """_in_scan_scope returns expected membership for each distinct glob shape."""
    import importlib
    mod = importlib.import_module("cortex_command.lint.contract")
    _in_scan_scope = mod._in_scan_scope  # type: ignore[attr-defined]
    result = _in_scan_scope(rel)
    assert result == expected, (
        f"_in_scan_scope({rel!r}) expected {expected}, got {result}"
    )


# ---------------------------------------------------------------------------
# End-to-end staged test: depth-≥3 file carrying a real violation is flagged
# ---------------------------------------------------------------------------


def test_staged_deep_file_violation_detected(tmp_path: Path) -> None:
    """A staged depth-3 in-scope file carrying an E101 violation is flagged.

    Sets up a minimal git repo with the contract-checker stub, stages a file
    at depth 3 (skills/lifecycle/references/SKILL.md) that contains a real
    missing-required-flag invocation, then asserts --staged exits 1 with E101.
    """
    import shutil
    import stat
    import textwrap

    # ── Set up minimal git repo ──────────────────────────────────────────────
    repo = tmp_path / "repo"
    repo.mkdir()

    # Init git
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(repo), check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(repo), check=True, capture_output=True,
    )

    # Stub module
    stub_src = (REPO_ROOT / "tests" / "fixtures" / "contract"
                / "invalid-missing-required-flag" / "stub_create_backlog_item.py")
    shutil.copy(str(stub_src), str(repo / "stub_create_backlog_item.py"))

    # pyproject.toml
    (repo / "pyproject.toml").write_text(textwrap.dedent("""\
        [project]
        name = "staged-deep-test"
        version = "0.0.1"

        [project.scripts]
        cortex-create-backlog-item = "stub_create_backlog_item:main"
    """), encoding="utf-8")

    # Initial commit (so HEAD exists and --staged works)
    subprocess.run(
        ["git", "add", "pyproject.toml", "stub_create_backlog_item.py"],
        cwd=str(repo), check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-m", "init"],
        cwd=str(repo), check=True, capture_output=True,
    )

    # Create depth-3 in-scope file carrying a violation (missing --status, --type)
    deep_dir = repo / "skills" / "lifecycle" / "references"
    deep_dir.mkdir(parents=True)
    deep_file = deep_dir / "implement.md"
    deep_file.write_text(textwrap.dedent("""\
        ---
        name: implement
        description: Deep skill reference
        ---

        Run:

        ```bash
        cortex-create-backlog-item --title "My feature"
        ```
    """), encoding="utf-8")

    # Stage the deep file
    subprocess.run(
        ["git", "add", str(deep_file.relative_to(repo))],
        cwd=str(repo), check=True, capture_output=True,
    )

    # ── Run cortex-check-contract --staged ──────────────────────────────────
    env = dict(os.environ)
    existing_pythonpath = env.get("PYTHONPATH", "")
    path_entries = [str(REPO_ROOT), str(repo)]
    if existing_pythonpath:
        path_entries.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(path_entries)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cortex_command.lint.contract",
            "--staged",
            "--root",
            str(repo),
            "--json",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(repo),
    )

    assert result.returncode == 1, (
        f"Expected exit 1 from --staged on depth-3 violation, got {result.returncode}\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    violations = json.loads(result.stdout.strip())
    codes = [v["code"] for v in violations]
    assert "E101" in codes, (
        f"Expected E101 from depth-3 staged file, got codes={codes}\n"
        f"violations={violations}\nstderr={result.stderr!r}"
    )


def test_resolve_module_path_falls_back_to_root_when_find_spec_fails(tmp_path: Path) -> None:
    """A module invisible to importlib (e.g. a parent package whose dependency
    is missing from the hook interpreter) must still resolve via the root
    fallback so extraction stays dependency-free."""
    from cortex_command.lint.contract import _resolve_module_path

    pkg = tmp_path / "fallback_pkg_xyz" / "deep"
    pkg.mkdir(parents=True)
    module = pkg / "tool.py"
    module.write_text("import argparse\n", encoding="utf-8")

    resolved = _resolve_module_path("fallback_pkg_xyz.deep.tool:main", root=tmp_path)
    assert resolved == module

    # Package form resolves to __init__.py.
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    resolved_pkg = _resolve_module_path("fallback_pkg_xyz.deep:main", root=tmp_path)
    assert resolved_pkg == pkg / "__init__.py"

    # Nothing on disk and nothing importable → None, as before.
    assert _resolve_module_path("fallback_pkg_xyz.missing:main", root=tmp_path) is None


def test_resolve_module_path_prefers_root_over_installed_when_both_resolve(
    tmp_path: Path,
) -> None:
    """When a root-relative candidate exists AND the module name is also
    importable from sys.path (e.g. a stale installed wheel), the root copy
    must win: the lint's job is to check the working tree at ``root``, not
    whatever copy ``sys.path`` happens to serve."""
    pytest.importorskip("yaml")
    from cortex_command.lint.contract import _resolve_module_path

    shadow_module = tmp_path / "yaml.py"
    shadow_module.write_text("# shadow copy under the lint root\n", encoding="utf-8")

    resolved = _resolve_module_path("yaml:main", root=tmp_path)
    assert resolved == shadow_module


def test_resolve_module_path_swallows_non_import_error_from_find_spec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A parent package whose import raises a non-ImportError (e.g. a broken
    dependency raising RuntimeError, as real packages do when a transitive
    import fails) must not crash resolution. The ``find_spec`` call is
    wrapped in a broad ``except Exception`` that treats any such failure as
    unresolved-by-spec."""
    import sys

    from cortex_command.lint.contract import _resolve_module_path

    sys_path_pkg = tmp_path / "on_sys_path"
    broken_pkg = sys_path_pkg / "brokenpkg_xyz"
    broken_pkg.mkdir(parents=True)
    (broken_pkg / "__init__.py").write_text(
        "raise RuntimeError('missing dependency')\n", encoding="utf-8"
    )
    (broken_pkg / "tool.py").write_text("import argparse\n", encoding="utf-8")

    monkeypatch.syspath_prepend(str(sys_path_pkg))
    for mod_name in list(sys.modules):
        if mod_name == "brokenpkg_xyz" or mod_name.startswith("brokenpkg_xyz."):
            del sys.modules[mod_name]

    # No matching file under root, so resolution must fall through to
    # find_spec (which raises) and land on None rather than crashing.
    root = tmp_path / "empty_root"
    root.mkdir()

    assert _resolve_module_path("brokenpkg_xyz.tool:main", root=root) is None
