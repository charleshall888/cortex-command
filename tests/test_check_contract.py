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
        # Assert that at least one violation has a code that appears in the
        # expected codes list.
        assert any(code in expected_codes for code in actual_codes), (
            f"{name}: no violation with expected code(s) {expected_codes}\n"
            f"actual violations={violations}\n"
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        )
        return

    pytest.fail(
        f"{name}: unrecognized fixture-name prefix; "
        f"expected one of valid-*, invalid-*"
    )
