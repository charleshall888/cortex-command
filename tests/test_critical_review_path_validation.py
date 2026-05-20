"""Path-validation tests for ``cortex_command.critical_review`` (Req 9).

Covers the Requirement 9 path-validation gate at TWO layers:

  1. Module API — direct calls to ``validate_artifact_path`` / ``prepare_dispatch``:
       (a) direct-symlink whose realpath escapes the root: rejected with the
           realpath endpoint named in the message (Req 9d / post-Phase-1
           gate-policy Req 3)
       (a') ancestor-symlink whose realpath endpoint still lives under the
            root's realpath endpoint: accepted (post-Phase-1 under-root
            scoping; the pre-Phase-1 ``realpath != abspath`` gate would
            false-positive this case)
       (b) out-of-prefix rejection
       (c) feature-narrowing acceptance + rejection
       (d) ``lifecycle_root`` itself rejected (strict prefix)
       (e) valid path returns realpath

  2. CLI subprocess — ``python3 -m cortex_command.critical_review``:
       (f) direct-symlink realpath-escaping-root rejected end-to-end
           (non-zero exit + stderr message naming the realpath endpoint)
       (f') ancestor-symlink-with-realpath-under-root accepted end-to-end
            (exit 0 + JSON payload)
       (g) valid path returns exit 0 + JSON on stdout

Each scenario is its own ``def test_*`` for granular failure reporting.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from cortex_command.critical_review import (
    _default_artifact_roots,
    prepare_dispatch,
    validate_artifact_path,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def lifecycle_layout(tmp_path: Path) -> dict:
    """Build a ``cortex/{lifecycle,research}/`` layout with real files and a symlink.

    Returns a dict with keys:
        lifecycle_root:  tmp_path/'cortex'/'lifecycle'
        feature_dir:     tmp_path/'cortex'/'lifecycle'/'foo'
        good_file:       tmp_path/'cortex'/'lifecycle'/'foo'/'spec.md' (regular file)
        evil_symlink:    tmp_path/'cortex'/'lifecycle'/'foo'/'evil.md' -> /etc/hostname
        research_root:   tmp_path/'cortex'/'research'
        topic_dir:       tmp_path/'cortex'/'research'/'bar'
        research_file:   tmp_path/'cortex'/'research'/'bar'/'research.md' (regular file)
        outside_file:    tmp_path/'outside.md' (regular file, not under either root)
    """
    lifecycle_root = tmp_path / "cortex" / "lifecycle"
    feature_dir = lifecycle_root / "foo"
    feature_dir.mkdir(parents=True)

    good_file = feature_dir / "spec.md"
    good_file.write_text("hello world\n", encoding="utf-8")

    evil_symlink = feature_dir / "evil.md"
    evil_symlink.symlink_to("/etc/hostname")

    research_root = tmp_path / "cortex" / "research"
    topic_dir = research_root / "bar"
    topic_dir.mkdir(parents=True)

    research_file = topic_dir / "research.md"
    research_file.write_text("discovery research\n", encoding="utf-8")

    outside_file = tmp_path / "outside.md"
    outside_file.write_text("not under either root\n", encoding="utf-8")

    return {
        "lifecycle_root": lifecycle_root,
        "feature_dir": feature_dir,
        "good_file": good_file,
        "evil_symlink": evil_symlink,
        "research_root": research_root,
        "topic_dir": topic_dir,
        "research_file": research_file,
        "outside_file": outside_file,
    }


# ---------------------------------------------------------------------------
# (1) Module API tests
# ---------------------------------------------------------------------------


def test_module_api_rejects_realpath_escaping_root(lifecycle_layout: dict) -> None:
    """Req 3/Req 5 (post-Phase-1): a direct symlink whose realpath escapes the
    lifecycle root is rejected. The stderr message must name the realpath
    endpoint (not the literal symlink path) so callers can debug what the path
    actually pointed at after resolution.
    """
    evil = lifecycle_layout["evil_symlink"]
    root = lifecycle_layout["lifecycle_root"]
    with pytest.raises(ValueError) as exc_info:
        validate_artifact_path(str(evil), str(root))
    msg = str(exc_info.value)
    # Contract: the message names the *realpath endpoint*, not the literal
    # symlink path. On macOS ``/etc/hostname`` realpaths to
    # ``/private/etc/hostname``; both endings are acceptable.
    assert "/etc/hostname" in msg or "/private/etc/hostname" in msg, (
        f"Expected realpath endpoint in rejection message; got {msg!r}"
    )


def test_module_api_accepts_ancestor_symlink_if_realpath_under_root(
    tmp_path: Path,
) -> None:
    """Req 3 (post-Phase-1): a candidate path that traverses an *ancestor*
    symlink is accepted as long as the candidate's realpath endpoint still
    lives under the root's realpath endpoint.

    Layout::

        tmp_path/real/cortex/lifecycle/foo/spec.md   (real file)
        tmp_path/via_link -> tmp_path/real           (ancestor symlink)

    Validation is invoked with both the candidate and the root expressed
    through the ancestor symlink (``tmp_path/via_link/...``). Under the
    pre-Phase-1 ``realpath != abspath`` gate this would false-positive as
    a symlinked path; under the under-root scoping replacement it is
    accepted because both realpaths resolve under ``tmp_path/real``.
    """
    real_dir = tmp_path / "real"
    feature_dir = real_dir / "cortex" / "lifecycle" / "foo"
    feature_dir.mkdir(parents=True)
    spec = feature_dir / "spec.md"
    spec.write_text("hello via ancestor symlink\n", encoding="utf-8")

    via_link = tmp_path / "via_link"
    via_link.symlink_to(real_dir, target_is_directory=True)

    # Both candidate and root traverse the ancestor symlink. The realpath
    # endpoints both land under ``tmp_path/real/cortex/lifecycle``, so the
    # under-root scoping check accepts.
    candidate_via_link = via_link / "cortex" / "lifecycle" / "foo" / "spec.md"
    root_via_link = via_link / "cortex" / "lifecycle"

    resolved = validate_artifact_path(str(candidate_via_link), str(root_via_link))
    # Return value is the realpath (resolved through the ancestor symlink).
    assert resolved == str(spec.resolve())
    assert isinstance(resolved, str)


def test_module_api_rejects_path_outside_lifecycle_root(lifecycle_layout: dict) -> None:
    """Req 9b: path outside lifecycle/ is rejected; message names the allowed prefix."""
    outside = lifecycle_layout["outside_file"]
    root = lifecycle_layout["lifecycle_root"]
    with pytest.raises(ValueError) as exc_info:
        validate_artifact_path(str(outside), str(root))
    msg = str(exc_info.value)
    # Message must reference the allowed prefix (lifecycle_root) and/or the offending path.
    assert str(root) in msg or "lifecycle" in msg


def test_module_api_accepts_path_under_matching_feature(lifecycle_layout: dict) -> None:
    """Req 9b auto-trigger: feature='foo' accepted when path is under cortex/lifecycle/foo/."""
    good = lifecycle_layout["good_file"]
    root = lifecycle_layout["lifecycle_root"]
    resolved = validate_artifact_path(str(good), str(root), feature="foo")
    assert resolved == str(good.resolve())


def test_module_api_rejects_path_under_mismatched_feature(lifecycle_layout: dict) -> None:
    """Req 9b auto-trigger: feature='bar' rejected when path is under cortex/lifecycle/foo/."""
    good = lifecycle_layout["good_file"]
    root = lifecycle_layout["lifecycle_root"]
    with pytest.raises(ValueError) as exc_info:
        validate_artifact_path(str(good), str(root), feature="bar")
    msg = str(exc_info.value)
    assert "bar" in msg


def test_module_api_rejects_path_equal_to_lifecycle_root(lifecycle_layout: dict) -> None:
    """Req 9b strict prefix: candidate == lifecycle_root is rejected."""
    root = lifecycle_layout["lifecycle_root"]
    with pytest.raises(ValueError) as exc_info:
        validate_artifact_path(str(root), str(root))
    msg = str(exc_info.value)
    assert "strictly under" in msg or str(root) in msg


def test_module_api_valid_path_returns_realpath(lifecycle_layout: dict) -> None:
    """Valid path under lifecycle/ returns its realpath (str)."""
    good = lifecycle_layout["good_file"]
    root = lifecycle_layout["lifecycle_root"]
    resolved = validate_artifact_path(str(good), str(root))
    assert resolved == str(good.resolve())
    # The return is a string (not Path).
    assert isinstance(resolved, str)


def test_module_api_prepare_dispatch_returns_sha_and_path(lifecycle_layout: dict) -> None:
    """``prepare_dispatch`` fuses validation + SHA-256 in one call."""
    good = lifecycle_layout["good_file"]
    root = lifecycle_layout["lifecycle_root"]
    result = prepare_dispatch(str(good), str(root), feature="foo")
    expected_sha = hashlib.sha256(good.read_bytes()).hexdigest()
    assert result == {
        "resolved_path": str(good.resolve()),
        "sha256": expected_sha,
    }


# ---------------------------------------------------------------------------
# (2) CLI subprocess tests
# ---------------------------------------------------------------------------


def _run_cli(lifecycle_root: Path, *args: str) -> subprocess.CompletedProcess:
    """Invoke ``python3 -m cortex_command.critical_review`` with --lifecycle-root."""
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "cortex_command.critical_review",
            "--lifecycle-root",
            str(lifecycle_root),
            *args,
        ],
        capture_output=True,
        text=True,
    )


def test_cli_rejects_realpath_escaping_root(lifecycle_layout: dict) -> None:
    """Req 3/Req 5 (post-Phase-1) end-to-end: CLI rejects a direct-symlink
    candidate whose realpath escapes the lifecycle root. The stderr message
    must name the realpath endpoint for caller-debuggability.
    """
    evil = lifecycle_layout["evil_symlink"]
    root = lifecycle_layout["lifecycle_root"]
    result = _run_cli(root, "prepare-dispatch", str(evil))
    assert result.returncode != 0, (
        f"Expected non-zero exit; got {result.returncode}. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    stderr_lower = result.stderr.lower()
    # Stderr must carry the rejection diagnostic.
    assert (
        "symlink" in stderr_lower
        or "path validation failed" in stderr_lower
    ), f"Expected rejection message in stderr; got {result.stderr!r}"
    # Stderr must name the *realpath endpoint*, not just the literal
    # symlink path — this is the caller-debuggability contract.
    assert (
        "/etc/hostname" in result.stderr
        or "/private/etc/hostname" in result.stderr
    ), f"Expected realpath endpoint in stderr; got {result.stderr!r}"


def test_cli_accepts_ancestor_symlink_if_realpath_under_root(
    tmp_path: Path,
) -> None:
    """Req 3 (post-Phase-1) end-to-end: CLI accepts a candidate whose path
    traverses an *ancestor* symlink, as long as the realpath endpoint still
    lives under the root's realpath endpoint.

    See ``test_module_api_accepts_ancestor_symlink_if_realpath_under_root``
    for the layout rationale.
    """
    real_dir = tmp_path / "real"
    feature_dir = real_dir / "cortex" / "lifecycle" / "foo"
    feature_dir.mkdir(parents=True)
    spec = feature_dir / "spec.md"
    spec.write_text("hello via ancestor symlink (cli)\n", encoding="utf-8")

    via_link = tmp_path / "via_link"
    via_link.symlink_to(real_dir, target_is_directory=True)

    candidate_via_link = via_link / "cortex" / "lifecycle" / "foo" / "spec.md"
    root_via_link = via_link / "cortex" / "lifecycle"

    result = _run_cli(root_via_link, "prepare-dispatch", str(candidate_via_link))
    assert result.returncode == 0, (
        f"Expected exit 0; got {result.returncode}. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    payload = json.loads(result.stdout)
    assert payload["resolved_path"] == str(spec.resolve())
    assert payload["sha256"] == hashlib.sha256(spec.read_bytes()).hexdigest()


def test_cli_accepts_valid_path_and_emits_json(lifecycle_layout: dict) -> None:
    """CLI returns exit 0 + JSON {resolved_path, sha256} for a valid path."""
    good = lifecycle_layout["good_file"]
    root = lifecycle_layout["lifecycle_root"]
    result = _run_cli(root, "prepare-dispatch", str(good))
    assert result.returncode == 0, (
        f"Expected exit 0; got {result.returncode}. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    payload = json.loads(result.stdout)
    assert "resolved_path" in payload
    assert "sha256" in payload
    assert payload["resolved_path"] == str(good.resolve())
    assert payload["sha256"] == hashlib.sha256(good.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# (3) Multi-root tests — discovery research artifacts (cortex/research/<topic>/)
# ---------------------------------------------------------------------------


def test_multi_root_accepts_lifecycle_path(lifecycle_layout: dict) -> None:
    """Multi-root: path under cortex/lifecycle/ accepted when both roots passed."""
    good = lifecycle_layout["good_file"]
    roots = [
        str(lifecycle_layout["lifecycle_root"]),
        str(lifecycle_layout["research_root"]),
    ]
    resolved = validate_artifact_path(str(good), roots)
    assert resolved == str(good.resolve())


def test_multi_root_accepts_research_path(lifecycle_layout: dict) -> None:
    """Multi-root: path under cortex/research/ accepted when both roots passed."""
    research_file = lifecycle_layout["research_file"]
    roots = [
        str(lifecycle_layout["lifecycle_root"]),
        str(lifecycle_layout["research_root"]),
    ]
    resolved = validate_artifact_path(str(research_file), roots)
    assert resolved == str(research_file.resolve())


def test_multi_root_rejects_path_outside_all_roots(lifecycle_layout: dict) -> None:
    """Multi-root: path under neither root is rejected; message lists both roots."""
    outside = lifecycle_layout["outside_file"]
    roots = [
        str(lifecycle_layout["lifecycle_root"]),
        str(lifecycle_layout["research_root"]),
    ]
    with pytest.raises(ValueError) as exc_info:
        validate_artifact_path(str(outside), roots)
    msg = str(exc_info.value)
    # Message must surface that multiple roots were tried.
    assert "any of" in msg
    assert str(lifecycle_layout["lifecycle_root"]) in msg
    assert str(lifecycle_layout["research_root"]) in msg


def test_multi_root_prepare_dispatch_research_path(lifecycle_layout: dict) -> None:
    """prepare_dispatch returns realpath + SHA for a path under the research root."""
    research_file = lifecycle_layout["research_file"]
    roots = (
        str(lifecycle_layout["lifecycle_root"]),
        str(lifecycle_layout["research_root"]),
    )
    result = prepare_dispatch(str(research_file), roots)
    assert result == {
        "resolved_path": str(research_file.resolve()),
        "sha256": hashlib.sha256(research_file.read_bytes()).hexdigest(),
    }


def test_multi_root_rejects_empty_root_sequence(lifecycle_layout: dict) -> None:
    """Passing an empty sequence of roots raises ValueError with a clear message."""
    good = lifecycle_layout["good_file"]
    with pytest.raises(ValueError) as exc_info:
        validate_artifact_path(str(good), [])
    assert "no artifact roots" in str(exc_info.value).lower()


def test_default_artifact_roots_returns_lifecycle_and_research(tmp_path: Path) -> None:
    """``_default_artifact_roots`` returns (cortex/lifecycle, cortex/research) under git toplevel."""
    roots = _default_artifact_roots()
    assert len(roots) == 2
    assert roots[0].endswith("/cortex/lifecycle")
    assert roots[1].endswith("/cortex/research")


# ---------------------------------------------------------------------------
# (4) Ad-hoc snapshot + candidate-string boundary tests (Phase 2, Fix 3)
# ---------------------------------------------------------------------------


def test_module_api_adhoc_snapshots_file_under_cortex_adhoc(
    lifecycle_layout: dict,
) -> None:
    """Req 6 (Phase 2): ``--allow-adhoc`` snapshots a file outside both roots
    into ``cortex/_adhoc/<sha[:2]>/<sha[2:]>/<basename>`` and returns a dict
    with ``source_path`` (the original candidate path) and ``snapshot_sha``
    (the full hex SHA-256 of the file content).

    The ad-hoc snapshot landing directory is a peer of ``cortex/lifecycle/``
    so the repo root is derived from the lifecycle root's ``.parent.parent``.
    """
    outside = lifecycle_layout["outside_file"]
    roots = [
        str(lifecycle_layout["lifecycle_root"]),
        str(lifecycle_layout["research_root"]),
    ]
    expected_sha = hashlib.sha256(outside.read_bytes()).hexdigest()
    expected_snapshot = (
        lifecycle_layout["lifecycle_root"].parent
        / "_adhoc"
        / expected_sha[:2]
        / expected_sha[2:]
        / outside.name
    )

    result = validate_artifact_path(str(outside), roots, allow_adhoc=True)

    # The result is a dict (extended shape on the ad-hoc path).
    assert isinstance(result, dict), (
        f"Expected dict result for ad-hoc snapshot; got {type(result).__name__}"
    )
    # (a) snapshot exists at the expected fanout path
    assert expected_snapshot.exists(), (
        f"Snapshot not found at expected path {expected_snapshot}"
    )
    # (b) snapshot bytes match the original
    assert expected_snapshot.read_bytes() == outside.read_bytes()
    # (c) returned validation result carries source_path and snapshot_sha
    assert result["source_path"] == str(outside)
    assert result["snapshot_sha"] == expected_sha
    assert result["resolved_path"] == str(expected_snapshot)


def test_module_api_rejects_nul_byte_in_path(lifecycle_layout: dict) -> None:
    """Req 7 / Edge Case (Phase 2): NUL byte in the candidate string raises
    ``ValueError`` at the validation boundary, before any realpath or
    snapshot work. NUL is the one byte POSIX paths cannot legally contain.
    """
    roots = [str(lifecycle_layout["lifecycle_root"])]
    bad = "/tmp/some\x00path/file.md"
    with pytest.raises(ValueError) as exc_info:
        validate_artifact_path(bad, roots, allow_adhoc=True)
    msg = str(exc_info.value).lower()
    assert "nul" in msg or "null" in msg, (
        f"Expected NUL-byte rejection diagnostic in error message; got {exc_info.value!r}"
    )


def test_module_api_rejects_surrogate_codepoint_in_path(
    lifecycle_layout: dict,
) -> None:
    """Req 7 / Edge Case (Phase 2): surrogate code points (from
    ``surrogateescape``-decoded argv carrying invalid UTF-8 bytes) raise
    ``ValueError`` at the validation boundary. Detected via
    ``candidate.encode('utf-8', errors='strict')`` raising
    ``UnicodeEncodeError``.
    """
    roots = [str(lifecycle_layout["lifecycle_root"])]
    # Construct a string containing a lone surrogate (U+DCFF is in the
    # low-surrogate range typically produced by surrogateescape decoding
    # of invalid UTF-8 byte 0xFF).
    bad = "/tmp/some\udcffpath/file.md"
    with pytest.raises(ValueError) as exc_info:
        validate_artifact_path(bad, roots, allow_adhoc=True)
    msg = str(exc_info.value).lower()
    assert "surrogate" in msg, (
        f"Expected surrogate-codepoint rejection diagnostic; got {exc_info.value!r}"
    )


def test_module_api_accepts_newline_in_path(tmp_path: Path) -> None:
    """Edge Case (Phase 2): newlines in path are LEGAL POSIX and accepted
    at validation. They are preserved verbatim in ``source_path`` for
    later JSON-escaping by ``json.dumps`` on events.log write.

    Constructs a real file at a path containing a newline (POSIX permits
    this), calls validation with ``--allow-adhoc``, and asserts the
    snapshot succeeds and ``source_path`` preserves the newline byte.
    """
    # Build cortex/{lifecycle,research}/ scaffolding so the ad-hoc snapshot
    # has a place to land (cortex/_adhoc/ is derived from the lifecycle
    # root's grandparent).
    lifecycle_root = tmp_path / "cortex" / "lifecycle"
    lifecycle_root.mkdir(parents=True)
    research_root = tmp_path / "cortex" / "research"
    research_root.mkdir(parents=True)

    # Create a real file at a path containing a newline. POSIX permits
    # this; only NUL is forbidden in a path.
    newline_dir = tmp_path / "weird\nname"
    newline_dir.mkdir()
    src = newline_dir / "input.md"
    src.write_text("newline in path is legal\n", encoding="utf-8")

    roots = [str(lifecycle_root), str(research_root)]
    result = validate_artifact_path(str(src), roots, allow_adhoc=True)

    assert isinstance(result, dict)
    # The original candidate string (preserved verbatim, including newline)
    # round-trips through source_path.
    assert "\n" in result["source_path"], (
        f"Expected newline preserved in source_path; got {result['source_path']!r}"
    )
    assert result["source_path"] == str(src)
    # The snapshot's bytes match the original.
    snapshot = Path(result["resolved_path"])
    assert snapshot.exists()
    assert snapshot.read_bytes() == src.read_bytes()
    # The snapshot_sha is the full hex SHA-256 of the content.
    assert result["snapshot_sha"] == hashlib.sha256(src.read_bytes()).hexdigest()
