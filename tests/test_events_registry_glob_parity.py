"""Anti-drift parity test: events-registry inline matcher == shared helper.

``bin/cortex-check-events-registry`` is a standalone, extensionless script that
cannot import ``cortex_command``, so it carries an inline copy of the
``**``=zero-or-more-segments matcher. This test pins that inline copy to the
canonical ``cortex_command.lint._globs.matches_any_glob`` over a corpus
covering all nine Edge Case shapes from
``cortex/lifecycle/pre-commit-gates-silently-skip-deep/spec.md`` — so the two
implementations can never silently diverge.

Loading notes:

- The script is extensionless, so it is loaded via
  ``importlib.machinery.SourceFileLoader`` + ``importlib.util.spec_from_loader``
  (``spec_from_file_location`` returns ``None`` for an extensionless path).
- The script runs a ``cortex-log-invocation`` subprocess at module load
  (gated on ``shutil.which``); ``shutil.which`` is monkeypatched to return
  ``None`` *before* ``exec_module`` so importing the script does not shell out.

The parity target is the inline two-arg ``matches_any_glob(rel_path, globs)``
symbol the script vendors — NOT the single-arg ``_matches_scan_glob``, which
closes over the script's own ``SCAN_GLOBS`` and cannot accept the corpus's
varied glob sets.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import shutil
from pathlib import Path

import pytest

from cortex_command.lint._globs import matches_any_glob as shared_matches_any_glob

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "bin" / "cortex-check-events-registry"


# (row id, rel_path, glob, expected) — every one of the nine Edge Case shapes,
# including the single-* over-scan rejection, the directory-prefix
# discrimination, and the hidden-file case. Mirrors test_lint_globs.py so a
# divergence in either implementation is caught.
TRUTH_TABLE = [
    ("depth-1", "docs/agentic-layer.md", "docs/**/*.md", True),
    ("depth-2", "docs/internals/pipeline.md", "docs/**/*.md", True),
    ("depth-3", "skills/lifecycle/references/implement.md", "skills/**/*.md", True),
    ("star-overscan-reject", "cortex/backlog/sub/x.md", "cortex/backlog/*.md", False),
    (
        "deep-litprefix-in",
        "cortex_command/overnight/prompts/plan-synthesizer.md",
        "cortex_command/overnight/prompts/*.md",
        True,
    ),
    (
        "deep-litprefix-reject",
        "cortex_command/overnight/prompts/sub/x.md",
        "cortex_command/overnight/prompts/*.md",
        False,
    ),
    ("bare-star-depth1", "hooks/cortex-cleanup-session.sh", "hooks/**", True),
    ("bare-star-deeper", "hooks/sub/cortex-x.sh", "hooks/**", True),
    ("exact-literal-in", "justfile", "justfile", True),
    ("exact-literal-claude", "CLAUDE.md", "CLAUDE.md", True),
    ("exact-literal-reject", "sub/CLAUDE.md", "CLAUDE.md", False),
    ("dirprefix-star-in", "hooks/cortex-foo.sh", "hooks/cortex-*.sh", True),
    ("dirprefix-star-reject", "claude/hooks/cortex-x.sh", "hooks/cortex-*.sh", False),
    ("hidden-file-in", "tests/fixtures/.parity-exceptions.md", "tests/**/*.md", True),
]


@pytest.fixture(scope="module")
def events_registry_module():
    """Load the extensionless events-registry script as an importable module.

    Neutralizes the module-load ``cortex-log-invocation`` subprocess by
    forcing ``shutil.which`` to return ``None`` before ``exec_module``.
    """
    orig_which = shutil.which
    shutil.which = lambda *args, **kwargs: None  # noqa: E731 — test-local neutralizer
    try:
        loader = importlib.machinery.SourceFileLoader(
            "cortex_check_events_registry_inline", str(SCRIPT_PATH)
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        assert spec is not None, "spec_from_loader returned None for the script"
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
    finally:
        shutil.which = orig_which
    return module


def test_inline_exports_two_arg_matcher(events_registry_module) -> None:
    """The script vendors a callable two-arg ``matches_any_glob`` symbol."""
    assert callable(getattr(events_registry_module, "matches_any_glob", None)), (
        "bin/cortex-check-events-registry must export a two-arg matches_any_glob "
        "for the parity lock (Task 3 vendors it)."
    )


@pytest.mark.parametrize(
    "rel_path, glob, expected",
    [(r[1], r[2], r[3]) for r in TRUTH_TABLE],
    ids=[r[0] for r in TRUTH_TABLE],
)
def test_inline_matcher_parity(
    events_registry_module, rel_path: str, glob: str, expected: bool
) -> None:
    """Inline matcher == shared helper == spec's expected value, per truth-table row."""
    inline = events_registry_module.matches_any_glob(rel_path, (glob,))
    shared = shared_matches_any_glob(rel_path, (glob,))
    assert inline == shared, (
        f"inline ({inline}) and shared ({shared}) disagree for {rel_path!r} "
        f"vs {glob!r} — the vendored copy has drifted from _globs.py"
    )
    assert inline is expected
