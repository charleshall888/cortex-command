"""Atomic CLI helpers for the critical-review dispatch ceremony.

The /cortex-core:critical-review skill dispatches reviewer sub-agents
and a synthesizer sub-agent against an artifact whose absolute path and
SHA-256 are pinned at dispatch time. The orchestrator-LLM (Claude running
the SKILL.md template) historically performed this ceremony as a 6-step
in-context prose sequence: validate path -> compute SHA -> dispatch ->
capture sentinel -> verify -> log. Each step in prose is a place where a
weakly-grounded LLM can skip, paraphrase, or self-suppress.

This module collapses the ceremony into three atomic CLI subcommands so
each subprocess call fuses validation + mutation. The orchestrator-LLM
cannot perform half the ceremony because the operations are no longer
addressable as independent steps:

  prepare-dispatch     -- realpath gate + SHA-256 in one call
  verify-synth-output  -- sentinel-parse + SHA-match + drift-log in one call
  record-exclusion     -- atomic sentinel_absence event append

Public functions are also importable for unit testing.

Schemas (events.log JSONL, matching spec Requirement 12):

  {"ts": ISO-8601, "event": "sentinel_absence", "feature": str,
   "reviewer_angle": str, "reason": "absent"|"sha_mismatch"|"read_failed",
   "model_tier": "haiku"|"sonnet"|"opus",
   "expected_sha": str, "observed_sha_or_null": str | None}

  {"ts": ISO-8601, "event": "synthesizer_drift", "feature": str,
   "expected_sha": str, "observed_sha_or_null": str | None}
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Path validation (Requirement 9)
# ---------------------------------------------------------------------------

def validate_artifact_path(
    candidate: str,
    lifecycle_root: str | Sequence[str],
    feature: str | None = None,
) -> str:
    """Validate ``candidate`` against under-root scoping (Fix 2).

    Implements ticket-255 Fix 2 (Phase 1):
      - the candidate's realpath endpoint MUST live under at least one
        root's realpath, regardless of whether the path traversed an
        ancestor symlink. This replaces the prior ``realpath != abspath``
        candidate-symlink gate (which false-positived sandbox-sanctioned
        ancestors like ``/tmp/claude`` on macOS) AND the redundant
        root-symlink gate (which pre-resolved each root and rejected
        any ancestor-resolved root before the under-root check could run).
      - when ``feature`` is supplied (auto-trigger flow), the resolved
        path MUST additionally be under ``{matched-root}/{feature}/``
      - the file at the resolved path MUST be a regular file (rejects
        directories, symlinks-resolving-to-non-files, device files)

    The under-root scoping uses ``Path(...).resolve().is_relative_to(...)``
    with macOS APFS case-normcase handling (mirroring the canonical
    in-house pattern at ``cortex_command/init/scaffold.py:113-172``).
    The ``realpath().startswith()`` shape is explicitly rejected — it
    false-positives sibling roots that share a prefix
    (e.g., ``/tmp/repository`` vs ``/tmp/repo``).

    Args:
        candidate: Caller-supplied artifact path.
        lifecycle_root: One or more acceptable artifact roots. When a
            sequence is supplied, the candidate matches if it is strictly
            under any root. Callers pass a single root (back-compat) or
            a sequence (e.g. ``(cortex/lifecycle, cortex/research)``) when
            the artifact may live under either tree.
        feature: Optional feature slug to narrow the prefix.

    Returns:
        The resolved realpath as a string.

    Raises:
        ValueError: On any rejection. Message names the offending path
            and the violated rule.
    """
    realpath = os.path.realpath(candidate)

    if isinstance(lifecycle_root, str):
        roots: list[str] = [lifecycle_root]
    else:
        roots = list(lifecycle_root)
    if not roots:
        raise ValueError(
            "Path validation failed: no artifact roots supplied."
        )

    candidate_path = Path(realpath)
    # macOS APFS preserves case but compares case-insensitively; ``resolve``
    # does not normalize case. Normalize both sides before the containment
    # check so the comparison matches filesystem semantics (mirrors the
    # canonical in-house pattern at ``init/scaffold.py:159-167``).
    candidate_norm = Path(os.path.normcase(str(candidate_path)))
    last_err: ValueError | None = None
    for root in roots:
        root_path = Path(root).resolve()
        root_norm = Path(os.path.normcase(str(root_path)))
        # Strict prefix: candidate must be *under* the root, not equal to it.
        if candidate_norm == root_norm or not candidate_norm.is_relative_to(root_norm):
            last_err = ValueError(
                f"Path validation failed (Req 9b): {realpath!r} is not "
                f"strictly under {str(root_path)!r}."
            )
            continue

        if feature is not None:
            feature_root_norm = Path(os.path.normcase(str(root_path / feature)))
            if not candidate_norm.is_relative_to(feature_root_norm):
                last_err = ValueError(
                    f"Path validation failed (Req 9b auto-trigger): {realpath!r} "
                    f"is not under {str(root_path / feature)!s}/."
                )
                continue

        # Root + feature checks passed; the file check is invariant of root.
        if not candidate_path.is_file():
            raise ValueError(
                f"Path validation failed: {realpath!r} is not a regular file."
            )

        return realpath

    if len(roots) > 1:
        raise ValueError(
            f"Path validation failed (Req 9b): {realpath!r} is not "
            f"strictly under any of: {', '.join(repr(r) for r in roots)}."
        )
    assert last_err is not None  # single-root loop always sets last_err on failure
    raise last_err


# ---------------------------------------------------------------------------
# SHA-256 of file bytes
# ---------------------------------------------------------------------------

def sha256_of_path(path: str) -> str:
    """Return the lowercase hex SHA-256 of the bytes at ``path``."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# prepare-dispatch (validate + SHA)
# ---------------------------------------------------------------------------

def prepare_dispatch(
    candidate: str,
    lifecycle_root: str | Sequence[str],
    feature: str | None = None,
) -> dict:
    """Fuse path validation + SHA-256 into one operation.

    Args:
        candidate: Caller-supplied artifact path.
        lifecycle_root: One or more acceptable artifact roots. See
            ``validate_artifact_path`` for multi-root semantics.
        feature: Optional feature slug to narrow the prefix.

    Returns:
        ``{"resolved_path": <realpath>, "sha256": <hex>}``.

    Raises:
        ValueError: On any path-validation rejection.
    """
    resolved = validate_artifact_path(candidate, lifecycle_root, feature)
    return {"resolved_path": resolved, "sha256": sha256_of_path(resolved)}


# ---------------------------------------------------------------------------
# verify-synth-output (parse SYNTH_READ_OK + compare SHA)
# ---------------------------------------------------------------------------

_SYNTH_RE = re.compile(r"^SYNTH_READ_OK: (\S+) ([0-9a-f]{64})$", re.MULTILINE)


def verify_synth_output(
    output: str,
    expected_sha: str,
) -> tuple[str, str | None]:
    """Inspect a synthesizer's stdout for ``SYNTH_READ_OK: <path> <sha>``.

    Args:
        output: The synthesizer's full stdout text.
        expected_sha: The orchestrator's pre-dispatch SHA.

    Returns:
        ``("ok", sha)`` if the sentinel is present and matches.
        ``("absent", None)`` if the sentinel line is missing.
        ``("mismatch", observed_sha)`` if present but does not match.
    """
    m = _SYNTH_RE.search(output)
    if not m:
        return ("absent", None)
    observed = m.group(2)
    if observed != expected_sha:
        return ("mismatch", observed)
    return ("ok", observed)


# ---------------------------------------------------------------------------
# verify-reviewer-output (parse READ_OK / READ_FAILED with OK-first precedence)
# ---------------------------------------------------------------------------

_REVIEWER_OK_RE = re.compile(r"^READ_OK: (\S+) ([0-9a-f]{64})\s*$", re.MULTILINE)
_REVIEWER_FAILED_RE = re.compile(r"^READ_FAILED: (\S+) (\S+)\s*$", re.MULTILINE)


def verify_reviewer_output(
    output: str,
    expected_sha: str,
    window_lines: int = 50,
) -> tuple[str, str | None]:
    """Inspect a reviewer's stdout for ``READ_OK`` / ``READ_FAILED`` sentinels.

    Uses **first-match-whose-SHA-equals-expected** (OK-first precedence)
    rather than earliest-position matching, so that adversarial preamble
    containing quoted ``READ_OK``/``READ_FAILED`` lines (e.g. when a reviewer
    reviews this fix's own artifacts) cannot misclassify a real success
    or failure sentinel that appears later in the window.

    Args:
        output: The reviewer's full stdout text.
        expected_sha: The orchestrator's pre-dispatch SHA.
        window_lines: How many leading lines of ``output`` to scan (default 50).

    Returns:
        ``("ok", expected_sha)`` if any ``READ_OK`` in the window has the
            expected SHA.
        ``("read_failed", reason)`` if no matching ``READ_OK`` exists but
            at least one ``READ_FAILED`` line is present; ``reason`` is the
            first failure's reason token.
        ``("mismatch", observed_sha)`` if ``READ_OK`` lines exist in the
            window but none match the expected SHA; ``observed_sha`` is the
            first ``READ_OK``'s SHA (diagnostic only — may be quoted text).
        ``("absent", None)`` if neither sentinel appears in the window.

    Note:
        The path-capture group is diagnostic only — only the SHA is
        validated. ``splitlines()`` normalizes ``\\r\\n`` line endings
        before the regex sees them.
    """
    window = "\n".join(output.splitlines()[:window_lines])
    ok_matches = list(_REVIEWER_OK_RE.finditer(window))
    for match in ok_matches:
        if match.group(2) == expected_sha:
            return ("ok", expected_sha)
    failed_matches = list(_REVIEWER_FAILED_RE.finditer(window))
    if failed_matches:
        return ("read_failed", failed_matches[0].group(2))
    if ok_matches:
        return ("mismatch", ok_matches[0].group(2))
    return ("absent", None)


# ---------------------------------------------------------------------------
# Atomic events.log append (tempfile + os.replace)
# ---------------------------------------------------------------------------

def append_event(events_log_path: Path, event: dict) -> None:
    """Atomically append a JSON event line to ``events_log_path``.

    Uses tempfile + ``os.replace`` rather than ``open(path, 'a')`` so
    the append is atomic against concurrent emitters: each call writes
    (existing contents + new line) to a unique temp file in the same
    directory and then renames over the target. The rename is atomic
    on POSIX; the temp file is unique per-call so concurrent appenders
    do not collide.

    Args:
        events_log_path: Path to the JSONL events log.
        event: Dict to serialize as one JSONL line.
    """
    events_log_path.parent.mkdir(parents=True, exist_ok=True)
    existing = b""
    if events_log_path.exists():
        existing = events_log_path.read_bytes()
        if existing and not existing.endswith(b"\n"):
            existing += b"\n"

    line = (
        json.dumps(event, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")

    tmp = tempfile.NamedTemporaryFile(
        dir=str(events_log_path.parent),
        prefix=f".{events_log_path.name}-",
        suffix=".tmp",
        delete=False,
    )
    try:
        tmp.write(existing)
        tmp.write(line)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp.close()
        os.replace(tmp.name, events_log_path)
    except BaseException:
        try:
            tmp.close()
        except Exception:
            pass
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Defaults: resolve lifecycle_root from git toplevel
# ---------------------------------------------------------------------------

def _git_toplevel() -> str:
    """Return the absolute path to the enclosing git repository toplevel."""
    try:
        toplevel = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
        ).decode("utf-8").strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise RuntimeError(
            "Could not resolve git toplevel; run from inside a git "
            "repository or pass --lifecycle-root explicitly."
        ) from e
    return toplevel


def _default_lifecycle_root() -> str:
    """Resolve ``{git toplevel}/cortex/lifecycle`` as the default lifecycle root."""
    return str(Path(_git_toplevel()) / "cortex" / "lifecycle")


def _default_artifact_roots() -> tuple[str, str]:
    """Resolve ``(cortex/lifecycle, cortex/research)`` under the git toplevel.

    ``prepare-dispatch`` accepts artifacts produced by either the lifecycle
    state machine (``cortex/lifecycle/<feature>/``) or the discovery skill
    (``cortex/research/<topic>/``). Downstream telemetry subcommands
    (``verify-synth-output``, ``record-exclusion``) remain single-root —
    the discovery flow's ``<path>``-arg invocation form omits ``--feature``
    and those telemetry calls are documented to be skipped in that mode.
    """
    cortex = Path(_git_toplevel()) / "cortex"
    return (str(cortex / "lifecycle"), str(cortex / "research"))


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string with seconds."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Shared event-construction helper (single schema source for sentinel_absence)
# ---------------------------------------------------------------------------

def _build_sentinel_absence_event(
    feature: str,
    reviewer_angle: str,
    reason: str,
    model_tier: str,
    expected_sha: str,
    observed_sha: str | None,
) -> dict:
    """Return the canonical 8-field ``sentinel_absence`` event dict.

    This is the single schema source for ``sentinel_absence`` events,
    consumed by both ``_cmd_record_exclusion`` (manual operator path) and
    ``_cmd_verify_reviewer_output`` (atomic reviewer-side parse + classify
    + telemetry path). Centralizing construction here eliminates schema
    duplication: future field additions or renames happen in exactly one
    place.

    Args:
        feature: Feature slug (e.g. ``critical-review-sentinel-gate-relax-first``).
        reviewer_angle: Reviewer-angle identifier (e.g. ``code-quality``).
        reason: One of ``"absent"``, ``"sha_mismatch"``, ``"read_failed"``.
        model_tier: One of ``"haiku"``, ``"sonnet"``, ``"opus"``.
        expected_sha: Orchestrator's pre-dispatch SHA-256 hex string.
        observed_sha: Observed SHA on ``sha_mismatch``; ``None`` on the
            ``absent`` and ``read_failed`` paths (the signature enforces
            this convention via the caller-supplied argument).

    Returns:
        Dict with exactly the keys ``{"ts", "event", "feature",
        "reviewer_angle", "reason", "model_tier", "expected_sha",
        "observed_sha_or_null"}``.
    """
    return {
        "ts": _now_iso(),
        "event": "sentinel_absence",
        "feature": feature,
        "reviewer_angle": reviewer_angle,
        "reason": reason,
        "model_tier": model_tier,
        "expected_sha": expected_sha,
        "observed_sha_or_null": observed_sha,
    }


# ---------------------------------------------------------------------------
# CLI subcommands
# ---------------------------------------------------------------------------

def _cmd_prepare_dispatch(args: argparse.Namespace) -> int:
    try:
        roots: str | tuple[str, ...] = (
            args.lifecycle_root if args.lifecycle_root else _default_artifact_roots()
        )
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 2

    try:
        result = prepare_dispatch(
            args.path,
            roots,
            feature=args.feature,
        )
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    except OSError as e:
        print(f"Path validation failed: {e}", file=sys.stderr)
        return 2

    sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
    return 0


def _cmd_verify_synth_output(args: argparse.Namespace) -> int:
    try:
        lifecycle_root = args.lifecycle_root or _default_lifecycle_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 2

    output = sys.stdin.read()
    status, observed = verify_synth_output(output, args.expected_sha)

    if status == "ok":
        sys.stdout.write(f"OK {observed}\n")
        return 0

    events_log = Path(lifecycle_root) / args.feature / "events.log"

    if status == "absent":
        diagnostic = (
            f"Critical-review pass invalidated: synthesizer SYNTH_READ_OK "
            f"sentinel absent; re-run after resolving concurrent write source."
        )
        event = {
            "ts": _now_iso(),
            "event": "synthesizer_drift",
            "feature": args.feature,
            "expected_sha": args.expected_sha,
            "observed_sha_or_null": None,
        }
    else:  # mismatch
        diagnostic = (
            f"Critical-review pass invalidated: synthesizer SHA drift "
            f"detected (expected {args.expected_sha}, got {observed}); "
            f"re-run after resolving concurrent write source."
        )
        event = {
            "ts": _now_iso(),
            "event": "synthesizer_drift",
            "feature": args.feature,
            "expected_sha": args.expected_sha,
            "observed_sha_or_null": observed,
        }

    sys.stdout.write(diagnostic + "\n")
    try:
        append_event(events_log, event)
    except OSError as e:
        print(f"WARN: failed to append synthesizer_drift event: {e}", file=sys.stderr)
    return 3


def _cmd_verify_reviewer_output(args: argparse.Namespace) -> int:
    try:
        lifecycle_root = args.lifecycle_root or _default_lifecycle_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 2

    try:
        with open(args.input_file, "r", encoding="utf-8", errors="strict") as fh:
            output = fh.read()
    except OSError as e:
        print(
            f"verify-reviewer-output: cannot read {args.input_file!r}: {e}",
            file=sys.stderr,
        )
        return 2

    status, observed = verify_reviewer_output(
        output, args.expected_sha, args.window_lines
    )

    if status == "ok":
        sys.stdout.write(f"OK {observed}\n")
        return 0

    # status is one of {"absent", "mismatch", "read_failed"}.
    # Map verify_reviewer_output status -> record-exclusion reason enum.
    if status == "mismatch":
        reason = "sha_mismatch"
        observed_for_event: str | None = observed
    elif status == "read_failed":
        reason = "read_failed"
        observed_for_event = None
    else:  # absent
        reason = "absent"
        observed_for_event = None

    event = _build_sentinel_absence_event(
        feature=args.feature,
        reviewer_angle=args.reviewer_angle,
        reason=reason,
        model_tier=args.model_tier,
        expected_sha=args.expected_sha,
        observed_sha=observed_for_event,
    )

    events_log = Path(lifecycle_root) / args.feature / "events.log"
    sys.stdout.write(f"EXCLUDED {reason}\n")
    try:
        append_event(events_log, event)
    except OSError as e:
        print(
            f"WARN: failed to append sentinel_absence event: {e}",
            file=sys.stderr,
        )
    return 3


def _cmd_record_exclusion(args: argparse.Namespace) -> int:
    try:
        lifecycle_root = args.lifecycle_root or _default_lifecycle_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 2

    events_log = Path(lifecycle_root) / args.feature / "events.log"
    event = _build_sentinel_absence_event(
        feature=args.feature,
        reviewer_angle=args.reviewer_angle,
        reason=args.reason,
        model_tier=args.model_tier,
        expected_sha=args.expected_sha,
        observed_sha=args.observed_sha,
    )
    try:
        append_event(events_log, event)
    except OSError as e:
        print(f"Failed to append sentinel_absence event: {e}", file=sys.stderr)
        return 2
    return 0


# ---------------------------------------------------------------------------
# argparse wiring
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python3 -m cortex_command.critical_review",
        description=(
            "Atomic CLI helpers for the critical-review dispatch ceremony. "
            "Fuses path-validation + SHA + telemetry into single subprocess "
            "calls so the orchestrator-LLM cannot perform partial ceremony."
        ),
    )
    p.add_argument(
        "--lifecycle-root",
        default=None,
        help="Override lifecycle root (default: {git toplevel}/lifecycle).",
    )
    sub = p.add_subparsers(dest="command", required=True)

    pd = sub.add_parser(
        "prepare-dispatch",
        help="Validate artifact path and compute SHA-256 atomically.",
    )
    pd.add_argument("path", help="Candidate artifact path.")
    pd.add_argument(
        "--feature",
        default=None,
        help="Feature slug for auto-trigger flows (narrows the prefix check).",
    )
    pd.set_defaults(func=_cmd_prepare_dispatch)

    vs = sub.add_parser(
        "verify-synth-output",
        help=(
            "Read synthesizer output on stdin, verify SYNTH_READ_OK SHA, "
            "log synthesizer_drift on mismatch/absence."
        ),
    )
    vs.add_argument("--feature", required=True)
    vs.add_argument("--expected-sha", required=True)
    vs.set_defaults(func=_cmd_verify_synth_output)

    vr = sub.add_parser(
        "verify-reviewer-output",
        help=(
            "Read reviewer output from --input-file, verify READ_OK SHA "
            "with OK-first precedence, log sentinel_absence on "
            "absent/mismatch/read_failed."
        ),
    )
    vr.add_argument("--feature", required=True)
    vr.add_argument("--reviewer-angle", required=True)
    vr.add_argument("--expected-sha", required=True)
    vr.add_argument(
        "--model-tier",
        required=True,
        choices=("haiku", "sonnet", "opus"),
    )
    vr.add_argument(
        "--input-file",
        required=True,
        help=(
            "Path to a UTF-8 file containing the reviewer's stdout. "
            "Reviewer outputs contain backticks/quotes/JSON-envelope content; "
            "--input-file avoids shell-quoting hazards (vs stdin on synth side)."
        ),
    )
    vr.add_argument(
        "--window-lines",
        type=int,
        default=50,
        help="Leading lines of reviewer output to scan (default: 50).",
    )
    vr.set_defaults(func=_cmd_verify_reviewer_output)

    re_ = sub.add_parser(
        "record-exclusion",
        help="Atomically append a sentinel_absence event to events.log.",
    )
    re_.add_argument("--feature", required=True)
    re_.add_argument("--reviewer-angle", required=True)
    re_.add_argument(
        "--reason",
        required=True,
        choices=("absent", "sha_mismatch", "read_failed"),
    )
    re_.add_argument(
        "--model-tier",
        required=True,
        choices=("haiku", "sonnet", "opus"),
    )
    re_.add_argument("--expected-sha", required=True)
    re_.add_argument("--observed-sha", default=None)
    re_.set_defaults(func=_cmd_record_exclusion)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
