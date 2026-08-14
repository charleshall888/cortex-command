"""Single main-root-anchored, worktree-aware events.log resolver for machine verbs.

This module pins **one** resolver that the served machine verbs (``next`` /
``advance`` / ``describe``) and the claim/commit transition primitive all use to
locate a feature's ``events.log``. Because events.log is the only durable
lifecycle state, a worktree session that resolved the log two different ways
would split into two logs — and, worse, two flock domains — silently forking
the single source of truth (hazard 1). Pinning every machine-verb path to this
resolver closes that split by construction.

**Flock domain = sibling lockfile of the resolved path.** The append discipline
in ``lifecycle_event._append_event_atomic`` serialises writes on the advisory
lock file ``{events_log}.lock`` sitting beside the resolved ``events.log``. Two
callers therefore share a flock domain iff they resolve the *same* physical
events.log path; :func:`resolve_flock_path` names that sibling explicitly so a
caller can record and assert it. Resolving the log two ways is exactly resolving
two flock domains — hence one resolver, not two.

Resolution semantics reuse ``interactive_lock._resolve_main_repo_root`` verbatim
(imported, not reimplemented, so there is exactly one implementation of the
walk):

  * ``CORTEX_REPO_ROOT`` is honoured first, ``.resolve()``-canonicalized (the
    overnight env-pin).
  * Otherwise the walk is worktree-aware: from ``Path.cwd()`` upward, the first
    ``.git`` **file** (a worktree gitfile) is parsed via
    ``interactive_lock._main_root_from_gitfile`` (which reads the worktree admin
    dir's ``commondir`` pointer) to reach the **main** repo root, guarded by
    ``(candidate / "cortex").is_dir()``.

This is deliberately distinct from the two CWD-flavoured resolvers in
``common``:

  * ``common._resolve_user_project_root_from_cwd`` (CWD-only, ignores
    ``CORTEX_REPO_ROOT``) — no longer what any appending verb uses: #484 routed
    every *typed* ``log_event`` subcommand through :func:`resolve_events_log`.
    It survives here as the CWD flavour :func:`detect_split_log` reports
    against and :func:`resolve_verdict_root` falls back to. From a worktree CWD
    carrying a co-located ``cortex/`` it returns the **worktree-local** root —
    the copy a pre-#484 typed append landed in.
  * ``common._resolve_user_project_root`` (env-honouring, else first
    ``cortex/``-bearing ancestor) — what ``enter.py`` uses.

That divergence **was** the live hazard, and #484 measured its cost: a lifecycle
driven from a worktree wrote half its history to the main-root log (``next`` /
``advance``) and half to the worktree copy (``event`` / ``review-brief``), with
no verb reporting the split. Every appending verb now anchors here.
:func:`detect_split_log` is the reporting half — the CWD-anchored path a legacy
caller *would* have written, surfaced when it exists and diverges, so an already
split lifecycle is visible rather than merely prevented going forward.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from cortex_command.interactive_lock import _resolve_main_repo_root

__all__ = [
    "resolve_main_repo_root",
    "resolve_verdict_root",
    "resolve_events_log",
    "resolve_flock_path",
    "detect_split_log",
]


def resolve_main_repo_root() -> Path:
    """Return the MAIN repo root for the machine-verb path, regardless of CWD.

    Thin public alias for ``interactive_lock._resolve_main_repo_root`` so the
    machine verbs and the claim/commit primitive share one main-root anchoring
    with the interactive lock (same lock/log convergence guarantee) without
    re-deriving the worktree walk. Honours ``CORTEX_REPO_ROOT`` first, else
    walks up from the CWD and parses the first ``.git`` worktree gitfile to the
    main root (guarded by a ``cortex/`` existence check); falls back to the
    shared ``common`` resolver when neither applies.

    Returns:
        Resolved absolute path to the main cortex project root.
    """
    return _resolve_main_repo_root()


def resolve_verdict_root(feature_slug: str) -> Path:
    """Return the root a verdict about *feature_slug* may trust.

    :func:`resolve_main_repo_root` honours ``CORTEX_REPO_ROOT`` verbatim and
    unchecked (``interactive_lock.py:177-179``), and ``docs/setup.md`` tells
    operators to export it precisely so the ``cortex-*`` shims run from outside
    a project. A stale or wrong value therefore reaches the artifact reads as a
    real root, where "no ``pr.json``, no ``events.log``" is indistinguishable
    from a genuinely fresh lifecycle — which is what drove ``complete_route``'s
    ``on_main`` finalize arm. This wrapper validates before it trusts:

      1. Take :func:`resolve_main_repo_root`; if ``{root}/cortex/lifecycle/
         {feature_slug}`` is a directory, it holds this lifecycle — return it.
      2. Otherwise fall back to the CWD walk
         (``common._resolve_user_project_root_from_cwd``) and return that root
         when *it* holds the slug directory.
      3. Otherwise the env/walk result from step 1 stands.

    The check is **slug-scoped**, not a bare ``cortex/`` existence test, so a
    populated but *different* cortex project is rejected too. Step 3 keeps the
    never-crash contract and preserves today's behaviour for a lifecycle whose
    directory does not exist yet: a wholly bogus root still reaches the read,
    which simply finds nothing.

    Args:
        feature_slug: Feature slug the caller is about to read artifacts for.

    Returns:
        Resolved absolute path to the project root the caller may anchor
        ``events.log`` / ``pr.json`` beneath.
    """
    from cortex_command.common import _resolve_user_project_root_from_cwd

    root = resolve_main_repo_root()
    if (root / "cortex" / "lifecycle" / feature_slug).is_dir():
        return root

    try:
        cwd_root = _resolve_user_project_root_from_cwd()
    except Exception:  # noqa: BLE001 — never-crash: the env result stands
        return root
    if (cwd_root / "cortex" / "lifecycle" / feature_slug).is_dir():
        return cwd_root
    return root


def resolve_events_log(feature_slug: str) -> Path:
    """Return the main-root-anchored ``events.log`` path for *feature_slug*.

    The single physical log path every machine verb and the claim/commit
    primitive must agree on. Anchored at :func:`resolve_main_repo_root`, so a
    worktree session resolves the **main-root** log rather than a worktree-local
    copy — the ``next`` envelope records this path and ``advance`` asserts the
    caller's expectation matches it.

    Args:
        feature_slug: Feature slug (e.g. ``"374-served-next-advance-loop"``).

    Returns:
        Resolved absolute path to ``cortex/lifecycle/{feature_slug}/events.log``.
    """
    return (
        resolve_main_repo_root()
        / "cortex"
        / "lifecycle"
        / feature_slug
        / "events.log"
    )


def resolve_flock_path(events_log: Path) -> Path:
    """Return the sibling lockfile — the flock domain — for *events_log*.

    The flock domain is the advisory lock file ``{events_log}.lock`` beside the
    resolved log, matching ``lifecycle_event._append_event_atomic``'s
    ``log_path.parent / f"{log_path.name}.lock"``. Two callers serialise against
    each other iff they resolve the same ``events_log``; naming the sibling here
    lets a caller record and assert its flock domain alongside the log path.

    Args:
        events_log: The resolved ``events.log`` path (from
            :func:`resolve_events_log`).

    Returns:
        The sibling ``{events_log}.lock`` path in the same directory.
    """
    return events_log.parent / f"{events_log.name}.lock"


def detect_split_log(feature_slug: str, resolved: Path) -> Optional[Path]:
    """Return an already-forked CWD-anchored ``events.log``, or ``None``.

    Preventing new splits does not heal the ones already on disk (#484): a
    worktree session that ran the pre-fix verbs left a second, divergent log
    that still parses, still looks plausible, and — because the worktree copy is
    git-tracked — merges a forked history if committed. Every appending verb
    calls this so the fork is *named* on the run that would otherwise silently
    ignore it.

    Returns the CWD-anchored path only when it both exists and differs from
    *resolved*; a non-worktree session, or one whose two resolutions agree,
    yields ``None``. Never raises — an unresolvable CWD root just means there is
    no second path to warn about.

    Args:
        feature_slug: Feature slug the caller resolved *resolved* for.
        resolved: The main-root-anchored path from :func:`resolve_events_log`.

    Returns:
        The divergent CWD-anchored ``events.log``, or ``None``.
    """
    from cortex_command.common import _resolve_user_project_root_from_cwd

    try:
        cwd_root = _resolve_user_project_root_from_cwd()
    except Exception:  # noqa: BLE001 — a report-only path never blocks the write
        return None
    candidate = (
        cwd_root / "cortex" / "lifecycle" / feature_slug / "events.log"
    )
    if candidate.resolve() == Path(resolved).resolve():
        return None
    return candidate if candidate.is_file() else None
