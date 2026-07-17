"""cortex-lifecycle-enter — composes the lifecycle Step-2 entry into one call.

Before the corpus-trim wave-2 follow-up, the lifecycle skill's Step 2 narrated
four back-to-back CLI calls in prose: create the lifecycle ``index.md``, run the
lifecycle-start backlog write-back, run ``cortex init --ensure``, and record the
session id in ``.session``. This verb composes those four in-process and returns
ONE ``{state, backlog_status, ...}`` JSON envelope, mirroring how
``cortex-lifecycle-prepare-worktree`` composed the Implement §1a mechanics.

Every discriminant is caller-passed — ``--feature --session-id --backend
--phase --backlog-file`` all come from the Step-1 resolver's output. Per
**ADR-0019's structural-guard principle** the verb NEVER self-resolves the
backend nor re-derives new-vs-resume: ``--phase none`` (a brand-new lifecycle)
is the only signal that gates the lifecycle-slug association, and it is the
caller who passes it. The composed ``start_sync.sync`` acts on the passed
``--backend`` verbatim.

``backlog_status`` reports the pre-entry state of the backlog item so the skill
can make its own close/continue decision — the verb **never auto-closes** an
``already_complete`` item. It is read BEFORE ``sync`` runs, because ``sync``
writes ``in_progress`` back to the item and would otherwise mask the original
status:

  no_match          — ``--backlog-file ""`` (resolver exit-3): no item to read.
  already_complete   — the item's frontmatter ``status:`` scalar is ``complete``.
  open               — any other status (or an unreadable/absent item — never
                       reported as complete, preserving the never-auto-close
                       safety invariant).

An ``already_complete`` item short-circuits the whole composition into the
``needs-decision`` state UNLESS ``--acknowledge-complete`` is passed. This
preserves — structurally, not in prose — the pre-verb carve-out where a
completed backlog item created no lifecycle artifacts: the return happens BEFORE
``create_index``/``sync``/``init_ensure``/``.session``, so a decision-required
entry leaves the tree untouched. The skill asks Close/Continue; **Continue**
re-runs the verb with ``--acknowledge-complete`` (a caller-passed acknowledgement
that keeps the verb a dumb arg-actor — it never decides on its own), which drives
the full composition normally.

States (the ``state`` discriminant reflects the ``cortex init --ensure`` gate,
the one composed step that can refuse a lifecycle entry — plus the
``needs-decision`` short-circuit above):

  ready         — all four steps succeeded; ``.session`` was written.
  needs-decision — the backlog item is ``already_complete`` and
                  ``--acknowledge-complete`` was not passed. NO side effect ran
                  (no index, no sync, no init-ensure, no ``.session``); the skill
                  must resolve Close/Continue before the verb re-runs.
  blocked       — ``cortex init --ensure`` returned 2 (a user-correctable gate,
                  e.g. invoked inside an attached git worktree). ``.session`` is
                  NOT written — the environment must be fixed and the verb re-run
                  (create-index/start-sync are idempotent skip-if-exists forms).
  ensure-failed — ``cortex init --ensure`` returned a non-zero code other than 2
                  (an unexpected runtime failure).
  error         — an unexpected exception escaped the composition; ``main``
                  catches it so the CLI always emits a JSON struct and exits 0
                  rather than a traceback (the ``prepare_worktree`` pattern).

Three hard exit codes bypass the envelope entirely (the caller handles them
exactly as it handled the underlying verbs). Exits 1 and 2 propagate from the
composed primitives, mirroring their own CLIs; exit 3 is this verb's own:

  exit 1 — ``create_index`` raised ``OSError`` (a non-empty ``--backlog-file``
           did not resolve to an existing ticket; a contract violation).
  exit 2 — ``sync`` raised ``_Exit2`` (a ``cortex-update-item`` call hit an
           ambiguous slug; its candidate list is already on stderr).
  exit 3 — a fail-loud guard rejected the invocation before any side effect ran
           (``_GuardRejected``): an unsafe ``--feature`` token, a resume
           (``--phase`` != ``none``) of a lifecycle whose dir does not exist, or
           an entry whose target dir already belongs to a DIFFERENT backlog item.
           These are contract violations of the verb's OWN args + filesystem
           preconditions, so they deliberately do NOT route through the
           ``state: "error"`` channel — that is the exit-0 catch-all for
           *unexpected* exceptions, and is invisible to every caller that
           branches on the exit code rather than parsing stdout JSON (including
           ``bin/cortex-lifecycle-enter``'s ``exec`` passthrough wrapper).

The write root resolves via ``_resolve_user_project_root`` (honoring
``CORTEX_REPO_ROOT``) so ``.session`` lands in the same tree as the
``create-index`` and ``start-sync`` write-backs under overnight (#319
precedent) — never a cwd-relative path that could diverge when the runner's
cwd differs from the recorded repo root.

Root-resolution invariant across the verb family: ``enter`` resolves via
``CORTEX_REPO_ROOT`` (env-honoring, as above) while ``finalize`` and
``register-artifact`` resolve from cwd; callers must ensure the two agree
(overnight runs with cwd == repo root).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import List, Optional

from cortex_command.backlog import _telemetry
from cortex_command.backlog.resolve_item import _parse_frontmatter
from cortex_command.common import (
    CortexProjectRootError,
    _resolve_user_project_root,
)
from cortex_command.lifecycle import init_ensure
from cortex_command.lifecycle.create_index import create_index
from cortex_command.lifecycle.protocol import PROTOCOL_VERSION
from cortex_command.lifecycle.start_sync import _Exit2, sync

KNOWN_STATES = ("ready", "needs-decision", "blocked", "ensure-failed", "error")

# First-match-wins frontmatter status scalar; ``.`` never crosses the newline so
# the capture is confined to the one ``status:`` line.
_STATUS_RE = re.compile(r"^status:\s*(\S+)", re.MULTILINE)


class _GuardRejected(Exception):
    """Signals a fail-loud guard rejection to ``main`` (→ stderr + exit 3).

    Deliberately NOT an ``OSError`` subclass: ``main``'s ``except OSError`` arm
    is the exit-1 create-index contract and would silently swallow this.
    """


# gate-class: hygiene
def _reject_unsafe_slug(feature: str) -> None:
    """Raise ``_GuardRejected`` when *feature* is empty or carries a path
    separator / ``..`` — a path-traversal guard applied BEFORE any filesystem
    access (including the ``--backlog-file`` read). Returns None when the slug is
    safe to use as a directory component.

    The house ``describe.py:_reject_unsafe_slug`` blacklist predicate, raising
    instead of returning an error envelope: this verb's guards must surface as a
    nonzero exit, not as an exit-0 ``state: "error"`` payload. The blacklist (not
    ``wontfix_cli``'s stricter ``_SLUG_RE`` whitelist) is deliberate — the
    grandfathered corpus holds numeric-keyed lifecycles (``374/``, ``378/``) that
    a kebab-only whitelist would be one edit away from orphaning.
    """
    if not feature or "/" in feature or "\\" in feature or ".." in feature:
        raise _GuardRejected(
            f"unsafe feature slug {feature!r}: no path separators or '..'"
        )


# gate-class: hygiene
def _reject_missing_lifecycle(feature: str, phase: str, root: Path) -> None:
    """Raise ``_GuardRejected`` when *phase* is a resume (``!= "none"``) and
    ``{root}/cortex/lifecycle/{feature}/`` is not an existing directory.

    The fourth application of ``critical_review._lifecycle_dir_exists``: the
    guard lives in the caller, never in the write primitive — ``create_index``
    must keep materializing the dir for the legitimate ``--phase none``
    fresh-lifecycle first write. ``--phase none`` is the caller-passed
    brand-new-lifecycle signal (ADR-0019: the verb never re-derives
    new-vs-resume), so it is the only shape allowed to create a dir; every other
    phase asserts the lifecycle already exists, and a resume that finds nothing
    fails loud rather than inventing a shadow lifecycle the morning report can
    never find (#379).
    """
    if phase == "none":
        return
    if (root / "cortex" / "lifecycle" / feature).is_dir():
        return
    raise _GuardRejected(
        f"no such lifecycle {feature!r}: --phase {phase!r} is a resume, but "
        f"cortex/lifecycle/{feature}/ does not exist, so there is nothing to "
        "resume. Either the dir vanished mid-flight (deleted between the "
        "resolver and this call — recover the dir, then re-run), or the caller "
        "mis-threaded the identity (a raw token such as a ticket number passed "
        "where the resolver's canonical slug belonged — re-run "
        "cortex-lifecycle-next and thread its resolved --feature verbatim). "
        "Creating nothing."
    )


def _parent_uuid(path: Path) -> Optional[str]:
    """Return *path*'s frontmatter ``uuid``/``parent_backlog_uuid`` scalar, or
    ``None`` when it is absent, null, or unreadable.

    ``create_index._render`` emits the literal ``null`` for an uuid-less Shape-B
    index (``create_index.py:112``), which ``yaml.safe_load`` yields as ``None``;
    the defensive ``"null"`` string arm covers a hand-edited quoted form. Either
    way the answer is "no uuid recorded" — never a uuid to compare against.

    A read/parse failure is also ``None``: an unresolvable ``--backlog-file`` is
    already ``create_index``'s exit-1 contract, and a malformed ``index.md``
    cannot establish that two items DIFFER, which is what the guard must prove
    before it refuses. Neither is this guard's trip to make.
    """
    try:
        fm = _parse_frontmatter(path)
    except Exception:  # noqa: BLE001 — OSError | yaml.YAMLError; both mean "cannot compare"
        return None
    value = fm.get("uuid", fm.get("parent_backlog_uuid"))
    if value is None or str(value) in ("", "null"):
        return None
    return str(value)


# gate-class: hygiene
def _reject_cross_item_merge(feature: str, backlog_file: str, root: Path) -> None:
    """Raise ``_GuardRejected`` when ``{root}/cortex/lifecycle/{feature}/index.md``
    already records a DIFFERENT backlog item than *backlog_file* names.

    Closes the silent cross-ticket merge that ``create_index``'s skip-if-exists
    (``create_index.py:164-165``) makes reachable once derived-slug identity lands:
    two items whose titles truncate to the same 6-word slug would otherwise land
    in one dir, the second entry silently adopting the first's index. The dir is
    left byte-identical — the guard only reads.

    The comparison is on the **uuid**, never the filename: a uuid is immutable
    across renames and renumbering, so it is the only field that still answers
    "same ticket?" after a title edit — the very drift that motivates the
    derived-slug pin.

    **Inert by design when *backlog_file* is ``""``** (the ``no_match`` /
    ad-hoc Shape-B entry): there is no item to collide on, so there is nothing
    to compare and the check is skipped. A stated coverage limit, not an
    oversight.
    """
    if not backlog_file:
        return
    existing = _parent_uuid(root / "cortex" / "lifecycle" / feature / "index.md")
    if existing is None:
        return
    incoming = _parent_uuid(root / "cortex" / "backlog" / Path(backlog_file).name)
    if incoming is None or incoming == existing:
        return
    raise _GuardRejected(
        f"lifecycle {feature!r} already belongs to backlog item "
        f"{existing!r}, but --backlog-file {Path(backlog_file).name!r} is item "
        f"{incoming!r}. Entering would silently merge two tickets into one "
        "lifecycle. Give the new item its own --feature slug (two titles "
        "truncating to the same slug is the usual cause), or re-run "
        "cortex-lifecycle-next and thread its resolved --feature verbatim if "
        "the identity was mis-threaded. Changing nothing."
    )


def _backlog_status(backlog_file: str, root: Path) -> str:
    """Report the pre-entry backlog status (``no_match``/``already_complete``/
    ``open``) WITHOUT ever auto-closing.

    An empty *backlog_file* is ``no_match``. Otherwise the item is read from the
    canonical ``cortex/backlog/`` dir and its first ``status:`` scalar matched;
    only a literal ``complete`` yields ``already_complete``. An unreadable or
    absent item is ``open`` — never ``already_complete`` — so a read failure can
    never be mistaken for a completed lifecycle.
    """
    if not backlog_file:
        return "no_match"
    path = root / "cortex" / "backlog" / Path(backlog_file).name
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return "open"
    match = _STATUS_RE.search(text)
    if match is not None and match.group(1) == "complete":
        return "already_complete"
    return "open"


def _write_session(feature: str, session_id: str, root: Path) -> None:
    """Record *session_id* in ``{root}/cortex/lifecycle/{feature}/.session``."""
    path = root / "cortex" / "lifecycle" / feature / ".session"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(session_id, encoding="utf-8")


def enter(
    *,
    feature: str,
    session_id: str,
    backend: str,
    phase: str,
    backlog_file: str,
    root: Path,
    acknowledge_complete: bool = False,
) -> dict:
    """Compose create-index, start-sync, init-ensure, and the ``.session`` write.

    Returns the ``{state, backlog_status, ...}`` envelope. Raises ``OSError``
    (create-index: unresolved non-empty backlog-file → the caller maps to exit 1)
    or ``_Exit2`` (start-sync: ambiguous slug → exit 2). ``backlog_status`` is
    read first, before ``sync`` mutates the item's status to ``in_progress``.

    An ``already_complete`` item returns ``needs-decision`` and runs NO composed
    step unless *acknowledge_complete* is set — the structural form of the
    pre-verb "completed item creates no artifacts" carve-out. The verb never
    decides on its own; the acknowledgement is caller-passed.

    All three fail-loud guards run FIRST — before ``_backlog_status``'s read,
    before the ``needs-decision`` short-circuit, and before ``create_index`` — so
    an unsafe token never reaches a filesystem op, and a rejected invocation is a
    ``_GuardRejected`` (→ exit 3) rather than a ``needs-decision`` envelope that
    a caller would read as a routine Close/Continue prompt. ``_reject_unsafe_slug``
    stays strictly first: the two guards behind it build paths from *feature*, so
    the token must be proven safe before either reads the filesystem.
    """
    _reject_unsafe_slug(feature)
    _reject_missing_lifecycle(feature, phase, root)
    _reject_cross_item_merge(feature, backlog_file, root)

    backlog_status = _backlog_status(backlog_file, root)

    if backlog_status == "already_complete" and not acknowledge_complete:
        # Short-circuit BEFORE any side effect so the tree is untouched. The skill
        # resolves Close/Continue; Continue re-runs with --acknowledge-complete.
        return {
            "state": "needs-decision",
            "backlog_status": backlog_status,
            "feature": feature,
        }

    index_result = create_index(feature, backlog_file, root)  # OSError → exit 1
    sync_result = sync(
        backend=backend,
        backlog_file=backlog_file,
        phase=phase,
        session_id=session_id,
        lifecycle_slug=feature,
    )  # _Exit2 → exit 2

    ensure_code = init_ensure.main([])
    if ensure_code == 0:
        state = "ready"
        _write_session(feature, session_id, root)
    elif ensure_code == 2:
        state = "blocked"
    else:
        state = "ensure-failed"

    return {
        "state": state,
        "backlog_status": backlog_status,
        "feature": feature,
        "index": index_result.get("signal"),
        "sync": sync_result.get("signal"),
        "ensure_code": ensure_code,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-lifecycle-enter",
        description=(
            "Compose the lifecycle Step-2 entry — create-index, start-sync, "
            "init-ensure, and the .session write — into a single "
            "{state, backlog_status, ...} JSON struct on stdout. All "
            "discriminants are caller-passed (ADR-0019); exit 1/2 propagate the "
            "composed primitives' contract failures, exit 3 is a fail-loud guard "
            "rejection (unsafe --feature, a resume of a lifecycle that does not "
            "exist, or a target dir owned by a different backlog item), else "
            "exit 0."
        ),
    )
    parser.add_argument("--feature", required=True, metavar="SLUG", help="Lifecycle feature slug.")
    parser.add_argument(
        "--session-id",
        required=True,
        help="Lifecycle session id ($LIFECYCLE_SESSION_ID); recorded in .session.",
    )
    parser.add_argument(
        "--backend",
        required=True,
        help="Caller-resolved backlog backend (cortex-backlog | none | other).",
    )
    parser.add_argument(
        "--phase",
        required=True,
        help="Current phase (none for a brand-new lifecycle, else any value).",
    )
    parser.add_argument(
        "--backlog-file",
        required=True,
        metavar="BASENAME",
        help='Resolver filename basename (e.g. 326-foo.md); "" on no match.',
    )
    parser.add_argument(
        "--acknowledge-complete",
        action="store_true",
        help=(
            "Caller-passed acknowledgement of the Continue decision for an "
            "already_complete item: proceed through the full composition. "
            "Without it, an already_complete item returns needs-decision and "
            "runs no composed step (no side effects)."
        ),
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _telemetry.log_invocation("cortex-lifecycle-enter")
    args = _build_parser().parse_args(argv)
    try:
        root = _resolve_user_project_root()
    except CortexProjectRootError as exc:
        sys.stderr.write(f"cortex-lifecycle-enter: {exc}\n")
        return 1
    try:
        result = enter(
            feature=args.feature,
            session_id=args.session_id,
            backend=args.backend,
            phase=args.phase,
            backlog_file=args.backlog_file,
            root=root,
            acknowledge_complete=args.acknowledge_complete,
        )
    except OSError as exc:
        sys.stderr.write(
            "cortex-lifecycle-enter: --backlog-file "
            f"{args.backlog_file!r} not found under cortex/backlog/ ({exc}). "
            "A non-empty --backlog-file must resolve to an existing ticket.\n"
        )
        return 1
    except _Exit2:
        return 2
    except _GuardRejected as exc:
        sys.stderr.write(f"cortex-lifecycle-enter: {exc}\n")
        return 3
    except Exception as exc:  # noqa: BLE001 — always emit a JSON struct, never a traceback
        result = {"state": "error", "message": repr(exc)}
    result["protocol"] = PROTOCOL_VERSION
    sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
