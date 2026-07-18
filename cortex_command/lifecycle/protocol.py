"""Protocol handshake constant for the served lifecycle loop.

The served next/advance loop is a **two-sided** system: a wheel (these Python
verbs, installed as a distribution) serves JSON payloads, and a prose loop (the
cortex-core plugin's skill markdown) consumes them. When the installed wheel and
the plugin prose drift out of sync — a *distribution-lag* phenomenon, since both
sides move together in this repo — the loop must be able to detect it.

The mechanism is a single additive ``protocol`` integer stamped into every verb
payload. The integer is declared **once per layer**:

- **This constant** (``PROTOCOL_VERSION``) states what the *wheel* serves.
- A **plugin-side expectation file**
  (``skills/lifecycle/references/protocol-expectation.txt``, mirrored into the
  cortex-core plugin tree beside the loop prose that reads it) states the compat
  *range* the *prose* expects, versioned in the same commit as the prose.

Compat is **always range-based, never exact-equality**: the plugin declares a
``[min, max]`` inclusive range and any served ``PROTOCOL_VERSION`` inside it is
compatible. Both sides advance together in-repo (a parity test asserts this
constant lies within the plugin file's range at HEAD); only distribution
introduces skew, which the per-verb payload check catches at the consumer.

``PROTOCOL_VERSION`` is **append-only**: bump it (never reuse or decrement) when
a payload change is not backward-compatible for the prose, and move the plugin
expectation range in the same commit. A bump that would strand out-of-repo
consumers is a *protocol-floor* decision made deliberately by the operator.
"""

from __future__ import annotations

from typing import Any, Literal, Mapping

# The protocol integer this wheel serves. Append-only; range-compared against the
# plugin-side expectation file — never exact-equality. See module docstring.
# 2: spec-approve may return state "approved-direct" (the specify->implement
#    short road) — prose predating the fork has no route for that state.
PROTOCOL_VERSION = 2

# --- Wheel-side compat evaluator (R7 substrate) ---------------------------------
#
# The Phase-5 loop and Task 13's ``next`` verb call ``classify_protocol`` to decide
# whether a served payload is compatible with the range the prose expects. It is a
# **pure** classification function: the CALLER reads the plugin expectation file
# (``skills/lifecycle/references/protocol-expectation.txt``) and passes ``min``/
# ``max`` in as ``expected_min``/``expected_max``. That caller-supplied expectation
# is what makes the fresh-plugin/stale-wheel direction — where the expectation's
# floor is NEWER (higher) than the served value — exercisable in a test.
#
# The three classifications match the spec vocabulary exactly:
#   - ``"ok"``          — ``protocol`` present and within ``[expected_min, expected_max]``.
#   - ``"legacy"``      — ``protocol`` field absent: a wheel predating the field.
#   - ``"out-of-range"``— ``protocol`` present but outside the inclusive range;
#                         includes the stale-wheel direction (served < expected_min)
#                         and the too-new-wheel direction (served > expected_max).
#
# Loop-side halt behavior and the ``{"state": "protocol-skew"}`` envelope are
# Phase 3/5 (Tasks 13/19); this module ships only the substrate + template.

COMPAT_OK: Literal["ok"] = "ok"
COMPAT_LEGACY: Literal["legacy"] = "legacy"
COMPAT_OUT_OF_RANGE: Literal["out-of-range"] = "out-of-range"

# The field every verb payload stamps (``result["protocol"] = PROTOCOL_VERSION``).
_PROTOCOL_FIELD = "protocol"


def classify_protocol(
    payload: Mapping[str, Any],
    *,
    expected_min: int,
    expected_max: int,
) -> Literal["ok", "legacy", "out-of-range"]:
    """Classify a served verb payload against a caller-supplied compat range.

    ``payload`` is a served verb payload (a ``dict``/mapping that, on a
    current wheel, carries an integer ``"protocol"`` field). ``expected_min`` and
    ``expected_max`` are the INCLUSIVE bounds the CALLER read from the plugin-side
    expectation file — never read here, keeping this a pure function with no I/O.

    Returns one of ``"ok"`` / ``"legacy"`` / ``"out-of-range"``:

    - ``"legacy"`` when the ``"protocol"`` field is absent (or ``None``) — an old
      wheel that predates the field.
    - ``"ok"`` when present and ``expected_min <= protocol <= expected_max``.
    - ``"out-of-range"`` when present but below ``expected_min`` (stale wheel /
      fresh plugin) or above ``expected_max`` (wheel newer than this prose).
    """
    served = payload.get(_PROTOCOL_FIELD)
    if served is None:
        return COMPAT_LEGACY
    if expected_min <= served <= expected_max:
        return COMPAT_OK
    return COMPAT_OUT_OF_RANGE


# The reinstall the operator runs to bring the installed wheel back into the
# plugin's compat range — the same command the bin-wrapper exit-2 messages emit
# (the copy-pasteable remediation template referenced by operator req 8).
REMEDIATION_COMMAND = (
    "uv tool install --reinstall --refresh "
    "git+https://github.com/charleshall888/cortex-command.git@<latest-tag>"
)

# Copy-pasteable remediation message template. ``str.format``-fillable with the
# named fields ``served`` / ``expected_min`` / ``expected_max`` / ``command`` —
# use ``remediation_message(...)`` to fill it. Loop-side callers (Tasks 13/19)
# surface this when ``classify_protocol`` returns ``"legacy"`` or ``"out-of-range"``.
REMEDIATION_TEMPLATE = (
    "protocol skew: the installed cortex-command wheel serves protocol {served} "
    "but this plugin's loop expects the inclusive range [{expected_min}, {expected_max}]. "
    "The wheel is out of sync with the plugin prose. To fix, run:\n"
    "  {command}\n"
    "then restart the session. If this happens after a recent upgrade, your wheel "
    "may be stale; a SessionStart background install initiates healing, but the "
    "loop stays halted until the wheel matches."
)


def remediation_message(
    *,
    served: int | None,
    expected_min: int,
    expected_max: int,
) -> str:
    """Render the copy-pasteable skew-remediation message.

    ``served`` is the payload's ``protocol`` value (``None`` for a legacy payload
    with no field); ``expected_min``/``expected_max`` are the caller-supplied
    range. Names ``REMEDIATION_COMMAND`` — the reinstall the operator runs.
    """
    served_label = "<absent>" if served is None else served
    return REMEDIATION_TEMPLATE.format(
        served=served_label,
        expected_min=expected_min,
        expected_max=expected_max,
        command=REMEDIATION_COMMAND,
    )
