"""Shared auth-resolution helper for the overnight runner and daytime pipeline.

Stdlib-only module invokable both pre-venv (via ``python3 -m claude.overnight.auth
--shell`` from ``runner.sh``) and in-process (via ``ensure_sdk_auth()`` from
``daytime_pipeline.py``). Resolves the SDK auth vector in the priority order:

    1. Pre-existing ``ANTHROPIC_API_KEY`` env var  (vector: env_preexisting)
    2. ``apiKeyHelper`` from ``~/.claude/settings.json`` or
       ``~/.claude/settings.local.json``                   (vector: api_key_helper)
    3. ``~/.claude/personal-oauth-token`` file             (vector: oauth_file)
    4. None resolved                                       (vector: none)

Tokens are written into ``os.environ`` so they inherit to child processes.
All user-facing messages are sanitized: ``sk-ant-[a-zA-Z0-9_-]+`` becomes
``sk-ant-<redacted>``.

No side effects at import time — all work happens inside the two entry-point
functions.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shlex
import subprocess
import sys

# Re-export the pipeline timestamp source so auth_bootstrap events byte-match
# existing log_event output. Both emission paths call the same function, which
# keeps the R7 byte-equivalence test monkey-patchable from a single site.
from cortex_command.pipeline.state import _now_iso

__all__ = ["ensure_sdk_auth", "resolve_auth_for_shell"]


# ---------------------------------------------------------------------------
# Sanitization
# ---------------------------------------------------------------------------

_SK_ANT_PATTERN = re.compile(r"sk-ant-[a-zA-Z0-9_-]+")


def _sanitize(text: str) -> str:
    """Redact ``sk-ant-*`` token-like substrings from free-form text."""
    return _SK_ANT_PATTERN.sub("sk-ant-<redacted>", text)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class _HelperInternalError(Exception):
    """Raised on helper-internal defects (malformed settings.json, etc.).

    Translates to exit code 2 in the shell entry point and re-raised from
    ``ensure_sdk_auth`` per the spec's Edge Cases table.
    """


# ---------------------------------------------------------------------------
# Resolution steps (mirror runner.sh:50-87)
# ---------------------------------------------------------------------------


def _read_api_key_helper() -> str:
    """Return the ``apiKeyHelper`` string from settings.json or settings.local.json.

    Empty string means no helper configured. Malformed JSON raises
    ``_HelperInternalError`` (classified as exit 2).
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
        except json.JSONDecodeError as exc:
            raise _HelperInternalError(
                f"malformed {candidate.name}: {_sanitize(str(exc))}"
            ) from exc
        except OSError as exc:
            raise _HelperInternalError(
                f"could not read {candidate.name}: {_sanitize(repr(exc))}"
            ) from exc
        helper = data.get("apiKeyHelper", "") if isinstance(data, dict) else ""
        if helper:
            return helper
    return ""


def _invoke_api_key_helper(helper: str) -> str:
    """Run ``helper`` via the shell-split parts and return stdout (stripped).

    Returns empty string on timeout, missing binary, non-zero exit, or any
    OS-level failure — per Edge Cases these are user-environment issues that
    fall through to the oauth-file branch, NOT helper-internal (exit 2).
    """
    home = pathlib.Path.home()
    try:
        parts = shlex.split(helper.replace("~", str(home)))
    except ValueError:
        # Malformed helper command — treat as "no vector from helper".
        return ""
    if not parts:
        return ""
    try:
        result = subprocess.run(
            parts,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def _read_oauth_file() -> tuple[str, str]:
    """Read the personal OAuth token file.

    Returns ``(token, warning)``. ``token`` is the whitespace-stripped contents
    (empty if absent / blank). ``warning`` is a human-readable warning message
    when the file is absent or blank, empty otherwise.
    """
    home = pathlib.Path.home()
    token_file = home / ".claude" / "personal-oauth-token"
    if not token_file.exists():
        return "", (
            f"Warning: no apiKeyHelper configured and no OAuth token file "
            f"at {token_file} — claude -p will use Keychain auth if available"
        )
    try:
        raw = token_file.read_text(encoding="utf-8")
    except OSError as exc:
        return "", f"Warning: could not read {token_file}: {_sanitize(repr(exc))}"
    token = "".join(raw.split())  # strip all whitespace, matching `tr -d '[:space:]'`
    if not token:
        return "", (
            f"Warning: {token_file} exists but is empty — "
            f"claude -p will use Keychain auth if available"
        )
    return token, f"Using OAuth token from {token_file}"


# ---------------------------------------------------------------------------
# Event emission
# ---------------------------------------------------------------------------


def _build_event(vector: str, message: str) -> dict:
    """Build the ``auth_bootstrap`` event payload (ts field first)."""
    entry: dict = {"ts": _now_iso()}
    entry["event"] = "auth_bootstrap"
    entry["vector"] = vector
    entry["message"] = message
    return entry


def _write_event(event_log_path: pathlib.Path, event: dict) -> None:
    """Append one JSON line to the events log, byte-matching log_event output."""
    event_log_path.parent.mkdir(parents=True, exist_ok=True)
    # Open in append-only mode (O_APPEND). Single json.dumps + "\n" matches
    # claude/pipeline/state.py::log_event byte-for-byte.
    with open(event_log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def ensure_sdk_auth(event_log_path: pathlib.Path | None = None) -> dict:
    """Resolve an SDK auth vector and write it into ``os.environ``.

    Priority: pre-existing ``ANTHROPIC_API_KEY`` → ``apiKeyHelper`` →
    ``~/.claude/personal-oauth-token`` → none.

    On resolution, writes the credential to the appropriate env var
    (``ANTHROPIC_API_KEY`` for api-key-helper, ``CLAUDE_CODE_OAUTH_TOKEN``
    for oauth-file). The pre-existing branch does not re-write.

    Args:
        event_log_path: If provided, the ``auth_bootstrap`` event is appended
            as a single JSON line to this path. If None, the message is
            written to stderr instead.

    Returns:
        ``{"vector": str, "message": str, "event": dict}`` where ``vector``
        is one of ``env_preexisting``, ``api_key_helper``, ``oauth_file``,
        ``none``, and ``event`` is the exact payload written to the log
        (or the payload that *would* have been written had a path been given).

    Raises:
        _HelperInternalError: on malformed ``~/.claude/settings.json`` or
            other deterministic helper-internal defects.
    """
    # 1. Pre-existing ANTHROPIC_API_KEY.
    if os.environ.get("ANTHROPIC_API_KEY"):
        vector = "env_preexisting"
        message = "Using pre-existing ANTHROPIC_API_KEY from environment"
    else:
        # 2. apiKeyHelper from settings.json / settings.local.json.
        helper = _read_api_key_helper()
        api_key = _invoke_api_key_helper(helper) if helper else ""
        if api_key:
            os.environ["ANTHROPIC_API_KEY"] = api_key
            vector = "api_key_helper"
            message = "Resolved ANTHROPIC_API_KEY via apiKeyHelper"
        elif os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
            # OAuth token already in env — treat as env_preexisting equivalent.
            vector = "env_preexisting"
            message = "Using pre-existing CLAUDE_CODE_OAUTH_TOKEN from environment"
        else:
            # 3. personal-oauth-token file.
            token, warning = _read_oauth_file()
            if token:
                os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = token
                vector = "oauth_file"
                message = warning  # "Using OAuth token from ..."
            else:
                vector = "none"
                message = warning or (
                    "Warning: no auth vector resolved — "
                    "claude -p will use Keychain auth if available"
                )

    message = _sanitize(message)
    event = _build_event(vector, message)

    if event_log_path is not None:
        _write_event(event_log_path, event)
    else:
        sys.stderr.write(message + "\n")

    return {"vector": vector, "message": message, "event": event}


def resolve_auth_for_shell() -> int:
    """Shell entry point: print an ``export VAR=VALUE`` line or exit non-zero.

    Invoked by ``runner.sh`` via ``python3 -m claude.overnight.auth --shell``
    before the venv is active. Prints ``export ANTHROPIC_API_KEY=<quoted>`` or
    ``export CLAUDE_CODE_OAUTH_TOKEN=<quoted>`` to stdout on resolution;
    warning text goes to stderr.

    Returns:
        0 on resolution, 1 on no-vector, 2 on helper-internal failure
        (malformed settings.json, import errors, stdlib regressions).
    """
    try:
        # Resolve but do NOT emit the event to a log path — shell callers
        # don't have one, and the R1 contract routes the message to stderr.
        # We pass None for event_log_path so ensure_sdk_auth writes message
        # to stderr, then we additionally handle the export line here.
        if os.environ.get("ANTHROPIC_API_KEY"):
            # Already set in parent shell env — nothing to export.
            sys.stderr.write(
                "Using pre-existing ANTHROPIC_API_KEY from environment\n"
            )
            return 0

        helper = _read_api_key_helper()
        api_key = _invoke_api_key_helper(helper) if helper else ""
        if api_key:
            sys.stdout.write(
                f"export ANTHROPIC_API_KEY={shlex.quote(api_key)}\n"
            )
            return 0

        if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
            sys.stderr.write(
                "Using pre-existing CLAUDE_CODE_OAUTH_TOKEN from environment\n"
            )
            return 0

        token, warning = _read_oauth_file()
        if token:
            sys.stdout.write(
                f"export CLAUDE_CODE_OAUTH_TOKEN={shlex.quote(token)}\n"
            )
            if warning:
                sys.stderr.write(_sanitize(warning) + "\n")
            return 0

        # No vector resolved.
        if warning:
            sys.stderr.write(_sanitize(warning) + "\n")
        else:
            sys.stderr.write(
                "Warning: no auth vector resolved — "
                "claude -p will use Keychain auth if available\n"
            )
        return 1
    except _HelperInternalError as exc:
        sys.stderr.write(f"Error: auth helper internal failure: {_sanitize(str(exc))}\n")
        return 2
    except Exception as exc:  # noqa: BLE001 — stdlib-regression safety net
        sys.stderr.write(
            f"Error: auth helper internal failure: {_sanitize(repr(exc))}\n"
        )
        return 2


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m claude.overnight.auth",
        description="Resolve the SDK auth vector for runner.sh / daytime_pipeline.py.",
    )
    parser.add_argument(
        "--shell",
        action="store_true",
        help="Print an 'export VAR=VALUE' line to stdout for shell eval.",
    )
    args = parser.parse_args(argv)
    if args.shell:
        return resolve_auth_for_shell()
    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main())
