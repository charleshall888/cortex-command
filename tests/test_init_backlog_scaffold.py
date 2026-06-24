"""Contract test: scaffolded ``lifecycle.config.md`` carries a resolvable ``backlog:`` block.

Spec #317 R3 (config-driven-backlog-backend-resolver-local) mandates that the
``cortex init`` scaffold declares the active backlog backend, defaulting to
``cortex-backlog`` so a fresh repo stays byte-identical to today's local
behavior.

The acceptance lens is deliberately end-to-end through the *independent*
resolver from Task 1 (R1): scaffold a repo, then read it back through
``resolve_backlog_backend`` (imported from ``cortex_command.lifecycle_config``).
This proves the ``backlog:`` block is nested at the exact path the resolver
descends (``backlog.backend``), not merely that the string ``backlog:`` appears
in the template. The resolver is a separate module, so this is not a
self-sealing check.
"""

from __future__ import annotations

from pathlib import Path

from cortex_command.init.scaffold import scaffold
from cortex_command.lifecycle_config import resolve_backlog_backend


def test_scaffolded_template_resolves_to_cortex_backlog(tmp_path: Path) -> None:
    """A freshly scaffolded repo resolves to the default ``cortex-backlog`` backend.

    ``scaffold`` materializes ``cortex/lifecycle.config.md`` under ``tmp_path``;
    ``resolve_backlog_backend`` then descends the nested ``backlog:`` mapping to
    read ``backend``. A return of ``"cortex-backlog"`` confirms the scaffolded
    block is both present and correctly nested at the resolver's descent path.
    """
    written = scaffold(tmp_path, overwrite=False, backup_dir=None)

    config_path = tmp_path / "cortex" / "lifecycle.config.md"
    assert config_path in written, (
        "scaffold did not write cortex/lifecycle.config.md; "
        f"wrote: {[str(p) for p in written]}"
    )

    assert resolve_backlog_backend(tmp_path) == "cortex-backlog"
