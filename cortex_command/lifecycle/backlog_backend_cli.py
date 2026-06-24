"""cortex-read-backlog-backend — emit the active backlog backend for a repo.

Graceful console-script reader (spec R2) mirroring
``cortex_command.lifecycle.branch_mode_cli``. Consumers shell to this
command argless to learn the active backend; it ALWAYS resolves to
``cortex-backlog`` for any degenerate input (fail-open, interactive) so
the interactive fail-safe lives here and no consumer carries fallback
prose.

Usage:
    cortex-read-backlog-backend [repo_root]

Resolves ``repo_root`` from an optional positional (default ``.``) and
honors ``CORTEX_COMMAND_ROOT`` when set. Calls
``cortex_command.lifecycle_config.resolve_backlog_backend`` — which never
returns ``None`` and never raises — then prints the resolved backend with
a trailing newline and exits 0. An unconfigured repo prints
``cortex-backlog``.

Distinct from the overnight guard, which resolves in-process and fails
*closed* (spec R5/R11): the two readers must NOT be DRY-merged.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
from typing import List, Optional

from cortex_command.backlog import _telemetry
from cortex_command.lifecycle_config import resolve_backlog_backend


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-read-backlog-backend",
        description=(
            "Emit the active backlog backend for a repo. Calls "
            "cortex_command.lifecycle_config.resolve_backlog_backend and "
            "prints the result, defaulting to 'cortex-backlog' for any "
            "unconfigured or degenerate repo (graceful, exit 0)."
        ),
    )
    parser.add_argument(
        "repo_root",
        nargs="?",
        default=".",
        help="Repo root to inspect (default '.'). $CORTEX_COMMAND_ROOT wins.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _telemetry.log_invocation("cortex-read-backlog-backend")
    parser = _build_parser()
    args = parser.parse_args(argv)
    root = pathlib.Path(os.environ.get("CORTEX_COMMAND_ROOT") or args.repo_root)
    backend = resolve_backlog_backend(root)
    sys.stdout.write(backend + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
