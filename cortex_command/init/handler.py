"""Argparse entry point for ``cortex init`` — orchestrates ADR-3 ordering.

The :func:`main` function is wired into ``cli.py`` by Task 10. It resolves
the target repo root via ``git rev-parse --show-toplevel`` (R2), refuses
submodules via ``git rev-parse --show-superproject-working-tree`` (R3),
runs the pre-flight gates in the ADR-3 sequence, and dispatches to
:mod:`cortex_command.init.scaffold` and
:mod:`cortex_command.init.settings_merge` in the mandated order:

    1. git-repo + submodule gates (R2, R3) — skipped for ``--unregister``.
    2. symlink-safety gate (R13) — returns the canonical sessions path
       that is threaded into the registration step (closes TOCTOU).
    3. malformed-settings pre-flight validation (R14) via
       :func:`settings_merge.validate_settings`.
    4. marker-present / content-aware decline gates (R6, R19).
    5. scaffold writes + backup (``--force``) / drift (``--update``).
    6. ``ensure_gitignore``.
    7. ``settings_merge.register`` (last — if it fails, repo is scaffolded
       and ``cortex init --update`` recovers idempotently).

Exit codes:
    0 -- success.
    2 -- user-correctable gate failure (not-a-repo, submodule, clobber,
         malformed settings, symlink escape). Covers R2, R3, R6, R13,
         R14, R19. Translated from :class:`ScaffoldError` and
         :class:`SettingsMergeError` at the top level of :func:`main`.
    1 -- unexpected runtime failure (disk full, permission error at write
         time). Any other exception propagates here.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from cortex_command.init import scaffold, settings_merge
from cortex_command.init.scaffold import ScaffoldError
from cortex_command.init.settings_merge import SettingsMergeError


def _resolve_repo_root(path_arg: str | None) -> Path:
    """Resolve the target repo root via ``git rev-parse --show-toplevel``.

    Mirrors ``cortex_command/pipeline/worktree.py:34-42`` but uses
    ``check=False`` so the handler can translate a non-zero returncode
    into a user-facing stderr message + exit 2 (R2) rather than letting
    ``CalledProcessError`` propagate as a crash.

    Raises:
        ScaffoldError: when git reports not-a-repo (non-zero returncode).
            The R3 submodule gate also raises ``ScaffoldError`` for a
            consistent translation path in :func:`main`.
    """
    cwd = path_arg or os.getcwd()

    toplevel = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if toplevel.returncode != 0:
        raise ScaffoldError("`cortex init`: not inside a git repository.")

    superproject = subprocess.run(
        ["git", "rev-parse", "--show-superproject-working-tree"],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    # Non-empty stdout signals submodule context. We only check stdout —
    # a non-zero returncode here is rare (this flag is available since
    # git 2.13); treat it the same as "not a submodule" to avoid
    # false-refusing on exotic git builds.
    if superproject.returncode == 0 and superproject.stdout.strip():
        raise ScaffoldError(
            "`cortex init`: cortex init should run at the top-level repo, "
            "not inside a submodule."
        )

    # Canonicalize ONCE at the handler level so every subsequent step
    # operates on the same resolved path. See plan.md Task 9 step 1 —
    # this closes the TOCTOU gap between the pre-flight symlink-safety
    # resolve and the registration re-resolve.
    return Path(toplevel.stdout.strip()).resolve()


def _emit_drift_report(drifted: list[Path]) -> None:
    """Emit R9's stderr drift report: bulleted paths + ``--force`` hint.

    Format per research.md §D8:

        N templates differ from shipped versions:
          - path/relative/to/repo
          - ...

        Overwrite all with shipped: cortex init --force
    """
    count = len(drifted)
    noun = "template" if count == 1 else "templates"
    verb = "differs" if count == 1 else "differ"
    print(f"{count} {noun} {verb} from shipped versions:", file=sys.stderr)
    for rel in drifted:
        print(f"  - {rel}", file=sys.stderr)
    print("", file=sys.stderr)
    print("Overwrite all with shipped: cortex init --force", file=sys.stderr)


def _run(args: argparse.Namespace) -> int:
    """Inner handler body — raises on gate failures; caller translates."""
    home: Path | None = None  # Settings-merge functions default to Path.home().

    # Step 0: --unregister early-branch (R15). --unregister is a settings-
    # cleanup verb, not a repo operation, so it skips R2/R3 so that entries
    # for already-deleted repos can be cleaned up by explicit --path. It
    # also skips check_symlink_safety (no scaffolding to guard; path may
    # no longer exist).
    if args.unregister:
        resolved_path = Path(args.path or os.getcwd()).resolve()
        cortex_target_path = str(resolved_path / "cortex") + "/"
        # R14 pre-flight still fires so a malformed settings file surfaces
        # before we try to mutate it.
        settings_merge.validate_settings(home)
        # Remove the umbrella cortex/ entry. The exact-string equality filter
        # is a no-op when the entry is absent (idempotent), so a repo that
        # was never registered under cortex/ safely no-ops.
        settings_merge.unregister(resolved_path, cortex_target_path, home=home)
        return 0

    # Step 1: git-repo + submodule gates (R2, R3). Resolution is done
    # here exactly once; the resolved path threads through every later
    # step so no downstream helper calls resolve() independently.
    repo_root = _resolve_repo_root(args.path)

    # Step 2: symlink-safety gate (R13). Still runs to validate that the
    # lifecycle/ path does not escape the repo via a symlink; the return
    # value is no longer threaded into register() since the umbrella cortex/
    # grant supersedes the narrow lifecycle/ path.
    scaffold.check_symlink_safety(repo_root)
    # Derive the umbrella cortex/ target. A single broader grant covers
    # cortex/lifecycle/sessions/ and all other cortex-managed state,
    # closing the same TOCTOU window as the prior dual-narrow grants.
    cortex_target = str(repo_root / "cortex") + "/"

    # Step 3: malformed-settings pre-flight (R14) — no mutation.
    settings_merge.validate_settings(home)

    # Steps 4–5: decline gates + scaffold dispatch.
    marker_present = (repo_root / ".cortex-init").exists()

    if marker_present:
        if args.update:
            # Additive scaffold (no overwrite) + marker refresh + drift report.
            scaffold.scaffold(repo_root, overwrite=False, backup_dir=None)
            scaffold.write_marker(repo_root, refresh=True)
            drifted = scaffold.drift_files(repo_root)
            if drifted:
                _emit_drift_report(drifted)
        elif args.force:
            # --force on a marker-present repo: backup + overwrite + refresh.
            # scaffold() handles the backup internally when backup_dir=None
            # and overwrite=True.
            scaffold.scaffold(repo_root, overwrite=True, backup_dir=None)
            scaffold.write_marker(repo_root, refresh=True)
        else:
            # R6 decline.
            scaffold.check_marker_decline(repo_root)
            # Unreachable — check_marker_decline raises when marker exists.
    else:
        # No marker.
        if args.update:
            # Additive scaffold + marker write (first time).
            scaffold.scaffold(repo_root, overwrite=False, backup_dir=None)
            scaffold.write_marker(repo_root, refresh=False)
        elif args.force:
            # R19 does NOT fire on --force: user explicitly asked for overwrite.
            scaffold.scaffold(repo_root, overwrite=True, backup_dir=None)
            scaffold.write_marker(repo_root, refresh=False)
        else:
            # Default invocation: R19 content-aware decline, then additive scaffold.
            scaffold.check_content_decline(repo_root)
            scaffold.scaffold(repo_root, overwrite=False, backup_dir=None)
            scaffold.write_marker(repo_root, refresh=False)

    # Step 6: idempotent .gitignore append (R4). Always runs — scaffold
    # branches above may or may not have touched .gitignore.
    scaffold.ensure_gitignore(repo_root)

    # Step 7: register allowWrite entry last (ADR-3). A single umbrella
    # cortex/ grant covers all cortex-managed state under the repo root;
    # no TOCTOU re-resolve is needed because repo_root was resolved once
    # at step 1.
    settings_merge.register(repo_root, cortex_target, home=home)

    return 0


def main(args: argparse.Namespace) -> int:
    """Entry point called from ``cli.py`` (Task 10 replaces the stub).

    Expected ``args`` attributes (attached to the subparser in Task 10):
        path       -- optional target directory (defaults to ``os.getcwd()``).
        update     -- bool, additive scaffold + drift report.
        force      -- bool, backup + overwrite scaffold.
        unregister -- bool, remove allowWrite entry and return.

    ``--update``, ``--force``, and ``--unregister`` are mutually exclusive
    at argparse time (Task 10); this handler does not re-check.

    Returns:
        Exit code -- 0 success, 2 user-correctable gate failure, 1 on
        unexpected runtime failure.
    """
    try:
        return _run(args)
    except (ScaffoldError, SettingsMergeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
