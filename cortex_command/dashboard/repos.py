"""The set of repositories one dashboard process serves, and their state.

Until this module existed the dashboard was single-root by construction: one
module-level ``DashboardState``, one polling loop, and a root resolved from
``CORTEX_REPO_ROOT`` at request time. Viewing a second repo meant stopping the
server and starting it again, which is the wrong shape for an operator whose
work spans sibling checkouts — the backlog corpora that matter here live in
several of them, and comparing two is exactly the moment the restart lands.

The shape is deliberately narrow. A repo is a root path, a slug derived from
its directory name, and a ``DashboardState`` of its own. Nothing is shared
between repos: each gets its own polling loop writing into its own state, so a
slow disk under one repo cannot stall another's poll, and a snapshot can never
be rendered against the wrong root.

Slugs, not indices, address a repo across the wire. An index would renumber
whenever the tracked set changed, which is the kind of identifier that silently
points at a different thing after a restart.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from cortex_command.common import CortexProjectRootError, _resolve_user_project_root
from cortex_command.dashboard.poller import DashboardState

#: Environment variable naming additional roots, separated by the platform's
#: path separator. Read once at startup; the tracked set is not live-editable,
#: because a repo appearing mid-run would need a polling loop started from a
#: request handler.
ROOTS_ENV = "CORTEX_DASHBOARD_ROOTS"

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify_root(root: Path) -> str:
    """Derive a URL-safe slug from a root's directory name.

    The directory name is what the operator calls the repo, so it is what the
    switcher shows and what the query string carries. A root whose name has no
    usable characters falls back to ``repo`` and is disambiguated by the
    caller.
    """
    name = _SLUG_STRIP.sub("-", root.name.lower()).strip("-")
    return name or "repo"


@dataclass(frozen=True)
class Repo:
    """One tracked repository."""

    slug: str
    label: str
    root: Path


@dataclass
class RepoRegistry:
    """The tracked repos, in display order, each with its own state.

    The first entry is the default: it is what a request with no ``repo``
    parameter resolves to, and it is the root the process was started against.
    """

    repos: list[Repo] = field(default_factory=list)
    states: dict[str, DashboardState] = field(default_factory=dict)

    @property
    def default(self) -> Repo | None:
        return self.repos[0] if self.repos else None

    @property
    def multi(self) -> bool:
        """Whether the switcher has anything to switch between.

        The single-repo case must look exactly as it did before this module
        existed — a chooser offering one choice is furniture, and most consumer
        repos will only ever track one.
        """
        return len(self.repos) > 1

    def resolve(self, slug: str | None) -> Repo | None:
        """Return the repo a request addressed, or the default.

        An unknown slug resolves to the default rather than raising. The slug
        arrives from a query string, so it is attacker- and typo-reachable, and
        a 500 on a bad one would be a worse answer than the page the operator
        was already looking at.
        """
        if slug:
            for repo in self.repos:
                if repo.slug == slug:
                    return repo
        return self.default

    def state_for(self, repo: Repo | None) -> DashboardState:
        """Return *repo*'s state, creating it on first use.

        A repo with no state yet returns an empty one rather than None: the
        view-models all treat ``backlog_snapshot is None`` as "not polled yet"
        and render a schema-complete empty page, which is the correct thing to
        show in the window between startup and the first poll.
        """
        if repo is None:
            return DashboardState()
        return self.states.setdefault(repo.slug, DashboardState())


def resolve_primary_root() -> Path:
    """Resolve the root a dashboard process leads with.

    Normally the cwd-derived project root. When that resolution fails — the
    operator ran ``cortex dashboard`` from somewhere that is not a cortex
    checkout, which is exactly what a bare from-anywhere launcher invites —
    the first entry of ``CORTEX_DASHBOARD_ROOTS`` stands in.

    This fallback is what makes that variable sufficient on its own. Without
    it the variable can only ever *add* repos alongside a primary resolved
    some other way, and the only other way to name a primary from outside a
    checkout is exporting ``CORTEX_REPO_ROOT`` — which ``docs/dashboard.md``
    forbids, because it is the unvalidated root funnel read by dozens of
    modules and would silently redirect backlog creation, lifecycle verbs, and
    overnight writes into whatever the dashboard happened to be pointed at.

    The first entry is taken verbatim rather than searched for a valid one.
    The lifespan's ``.claude/`` check still applies to whatever comes back, so
    a typo in that entry fails loudly naming the path; advancing quietly to
    the second entry would hide the typo behind a dashboard that looks correct
    and is simply missing a repo — the same class of silent wrongness this
    launcher work exists to close.
    """
    try:
        return _resolve_user_project_root()
    except CortexProjectRootError:
        for part in os.environ.get(ROOTS_ENV, "").split(os.pathsep):
            if part.strip():
                return Path(part.strip()).expanduser().resolve()
        raise


def resolve_roots(primary: Path, extra: list[str] | None = None) -> list[Path]:
    """Build the ordered, de-duplicated root list for one dashboard process.

    *primary* leads and is always kept, even if it carries no ``cortex/``
    directory — a freshly-initialised repo is a legitimate thing to point the
    dashboard at, and dropping it would leave a process serving nothing.
    Additional roots are dropped when they do not resolve to a directory,
    because those are typos rather than empty repos, and a switcher entry
    leading to a permanently blank page is worse than no entry.

    Order is preserved: the operator named these, and the order they named
    them in is the order the switcher shows.
    """
    ordered: list[Path] = []
    seen: set[Path] = set()

    def add(candidate: Path, *, require_dir: bool) -> None:
        resolved = candidate.expanduser().resolve()
        if require_dir and not resolved.is_dir():
            return
        if resolved in seen:
            return
        seen.add(resolved)
        ordered.append(resolved)

    add(primary, require_dir=False)

    from_env = os.environ.get(ROOTS_ENV, "")
    candidates = list(extra or [])
    candidates += [part for part in from_env.split(os.pathsep) if part.strip()]
    for candidate in candidates:
        add(Path(candidate.strip()), require_dir=True)

    return ordered


def build_registry(roots: list[Path]) -> RepoRegistry:
    """Assemble a registry over *roots*, assigning unique slugs.

    Two checkouts can share a directory name — a worktree and its origin, or
    the same project under two parents — so a colliding slug takes a numeric
    suffix rather than silently overwriting the earlier repo's state. The label
    stays the bare directory name in both cases; the slug is plumbing and the
    label is what the operator reads.
    """
    registry = RepoRegistry()
    used: set[str] = set()
    for root in roots:
        base = slugify_root(root)
        slug = base
        counter = 2
        while slug in used:
            slug = "%s-%d" % (base, counter)
            counter += 1
        used.add(slug)
        registry.repos.append(Repo(slug=slug, label=root.name or slug, root=root))
    return registry
