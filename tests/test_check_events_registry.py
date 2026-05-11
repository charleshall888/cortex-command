"""Self-tests for ``bin/cortex-check-events-registry`` (R5 acceptance).

Each test case sets up a temp directory with a minimal fixture for
``bin/.events-registry.md`` and (where relevant) a staged-files corpus under
``skills/`` or ``cortex_command/overnight/prompts/``. The gate is invoked via
``subprocess`` with the ``--root <tmp_path>`` test-only override, which lets
us exercise the pre-commit path without a real git index. We assert exit code
and a stable substring of the gate's positive-routing diagnostic.

R5 acceptance cases covered:

1. Unregistered skill-prompt event name fails the pre-commit (--staged) path
   with ``UNREGISTERED_EVENT``.
2. Registered name with a valid consumer passes the pre-commit path.
3. Audit mode flags a past ``deprecation_date`` with ``STALE_DEPRECATION``.
4. Pre-commit path does NOT fire the date check — a registry with stale rows
   still passes ``--staged`` so long as referential integrity holds.
5. Audit mode flags a ``deprecated-pending-removal`` row missing ``owner``
   with ``MISSING_OWNER``.
6. Missing registry file errors with ``MISSING_REGISTRY`` on both paths.
7. Audit mode (via schema validation) flags a ``category != live`` row with
   missing rationale.
8. Pre-commit path passes when no in-scope files are staged, even when the
   registry contains stale deprecation rows.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "bin" / "cortex-check-events-registry"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_registry(root: Path, body: str) -> None:
    """Write ``body`` to ``<root>/bin/.events-registry.md``."""
    (root / "bin").mkdir(parents=True, exist_ok=True)
    (root / "bin" / ".events-registry.md").write_text(body, encoding="utf-8")


def _write_skill_prompt(root: Path, rel: str, body: str) -> None:
    """Write ``body`` to ``<root>/<rel>`` after ensuring parent dirs exist."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _run(args: list[str], root: Path) -> subprocess.CompletedProcess[bytes]:
    """Invoke the gate script with ``--root <root>`` + ``args``."""
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args, "--root", str(root)],
        capture_output=True,
        check=False,
    )


# Minimal canonical registry header used in fixtures. Tests append rows
# directly to this template body.
_HEADER = (
    "# Test fixture registry\n\n"
    "| event_name | target | scan_coverage | producers | consumers | "
    "category | added_date | deprecation_date | rationale | owner |\n"
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
)


def _registry_with_rows(*rows: str) -> str:
    """Compose a registry body from the canonical header and ``rows`` lines."""
    return _HEADER + "".join(row if row.endswith("\n") else row + "\n" for row in rows)


# A canonical valid live row referencing event ``alpha_event``.
_ALPHA_LIVE_ROW = (
    "| `alpha_event` | `per-feature-events-log` | `gate-enforced` | "
    "`skills/alpha/SKILL.md` | `cortex_command/pipeline/metrics.py:1` | "
    "`live` | `2026-05-11` |  |  |  |"
)


# ---------------------------------------------------------------------------
# Case 1: unregistered skill-prompt name fails pre-commit
# ---------------------------------------------------------------------------


def test_case1_unregistered_event_fails_staged(tmp_path: Path) -> None:
    _write_registry(tmp_path, _registry_with_rows(_ALPHA_LIVE_ROW))
    _write_skill_prompt(
        tmp_path,
        "skills/example/SKILL.md",
        '```json\n{"event": "unknown_event", "phase": "x"}\n```\n',
    )

    result = _run(["--staged"], tmp_path)

    assert result.returncode == 1, result.stderr.decode()
    stderr = result.stderr.decode()
    assert "UNREGISTERED_EVENT" in stderr
    assert "unknown_event" in stderr


# ---------------------------------------------------------------------------
# Case 2: registered name with valid consumer passes pre-commit
# ---------------------------------------------------------------------------


def test_case2_registered_event_passes_staged(tmp_path: Path) -> None:
    _write_registry(tmp_path, _registry_with_rows(_ALPHA_LIVE_ROW))
    _write_skill_prompt(
        tmp_path,
        "skills/alpha/SKILL.md",
        '```json\n{"event": "alpha_event", "phase": "y"}\n```\n',
    )

    result = _run(["--staged"], tmp_path)

    assert result.returncode == 0, result.stderr.decode()
    assert result.stderr == b""


# ---------------------------------------------------------------------------
# Case 3: audit mode flags stale deprecation_date
# ---------------------------------------------------------------------------


def test_case3_audit_flags_stale_deprecation(tmp_path: Path) -> None:
    stale_row = (
        "| `gamma_event` | `per-feature-events-log` | `gate-enforced` | "
        "`skills/gamma/SKILL.md` | `tests/test_gamma.py:1 (tests-only)` | "
        "`deprecated-pending-removal` | `2025-01-01` | `2025-06-01` | "
        "Replaced by alpha_event after the 2025 emission redesign cleanup. | "
        "`alice` |"
    )
    _write_registry(tmp_path, _registry_with_rows(stale_row))

    result = _run(["--audit"], tmp_path)

    assert result.returncode == 1, result.stderr.decode()
    stderr = result.stderr.decode()
    assert "STALE_DEPRECATION" in stderr
    assert "gamma_event" in stderr


# ---------------------------------------------------------------------------
# Case 4: pre-commit path does NOT fire the date check
# ---------------------------------------------------------------------------


def test_case4_staged_ignores_stale_deprecation(tmp_path: Path) -> None:
    stale_row = (
        "| `gamma_event` | `per-feature-events-log` | `gate-enforced` | "
        "`skills/gamma/SKILL.md` | `tests/test_gamma.py:1 (tests-only)` | "
        "`deprecated-pending-removal` | `2025-01-01` | `2025-06-01` | "
        "Replaced by alpha_event after the 2025 emission redesign cleanup. | "
        "`alice` |"
    )
    _write_registry(tmp_path, _registry_with_rows(_ALPHA_LIVE_ROW, stale_row))
    _write_skill_prompt(
        tmp_path,
        "skills/alpha/SKILL.md",
        '```json\n{"event": "alpha_event"}\n```\n',
    )

    result = _run(["--staged"], tmp_path)

    assert result.returncode == 0, result.stderr.decode()
    stderr = result.stderr.decode()
    # Staged path does not perform date checks.
    assert "STALE_DEPRECATION" not in stderr


# ---------------------------------------------------------------------------
# Case 5: audit mode flags deprecated-pending-removal row missing owner
# ---------------------------------------------------------------------------


def test_case5_audit_flags_missing_owner(tmp_path: Path) -> None:
    # deprecation_date set to a far-future date so MISSING_OWNER is the
    # diagnostic under test (STALE_DEPRECATION is only emitted for past dates).
    no_owner_row = (
        "| `delta_event` | `per-feature-events-log` | `gate-enforced` | "
        "`skills/delta/SKILL.md` | `tests/test_delta.py:1 (tests-only)` | "
        "`deprecated-pending-removal` | `2026-05-11` | `2099-01-01` | "
        "Slated for removal once delta consumers migrate to alpha emission. |  |"
    )
    _write_registry(tmp_path, _registry_with_rows(no_owner_row))

    result = _run(["--audit"], tmp_path)

    assert result.returncode == 1, result.stderr.decode()
    stderr = result.stderr.decode()
    assert "MISSING_OWNER" in stderr
    assert "delta_event" in stderr


# ---------------------------------------------------------------------------
# Case 6: missing registry file errors with MISSING_REGISTRY (both paths)
# ---------------------------------------------------------------------------


def test_case6_missing_registry_staged(tmp_path: Path) -> None:
    # No registry written at all.
    result = _run(["--staged"], tmp_path)

    assert result.returncode == 1, result.stderr.decode()
    assert "MISSING_REGISTRY" in result.stderr.decode()


def test_case6_missing_registry_audit(tmp_path: Path) -> None:
    result = _run(["--audit"], tmp_path)

    assert result.returncode == 1, result.stderr.decode()
    assert "MISSING_REGISTRY" in result.stderr.decode()


# ---------------------------------------------------------------------------
# Case 7: category != live row missing rationale errors
# ---------------------------------------------------------------------------


def test_case7_non_live_row_missing_rationale(tmp_path: Path) -> None:
    # category=audit-affordance (non-live) with an empty rationale cell —
    # gate requires rationale >= 30 chars for any non-live category.
    no_rationale_row = (
        "| `epsilon_event` | `per-feature-events-log` | `gate-enforced` | "
        "`skills/epsilon/SKILL.md` | `human-skim` | `audit-affordance` | "
        "`2026-05-11` |  |  |  |"
    )
    _write_registry(tmp_path, _registry_with_rows(no_rationale_row))

    # Audit path surfaces schema errors. Either path catches the schema
    # violation (parse_registry emits INVALID_ROW for the missing rationale).
    result = _run(["--audit"], tmp_path)

    assert result.returncode == 1, result.stderr.decode()
    stderr = result.stderr.decode()
    assert "INVALID_ROW" in stderr
    assert "epsilon_event" in stderr
    assert "rationale" in stderr


# ---------------------------------------------------------------------------
# Case 8: pre-commit path passing with no in-scope staged files
# ---------------------------------------------------------------------------


def test_case8_staged_passes_when_no_scan_files(tmp_path: Path) -> None:
    # Registry contains a stale deprecation row, but no skill prompts or
    # orchestrator-round-style prompt files exist under root — so the
    # staged path has nothing to check and exits 0.
    stale_row = (
        "| `gamma_event` | `per-feature-events-log` | `gate-enforced` | "
        "`skills/gamma/SKILL.md` | `tests/test_gamma.py:1 (tests-only)` | "
        "`deprecated-pending-removal` | `2025-01-01` | `2025-06-01` | "
        "Replaced by alpha_event after the 2025 emission redesign cleanup. | "
        "`alice` |"
    )
    _write_registry(tmp_path, _registry_with_rows(_ALPHA_LIVE_ROW, stale_row))

    # Drop an unrelated file outside the scan globs — proves the gate
    # ignores it and still passes.
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "notes.md").write_text(
        '```json\n{"event": "unknown_event"}\n```\n', encoding="utf-8"
    )

    result = _run(["--staged"], tmp_path)

    assert result.returncode == 0, result.stderr.decode()
    assert result.stderr == b""
