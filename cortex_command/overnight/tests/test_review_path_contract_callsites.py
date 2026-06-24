"""Value-level regression guard (spec R3): every review-gate call site passes
an *absolute* ``lifecycle_base`` into ``dispatch_review``.

A source grep cannot distinguish an absolute base from a relative one, so each
of the three production call paths is driven with ``dispatch_review`` patched
to a capturing mock; the test then asserts the ``lifecycle_base`` kwarg that
actually reached the call is present and absolute.

Read fail-closed: because the capturing mock bypasses ``dispatch_review``'s
body, the signature default never applies — a call site that *omits* the kwarg
(a regression to the relative default) yields no ``lifecycle_base`` key at all,
so presence is asserted explicitly rather than via a defensive ``.get`` that
would silently mask the omission.

``CORTEX_REPO_ROOT`` is pinned to an absolute path so
``_resolve_lifecycle_base()`` resolves deterministically and the assertion is
not coupled to the ambient environment.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from cortex_command.overnight.outcome_router import (
    _recovery_review_gate,
    _repair_review_or_revert,
    apply_feature_result,
)
from cortex_command.overnight.tests.test_outcome_router import _make_ctx
from cortex_command.overnight.types import FeatureResult

# Absolute CORTEX_REPO_ROOT so _resolve_lifecycle_base() -> absolute,
# deterministically, independent of the ambient env.
_ABS_ENV = "/private/tmp/cortex-r3-root"

_ROUTER = "cortex_command.overnight.outcome_router"


def _approved() -> MagicMock:
    """A review result that lets each gate fall through cleanly (not deferred)."""
    return MagicMock(deferred=False, could_not_run=False, verdict="approved", cycle=1)


class TestReviewGateLifecycleBaseIsAbsolute(unittest.IsolatedAsyncioTestCase):

    def _assert_absolute_lifecycle_base(self, m_dispatch: AsyncMock) -> None:
        m_dispatch.assert_awaited_once()
        kwargs = m_dispatch.await_args.kwargs
        self.assertIn(
            "lifecycle_base", kwargs,
            "review-gate call site omitted lifecycle_base (regressed to the "
            "relative default)",
        )
        self.assertTrue(
            Path(kwargs["lifecycle_base"]).is_absolute(),
            f"lifecycle_base reaching dispatch_review is not absolute: "
            f"{kwargs['lifecycle_base']!r}",
        )

    async def test_recovery_gate_passes_absolute_lifecycle_base(self):
        ctx = _make_ctx(pauses=0)
        ctx.worktree_branches["feat-a"] = "pipeline/feat-a"
        with (
            patch.dict("os.environ", {"CORTEX_REPO_ROOT": _ABS_ENV}),
            patch(f"{_ROUTER}._review_required", return_value=True),
            patch(f"{_ROUTER}.read_tier", return_value="complex"),
            patch(f"{_ROUTER}.read_criticality", return_value="high"),
            patch(f"{_ROUTER}.dispatch_review",
                  new=AsyncMock(return_value=_approved())) as m_dispatch,
        ):
            await _recovery_review_gate(
                "feat-a", ctx,
                recovery_merge_sha="sha",
                actual_branch="pipeline/feat-a",
                repo_path=Path("/tmp/repo"),
                merge_target=Path("/tmp/repo"),
                deferred_dir=Path("/tmp/deferred"),
            )
        self._assert_absolute_lifecycle_base(m_dispatch)

    async def test_repair_completed_gate_passes_absolute_lifecycle_base(self):
        ctx = _make_ctx(pauses=0)
        with (
            patch.dict("os.environ", {"CORTEX_REPO_ROOT": _ABS_ENV}),
            patch(f"{_ROUTER}.read_tier", return_value="complex"),
            patch(f"{_ROUTER}.read_criticality", return_value="high"),
            patch(f"{_ROUTER}.dispatch_review",
                  new=AsyncMock(return_value=_approved())) as m_dispatch,
        ):
            await _repair_review_or_revert(
                "feat-a", ctx,
                repo=Path("/tmp/repo"),
                pre_ff_base_sha="sha",
                actual_branch="pipeline/feat-a",
                repo_path=Path("/tmp/repo"),
                deferred_dir=Path("/tmp/deferred"),
            )
        self._assert_absolute_lifecycle_base(m_dispatch)

    async def test_primary_gate_passes_absolute_lifecycle_base(self):
        ctx = _make_ctx(pauses=0)
        ctx.worktree_branches["feat-a"] = "pipeline/feat-a"
        merge_result = MagicMock(
            success=True, error=None, conflict=False, test_result=None,
        )
        with (
            patch.dict("os.environ", {"CORTEX_REPO_ROOT": _ABS_ENV}),
            patch(f"{_ROUTER}._get_changed_files", return_value=["src/a.py"]),
            patch(f"{_ROUTER}.merge_feature", return_value=merge_result),
            patch(f"{_ROUTER}.requires_review", return_value=True),
            patch(f"{_ROUTER}._review_required", return_value=True),
            patch(f"{_ROUTER}.read_tier", return_value="complex"),
            patch(f"{_ROUTER}.read_criticality", return_value="high"),
            patch(f"{_ROUTER}._write_back_to_backlog"),
            patch(f"{_ROUTER}.overnight_log_event"),
            patch(f"{_ROUTER}.cleanup_worktree"),
            patch(f"{_ROUTER}.dispatch_review",
                  new=AsyncMock(return_value=_approved())) as m_dispatch,
        ):
            await apply_feature_result(
                "feat-a",
                FeatureResult(name="feat-a", status="completed"),
                ctx,
            )
        self._assert_absolute_lifecycle_base(m_dispatch)


if __name__ == "__main__":
    unittest.main()
