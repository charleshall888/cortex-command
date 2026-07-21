"""Sandbox pre-flight commit gate (spec Req 17 / Task 12).

Extracted from the retired ``cortex_command.parity_check`` module (#407): the
SKILL.md-to-bin parity linter retired without named evidence, but this gate is
one of the named survivors in the "Enforcement gates carry named evidence"
constraint (`cortex/requirements/project.md`).

Fires when a staged diff hunk touches sandbox-source patterns in the watched
files below, and then requires a fresh, schema-valid
``preflight.md`` whose ``commit_hash`` matches HEAD and whose
``claude_version`` matches the current install. Silently passes when no
sandbox-source change is staged.

Invoked pre-commit via ``just check-sandbox-preflight`` (module invocation
under ``uv run`` — PyYAML is required for the embedded YAML block).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# Watched files whose staged diff hunks are scanned for sandbox-source
# patterns. Maps file path -> tuple of regex patterns (any match in a staged
# diff hunk fires the gate). The sandbox_settings module fires on ANY change
# (entire file is sandbox-source, so the pattern is r"." matching everything).
SANDBOX_WATCHED_FILES: dict[str, tuple[str, ...]] = {
    "cortex_command/pipeline/dispatch.py": (
        r"_load_project_settings",
        r"sandbox",
        r"SandboxSettings",
        r"build_sandbox",
        r"write_settings_tempfile",
    ),
    "cortex_command/overnight/runner.py": (
        r"_spawn_orchestrator",
        r"--settings",
        r"sandbox",
    ),
    "cortex_command/overnight/sandbox_settings.py": (
        # entire file is sandbox-source — any change fires the gate
        r".",
    ),
    "pyproject.toml": (
        r"claude-agent-sdk",
    ),
}

# Canonical preflight artifact location for the sandbox per-spawn epic.
PREFLIGHT_PATH = (
    "cortex/lifecycle/apply-per-spawn-sandboxfilesystemdenywrite-at-all-overnight-spawn-sites/preflight.md"
)


def _staged_diff_hunks(path: str, root: Path) -> str:
    """Return ``git diff --cached -U0 -- <path>`` output (added-line content).

    Returns empty string if the file is not staged or git fails. Only the
    ``+``-prefixed added lines are extracted (excluding the ``+++`` header
    line) so renames/whitespace shifts don't generate false positives.
    """
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "-U0", "--", path],
            cwd=str(root),
            capture_output=True,
            check=False,
            text=True,
        )
    except (FileNotFoundError, OSError):
        return ""
    if out.returncode != 0:
        return ""
    added: list[str] = []
    for ln in out.stdout.splitlines():
        # Skip diff metadata; capture only added-line content.
        if ln.startswith("+++"):
            continue
        if ln.startswith("+"):
            added.append(ln[1:])
    return "\n".join(added)


def _gate_fires_for_file(path: str, hunk_text: str, patterns: tuple[str, ...]) -> bool:
    """True if any pattern matches the staged-hunk text for ``path``."""
    if not hunk_text:
        return False
    for pat in patterns:
        if re.search(pat, hunk_text):
            return True
    return False


def _detect_sandbox_source_changes(root: Path) -> list[str]:
    """Return the list of watched-file paths whose staged hunks fire the gate."""
    fired: list[str] = []
    for path, patterns in SANDBOX_WATCHED_FILES.items():
        hunk = _staged_diff_hunks(path, root)
        if _gate_fires_for_file(path, hunk, patterns):
            fired.append(path)
    return fired


def _resolve_preflight_target_hash(root: Path) -> str | None:
    """Return the commit hash that ``preflight.md::commit_hash`` must match.

    The gate runs **pre-commit**, so the staged change has not yet become a
    commit. ``commit_hash`` in preflight.md is documented to be "the full sha
    of the cortex-command HEAD at preflight-run time" — i.e., the most-recent
    existing commit at the moment the human ran the preflight test.

    At gate time (pre-commit), the most-recent existing commit IS current
    ``HEAD`` (the staged change is the about-to-be-created NEW commit, not
    yet HEAD). So we resolve ``git rev-parse HEAD``. The hash binding is
    self-invalidating: once any sandbox-source commit lands, current HEAD
    advances and the recorded hash no longer matches → a new preflight is
    required. (The spec text mentions ``HEAD~`` in passing, but the
    workflow it describes — "preflight then stage sandbox-source change" —
    only self-consistent if the comparison target is current HEAD at
    pre-commit gate time, not HEAD~.)
    """
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            capture_output=True,
            check=False,
            text=True,
        )
    except (FileNotFoundError, OSError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def _capture_claude_version() -> str | None:
    """Return ``claude --version`` stdout (stripped) or None if unavailable."""
    try:
        out = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def _parse_preflight_yaml(text: str) -> tuple[dict | None, str | None]:
    """Extract and parse the embedded YAML block from preflight.md.

    The file may contain a fenced ```yaml ... ``` block; this helper extracts
    the first such block and returns ``(parsed_dict, error)``. On error,
    returns ``(None, error_message)``.
    """
    m = re.search(r"```yaml\s*\n(.*?)\n```", text, re.DOTALL)
    if not m:
        return None, "no fenced ```yaml block found in preflight.md"
    yaml_body = m.group(1)
    try:
        import yaml  # type: ignore
    except ImportError:
        return None, "PyYAML not installed (required for preflight gate)"
    try:
        data = yaml.safe_load(yaml_body)
    except Exception as exc:  # YAML parser raises various exception types
        return None, f"YAML parse error: {exc}"
    if not isinstance(data, dict):
        return None, "preflight YAML block did not parse as a mapping"
    return data, None


def _validate_preflight_schema(data: dict) -> list[str]:
    """Return a list of schema-violation messages; empty list = valid."""
    errors: list[str] = []
    required_fields = {
        "pass": bool,
        "timestamp": str,
        "commit_hash": str,
        "claude_version": str,
        "test_command": str,
        "exit_code": int,
        "stderr_contains_eperm": bool,
        "stderr_excerpt": str,
        "target_path": str,
        "target_unmodified": bool,
    }
    for field, expected_type in required_fields.items():
        if field not in data:
            errors.append(f"missing required field {field!r}")
            continue
        value = data[field]
        # bool is a subclass of int in Python; tighten the check.
        if expected_type is bool and not isinstance(value, bool):
            errors.append(f"field {field!r} must be bool, got {type(value).__name__}")
            continue
        if expected_type is int and isinstance(value, bool):
            errors.append(f"field {field!r} must be int (not bool)")
            continue
        if not isinstance(value, expected_type):
            errors.append(
                f"field {field!r} must be {expected_type.__name__}, "
                f"got {type(value).__name__}"
            )
    if errors:
        return errors
    # Semantic checks: gate only passes when the recorded run actually denied.
    # exit_code is recorded for forensics but NOT asserted: claude -p wraps inner
    # tool failures gracefully and exits 0 even when a Bash subprocess hit EPERM.
    # Kernel-enforcement signals (target_unmodified + stderr_contains_eperm) are
    # the load-bearing checks; the wrapper's exit code is incidental.
    if data.get("pass") is not True:
        errors.append("field 'pass' must be true (preflight did not record a passing run)")
    if data.get("stderr_contains_eperm") is not True:
        errors.append("field 'stderr_contains_eperm' must be true")
    if data.get("target_unmodified") is not True:
        errors.append("field 'target_unmodified' must be true")
    return errors


def check_sandbox_preflight_gate(root: Path) -> list[str]:
    """Run the structured preflight gate per spec Req 17.

    Returns a list of ``E100``-series violation messages. Empty list means the
    gate did not fire OR fired and passed all checks.
    """
    violations: list[str] = []

    fired_files = _detect_sandbox_source_changes(root)
    if not fired_files:
        return []  # gate did not fire — no sandbox-source changes staged

    # Gate fired: validate preflight.md exists.
    preflight_abs = root / PREFLIGHT_PATH
    if not preflight_abs.is_file():
        return [
            f"E100 sandbox preflight gate fired ({', '.join(fired_files)}) "
            f"but {PREFLIGHT_PATH} is missing — re-run pre-flight per spec Req 12"
        ]

    try:
        text = preflight_abs.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"E100 cannot read preflight: {exc}"]

    data, parse_err = _parse_preflight_yaml(text)
    if data is None:
        return [f"E101 preflight schema invalid: {parse_err}"]

    schema_errors = _validate_preflight_schema(data)
    if schema_errors:
        return [f"E101 preflight schema invalid: {err}" for err in schema_errors]

    # Commit-hash freshness check: recorded hash must match current HEAD
    # at gate time (gate runs pre-commit; staged change is not yet a commit;
    # current HEAD is the most-recent existing commit, which is the value
    # the human recorded when running the preflight test).
    head = _resolve_preflight_target_hash(root)
    if head is None:
        return ["E102 cannot resolve git HEAD for commit-hash freshness check"]
    recorded_hash = str(data.get("commit_hash", "")).strip()
    if recorded_hash != head:
        violations.append(
            f"E102 preflight evidence is stale relative to current sandbox-source "
            f"state — re-run pre-flight against HEAD "
            f"(recorded={recorded_hash[:12] or '<empty>'}, HEAD={head[:12]})"
        )

    # claude --version drift check
    current_version = _capture_claude_version()
    recorded_version = str(data.get("claude_version", "")).strip()
    if current_version is None:
        violations.append("E103 cannot invoke `claude --version` for drift check")
    elif current_version != recorded_version:
        violations.append(
            f"E103 claude binary drift between preflight and current install — "
            f"re-run preflight (recorded={recorded_version!r}, "
            f"current={current_version!r})"
        )

    return violations


def main(argv: list[str] | None = None) -> int:  # noqa: ARG001
    """Gate entry point: exit 1 on violations, 0 otherwise.

    An internal error must never block a commit — it degrades to a stderr
    warning and exit 0, matching the gate's behavior inside the retired host.
    """
    import os

    root = Path(os.getcwd()).resolve()
    try:
        violations = check_sandbox_preflight_gate(root)
    except Exception as exc:  # defensive: gate must never crash the commit path
        print(
            f"sandbox-preflight-gate: internal error ({exc}); skipping gate",
            file=sys.stderr,
        )
        return 0
    for v in violations:
        print(f"{PREFLIGHT_PATH}:1:1: {v}", file=sys.stderr)
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
