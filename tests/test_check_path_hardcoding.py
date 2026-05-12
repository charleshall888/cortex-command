"""Self-tests for ``bin/cortex-check-path-hardcoding`` (#203 acceptance).

Each test case sets up a temp directory with a minimal scan-scope tree under
``cortex_command/`` (or ``bin/``, ``hooks/``, ``claude/hooks/``) plus an
optional ``bin/.path-hardcoding-allowlist.md`` fixture. The gate is invoked
via ``subprocess`` with the ``--root <tmp_path>`` test-only override.

Fixture script names are constructed via string concatenation (``_F + "bad"``)
so a contiguous fictional cortex-* token never appears in this source file —
otherwise the parity linter would treat the mention as a wiring signal
pointing at a non-existent deployed script.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "bin" / "cortex-check-path-hardcoding"

# Concatenation guard — see module docstring.
_F = "cor" + "tex-"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(root: Path, rel: str, body: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _run_audit(root: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--audit", "--root", str(root)],
        capture_output=True,
        check=False,
    )


def _run_staged(root: Path) -> subprocess.CompletedProcess[bytes]:
    subprocess.run(["git", "init", "-q"], cwd=str(root), check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=str(root),
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "test"], cwd=str(root), check=True
    )
    subprocess.run(["git", "add", "-A"], cwd=str(root), check=True)
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--staged", "--root", str(root)],
        capture_output=True,
        check=False,
    )


_VALID_ALLOWLIST_HEADER = (
    "# Allowlist\n\n"
    "## Entries\n\n"
    "| file | line_pattern | category | rationale | lifecycle_id | added_date |\n"
    "| --- | --- | --- | --- | --- | --- |\n"
)


def _allowlist_with_rows(*rows: str) -> str:
    return _VALID_ALLOWLIST_HEADER + "".join(
        r if r.endswith("\n") else r + "\n" for r in rows
    )


# ---------------------------------------------------------------------------
# Detection tests
# ---------------------------------------------------------------------------


def test_audit_clean_tree_exits_zero(tmp_path: Path) -> None:
    """Empty in-scope tree exits 0."""
    (tmp_path / "cortex_command").mkdir()
    _write(tmp_path, "cortex_command/clean.py", 'x = Path("cortex/lifecycle")\n')
    result = _run_audit(tmp_path)
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")


def test_slash_prefix_violation_flags(tmp_path: Path) -> None:
    """``Path("lifecycle/x")`` is flagged."""
    _write(tmp_path, "cortex_command/bad.py", 'x = Path("lifecycle/foo")\n')
    result = _run_audit(tmp_path)
    assert result.returncode == 1
    stderr = result.stderr.decode("utf-8", errors="replace")
    assert "PH001" in stderr
    assert "cortex_command/bad.py:1" in stderr


def test_fstring_slash_prefix_violation_flags(tmp_path: Path) -> None:
    """``f"backlog/{x}"`` is flagged."""
    _write(tmp_path, "cortex_command/bad.py", 'x = f"backlog/{name}"\n')
    result = _run_audit(tmp_path)
    assert result.returncode == 1
    assert b"cortex_command/bad.py:1" in result.stderr


def test_bare_path_literal_flags(tmp_path: Path) -> None:
    """``Path("lifecycle")`` (no slash) is flagged."""
    _write(tmp_path, "cortex_command/bad.py", 'x = Path("lifecycle") / "x"\n')
    result = _run_audit(tmp_path)
    assert result.returncode == 1
    assert b"PH001" in result.stderr


def test_bare_os_path_join_flags(tmp_path: Path) -> None:
    """``os.path.join("backlog", x)`` is flagged."""
    _write(tmp_path, "cortex_command/bad.py", 'x = os.path.join("backlog", name)\n')
    result = _run_audit(tmp_path)
    assert result.returncode == 1
    assert b"PH001" in result.stderr


def test_canonical_anchor_does_not_flag(tmp_path: Path) -> None:
    """``Path("cortex/lifecycle")`` is the correct form and does NOT flag."""
    _write(tmp_path, "cortex_command/ok.py", 'x = Path("cortex/lifecycle") / name\n')
    result = _run_audit(tmp_path)
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Scan-scope tests (fixture script names built via _F + suffix concatenation)
# ---------------------------------------------------------------------------


def test_scope_includes_bin_cortex_scripts(tmp_path: Path) -> None:
    name = _F + "bad"
    rel = "bin/" + name
    _write(tmp_path, rel, '#!/usr/bin/env python3\nx = "lifecycle/foo"\n')
    os.chmod(tmp_path / rel, 0o755)
    result = _run_audit(tmp_path)
    assert result.returncode == 1
    assert rel.encode() in result.stderr


def test_scope_includes_hooks(tmp_path: Path) -> None:
    name = _F + "bad"
    rel = "hooks/" + name
    _write(tmp_path, rel, 'x = "backlog/foo"\n')
    result = _run_audit(tmp_path)
    assert result.returncode == 1
    assert rel.encode() in result.stderr


def test_scope_includes_claude_hooks(tmp_path: Path) -> None:
    name = _F + "bad"
    rel = "claude/hooks/" + name
    _write(tmp_path, rel, 'x = "research/foo"\n')
    result = _run_audit(tmp_path)
    assert result.returncode == 1
    assert rel.encode() in result.stderr


def test_scope_excludes_tests_subtree_top_level(tmp_path: Path) -> None:
    """Top-level ``tests/`` is excluded even with .py files."""
    _write(tmp_path, "tests/test_something.py", 'x = "lifecycle/foo"\n')
    result = _run_audit(tmp_path)
    assert result.returncode == 0


def test_scope_excludes_tests_subtree_nested(tmp_path: Path) -> None:
    """A ``tests/`` subtree under a production scan root is excluded."""
    _write(
        tmp_path,
        "cortex_command/init/tests/test_fixture.py",
        'x = "lifecycle/foo"\n',
    )
    result = _run_audit(tmp_path)
    assert result.returncode == 0


def test_scope_excludes_markdown(tmp_path: Path) -> None:
    """Markdown files are not scanned even when they contain violations."""
    _write(tmp_path, "cortex_command/notes.md", '"lifecycle/foo" appears here\n')
    result = _run_audit(tmp_path)
    assert result.returncode == 0


def test_scope_excludes_non_cortex_prefix_in_bin(tmp_path: Path) -> None:
    """A bin/ file that is NOT named like a cortex-* script is out of scope."""
    _write(tmp_path, "bin/random-script", 'x = "lifecycle/foo"\n')
    result = _run_audit(tmp_path)
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Allowlist tests
# ---------------------------------------------------------------------------


def test_allowlist_suppresses_matching_violation(tmp_path: Path) -> None:
    name = _F + "rewriter"
    rel = "bin/" + name
    _write(
        tmp_path,
        rel,
        'x = Path("lifecycle") / "archive"\n',
    )
    _write(
        tmp_path,
        "bin/.path-hardcoding-allowlist.md",
        _allowlist_with_rows(
            "| `" + rel + "` | `Path..lifecycle..` "
            "| `archive-rewriter` "
            "| Archive rewriter operates on pre-relocation paths and the bare prefix is intentional. "
            "| `203` | `2026-05-12` |"
        ),
    )
    result = _run_audit(tmp_path)
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")


def test_allowlist_does_not_suppress_unrelated_violation(tmp_path: Path) -> None:
    """An allowlist row for file A does not cover a violation in file B."""
    _write(
        tmp_path,
        "cortex_command/bad.py",
        'x = "lifecycle/foo"\n',
    )
    _write(
        tmp_path,
        "bin/.path-hardcoding-allowlist.md",
        _allowlist_with_rows(
            "| `cortex_command/other.py` | `lifecycle/` "
            "| `archive-rewriter` "
            "| Some unrelated file's bare prefix is intentional and well-rationalized here. "
            "| `203` | `2026-05-12` |"
        ),
    )
    result = _run_audit(tmp_path)
    assert result.returncode == 1


def test_fail_open_on_missing_allowlist_clean_tree(tmp_path: Path) -> None:
    """No allowlist file + no violations → exit 0."""
    _write(tmp_path, "cortex_command/clean.py", 'x = Path("cortex/lifecycle")\n')
    assert not (tmp_path / "bin/.path-hardcoding-allowlist.md").exists()
    result = _run_audit(tmp_path)
    assert result.returncode == 0


def test_fail_open_on_missing_allowlist_with_violation(tmp_path: Path) -> None:
    """No allowlist file + violation → exit 1 (strict mode)."""
    _write(tmp_path, "cortex_command/bad.py", 'x = "lifecycle/foo"\n')
    assert not (tmp_path / "bin/.path-hardcoding-allowlist.md").exists()
    result = _run_audit(tmp_path)
    assert result.returncode == 1


# ---------------------------------------------------------------------------
# Allowlist schema tests
# ---------------------------------------------------------------------------


def _fixture_allowlist_row(category: str, rationale: str, date: str) -> str:
    return (
        "| `bin/" + _F + "fixturex` | `lifecycle/` | `" + category + "` "
        "| " + rationale + " "
        "| `203` | `" + date + "` |"
    )


def test_allowlist_unknown_category_rejected(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "bin/.path-hardcoding-allowlist.md",
        _allowlist_with_rows(
            _fixture_allowlist_row(
                "bogus-category",
                "This is a fine-looking rationale of sufficient length for the test.",
                "2026-05-12",
            )
        ),
    )
    _write(tmp_path, "cortex_command/clean.py", "x = 1\n")
    result = _run_audit(tmp_path)
    assert result.returncode == 1
    assert b"ALLOWLIST_CATEGORY" in result.stderr


def test_allowlist_short_rationale_rejected(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "bin/.path-hardcoding-allowlist.md",
        _allowlist_with_rows(
            _fixture_allowlist_row("archive-rewriter", "too short", "2026-05-12")
        ),
    )
    _write(tmp_path, "cortex_command/clean.py", "x = 1\n")
    result = _run_audit(tmp_path)
    assert result.returncode == 1
    assert b"ALLOWLIST_RATIONALE_LEN" in result.stderr


@pytest.mark.parametrize(
    "forbidden_word",
    ["internal", "INTERNAL", "misc", "tbd", "n/a", "pending", "temporary"],
)
def test_allowlist_forbidden_literal_rejected(
    tmp_path: Path, forbidden_word: str
) -> None:
    rationale = (
        "This " + forbidden_word
        + " reason should be rejected even if length is OK enough."
    )
    _write(
        tmp_path,
        "bin/.path-hardcoding-allowlist.md",
        _allowlist_with_rows(
            _fixture_allowlist_row("archive-rewriter", rationale, "2026-05-12")
        ),
    )
    _write(tmp_path, "cortex_command/clean.py", "x = 1\n")
    result = _run_audit(tmp_path)
    assert result.returncode == 1
    assert b"ALLOWLIST_RATIONALE_FORBIDDEN" in result.stderr


def test_allowlist_invalid_date_rejected(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "bin/.path-hardcoding-allowlist.md",
        _allowlist_with_rows(
            _fixture_allowlist_row(
                "archive-rewriter",
                "This rationale is plenty long and specific for the test.",
                "not-a-date",
            )
        ),
    )
    _write(tmp_path, "cortex_command/clean.py", "x = 1\n")
    result = _run_audit(tmp_path)
    assert result.returncode == 1
    assert b"ALLOWLIST_DATE" in result.stderr


def test_allowlist_schema_doc_table_skipped(tmp_path: Path) -> None:
    """A non-canonical doc table at the top of the allowlist is silently skipped."""
    body = (
        "# Allowlist\n\n"
        "## Schema\n\n"
        "| Column | Constraint |\n"
        "| --- | --- |\n"
        "| `file` | A path. |\n\n"
        "## Entries\n\n"
        "| file | line_pattern | category | rationale | lifecycle_id | added_date |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        + _fixture_allowlist_row(
            "archive-rewriter",
            "This rationale is plenty long and specific for the test.",
            "2026-05-12",
        )
        + "\n"
    )
    _write(tmp_path, "bin/.path-hardcoding-allowlist.md", body)
    _write(tmp_path, "cortex_command/clean.py", "x = 1\n")
    result = _run_audit(tmp_path)
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Mode tests
# ---------------------------------------------------------------------------


def test_staged_mode_with_no_in_scope_files_exits_zero(tmp_path: Path) -> None:
    """``--staged`` with nothing in scope staged exits 0."""
    _write(tmp_path, "docs/notes.md", '"lifecycle/foo" appears in docs\n')
    result = _run_staged(tmp_path)
    assert result.returncode == 0


def test_staged_mode_flags_in_scope_violation(tmp_path: Path) -> None:
    _write(tmp_path, "cortex_command/bad.py", 'x = "lifecycle/foo"\n')
    result = _run_staged(tmp_path)
    assert result.returncode == 1
    assert b"cortex_command/bad.py" in result.stderr


def test_help_exits_zero(tmp_path: Path) -> None:
    """``--help`` exits 0 and lists all three modes."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--help"],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    stdout = result.stdout.decode("utf-8", errors="replace")
    assert "--staged" in stdout
    assert "--audit" in stdout
    assert "--root" in stdout
