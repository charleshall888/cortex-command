"""Unit tests for ``cortex_command.lifecycle_config.read_branch_mode``.

Covers the eight R2 acceptance cases from
``cortex/lifecycle/lifecycle-implement-auto-enter-worktree-drop/spec.md``:

  1. Missing file → ``None``.
  2. Malformed YAML frontmatter → ``None`` + stderr warning.
  3. Field absent → ``None``.
  4. Field present with each of the four closed-set values
     (``worktree-interactive``, ``trunk``, ``feature-branch``, ``prompt``).
  5. Duplicate ``branch-mode:`` key → last-wins (yaml.safe_load default).
  6. Field present with leading/trailing whitespace → stripped value.
  7. Field present with a commented-out value (``branch-mode: # ...``) →
     parses as YAML null → ``None``.
  8. Field present with an out-of-set value → raw string returned (the
     primitive does not validate; callers do).

Each test creates ``tmp_path / "cortex" / "lifecycle.config.md"`` with
controlled content, then asserts on ``read_branch_mode(tmp_path)``.
"""

from __future__ import annotations

import pathlib

import pytest

from cortex_command.lifecycle_config import read_branch_mode


def _write_config(tmp_path: pathlib.Path, body: str) -> pathlib.Path:
    """Write ``cortex/lifecycle.config.md`` under ``tmp_path`` and return path."""
    cortex_dir = tmp_path / "cortex"
    cortex_dir.mkdir(parents=True, exist_ok=True)
    config_path = cortex_dir / "lifecycle.config.md"
    config_path.write_text(body, encoding="utf-8")
    return config_path


# ---------------------------------------------------------------------------
# Case 1: missing file
# ---------------------------------------------------------------------------


def test_missing_file_returns_none(tmp_path: pathlib.Path) -> None:
    # No ``cortex/lifecycle.config.md`` is written.
    assert read_branch_mode(tmp_path) is None


def test_missing_cortex_directory_returns_none(tmp_path: pathlib.Path) -> None:
    # Not even the cortex/ parent exists.
    assert read_branch_mode(tmp_path) is None


# ---------------------------------------------------------------------------
# Case 2: malformed YAML frontmatter
# ---------------------------------------------------------------------------


def test_malformed_yaml_returns_none_and_warns(
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # ``: : :`` is invalid YAML at the top level.
    body = "---\n: : :\n---\nbody\n"
    config_path = _write_config(tmp_path, body)

    result = read_branch_mode(tmp_path)

    assert result is None
    captured = capsys.readouterr()
    assert "warning" in captured.err.lower()
    assert str(config_path) in captured.err


def test_unclosed_frontmatter_returns_none(tmp_path: pathlib.Path) -> None:
    # Opening ``---`` but no closing delimiter → frontmatter extractor
    # returns None → ``read_branch_mode`` returns None without a warning.
    body = "---\nbranch-mode: trunk\nbody without closing delim\n"
    _write_config(tmp_path, body)
    assert read_branch_mode(tmp_path) is None


# ---------------------------------------------------------------------------
# Case 3: field absent
# ---------------------------------------------------------------------------


def test_field_absent_returns_none(tmp_path: pathlib.Path) -> None:
    body = "---\nother-field: value\n---\nbody\n"
    _write_config(tmp_path, body)
    assert read_branch_mode(tmp_path) is None


def test_empty_frontmatter_returns_none(tmp_path: pathlib.Path) -> None:
    body = "---\n---\nbody\n"
    _write_config(tmp_path, body)
    assert read_branch_mode(tmp_path) is None


# ---------------------------------------------------------------------------
# Case 4: field present with each of the four closed-set values
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    ["worktree-interactive", "trunk", "feature-branch", "prompt"],
)
def test_closed_set_values_returned_raw(
    tmp_path: pathlib.Path, value: str
) -> None:
    body = f"---\nbranch-mode: {value}\n---\nbody\n"
    _write_config(tmp_path, body)
    assert read_branch_mode(tmp_path) == value


# ---------------------------------------------------------------------------
# Case 5: duplicate ``branch-mode:`` key → last-wins
# ---------------------------------------------------------------------------


def test_duplicate_key_last_wins(tmp_path: pathlib.Path) -> None:
    body = "---\nbranch-mode: trunk\nbranch-mode: feature-branch\n---\nbody\n"
    _write_config(tmp_path, body)
    assert read_branch_mode(tmp_path) == "feature-branch"


# ---------------------------------------------------------------------------
# Case 6: field present with leading/trailing whitespace → stripped
# ---------------------------------------------------------------------------


def test_whitespace_padded_value_is_stripped(tmp_path: pathlib.Path) -> None:
    # Quoted form forces YAML to preserve the surrounding spaces inside the
    # string; ``read_branch_mode`` is responsible for stripping them.
    body = '---\nbranch-mode: "  trunk  "\n---\nbody\n'
    _write_config(tmp_path, body)
    assert read_branch_mode(tmp_path) == "trunk"


# ---------------------------------------------------------------------------
# Case 7: commented-out value (``branch-mode: # ...``) → null → None
# ---------------------------------------------------------------------------


def test_commented_value_returns_none(tmp_path: pathlib.Path) -> None:
    body = "---\nbranch-mode: # commented out\n---\nbody\n"
    _write_config(tmp_path, body)
    assert read_branch_mode(tmp_path) is None


def test_explicit_null_value_returns_none(tmp_path: pathlib.Path) -> None:
    body = "---\nbranch-mode: null\n---\nbody\n"
    _write_config(tmp_path, body)
    assert read_branch_mode(tmp_path) is None


# ---------------------------------------------------------------------------
# Case 8: out-of-set value → raw string returned (caller validates)
# ---------------------------------------------------------------------------


def test_out_of_set_value_returns_raw_string(tmp_path: pathlib.Path) -> None:
    body = "---\nbranch-mode: TRUNK\n---\nbody\n"
    _write_config(tmp_path, body)
    # Case-sensitive — ``TRUNK`` is returned as-is for the caller to reject.
    assert read_branch_mode(tmp_path) == "TRUNK"


def test_out_of_set_typo_returns_raw_string(tmp_path: pathlib.Path) -> None:
    body = "---\nbranch-mode: wurktree-interactive\n---\nbody\n"
    _write_config(tmp_path, body)
    assert read_branch_mode(tmp_path) == "wurktree-interactive"


# ---------------------------------------------------------------------------
# Dormant/unknown-key warnings (backlog #372 dormant-config audit)
# ---------------------------------------------------------------------------


def test_dormant_key_warns_once(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    import cortex_command.lifecycle_config as lc

    lc._WARNED_KEYS.clear()
    body = "---\nskip-specify: true\nbranch-mode: trunk\n---\nbody\n"
    _write_config(tmp_path, body)
    assert read_branch_mode(tmp_path) == "trunk"
    err = capsys.readouterr().err
    assert "skip-specify" in err and "no effect" in err
    # Second read: once-per-process dedup — no repeat warning.
    read_branch_mode(tmp_path)
    assert "skip-specify" not in capsys.readouterr().err


def test_unknown_workflow_key_warns(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    import cortex_command.lifecycle_config as lc

    lc._WARNED_KEYS.clear()
    body = "---\nphase-order: [a, b]\nbranch-mode: trunk\n---\nbody\n"
    _write_config(tmp_path, body)
    assert read_branch_mode(tmp_path) == "trunk"
    err = capsys.readouterr().err
    assert "phase-order" in err and "unknown" in err


def test_live_keys_do_not_warn(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    import cortex_command.lifecycle_config as lc

    lc._WARNED_KEYS.clear()
    body = (
        "---\nbranch-mode: trunk\ncommit-artifacts: true\n"
        "test-command: just test\nbacklog:\n  backend: cortex-backlog\n---\n"
    )
    _write_config(tmp_path, body)
    assert read_branch_mode(tmp_path) == "trunk"
    assert capsys.readouterr().err == ""
