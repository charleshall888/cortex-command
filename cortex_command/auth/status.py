"""Implementation of ``cortex auth status``.

Reports the resolved auth vector via
:func:`cortex_command.overnight.auth.ensure_sdk_auth`, the human-readable
source the vector resolved from, a remediation line when no vector
resolved, and a list of *shadowed* vectors (lower-precedence sources that
are configured but masked by the resolved one).

Output is verified to never contain ``sk-ant-`` substrings — the handler
only emits human-readable labels, never token / key material.

See ``cortex/lifecycle/restore-subscription-auth-for-autonomous-worktree/spec.md``
Requirement 8 and the Task 5 entry in ``plan.md`` for the contract.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys


# ---------------------------------------------------------------------------
# Vector / source labels
# ---------------------------------------------------------------------------
#
# The five-vector precedence chain enforced by
# :func:`cortex_command.overnight.auth.ensure_sdk_auth` is, highest first:
#
#     1. ANTHROPIC_AUTH_TOKEN env       (vector: auth_token)
#     2. ANTHROPIC_API_KEY env          (vector: env_preexisting)
#     3. apiKeyHelper from settings     (vector: api_key_helper)
#     4. CLAUDE_CODE_OAUTH_TOKEN env    (vector: env_preexisting)
#     5. ~/.claude/personal-oauth-token (vector: oauth_file)
#
# Note that step 2 and step 4 collapse to the same ``env_preexisting`` vector
# string — the status handler disambiguates by inspecting the env-var presence
# captured *before* ``ensure_sdk_auth`` was invoked (the call may write
# ``CLAUDE_CODE_OAUTH_TOKEN`` into ``os.environ`` for the ``oauth_file``
# branch, so post-call inspection would be misleading).


_OAUTH_FILE_PATH_LITERAL = "~/.claude/personal-oauth-token"


def _capture_env_state() -> dict[str, bool]:
    """Snapshot which auth-related env vars were set entering the handler."""

    return {
        "ANTHROPIC_AUTH_TOKEN": bool(os.environ.get("ANTHROPIC_AUTH_TOKEN")),
        "ANTHROPIC_API_KEY": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "CLAUDE_CODE_OAUTH_TOKEN": bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")),
    }


def _api_key_helper_configured() -> bool:
    """Return True if ``apiKeyHelper`` is configured in either settings file.

    Mirrors :func:`cortex_command.overnight.auth._read_api_key_helper`'s file
    list but is fault-tolerant: malformed JSON / unreadable files report
    *not configured* here so the status handler doesn't error out before
    ``ensure_sdk_auth`` has a chance to surface the same defect with its
    own (more informative) ``_HelperInternalError``.
    """

    home = pathlib.Path.home()
    for candidate in (
        home / ".claude" / "settings.json",
        home / ".claude" / "settings.local.json",
    ):
        if not candidate.exists():
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict) and data.get("apiKeyHelper"):
            return True
    return False


def _oauth_file_present() -> bool:
    """Return True if ``~/.claude/personal-oauth-token`` exists."""

    return (pathlib.Path.home() / ".claude" / "personal-oauth-token").exists()


def _source_label(vector: str, env_state: dict[str, bool]) -> str:
    """Map a resolved vector to its human-readable origin label."""

    if vector == "auth_token":
        return "ANTHROPIC_AUTH_TOKEN environment variable"
    if vector == "env_preexisting":
        # ``env_preexisting`` is shared between ANTHROPIC_API_KEY (step 2) and
        # CLAUDE_CODE_OAUTH_TOKEN (step 4). ANTHROPIC_API_KEY wins precedence
        # when both are set, so report it first.
        if env_state["ANTHROPIC_API_KEY"]:
            return "ANTHROPIC_API_KEY environment variable"
        return "CLAUDE_CODE_OAUTH_TOKEN environment variable"
    if vector == "api_key_helper":
        return "settings.json apiKeyHelper"
    if vector == "oauth_file":
        return _OAUTH_FILE_PATH_LITERAL
    if vector == "none":
        return "(none)"
    # Defensive: if a future ensure_sdk_auth introduces a new vector string,
    # surface it literally rather than misreport.
    return vector


# Precedence order (highest first) used to compute "lower-precedence than the
# resolved vector". Each entry is a (label, predicate) pair where the label is
# what gets printed in the ``shadowed: ...`` list and the predicate inspects
# ``env_state`` / disk to decide if that source is currently configured.
#
# ``env_preexisting`` resolves at *either* slot 2 (ANTHROPIC_API_KEY) or
# slot 4 (CLAUDE_CODE_OAUTH_TOKEN). For shadowing we treat the two as
# distinct precedence slots so a CLAUDE_CODE_OAUTH_TOKEN-resolved status
# can correctly report a present ``personal-oauth-token`` file as shadowed.


def _shadowed_vectors(
    resolved_vector: str,
    env_state: dict[str, bool],
    helper_configured: bool,
    oauth_file_present: bool,
) -> list[str]:
    """Return the list of lower-precedence sources that are present but masked."""

    # Slots, highest precedence first. Each tuple: (slot_id, label, present).
    # ``slot_id`` is just used to compare positions; labels are what we print.
    slots: list[tuple[int, str, bool]] = [
        (1, "ANTHROPIC_AUTH_TOKEN environment variable", env_state["ANTHROPIC_AUTH_TOKEN"]),
        (2, "ANTHROPIC_API_KEY environment variable", env_state["ANTHROPIC_API_KEY"]),
        (3, "settings.json apiKeyHelper", helper_configured),
        (4, "CLAUDE_CODE_OAUTH_TOKEN environment variable", env_state["CLAUDE_CODE_OAUTH_TOKEN"]),
        (5, "personal-oauth-token file", oauth_file_present),
    ]

    # Determine the slot the resolved vector occupies.
    if resolved_vector == "auth_token":
        resolved_slot = 1
    elif resolved_vector == "env_preexisting":
        # If both ANTHROPIC_API_KEY and CLAUDE_CODE_OAUTH_TOKEN are set, the
        # higher-precedence one (ANTHROPIC_API_KEY at slot 2) wins.
        resolved_slot = 2 if env_state["ANTHROPIC_API_KEY"] else 4
    elif resolved_vector == "api_key_helper":
        resolved_slot = 3
    elif resolved_vector == "oauth_file":
        resolved_slot = 5
    else:
        # ``none`` (or unknown): nothing resolved, so nothing is "shadowed by"
        # a higher-precedence pick. Return empty.
        return []

    return [label for slot_id, label, present in slots if slot_id > resolved_slot and present]


def run(_args: argparse.Namespace) -> int:
    """Entry point for ``cortex auth status``."""

    # Lazy import: keeps the cortex_command.auth package import-time cost low
    # and matches the convention used by the bootstrap post-write shadowing
    # check in ``cortex_command/auth/bootstrap.py``.
    from cortex_command.overnight.auth import ensure_sdk_auth

    # Snapshot env state BEFORE ``ensure_sdk_auth`` runs — that call may write
    # CLAUDE_CODE_OAUTH_TOKEN / ANTHROPIC_API_KEY into os.environ as part of
    # resolving the oauth_file / api_key_helper branches, which would
    # otherwise contaminate downstream shadowing detection.
    env_state = _capture_env_state()
    helper_configured = _api_key_helper_configured()
    oauth_file_present = _oauth_file_present()

    # ``ensure_sdk_auth`` raises ``_HelperInternalError`` on malformed
    # apiKeyHelper / settings.json — propagate so the CLI exits non-zero,
    # mirroring the resolver's own error-surface contract.
    info = ensure_sdk_auth(event_log_path=None)
    vector = info["vector"]

    print(f"vector: {vector}")
    print(f"source: {_source_label(vector, env_state)}")

    if vector == "none":
        print(
            "remediation: run 'cortex auth bootstrap' to mint a "
            "subscription OAuth token."
        )

    shadowed = _shadowed_vectors(
        vector,
        env_state,
        helper_configured,
        oauth_file_present,
    )
    if shadowed:
        print(f"shadowed: {', '.join(shadowed)}")
        print(
            "hint: unset / remove the listed source(s) to enable the "
            "lower-precedence vector."
        )

    return 0
