"""Unit tests for cortex_command.doctor.path_self_test entry-point enumeration.

The former parity-exceptions subtraction retired with the parity linter
(#407); the self-test now expects every installed ``cortex-`` console script
on PATH. Remaining coverage:

  (1) all cortex- entry points appear in the expected set; non-cortex names
      are excluded
  (2) importlib.metadata.PackageNotFoundError-equivalent -> main() exits 0
      silently (entry_points raises, exception is swallowed by the outer try)

Each test mocks importlib.metadata.entry_points to avoid coupling to the
actual installed wheel contents, which vary across developer environments.
"""

from __future__ import annotations

import unittest.mock

import pytest

import cortex_command.doctor.path_self_test as psm


def _make_eps(*names: str):
    """Return a list of fake entry-point objects with the given names."""
    eps = []
    for name in names:
        ep = unittest.mock.MagicMock()
        ep.name = name
        eps.append(ep)
    return eps


def test_all_cortex_entries_expected() -> None:
    """Every cortex- console script is in the expected set; others are not."""
    fake_eps = _make_eps(
        "cortex-worktree-resolve", "cortex-lifecycle-state", "black"
    )

    with unittest.mock.patch(
        "importlib.metadata.entry_points",
        return_value=fake_eps,
    ):
        result = psm._get_expected_entry_points()

    assert result == {"cortex-worktree-resolve", "cortex-lifecycle-state"}


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
