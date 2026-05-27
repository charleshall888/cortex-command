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
    6b. ``ensure_claude_md_authorization`` — splice the cortex-managed
        ``EnterWorktree`` authorization fence into consumer ``CLAUDE.md``
        (R5).
    7. ``settings_merge.register`` (last — if it fails, repo is scaffolded
       and ``cortex init --update`` recovers idempotently).

Exit codes:
    0 -- success. For ``--verify-worktree-auth``, also signals the
         cortex-managed CLAUDE.md fence is present at the current
         canonical version (R20).
    2 -- user-correctable gate failure (not-a-repo, submodule, clobber,
         malformed settings, symlink escape). Covers R2, R3, R6, R13,
         R14, R19. Translated from :class:`ScaffoldError` and
         :class:`SettingsMergeError` at the top level of :func:`main`.
         Also returned by ``--verify-worktree-auth`` when the fence is
         present but stale (in-fence ``version`` strictly below the
         canonical version).
    1 -- unexpected runtime failure (disk full, permission error at write
         time). Any other exception propagates here. Also returned by
         ``--verify-worktree-auth`` when the fence is absent (CLAUDE.md
         missing or no opening sigil found).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from cortex_command.init import scaffold, settings_merge
from cortex_command.init.install_state import (
    INSTALL_MARKER_STALE_SECONDS,
    install_in_progress_marker_path,
)
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


def _run_ensure(args: argparse.Namespace) -> int:
    """Inner body for ``--ensure`` — hash-compare dispatch with R19 narrow-bypass.

    Called by :func:`_run` when ``args.ensure`` is True.  Implements the
    ordered gate sequence described in spec R4–R8.

    Raises:
        ScaffoldError: On worktree-attached refusal, install-in-progress
            timeout, marker provenance failure, or R19/R5 foreign-content
            decline.  Caller (:func:`main`) translates to exit 2.
    """
    home: Path | None = None  # Settings-merge functions default to Path.home().

    # (a) CORTEX_AUTO_ENSURE=0 opt-out (R7). First check; writes nothing.
    if os.environ.get("CORTEX_AUTO_ENSURE") == "0":
        return 0

    # (b) Worktree-attached refusal (R11 CLI-surface mirror).
    # Mirrors the probe in Task 7's skill-helper module — duplication is
    # intentional structural defense-in-depth (``cortex init --ensure`` is
    # reachable from the bare CLI surface before Task 8 wires the helper).
    _check_not_attached_worktree()

    # (c) Install-in-progress lock-check (R6).
    _wait_for_install_complete()

    # R2/R3: resolve the repo root (same as the standard init path).
    repo_root = _resolve_repo_root(args.path)

    # R13: symlink-safety gate.
    scaffold.check_symlink_safety(repo_root)
    cortex_target = str(repo_root / "cortex") + "/"

    # R14: malformed-settings pre-flight.
    settings_merge.validate_settings(home)

    # (d) Compute the installed hash and read marker provenance (R1, R8).
    installed_hash = scaffold._compute_init_artifacts_hash()
    marker_hash, cortex_version = scaffold._read_marker_provenance(repo_root)
    # _read_marker_provenance raises ScaffoldError on JSON parse failure or
    # foreign-artifact discrimination (both translate to exit 2 via main()).

    cortex_dir = repo_root / "cortex"

    # (e) Five-case dispatch.
    if marker_hash is not None:
        # Case (i): marker-present + hash-matches → no-op.
        if marker_hash == installed_hash:
            return 0

        # Case (ii): marker-present + hash-mismatch → refresh via --update path.
        # Marker presence establishes prior cortex authorship; R5 is not relevant.
        scaffold.scaffold(repo_root, overwrite=False, backup_dir=None)
        scaffold.write_marker(repo_root, refresh=True)
        drifted = scaffold.drift_files(repo_root)
        if drifted:
            _emit_drift_report(drifted)

    elif cortex_version is not None:
        # Case (v): R8 recovery — marker-present + missing init_artifacts_hash +
        # cortex_version-present-and-parseable. The cortex_version discrimination
        # at _read_marker_provenance() establishes prior cortex authorship, so
        # this branch dispatches identically to case (ii) — additive scaffold +
        # write_marker(refresh=True) — without re-firing R5's content-decline.
        # R5 is scoped to marker-absent + cortex/-has-content (spec.md:30); a
        # present marker, even one lacking init_artifacts_hash, is outside its
        # boundary. The stderr warning surfaces the one-time migration to the
        # user (spec.md:66 "one-time storm at Phase 3 release ... accepted
        # cost").
        print(
            "cortex init --ensure: .cortex-init missing init_artifacts_hash "
            "field; refreshing",
            file=sys.stderr,
        )
        scaffold.scaffold(repo_root, overwrite=False, backup_dir=None)
        scaffold.write_marker(repo_root, refresh=True)
        drifted = scaffold.drift_files(repo_root)
        if drifted:
            _emit_drift_report(drifted)

    else:
        # marker_hash is None and cortex_version is None → marker absent.
        # (Both fields are None only when _read_marker_provenance returned
        # (None, None), which means the marker file does not exist.)

        # Case (iii): marker-absent + cortex/ absent or empty → bootstrap.
        # "empty" means no child entries at all.
        cortex_absent_or_empty = (
            not cortex_dir.exists() or not any(cortex_dir.iterdir())
        )
        if cortex_absent_or_empty:
            # Skip check_content_decline: R19 would no-op anyway on an empty dir.
            scaffold.scaffold(repo_root, overwrite=False, backup_dir=None)
            scaffold.write_marker(repo_root, refresh=False)
        else:
            # Case (iv): marker-absent + cortex/ has content → R5 boundary.
            # Fire R19 to preserve the foreign-repo / wrong-window protection.
            scaffold.check_content_decline(repo_root)
            # Unreachable — check_content_decline raises when content found.

    # Post-dispatch: idempotent gitignore, CLAUDE.md fence, and settings
    # registration (same ADR-3 ordering as the standard init path).
    scaffold.ensure_gitignore(repo_root)
    scaffold.ensure_claude_md_authorization(repo_root)
    settings_merge.register(repo_root, cortex_target, home=home)

    # Migration: expunge stale "cortex-worktrees"-prefixed entries (mirrors
    # the --update step in the standard path; --ensure routes through additive
    # scaffold on drift so the migration applies here as well).
    settings_merge.unregister_matching_in_place("cortex-worktrees", home=home)

    return 0


def _check_not_attached_worktree() -> None:
    """Refuse if the CWD is inside an attached ``git worktree add`` worktree.

    Mirrors the probe in ``cortex_command/lifecycle/init_ensure.py`` (Task 7).
    Duplication is intentional structural defense-in-depth per spec R11: the
    CLI surface is reachable before the skill-helper is wired (Task 8), so both
    layers independently enforce the worktree guard.

    Raises:
        ScaffoldError: when CWD is inside an attached worktree (not the primary
            worktree).  The message names the F9 data-loss diagnostic.
    """
    common_dir_proc = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        check=False,
        capture_output=True,
        text=True,
    )
    if common_dir_proc.returncode != 0:
        # Not inside a git repo at all; _resolve_repo_root will surface R2.
        return

    git_dir_proc = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        check=False,
        capture_output=True,
        text=True,
    )
    if git_dir_proc.returncode != 0:
        return

    common_dir = Path(common_dir_proc.stdout.strip()).resolve()
    git_dir = Path(git_dir_proc.stdout.strip()).resolve()

    # In the primary worktree, ``--git-common-dir`` == ``--git-dir`` (both
    # resolve to ``<repo>/.git``).  In an attached worktree, ``--git-dir``
    # resolves to ``<repo>/.git/worktrees/<name>`` while ``--git-common-dir``
    # still resolves to ``<repo>/.git``.
    if common_dir != git_dir:
        # Resolve the worktree root for the diagnostic.
        worktree_root = git_dir.parent.parent.parent  # .git/worktrees/<name>/../../../
        primary_root = common_dir.parent  # .git/..
        raise ScaffoldError(
            f"`cortex init --ensure`: invoked inside a git worktree "
            f"({worktree_root}); run from the primary worktree ({primary_root}) "
            "to bootstrap or refresh cortex/. Scaffolding inside an attached "
            "worktree risks data loss (F9): cortex/ content written here will "
            "be silently destroyed when the worktree is removed."
        )


def _wait_for_install_complete() -> None:
    """Poll until the install-in-progress marker is absent or stale (R6).

    Reads ``install_in_progress_marker_path()`` and checks:
        - If absent or stale (mtime > ``INSTALL_MARKER_STALE_SECONDS`` ago):
          return immediately.
        - If fresh: poll at 50 ms intervals for up to 5 seconds (100 iterations).
          On still-fresh after the budget: raise ``ScaffoldError`` with the R6
          diagnostic (translated to exit 2 by :func:`main`).

    Raises:
        ScaffoldError: when a fresh install-in-progress marker persists for the
            full 5-second polling budget.
    """
    marker = install_in_progress_marker_path()
    max_iterations = 100
    sleep_seconds = 0.05  # 50 ms

    for _ in range(max_iterations):
        if not marker.exists():
            return
        try:
            mtime = marker.stat().st_mtime
        except OSError:
            # File disappeared between exists() and stat() — treat as absent.
            return
        age = time.time() - mtime
        if age > INSTALL_MARKER_STALE_SECONDS:
            # Stale marker (catastrophic-failure remnant) — proceed.
            return
        time.sleep(sleep_seconds)

    # Still fresh after the full budget.
    try:
        mtime_ts = marker.stat().st_mtime
    except OSError:
        return  # Disappeared — safe to proceed.
    raise ScaffoldError(
        f"cortex init --ensure: Layer-3 install in progress "
        f"(marker mtime {mtime_ts}); rerun after install completes."
    )


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

    # Step 0b: --revoke-worktree-auth early-branch (R7). Revocation is a
    # CLAUDE.md-rollback verb; it skips scaffold/settings entirely and only
    # touches the cortex-managed fence. The git-repo gate (R2) still runs
    # because the live-session pre-condition scans
    # ``cortex/lifecycle/sessions/`` under ``repo_root`` — we need a
    # resolved repo path. Submodule gate (R3) runs in
    # ``_resolve_repo_root`` as a side effect.
    if getattr(args, "revoke_worktree_auth", False):
        repo_root = _resolve_repo_root(args.path)

        claude_md_path = repo_root / "CLAUDE.md"
        # No fence on disk → no-op success (idempotent absent → 0).
        if claude_md_path.exists():
            content = claude_md_path.read_text(encoding="utf-8")
            fence_present = scaffold._find_claude_md_auth_fence(content) is not None
        else:
            fence_present = False
        if not fence_present:
            return 0

        # Fence present: check the live-session pre-condition unless
        # --force bypasses it. Live = a ``*.interactive.pid`` file whose
        # contents map to a live PID per the canonical liveness probe.
        if not getattr(args, "force", False):
            live = scaffold.live_interactive_sessions(repo_root)
            if live:
                print(
                    "`cortex init --revoke-worktree-auth`: refusing — "
                    "live interactive session(s) depend on the "
                    "EnterWorktree authorization fence:",
                    file=sys.stderr,
                )
                for pid_file in live:
                    print(f"  - {pid_file}", file=sys.stderr)
                print(
                    "",
                    file=sys.stderr,
                )
                print(
                    "Re-run with --force to revoke anyway "
                    "(the live session's next EnterWorktree call will "
                    "fail closed).",
                    file=sys.stderr,
                )
                return 2

        scaffold.revoke_claude_md_authorization(repo_root)
        return 0

    # Step 0c: --verify-worktree-auth early-branch (R20). Verification is a
    # read-only probe of the cortex-managed CLAUDE.md fence; it skips
    # scaffold/settings entirely. The git-repo gate (R2) still runs so
    # ``CLAUDE.md`` is resolved relative to a real repo root rather than
    # an arbitrary CWD. Exit codes per R20: 0 fence present at canonical
    # version, 1 fence absent (CLAUDE.md missing or no sigil), 2 fence
    # present but stale (in-fence ``version=N`` strictly below canonical).
    # Uses the same sigil parser as ensure/revoke so the three branches
    # share one source of truth.
    if getattr(args, "verify_worktree_auth", False):
        repo_root = _resolve_repo_root(args.path)

        claude_md_path = repo_root / "CLAUDE.md"
        if not claude_md_path.exists():
            return 1

        content = claude_md_path.read_text(encoding="utf-8")
        located = scaffold._find_claude_md_auth_fence(content)
        if located is None:
            return 1

        _start, _end, version = located
        if version < scaffold._CLAUDE_MD_AUTH_VERSION:
            return 2
        # Equal or future-version fences both count as "present at the current
        # canonical version" from the probe's perspective: the lifecycle
        # skill's §1a path only needs to know the gate is satisfied, and a
        # future-version fence written by a newer cortex-command does satisfy
        # it (the newer body is a superset commitment to the same surface).
        return 0

    # Step 0d: --ensure early-branch (R4–R8). Hash-compare dispatch for
    # automated drift recovery. Ordered gate sequence:
    # (a) CORTEX_AUTO_ENSURE=0 opt-out → silent no-op (R7).
    # (b) Worktree-attached refusal (R11 CLI-surface mirror).
    # (c) Install-in-progress lock-check (R6).
    # (d) Hash computation + marker-provenance read (R1, R8).
    # (e) Five-case dispatch (R4 + R8 recovery case).
    if getattr(args, "ensure", False):
        return _run_ensure(args)

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
    marker_present = (repo_root / "cortex" / ".cortex-init").exists()

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

    # Step 6b: idempotent CLAUDE.md authorization-fence splice (R5). Writes
    # the cortex-managed ``EnterWorktree`` authorization clause to consumer
    # CLAUDE.md when absent or when the in-fence version is stale; no-op when
    # the fence is already at the canonical version. Runs after ensure_gitignore
    # so any new CLAUDE.md write does not race the gitignore append, and before
    # settings_merge.register so a settings-merge failure still leaves a
    # well-formed CLAUDE.md the lifecycle skill can read on the next run.
    scaffold.ensure_claude_md_authorization(repo_root)

    # Step 7: register allowWrite entry last (ADR-3). A single umbrella
    # cortex/ grant covers all cortex-managed state under the repo root;
    # no TOCTOU re-resolve is needed because repo_root was resolved once
    # at step 1.
    settings_merge.register(repo_root, cortex_target, home=home)

    # Step 7b (migration): expunge stale "cortex-worktrees"-prefixed entries
    # from a prior version of cortex that registered worktree-base paths in
    # user settings. Same-repo worktrees now live at <repo>/.claude/worktrees/
    # under the project's trust scope — no per-shell registration needed.
    # Only fires on --update so a fresh init never touches a clean settings
    # file.
    if args.update:
        settings_merge.unregister_matching_in_place("cortex-worktrees", home=home)

    return 0


def main(args: argparse.Namespace) -> int:
    """Entry point called from ``cli.py`` (Task 10 replaces the stub).

    Expected ``args`` attributes (attached to the subparser in Task 10):
        path                  -- optional target directory (defaults to ``os.getcwd()``).
        update                -- bool, additive scaffold + drift report.
        force                 -- bool modifier: with the default scaffold path,
                                 enables backup + overwrite; with
                                 ``--revoke-worktree-auth``, bypasses the
                                 live-session pre-condition.
        unregister            -- bool, remove allowWrite entry and return.
        revoke_worktree_auth  -- bool, remove the cortex-managed CLAUDE.md
                                 authorization fence and return.
        verify_worktree_auth  -- bool, probe the cortex-managed CLAUDE.md
                                 authorization fence (read-only) and exit
                                 with 0/1/2 per R20.
        ensure                -- bool, hash-compare dispatch: no-op when
                                 hash matches; refresh when mismatch;
                                 bootstrap when cortex/ absent/empty;
                                 decline when cortex/ has content but no
                                 marker (R4–R8). Honors
                                 ``CORTEX_AUTO_ENSURE=0`` opt-out.

    ``--update``, ``--unregister``, ``--revoke-worktree-auth``,
    ``--verify-worktree-auth``, and ``--ensure`` are mutually exclusive at
    argparse time; ``--force`` is a modifier and may combine with the
    default invocation or with ``--revoke-worktree-auth``. This handler
    does not re-check the mutex.

    Returns:
        Exit code -- 0 success (or fence present at canonical version for
        ``--verify-worktree-auth``), 2 user-correctable gate failure (incl.
        R7's live-session refusal, R20's stale fence), 1 on unexpected
        runtime failure (or R20's absent fence).
    """
    try:
        return _run(args)
    except (ScaffoldError, SettingsMergeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
