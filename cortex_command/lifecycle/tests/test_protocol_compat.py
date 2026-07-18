"""Tests for the wheel-side compat evaluator and remediation template (R7).

``classify_protocol`` is a pure classification function: the caller reads the
plugin-side expectation file and passes ``expected_min``/``expected_max`` in, so
these tests drive it with hand-built payloads and hand-supplied ranges. That
caller-supplied expectation is what makes the fresh-plugin/stale-wheel direction
(expectation floor NEWER than the served value) exercisable without a wheel bump.
"""

from __future__ import annotations

from cortex_command.lifecycle.protocol import (
    COMPAT_LEGACY,
    COMPAT_OK,
    COMPAT_OUT_OF_RANGE,
    PROTOCOL_VERSION,
    REMEDIATION_COMMAND,
    classify_protocol,
    remediation_message,
)


# --- classify_protocol: the three classifications -------------------------------


def test_ok_when_present_and_within_range() -> None:
    payload = {"state": "specify", "protocol": PROTOCOL_VERSION}
    assert (
        classify_protocol(payload, expected_min=1, expected_max=PROTOCOL_VERSION)
        == COMPAT_OK
    )


def test_ok_at_inclusive_bounds() -> None:
    # min and max are INCLUSIVE bounds.
    assert classify_protocol({"protocol": 2}, expected_min=2, expected_max=5) == COMPAT_OK
    assert classify_protocol({"protocol": 5}, expected_min=2, expected_max=5) == COMPAT_OK


def test_legacy_when_field_absent() -> None:
    # An old wheel that predates the protocol field: no "protocol" key.
    payload = {"state": "specify"}
    assert (
        classify_protocol(payload, expected_min=1, expected_max=1) == COMPAT_LEGACY
    )


def test_legacy_when_field_is_none() -> None:
    # A None-valued field is treated as absent (legacy).
    payload = {"state": "specify", "protocol": None}
    assert (
        classify_protocol(payload, expected_min=1, expected_max=1) == COMPAT_LEGACY
    )


def test_out_of_range_when_served_above_max() -> None:
    # Wheel newer than this prose understands (served > expected_max).
    payload = {"protocol": 3}
    assert (
        classify_protocol(payload, expected_min=1, expected_max=2)
        == COMPAT_OUT_OF_RANGE
    )


def test_out_of_range_when_expectation_newer_than_served() -> None:
    # Fresh plugin / stale wheel: the expectation's floor (min=2) is NEWER/higher
    # than the served value (1). Exercisable ONLY because the expectation is
    # caller-supplied — the wheel itself never serves a value below its own floor.
    payload = {"protocol": 1}
    assert (
        classify_protocol(payload, expected_min=2, expected_max=2)
        == COMPAT_OUT_OF_RANGE
    )


# --- remediation_message: the copy-pasteable template ---------------------------


def test_remediation_names_the_reinstall_command() -> None:
    msg = remediation_message(served=1, expected_min=2, expected_max=2)
    assert REMEDIATION_COMMAND in msg
    # Context the operator needs: served value and the expected range.
    assert "1" in msg
    assert "[2, 2]" in msg


def test_remediation_handles_absent_served_value() -> None:
    # Legacy payloads have no served value; the message renders without a number.
    msg = remediation_message(served=None, expected_min=1, expected_max=1)
    assert REMEDIATION_COMMAND in msg
    assert "<absent>" in msg
