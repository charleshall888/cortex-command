"""Unit tests for ``verify_reviewer_output`` in ``cortex_command.critical_review``.

Exercises the reviewer-side sentinel parser at the function-call layer
(not the CLI surface — CLI coverage is implicit in the function tests).

Coverage map:

  Fixture-driven (Phase 1 corpus at
  ``tests/fixtures/critical-review/reviewer-outputs/``):
    - case-ok-line-1                  — sentinel at line 1
    - case-ok-after-preamble          — sentinel at line 3
    - case-ok-deeper-preamble         — sentinel at line 11 (a.k.a.
      "deeper preamble" — the line number is 11, not 15, but the
      semantics are identical: deep-preamble pass within the 50-line
      default window)
    - case-absent                     — no sentinel
    - case-mismatch                   — sentinel present, wrong SHA
    - case-adversarial-quoted-sha     — quoted decoy at line 3, real
      sentinel at line 8: OK-first precedence regression case

  Inline-string (edge cases the fixture corpus does not exercise):
    - sentinel past the 50-line window      — returns ("absent", None)
    - READ_FAILED quote then real READ_OK    — returns ("ok", expected_sha)
    - quoted-OK-wrong-sha then real READ_FAILED — returns ("read_failed", reason)
    - blockquoted (``> READ_OK: …``) sentinel — rejected (anchor enforcement)
    - BOM-prefixed line 1 + sentinel on line 2 — passes
    - CRLF line endings on line-1 sentinel    — passes
    - READ_FAILED only (no READ_OK)           — returns ("read_failed", reason)
    - window-size default boundary             — line 50 passes, line 51 absent
"""

from __future__ import annotations

import json
import pathlib

from cortex_command.critical_review import verify_reviewer_output


# ---------------------------------------------------------------------------
# Fixture location
# ---------------------------------------------------------------------------

FIXTURE_DIR = (
    pathlib.Path(__file__).parent
    / "fixtures"
    / "critical-review"
    / "reviewer-outputs"
)


def _load_case(name: str) -> tuple[str, dict]:
    """Return ``(reviewer_output_text, meta_dict)`` for a fixture stem."""
    text = (FIXTURE_DIR / f"{name}.txt").read_text(encoding="utf-8")
    meta = json.loads((FIXTURE_DIR / f"{name}.meta.json").read_text())
    return text, meta


# ---------------------------------------------------------------------------
# (1) Fixture-driven tests
# ---------------------------------------------------------------------------


def test_sentinel_at_line_1_pass() -> None:
    """``case-ok-line-1`` — sentinel on line 1 returns ("ok", expected_sha)."""
    output, meta = _load_case("case-ok-line-1")
    expected_sha = meta["expected_sha"]
    assert verify_reviewer_output(output, expected_sha) == ("ok", expected_sha)


def test_sentinel_at_line_3_after_preamble_pass() -> None:
    """``case-ok-after-preamble`` — sentinel on line 3 returns ("ok", expected_sha)."""
    output, meta = _load_case("case-ok-after-preamble")
    expected_sha = meta["expected_sha"]
    assert verify_reviewer_output(output, expected_sha) == ("ok", expected_sha)


def test_sentinel_at_line_15_pass() -> None:
    """``case-ok-deeper-preamble`` — sentinel on line 11 returns ("ok", expected_sha).

    The test name preserves the "line 15" label from the task spec for
    cross-reference, but the actual Task-3a fixture places the sentinel
    at line 11. Both line 11 and line 15 are "deeper preamble" within the
    50-line default window — semantically identical for parser coverage.
    """
    output, meta = _load_case("case-ok-deeper-preamble")
    expected_sha = meta["expected_sha"]
    assert verify_reviewer_output(output, expected_sha) == ("ok", expected_sha)


def test_sentinel_absent_returns_absent() -> None:
    """``case-absent`` — no sentinel anywhere returns ("absent", None)."""
    output, meta = _load_case("case-absent")
    expected_sha = meta["expected_sha"]
    assert verify_reviewer_output(output, expected_sha) == ("absent", None)


def test_sentinel_with_wrong_sha_returns_mismatch() -> None:
    """``case-mismatch`` — sentinel present, SHA wrong, returns ("mismatch", observed)."""
    output, meta = _load_case("case-mismatch")
    expected_sha = meta["expected_sha"]
    observed_sha = meta["observed_sha_in_fixture"]
    assert verify_reviewer_output(output, expected_sha) == (
        "mismatch",
        observed_sha,
    )


def test_multiple_sentinels_first_matching_sha_wins() -> None:
    """``case-adversarial-quoted-sha`` — load-bearing OK-first precedence.

    Line 3 has a quoted ``READ_OK:`` with the WRONG SHA; line 8 has the
    real ``READ_OK:`` with the EXPECTED SHA. A correct first-match-
    matching-SHA parser routes to line 8 and returns ("ok", expected_sha).
    A naive first-position parser would misclassify as ("mismatch", decoy).
    """
    output, meta = _load_case("case-adversarial-quoted-sha")
    expected_sha = meta["expected_sha"]
    assert verify_reviewer_output(output, expected_sha) == ("ok", expected_sha)


# ---------------------------------------------------------------------------
# (2) Inline-string edge cases
# ---------------------------------------------------------------------------


def test_sentinel_in_evidence_quote_past_window_returns_absent() -> None:
    """A sentinel at line 55 is outside the 50-line default window.

    Builds 54 lines of preamble (line numbers 1..54), then places the
    sentinel on line 55. ``verify_reviewer_output`` should ignore it.
    """
    expected_sha = "0" * 64
    preamble = "\n".join([f"preamble line {i}" for i in range(1, 55)])
    output = preamble + f"\nREAD_OK: /p {expected_sha}\n"
    # Sanity-check: the sentinel is at line 55 (1-indexed).
    assert output.splitlines()[54] == f"READ_OK: /p {expected_sha}"
    assert verify_reviewer_output(output, expected_sha) == ("absent", None)


def test_quoted_read_failed_before_real_read_ok_returns_ok() -> None:
    """READ_FAILED earlier than a matching READ_OK must not preempt success.

    Line 2 quotes a ``READ_FAILED`` token; line 5 carries the real
    matching ``READ_OK``. OK-first precedence: ("ok", expected_sha).
    """
    expected_sha = "a" * 64
    output = "\n".join(
        [
            "Preamble line 1.",
            "READ_FAILED: /quoted/path crashed",
            "More preamble line 3.",
            "Even more preamble line 4.",
            f"READ_OK: /real/path {expected_sha}",
        ]
    )
    assert verify_reviewer_output(output, expected_sha) == ("ok", expected_sha)


def test_quoted_read_ok_wrong_sha_before_real_read_failed_returns_read_failed() -> None:
    """A quoted READ_OK with wrong SHA, then a real READ_FAILED, must route to read_failed.

    No matching READ_OK anywhere ⇒ failed-route takes precedence over a
    mismatched-OK report, so ("read_failed", reason).
    """
    expected_sha = "b" * 64
    wrong_sha = "c" * 64
    output = "\n".join(
        [
            "Preamble line 1.",
            "Preamble line 2.",
            f"READ_OK: /quoted/path {wrong_sha}",
            "More preamble line 4.",
            "More preamble line 5.",
            "More preamble line 6.",
            "More preamble line 7.",
            "READ_FAILED: /real/path crashed",
        ]
    )
    assert verify_reviewer_output(output, expected_sha) == ("read_failed", "crashed")


def test_blockquoted_sentinel_is_rejected() -> None:
    """A ``> READ_OK:`` blockquoted sentinel is rejected (anchor enforcement).

    The regex anchors ``READ_OK:`` at column 0 of each line. A leading
    ``> `` (markdown blockquote) prevents the match. Result: absent.
    """
    expected_sha = "d" * 64
    output = f"> READ_OK: /p {expected_sha}\n"
    assert verify_reviewer_output(output, expected_sha) == ("absent", None)


def test_bom_prefixed_first_line_pass() -> None:
    """A UTF-8 BOM-prefixed line 1 followed by a sentinel on line 2 passes.

    The BOM (U+FEFF) sits on line 1 as preamble; the regex sees a clean
    anchored ``READ_OK:`` on line 2.
    """
    expected_sha = "e" * 64
    output = f"﻿some BOM-prefixed preamble\nREAD_OK: /p {expected_sha}\n"
    assert verify_reviewer_output(output, expected_sha) == ("ok", expected_sha)


def test_crlf_line_endings_pass() -> None:
    """CRLF line endings are normalized via ``splitlines()`` and the sentinel passes."""
    expected_sha = "f" * 64
    output = f"READ_OK: /p {expected_sha}\r\nsome trailing CRLF prose\r\n"
    assert verify_reviewer_output(output, expected_sha) == ("ok", expected_sha)


def test_read_failed_route() -> None:
    """A bare ``READ_FAILED`` with no ``READ_OK`` anywhere returns ("read_failed", reason)."""
    expected_sha = "9" * 64
    output = "\n".join(
        [
            "Preamble line 1.",
            "READ_FAILED: /p reason_token",
            "Trailing prose line 3.",
        ]
    )
    assert verify_reviewer_output(output, expected_sha) == (
        "read_failed",
        "reason_token",
    )


def test_window_size_default_is_50() -> None:
    """Boundary: sentinel at line 50 passes; sentinel at line 51 is absent."""
    expected_sha = "1" * 64
    # 49 preamble lines + sentinel on line 50 (1-indexed).
    on_line_50 = "\n".join(["x"] * 49) + f"\nREAD_OK: /p {expected_sha}"
    assert verify_reviewer_output(on_line_50, expected_sha) == ("ok", expected_sha)

    # One more preamble line pushes the sentinel to line 51 (outside window).
    on_line_51 = "\n".join(["x"] * 50) + f"\nREAD_OK: /p {expected_sha}"
    assert verify_reviewer_output(on_line_51, expected_sha) == ("absent", None)
