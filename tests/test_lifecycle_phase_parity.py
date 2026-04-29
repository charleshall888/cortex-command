#!/usr/bin/env python3
"""Three-layer parity tests for lifecycle phase detection (R12).

Layer 12a — Hook glue unit test
    Asserts byte-equality of the bash glue function `encode_phase`
    (defined in hooks/cortex-scan-lifecycle.sh) against the R3 normative
    wire-format encoding for a fixture matrix of (phase, checked, total,
    cycle) tuples.

Layer 12b — Statusline ladder + parser vs canonical Python
    Two sub-tests source distinct fragments of `claude/statusline.sh` into
    isolated bash harnesses. The "ladder" sub-test asserts that the
    upstream phase-detection block (the `_lc_phase=""` ladder) emits a
    wire-format string equivalent to what the canonical
    `detect_lifecycle_phase()` returns for the same fixture directory,
    excluding the cycle dimension (statusline-side cycle-blindness is
    structural — see R11 / Non-Requirements). The "parser" sub-test
    asserts that the downstream wire-format parser block (the
    `_lc_single_phase` case statement) handles every R12a wire-format
    value without crashing or producing malformed output.

Layer 12c (hook end-to-end) is delivered by a sibling task; this file is
the home for that test class when it lands.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from cortex_command.common import detect_lifecycle_phase


REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK_PATH = REPO_ROOT / "hooks" / "cortex-scan-lifecycle.sh"
STATUSLINE_PATH = REPO_ROOT / "claude" / "statusline.sh"
PARITY_FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "lifecycle_phase_parity"


# Fixture matrix: (phase, checked, total, cycle, expected_emit)
# Verbatim from spec R12a (≥10 cases). Each tuple maps the canonical
# detector's dict shape (R1) to the glue function's wire-format string (R3).
GLUE_FIXTURES: list[tuple[str, int, int, int, str]] = [
    ("research", 0, 0, 1, "research"),
    ("implement", 0, 0, 1, "implement:0/0"),
    ("implement", 2, 5, 1, "implement:2/5"),
    ("implement-rework", 0, 0, 1, "implement-rework:1"),
    ("implement-rework", 3, 5, 2, "implement-rework:2"),
    ("review", 5, 5, 1, "review"),
    ("complete", 5, 5, 1, "complete"),
    ("escalated", 0, 0, 1, "escalated"),
    ("plan", 0, 0, 1, "plan"),
    ("specify", 0, 0, 1, "specify"),
]


def _extract_encode_phase_function() -> str:
    """Extract just the `encode_phase` bash function definition from the hook.

    Sourcing the entire hook is impractical: the hook reads stdin at the top
    and has executable side effects. Instead we slice out the function block
    by regex and execute it in isolation.
    """
    src = HOOK_PATH.read_text()
    match = re.search(
        r"^encode_phase\(\)\s*\{.*?^\}\s*$",
        src,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise RuntimeError(
            f"Could not locate encode_phase() in {HOOK_PATH}. "
            "Hook structure may have changed; update test extractor."
        )
    return match.group(0)


def _invoke_encode_phase(phase: str, checked: int, total: int, cycle: int) -> str:
    """Source the extracted glue fragment and call encode_phase, capturing stdout."""
    fragment = _extract_encode_phase_function()
    script = f"""
set -euo pipefail
{fragment}
encode_phase {phase!r} {int(checked)} {int(total)} {int(cycle)}
"""
    proc = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        check=True,
    )
    # Strip the trailing newline that `echo` always adds; preserve any
    # internal characters (the wire format never contains newlines).
    return proc.stdout.rstrip("\n")


@pytest.mark.parametrize(
    "phase,checked,total,cycle,expected",
    GLUE_FIXTURES,
    ids=[f"{p}-{c}/{t}-cycle{cy}" for p, c, t, cy, _ in GLUE_FIXTURES],
)
def test_hook_glue(
    phase: str,
    checked: int,
    total: int,
    cycle: int,
    expected: str,
) -> None:
    """R12a: bash `encode_phase` glue produces byte-equal R3 wire-format output."""
    actual = _invoke_encode_phase(phase, checked, total, cycle)
    assert actual == expected, (
        f"encode_phase({phase!r}, {checked}, {total}, {cycle}) "
        f"emitted {actual!r}, expected {expected!r}"
    )


# ---------------------------------------------------------------------------
# R12b — Statusline ladder + parser vs canonical Python
# ---------------------------------------------------------------------------
#
# The statusline at claude/statusline.sh is a bash-only mirror of the
# canonical Python detector (Task 10 documented this; structural exception
# per R11 driven by the < 500ms render-latency budget). This test class
# enforces equivalence at TWO sub-surfaces:
#
#   Ladder (upstream):  fixture dir → wire-format string  vs  canonical Python
#   Parser (downstream): wire-format string → render output (must not crash)
#
# The cycle dimension is excluded from the upstream comparison because the
# statusline ladder reads only `verdict`, never `cycle` (verified at
# claude/statusline.sh L394-401). This is the documented statusline-side
# cycle-blindness exception. R12a (glue unit) and R12c (hook end-to-end)
# enforce cycle correctness from the other side.


def _extract_statusline_ladder() -> str:
    """Slice the L377-415-ish phase-detection ladder out of statusline.sh.

    The ladder content has shifted with documenting comments inserted by
    Task 10 above L377 — re-locate by content, not line number. The block
    starts with `_lc_phase=""` (the variable initialiser at the top of the
    ladder) and ends with the `_lc_phase="research"` default fallback
    line. We slice between those two anchors.
    """
    src = STATUSLINE_PATH.read_text()
    # Anchor on the literal `_lc_phase=""` initialiser. There is exactly
    # one such occurrence in statusline.sh; if duplicates appear, the
    # extractor fails loudly so the test author can investigate.
    init_pattern = r'^\s*_lc_phase=""\s*$'
    init_matches = list(re.finditer(init_pattern, src, re.MULTILINE))
    if len(init_matches) != 1:
        raise RuntimeError(
            f"Expected exactly one `_lc_phase=\"\"` in {STATUSLINE_PATH}; "
            f"found {len(init_matches)}. Statusline structure has drifted; "
            "update the parity test extractor."
        )
    start = init_matches[0].start()
    # End anchor: the `_lc_phase="research"` default. Match the line that
    # contains it as a whole-line statement (not the case-arm).
    end_pattern = r'_lc_phase="research"\s*$'
    end_match = re.search(end_pattern, src[start:], re.MULTILINE)
    if not end_match:
        raise RuntimeError(
            f"Could not find `_lc_phase=\"research\"` end anchor in "
            f"{STATUSLINE_PATH} after the ladder init."
        )
    end = start + end_match.end()
    return src[start:end]


def _extract_statusline_parser() -> str:
    """Slice the wire-format parser block (case "$_lc_single_phase") out.

    The parser block begins at the `case "$_lc_single_phase" in` header
    and ends at the matching `esac`. We do not include the surrounding
    `_lc_append` calls (they require helper functions); the harness
    provides stub implementations of those.
    """
    src = STATUSLINE_PATH.read_text()
    match = re.search(
        r'case\s+"\$_lc_single_phase"\s+in.*?^\s*esac\s*$',
        src,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise RuntimeError(
            f"Could not locate `case \"$_lc_single_phase\" in ... esac` "
            f"block in {STATUSLINE_PATH}; parser structure has drifted."
        )
    return match.group(0)


def _invoke_statusline_ladder(fixture_dir: Path) -> str:
    """Source the ladder fragment with `_lc_fdir` set; return emitted `_lc_phase`.

    The ladder writes its result into the `_lc_phase` variable. We echo it
    after the ladder block runs and capture stdout. The wire-format string
    is one of: "research", "specify", "plan", "implement:N/M", "review",
    "implement-rework" (BARE — statusline does not emit cycle), "escalated",
    or "complete".
    """
    ladder = _extract_statusline_ladder()
    script = f"""
set -euo pipefail
_lc_fdir={str(fixture_dir)!r}
{ladder}
printf '%s' "$_lc_phase"
"""
    proc = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout


def _invoke_statusline_parser(wire_value: str) -> str:
    """Source the parser case-block with `_lc_single_phase` set; return display string.

    The parser sets `_lc_display` (and may also call `_lc_append` for the
    `implement:*` arm). We provide stubs for the helper functions and
    capture `_lc_display` (or the appended line) on stdout. The assertion
    is "no crash, produces some output," not a specific display string.
    """
    parser = _extract_statusline_parser()
    # Stubs for the helper functions referenced inside the parser block.
    # progress_bar is required for the `implement:*` arm; _lc_phase_icon
    # is referenced just before the case (we don't include that line, but
    # we keep the stub for safety in case the slice grows). _lc_append
    # writes to stdout for capture.
    script = f"""
set -euo pipefail
progress_bar() {{ printf 'BAR'; }}
_lc_phase_icon() {{ printf 'ICON'; }}
_lc_append() {{ printf '%s\\n' "$1"; }}
_lc_icon_color=''
_lc_name_color=''
_lc_rst=''
_lc_single_name='example'
_lc_single_phase={wire_value!r}
_lc_icon="$(_lc_phase_icon "$_lc_single_phase")"
{parser}
# If we fell through to the default `*` arm or any non-implement arm,
# emit the resolved display string so the harness can capture it.
printf 'DISPLAY:%s\\n' "${{_lc_display:-}}"
"""
    proc = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"Statusline parser crashed on wire value {wire_value!r}: "
            f"rc={proc.returncode}, stderr={proc.stderr!r}"
        )
    return proc.stdout


def _parse_statusline_phase(emitted: str) -> tuple[str, int, int]:
    """Parse the statusline's emitted `_lc_phase` back into (phase, checked, total).

    The statusline emits one of:
      - bare phase string: "research", "specify", "plan", "review",
        "complete", "escalated", "implement-rework"
      - "implement:N/M" with progress fraction

    Cycle is NOT emitted by the ladder (structural cycle-blindness); the
    caller compares against the canonical detector's dict EXCLUDING cycle.
    """
    if emitted.startswith("implement:"):
        frac = emitted[len("implement:"):]
        checked_str, total_str = frac.split("/", 1)
        return ("implement", int(checked_str), int(total_str))
    # Bare phase string — checked/total default to 0 (no progress info on
    # the wire). The canonical detector reports the actual checked/total
    # for the phase, so we must skip those dimensions in the comparison
    # for bare-phase wire values.
    return (emitted, 0, 0)


_ladder_fixture_dirs = sorted(
    [d for d in PARITY_FIXTURE_DIR.iterdir() if d.is_dir()]
) if PARITY_FIXTURE_DIR.is_dir() else []


@pytest.mark.parametrize(
    "fixture_dir",
    _ladder_fixture_dirs,
    ids=[d.name for d in _ladder_fixture_dirs],
)
def test_statusline_ladder_matches_canonical(fixture_dir: Path) -> None:
    """R12b ladder: statusline phase ladder == canonical Python detector.

    Sources the L377-415-ish phase-detection block from claude/statusline.sh
    into a bash harness with `_lc_fdir` pre-set to a fixture directory,
    parses the resulting `_lc_phase` wire-format string, and asserts the
    parsed (phase, checked, total) tuple matches the canonical detector.

    Documented exception: the statusline ladder does not extract `cycle`
    from review.md (only `verdict`), so cycle is excluded from the
    comparison. When the canonical detector returns "implement-rework",
    the statusline emits BARE "implement-rework" (no `:N` cycle suffix);
    that is acceptable. The R12a glue unit and R12c hook end-to-end tests
    enforce cycle correctness from their respective surfaces.
    """
    canonical = detect_lifecycle_phase(fixture_dir)
    canonical_phase = canonical["phase"]

    statusline_emit = _invoke_statusline_ladder(fixture_dir)
    parsed_phase, parsed_checked, parsed_total = _parse_statusline_phase(
        statusline_emit
    )

    # Phase comparison. Statusline emits bare "implement-rework" (no cycle
    # suffix); canonical also emits "implement-rework". They match.
    assert parsed_phase == canonical_phase, (
        f"Statusline ladder emitted {statusline_emit!r} for {fixture_dir.name}, "
        f"parsed phase {parsed_phase!r}, but canonical Python returned "
        f"phase {canonical_phase!r}"
    )

    # checked/total comparison: only meaningful for the "implement" wire
    # format (which carries N/M). For bare-phase emits, the statusline
    # does not communicate checked/total, so we skip those dimensions.
    if statusline_emit.startswith("implement:"):
        assert parsed_checked == canonical["checked"], (
            f"Statusline emit {statusline_emit!r} for {fixture_dir.name} "
            f"parsed checked={parsed_checked}, canonical={canonical['checked']}"
        )
        assert parsed_total == canonical["total"], (
            f"Statusline emit {statusline_emit!r} for {fixture_dir.name} "
            f"parsed total={parsed_total}, canonical={canonical['total']}"
        )


# Wire-format strings produced by the hook glue per R3 / R12a. The parser
# sub-test asserts that the statusline's downstream parser handles every
# one of these without crashing or producing empty output.
_PARSER_WIRE_VALUES: list[str] = [
    "research",
    "implement:0/0",
    "implement:2/5",
    "implement-rework:1",
    "implement-rework:2",
    "review",
    "complete",
    "escalated",
    "plan",
    "specify",
]


@pytest.mark.parametrize("wire_value", _PARSER_WIRE_VALUES)
def test_statusline_parser_handles_wire_values(wire_value: str) -> None:
    """R12b parser: statusline wire-format parser handles every R12a value.

    Sources the L500-562-ish `case "$_lc_single_phase"` block from
    claude/statusline.sh into a bash harness with `_lc_single_phase` set
    to each wire-format string from R12a. The exact rendered display
    string is implementation-defined; the assertion is "the parser does
    not crash, fall through silently, or produce empty output for any
    wire-format value the hook glue can emit."

    Critically verifies that the new "implement-rework:N" vocabulary
    introduced by R3 does not trip the parser (the BARE `implement-rework`
    case in the parser does not match the cycle-suffixed wire format, so
    such values fall through to the default `*` arm — non-crashing
    behavior, which is acceptable per the spec).
    """
    output = _invoke_statusline_parser(wire_value)
    # Output is either the implement:* arm's _lc_append line, or the
    # final DISPLAY:<value> emit, or both. In all cases the harness
    # should produce non-empty output for a successful run.
    assert output, (
        f"Statusline parser produced no output for wire value {wire_value!r}; "
        "expected at least a DISPLAY: line or an _lc_append emit."
    )
    # Stronger check: confirm we got at least one of the two known emit
    # forms. This catches a parser arm that silently sets _lc_display=""
    # without going through the implement:* path.
    has_display = "DISPLAY:" in output
    has_append = output.strip() and not output.strip().startswith("DISPLAY:")
    assert has_display or has_append, (
        f"Statusline parser output for {wire_value!r} does not contain "
        f"either a DISPLAY: line or an _lc_append emit. Output: {output!r}"
    )
    # If we hit the DISPLAY: line, the resolved display string must be
    # non-empty (catches a silent fall-through that sets _lc_display="").
    if has_display:
        for line in output.splitlines():
            if line.startswith("DISPLAY:"):
                resolved = line[len("DISPLAY:"):]
                assert resolved, (
                    f"Statusline parser fell through to default arm with "
                    f"empty _lc_display for wire value {wire_value!r}."
                )
                break
