"""End-to-end tests for ``cortex_command.parity_check`` driven by mini-repo fixtures.

Each subdirectory of ``tests/fixtures/parity/`` is a self-contained mini-repo
exercising one wiring/violation scenario. The linter is invoked with that
directory as ``cwd`` (it operates on ``os.getcwd()``) and its JSON output is
asserted against expectations keyed on the fixture name's prefix:

  - ``valid-*`` → exit 0, JSON is an empty array.
  - ``invalid-*`` → exit 1, JSON contains the codes listed in
    ``expected.json`` (a JSON array of expected violation codes, e.g.
    ``["E001", "E001"]``).
  - ``exclude-*`` → exit 0, JSON is an empty array (proves R5 exclusions).

Tasks 5 and 6 add ``invalid-*`` and ``exclude-*`` fixtures into the same
directory using this harness without modification.

Note: ``bin/cortex-check-parity`` is now a dual-channel bash wrapper (promoted
in Task 12 of installation-integrity-layer-bash-to-entry). The test now invokes
the module directly via ``python3 -m cortex_command.parity_check`` to remain
runnable in both wheel-installed and working-tree contexts.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures" / "parity"


def _fixture_dirs() -> list[Path]:
    if not FIXTURES_ROOT.is_dir():
        return []
    return sorted(p for p in FIXTURES_ROOT.iterdir() if p.is_dir())


@pytest.mark.parametrize(
    "fixture",
    _fixture_dirs(),
    ids=lambda p: p.name,
)
def test_parity_fixture(fixture: Path) -> None:
    """Run the linter against ``fixture`` and assert outcome by prefix."""
    env = dict(os.environ)
    # Ensure the working-tree module is used even when the installed wheel
    # points to a different worktree (common in multi-worktree setups).
    existing_pythonpath = env.get("PYTHONPATH", "")
    if existing_pythonpath:
        env["PYTHONPATH"] = f"{REPO_ROOT}:{existing_pythonpath}"
    else:
        env["PYTHONPATH"] = str(REPO_ROOT)
    result = subprocess.run(
        [sys.executable, "-m", "cortex_command.parity_check", "--json"],
        cwd=str(fixture),
        capture_output=True,
        text=True,
        env=env,
    )

    name = fixture.name
    stdout = result.stdout.strip()
    # The linter emits a single JSON array on stdout when --json is set.
    try:
        violations = json.loads(stdout) if stdout else []
    except json.JSONDecodeError as exc:  # pragma: no cover - diagnostic aid
        pytest.fail(
            f"{name}: linter stdout is not JSON: {exc}\n"
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        )

    if name.startswith("valid-") or name.startswith("exclude-"):
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
        actual_codes = sorted(v["code"] for v in violations)
        assert actual_codes == sorted(expected_codes), (
            f"{name}: violation codes mismatch\n"
            f"expected={sorted(expected_codes)}\nactual={actual_codes}\n"
            f"violations={violations}"
        )
        return

    pytest.fail(
        f"{name}: unrecognized fixture-name prefix; "
        f"expected one of valid-*, invalid-*, exclude-*"
    )


# ---------------------------------------------------------------------------
# R5 behavioral regression lock — real-git --staged path (NOT --root).
#
# parity_check.lint() overlays staged blobs onto a working-tree root.glob
# enumeration, and _matches_scan_glob gates ONLY the overlay. So a violation
# present in BOTH the staged blob and the on-disk copy would fire via the disk
# path even with the bug present (a false lock). This test makes the violation
# reachable ONLY through the staged blob: commit the deep files clean, stage a
# modification that adds the orphan reference, then restore the working-tree
# copy to clean (index=violation, worktree=clean). Under the old Path.match
# semantics the deep (and depth-1) files are dropped from the overlay, only the
# clean worktree copy is scanned, the checker exits 0 — so this test goes RED.
# It deliberately avoids --root, which routes through the already-correct
# root.glob audit path and never reaches _matches_scan_glob.
# ---------------------------------------------------------------------------


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def _init_real_repo(root: Path) -> None:
    """Init a hermetic git repo — hooks disabled so no cortex hook interferes."""
    (root / ".no-hooks").mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "core.hooksPath", str(root / ".no-hooks"))
    _git(root, "config", "commit.gpgsign", "false")  # sandbox: gpg signing unavailable
    _git(root, "commit", "--allow-empty", "-q", "-m", "Initialize test repo")


def _write_inscope(root: Path, rel: str, body: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _staged_env() -> dict[str, str]:
    """Env that forces the working-tree cortex_command (not a stale wheel)."""
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{REPO_ROOT}:{existing}" if existing else str(REPO_ROOT)
    return env


def test_staged_deep_nested_file_flags_via_real_git(tmp_path: Path) -> None:
    """Real --staged run with a staged-blob-only divergence.

    A depth-≥3 AND a depth-1 in-scope file each gain an orphan cortex-* drift
    reference present ONLY in the staged blob (worktree restored to clean).
    Asserts a non-zero exit AND that each deep file's path appears in the
    reported E002 violation — a bare non-zero exit alone is as weak as a grep.
    """
    _init_real_repo(tmp_path)
    deep = "skills/lifecycle/references/deep_probe.md"  # depth-≥3
    shallow = "skills/depth1_probe.md"  # depth-1 (** = zero segments)
    clean = "# Skill\n\nNothing references a script here.\n"
    # Assemble the orphan script names from fragments and interpolate them, so
    # the contiguous cortex-* tokens exist only at runtime — inside the staged
    # blob the temp repo scans — and never appear as a literal backtick span in
    # THIS file, which the parity gate itself scans (tests/**/*.py) and would
    # otherwise flag as E002 self-drift.
    fake_deep = "cortex-" + "fake-deep-probe"
    fake_shallow = "cortex-" + "fake-depth1-probe"
    deep_dirty = f"# Skill\n\nRun `{fake_deep}` to do the thing.\n"
    shallow_dirty = f"# Skill\n\nRun `{fake_shallow}` to do the thing.\n"

    # 1. Commit both files CLEAN (no cortex-* reference on disk at HEAD).
    _write_inscope(tmp_path, deep, clean)
    _write_inscope(tmp_path, shallow, clean)
    _git(tmp_path, "add", deep, shallow)
    _git(tmp_path, "commit", "-q", "-m", "Add clean deep files")

    # 2. Stage a modification that introduces the orphan reference.
    _write_inscope(tmp_path, deep, deep_dirty)
    _write_inscope(tmp_path, shallow, shallow_dirty)
    _git(tmp_path, "add", deep, shallow)

    # 3. Restore the working-tree copies to clean — index=violation, worktree=clean.
    _write_inscope(tmp_path, deep, clean)
    _write_inscope(tmp_path, shallow, clean)

    result = subprocess.run(
        [sys.executable, "-m", "cortex_command.parity_check", "--staged"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        env=_staged_env(),
    )
    out = result.stdout + result.stderr
    assert result.returncode != 0, f"expected non-zero exit, got 0\n{out}"
    assert "E002" in out, out
    assert deep in out, f"deep path missing from violation output\n{out}"
    assert shallow in out, f"depth-1 path missing from violation output\n{out}"
