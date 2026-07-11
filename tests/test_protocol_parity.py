"""Protocol handshake parity at HEAD.

The served lifecycle loop is two-sided: the wheel constant
(``cortex_command/lifecycle/protocol.py``'s ``PROTOCOL_VERSION``) declares what
the wheel serves; the plugin expectation file
(``skills/lifecycle/references/protocol-expectation.txt``) declares the inclusive
compat range the prose loop expects. Both sides move together *in this repo* — so
at HEAD the served value MUST lie within the expected range. Skew is only a
distribution-lag phenomenon (a shipped wheel older/newer than an installed
plugin), which the per-verb payload check catches at the consumer; it can never
occur within a single commit.

Compat is range-based, never exact-equality (the same range discipline the loop
uses at runtime). This test asserts the in-repo invariant:
``min <= PROTOCOL_VERSION <= max``.
"""

from __future__ import annotations

from pathlib import Path

from cortex_command.lifecycle.protocol import PROTOCOL_VERSION

REPO_ROOT = Path(__file__).resolve().parent.parent
EXPECTATION_FILE = (
    REPO_ROOT / "skills" / "lifecycle" / "references" / "protocol-expectation.txt"
)


def _parse_expectation(path: Path) -> dict[str, int]:
    """Parse the plugin expectation file into its integer keys.

    Format (documented in the file itself): ``key=value`` lines with integer
    values; ``#`` comment lines and blank lines ignored. This mirrors the parse
    the wheel-side compat evaluator and the loop perform on the same file.
    """
    values: dict[str, int] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = int(value.strip())
    return values


def test_expectation_file_exists_and_declares_a_range() -> None:
    assert EXPECTATION_FILE.is_file(), (
        f"missing plugin-side protocol expectation file at {EXPECTATION_FILE}"
    )
    expectation = _parse_expectation(EXPECTATION_FILE)
    assert "min" in expectation and "max" in expectation, (
        "expectation file must declare both `min` and `max` inclusive bounds"
    )
    assert expectation["min"] <= expectation["max"], (
        "expectation range is inverted: min must be <= max"
    )


def test_wheel_protocol_version_within_plugin_range_at_head() -> None:
    """The in-repo two-sided invariant: the served protocol integer lies within
    the plugin's expected compat range (range-based, never exact-equality)."""
    expectation = _parse_expectation(EXPECTATION_FILE)
    assert expectation["min"] <= PROTOCOL_VERSION <= expectation["max"], (
        f"wheel PROTOCOL_VERSION={PROTOCOL_VERSION} is outside the plugin "
        f"expectation range [{expectation['min']}, {expectation['max']}] at HEAD; "
        "both sides must move together in-repo."
    )
