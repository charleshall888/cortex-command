#!/usr/bin/env python3
"""Rewrite bare ``/<skill-name>`` references to ``/cortex:<skill-name>``.

Scoped namespace migration tool used by ticket 120 to prepare the cortex-command
source tree for the ``cortex-interactive`` Claude Code plugin. Walks an explicit
include-list of files or directories, rewriting every bare ``/<skill>`` token
(for an allowlist of 14 shipped skill names) to its ``/cortex:<skill>`` form,
subject to a built-in skip list and word-boundary regex.

CLI:
    scripts/migrate-namespace.py --include <path> [--include <path>...]
                                 [--mode dry-run|apply] [--verify]

Modes:
    dry-run (default): Print rewrites that would occur; do not write files.
    apply:             Print rewrites and write changes back to disk.
    --verify:          Run in-memory; exit 0 if no changes would be written
                       (idempotence proof), exit 1 otherwise. Mutually in
                       effect with dry-run (no files are written).

Skip rules (any one skips a file or a match):
    1. Path component equal to any of ``retros``, ``.claude/worktrees``,
       ``research`` (top-level anchor only — ``skills/research/`` is NOT
       skipped because the ``research`` skill ships), or path matches glob
       ``lifecycle/sessions/**``, ``lifecycle/*/events.log``, or is under
       ``backlog/`` (historical tickets).
    2. Match substring contains any of ``://``, ``github.com/``,
       ``gitlab.com/``, ``bitbucket.org/``.
    3. Match is a relative-path segment (the character immediately preceding
       the left delimiter is a path-like character — ``.`` or an alphanumeric,
       indicating forms like ``./commit/hook.sh`` or ``src/pr/util.py``).
    4. File extension not in {``.md``, ``.sh``, ``.py``, ``.json``,
       ``.yaml``, ``.yml``, no-extension-files}.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Hardcoded allowlist of 14 shipped skills.
SKILL_NAMES = (
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
)

# Left delimiters (chars that may precede ``/<skill>``).
# Includes space, backtick, parenthesis, bracket, comma, semicolon, colon,
# double-quote (covers YAML frontmatter quoted forms like ``"/commit"``).
LEFT_DELIMS = r'(?P<lhs>^| |\`|\(|\[|,|;|:|")'

# Right delimiters (chars that may follow ``/<skill>``).
# Adds ``\.`` beyond the spec base set to cover sentence-terminating forms
# like ``/commit.``.
RIGHT_DELIMS = r'(?P<rhs> |$|"|\`|\)|\]|,|;|:|\.)'

ALLOWED_EXTENSIONS = frozenset({".md", ".sh", ".py", ".json", ".yaml", ".yml"})

URL_MARKERS = ("://", "github.com/", "gitlab.com/", "bitbucket.org/")

# Path components that trigger a full-file skip.
# ``research`` is matched only as the TOP-LEVEL component (parts[0]) so that
# ``skills/research/`` — the shipped ``research`` skill — is not skipped.
SKIP_ANY_COMPONENTS = ("retros", "migrate_namespace")


def build_pattern(skill_names: tuple[str, ...]) -> re.Pattern[str]:
    """Return the word-boundary regex that matches any bare ``/<skill>`` token.

    Alternation lists longer names first so ``critical-review`` is not
    partially matched as ``critical``.
    """
    sorted_names = sorted(skill_names, key=len, reverse=True)
    alt = "|".join(re.escape(name) for name in sorted_names)
    return re.compile(rf"{LEFT_DELIMS}/(?P<skill>{alt}){RIGHT_DELIMS}")


PATTERN = build_pattern(SKILL_NAMES)


def _rel_parts_under_roots(path: Path, include_roots: list[Path]) -> list[tuple[str, ...]]:
    """Return all path-part tuples derived from ``path`` relative to each root.

    Supports both directory-include (``path`` is under ``root``) and
    file-include (``path == root`` or ``path`` is ``root``'s file). For a
    file-include, skip rules still apply based on the file's own parts when
    the root is the file itself (e.g., a single fixture passed directly).
    """
    abs_path = path.resolve()
    results: list[tuple[str, ...]] = []
    for root in include_roots:
        root_abs = root.resolve()
        # Treat the root's parent as the base so a file-include like
        # `fixtures/retros/seed.md` exposes `retros/seed.md` as its rel path.
        if root_abs.is_file():
            base = root_abs.parent
        else:
            base = root_abs
        try:
            rel = abs_path.relative_to(base)
        except ValueError:
            continue
        results.append(rel.parts)
    return results


def path_should_skip(path: Path, include_roots: list[Path]) -> bool:
    """Return True when ``path`` is fully skipped by directory-prefix rules.

    The path is inspected relative to each include root (or the root's parent
    if the root is a file). Evaluated rules per rel-path:
      - Any component equals a name in SKIP_ANY_COMPONENTS (``retros``).
      - The first component equals ``research`` (top-level anchor only —
        ``skills/research/`` is therefore NOT skipped).
      - Any two consecutive components equal ``.claude`` then ``worktrees``.
      - The first component equals ``backlog`` (historical tickets).
      - Matches glob ``lifecycle/sessions/**``.
      - Matches glob ``lifecycle/*/events.log``.
    """
    for parts in _rel_parts_under_roots(path, include_roots):
        if not parts:
            continue

        for component in SKIP_ANY_COMPONENTS:
            if component in parts:
                return True

        if parts[0] == "research":
            return True

        if parts[0] == "backlog":
            return True

        for i in range(len(parts) - 1):
            if parts[i] == ".claude" and parts[i + 1] == "worktrees":
                return True

        if len(parts) >= 2 and parts[0] == "lifecycle":
            if parts[1] == "sessions":
                return True
            if len(parts) >= 3 and parts[-1] == "events.log":
                return True

        if parts[-1] == "test_migrate_namespace.py":
            return True

    return False


def extension_allowed(path: Path) -> bool:
    """True if ``path`` has an allowed extension or no extension."""
    suffix = path.suffix
    if suffix == "":
        return True
    return suffix in ALLOWED_EXTENSIONS


def match_is_url(line: str, match: re.Match[str]) -> bool:
    """Return True if ``match`` is inside a URL substring on ``line``."""
    # Conservative: if any URL marker appears on the line AND the marker's
    # span overlaps-or-precedes this match such that the match falls inside
    # the URL token, skip. The easier heuristic — any URL marker followed
    # by ``/<skill>`` contiguously — covers all documented patterns.
    skill = match.group("skill")
    token = f"/{skill}"
    token_start = match.start() + len(match.group("lhs"))
    # Look at a small window to the left of the token for a URL marker.
    left_window = line[:token_start]
    for marker in URL_MARKERS:
        idx = left_window.rfind(marker)
        if idx == -1:
            continue
        # If no whitespace separates marker and token, treat as URL.
        between = left_window[idx + len(marker) :]
        if " " not in between and "\t" not in between:
            return True
    return False


def match_is_relative_path_segment(line: str, match: re.Match[str]) -> bool:
    """Return True if ``match`` is a relative-path segment on ``line``.

    Per spec rule 3: a ``/`` appears in the line before the ``/<skill>``
    token without an intervening space or word boundary. The token's left
    delimiter is one of the enumerated delimiters already; this predicate
    only fires if BEFORE the left-delim we find a ``/`` reached by walking
    backward through non-space, non-delimiter characters.

    Example: ``foo/commit/sub`` — the regex would not match here because
    ``o`` is not a left delimiter, so this predicate is secondary insurance
    for forms like ``./pr`` that slip through via an explicit leading ``.``.
    """
    lhs = match.group("lhs")
    lhs_pos = match.start()
    # Start of the left-delim character (or 0 if lhs is empty/start).
    # Walk backward from just before the left-delim through "connected" chars.
    cursor = lhs_pos if lhs == "" else lhs_pos
    # Move the cursor to just before the lhs character (or at 0 if ^ matched).
    if lhs != "":
        cursor = lhs_pos  # lhs occupies [lhs_pos, lhs_pos+1); previous text is [0, lhs_pos)
    # Walk backwards through characters that are "path-like"
    # (non-space, non-delimiter). If we hit a ``/`` while walking,
    # treat as relative-path segment.
    i = cursor - 1
    path_like = lambda c: c not in (" ", "\t", "`", "(", "[", ",", ";", ":", '"', ")", "]")
    while i >= 0 and path_like(line[i]):
        if line[i] == "/":
            return True
        i -= 1
    return False


def rewrite_line(line: str) -> tuple[str, list[str]]:
    """Rewrite bare ``/<skill>`` references in ``line``.

    Returns (new_line, list_of_rewritten_skill_names). The list is ordered
    in the order rewrites were applied.
    """
    rewrites: list[str] = []

    def repl(match: re.Match[str]) -> str:
        skill = match.group("skill")
        lhs = match.group("lhs")
        rhs = match.group("rhs")
        if match_is_url(line, match):
            return match.group(0)
        if match_is_relative_path_segment(line, match):
            return match.group(0)
        rewrites.append(skill)
        return f"{lhs}/cortex:{skill}{rhs}"

    new_line = PATTERN.sub(repl, line)
    return new_line, rewrites


def iter_candidate_files(include_paths: list[Path]) -> list[Path]:
    """Return the list of candidate files under each include path."""
    files: list[Path] = []
    seen: set[Path] = set()
    for p in include_paths:
        if not p.exists():
            continue
        if p.is_file():
            resolved = p.resolve()
            if resolved not in seen:
                seen.add(resolved)
                files.append(p)
            continue
        for sub in sorted(p.rglob("*")):
            if sub.is_file():
                resolved = sub.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    files.append(sub)
    return files


def process_file(
    path: Path,
    include_roots: list[Path],
    apply_changes: bool,
) -> tuple[int, list[str]]:
    """Rewrite one file, returning (num_rewrites, list_of_stdout_lines).

    When ``apply_changes`` is True, writes back to ``path`` if any rewrites
    occur. Otherwise reports only.
    """
    if not extension_allowed(path):
        return 0, []
    if path_should_skip(path, include_roots):
        return 0, []

    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return 0, []

    out_lines: list[str] = []
    stdout_lines: list[str] = []
    total_rewrites = 0
    changed = False
    # Split preserving line endings so round-trip is exact.
    lines = text.splitlines(keepends=True)
    for lineno, line in enumerate(lines, start=1):
        # Strip trailing newline for regex evaluation, re-append after.
        if line.endswith("\r\n"):
            body, nl = line[:-2], "\r\n"
        elif line.endswith("\n"):
            body, nl = line[:-1], "\n"
        elif line.endswith("\r"):
            body, nl = line[:-1], "\r"
        else:
            body, nl = line, ""
        new_body, rewrites = rewrite_line(body)
        if rewrites:
            changed = True
            total_rewrites += len(rewrites)
            for skill in rewrites:
                stdout_lines.append(
                    f"{path}:{lineno}: /{skill} -> /cortex:{skill}"
                )
        out_lines.append(new_body + nl)

    if changed and apply_changes:
        path.write_text("".join(out_lines), encoding="utf-8")

    return total_rewrites, stdout_lines


def run(
    include_paths: list[Path],
    mode: str,
    verify: bool,
    stdout=sys.stdout,
) -> int:
    """Run the migration. Returns the process exit code.

    - ``mode='dry-run'``: report rewrites; exit 0.
    - ``mode='apply'``: report and write rewrites; exit 0.
    - ``verify=True``: ignore mode; run in-memory; exit 0 iff zero rewrites.
    """
    apply_changes = (mode == "apply") and not verify
    include_roots = [p.resolve() for p in include_paths if p.exists()]

    total_rewrites = 0
    total_files = 0
    for file_path in iter_candidate_files(include_paths):
        n, lines = process_file(file_path, include_roots, apply_changes)
        if n:
            total_rewrites += n
            total_files += 1
            for line in lines:
                print(line, file=stdout)

    print(
        f"Rewrote {total_rewrites} references across {total_files} files",
        file=stdout,
    )

    if verify:
        return 0 if total_rewrites == 0 else 1
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="migrate-namespace",
        description=(
            "Rewrite bare /<skill-name> references to /cortex:<skill-name> "
            "across an explicit include-list of files or directories."
        ),
    )
    parser.add_argument(
        "--include",
        action="append",
        required=True,
        type=Path,
        help="File or directory to process (repeat for multiple paths).",
    )
    parser.add_argument(
        "--mode",
        choices=("dry-run", "apply"),
        default="dry-run",
        help="dry-run (default) reports only; apply writes changes to disk.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help=(
            "Run in-memory; exit 0 if no changes would be written "
            "(idempotence proof); exit 1 if changes would occur."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return run(args.include, args.mode, args.verify)


if __name__ == "__main__":
    sys.exit(main())
