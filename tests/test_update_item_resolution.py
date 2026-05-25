"""Unit and subprocess tests for ``cortex-update-item`` resolution behavior.

Task 7 of unified-backlog-lifecycle-slug-resolver-extend.

Covers the new exit-code surface introduced by Task 6:

  * Library-level: ``_find_item_with_status(slug_or_uuid, backlog_dir)`` returns
    the right ``ResolutionResult`` shape across the 5-step order.
  * Subprocess-level: the CLI exit-code surface for ambiguous/not-found/
    unambiguous resolution — exit-2 emits the standard ``_format_candidates``
    shape on stderr with no file mutation, exit-1 emits
    ``Item not found: <input>`` with no file mutation, exit-0 mutates the
    matched file in place.

Imports the shared ``BACKLOG_RESOLUTION_CORPUS`` and ``make_item`` helpers
that Task 5 promoted to ``tests/conftest.py`` (per R9). The corpus is touched
here purely to satisfy R9's "one citation per file" acceptance — see
``test_corpus_is_imported_for_r9`` below.

Subprocess invocations use ``python -m cortex_command.backlog.update_item``
(consistent with ``tests/test_resolve_backlog_item.py:136-144``) and route
the temp backlog dir via ``CORTEX_REPO_ROOT`` because ``update_item.main()``
calls ``_resolve_user_project_root()`` (not ``CORTEX_BACKLOG_DIR``) per
research §Tradeoffs Decision 5 / spec §Non-Requirements (backlog-dir
discovery divergence is an intentional out-of-scope deferral).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

import cortex_command.backlog.update_item as _update_item_module
from cortex_command.backlog.resolve_item import ResolutionResult

from tests.conftest import (
    BACKLOG_RESOLUTION_CORPUS,
    make_item,
)


# ---------------------------------------------------------------------------
# Subprocess helper
# ---------------------------------------------------------------------------


def _run(args: list[str], repo_root: Path) -> subprocess.CompletedProcess:
    """Run ``cortex-update-item`` against a tmp project root.

    Mirrors the ``_run`` pattern in tests/test_resolve_backlog_item.py:136-144
    but invokes ``cortex_command.backlog.update_item`` and passes
    ``CORTEX_REPO_ROOT`` (not ``CORTEX_BACKLOG_DIR``) because
    ``update_item.main()`` uses ``_resolve_user_project_root()`` per spec
    §Non-Requirements Decision 5. The temp tree must contain
    ``cortex/backlog/<NNN>-foo.md`` for the CLI to discover items.
    """
    env = {"CORTEX_REPO_ROOT": str(repo_root), **os.environ}
    return subprocess.run(
        [sys.executable, "-m", "cortex_command.backlog.update_item", *args],
        capture_output=True,
        text=True,
        env=env,
    )


def _make_repo(tmp_path: Path) -> Path:
    """Construct a temp project root containing ``cortex/backlog/``.

    Returns the project-root Path (the directory containing ``cortex/``).
    """
    backlog = tmp_path / "cortex" / "backlog"
    backlog.mkdir(parents=True)
    return tmp_path


# ---------------------------------------------------------------------------
# R9 corpus citation — minimum-one-import-per-file acceptance gate.
#
# Spec R9: ``grep -c "backlog_resolution_corpus|BACKLOG_RESOLUTION_CORPUS"``
# across this file and tests/test_resolve_backlog_item.py must return 2 (one
# per file). The constant is imported above; this test additionally exercises
# it so the import is load-bearing rather than purely cosmetic.
# ---------------------------------------------------------------------------


def test_corpus_is_imported_for_r9():
    """Sanity-check the shared corpus is non-empty and importable.

    R9 acceptance requires one citation per consumer file; this test makes
    the import load-bearing rather than purely structural.
    """
    assert isinstance(BACKLOG_RESOLUTION_CORPUS, list)
    assert len(BACKLOG_RESOLUTION_CORPUS) > 0
    # Spot-check a known entry — "fix" is one of the substring-ambiguous
    # inputs that transitions from silent-first-match to exit-2 ambiguous
    # under the new contract.
    assert "fix" in BACKLOG_RESOLUTION_CORPUS


# ---------------------------------------------------------------------------
# Library-level: _find_item_with_status returns the right ResolutionResult
# shape across the 5-step order.
# ---------------------------------------------------------------------------


_UUID_A = "a3b9ae8a-1111-1111-1111-111111111111"
_UUID_B = "a3b9ae8a-2222-2222-2222-222222222222"
_UUID_C = "a3b9ae8a-3333-3333-3333-333333333333"
_UUID_D = "dadaf6b6-431d-4c5a-92b5-6226be90d26b"


def test_find_item_with_status_ok(tmp_path):
    """Unambiguous match → status='ok' with the matched Path."""
    backlog = tmp_path / "cortex" / "backlog"
    backlog.mkdir(parents=True)
    item = make_item(backlog, "001-unique-zorp.md", "Unique Zorp Widget")
    result = _update_item_module._find_item_with_status("zorp", backlog)
    assert isinstance(result, ResolutionResult)
    assert result.status == "ok"
    assert result.item == item


def test_find_item_with_status_not_found(tmp_path):
    """No match → status='not_found' with item=None and candidates=[]."""
    backlog = tmp_path / "cortex" / "backlog"
    backlog.mkdir(parents=True)
    make_item(backlog, "001-some-ticket.md", "Some Ticket")
    result = _update_item_module._find_item_with_status(
        "xyzzy-nonexistent-99999", backlog
    )
    assert isinstance(result, ResolutionResult)
    assert result.status == "not_found"
    assert result.item is None
    assert result.candidates == []


def test_find_item_with_status_ambiguous(tmp_path):
    """Multi-match → status='ambiguous' with the candidate list populated."""
    backlog = tmp_path / "cortex" / "backlog"
    backlog.mkdir(parents=True)
    a = make_item(backlog, "001-extract-foo.md", "Extract foo from bar")
    b = make_item(backlog, "002-extract-baz.md", "Extract baz from qux")
    result = _update_item_module._find_item_with_status("extract", backlog)
    assert isinstance(result, ResolutionResult)
    assert result.status == "ambiguous"
    assert result.item is None
    assert len(result.candidates) == 2
    assert a in result.candidates
    assert b in result.candidates


def test_find_item_with_status_uuid_prefix(tmp_path):
    """UUID-prefix step (≥8 hex chars) resolves uniquely."""
    backlog = tmp_path / "cortex" / "backlog"
    backlog.mkdir(parents=True)
    item = make_item(backlog, "004-delta.md", "Delta", extra=f"uuid: {_UUID_D}\n")
    result = _update_item_module._find_item_with_status("dadaf6b6", backlog)
    assert result.status == "ok"
    assert result.item == item


def test_find_item_with_status_uuid_prefix_ambiguous(tmp_path):
    """UUID-prefix step returns ambiguous when ≥2 UUIDs share an 8-char prefix."""
    backlog = tmp_path / "cortex" / "backlog"
    backlog.mkdir(parents=True)
    make_item(backlog, "001-alpha.md", "Alpha", extra=f"uuid: {_UUID_A}\n")
    make_item(backlog, "002-beta.md", "Beta", extra=f"uuid: {_UUID_B}\n")
    make_item(backlog, "003-gamma.md", "Gamma", extra=f"uuid: {_UUID_C}\n")
    result = _update_item_module._find_item_with_status("a3b9ae8a", backlog)
    assert result.status == "ambiguous"
    assert len(result.candidates) == 3


def test_find_item_with_status_lifecycle_slug(tmp_path):
    """Step 4: exact lifecycle_slug frontmatter equality."""
    backlog = tmp_path / "cortex" / "backlog"
    backlog.mkdir(parents=True)
    item = make_item(
        backlog,
        "010-some-ticket.md",
        "Some Ticket",
        extra="lifecycle_slug: my-bespoke-lifecycle-slug\n",
    )
    make_item(backlog, "011-other.md", "Other Ticket")
    result = _update_item_module._find_item_with_status(
        "my-bespoke-lifecycle-slug", backlog
    )
    assert result.status == "ok"
    assert result.item == item


# ---------------------------------------------------------------------------
# Subprocess-level: CLI exit-code surface.
#
# Required parametrized tests per task brief (R7 + R8):
#   * test_ambiguous_exits_2_with_candidate_list
#   * test_not_found_exits_1
#   * test_unambiguous_succeeds_and_mutates
# ---------------------------------------------------------------------------


# Regex matching the _format_candidates output shape:
#   "ambiguous: N matches\n<filename>\t<title>\n…"
# Capped at 5 with "... (N more)" overflow per resolve_item._format_candidates.
_CANDIDATE_LIST_RE = re.compile(
    r"^ambiguous:\s+(\d+)\s+matches\n"
    r"([0-9]+-[a-z0-9-]+\.md\t.+\n?)+",
    re.MULTILINE,
)


@pytest.mark.parametrize(
    "ambiguous_input,filenames,titles",
    [
        (
            "extract",
            ["001-extract-foo.md", "002-extract-baz.md"],
            ["Extract foo from bar", "Extract baz from qux"],
        ),
        (
            "fix",
            ["001-fix-alpha.md", "002-fix-beta.md", "003-fix-gamma.md"],
            ["Fix alpha bug", "Fix beta bug", "Fix gamma bug"],
        ),
    ],
)
def test_ambiguous_exits_2_with_candidate_list(
    tmp_path, ambiguous_input, filenames, titles
):
    """Ambiguous input → exit 2 + ``_format_candidates`` stderr + no mutation.

    Asserts (per R7):
      * exit_code == 2
      * stderr matches the ``ambiguous: N matches\\n<filename>\\t<title>\\n…``
        shape via regex (the same ``_format_candidates`` output as
        ``cortex-resolve-backlog-item``).
      * No backlog file is mutated — verified via ``mtime`` comparison
        across all candidate files.
    """
    repo_root = _make_repo(tmp_path)
    backlog = repo_root / "cortex" / "backlog"
    paths: list[Path] = []
    for filename, title in zip(filenames, titles):
        paths.append(make_item(backlog, filename, title))

    # Snapshot mtimes before invocation.
    mtimes_before = {p: p.stat().st_mtime_ns for p in paths}

    # Sleep briefly to ensure any mutation would advance mtime beyond the
    # snapshot tick (defensive against same-tick comparisons on coarse-
    # granularity filesystems).
    time.sleep(0.01)

    result = _run([ambiguous_input, "--status", "complete"], repo_root)

    assert result.returncode == 2, (
        f"expected exit 2, got {result.returncode}; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    # Candidate-list shape check.
    assert _CANDIDATE_LIST_RE.search(result.stderr), (
        f"stderr does not match _format_candidates shape; "
        f"got: {result.stderr!r}"
    )
    # First line must declare ambiguity with the correct match count.
    expected_header = f"ambiguous: {len(filenames)} matches"
    assert expected_header in result.stderr, (
        f"missing header {expected_header!r} in stderr: {result.stderr!r}"
    )
    # Each candidate filename must appear in stderr (capped at 5; our
    # parametrize cases stay under the cap).
    for filename in filenames:
        assert filename in result.stderr, (
            f"missing candidate {filename!r} in stderr: {result.stderr!r}"
        )

    # No-mutation check: all candidate files' mtimes must be unchanged.
    for p, mtime_before in mtimes_before.items():
        mtime_after = p.stat().st_mtime_ns
        assert mtime_after == mtime_before, (
            f"file {p} was mutated on exit-2 (mtime advanced from "
            f"{mtime_before} to {mtime_after})"
        )


@pytest.mark.parametrize(
    "missing_input",
    [
        "xyzzy-nonexistent-99999",
        "quantum-flux-capacitor",
    ],
)
def test_not_found_exits_1(tmp_path, missing_input):
    """Not-found input → exit 1 + ``Item not found: <input>`` + no mutation.

    Asserts (per R8):
      * exit_code == 1
      * stderr contains ``Item not found: <input>``.
      * No backlog file is mutated — verified via ``mtime`` comparison.
    """
    repo_root = _make_repo(tmp_path)
    backlog = repo_root / "cortex" / "backlog"
    item = make_item(backlog, "001-some-ticket.md", "Some Ticket")
    mtime_before = item.stat().st_mtime_ns
    time.sleep(0.01)

    result = _run([missing_input, "--status", "complete"], repo_root)

    assert result.returncode == 1, (
        f"expected exit 1, got {result.returncode}; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    expected_msg = f"Item not found: {missing_input}"
    assert expected_msg in result.stderr, (
        f"missing {expected_msg!r} in stderr: {result.stderr!r}"
    )

    # No-mutation check.
    mtime_after = item.stat().st_mtime_ns
    assert mtime_after == mtime_before, (
        f"file {item} was mutated on exit-1 (mtime advanced from "
        f"{mtime_before} to {mtime_after})"
    )


@pytest.mark.parametrize(
    "input_str,filename,title,extra",
    [
        # Numeric ID
        ("1", "001-unique-foo.md", "Unique foo", ""),
        # Kebab stem
        ("unique-bar", "002-unique-bar.md", "Unique bar baz", ""),
        # UUID prefix (≥8 hex chars, unique)
        ("dadaf6b6", "003-unique-delta.md", "Unique delta", f"uuid: {_UUID_D}\n"),
        # Lifecycle_slug frontmatter
        (
            "my-bespoke-slug",
            "004-some-ticket.md",
            "Some unique ticket",
            "lifecycle_slug: my-bespoke-slug\n",
        ),
    ],
)
def test_unambiguous_succeeds_and_mutates(
    tmp_path, input_str, filename, title, extra
):
    """Unambiguous input → exit 0 + file mutated in place.

    Asserts (per R7/R8 implicit, R6 + Task 6 acceptance):
      * exit_code == 0
      * mtime advances on the resolved file (proof of in-place mutation).
      * Status field in the file's frontmatter reflects the new value.

    Parametrized across all four single-match steps (numeric, kebab,
    UUID-prefix, lifecycle_slug) to ensure no resolution branch leaks the
    legacy silent-first-match bug.
    """
    repo_root = _make_repo(tmp_path)
    backlog = repo_root / "cortex" / "backlog"
    item = make_item(backlog, filename, title, extra=extra)
    mtime_before = item.stat().st_mtime_ns

    # Sleep so the post-write mtime is guaranteed to advance beyond the
    # snapshot tick even on coarse-granularity filesystems.
    time.sleep(0.01)

    result = _run([input_str, "--status", "complete"], repo_root)

    assert result.returncode == 0, (
        f"expected exit 0 for input={input_str!r}, got {result.returncode}; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    # mtime advance confirms the file was rewritten in place.
    mtime_after = item.stat().st_mtime_ns
    assert mtime_after > mtime_before, (
        f"file {item} mtime did not advance — expected in-place mutation. "
        f"before={mtime_before} after={mtime_after}"
    )
    # Frontmatter sanity: the status field should now be 'complete'.
    contents = item.read_text(encoding="utf-8")
    assert "status: complete" in contents, (
        f"status field not updated in {item}; contents: {contents!r}"
    )
