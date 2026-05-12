"""Self-tests for ``bin/cortex-check-prescriptive-prose`` (R7 acceptance).

Each test case sets up a temp directory with a minimal markdown fixture under
``skills/`` or ``backlog/`` and invokes the scanner via ``subprocess`` with the
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
        [sys.executable, str(SCRIPT_PATH), "--staged", "--root", str(root)],
        capture_output=True,
        check=False,
    )


def _run_file(file_path: Path, root: Path) -> subprocess.CompletedProcess[bytes]:
    """Invoke the scanner in single-file mode with --root override."""
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--root", str(root), str(file_path)],
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
    _write_ticket(tmp_path, "backlog/100-clean.md", body)
    result = _run_staged(tmp_path)
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")


def test_path_line_in_role_flags(tmp_path: Path) -> None:
    """(b) ``path:line`` in Role section produces a violation."""
    body = (
        "## Role\n\n"
        "This piece must update decompose.md:147 to replace the ban.\n"
    )
    _write_ticket(tmp_path, "backlog/101-path-line.md", body)
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
    _write_ticket(tmp_path, "backlog/102-section-index.md", body)
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
    _write_ticket(tmp_path, "backlog/103-fenced.md", body)
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
    _write_ticket(tmp_path, "backlog/104-touch-points.md", body)
    result = _run_staged(tmp_path)
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")


def test_bare_path_without_line_does_not_flag(tmp_path: Path) -> None:
    """(f) Bare path without ``:line`` is a narrative reference and does not flag."""
    body = (
        "## Edges\n\n"
        "The phase-transition contract is documented in skills/lifecycle/SKILL.md.\n"
        "See research/foo/research.md for context.\n"
    )
    _write_ticket(tmp_path, "backlog/105-bare-path.md", body)
    result = _run_staged(tmp_path)
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")


def test_inline_backtick_does_not_flag(tmp_path: Path) -> None:
    """(g) Inline backtick code references are narrative and do not flag."""
    body = (
        "## Role\n\n"
        "The role is to track lifecycle state. "
        "See `cortex-update-item` for the helper.\n"
    )
    _write_ticket(tmp_path, "backlog/106-inline-backtick.md", body)
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
    target = _write_ticket(tmp_path, "backlog/200-single-file.md", body)
    result = _run_file(target, tmp_path)
    assert result.returncode == 1
    stderr = result.stderr.decode("utf-8", errors="replace")
    assert "foo.py:42" in stderr
