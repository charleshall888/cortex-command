"""Unit tests for the scheduler protocol scaffolding (Task 1).

Covers:
  TestProtocolShape         — Scheduler protocol exposes the four required methods.
  TestScheduledHandleShape  — ScheduledHandle dataclass is frozen and has the listed fields.
  TestCancelResultShape     — CancelResult dataclass is frozen and has the listed fields.
  TestBackendDispatch       — get_backend() returns the right backend per platform.
"""

from __future__ import annotations

import dataclasses
import unittest
from pathlib import Path

from cortex_command.overnight.scheduler import (
    CancelResult,
    ScheduledHandle,
    Scheduler,
    get_backend,
)
from cortex_command.overnight.scheduler import dispatch as dispatch_mod
from cortex_command.overnight.scheduler.dispatch import _UnsupportedScheduler
from cortex_command.overnight.scheduler.macos import MacOSLaunchAgentBackend


# ---------------------------------------------------------------------------
# TestProtocolShape
# ---------------------------------------------------------------------------
class TestProtocolShape(unittest.TestCase):
    """The Scheduler Protocol must expose the four agreed methods."""

    def test_protocol_has_schedule(self) -> None:
        self.assertTrue(hasattr(Scheduler, "schedule"))

    def test_protocol_has_cancel(self) -> None:
        self.assertTrue(hasattr(Scheduler, "cancel"))

    def test_protocol_has_list_active(self) -> None:
        self.assertTrue(hasattr(Scheduler, "list_active"))

    def test_protocol_has_is_supported(self) -> None:
        self.assertTrue(hasattr(Scheduler, "is_supported"))

    def test_macos_backend_satisfies_protocol_methods(self) -> None:
        backend = MacOSLaunchAgentBackend()
        for name in ("schedule", "cancel", "list_active", "is_supported"):
            self.assertTrue(
                callable(getattr(backend, name, None)),
                f"MacOSLaunchAgentBackend missing callable method {name!r}",
            )

    def test_unsupported_scheduler_satisfies_protocol_methods(self) -> None:
        backend = _UnsupportedScheduler()
        for name in ("schedule", "cancel", "list_active", "is_supported"):
            self.assertTrue(
                callable(getattr(backend, name, None)),
                f"_UnsupportedScheduler missing callable method {name!r}",
            )


# ---------------------------------------------------------------------------
# TestScheduledHandleShape
# ---------------------------------------------------------------------------
class TestScheduledHandleShape(unittest.TestCase):
    """ScheduledHandle must be a frozen dataclass with the listed fields."""

    EXPECTED_FIELDS = (
        "label",
        "session_id",
        "plist_path",
        "launcher_path",
        "scheduled_for_iso",
        "created_at_iso",
    )

    def test_is_dataclass(self) -> None:
        self.assertTrue(dataclasses.is_dataclass(ScheduledHandle))

    def test_is_frozen(self) -> None:
        params = getattr(ScheduledHandle, "__dataclass_params__", None)
        self.assertIsNotNone(params)
        self.assertTrue(params.frozen, "ScheduledHandle must be frozen")

    def test_has_expected_fields(self) -> None:
        names = tuple(f.name for f in dataclasses.fields(ScheduledHandle))
        self.assertEqual(names, self.EXPECTED_FIELDS)

    def test_can_construct_with_fields(self) -> None:
        handle = ScheduledHandle(
            label="com.cortex.overnight.abc",
            session_id="abc",
            plist_path=Path("/tmp/foo.plist"),
            launcher_path=Path("/tmp/foo.sh"),
            scheduled_for_iso="2026-05-04T20:00:00+00:00",
            created_at_iso="2026-05-04T19:00:00+00:00",
        )
        self.assertEqual(handle.label, "com.cortex.overnight.abc")
        self.assertEqual(handle.session_id, "abc")


# ---------------------------------------------------------------------------
# TestCancelResultShape
# ---------------------------------------------------------------------------
class TestCancelResultShape(unittest.TestCase):
    """CancelResult must be a frozen dataclass with the listed fields."""

    EXPECTED_FIELDS = (
        "label",
        "bootout_exit_code",
        "sidecar_removed",
        "plist_removed",
        "launcher_removed",
    )

    def test_is_dataclass(self) -> None:
        self.assertTrue(dataclasses.is_dataclass(CancelResult))

    def test_is_frozen(self) -> None:
        params = getattr(CancelResult, "__dataclass_params__", None)
        self.assertIsNotNone(params)
        self.assertTrue(params.frozen, "CancelResult must be frozen")

    def test_has_expected_fields(self) -> None:
        names = tuple(f.name for f in dataclasses.fields(CancelResult))
        self.assertEqual(names, self.EXPECTED_FIELDS)

    def test_can_construct_with_fields(self) -> None:
        result = CancelResult(
            label="com.cortex.overnight.abc",
            bootout_exit_code=0,
            sidecar_removed=True,
            plist_removed=True,
            launcher_removed=True,
        )
        self.assertEqual(result.bootout_exit_code, 0)
        self.assertTrue(result.sidecar_removed)


# ---------------------------------------------------------------------------
# TestBackendDispatch
# ---------------------------------------------------------------------------
class TestBackendDispatch(unittest.TestCase):
    """get_backend() must select per platform and respect is_supported()."""

    def test_returns_macos_backend_on_darwin(self) -> None:
        original = dispatch_mod.sys.platform
        try:
            dispatch_mod.sys.platform = "darwin"
            backend = get_backend()
        finally:
            dispatch_mod.sys.platform = original
        self.assertIsInstance(backend, MacOSLaunchAgentBackend)

    def test_returns_unsupported_on_non_darwin(self) -> None:
        original = dispatch_mod.sys.platform
        try:
            dispatch_mod.sys.platform = "linux"
            backend = get_backend()
        finally:
            dispatch_mod.sys.platform = original
        self.assertIsInstance(backend, _UnsupportedScheduler)

    def test_unsupported_is_supported_returns_false(self) -> None:
        self.assertFalse(_UnsupportedScheduler.is_supported())

    def test_unsupported_methods_raise_not_implemented(self) -> None:
        backend = _UnsupportedScheduler()
        from datetime import datetime, timezone

        with self.assertRaises(NotImplementedError):
            backend.schedule(
                target=datetime.now(timezone.utc),
                session_id="abc",
                env={},
                repo_root=Path("/tmp"),
            )
        with self.assertRaises(NotImplementedError):
            backend.cancel("com.cortex.overnight.abc")
        with self.assertRaises(NotImplementedError):
            backend.list_active()


if __name__ == "__main__":
    unittest.main()
