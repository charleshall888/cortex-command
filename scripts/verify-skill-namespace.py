#!/usr/bin/env python3
"""Verify skill-namespace invocations across the cortex-command tree.

Walks the in-scope file set and finds every reference of the form
`/cortex(-interactive|-overnight-integration)?:<skill>`. Asserts that each
`<plugin>:<skill>` pair matches the canonical mapping derived from the
`justfile` `build-plugin` recipe's case statement:

  cortex-core            -> 14 skills
  cortex-overnight  -> 2 skills

Old-form references (`/cortex:<skill>`) are surfaced as "old-form survivors"
and must either be migrated (Task 8) or listed in the carve-out file.

Stdlib-only. Runs without `uv` or a venv.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Canonical mapping (derived from justfile:423-432)
# ---------------------------------------------------------------------------

CORTEX_INTERACTIVE_SKILLS = {
    "commit",
    "pr",
    "lifecycle",
    "backlog",
    "requirements",
    "research",
    "discovery",
    "refine",
    "retro",
    "dev",
    "fresh",
    "diagnose",
    "evolve",
    "critical-review",
}

CORTEX_OVERNIGHT_INTEGRATION_SKILLS = {
    "overnight",
    "morning-review",
}

# skill -> owning plugin
SKILL_OWNER: dict[str, str] = {}
for s in CORTEX_INTERACTIVE_SKILLS:
    SKILL_OWNER[s] = "cortex-core"
for s in CORTEX_OVERNIGHT_INTEGRATION_SKILLS:
    SKILL_OWNER[s] = "cortex-overnight"

# ---------------------------------------------------------------------------
# Walked file set & exclusions
# ---------------------------------------------------------------------------

INCLUDE_GLOBS: list[str] = [
    "CLAUDE.md",
    "README.md",
    "docs/**/*.md",
    "skills/**/*.md",
    "tests/**/*.py",
    "tests/scenarios/**/*.yaml",
    "hooks/cortex-*.sh",
    "cortex_command/init/templates/**/*.md",
    "plugins/cortex-core/skills/**/*.md",
    "plugins/cortex-overnight/skills/**/*.md",
]

# Path prefixes (relative to root) to exclude.
EXCLUDE_PREFIXES: tuple[str, ...] = (
    "lifecycle/",
    "backlog/",
    "retros/",
    "tests/fixtures/migrate_namespace/",
)

# ---------------------------------------------------------------------------
# Regexes
# ---------------------------------------------------------------------------

# Matches /cortex:<skill>, /cortex-core:<skill>,
# /cortex-overnight:<skill>. Does NOT use a leading word-boundary
# because '/' is a non-word char that already provides separation; we instead
# require either start-of-string or a non-alphanumeric char before the slash.
SKILL_INVOCATION_RE = re.compile(
    r"(?<![A-Za-z0-9_-])"
    r"/(cortex(?:-interactive|-overnight-integration)?)"
    r":([a-z][a-z0-9-]*)"
)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Match:
    file: str  # path relative to root
    line: int  # 1-based
    column: int  # 1-based
    raw: str  # full match text, e.g. "/cortex-core:commit"
    plugin: str  # "cortex" | "cortex-core" | "cortex-overnight"
    skill: str  # skill name


@dataclass(frozen=True)
class Violation:
    match: Match
    expected_plugin: str  # owner per canonical mapping
    kind: str  # "old-form" | "cross-mapping" | "unknown-skill"


# ---------------------------------------------------------------------------
# Carve-outs
# ---------------------------------------------------------------------------


def load_carve_outs(path: Path) -> set[tuple[str, int, str]]:
    """Parse carve-out file. Format: ``<file>:<line> <quoted-string>`` per line.

    Returns a set of (file, line, quoted_string) tuples used to suppress
    matching old-form survivors. Blank lines and ``#`` comments are ignored.
    """
    carve_outs: set[tuple[str, int, str]] = set()
    if not path.exists():
        return carve_outs
    with path.open("r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.rstrip("\n").strip()
            if not line or line.startswith("#"):
                continue
            # Split on first space: "<file>:<line> <rest>"
            try:
                head, rest = line.split(" ", 1)
            except ValueError:
                continue
            if ":" not in head:
                continue
            file_part, _, lineno_str = head.rpartition(":")
            try:
                lineno = int(lineno_str)
            except ValueError:
                continue
            carve_outs.add((file_part, lineno, rest.strip()))
    return carve_outs


def carve_out_matches(violation: Violation, carve_outs: set[tuple[str, int, str]]) -> bool:
    for file_part, lineno, quoted in carve_outs:
        if violation.match.file != file_part or violation.match.line != lineno:
            continue
        # quoted form like '"/cortex:retro ---"' — strip surrounding quotes if present
        needle = quoted
        if len(needle) >= 2 and needle[0] == '"' and needle[-1] == '"':
            needle = needle[1:-1]
        if violation.match.raw in needle or needle.startswith(violation.match.raw):
            return True
    return False


# ---------------------------------------------------------------------------
# Walking & scanning
# ---------------------------------------------------------------------------


def iter_in_scope_files(root: Path) -> list[Path]:
    seen: set[Path] = set()
    for pattern in INCLUDE_GLOBS:
        for p in root.glob(pattern):
            if not p.is_file():
                continue
            rel = p.relative_to(root).as_posix()
            if any(rel.startswith(prefix) for prefix in EXCLUDE_PREFIXES):
                continue
            seen.add(p)
    return sorted(seen)


def scan_text(text: str, file_rel: str) -> list[Match]:
    matches: list[Match] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for m in SKILL_INVOCATION_RE.finditer(line):
            plugin = m.group(1)
            skill = m.group(2)
            matches.append(
                Match(
                    file=file_rel,
                    line=lineno,
                    column=m.start() + 1,
                    raw=m.group(0),
                    plugin=plugin,
                    skill=skill,
                )
            )
    return matches


def classify(match: Match) -> Violation | None:
    """Return a Violation if the match deviates from the canonical mapping.

    - old-form (``/cortex:<skill>``): always a violation (subject to carve-outs).
    - new-form: violation if plugin != expected owner.
    - unknown skill: violation flagged as 'unknown-skill'.
    """
    expected = SKILL_OWNER.get(match.skill)
    if expected is None:
        # Skill not in canonical table at all.
        return Violation(match=match, expected_plugin="<unknown>", kind="unknown-skill")
    if match.plugin == "cortex":
        return Violation(match=match, expected_plugin=expected, kind="old-form")
    if match.plugin != expected:
        return Violation(match=match, expected_plugin=expected, kind="cross-mapping")
    return None


def scan_repo(root: Path) -> tuple[list[Match], list[Violation]]:
    all_matches: list[Match] = []
    violations: list[Violation] = []
    for path in iter_in_scope_files(root):
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for match in scan_text(text, rel):
            all_matches.append(match)
            v = classify(match)
            if v is not None:
                violations.append(v)
    return all_matches, violations


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def format_violation(v: Violation) -> str:
    return (
        f"{v.match.file}:{v.match.line}:{v.match.column}: "
        f"{v.match.raw} — expected /{v.expected_plugin}:{v.match.skill}"
    )


def render_report(violations: list[Violation]) -> str:
    sorted_v = sorted(violations, key=lambda v: (v.match.file, v.match.line, v.match.column))
    lines = [f"violations: {len(sorted_v)}"]
    for v in sorted_v:
        lines.append(format_violation(v))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Self-test (positive control)
# ---------------------------------------------------------------------------


def run_self_test() -> int:
    """Run three in-process fixtures. Exit non-zero if any classification is wrong."""
    failures: list[str] = []

    # 1. Known-good: cortex-core:commit -> VALID (no violation).
    good_text = "Run /cortex-core:commit to save your work"
    good_matches = scan_text(good_text, "<self-test-good>")
    good_violations = [v for v in (classify(m) for m in good_matches) if v is not None]
    if len(good_matches) != 1:
        failures.append(
            f"fixture 1 (known-good): expected 1 match, got {len(good_matches)}: {good_matches!r}"
        )
    elif good_violations:
        failures.append(
            f"fixture 1 (known-good): expected NO violation, got {good_violations!r}"
        )

    # 2. Known-bad cross-mapping: cortex-core:morning-review -> VIOLATION
    #    with expected_plugin = cortex-overnight.
    cross_text = "Run /cortex-core:morning-review tomorrow"
    cross_matches = scan_text(cross_text, "<self-test-cross>")
    cross_violations = [v for v in (classify(m) for m in cross_matches) if v is not None]
    if len(cross_matches) != 1:
        failures.append(
            f"fixture 2 (cross-mapping): expected 1 match, got {len(cross_matches)}"
        )
    elif len(cross_violations) != 1:
        failures.append(
            f"fixture 2 (cross-mapping): expected 1 violation, got {len(cross_violations)}"
        )
    else:
        v = cross_violations[0]
        if v.kind != "cross-mapping":
            failures.append(
                f"fixture 2 (cross-mapping): kind='{v.kind}', expected 'cross-mapping'"
            )
        if v.expected_plugin != "cortex-overnight":
            failures.append(
                "fixture 2 (cross-mapping): expected_plugin="
                f"'{v.expected_plugin}', expected 'cortex-overnight'"
            )

    # 3. Known-bad old-form: /cortex:lifecycle -> VIOLATION classified as old-form.
    old_text = "Run /cortex:lifecycle 122"
    old_matches = scan_text(old_text, "<self-test-old>")
    old_violations = [v for v in (classify(m) for m in old_matches) if v is not None]
    if len(old_matches) != 1:
        failures.append(
            f"fixture 3 (old-form): expected 1 match, got {len(old_matches)}"
        )
    elif len(old_violations) != 1:
        failures.append(
            f"fixture 3 (old-form): expected 1 violation, got {len(old_violations)}"
        )
    else:
        v = old_violations[0]
        if v.kind != "old-form":
            failures.append(
                f"fixture 3 (old-form): kind='{v.kind}', expected 'old-form'"
            )
        if v.expected_plugin != "cortex-core":
            failures.append(
                "fixture 3 (old-form): expected_plugin="
                f"'{v.expected_plugin}', expected 'cortex-core'"
            )

    if failures:
        sys.stderr.write("--self-test FAILED:\n")
        for f in failures:
            sys.stderr.write(f"  - {f}\n")
        return 1
    sys.stdout.write("--self-test PASSED (3/3 fixtures classified correctly)\n")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify skill-namespace invocations across the cortex-command tree.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repo root (defaults to the parent of the scripts/ directory).",
    )
    parser.add_argument(
        "--carve-out-file",
        type=Path,
        default=None,
        help="Path to carve-out file (defaults to scripts/verify-skill-namespace.carve-outs.txt).",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Print a report of all violations (still exits 1 on any violation).",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run in-process positive-control fixtures and exit.",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test()

    root: Path = args.root.resolve()
    carve_path: Path = (
        args.carve_out_file
        if args.carve_out_file is not None
        else root / "scripts" / "verify-skill-namespace.carve-outs.txt"
    )
    carve_outs = load_carve_outs(carve_path)

    _, violations = scan_repo(root)

    # Subtract carve-outs.
    effective: list[Violation] = [
        v for v in violations if not carve_out_matches(v, carve_outs)
    ]

    if args.report:
        sys.stdout.write(render_report(effective) + "\n")
    elif effective:
        # Default mode: print violations one per line on failure.
        sorted_v = sorted(
            effective, key=lambda v: (v.match.file, v.match.line, v.match.column)
        )
        for v in sorted_v:
            sys.stdout.write(format_violation(v) + "\n")

    return 0 if not effective else 1


if __name__ == "__main__":
    raise SystemExit(main())
