"""ADR citation auditor.

Scans a repo for 4-digit ADR references (``ADR-NNNN``, ``[ADR-NNNN]``,
``ADR NNNN``, ``adr/NNNN[-slug]``) and reports unresolved, slug-mismatch,
duplicate-number, and gap findings as a single JSON object on stdout.
Report-only: exits 0 on every path. Stdlib-only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Iterator

# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------
# Output schema (JSON object on stdout):
#
#   {
#     "corpus_present": <bool>,   # true iff <root>/cortex/adr/ exists AND
#                                 # contains ≥1 conforming NNNN-slug.md file
#     "findings": [
#       {
#         "kind": <str>,          # one of the four values below
#         "file": <str>,          # source file path (relative to root),
#                                 #   absent for duplicate_number and gap findings
#         "token": <str>,         # the matched reference token (for unresolved/
#                                 #   slug_mismatch only)
#         "number": <int>,        # the 4-digit ADR number (all kinds except gap
#                                 #   where "gap_number" is used instead)
#         ...
#       },
#       ...
#     ]
#   }
#
# Finding kinds:
#   "unresolved"       — a referenced ADR number is not present in the corpus
#   "slug_mismatch"    — a path-form reference (adr/NNNN-slug) whose slug does
#                        not match the corpus file for that number
#   "duplicate_number" — two or more corpus files share the same NNNN prefix
#   "gap"              — a number in 1..max(filed) is absent from the corpus
#                        (keyed on file presence, not status: field)
#
# Exit code is 0 regardless of finding count — informational audit only.
#
# Usage:
#     cortex-adr-citation-audit              # cwd as root
#     cortex-adr-citation-audit --root <dir> # alternate root (tests / consumer repos)
#     cortex-adr-citation-audit --help

# ---------------------------------------------------------------------------
# Constants / Token grammar
# ---------------------------------------------------------------------------

# Verbatim from spec Technical Constraints — do not normalize.
# Matches prefix, space, and bracketed forms: ADR-NNNN, [ADR-NNNN], ADR NNNN
_PREFIX_RE = re.compile(
    r"(?<![0-9A-Za-z])\[?ADR[- ](?P<num>[0-9]{4})\]?(?![0-9A-Za-z])"
)

# Matches path forms: adr/NNNN or adr/NNNN-slug
_PATH_RE = re.compile(
    r"(?<![0-9A-Za-z])adr/(?P<num>[0-9]{4})(?:-(?P<slug>[a-z0-9-]+?))?(?=\.md|[^a-z0-9-]|$)"
)

# Corpus filename pattern: ^NNNN-slug.md$ (README.md excluded by non-digit start)
_CORPUS_FILENAME_RE = re.compile(r"^([0-9]{4})-([a-z0-9-]+)\.md$")

# Scan scope: extensions where ADR references demonstrably appear
_SCAN_EXTENSIONS: frozenset[str] = frozenset({".md", ".py"})

# Excluded subtrees (relative to root, as prefix strings for Path.parts matching)
_EXCLUDED_DIR_PARTS: tuple[tuple[str, ...], ...] = (
    (".git",),
    ("tests", "fixtures", "cortex-adr-citation-audit"),
    ("plugins", "cortex-core"),
)


# ---------------------------------------------------------------------------
# Corpus loader
# ---------------------------------------------------------------------------


def load_corpus(adr_dir: Path) -> tuple[dict[int, list[str]], bool]:
    """Scan ``adr_dir`` for conforming ADR files and return (index, corpus_present).

    The index maps ADR number (int) to the list of conforming filenames (stems
    without the .md extension) found under that number.  corpus_present is True
    iff the directory exists AND contains at least one conforming file.
    """
    index: dict[int, list[str]] = {}
    if not adr_dir.is_dir():
        return index, False

    any_found = False
    try:
        entries = sorted(adr_dir.iterdir())
    except OSError:
        return index, False

    for entry in entries:
        if not entry.is_file():
            continue
        m = _CORPUS_FILENAME_RE.match(entry.name)
        if not m:
            continue
        num = int(m.group(1))
        slug = m.group(2)
        stem = f"{m.group(1)}-{slug}"
        index.setdefault(num, []).append(stem)
        any_found = True

    return index, any_found


# ---------------------------------------------------------------------------
# Gap and duplicate detectors
# ---------------------------------------------------------------------------


def detect_duplicates(index: dict[int, list[str]]) -> list[dict]:
    """Return duplicate_number findings for numbers with >1 corpus file."""
    findings: list[dict] = []
    for num, stems in sorted(index.items()):
        if len(stems) > 1:
            findings.append(
                {
                    "kind": "duplicate_number",
                    "number": num,
                    "files": [f"{s}.md" for s in sorted(stems)],
                }
            )
    return findings


def detect_gaps(index: dict[int, list[str]]) -> list[dict]:
    """Return gap findings for missing numbers in 1..max(filed).

    Gap detection keys on file *presence* over the range — a superseded-but-
    present ADR file is NOT a gap.
    """
    if not index:
        return []
    max_num = max(index.keys())
    findings: list[dict] = []
    for n in range(1, max_num + 1):
        if n not in index:
            findings.append(
                {
                    "kind": "gap",
                    "gap_number": n,
                }
            )
    return findings


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


def _is_excluded(path: Path, root: Path) -> bool:
    """Return True if ``path`` falls under an excluded subtree."""
    try:
        rel_parts = path.relative_to(root).parts
    except ValueError:
        return False
    for excl in _EXCLUDED_DIR_PARTS:
        if rel_parts[: len(excl)] == excl:
            return True
    return False


def iter_scan_files(root: Path) -> Iterator[Path]:
    """Yield source text files under ``root`` in scope for ADR reference scanning.

    Excludes ``.git/``, ``tests/fixtures/cortex-adr-citation-audit/``, and
    ``plugins/cortex-core/**``.  Yields ``.md`` and ``.py`` files only.
    """
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        # Prune excluded directories in-place so os.walk doesn't descend.
        dirnames[:] = [
            d
            for d in dirnames
            if not _is_excluded(current / d, root)
        ]
        for fname in filenames:
            fpath = current / fname
            if _is_excluded(fpath, root):
                continue
            if fpath.suffix in _SCAN_EXTENSIONS:
                yield fpath


# ---------------------------------------------------------------------------
# Reference extraction and classification
# ---------------------------------------------------------------------------


def _extract_references(text: str) -> list[tuple[str, int, str | None]]:
    """Return a list of (token, number, slug_or_None) from ``text``.

    Processes both the prefix/bracketed form and the path form.  Slug is None
    for prefix/bracketed/bare-path forms.
    """
    refs: list[tuple[str, int, str | None]] = []

    for m in _PREFIX_RE.finditer(text):
        num = int(m.group("num"))
        refs.append((m.group(0), num, None))

    for m in _PATH_RE.finditer(text):
        num = int(m.group("num"))
        slug = m.group("slug")  # may be None for bare adr/NNNN
        refs.append((m.group(0), num, slug))

    return refs


def classify_reference(
    token: str,
    num: int,
    slug: str | None,
    index: dict[int, list[str]],
) -> dict | None:
    """Classify a single reference against the corpus index.

    Returns a finding dict if the reference is problematic, or None if it
    resolves cleanly.

    - unresolved: number not in index
    - slug_mismatch: path form with a slug that doesn't match any corpus stem for
      that number.  Bare path form (no slug) resolves by prefix only — no
      slug to check.
    """
    if num not in index:
        return {"kind": "unresolved", "token": token, "number": num}

    if slug is not None:
        # Path form with explicit slug: check for exact NNNN-slug match.
        expected_stem = f"{num:04d}-{slug}"
        if expected_stem not in index[num]:
            return {
                "kind": "slug_mismatch",
                "token": token,
                "number": num,
                "expected_stem": expected_stem,
                "corpus_stems": index[num],
            }

    return None


def scan_file(
    fpath: Path,
    root: Path,
    index: dict[int, list[str]],
) -> list[dict]:
    """Scan a single file for ADR references and return per-file findings."""
    try:
        text = fpath.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    findings: list[dict] = []
    rel = str(fpath.relative_to(root))
    for token, num, slug in _extract_references(text):
        finding = classify_reference(token, num, slug, index)
        if finding is not None:
            finding["file"] = rel
            findings.append(finding)

    return findings


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def audit(root: Path) -> dict:
    """Run the four-stage pipeline and return the report dict."""
    adr_dir = root / "cortex" / "adr"
    index, corpus_present = load_corpus(adr_dir)

    findings: list[dict] = []

    # Stage 1: duplicate-number findings (from corpus index alone)
    findings.extend(detect_duplicates(index))

    # Stage 2: gap findings (from corpus index alone)
    findings.extend(detect_gaps(index))

    # Stage 3 + 4: scan source files, resolve and classify each reference
    for fpath in iter_scan_files(root):
        findings.extend(scan_file(fpath, root, index))

    return {
        "corpus_present": corpus_present,
        "findings": findings,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cortex-adr-citation-audit",
        description=(
            "Scan a repo for ADR citation problems (unresolved, slug-mismatch, "
            "duplicate-number, gap) and emit a JSON report on stdout. "
            "Report-only: exits 0 on every path."
        ),
    )
    p.add_argument(
        "--root",
        default=None,
        help="Repository root to audit (defaults to current working directory).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve() if args.root else Path.cwd().resolve()

    report = audit(root)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
