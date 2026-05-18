"""Lint: backlog ``grep -c "<token>"`` examples must reference real events.

Spec: cortex/lifecycle/release-gate-empirical-from-claude-session/spec.md (Task 3).

Backlog tickets routinely include verification commands of the form
``grep -c "<event-name>" <path>`` as Done-When conditions. When an author
hallucinates an event name (e.g. ``feature_dispatched`` instead of the
emitted ``dispatch_complete``), the gate looks credible but every smoke run
returns ``0`` and the failure mode is invisible until an operator tries to
follow the procedure.

This file is a pure-python pytest lint. It walks ``cortex/backlog/*.md``
(skipping ``cortex/backlog/archive/``), extracts every ``grep -c "<token>"``
and ``grep -c '<token>'`` invocation (both in fenced code blocks and inline
prose), filters to tokens that look like event names
(``re.fullmatch(r'[a-z_]+', token)``), and for each such token verifies
that it appears in EITHER the registry at ``bin/.events-registry.md`` OR as
a literal string under ``cortex_command/`` (via ``git grep -F``). Tokens
that fail both checks are reported as ``UNREGISTERED_GREP_TARGET`` with
the offending ticket path and line number.

Self-tests at the bottom of the file exercise the helper against
``tmp_path`` fixtures (one positive, one negative). The terminal
``test_live_backlog_has_no_unregistered_grep_targets`` runs the lint
against the actual backlog corpus and is the load-bearing regression
guard: it would have failed on the pre-fix #230 ticket that referenced
``feature_dispatched``.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Iterable

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
BACKLOG_DIR = REPO_ROOT / "cortex" / "backlog"
REGISTRY_PATH = REPO_ROOT / "bin" / ".events-registry.md"

# Capture the token inside the quotes after ``grep -c``. Either quote style
# (single or double) is accepted; the closing quote must match-or-mismatch
# only after at least one non-quote character. The character class
# ``[^"\']+`` ensures we do not cross another quote boundary inside the
# captured token.
_GREP_C_RE = re.compile(r"""grep\s+-c\s+["']([^"']+)["']""")

# Event-name shape: lowercase ASCII letters and underscores only. This
# filter excludes file paths (contain ``/`` or ``.``), uppercase
# identifiers (e.g. EPERM), quoted prose (contains spaces), and regex
# patterns (contain metacharacters). It targets the
# ``feature_dispatched``-class hallucinations described in the spec.
_EVENT_SHAPE_RE = re.compile(r"[a-z_]+")

# Narrow allowlist for tokens that pass the shape filter but are
# definitively not event names (start tiny; expand only if false positives
# surface in practice).
_ALLOWLIST: frozenset[str] = frozenset({"true", "false", "none", "null"})


def _iter_backlog_files(backlog_dir: Path) -> Iterable[Path]:
    """Yield numbered backlog markdown files, skipping ``archive/``."""
    for path in sorted(backlog_dir.glob("[0-9]*-*.md")):
        if "/archive/" in str(path):
            continue
        yield path


def _token_emitted_in_codebase(token: str, root: Path) -> bool:
    """Return True if ``token`` appears as a literal under ``cortex_command/``."""
    result = subprocess.run(
        ["git", "grep", "-lF", token, "cortex_command/"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def _find_unregistered_grep_targets(
    backlog_dir: Path,
    registry_path: Path,
    root: Path,
) -> list[str]:
    """Walk ``backlog_dir`` and return diagnostic strings for hallucinated tokens.

    Each returned string is the operator-facing failure message:
    ``UNREGISTERED_GREP_TARGET: <ticket-path>:<line> references "<token>" ...``
    """
    registry_text = registry_path.read_text(encoding="utf-8") if registry_path.exists() else ""

    diagnostics: list[str] = []
    for ticket in _iter_backlog_files(backlog_dir):
        try:
            lines = ticket.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(lines, start=1):
            for match in _GREP_C_RE.finditer(line):
                token = match.group(1)
                if not _EVENT_SHAPE_RE.fullmatch(token):
                    continue
                if token in _ALLOWLIST:
                    continue
                if token in registry_text:
                    continue
                if _token_emitted_in_codebase(token, root):
                    continue
                diagnostics.append(
                    f"UNREGISTERED_GREP_TARGET: {ticket}:{lineno} "
                    f'references "{token}" which is neither a '
                    "registered event nor an emitted string"
                )
    return diagnostics


# ---------------------------------------------------------------------------
# Self-tests against tmp_path fixtures
# ---------------------------------------------------------------------------


def _seed_fake_repo(tmp_path: Path, registry_body: str, codebase_files: dict[str, str]) -> None:
    """Initialise a minimal git repo with a registry and codebase strings.

    The lint uses ``git grep`` for the codebase check, so the fixture must
    be a real git repo with the cortex_command/ files committed (or at
    least tracked). We commit so ``git grep`` picks them up without
    requiring ``--cached`` semantics.
    """
    (tmp_path / "bin").mkdir(parents=True, exist_ok=True)
    (tmp_path / "bin" / ".events-registry.md").write_text(registry_body, encoding="utf-8")

    (tmp_path / "cortex_command").mkdir(parents=True, exist_ok=True)
    for rel, body in codebase_files.items():
        full = tmp_path / "cortex_command" / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(body, encoding="utf-8")

    (tmp_path / "cortex" / "backlog").mkdir(parents=True, exist_ok=True)

    # Initialise a throwaway git repo so the production helper's
    # ``git grep -lF`` call has an index to search. The ``commit.gpgsign``
    # / ``tag.gpgsign`` overrides are fixture-only — they are required so
    # the seeding commit succeeds on operator machines whose ``--global``
    # git config enables signing while the sandbox blocks ``~/.gnupg``
    # access. The production code under test never commits and is
    # unaffected by these overrides.
    git_env = [
        "-c",
        "user.email=fixture@test.invalid",
        "-c",
        "user.name=fixture",
        "-c",
        "commit.gpgsign=false",
        "-c",
        "tag.gpgsign=false",
    ]
    subprocess.run(
        ["git", "init", "-q"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", *git_env, "add", "-A"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", *git_env, "commit", "-q", "-m", "seed"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )


def _write_backlog(tmp_path: Path, name: str, body: str) -> Path:
    """Write a backlog markdown file under the fixture tree."""
    target = tmp_path / "cortex" / "backlog" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return target


def test_fixture_positive_registered_event_passes_lint(tmp_path: Path) -> None:
    """A backlog grep target whose token appears in the registry passes."""
    _seed_fake_repo(
        tmp_path,
        registry_body="| `dispatch_complete` | per-feature-events-log | gate-enforced |\n",
        codebase_files={"pipeline/dispatch.py": '"event": "dispatch_complete"\n'},
    )
    _write_backlog(
        tmp_path,
        "100-positive-fixture.md",
        '- `grep -c "dispatch_complete" cortex/lifecycle/x/pipeline-events.log` returns >= 1\n',
    )

    diagnostics = _find_unregistered_grep_targets(
        tmp_path / "cortex" / "backlog",
        tmp_path / "bin" / ".events-registry.md",
        tmp_path,
    )

    assert diagnostics == [], diagnostics


def test_fixture_negative_hallucinated_event_fails_lint(tmp_path: Path) -> None:
    """A backlog grep target with no registry/codebase backing is reported."""
    _seed_fake_repo(
        tmp_path,
        registry_body="| `dispatch_complete` | per-feature-events-log | gate-enforced |\n",
        codebase_files={"pipeline/dispatch.py": '"event": "dispatch_complete"\n'},
    )
    backlog_path = _write_backlog(
        tmp_path,
        "101-negative-fixture.md",
        '- `grep -c "feature_dispatched" cortex/lifecycle/x/pipeline-events.log` returns >= 1\n',
    )

    diagnostics = _find_unregistered_grep_targets(
        tmp_path / "cortex" / "backlog",
        tmp_path / "bin" / ".events-registry.md",
        tmp_path,
    )

    assert len(diagnostics) == 1, diagnostics
    msg = diagnostics[0]
    assert "UNREGISTERED_GREP_TARGET" in msg
    assert "feature_dispatched" in msg
    assert str(backlog_path) in msg
    assert ":1" in msg  # line number is preserved


# ---------------------------------------------------------------------------
# Live-corpus assertion: load-bearing regression guard against #230-style
# hallucinations. After Task 1's rewrite of #230 the corpus is clean; this
# test would have failed before that rewrite landed.
# ---------------------------------------------------------------------------


def test_live_backlog_has_no_unregistered_grep_targets() -> None:
    """Every shape-matching ``grep -c`` token in cortex/backlog/ must resolve."""
    diagnostics = _find_unregistered_grep_targets(
        BACKLOG_DIR,
        REGISTRY_PATH,
        REPO_ROOT,
    )
    assert diagnostics == [], "\n".join(diagnostics)
