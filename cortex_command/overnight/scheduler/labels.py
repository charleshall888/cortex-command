"""launchd label minting and parsing for the overnight scheduler.

DR-6 of the spec defines the canonical label format:

    com.charleshall.cortex-command.overnight-schedule.{session_id}.{epoch_seconds}

Labels are never reused — the trailing epoch makes each launch a fresh
identifier even when ``session_id`` is recycled.

This module is intentionally pure (no I/O, no subprocess) so it can be
imported anywhere in the scheduler package without ordering concerns.
"""

from __future__ import annotations

import time

LABEL_PREFIX = "com.charleshall.cortex-command.overnight-schedule"


def mint_label(session_id: str, now_epoch: int | None = None) -> str:
    """Build a launchd label for ``session_id`` at the given epoch.

    Args:
        session_id: Overnight session identifier. Must not contain a
            literal ``"."`` because the label uses dots as field
            separators.
        now_epoch: Optional explicit epoch-seconds value. Defaults to
            ``int(time.time())``. Tests inject deterministic values via
            this argument; the same argument is also used by the
            collision-retry path (epoch + 1).

    Returns:
        Fully-qualified launchd label string.
    """
    if not session_id:
        raise ValueError("session_id must be non-empty")
    if "." in session_id:
        raise ValueError(
            f"session_id must not contain '.' (got {session_id!r})"
        )
    epoch = int(time.time()) if now_epoch is None else int(now_epoch)
    return f"{LABEL_PREFIX}.{session_id}.{epoch}"


def parse_label(label: str) -> tuple[str, int]:
    """Parse a label produced by :func:`mint_label`.

    Args:
        label: Label string to parse.

    Returns:
        Tuple of ``(session_id, epoch_seconds)``.

    Raises:
        ValueError: If ``label`` does not begin with the expected prefix
            or its trailing epoch component is not an integer.
    """
    expected_prefix = f"{LABEL_PREFIX}."
    if not label.startswith(expected_prefix):
        raise ValueError(
            f"label does not start with expected prefix {expected_prefix!r}: "
            f"{label!r}"
        )
    remainder = label[len(expected_prefix) :]
    # Split from the right so the session_id can in principle contain
    # extra dots in the future without ambiguity (current mint_label
    # rejects them, but parse should be lenient).
    try:
        session_id, epoch_str = remainder.rsplit(".", 1)
    except ValueError as exc:
        raise ValueError(
            f"label missing epoch suffix: {label!r}"
        ) from exc
    if not session_id:
        raise ValueError(f"label has empty session_id: {label!r}")
    try:
        epoch = int(epoch_str)
    except ValueError as exc:
        raise ValueError(
            f"label epoch suffix not an integer ({epoch_str!r}): {label!r}"
        ) from exc
    return session_id, epoch
