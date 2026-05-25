"""WorktreeCreate-bypass implementation test (R18).

Pins the actual invariant ADR-0004's bypass clause protects: that
``cortex_command/pipeline/worktree.py::create_worktree`` invokes
``git worktree add`` directly via ``subprocess`` (not via Claude Code's
``claude --worktree`` launch path).

The mid-session auto-enter feature (lifecycle-implement-auto-enter-worktree-via)
depends on this non-expansion — if ``create_worktree`` ever switched to
spawning a fresh Claude session, the EnterWorktree mid-session mode would
silently regress.

The load-bearing assertion reads the function source via
``inspect.getsource(create_worktree)`` and asserts the relevant tokens
appear / don't appear. The defensive ``hooks.json`` grep is a secondary
guard against a future hook registration on the ``EnterWorktree`` event.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from cortex_command.pipeline.worktree import create_worktree

REPO_ROOT = Path(__file__).parent.parent
HOOKS_JSON = REPO_ROOT / "plugins" / "cortex-core" / "hooks" / "hooks.json"


def test_create_worktree_invokes_git_worktree_add_directly() -> None:
    """create_worktree's source contains the 'git', 'worktree', 'add' subprocess
    invocation tokens AND does not contain 'claude', '--worktree' tokens.

    This is the load-bearing assertion: it pins the implementation detail
    that ADR-0004's bypass clause actually protects.
    """
    source = inspect.getsource(create_worktree)

    # Positive: the function invokes `git worktree add` directly via subprocess.
    assert "'git'" in source or '"git"' in source, (
        "create_worktree source missing 'git' subprocess arg"
    )
    assert "'worktree'" in source or '"worktree"' in source, (
        "create_worktree source missing 'worktree' subprocess arg"
    )
    assert "'add'" in source or '"add"' in source, (
        "create_worktree source missing 'add' subprocess arg"
    )

    # Negative: the function does NOT shell out to `claude --worktree`.
    assert "'claude'" not in source and '"claude"' not in source, (
        "create_worktree source unexpectedly contains 'claude' subprocess arg — "
        "ADR-0004 bypass invariant violated"
    )
    assert "--worktree" not in source, (
        "create_worktree source unexpectedly contains '--worktree' flag — "
        "ADR-0004 bypass invariant violated"
    )


def test_hooks_json_has_no_enterworktree_registration() -> None:
    """Defensive secondary check: no hook is registered against the
    ``EnterWorktree`` event in ``plugins/cortex-core/hooks/hooks.json``.

    Not the load-bearing assertion (R18 framing per spec). Catches a future
    hook registration on the EnterWorktree event but is structurally
    independent of ``create_worktree``'s implementation.
    """
    contents = HOOKS_JSON.read_text()
    assert contents.count("EnterWorktree") == 0, (
        "hooks.json unexpectedly contains EnterWorktree event registration"
    )
