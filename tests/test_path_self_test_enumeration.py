"""Unit tests for cortex_command.doctor.path_self_test entry-point enumeration.

Covers the requirement that scripts listed in bin/.parity-exceptions.md under
any doctor-irrelevant category (maintainer-only-tool, library-internal,
deprecated-pending-removal) are excluded from the set of entry points the
self-test checks against PATH.

Test matrix:
  (1) library-internal entry in parity-exceptions -> NOT in expected set
  (2) unlisted cortex- entry -> IS in expected set
  (3) cortex- entry listed under an unknown category -> IS in expected set
      (unknown categories are NOT in _DOCTOR_IRRELEVANT_CATEGORIES)
  (4) importlib.metadata.PackageNotFoundError-equivalent -> main() exits 0
      silently (entry_points raises, exception is swallowed by the outer try)

Each test mocks importlib.metadata.entry_points to avoid coupling to the
actual installed wheel contents, which vary across developer environments.
"""

from __future__ import annotations

import types
import unittest.mock
from pathlib import Path

import pytest

import cortex_command.doctor.path_self_test as psm


# ---------------------------------------------------------------------------
# Helper: build a minimal fake entry_points() return value
# ---------------------------------------------------------------------------


def _make_eps(*names: str):
    """Return a list of fake entry-point objects with the given names."""
    eps = []
    for name in names:
        ep = unittest.mock.MagicMock()
        ep.name = name
        eps.append(ep)
    return eps


# ---------------------------------------------------------------------------
# Helper: build a minimal parity-exceptions markdown table
# ---------------------------------------------------------------------------

_TABLE_HEADER = (
    "| script | category | rationale | lifecycle_id | added_date |\n"
    "| --- | --- | --- | --- | --- |\n"
)


def _exceptions_table(*rows: tuple[str, str]) -> str:
    """Return a minimal parity-exceptions markdown table text.

    Each row is (script_name, category).
    """
    lines = ["# Parity exceptions allowlist\n\n", _TABLE_HEADER]
    for script, category in rows:
        lines.append(
            f"| `{script}` | `{category}` | "
            "Placeholder rationale text that is thirty-plus characters long. "
            "| 252 | 2026-05-20 |\n"
        )
    return "".join(lines)


# ---------------------------------------------------------------------------
# (1) library-internal entry listed in parity-exceptions -> NOT in expected set
# ---------------------------------------------------------------------------


def test_library_internal_exception_excluded(monkeypatch: pytest.MonkeyPatch) -> None:
    """A script listed as library-internal in parity-exceptions is excluded from
    the expected-binary set that the self-test checks against PATH.
    """
    # Fake entry_points: two cortex- scripts, one of which is a library-internal exception.
    fake_eps = _make_eps("cortex-batch-runner", "cortex-log-invocation")

    exceptions_text = _exceptions_table(
        ("cortex-batch-runner", "library-internal"),
    )

    # Patch at the component level: entry_points and _load_parity_exceptions.
    with (
        unittest.mock.patch(
            "cortex_command.doctor.path_self_test._load_parity_exceptions",
            return_value=psm._parse_parity_exceptions(exceptions_text),
        ),
        unittest.mock.patch(
            "importlib.metadata.entry_points",
            return_value=fake_eps,
        ),
    ):
        result = psm._get_expected_entry_points()

    # cortex-batch-runner is library-internal -> must be excluded
    assert "cortex-batch-runner" not in result, (
        f"library-internal exception 'cortex-batch-runner' appeared in expected set: {result}"
    )
    # cortex-log-invocation is not excepted -> must be included
    assert "cortex-log-invocation" in result, (
        f"non-excepted entry 'cortex-log-invocation' missing from expected set: {result}"
    )


# ---------------------------------------------------------------------------
# (2) Unlisted cortex- entry -> IS in expected set
# ---------------------------------------------------------------------------


def test_unlisted_entry_included(monkeypatch: pytest.MonkeyPatch) -> None:
    """A cortex- entry NOT listed in parity-exceptions appears in the expected set."""
    fake_eps = _make_eps("cortex-worktree-resolve", "cortex-lifecycle-state")
    # Empty exceptions table (no exceptions declared).
    exceptions_text = _TABLE_HEADER

    with (
        unittest.mock.patch(
            "cortex_command.doctor.path_self_test._load_parity_exceptions",
            return_value=psm._parse_parity_exceptions(exceptions_text),
        ),
        unittest.mock.patch(
            "importlib.metadata.entry_points",
            return_value=fake_eps,
        ),
    ):
        result = psm._get_expected_entry_points()

    assert "cortex-worktree-resolve" in result
    assert "cortex-lifecycle-state" in result


# ---------------------------------------------------------------------------
# (3) cortex- entry listed under an UNKNOWN category -> IS in expected set
# ---------------------------------------------------------------------------


def test_unknown_category_not_excluded(monkeypatch: pytest.MonkeyPatch) -> None:
    """A script listed under an unrecognised category is NOT treated as excepted."""
    fake_eps = _make_eps("cortex-future-command")
    exceptions_text = _exceptions_table(
        ("cortex-future-command", "some-unknown-category"),
    )

    with (
        unittest.mock.patch(
            "cortex_command.doctor.path_self_test._load_parity_exceptions",
            return_value=psm._parse_parity_exceptions(exceptions_text),
        ),
        unittest.mock.patch(
            "importlib.metadata.entry_points",
            return_value=fake_eps,
        ),
    ):
        result = psm._get_expected_entry_points()

    # Unknown category is not doctor-irrelevant -> entry must remain in expected set.
    assert "cortex-future-command" in result, (
        f"Entry with unknown category should remain in expected set; got: {result}"
    )


# ---------------------------------------------------------------------------
# (4) All three doctor-irrelevant categories exclude their entries
# ---------------------------------------------------------------------------


def test_all_doctor_irrelevant_categories_excluded(monkeypatch: pytest.MonkeyPatch) -> None:
    """All three doctor-irrelevant categories (maintainer-only-tool, library-internal,
    deprecated-pending-removal) result in exclusion from the expected set.
    """
    fake_eps = _make_eps(
        "cortex-archive-sample-select",
        "cortex-batch-runner",
        "cortex-old-command",
        "cortex-always-expected",
    )
    exceptions_text = _exceptions_table(
        ("cortex-archive-sample-select", "maintainer-only-tool"),
        ("cortex-batch-runner", "library-internal"),
        ("cortex-old-command", "deprecated-pending-removal"),
    )

    with (
        unittest.mock.patch(
            "cortex_command.doctor.path_self_test._load_parity_exceptions",
            return_value=psm._parse_parity_exceptions(exceptions_text),
        ),
        unittest.mock.patch(
            "importlib.metadata.entry_points",
            return_value=fake_eps,
        ),
    ):
        result = psm._get_expected_entry_points()

    assert "cortex-archive-sample-select" not in result
    assert "cortex-batch-runner" not in result
    assert "cortex-old-command" not in result
    assert "cortex-always-expected" in result


# ---------------------------------------------------------------------------
# (5) importlib.metadata raises -> main() exits 0 silently
# ---------------------------------------------------------------------------


def test_main_exits_0_when_entry_points_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate importlib.metadata.PackageNotFoundError (or any exception from
    entry_points) — main() must return 0 and emit nothing.
    """
    from importlib.metadata import PackageNotFoundError

    def _raising_entry_points(**kwargs):
        raise PackageNotFoundError("cortex-command")

    # Ensure neither dev-mode nor source-tree skip fires so the exception path
    # is actually reached.
    monkeypatch.setattr(psm, "_should_skip", lambda: False)

    with (
        unittest.mock.patch(
            "importlib.metadata.entry_points",
            side_effect=_raising_entry_points,
        ),
        unittest.mock.patch.object(psm, "_emit_advisory") as mock_emit,
    ):
        rc = psm.main()

    assert rc == 0, f"expected exit 0, got {rc}"
    mock_emit.assert_not_called()


# ---------------------------------------------------------------------------
# (6) _parse_parity_exceptions: empty/malformed text -> empty set (over-enumerate)
# ---------------------------------------------------------------------------


def test_parse_parity_exceptions_malformed_returns_empty() -> None:
    """Malformed / empty parity-exceptions text returns empty set."""
    assert psm._parse_parity_exceptions("") == set()
    assert psm._parse_parity_exceptions("# No table here\n\nJust prose.") == set()
    assert psm._parse_parity_exceptions("| wrong | columns |\n| --- | --- |\n| data | row |") == set()
