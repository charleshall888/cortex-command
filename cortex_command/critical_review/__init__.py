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
  check-synth-stable   -- sentinel-parse + SHA-match + drift-log in one call
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


# Exit code emitted when a telemetry write is suppressed because the target
# lifecycle dir does not exist. Distinct from 0 (clean/recorded), 2 (OSError),
# and 3 (drift/absence) so a skipped write is observably distinguishable from a
# real invalidation and from a successful record.
EXIT_TELEMETRY_SKIPPED = 4


# ---------------------------------------------------------------------------
# Path validation (Requirement 9)
# ---------------------------------------------------------------------------

def validate_artifact_path(
    candidate: str,
    lifecycle_root: str | Sequence[str],
    feature: str | None = None,
    allow_adhoc: bool = False,
) -> str | dict:
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

    Candidate-string boundary validation (ticket-255 Fix 3, Phase 2):
      - the candidate string MUST NOT contain a NUL byte (``\\x00``) — NUL
        is the one byte POSIX paths cannot legally contain.
      - the candidate string MUST NOT contain surrogate code points
        produced by ``surrogateescape``-decoded argv carrying invalid
        UTF-8 bytes (checked via ``candidate.encode('utf-8', errors='strict')``
        — a ``UnicodeEncodeError`` raised means a surrogate is present).
      - other ASCII control characters (newlines, tabs, ANSI escapes,
        0x01-0x09, 0x0B-0x1F, 0x7F) are LEGAL and pass through unchanged.

    Ad-hoc snapshot flow (ticket-255 Fix 3, Phase 2):
      - when ``allow_adhoc`` is True and the candidate's realpath lies
        outside ALL supplied roots, the helper snapshots the file into
        ``cortex/_adhoc/<sha[:2]>/<sha[2:]>/<basename>`` (peer of
        ``cortex/lifecycle/``, full-hash + 2-char fanout). The snapshot
        write is atomic temp-rename: write to
        ``cortex/_adhoc/<sha[:2]>/.staging-<sha[2:]>.<basename>`` first,
        then ``os.rename`` to the final path. The repo root is derived
        from the first supplied root by ``.parent.parent`` (which makes
        ``cortex/_adhoc/`` a sibling of ``cortex/lifecycle/``).

    Args:
        candidate: Caller-supplied artifact path.
        lifecycle_root: One or more acceptable artifact roots. When a
            sequence is supplied, the candidate matches if it is strictly
            under any root. Callers pass a single root (back-compat) or
            a sequence (e.g. ``(cortex/lifecycle, cortex/research)``) when
            the artifact may live under either tree.
        feature: Optional feature slug to narrow the prefix.
        allow_adhoc: When True, ad-hoc snapshot the candidate into
            ``cortex/_adhoc/`` if its realpath lies outside all roots.
            Default False (back-compat).

    Returns:
        For non-adhoc paths (the back-compat path): the resolved realpath
        as a string. For ad-hoc-snapshotted paths: a dict with keys
        ``{"resolved_path", "source_path", "snapshot_sha"}`` where
        ``resolved_path`` is the snapshot's path, ``source_path`` is the
        original candidate string (preserved verbatim post-NUL/surrogate
        validation), and ``snapshot_sha`` is the full hex SHA-256.

    Raises:
        ValueError: On any rejection. Message names the offending path
            and the violated rule. Also raised on NUL-byte or surrogate
            code points in the candidate string.
    """
    # gate-class: hygiene
    if "\x00" in candidate:
        raise ValueError(
            "Path validation failed: candidate contains NUL byte "
            "(POSIX paths cannot legally contain NUL)."
        )
    try:
        candidate.encode("utf-8", errors="strict")
    except UnicodeEncodeError as e:
        # gate-class: hygiene
        raise ValueError(
            f"Path validation failed: candidate contains surrogate "
            f"code point (likely from surrogateescape-decoded argv "
            f"with invalid UTF-8 bytes): {e}"
        ) from e

    realpath = os.path.realpath(candidate)

    if isinstance(lifecycle_root, str):
        roots: list[str] = [lifecycle_root]
    else:
        roots = list(lifecycle_root)
    if not roots:
        # gate-class: hygiene
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
            # gate-class: hygiene
            last_err = ValueError(
                f"Path validation failed (Req 9b): {realpath!r} is not "
                f"strictly under {str(root_path)!r}."
            )
            continue

        if feature is not None:
            feature_root_norm = Path(os.path.normcase(str(root_path / feature)))
            if not candidate_norm.is_relative_to(feature_root_norm):
                # gate-class: hygiene
                last_err = ValueError(
                    f"Path validation failed (Req 9b auto-trigger): {realpath!r} "
                    f"is not under {str(root_path / feature)!s}/."
                )
                continue

        # Root + feature checks passed; the file check is invariant of root.
        if not candidate_path.is_file():
            # gate-class: security
            raise ValueError(
                f"Path validation failed: {realpath!r} is not a regular file."
            )

        return realpath

    # No root accepted the candidate. If ad-hoc is allowed, snapshot.
    if allow_adhoc:
        # Reject non-regular files at the validation boundary even on the
        # ad-hoc path — snapshotting a directory or device file is nonsense.
        if not candidate_path.is_file():
            # gate-class: security
            raise ValueError(
                f"Path validation failed: {realpath!r} is not a regular file."
            )
        # Derive repo root from the first supplied root. The roots resolve
        # to e.g. ``<repo>/cortex/lifecycle`` and ``<repo>/cortex/research``;
        # ``cortex/_adhoc/`` is a peer of ``cortex/lifecycle/``, so the
        # repo root is the root's parent's parent.
        first_root = Path(roots[0]).resolve()
        repo_root = first_root.parent.parent
        snapshot_path, full_sha = _snapshot_adhoc(candidate_path, repo_root)
        return {
            "resolved_path": str(snapshot_path),
            "source_path": candidate,
            "snapshot_sha": full_sha,
        }

    if len(roots) > 1:
        # gate-class: hygiene
        raise ValueError(
            f"Path validation failed (Req 9b): {realpath!r} is not "
            f"strictly under any of: {', '.join(repr(r) for r in roots)}."
        )
    assert last_err is not None  # single-root loop always sets last_err on failure
    raise last_err


# ---------------------------------------------------------------------------
# Ad-hoc snapshot helper (Fix 3, Phase 2)
# ---------------------------------------------------------------------------

def _snapshot_adhoc(
    candidate_realpath: Path,
    repo_root: Path,
) -> tuple[Path, str]:
    """Snapshot ``candidate_realpath`` into ``cortex/_adhoc/<sha[:2]>/<sha[2:]>/<basename>``.

    Uses atomic temp-rename: write content to
    ``cortex/_adhoc/<sha[:2]>/.staging-<sha[2:]>.<basename>`` first, then
    ``os.rename`` to the final path
    ``cortex/_adhoc/<sha[:2]>/<sha[2:]>/<basename>`` after the destination
    directory is created. The ``.staging-*`` filename is invisible to
    ``cortex-clean --adhoc`` (which ignores ``.staging-*``); the
    ``os.rename`` final step is atomic on the same filesystem.

    Args:
        candidate_realpath: The fully-resolved path of the file to snapshot.
        repo_root: The repository root (parent of ``cortex/``).

    Returns:
        ``(snapshot_path, full_sha)`` where ``snapshot_path`` is the
        absolute path to the final snapshot location and ``full_sha`` is
        the lowercase hex SHA-256 of the file content.
    """
    full_sha = sha256_of_path(str(candidate_realpath))
    basename = candidate_realpath.name
    adhoc_root = repo_root / "cortex" / "_adhoc"
    fanout_dir = adhoc_root / full_sha[:2]
    final_dir = fanout_dir / full_sha[2:]
    final_path = final_dir / basename
    staging_path = fanout_dir / f".staging-{full_sha[2:]}.{basename}"

    fanout_dir.mkdir(parents=True, exist_ok=True)

    # Read source bytes and write to staging, then atomically rename into
    # the final directory. ``os.makedirs(final_dir, exist_ok=True)`` is
    # performed before the rename so the destination dir exists.
    content = candidate_realpath.read_bytes()
    with open(staging_path, "wb") as fh:
        fh.write(content)
        fh.flush()
        os.fsync(fh.fileno())

    final_dir.mkdir(parents=True, exist_ok=True)
    os.rename(staging_path, final_path)
    return (final_path, full_sha)


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
    allow_adhoc: bool = False,
) -> dict:
    """Fuse path validation + SHA-256 into one operation.

    Args:
        candidate: Caller-supplied artifact path.
        lifecycle_root: One or more acceptable artifact roots. See
            ``validate_artifact_path`` for multi-root semantics.
        feature: Optional feature slug to narrow the prefix.
        allow_adhoc: When True, allow validation to snapshot ad-hoc
            inputs into ``cortex/_adhoc/`` if their realpath is outside
            all roots. See ``validate_artifact_path`` for snapshot
            semantics. Default False (back-compat).

    Returns:
        For non-adhoc paths: ``{"resolved_path": <realpath>, "sha256": <hex>}``.
        For ad-hoc-snapshotted paths: ``{"resolved_path": <snapshot_path>,
        "sha256": <hex>, "source_path": <original>, "snapshot_sha": <hex>}``.

    Raises:
        ValueError: On any path-validation rejection.
    """
    result = validate_artifact_path(
        candidate, lifecycle_root, feature, allow_adhoc=allow_adhoc
    )
    if isinstance(result, dict):
        # Ad-hoc snapshot path — result already carries source_path and
        # snapshot_sha. Compute sha256 of the (snapshot) resolved_path so
        # the existing prepare_dispatch return shape is preserved.
        resolved = result["resolved_path"]
        return {
            "resolved_path": resolved,
            "sha256": sha256_of_path(resolved),
            "source_path": result["source_path"],
            "snapshot_sha": result["snapshot_sha"],
        }
    return {"resolved_path": result, "sha256": sha256_of_path(result)}


# ---------------------------------------------------------------------------
# check-synth-stable (parse SYNTH_READ_OK + compare SHA) — advisory gate
# ---------------------------------------------------------------------------

_SYNTH_RE = re.compile(r"^SYNTH_READ_OK: (\S+) ([0-9a-f]{64})$", re.MULTILINE)


def check_synth_stable(
    output: str,
    expected_sha: str,
) -> tuple[str, str | None]:
    """Detect SHA drift of the artifact between dispatch and verification time.

    Does NOT detect reviewer/synth engagement quality,
    orchestrator-fabricated input, or coordinated injection — the
    orchestrator-LLM controls both the SHA and the input file and can
    satisfy this gate without dispatching a real reviewer/synth.
    Engagement quality depends on reviewer/synth prompt fidelity, not on
    this gate.

    Sentinel-string divergence note: the wire-protocol sentinel
    ``SYNTH_READ_OK:`` (and the reviewer-side ``READ_OK:``) is intentionally
    unchanged despite this function's rename — renaming wire-protocol
    sentinels would break every reviewer-fixture transcript and every
    dispatching skill that emits the sentinel, which is out of ticket 255
    scope.

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
    # gate-class: advisory
    return ("ok", observed)


# ---------------------------------------------------------------------------
# check-artifact-stable (parse READ_OK / READ_FAILED with OK-first precedence)
# — advisory gate
# ---------------------------------------------------------------------------

_REVIEWER_OK_RE = re.compile(r"^READ_OK: (\S+) ([0-9a-f]{64})\s*$", re.MULTILINE)
_REVIEWER_FAILED_RE = re.compile(r"^READ_FAILED: (\S+) (\S+)\s*$", re.MULTILINE)


def check_artifact_stable(
    output: str,
    expected_sha: str,
    window_lines: int = 50,
) -> tuple[str, str | None]:
    """Detect SHA drift of the artifact between dispatch and verification time.

    Does NOT detect reviewer/synth engagement quality,
    orchestrator-fabricated input, or coordinated injection — the
    orchestrator-LLM controls both the SHA and the input file and can
    satisfy this gate without dispatching a real reviewer/synth.
    Engagement quality depends on reviewer/synth prompt fidelity, not on
    this gate.

    Sentinel-string divergence note: the wire-protocol sentinels ``READ_OK:``
    and ``READ_FAILED:`` are intentionally unchanged despite this function's
    rename — renaming wire-protocol sentinels would break every reviewer-
    fixture transcript and every dispatching skill that emits the sentinel,
    which is out of ticket 255 scope.

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
    # gate-class: advisory
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


# gate-class: hygiene
def _lifecycle_dir_exists(lifecycle_root: str, feature: str) -> bool:
    """Return whether ``Path(lifecycle_root) / feature`` is an existing directory.

    Used by the telemetry write-guard: the three critical-review telemetry
    writers suppress their dir-creating ``append_event`` side effect when this
    returns ``False``, so a non-feature (``<path>``-arg) review cannot create a
    phantom lifecycle dir. The guard lives in the callers, NOT in
    ``append_event`` (which must keep creating the dir for the legitimate
    fresh-lifecycle first-write at Site A, ``refine.py``).
    """
    return (Path(lifecycle_root) / feature).is_dir()


def _default_artifact_roots() -> tuple[str, str]:
    """Resolve ``(cortex/lifecycle, cortex/research)`` under the git toplevel.

    ``prepare-dispatch`` accepts artifacts produced by either the lifecycle
    state machine (``cortex/lifecycle/<feature>/``) or the discovery skill
    (``cortex/research/<topic>/``). Downstream telemetry subcommands
    (``check-synth-stable``, ``record-exclusion``) remain single-root —
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
    source_path: str | None = None,
    snapshot_sha: str | None = None,
) -> dict:
    """Return the canonical ``sentinel_absence`` event dict.

    This is the single schema source for ``sentinel_absence`` events,
    consumed by both ``_cmd_record_exclusion`` (manual operator path) and
    ``_cmd_check_artifact_stable`` (atomic reviewer-side parse + classify
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
        source_path: Optional original caller-supplied path when the
            artifact was ad-hoc-snapshotted (Requirement 6/7). When
            ``None`` the field is omitted from the emitted dict.
            Preserved verbatim from the candidate string post-NUL/
            surrogate validation; ASCII control characters (including
            newlines) are legal here and JSON-escaped on write.
        snapshot_sha: Optional full hex SHA-256 of the ad-hoc snapshot
            content (the pin token consumed by ``cortex clean --adhoc``
            retention). When ``None`` the field is omitted from the
            emitted dict.

    Returns:
        Dict with the base ``sentinel_absence`` keys; ``source_path`` and
        ``snapshot_sha`` are appended only when the corresponding kwarg
        is not ``None`` (field-additive extension; the events-registry
        row declares both as optional).
    """
    event: dict = {
        "ts": _now_iso(),
        "event": "sentinel_absence",
        "feature": feature,
        "reviewer_angle": reviewer_angle,
        "reason": reason,
        "model_tier": model_tier,
        "expected_sha": expected_sha,
        "observed_sha_or_null": observed_sha,
    }
    if source_path is not None:
        event["source_path"] = source_path
    if snapshot_sha is not None:
        event["snapshot_sha"] = snapshot_sha
    return event


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
            allow_adhoc=args.allow_adhoc,
        )
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    except OSError as e:
        print(f"Path validation failed: {e}", file=sys.stderr)
        return 2

    sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
    return 0


def _cmd_check_synth_stable(args: argparse.Namespace) -> int:
    try:
        lifecycle_root = args.lifecycle_root or _default_lifecycle_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 2

    output = sys.stdin.read()
    status, observed = check_synth_stable(output, args.expected_sha)

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


def _cmd_check_artifact_stable(args: argparse.Namespace) -> int:
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
            f"check-artifact-stable: cannot read {args.input_file!r}: {e}",
            file=sys.stderr,
        )
        return 2

    status, observed = check_artifact_stable(
        output, args.expected_sha, args.window_lines
    )

    if status == "ok":
        sys.stdout.write(f"OK {observed}\n")
        return 0

    # status is one of {"absent", "mismatch", "read_failed"}.
    # Map check_artifact_stable status -> record-exclusion reason enum.
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
        source_path=args.source_path,
        snapshot_sha=args.snapshot_sha,
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
        source_path=args.source_path,
        snapshot_sha=args.snapshot_sha,
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
    pd.add_argument(
        "--allow-adhoc",
        action="store_true",
        default=False,
        help=(
            "Allow ad-hoc inputs outside cortex/lifecycle/ and cortex/research/ "
            "to be snapshotted into cortex/_adhoc/<sha[:2]>/<sha[2:]>/<basename>. "
            "Default off — paths outside the canonical roots are rejected."
        ),
    )
    pd.set_defaults(func=_cmd_prepare_dispatch)

    vs = sub.add_parser(
        "check-synth-stable",
        help=(
            "Read synthesizer output on stdin, verify SYNTH_READ_OK SHA, "
            "log synthesizer_drift on mismatch/absence."
        ),
    )
    vs.add_argument("--feature", required=True)
    vs.add_argument("--expected-sha", required=True)
    vs.set_defaults(func=_cmd_check_synth_stable)

    vr = sub.add_parser(
        "check-artifact-stable",
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
    vr.add_argument(
        "--source-path",
        default=None,
        help=(
            "Optional original caller-supplied path when the artifact was "
            "ad-hoc-snapshotted (Req 7). Threads onto the sentinel_absence "
            "event as the field-additive ``source_path`` extension."
        ),
    )
    vr.add_argument(
        "--snapshot-sha",
        default=None,
        help=(
            "Optional full hex SHA-256 of the ad-hoc snapshot content "
            "(Req 7). Threads onto the sentinel_absence event as the "
            "field-additive ``snapshot_sha`` extension; consumed by "
            "``cortex clean --adhoc`` retention pinning."
        ),
    )
    vr.set_defaults(func=_cmd_check_artifact_stable)

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
    re_.add_argument(
        "--source-path",
        default=None,
        help=(
            "Optional original caller-supplied path when the artifact was "
            "ad-hoc-snapshotted (Req 7). Threads onto the sentinel_absence "
            "event as the field-additive ``source_path`` extension."
        ),
    )
    re_.add_argument(
        "--snapshot-sha",
        default=None,
        help=(
            "Optional full hex SHA-256 of the ad-hoc snapshot content "
            "(Req 7). Threads onto the sentinel_absence event as the "
            "field-additive ``snapshot_sha`` extension; consumed by "
            "``cortex clean --adhoc`` retention pinning."
        ),
    )
    re_.set_defaults(func=_cmd_record_exclusion)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
