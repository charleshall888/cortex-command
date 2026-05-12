"""Atomic CLI helpers for the /cortex-core:discovery skill.

The discovery skill emits three new event types per spec R8b:

  - ``architecture_section_written``    (research-phase Architecture write)
  - ``approval_checkpoint_responded``   (R4 research->decompose gate AND
                                         R15 decompose->commit batch-review gate)
  - ``prescriptive_check_run``          (decompose-phase ticket-body scan)

Each event carries a small but non-trivial payload (e.g. the
``prescriptive_check_run.flag_locations[]`` nested array) that meets the
project.md L33 "skill-helper module" paraphrase-vulnerability threshold:
authoring the JSON inline in skill prose invites the orchestrator-LLM to
silently drop fields or fold the array shape.

This module collapses each emission into one atomic CLI subcommand that
fuses input validation + JSONL append + path resolution. The orchestrator
invokes:

  python3 -m cortex_command.discovery emit-architecture-written ...
  python3 -m cortex_command.discovery emit-checkpoint-response  ...
  python3 -m cortex_command.discovery emit-prescriptive-check   ...
  python3 -m cortex_command.discovery resolve-events-log-path   ...

The first three emit-* subcommands internally call ``resolve-events-log-path``
to pick the correct events.log target -- never hardcoded. Path resolution
rules (spec R9 + R13 + EVT-1):

  1. If ``LIFECYCLE_SESSION_ID`` is set in the env AND a lifecycle directory
     under ``{repo_root}/cortex/lifecycle/`` contains a ``.session`` (or
     ``.session-owner``) file whose contents byte-equal that ID, the active
     lifecycle slug is that directory's basename and the target is
     ``cortex/lifecycle/{lifecycle-slug}/events.log``.

  2. Otherwise, when the supplied topic slug has a trailing ``-N`` suffix
     (decimal integer, N >= 2 per R13's re-run rule), the target is
     ``cortex/research/{topic}-N/events.log``.

  3. Otherwise, the target is ``cortex/research/{topic}/events.log``.

Public functions are importable for unit testing; the CLI is a thin
argparse wrapper.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Defaults: resolve repo root from git toplevel
# ---------------------------------------------------------------------------

def _default_repo_root() -> str:
    """Resolve the git toplevel as the default repo root."""
    try:
        toplevel = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
        ).decode("utf-8").strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise RuntimeError(
            "Could not resolve git toplevel; run from inside a git "
            "repository or pass --repo-root explicitly."
        ) from e
    return toplevel


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string with seconds."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Active-lifecycle detection
# ---------------------------------------------------------------------------

def _active_lifecycle_slug(repo_root: Path) -> str | None:
    """Return the active lifecycle slug under ``repo_root``, or ``None``.

    The SessionStart hook (``hooks/cortex-scan-lifecycle.sh``) injects
    ``LIFECYCLE_SESSION_ID`` into the environment. The active lifecycle
    feature is the ``cortex/lifecycle/<slug>/`` directory whose ``.session`` (or
    chain-migrated ``.session-owner``) file contents byte-equal that ID.

    Args:
        repo_root: Absolute path to the repo root.

    Returns:
        The matching lifecycle slug, or ``None`` if no env var is set, no
        ``cortex/lifecycle/`` directory exists, or no slug's ``.session`` matches.
    """
    session_id = os.environ.get("LIFECYCLE_SESSION_ID", "").strip()
    if not session_id:
        return None
    lifecycle_dir = repo_root / "cortex" / "lifecycle"
    if not lifecycle_dir.is_dir():
        return None
    for candidate in sorted(lifecycle_dir.iterdir()):
        if not candidate.is_dir():
            continue
        if candidate.name == "archive":
            continue
        for marker_name in (".session", ".session-owner"):
            marker = candidate / marker_name
            if not marker.is_file():
                continue
            try:
                content = marker.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if content == session_id:
                return candidate.name
    return None


# ---------------------------------------------------------------------------
# Slug-to-events.log path resolution (spec R9 + R13 + EVT-1)
# ---------------------------------------------------------------------------

_TOPIC_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]*$")
_RERUN_SUFFIX_RE = re.compile(r"-(\d+)$")


def _validate_topic_slug(slug: str) -> None:
    """Reject slugs that are empty, path-traversal, or non-kebab-case.

    Raises:
        ValueError: with a message naming the offending slug.
    """
    if not slug:
        raise ValueError("topic slug must be non-empty")
    if "/" in slug or "\\" in slug or ".." in slug:
        raise ValueError(
            f"topic slug must not contain path separators or '..': {slug!r}"
        )
    if not _TOPIC_SLUG_RE.match(slug):
        raise ValueError(
            f"topic slug must be lowercase-kebab-case: {slug!r}"
        )


def resolve_events_log_path(
    topic: str,
    repo_root: Path,
) -> Path:
    """Resolve the events.log target for the discovery skill.

    Resolution rules (spec R9 + R13 + EVT-1):

      1. If an active lifecycle is detected (``LIFECYCLE_SESSION_ID`` env
         set AND a ``cortex/lifecycle/<slug>/.session`` file matches), the target
         is ``{repo_root}/cortex/lifecycle/{lifecycle-slug}/events.log``. The
         topic argument is honored for slug validation but the lifecycle
         path takes precedence per EVT-1.

      2. Otherwise, if ``topic`` has a trailing ``-N`` decimal suffix
         (R13 re-run semantics, N >= 2), the target is
         ``{repo_root}/cortex/research/{topic}/events.log`` where the ``-N`` is
         already in the slug.

      3. Otherwise, the target is ``{repo_root}/cortex/research/{topic}/events.log``.

    Args:
        topic: The discovery topic slug (lowercase-kebab-case, may carry a
            ``-N`` re-run suffix).
        repo_root: Absolute path to the repo root.

    Returns:
        The absolute path to the events.log target. Parent directory may
        not yet exist; ``append_event`` creates it on write.

    Raises:
        ValueError: If ``topic`` fails slug validation.
    """
    _validate_topic_slug(topic)
    lifecycle_slug = _active_lifecycle_slug(repo_root)
    if lifecycle_slug is not None:
        return repo_root / "cortex" / "lifecycle" / lifecycle_slug / "events.log"
    # Cases (2) and (3) both produce cortex/research/{topic}/events.log -- the
    # -N suffix is already part of the slug per R13 (the agent generates
    # ``{topic}-2`` and passes that as the topic argument). Per spec R9:
    # "When the slug has a -N suffix (per R13 re-run semantics), the
    # resolver returns cortex/research/{topic}-N/events.log" -- i.e. the same
    # research/{slug}/events.log shape, with the slug already including
    # the suffix.
    return repo_root / "cortex" / "research" / topic / "events.log"


def _has_rerun_suffix(topic: str) -> bool:
    """Return True if ``topic`` ends with a ``-N`` decimal suffix (N >= 2)."""
    m = _RERUN_SUFFIX_RE.search(topic)
    if not m:
        return False
    try:
        return int(m.group(1)) >= 2
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Atomic events.log append (tempfile + os.replace) -- ported from
# critical_review.py to keep both helpers consistent.
# ---------------------------------------------------------------------------

def append_event(events_log_path: Path, event: dict) -> None:
    """Atomically append a JSON event line to ``events_log_path``.

    Uses tempfile + ``os.replace`` rather than ``open(path, 'a')`` so the
    append is atomic against concurrent emitters.

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
# Event payload validators
# ---------------------------------------------------------------------------

_CHECKPOINT_VALUES = frozenset({"research-decompose", "decompose-commit"})
_RESPONSE_VALUES = frozenset({
    "approve",
    "revise",
    "drop",
    "promote-sub-topic",
    "approve-all",
    "revise-piece",
    "drop-piece",
})
_STATUS_VALUES = frozenset({"draft", "approved", "revised", "walk-back"})


def _validate_architecture_payload(
    topic: str,
    piece_count: int,
    has_why_n_justification: bool,
    status: str,
    re_walk_attempt: int | None,
) -> None:
    _validate_topic_slug(topic)
    if not isinstance(piece_count, int) or piece_count < 0:
        raise ValueError(
            f"piece_count must be a non-negative int: got {piece_count!r}"
        )
    if not isinstance(has_why_n_justification, bool):
        raise ValueError(
            "has_why_n_justification must be bool: got "
            f"{type(has_why_n_justification).__name__}"
        )
    if status not in _STATUS_VALUES:
        raise ValueError(
            f"status must be one of {sorted(_STATUS_VALUES)}: got {status!r}"
        )
    if re_walk_attempt is not None and (
        not isinstance(re_walk_attempt, int) or re_walk_attempt < 0
    ):
        raise ValueError(
            f"re_walk_attempt must be a non-negative int or None: "
            f"got {re_walk_attempt!r}"
        )


def _validate_checkpoint_payload(
    topic: str,
    checkpoint: str,
    response: str,
    revision_round: int,
) -> None:
    _validate_topic_slug(topic)
    if checkpoint not in _CHECKPOINT_VALUES:
        raise ValueError(
            f"checkpoint must be one of {sorted(_CHECKPOINT_VALUES)}: "
            f"got {checkpoint!r}"
        )
    if response not in _RESPONSE_VALUES:
        raise ValueError(
            f"response must be one of {sorted(_RESPONSE_VALUES)}: "
            f"got {response!r}"
        )
    if not isinstance(revision_round, int) or revision_round < 0:
        raise ValueError(
            f"revision_round must be a non-negative int: got {revision_round!r}"
        )


def _validate_prescriptive_payload(
    topic: str,
    tickets_checked: int,
    flagged_count: int,
    flag_locations: list,
) -> None:
    _validate_topic_slug(topic)
    if not isinstance(tickets_checked, int) or tickets_checked < 0:
        raise ValueError(
            f"tickets_checked must be a non-negative int: got "
            f"{tickets_checked!r}"
        )
    if not isinstance(flagged_count, int) or flagged_count < 0:
        raise ValueError(
            f"flagged_count must be a non-negative int: got {flagged_count!r}"
        )
    if not isinstance(flag_locations, list):
        raise ValueError(
            f"flag_locations must be a list: got "
            f"{type(flag_locations).__name__}"
        )
    for i, loc in enumerate(flag_locations):
        if not isinstance(loc, dict):
            raise ValueError(
                f"flag_locations[{i}] must be a dict: got "
                f"{type(loc).__name__}"
            )
        for required_key in ("ticket", "section", "signal"):
            if required_key not in loc:
                raise ValueError(
                    f"flag_locations[{i}] missing required key "
                    f"{required_key!r}: {loc!r}"
                )


# ---------------------------------------------------------------------------
# Emit helpers (importable)
# ---------------------------------------------------------------------------

def emit_architecture_written(
    topic: str,
    piece_count: int,
    has_why_n_justification: bool,
    status: str,
    repo_root: Path,
    re_walk_attempt: int | None = None,
) -> Path:
    """Validate + emit one ``architecture_section_written`` event.

    Returns the events.log path written to.
    """
    _validate_architecture_payload(
        topic, piece_count, has_why_n_justification, status, re_walk_attempt
    )
    events_log = resolve_events_log_path(topic, repo_root)
    event: dict = {
        "ts": _now_iso(),
        "event": "architecture_section_written",
        "topic": topic,
        "piece_count": piece_count,
        "has_why_n_justification": has_why_n_justification,
        "status": status,
    }
    if re_walk_attempt is not None:
        event["re_walk_attempt"] = re_walk_attempt
    append_event(events_log, event)
    return events_log


def emit_checkpoint_response(
    topic: str,
    checkpoint: str,
    response: str,
    revision_round: int,
    repo_root: Path,
) -> Path:
    """Validate + emit one ``approval_checkpoint_responded`` event.

    Returns the events.log path written to.
    """
    _validate_checkpoint_payload(topic, checkpoint, response, revision_round)
    events_log = resolve_events_log_path(topic, repo_root)
    event = {
        "ts": _now_iso(),
        "event": "approval_checkpoint_responded",
        "topic": topic,
        "checkpoint": checkpoint,
        "response": response,
        "revision_round": revision_round,
    }
    append_event(events_log, event)
    return events_log


def emit_prescriptive_check(
    topic: str,
    tickets_checked: int,
    flagged_count: int,
    flag_locations: list,
    repo_root: Path,
) -> Path:
    """Validate + emit one ``prescriptive_check_run`` event.

    Returns the events.log path written to.
    """
    _validate_prescriptive_payload(
        topic, tickets_checked, flagged_count, flag_locations
    )
    events_log = resolve_events_log_path(topic, repo_root)
    event = {
        "ts": _now_iso(),
        "event": "prescriptive_check_run",
        "topic": topic,
        "tickets_checked": tickets_checked,
        "flagged_count": flagged_count,
        "flag_locations": flag_locations,
    }
    append_event(events_log, event)
    return events_log


# ---------------------------------------------------------------------------
# CLI subcommand dispatch
# ---------------------------------------------------------------------------

def _resolve_repo_root_arg(args: argparse.Namespace) -> Path | None:
    if args.repo_root:
        return Path(args.repo_root).resolve()
    try:
        return Path(_default_repo_root()).resolve()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return None


def _cmd_resolve_events_log_path(args: argparse.Namespace) -> int:
    repo_root = _resolve_repo_root_arg(args)
    if repo_root is None:
        return 2
    try:
        target = resolve_events_log_path(args.topic, repo_root)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    sys.stdout.write(str(target) + "\n")
    return 0


def _cmd_emit_architecture_written(args: argparse.Namespace) -> int:
    repo_root = _resolve_repo_root_arg(args)
    if repo_root is None:
        return 2
    try:
        target = emit_architecture_written(
            topic=args.topic,
            piece_count=args.piece_count,
            has_why_n_justification=args.has_why_n_justification,
            status=args.status,
            repo_root=repo_root,
            re_walk_attempt=args.re_walk_attempt,
        )
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    except OSError as e:
        print(f"Failed to append architecture_section_written event: {e}",
              file=sys.stderr)
        return 2
    sys.stdout.write(str(target) + "\n")
    return 0


def _cmd_emit_checkpoint_response(args: argparse.Namespace) -> int:
    repo_root = _resolve_repo_root_arg(args)
    if repo_root is None:
        return 2
    try:
        target = emit_checkpoint_response(
            topic=args.topic,
            checkpoint=args.checkpoint,
            response=args.response,
            revision_round=args.revision_round,
            repo_root=repo_root,
        )
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    except OSError as e:
        print(f"Failed to append approval_checkpoint_responded event: {e}",
              file=sys.stderr)
        return 2
    sys.stdout.write(str(target) + "\n")
    return 0


def _cmd_emit_prescriptive_check(args: argparse.Namespace) -> int:
    repo_root = _resolve_repo_root_arg(args)
    if repo_root is None:
        return 2
    # flag_locations comes in as a JSON string on the CLI (stdin or arg).
    if args.flag_locations_json == "-":
        raw = sys.stdin.read()
    else:
        raw = args.flag_locations_json
    try:
        flag_locations = json.loads(raw) if raw.strip() else []
    except json.JSONDecodeError as e:
        print(f"--flag-locations-json must be valid JSON: {e}", file=sys.stderr)
        return 2
    try:
        target = emit_prescriptive_check(
            topic=args.topic,
            tickets_checked=args.tickets_checked,
            flagged_count=args.flagged_count,
            flag_locations=flag_locations,
            repo_root=repo_root,
        )
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    except OSError as e:
        print(f"Failed to append prescriptive_check_run event: {e}",
              file=sys.stderr)
        return 2
    sys.stdout.write(str(target) + "\n")
    return 0


# ---------------------------------------------------------------------------
# argparse wiring
# ---------------------------------------------------------------------------

def _add_repo_root_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--repo-root",
        default=None,
        help="Override repo root (default: git rev-parse --show-toplevel).",
    )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python3 -m cortex_command.discovery",
        description=(
            "Atomic CLI helpers for the /cortex-core:discovery skill. "
            "Fuses payload-validation + slug-to-events.log resolution + "
            "JSONL append into single subprocess calls so the orchestrator-LLM "
            "cannot silently drop fields or hardcode the events.log path."
        ),
    )
    sub = p.add_subparsers(dest="command", required=True)

    # resolve-events-log-path
    rp = sub.add_parser(
        "resolve-events-log-path",
        help=(
            "Resolve the events.log target for a topic slug, honoring the "
            "-N re-run suffix (R13) and active-lifecycle env override (EVT-1)."
        ),
    )
    _add_repo_root_arg(rp)
    rp.add_argument("--topic", required=True, help="Discovery topic slug.")
    rp.set_defaults(func=_cmd_resolve_events_log_path)

    # emit-architecture-written
    ea = sub.add_parser(
        "emit-architecture-written",
        help="Validate and emit one architecture_section_written event.",
    )
    _add_repo_root_arg(ea)
    ea.add_argument("--topic", required=True)
    ea.add_argument("--piece-count", required=True, type=int)
    ea.add_argument(
        "--has-why-n-justification",
        required=True,
        choices=("true", "false"),
    )
    ea.add_argument(
        "--status",
        required=True,
        choices=sorted(_STATUS_VALUES),
    )
    ea.add_argument(
        "--re-walk-attempt",
        type=int,
        default=None,
        help="Optional R12 re-walk attempt counter.",
    )
    ea.set_defaults(
        func=lambda a: _cmd_emit_architecture_written(
            _coerce_bool_namespace(a, "has_why_n_justification")
        )
    )

    # emit-checkpoint-response
    ec = sub.add_parser(
        "emit-checkpoint-response",
        help="Validate and emit one approval_checkpoint_responded event.",
    )
    _add_repo_root_arg(ec)
    ec.add_argument("--topic", required=True)
    ec.add_argument(
        "--checkpoint",
        required=True,
        choices=sorted(_CHECKPOINT_VALUES),
    )
    ec.add_argument(
        "--response",
        required=True,
        choices=sorted(_RESPONSE_VALUES),
    )
    ec.add_argument(
        "--revision-round",
        required=True,
        type=int,
        help="Revision-loop counter (0 for the first response).",
    )
    ec.set_defaults(func=_cmd_emit_checkpoint_response)

    # emit-prescriptive-check
    ep = sub.add_parser(
        "emit-prescriptive-check",
        help="Validate and emit one prescriptive_check_run event.",
    )
    _add_repo_root_arg(ep)
    ep.add_argument("--topic", required=True)
    ep.add_argument("--tickets-checked", required=True, type=int)
    ep.add_argument("--flagged-count", required=True, type=int)
    ep.add_argument(
        "--flag-locations-json",
        required=True,
        help=(
            "JSON list of {ticket, section, signal} dicts. Pass '-' to read "
            "JSON from stdin."
        ),
    )
    ep.set_defaults(func=_cmd_emit_prescriptive_check)

    return p


def _coerce_bool_namespace(args: argparse.Namespace, name: str) -> argparse.Namespace:
    """Coerce a "true"/"false" argparse string into a real Python bool."""
    raw = getattr(args, name)
    setattr(args, name, raw == "true")
    return args


def main(argv: list[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
