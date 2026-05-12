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
    """Validate ``candidate`` against the realpath-based security gate.

    Implements Requirement 9a-c:
      - realpath(candidate) MUST byte-equal abspath(candidate) (no symlinks)
      - resolved path MUST be a strict path-component prefix of at least
        one root in ``lifecycle_root`` (rejects candidate equal to a root)
      - when ``feature`` is supplied (auto-trigger flow), the resolved
        path MUST additionally be under ``{matched-root}/{feature}/``

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
    abspath = os.path.abspath(candidate)
    realpath = os.path.realpath(candidate)
    if realpath != abspath:
        raise ValueError(
            f"Path validation failed (Req 9a/9c): symlink detected in "
            f"{candidate!r}; realpath={realpath!r} != abspath={abspath!r}. "
            f"Artifact directories must not contain symlinks."
        )

    if isinstance(lifecycle_root, str):
        roots: list[str] = [lifecycle_root]
    else:
        roots = list(lifecycle_root)
    if not roots:
        raise ValueError(
            "Path validation failed: no artifact roots supplied."
        )

    candidate_path = Path(realpath)
    last_err: ValueError | None = None
    for root in roots:
        root_abs = os.path.abspath(root)
        root_real = os.path.realpath(root)
        if root_real != root_abs:
            last_err = ValueError(
                f"Path validation failed (Req 9c): artifact root "
                f"{root!r} resolves through a symlink "
                f"(realpath={root_real!r} != abspath={root_abs!r})."
            )
            continue

        root_path = Path(root_real)
        # Strict prefix: candidate must be *under* the root, not equal to it.
        if candidate_path == root_path or not candidate_path.is_relative_to(root_path):
            last_err = ValueError(
                f"Path validation failed (Req 9b): {realpath!r} is not "
                f"strictly under {root_real!r}."
            )
            continue

        if feature is not None:
            feature_root = root_path / feature
            if not candidate_path.is_relative_to(feature_root):
                last_err = ValueError(
                    f"Path validation failed (Req 9b auto-trigger): {realpath!r} "
                    f"is not under {feature_root!s}/."
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


def _cmd_record_exclusion(args: argparse.Namespace) -> int:
    try:
        lifecycle_root = args.lifecycle_root or _default_lifecycle_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 2

    events_log = Path(lifecycle_root) / args.feature / "events.log"
    event = {
        "ts": _now_iso(),
        "event": "sentinel_absence",
        "feature": args.feature,
        "reviewer_angle": args.reviewer_angle,
        "reason": args.reason,
        "model_tier": args.model_tier,
        "expected_sha": args.expected_sha,
        "observed_sha_or_null": args.observed_sha,
    }
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


def main(argv: list[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
