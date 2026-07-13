"""Unit tests for ``check_artifact_stable`` in ``cortex_command.critical_review``.

Two layers of coverage live here:

  (A) the reviewer-side sentinel parser at the function-call layer
      (``check_artifact_stable`` — the fixture-driven and inline-string
      cases below); and
  (B) the CLI gate wrappers ``_cmd_check_artifact_stable`` /
      ``_cmd_check_synth_stable`` driven through ``main`` — the
      absent-sentinel gate-time re-hash disambiguation from spec
      ``critical-review-sentinel-gate-excludes-async`` R2/R3 (the
      ``TestArtifactStableWrapperRehash`` / ``TestSynthStableWrapperRehash``
      classes at the end of the file). The wrapper tests assert the three
      new absent-branch outcomes (advisory-pass, drift, unreadable) plus
      the no-``--artifact-path`` backward-compat exclusion, on BOTH
      wrappers.

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

import io
import json
import pathlib

import pytest

from cortex_command.critical_review import (
    check_artifact_stable,
    main as cr_main,
    sha256_of_path,
)


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
    assert check_artifact_stable(output, expected_sha) == ("ok", expected_sha)


def test_sentinel_at_line_3_after_preamble_pass() -> None:
    """``case-ok-after-preamble`` — sentinel on line 3 returns ("ok", expected_sha)."""
    output, meta = _load_case("case-ok-after-preamble")
    expected_sha = meta["expected_sha"]
    assert check_artifact_stable(output, expected_sha) == ("ok", expected_sha)


def test_sentinel_at_line_15_pass() -> None:
    """``case-ok-deeper-preamble`` — sentinel on line 11 returns ("ok", expected_sha).

    The test name preserves the "line 15" label from the task spec for
    cross-reference, but the actual Task-3a fixture places the sentinel
    at line 11. Both line 11 and line 15 are "deeper preamble" within the
    50-line default window — semantically identical for parser coverage.
    """
    output, meta = _load_case("case-ok-deeper-preamble")
    expected_sha = meta["expected_sha"]
    assert check_artifact_stable(output, expected_sha) == ("ok", expected_sha)


def test_sentinel_absent_returns_absent() -> None:
    """``case-absent`` — no sentinel anywhere returns ("absent", None)."""
    output, meta = _load_case("case-absent")
    expected_sha = meta["expected_sha"]
    assert check_artifact_stable(output, expected_sha) == ("absent", None)


def test_sentinel_with_wrong_sha_returns_mismatch() -> None:
    """``case-mismatch`` — sentinel present, SHA wrong, returns ("mismatch", observed)."""
    output, meta = _load_case("case-mismatch")
    expected_sha = meta["expected_sha"]
    observed_sha = meta["observed_sha_in_fixture"]
    assert check_artifact_stable(output, expected_sha) == (
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
    assert check_artifact_stable(output, expected_sha) == ("ok", expected_sha)


# ---------------------------------------------------------------------------
# (2) Inline-string edge cases
# ---------------------------------------------------------------------------


def test_sentinel_in_evidence_quote_past_window_returns_absent() -> None:
    """A sentinel at line 55 is outside the 50-line default window.

    Builds 54 lines of preamble (line numbers 1..54), then places the
    sentinel on line 55. ``check_artifact_stable`` should ignore it.
    """
    expected_sha = "0" * 64
    preamble = "\n".join([f"preamble line {i}" for i in range(1, 55)])
    output = preamble + f"\nREAD_OK: /p {expected_sha}\n"
    # Sanity-check: the sentinel is at line 55 (1-indexed).
    assert output.splitlines()[54] == f"READ_OK: /p {expected_sha}"
    assert check_artifact_stable(output, expected_sha) == ("absent", None)


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
    assert check_artifact_stable(output, expected_sha) == ("ok", expected_sha)


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
    assert check_artifact_stable(output, expected_sha) == ("read_failed", "crashed")


def test_blockquoted_sentinel_is_rejected() -> None:
    """A ``> READ_OK:`` blockquoted sentinel is rejected (anchor enforcement).

    The regex anchors ``READ_OK:`` at column 0 of each line. A leading
    ``> `` (markdown blockquote) prevents the match. Result: absent.
    """
    expected_sha = "d" * 64
    output = f"> READ_OK: /p {expected_sha}\n"
    assert check_artifact_stable(output, expected_sha) == ("absent", None)


def test_bom_prefixed_first_line_pass() -> None:
    """A UTF-8 BOM-prefixed line 1 followed by a sentinel on line 2 passes.

    The BOM (U+FEFF) sits on line 1 as preamble; the regex sees a clean
    anchored ``READ_OK:`` on line 2.
    """
    expected_sha = "e" * 64
    output = f"﻿some BOM-prefixed preamble\nREAD_OK: /p {expected_sha}\n"
    assert check_artifact_stable(output, expected_sha) == ("ok", expected_sha)


def test_crlf_line_endings_pass() -> None:
    """CRLF line endings are normalized via ``splitlines()`` and the sentinel passes."""
    expected_sha = "f" * 64
    output = f"READ_OK: /p {expected_sha}\r\nsome trailing CRLF prose\r\n"
    assert check_artifact_stable(output, expected_sha) == ("ok", expected_sha)


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
    assert check_artifact_stable(output, expected_sha) == (
        "read_failed",
        "reason_token",
    )


def test_window_size_default_is_50() -> None:
    """Boundary: sentinel at line 50 passes; sentinel at line 51 is absent."""
    expected_sha = "1" * 64
    # 49 preamble lines + sentinel on line 50 (1-indexed).
    on_line_50 = "\n".join(["x"] * 49) + f"\nREAD_OK: /p {expected_sha}"
    assert check_artifact_stable(on_line_50, expected_sha) == ("ok", expected_sha)

    # One more preamble line pushes the sentinel to line 51 (outside window).
    on_line_51 = "\n".join(["x"] * 50) + f"\nREAD_OK: /p {expected_sha}"
    assert check_artifact_stable(on_line_51, expected_sha) == ("absent", None)


# ---------------------------------------------------------------------------
# (3) CLI-wrapper gate-time re-hash tests
#     (spec critical-review-sentinel-gate-excludes-async, R2/R3)
# ---------------------------------------------------------------------------
#
# These drive the argparse entry point ``main`` against the two gate
# wrappers. On an ``absent`` pure-verifier result, an optional
# ``--artifact-path`` is re-hashed via ``sha256_of_path``:
#   - re-hash matches expected SHA  -> exit 0 + ``sentinel_advisory``
#   - re-hash differs (drift)        -> exit 3 (+ wrapper's drift event)
#   - path unreadable/deleted        -> exit 3
#   - ``--artifact-path`` omitted    -> exit 3 (today's behavior, unchanged)
#
# CRITICAL asymmetry (verified against the Task-2 implementation in
# ``cortex_command/critical_review/__init__.py``): the ARTIFACT wrapper's
# absent+drift branch emits ``sentinel_absence``; the SYNTH wrapper's
# absent+drift branch preserves its EXISTING behavior and emits
# ``synthesizer_drift`` (NOT ``sentinel_absence``). The advisory-clean
# event name is ``sentinel_advisory`` on both.
#
# The lifecycle dir is created in every case so the write-guard does not
# short-circuit to EXIT_TELEMETRY_SKIPPED (4); we are exercising the
# re-hash verdict (0 / 3), not the phantom-dir guard (covered by
# ``tests/test_critical_review_phantom_guard.py``).

SENTINEL_ABSENT_STABLE = "case-sentinel-absent-but-stable"


def _read_jsonl(path: pathlib.Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _invoke_check_artifact_stable(
    lifecycle_root: pathlib.Path,
    feature: str,
    input_file: pathlib.Path,
    expected_sha: str,
    artifact_path: pathlib.Path | None = None,
) -> int:
    """Drive ``check-artifact-stable`` through ``main`` (reviewer path)."""
    argv = [
        "--lifecycle-root",
        str(lifecycle_root),
        "check-artifact-stable",
        "--feature",
        feature,
        "--reviewer-angle",
        "code-quality",
        "--expected-sha",
        expected_sha,
        "--model-tier",
        "sonnet",
        "--input-file",
        str(input_file),
    ]
    if artifact_path is not None:
        argv += ["--artifact-path", str(artifact_path)]
    return cr_main(argv)


def _invoke_check_synth_stable(
    monkeypatch: pytest.MonkeyPatch,
    lifecycle_root: pathlib.Path,
    feature: str,
    stdin_text: str,
    expected_sha: str,
    artifact_path: pathlib.Path | None = None,
) -> int:
    """Drive ``check-synth-stable`` through ``main`` (synthesizer path)."""
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin_text))
    argv = [
        "--lifecycle-root",
        str(lifecycle_root),
        "check-synth-stable",
        "--feature",
        feature,
        "--expected-sha",
        expected_sha,
    ]
    if artifact_path is not None:
        argv += ["--artifact-path", str(artifact_path)]
    return cr_main(argv)


class TestArtifactStableWrapperRehash:
    """``_cmd_check_artifact_stable`` absent-branch re-hash disambiguation.

    The sentinel-free reviewer output (``case-sentinel-absent-but-stable``)
    drives the pure verifier's ``absent`` branch; the ``--artifact-path``
    re-hash decides advisory-pass vs. drift-exclusion.
    """

    def test_absent_stable_path_advisory_pass(self, tmp_path: pathlib.Path) -> None:
        """Absent sentinel + re-hash matches -> exit 0 + ``sentinel_advisory`` (R2)."""
        text, meta = _load_case(SENTINEL_ABSENT_STABLE)
        expected_sha = meta["expected_sha"]
        lifecycle_root = tmp_path / "cortex" / "lifecycle"
        feature = "advisory-feature"
        feature_dir = lifecycle_root / feature
        feature_dir.mkdir(parents=True)

        input_file = tmp_path / "reviewer-output.txt"
        input_file.write_text(text, encoding="utf-8")

        # The pinned artifact re-hashes to the expected SHA (proving no drift).
        pinned = tmp_path / "pinned-artifact.md"
        pinned.write_text(meta["pinned_artifact_content"], encoding="utf-8")
        # Fixture-integrity sanity: the declared expected_sha IS the real hash.
        assert sha256_of_path(str(pinned)) == expected_sha

        rc = _invoke_check_artifact_stable(
            lifecycle_root, feature, input_file, expected_sha, artifact_path=pinned
        )

        assert rc == 0
        rows = _read_jsonl(feature_dir / "events.log")
        assert len(rows) == 1
        assert rows[0]["event"] == "sentinel_advisory"
        assert rows[0]["feature"] == feature
        assert rows[0]["reviewer_angle"] == "code-quality"
        assert rows[0]["observed_sha_or_null"] == expected_sha
        # The advisory outcome MUST NOT emit a (forbidden) sentinel_absence row.
        assert all(r["event"] != "sentinel_absence" for r in rows)

    def test_absent_drifted_path_exit3_sentinel_absence(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Absent sentinel + re-hash differs -> exit 3 + ``sentinel_absence`` (R3)."""
        text, meta = _load_case(SENTINEL_ABSENT_STABLE)
        expected_sha = meta["expected_sha"]
        lifecycle_root = tmp_path / "cortex" / "lifecycle"
        feature = "drift-feature"
        feature_dir = lifecycle_root / feature
        feature_dir.mkdir(parents=True)

        input_file = tmp_path / "reviewer-output.txt"
        input_file.write_text(text, encoding="utf-8")

        drifted = tmp_path / "drifted-artifact.md"
        drifted.write_text("DRIFTED: these bytes differ from the pinned artifact\n", encoding="utf-8")
        assert sha256_of_path(str(drifted)) != expected_sha

        rc = _invoke_check_artifact_stable(
            lifecycle_root, feature, input_file, expected_sha, artifact_path=drifted
        )

        assert rc == 3
        rows = _read_jsonl(feature_dir / "events.log")
        assert len(rows) == 1
        assert rows[0]["event"] == "sentinel_absence"
        assert rows[0]["reason"] == "absent"
        assert all(r["event"] != "sentinel_advisory" for r in rows)

    def test_absent_unreadable_path_exit3(self, tmp_path: pathlib.Path) -> None:
        """Absent sentinel + unreadable/deleted ``--artifact-path`` -> exit 3 (R3)."""
        text, meta = _load_case(SENTINEL_ABSENT_STABLE)
        expected_sha = meta["expected_sha"]
        lifecycle_root = tmp_path / "cortex" / "lifecycle"
        feature = "unreadable-feature"
        feature_dir = lifecycle_root / feature
        feature_dir.mkdir(parents=True)

        input_file = tmp_path / "reviewer-output.txt"
        input_file.write_text(text, encoding="utf-8")

        # Never created — sha256_of_path raises OSError -> treated as drift.
        missing = tmp_path / "does-not-exist.md"

        rc = _invoke_check_artifact_stable(
            lifecycle_root, feature, input_file, expected_sha, artifact_path=missing
        )

        assert rc == 3
        rows = _read_jsonl(feature_dir / "events.log")
        assert len(rows) == 1
        assert rows[0]["event"] == "sentinel_absence"

    def test_absent_no_artifact_path_exit3_backcompat(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Absent sentinel + no ``--artifact-path`` -> today's exit 3 exclusion (R1)."""
        text, meta = _load_case(SENTINEL_ABSENT_STABLE)
        expected_sha = meta["expected_sha"]
        lifecycle_root = tmp_path / "cortex" / "lifecycle"
        feature = "backcompat-feature"
        feature_dir = lifecycle_root / feature
        feature_dir.mkdir(parents=True)

        input_file = tmp_path / "reviewer-output.txt"
        input_file.write_text(text, encoding="utf-8")

        rc = _invoke_check_artifact_stable(
            lifecycle_root, feature, input_file, expected_sha, artifact_path=None
        )

        assert rc == 3
        rows = _read_jsonl(feature_dir / "events.log")
        assert len(rows) == 1
        assert rows[0]["event"] == "sentinel_absence"
        assert rows[0]["reason"] == "absent"


class TestSynthStableWrapperRehash:
    """``_cmd_check_synth_stable`` absent-branch re-hash disambiguation.

    Distinct function from ``_cmd_check_artifact_stable``: the advisory-clean
    event is ``sentinel_advisory`` (shared), but the absent+drift branch
    preserves the synth wrapper's EXISTING ``synthesizer_drift`` event —
    NOT ``sentinel_absence``.
    """

    def test_absent_stable_path_advisory_pass(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Absent SYNTH sentinel + re-hash matches -> exit 0 + ``sentinel_advisory`` (R2)."""
        text, meta = _load_case(SENTINEL_ABSENT_STABLE)
        expected_sha = meta["expected_sha"]
        lifecycle_root = tmp_path / "cortex" / "lifecycle"
        feature = "synth-advisory-feature"
        feature_dir = lifecycle_root / feature
        feature_dir.mkdir(parents=True)

        pinned = tmp_path / "pinned-artifact.md"
        pinned.write_text(meta["pinned_artifact_content"], encoding="utf-8")
        assert sha256_of_path(str(pinned)) == expected_sha

        rc = _invoke_check_synth_stable(
            monkeypatch, lifecycle_root, feature, text, expected_sha, artifact_path=pinned
        )

        assert rc == 0
        rows = _read_jsonl(feature_dir / "events.log")
        assert len(rows) == 1
        assert rows[0]["event"] == "sentinel_advisory"
        assert rows[0]["feature"] == feature
        assert rows[0]["observed_sha_or_null"] == expected_sha
        # Synth advisory event carries no reviewer_angle/model_tier (distinct schema).
        assert "reviewer_angle" not in rows[0]
        assert all(r["event"] != "synthesizer_drift" for r in rows)

    def test_absent_drifted_path_exit3_synthesizer_drift(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Absent SYNTH sentinel + re-hash differs -> exit 3 + ``synthesizer_drift`` (R3).

        Asserts the synth wrapper's EXISTING drift event name, NOT
        ``sentinel_absence`` — the load-bearing artifact-vs-synth asymmetry.
        """
        text, meta = _load_case(SENTINEL_ABSENT_STABLE)
        expected_sha = meta["expected_sha"]
        lifecycle_root = tmp_path / "cortex" / "lifecycle"
        feature = "synth-drift-feature"
        feature_dir = lifecycle_root / feature
        feature_dir.mkdir(parents=True)

        drifted = tmp_path / "drifted-artifact.md"
        drifted.write_text("DRIFTED: synth bytes differ from the pinned artifact\n", encoding="utf-8")
        assert sha256_of_path(str(drifted)) != expected_sha

        rc = _invoke_check_synth_stable(
            monkeypatch, lifecycle_root, feature, text, expected_sha, artifact_path=drifted
        )

        assert rc == 3
        rows = _read_jsonl(feature_dir / "events.log")
        assert len(rows) == 1
        assert rows[0]["event"] == "synthesizer_drift"
        assert rows[0]["event"] != "sentinel_absence"
        assert all(r["event"] != "sentinel_advisory" for r in rows)

    def test_absent_unreadable_path_exit3(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Absent SYNTH sentinel + unreadable ``--artifact-path`` -> exit 3 (R3)."""
        text, meta = _load_case(SENTINEL_ABSENT_STABLE)
        expected_sha = meta["expected_sha"]
        lifecycle_root = tmp_path / "cortex" / "lifecycle"
        feature = "synth-unreadable-feature"
        feature_dir = lifecycle_root / feature
        feature_dir.mkdir(parents=True)

        missing = tmp_path / "does-not-exist.md"

        rc = _invoke_check_synth_stable(
            monkeypatch, lifecycle_root, feature, text, expected_sha, artifact_path=missing
        )

        assert rc == 3
        rows = _read_jsonl(feature_dir / "events.log")
        assert len(rows) == 1
        assert rows[0]["event"] == "synthesizer_drift"

    def test_absent_no_artifact_path_exit3_backcompat(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Absent SYNTH sentinel + no ``--artifact-path`` -> today's exit 3 (R1)."""
        text, meta = _load_case(SENTINEL_ABSENT_STABLE)
        expected_sha = meta["expected_sha"]
        lifecycle_root = tmp_path / "cortex" / "lifecycle"
        feature = "synth-backcompat-feature"
        feature_dir = lifecycle_root / feature
        feature_dir.mkdir(parents=True)

        rc = _invoke_check_synth_stable(
            monkeypatch, lifecycle_root, feature, text, expected_sha, artifact_path=None
        )

        assert rc == 3
        rows = _read_jsonl(feature_dir / "events.log")
        assert len(rows) == 1
        assert rows[0]["event"] == "synthesizer_drift"
