"""Hermetic tests for ``cortex_command.adr_citation_audit`` (R9).

Exercises requirements 2–7 via subprocess with ``--root <tmp_path tree>``.
Modeled on ``tests/test_requirements_parity_audit.py``.

Invocation: ``python3 -m cortex_command.adr_citation_audit --root <dir>``
(NOT the bin/ wrapper path — module invocation exercises the working tree
directly per spec Technical Constraints.)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _invoke(root: Path, extra_args: list[str] | None = None) -> subprocess.CompletedProcess:
    """Run the auditor module against ``root`` and return the completed process."""
    cmd = [sys.executable, "-m", "cortex_command.adr_citation_audit", "--root", str(root)]
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def _audit(root: Path) -> dict:
    """Invoke the auditor and return the parsed JSON report; asserts exit 0."""
    result = _invoke(root)
    assert result.returncode == 0, (
        f"auditor exited {result.returncode}; stderr:\n{result.stderr}"
    )
    return json.loads(result.stdout)


def _write(path: Path, content: str) -> None:
    """Create parent directories and write ``content`` to ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# help: --help exits 0
# ---------------------------------------------------------------------------


def test_help_flag_exits_zero():
    """``--help`` is a CLI contract smoke test; must exit 0."""
    result = subprocess.run(
        [sys.executable, "-m", "cortex_command.adr_citation_audit", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# contract: JSON schema and finding taxonomy
# ---------------------------------------------------------------------------


def test_json_contract_schema(tmp_path: Path):
    """Output has ``corpus_present`` at top level; every finding has a ``kind``
    from the four-value set."""
    # Build a tree with one ADR and one citation to exercise all paths.
    _write(tmp_path / "cortex/adr/0001-foo.md", "# ADR-0001 Foo\n")
    _write(tmp_path / "docs/notes.md", "See ADR-0001 and ADR-9999.\n")

    report = _audit(tmp_path)

    assert isinstance(report, dict), "top-level output must be a dict"
    assert "corpus_present" in report, "top-level key 'corpus_present' missing"
    assert "findings" in report, "top-level key 'findings' missing"
    assert isinstance(report["corpus_present"], bool)
    assert isinstance(report["findings"], list)

    valid_kinds = {"unresolved", "slug_mismatch", "duplicate_number", "gap"}
    for finding in report["findings"]:
        assert "kind" in finding, f"finding missing 'kind': {finding}"
        assert finding["kind"] in valid_kinds, (
            f"unexpected kind {finding['kind']!r}; must be one of {valid_kinds}"
        )


# ---------------------------------------------------------------------------
# req 2: canonical 4-digit reference resolution
# ---------------------------------------------------------------------------


def test_req2_filed_adr_no_finding(tmp_path: Path):
    """``ADR-0001`` resolves cleanly when ``cortex/adr/0001-foo.md`` is filed."""
    _write(tmp_path / "cortex/adr/0001-foo.md", "# ADR-0001 Foo\n")
    _write(tmp_path / "docs/notes.md", "See ADR-0001 for context.\n")

    report = _audit(tmp_path)

    unresolved_for_0001 = [
        f for f in report["findings"]
        if f.get("kind") == "unresolved" and f.get("number") == 1
    ]
    assert unresolved_for_0001 == [], (
        "ADR-0001 should resolve cleanly but produced findings: "
        f"{unresolved_for_0001}"
    )


def test_req2_unfiled_adr_unresolved(tmp_path: Path):
    """``ADR-9999`` with no matching corpus file → ``kind: "unresolved"``."""
    _write(tmp_path / "cortex/adr/0001-foo.md", "# ADR-0001 Foo\n")
    _write(tmp_path / "docs/notes.md", "See ADR-9999 for context.\n")

    report = _audit(tmp_path)

    unresolved = [
        f for f in report["findings"]
        if f.get("kind") == "unresolved" and f.get("number") == 9999
    ]
    assert len(unresolved) >= 1, (
        "ADR-9999 (unfiled) should produce an unresolved finding; "
        f"findings: {report['findings']}"
    )
    assert unresolved[0]["token"] == "ADR-9999"


def test_req2_path_form_slug_mismatch(tmp_path: Path):
    """``adr/0001-wrong-slug`` where the real slug differs → ``kind: "slug_mismatch"``."""
    _write(tmp_path / "cortex/adr/0001-foo.md", "# ADR-0001 Foo\n")
    # Reference path form with wrong slug
    _write(tmp_path / "docs/notes.md", "See adr/0001-wrong-slug for context.\n")

    report = _audit(tmp_path)

    slug_mismatches = [
        f for f in report["findings"]
        if f.get("kind") == "slug_mismatch" and f.get("number") == 1
    ]
    assert len(slug_mismatches) >= 1, (
        "adr/0001-wrong-slug should produce a slug_mismatch finding; "
        f"findings: {report['findings']}"
    )
    finding = slug_mismatches[0]
    assert "expected_stem" in finding
    assert "corpus_stems" in finding
    assert finding["expected_stem"] == "0001-wrong-slug"
    assert "0001-foo" in finding["corpus_stems"]


# ---------------------------------------------------------------------------
# req 3: document-local labels and placeholders are not flagged
# ---------------------------------------------------------------------------


def test_req3_non_four_digit_not_flagged(tmp_path: Path):
    """``ADR-2``, ``ADR-000N``, and ``NNNN-slug`` placeholders produce zero findings."""
    _write(tmp_path / "cortex/adr/0001-foo.md", "# ADR-0001 Foo\n")
    # ADR-2 = 1-digit; ADR-000N = non-numeric; NNNN-slug = template placeholder
    _write(
        tmp_path / "docs/notes.md",
        "See ADR-2, or ADR-000N, or NNNN-slug for context.\n",
    )

    report = _audit(tmp_path)

    # None of these placeholder tokens should appear in findings
    finding_tokens = [f.get("token", "") for f in report["findings"]]
    assert "ADR-2" not in finding_tokens, f"ADR-2 should not be flagged; findings: {report['findings']}"
    assert "ADR-000N" not in finding_tokens, f"ADR-000N should not be flagged; findings: {report['findings']}"
    assert "NNNN-slug" not in finding_tokens, f"NNNN-slug should not be flagged; findings: {report['findings']}"


# ---------------------------------------------------------------------------
# req 4: repo-agnostic within the cortex convention
# ---------------------------------------------------------------------------


def test_req4_synthetic_cortex_convention_tree(tmp_path: Path):
    """With ``--root`` pointing at a synthetic cortex-convention tree (no plugins/,
    no cortex-command layout), ``ADR-0001`` resolves and ``ADR-0002`` is unresolved."""
    # Only cortex/adr/ — no plugins/, no bin/, etc.
    _write(tmp_path / "cortex/adr/0001-foo.md", "# ADR-0001 Foo\n")
    _write(tmp_path / "docs/guide.md", "This doc cites ADR-0001 and ADR-0002.\n")

    report = _audit(tmp_path)

    assert report["corpus_present"] is True

    unresolved_0001 = [
        f for f in report["findings"]
        if f.get("kind") == "unresolved" and f.get("number") == 1
    ]
    assert unresolved_0001 == [], (
        "ADR-0001 is filed; should not be unresolved; "
        f"findings: {report['findings']}"
    )

    unresolved_0002 = [
        f for f in report["findings"]
        if f.get("kind") == "unresolved" and f.get("number") == 2
    ]
    assert len(unresolved_0002) >= 1, (
        "ADR-0002 is not filed; should be unresolved; "
        f"findings: {report['findings']}"
    )


# ---------------------------------------------------------------------------
# req 5: missing-corpus handling
# ---------------------------------------------------------------------------


def test_req5_no_adr_dir_corpus_present_false(tmp_path: Path):
    """When ``cortex/adr/`` is absent, ``corpus_present`` is ``false`` and
    any ADR references are reported as ``unresolved``."""
    # No cortex/adr/ directory at all
    _write(tmp_path / "docs/notes.md", "See ADR-0001 for context.\n")

    report = _audit(tmp_path)

    assert report["corpus_present"] is False, (
        f"corpus_present should be False when no cortex/adr/ exists; got {report['corpus_present']}"
    )

    unresolved = [f for f in report["findings"] if f.get("kind") == "unresolved"]
    assert len(unresolved) >= 1, (
        "ADR-0001 should be unresolved when corpus is absent; "
        f"findings: {report['findings']}"
    )


# ---------------------------------------------------------------------------
# req 6: duplicate-number detection
# ---------------------------------------------------------------------------


def test_req6_duplicate_number_finding(tmp_path: Path):
    """Two corpus files sharing ``0001`` produce ``kind: "duplicate_number"``
    naming both files."""
    _write(tmp_path / "cortex/adr/0001-a.md", "# ADR-0001-a\n")
    _write(tmp_path / "cortex/adr/0001-b.md", "# ADR-0001-b\n")

    report = _audit(tmp_path)

    duplicates = [f for f in report["findings"] if f.get("kind") == "duplicate_number"]
    assert len(duplicates) >= 1, (
        "Expected duplicate_number finding for 0001; "
        f"findings: {report['findings']}"
    )
    dup = duplicates[0]
    assert dup["number"] == 1
    assert "files" in dup
    assert "0001-a.md" in dup["files"]
    assert "0001-b.md" in dup["files"]


# ---------------------------------------------------------------------------
# req 7: gap detection
# ---------------------------------------------------------------------------


def test_req7_gap_missing_number(tmp_path: Path):
    """With 0001, 0002, 0004 filed (0003 absent), a gap finding for 0003 is produced."""
    _write(tmp_path / "cortex/adr/0001-init.md", "# ADR-0001\n")
    _write(tmp_path / "cortex/adr/0002-second.md", "# ADR-0002\n")
    _write(tmp_path / "cortex/adr/0004-fourth.md", "# ADR-0004\n")

    report = _audit(tmp_path)

    gaps = [f for f in report["findings"] if f.get("kind") == "gap"]
    gap_numbers = [f["gap_number"] for f in gaps]
    assert 3 in gap_numbers, (
        "Expected a gap finding for 0003 (absent between 0002 and 0004); "
        f"gap findings: {gaps}"
    )


def test_req7_superseded_present_file_not_a_gap(tmp_path: Path):
    """A corpus file with ``status: superseded`` in its frontmatter is still present
    on disk — it must NOT produce a gap finding for its number."""
    _write(
        tmp_path / "cortex/adr/0001-init.md",
        "---\nstatus: superseded\n---\n# ADR-0001\n",
    )
    _write(tmp_path / "cortex/adr/0002-current.md", "# ADR-0002\n")

    report = _audit(tmp_path)

    gaps = [f for f in report["findings"] if f.get("kind") == "gap"]
    gap_numbers = [f["gap_number"] for f in gaps]
    assert 1 not in gap_numbers, (
        "ADR-0001 file is present (even if superseded) — must not be a gap; "
        f"gap findings: {gaps}"
    )
    assert 2 not in gap_numbers, (
        "ADR-0002 is present — must not be a gap; "
        f"gap findings: {gaps}"
    )
