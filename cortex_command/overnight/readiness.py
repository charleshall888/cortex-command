"""Dispatch readiness fuse for the daytime pipeline (Phase 4, R18).

Fuses the auth resolution+probe (R3) and worktree-writability probe (R8)
into a single ``verify_dispatch_readiness()`` call placed in ``run_daytime``
Phase A immediately after the existing CWD check.

Entry-point importability is intentionally NOT checked here.

Rationale: a ``find_spec("claude_agent_sdk")`` check is informationally
vacuous within ``run_daytime`` — the surrounding ``daytime_pipeline`` module
is already imported by the time the fuse runs, so the check cannot distinguish
between "importable" and "already imported". A ``shutil.which("cortex-daytime-
pipeline")`` check tests a future invocation's launcher health, not the current
dispatch's correctness — failing the dispatch on ``which=None`` would abort a
successfully-launched run while passing the broken-launch case. The F3 failure
mode (``claude_agent_sdk`` unimportable, console script missing) surfaces at
process start via Python's normal import-error path or via the launch-command's
``command not found``, both of which appear in ``daytime.log`` before the fuse
runs. The fuse owns the auth and worktree concerns; launch-time concerns belong
in the launching skill (see R10 §1a Step 3).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from cortex_command.overnight.auth import resolve_and_probe
from cortex_command.pipeline.worktree import probe_worktree_writable, resolve_worktree_root


@dataclass
class ReadinessResult:
    """Result of the combined dispatch readiness fuse.

    Fields:
        ok:               True if both checks passed and the dispatch should
                          continue.  False signals startup failure.
        failed_check:     Which check failed: ``"auth"`` or ``"worktree"``.
                          ``None`` when ``ok`` is ``True``.
        cause:            Human-readable description of the failure cause, or
                          ``None`` on success.
        remediation_hint: Actionable remediation text for the operator, or
                          ``None`` on success.
        auth_probe_result: The ``AuthProbeResult`` from ``resolve_and_probe``.
                           Always set (used by the caller to emit Phase B events).
    """

    ok: bool
    failed_check: Optional[Literal["auth", "worktree"]]
    cause: Optional[str]
    remediation_hint: Optional[str]
    auth_probe_result: object  # AuthProbeResult; typed as object to avoid circular imports


def verify_dispatch_readiness(
    feature: str,
    session_id: Optional[str] = None,
) -> ReadinessResult:
    """Fuse the auth and worktree readiness probes.

    Runs in order:
        (a) ``resolve_and_probe(feature, event_log_path=None)`` — resolves the
            SDK auth vector and applies the R3 Keychain probe policy.  On
            failure (``probe_result.ok is False``), returns immediately with
            ``failed_check="auth"``.
        (b) ``probe_worktree_writable(resolve_worktree_root(feature, session_id))``
            — verifies the resolved worktree root is filesystem-writable and
            accepts ``git worktree add``.  On failure, returns with
            ``failed_check="worktree"``.

    Returns a ``ReadinessResult`` with ``ok=True`` and both probe results
    available when all checks pass, or ``ok=False`` with the first failed
    check named in ``failed_check`` and a ``cause`` + ``remediation_hint``
    for operator diagnostics.

    Args:
        feature:    Feature slug (used for auth event labelling and for
                    ``resolve_worktree_root``).
        session_id: Overnight session ID passed through to
                    ``resolve_worktree_root`` for cross-repo dispatch.
                    ``None`` for same-repo same-session daytime dispatches.
    """
    # ------------------------------------------------------------------
    # Check (a): auth resolution + Keychain probe (R3 policy)
    # ------------------------------------------------------------------
    auth_result = resolve_and_probe(feature=feature, event_log_path=None)

    if not auth_result.ok:
        return ReadinessResult(
            ok=False,
            failed_check="auth",
            cause=(
                f"auth probe failed: vector={auth_result.vector}, "
                f"keychain={auth_result.keychain} — "
                "Keychain entry absent; no auth vector available"
            ),
            remediation_hint=(
                "Ensure an SDK auth credential is available: set ANTHROPIC_API_KEY, "
                "ANTHROPIC_AUTH_TOKEN, or authenticate via 'claude auth login' so a "
                "Keychain entry is present under the service name 'Claude Code-credentials'."
            ),
            auth_probe_result=auth_result,
        )

    # ------------------------------------------------------------------
    # Check (b): worktree-root writability probe (R8)
    # ------------------------------------------------------------------
    worktree_root = resolve_worktree_root(feature, session_id)
    wt_probe = probe_worktree_writable(worktree_root)

    if not wt_probe.ok:
        return ReadinessResult(
            ok=False,
            failed_check="worktree",
            cause=wt_probe.cause,
            remediation_hint=wt_probe.remediation_hint,
            auth_probe_result=auth_result,
        )

    return ReadinessResult(
        ok=True,
        failed_check=None,
        cause=None,
        remediation_hint=None,
        auth_probe_result=auth_result,
    )
