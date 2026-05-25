"""Unit and integration tests for the update_item CLI parsing layer.

Covers Task 4 of the make-cortex-update-item-accept-flag lifecycle:
  - argparse scalar/list-flag parsing
  - null/none/"" coercion to Python None for scalar fields
  - allow_abbrev=False rejection of prefix-shortened flags
  - argv pre-flight migration hint for legacy positional key=value form
  - subprocess integration test exercising the full module entrypoint
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from cortex_command.backlog.update_item import (
    _DEST_TO_FRONTMATTER_KEY,
    _SCALAR_DESTS,
    _argv_preflight,
    _build_parser,
)


REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# (a) Scalar-flag parsing
# ---------------------------------------------------------------------------

def test_scalar_flag_status_parses_value() -> None:
    parser = _build_parser()
    args = parser.parse_args(["257", "--status", "complete"])
    assert args.status == "complete"


def test_scalar_flag_lifecycle_phase_parses_value() -> None:
    parser = _build_parser()
    args = parser.parse_args(["257", "--lifecycle-phase", "implementing"])
    assert args.lifecycle_phase == "implementing"


# ---------------------------------------------------------------------------
# (b) List-flag parsing — bare empty form and last-wins on duplicate
# ---------------------------------------------------------------------------

def test_list_flag_areas_bare_yields_empty_list() -> None:
    parser = _build_parser()
    args = parser.parse_args(["257", "--areas"])
    assert args.areas == []


def test_list_flag_areas_last_wins_on_duplicate() -> None:
    parser = _build_parser()
    args = parser.parse_args(["257", "--areas", "a", "b", "--areas", "c"])
    assert args.areas == ["c"]


# ---------------------------------------------------------------------------
# (c) null/none/"" coercion to Python None for scalar fields
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sentinel", ["null", "none", "NULL", "None", ""])
def test_scalar_null_sentinel_coerces_to_python_none(sentinel: str) -> None:
    """Reproduce the main() coercion logic for scalar dests.

    The CLI's main() iterates _DEST_TO_FRONTMATTER_KEY and, for any dest in
    _SCALAR_DESTS whose value lowercases to a sentinel, writes Python None
    into fields_dict. This test exercises that branch directly.
    """
    parser = _build_parser()
    args = parser.parse_args(["257", "--status", sentinel])

    # Mirror main()'s fields-dict assembly for the status dest.
    fields: dict = {}
    for dest, fm_key in _DEST_TO_FRONTMATTER_KEY.items():
        value = getattr(args, dest, None)
        if value is None:
            continue
        if dest in _SCALAR_DESTS and isinstance(value, str):
            if value.lower() in ("null", "none", ""):
                fields[fm_key] = None
                continue
        fields[fm_key] = value

    assert "status" in fields
    assert fields["status"] is None


# ---------------------------------------------------------------------------
# (d) allow_abbrev=False — prefix-shortened flag raises SystemExit
# ---------------------------------------------------------------------------

def test_allow_abbrev_false_rejects_prefix_shortened_flag() -> None:
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["257", "--stat", "complete"])


# ---------------------------------------------------------------------------
# (e) argv pre-flight hint for bare key=value positional
# ---------------------------------------------------------------------------

def test_argv_preflight_detects_bare_key_value(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        _argv_preflight(["update-item", "257", "status=complete"])
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "Detected legacy positional argument" in err
    assert "status=complete" in err


# ---------------------------------------------------------------------------
# (f) argv pre-flight hint for bracket-list legacy form
# ---------------------------------------------------------------------------

def test_argv_preflight_detects_bracket_list_legacy(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        _argv_preflight(["update-item", "257", "areas=[a,b]"])
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "Detected legacy positional argument" in err
    assert "areas=[a,b]" in err


# ---------------------------------------------------------------------------
# (g) argv pre-flight negative case — --status=complete does NOT raise
# ---------------------------------------------------------------------------

def test_argv_preflight_allows_double_dash_equals_form() -> None:
    # Should not raise — the leading "--" prevents the regex from matching.
    _argv_preflight(["update-item", "257", "--status=complete"])


# ---------------------------------------------------------------------------
# (h) Subprocess integration test
# ---------------------------------------------------------------------------

def test_subprocess_legacy_positional_exits_2_with_hint() -> None:
    """Full module entrypoint rejects legacy positional with exit 2 + hint.

    Invokes the module as a child process to verify the pre-flight fires
    from main() before any backlog lookup (so the test passes regardless
    of whether slug 257 resolves on disk).
    """
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cortex_command.backlog.update_item",
            "257",
            "status=complete",
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 2, (
        f"expected exit 2, got {result.returncode}; "
        f"stdout={result.stdout!r}, stderr={result.stderr!r}"
    )
    assert "Detected legacy positional argument" in result.stderr
