"""Self-tests for ``bin/cortex-check-prescriptive-prose`` (R7 acceptance).

Each test case sets up a temp directory with a minimal markdown fixture under
``skills/`` or ``cortex/backlog/`` and invokes the scanner via ``subprocess`` with the
``--root <tmp_path>`` test-only override. We assert exit codes and a stable
substring of the scanner's positive-routing diagnostic.

R7 acceptance cases covered (per spec):

(a) clean section produces exit 0
(b) ``path:line`` in Role section flags
(c) ``§N`` in Edges section flags
(d) fenced code block ≥2 lines in Integration flags
(e) Touch points is exempted (path:line and §N inside Touch points do NOT flag)
(f) bare path without ``:line`` does NOT flag (narrative reference)
(g) inline backtick code reference does NOT flag
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "bin" / "cortex-check-prescriptive-prose"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_ticket(root: Path, rel: str, body: str) -> Path:
    """Write ``body`` to ``<root>/<rel>`` after ensuring parent dirs exist."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _run_staged(root: Path) -> subprocess.CompletedProcess[bytes]:
    """Invoke the scanner in --staged mode with --root override."""
    return subprocess.run(
        [sys.executable, "-m", "cortex_command.lint.prescriptive_prose", "--staged", "--root", str(root)],
        capture_output=True,
        check=False,
    )


def _run_file(file_path: Path, root: Path) -> subprocess.CompletedProcess[bytes]:
    """Invoke the scanner in single-file mode with --root override."""
    return subprocess.run(
        [sys.executable, "-m", "cortex_command.lint.prescriptive_prose", "--root", str(root), str(file_path)],
        capture_output=True,
        check=False,
    )


# ---------------------------------------------------------------------------
# R7 acceptance tests
# ---------------------------------------------------------------------------


def test_clean_section_exits_zero(tmp_path: Path) -> None:
    """(a) A clean ticket body with no LEX-1 hits exits 0."""
    body = (
        "# Ticket\n\n"
        "## Role\n\n"
        "This piece tracks lifecycle state.\n\n"
        "## Integration\n\n"
        "Connects via the phase-transition contract.\n\n"
        "## Edges\n\n"
        "Breaks if the phase-transition contract changes.\n"
    )
    _write_ticket(tmp_path, "cortex/backlog/100-clean.md", body)
    result = _run_staged(tmp_path)
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")


def test_path_line_in_role_flags(tmp_path: Path) -> None:
    """(b) ``path:line`` in Role section produces a violation."""
    body = (
        "## Role\n\n"
        "This piece must update decompose.md:147 to replace the ban.\n"
    )
    _write_ticket(tmp_path, "cortex/backlog/101-path-line.md", body)
    result = _run_staged(tmp_path)
    assert result.returncode == 1
    stderr = result.stderr.decode("utf-8", errors="replace")
    assert "PRESCRIPTIVE_PROSE" in stderr
    assert "path:line" in stderr
    assert "decompose.md:147" in stderr
    assert "'Role'" in stderr


def test_section_index_in_edges_flags(tmp_path: Path) -> None:
    """(c) ``§N`` in Edges section produces a violation."""
    body = (
        "## Edges\n\n"
        "Follows the pattern in §3a from the spec.\n"
    )
    _write_ticket(tmp_path, "cortex/backlog/102-section-index.md", body)
    result = _run_staged(tmp_path)
    assert result.returncode == 1
    stderr = result.stderr.decode("utf-8", errors="replace")
    assert "section-index" in stderr
    assert "§3a" in stderr
    assert "'Edges'" in stderr


def test_fenced_block_two_lines_in_integration_flags(tmp_path: Path) -> None:
    """(d) Fenced code block of ≥2 non-empty lines inside Integration flags."""
    body = (
        "## Integration\n\n"
        "Add this snippet:\n\n"
        "```python\n"
        "def foo():\n"
        "    return 42\n"
        "```\n"
    )
    _write_ticket(tmp_path, "cortex/backlog/103-fenced.md", body)
    result = _run_staged(tmp_path)
    assert result.returncode == 1
    stderr = result.stderr.decode("utf-8", errors="replace")
    assert "quoted-prose-patch" in stderr
    assert "'Integration'" in stderr


def test_touch_points_exempted(tmp_path: Path) -> None:
    """(e) Touch points is the sole permitted section — path:line and §N do not flag."""
    body = (
        "## Role\n\n"
        "Tracks state.\n\n"
        "## Touch points\n\n"
        "- `decompose.md:147` — replace the ban\n"
        "- §3a of research.md\n"
        "- R2(b) premise check\n"
    )
    _write_ticket(tmp_path, "cortex/backlog/104-touch-points.md", body)
    result = _run_staged(tmp_path)
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")


def test_bare_path_without_line_does_not_flag(tmp_path: Path) -> None:
    """(f) Bare path without ``:line`` is a narrative reference and does not flag."""
    body = (
        "## Edges\n\n"
        "The phase-transition contract is documented in skills/lifecycle/SKILL.md.\n"
        "See research/foo/research.md for context.\n"
    )
    _write_ticket(tmp_path, "cortex/backlog/105-bare-path.md", body)
    result = _run_staged(tmp_path)
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")


def test_inline_backtick_does_not_flag(tmp_path: Path) -> None:
    """(g) Inline backtick code references are narrative and do not flag."""
    body = (
        "## Role\n\n"
        "The role is to track lifecycle state. "
        "See `cortex-update-item` for the helper.\n"
    )
    _write_ticket(tmp_path, "cortex/backlog/106-inline-backtick.md", body)
    result = _run_staged(tmp_path)
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Additional coverage
# ---------------------------------------------------------------------------


def test_single_file_mode(tmp_path: Path) -> None:
    """Positional file-arg mode scans a single file directly."""
    body = (
        "## Edges\n\n"
        "This piece must update foo.py:42 to fix the bug.\n"
    )
    target = _write_ticket(tmp_path, "cortex/backlog/200-single-file.md", body)
    result = _run_file(target, tmp_path)
    assert result.returncode == 1
    stderr = result.stderr.decode("utf-8", errors="replace")
    assert "foo.py:42" in stderr


# ---------------------------------------------------------------------------
# R5 behavioral regression lock — real-git --staged path (NOT --root).
#
# The cases above use --root, which routes through the already-correct
# root.glob audit path and never reaches _matches_scan_glob — so they cannot
# detect the deep-file under-scan bug. This test uses real git staging WITHOUT
# --root, so a deep-≥3 (and depth-1) in-scope file with a genuine
# prescriptive-prose violation must trip the gate. Under the old Path.match
# semantics the deep files are dropped from the staged scan and the gate
# silently exits 0 — so this test goes RED if the bug returns.
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
    """Real --staged run: deep-≥3 AND depth-1 skill files both trip the gate.

    Asserts a non-zero exit AND that each deep file's path appears in the
    reported violation — a bare non-zero exit alone is as weak as a grep.
    """
    _init_real_repo(tmp_path)
    deep = "skills/lifecycle/references/deep_probe.md"  # depth-≥3
    shallow = "skills/depth1_probe.md"  # depth-1 (** = zero segments)
    violation = (
        "## Role\n\nThis piece must update decompose.md:147 to replace the ban.\n"
    )
    _write_inscope(tmp_path, deep, violation)
    _write_inscope(tmp_path, shallow, violation)
    _git(tmp_path, "add", deep, shallow)

    result = subprocess.run(
        [sys.executable, "-m", "cortex_command.lint.prescriptive_prose", "--staged"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=_staged_env(),
    )
    out = result.stdout + result.stderr
    assert result.returncode != 0, f"expected non-zero exit, got 0\n{out}"
    assert "PRESCRIPTIVE_PROSE" in out, out
    assert deep in out, f"deep path missing from violation output\n{out}"
    assert shallow in out, f"depth-1 path missing from violation output\n{out}"
