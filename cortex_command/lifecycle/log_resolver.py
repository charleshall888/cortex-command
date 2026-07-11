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
    ``CORTEX_REPO_ROOT``) — what ``log_event`` uses for the *typed* subcommands.
    From a worktree CWD carrying a co-located ``cortex/`` it returns the
    **worktree-local** root, so a typed append lands in the worktree copy.
  * ``common._resolve_user_project_root`` (env-honouring, else first
    ``cortex/``-bearing ancestor) — what ``enter.py`` uses.

That divergence is the live hazard. This resolver is the separate machine-verb
path; ``log_event`` / ``log_event_at`` are intentionally left on their legacy
CWD resolution for the typed subcommands and are **not** changed by this module.
"""

from __future__ import annotations

from pathlib import Path

from cortex_command.interactive_lock import _resolve_main_repo_root

__all__ = [
    "resolve_main_repo_root",
    "resolve_events_log",
    "resolve_flock_path",
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
