"""Bare-Python cortex_command import scanner (L201).

Scans skill prose and related corpus files for bare-Python ``cortex_command``
imports -- static ``import``/``from import`` forms and dynamic
``importlib.util.find_spec``/``importlib.import_module``/``__import__``
forms -- inside Python-source regions defined by spec R5:

  Rule 1: labeled fences (info-string ``python|python3|py``)
  Rule 2: ``python3 -c "<body>"`` invocation bodies (anywhere in file)
  Rule 3: ``python3 <<MARKER ... MARKER`` heredoc bodies
  Rule 4: Rule 2/3 invocations inside unlabeled fences are scanned

The dynamic-import alternatives are required because the §1 probe being
removed uses ``importlib.util.find_spec('cortex_command')``; without these,
a verbatim regression of the removed probe would pass clean.

Inline-code spans (``\\`...\\```) are stripped before regex application (Rule 5
exclusion from spec R5) -- narrative mentions like
``\\`python3 -c "import cortex_command"\\``` do not flag.

Sentinel: ``<!-- bare-python-lint:ignore-next -->`` suppresses one
python-source region per sentinel.  The ``prev_nonblank`` pattern from
``contract.py:553`` is used -- intervening blank lines between sentinel and
region do not defeat suppression.

Error code: L201  bare-Python cortex_command import in skill prose -- use
                  console-script invocation instead.

Three modes:
  --staged  Pre-commit path: scan staged blobs matching the corpus globs.
  --audit   Scan the working-tree corpus.
  (neither) If --root is given without a mode, default to audit. If no
            args, print usage to stderr and exit 2.

Exit codes: 0 (clean), 1 (violations), 2 (usage error).

Stdlib-only.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from ._globs import matches_any_glob


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Corpus globs -- mirrors contract.py's _SCAN_GLOBS.
_SCAN_GLOBS: tuple[str, ...] = (
    "skills/**/*.md",
    "hooks/**",
    "justfile",
    "docs/**/*.md",
    "tests/**/*.md",
    "CLAUDE.md",
    "cortex/requirements/**/*.md",
)

# Hard exclusion prefixes (relative path strings).
_HARD_EXCLUDE_PREFIXES: tuple[str, ...] = (
    "cortex/lifecycle/archive/",
    "cortex/research/archive/",
    # Intentional violation fixtures; scanning them against the live corpus
    # would always produce false failures.
    "tests/fixtures/bare_python_import/",
    # Sibling lint fixtures must not cross-trigger.
    "tests/fixtures/contract/",
)

# Fence delimiter regex -- backtick or tilde runs of >=3.
_FENCE_RE = re.compile(r"^(`{3,}|~{3,})(.*)")

# Info-string regex for labeled python fences.
_PYTHON_INFO_RE = re.compile(r"^(python|python3|py)$", re.IGNORECASE)

# Heredoc opener: python3 - <<MARKER or python3 <<MARKER
_HEREDOC_RE = re.compile(
    r"^\s*python3?(?:\s+-)?\s+<<(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1\s*$"
)

# python3 -c invocation opener.  Matches both double-quoted and single-quoted bodies.
# Match ends just before the opening quote character.
# The negative lookbehind ``(?<!run )`` excludes ``uv run python -c`` invocations
# (tool-runner context) which are legitimate in justfile/CI scripts and should not
# be treated as bare-Python cortex_command import sites.
_PYTHON_C_RE = re.compile(r"(?<!run )\bpython3?\s+-c\s+(['\"])")

# Import regex applied to python-source region content.
# Covers static import/from-import and dynamic find_spec/import_module/__import__.
_IMPORT_RE = re.compile(
    r"\b(?:"
    r"import\s+cortex_command"
    r"|from\s+cortex_command(?:\.[a-z_][a-z0-9_]*)*\s+import"
    r"|importlib\.util\.find_spec\(['\"]cortex_command"
    r"|importlib\.import_module\(['\"]cortex_command"
    r"|__import__\(['\"]cortex_command"
    r")\b"
)

# Sentinel literal.
_SENTINEL_RE = re.compile(r"<!--\s*bare-python-lint:ignore-next\s*-->")

# Inline code span removal -- balanced single-backtick spans.
_INLINE_CODE_RE = re.compile(r"`[^`]*`")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    col: int
    code: str
    message: str

    def format_text(self) -> str:
        return f"{self.path}:{self.line}:{self.col}: {self.code} {self.message}"

    def format_json_dict(self) -> dict:
        return {
            "path": str(self.path),
            "line": self.line,
            "col": self.col,
            "code": self.code,
            "message": self.message,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strip_inline_backticks(line: str) -> str:
    """Remove balanced single-backtick spans from *line* (Rule 5 exclusion)."""
    return _INLINE_CODE_RE.sub(" ", line)


def _is_sentinel(line: str | None) -> bool:
    """Return True if *line* matches the bare-python-lint:ignore-next sentinel."""
    if line is None:
        return False
    return bool(_SENTINEL_RE.search(line))


def _extract_quoted_body(text: str, start: int) -> tuple[str, int] | None:
    """Extract the shell-quoted body of a ``python3 -c`` invocation.

    *start* is the index of the opening quote character in *text*.
    Returns ``(body, end_index)`` where ``end_index`` is the index immediately
    after the closing quote, or ``None`` if the closing quote is absent.

    Handles embedded newlines (multi-line quoted bodies), backslash-escaped
    quotes in double-quoted strings, and single-quoted strings (all content
    literal, no escapes).
    """
    quote = text[start]
    pos = start + 1
    body_parts: list[str] = []
    while pos < len(text):
        ch = text[pos]
        if quote == '"' and ch == "\\" and pos + 1 < len(text):
            next_ch = text[pos + 1]
            if next_ch == '"':
                body_parts.append('"')
                pos += 2
                continue
            elif next_ch == "\n":
                # Backslash-newline continuation -- include the newline in body.
                body_parts.append("\n")
                pos += 2
                continue
            else:
                body_parts.append(ch)
                pos += 1
                continue
        if ch == quote:
            return "".join(body_parts), pos + 1
        body_parts.append(ch)
        pos += 1
    return None


def _char_to_lineno(text: str, char_offset: int) -> int:
    """Return the 1-based line number of the character at *char_offset* in *text*."""
    return text[:char_offset].count("\n") + 1


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


def scan_text(text: str, path: Path) -> list[Violation]:
    """Scan *text* for L201 violations.

    Python-source regions are extracted per R5 Rules 1-4; the import regex
    is applied to each region.  Sentinel suppression is applied per the
    ``prev_nonblank`` pattern.

    Strategy:
    - Phase A (Rule 2 -- python3 -c invocations): scan the full text
      (with inline-code spans stripped per-line) for python3 -c bodies.
      These are scanned regardless of fence context (Rule 2 fires anywhere).
      Sentinel suppression: the line immediately before the python3 -c line
      (most recent non-blank, per prev_nonblank logic) acts as the suppressor.
    - Phase B (Rules 1, 3, 4): line-by-line state machine for labeled fences
      (Rule 1), heredocs (Rule 3), and unlabeled fences (Rule 4 -- only Rule 3
      heredocs inside them are scanned in phase B; Rule 2 is already covered
      by phase A).
    """
    violations: list[Violation] = []
    lines = text.splitlines()

    # Build a per-line stripped version for inline-code-span exclusion.
    stripped_lines = [_strip_inline_backticks(ln) for ln in lines]
    # Rejoin for multi-line python3 -c body extraction.
    stripped_text = "\n".join(stripped_lines)

    # Build a map from line number -> prev_nonblank line, for sentinel checks.
    # We need this for phase A to know the sentinel preceding a python3 -c line.
    prev_nonblank_at: dict[int, str | None] = {}
    prev_nb: str | None = None
    for idx, raw in enumerate(lines, start=1):
        prev_nonblank_at[idx] = prev_nb
        if raw.strip():
            prev_nb = raw

    # ---------------------------------------------------------------------- #
    # Phase A: Rule 2 -- python3 -c invocations anywhere in text             #
    # ---------------------------------------------------------------------- #

    for m in _PYTHON_C_RE.finditer(stripped_text):
        # m.end() - 1 points to the opening quote character.
        quote_start = m.end() - 1
        result = _extract_quoted_body(stripped_text, quote_start)
        if result is None:
            continue
        body, _end = result
        lineno = _char_to_lineno(stripped_text, m.start())
        # Sentinel: check the prev_nonblank at this line.
        sentinel_line = prev_nonblank_at.get(lineno)
        if _is_sentinel(sentinel_line):
            continue
        # Scan the body for imports.
        for im in _IMPORT_RE.finditer(body):
            violations.append(Violation(
                path=path,
                line=lineno,
                col=im.start() + 1,
                code="L201",
                message=(
                    "bare-Python cortex_command import in skill prose"
                    " -- use console-script invocation instead"
                ),
            ))

    # ---------------------------------------------------------------------- #
    # Phase B: Rules 1, 3, 4 -- fence/heredoc state machine                  #
    # ---------------------------------------------------------------------- #

    in_labeled_fence = False      # Rule 1: inside a python-labeled fence
    in_unlabeled_fence = False    # Rule 4: inside an unlabeled fence
    in_heredoc = False            # Rule 3: inside a heredoc
    heredoc_marker: str | None = None
    fence_delim: str | None = None

    prev_nonblank: str | None = None
    region_suppressed = False

    def _scan_python_source(content: str, lineno: int, suppressed: bool) -> None:
        if suppressed:
            return
        for im in _IMPORT_RE.finditer(content):
            violations.append(Violation(
                path=path,
                line=lineno,
                col=im.start() + 1,
                code="L201",
                message=(
                    "bare-Python cortex_command import in skill prose"
                    " -- use console-script invocation instead"
                ),
            ))

    for idx, raw in enumerate(lines, start=1):

        # ------------------------------------------------------------------ #
        # Heredoc body                                                         #
        # ------------------------------------------------------------------ #
        if in_heredoc:
            stripped = raw.strip()
            if stripped == heredoc_marker:
                in_heredoc = False
                heredoc_marker = None
            else:
                # Scan raw heredoc content (not inline-stripped -- heredoc is
                # an actual python source region, not markdown).
                _scan_python_source(raw, idx, region_suppressed)
            if raw.strip():
                prev_nonblank = raw
            continue

        # ------------------------------------------------------------------ #
        # Fence delimiter detection                                            #
        # ------------------------------------------------------------------ #
        m_fence = _FENCE_RE.match(raw)
        if m_fence:
            delim_chars = m_fence.group(1)
            info_string = m_fence.group(2).strip()

            if in_labeled_fence or in_unlabeled_fence:
                # Potential closing fence.
                opener_char = fence_delim[0]  # type: ignore[index]
                opener_len = len(fence_delim)  # type: ignore[arg-type]
                raw_stripped = raw.rstrip()
                if (
                    raw_stripped
                    and all(c == opener_char for c in raw_stripped)
                    and len(raw_stripped) >= opener_len
                ):
                    in_labeled_fence = False
                    in_unlabeled_fence = False
                    fence_delim = None
            else:
                # Opening fence.
                fence_delim = delim_chars[0] * len(delim_chars)
                if _PYTHON_INFO_RE.match(info_string):
                    in_labeled_fence = True
                    region_suppressed = _is_sentinel(prev_nonblank)
                else:
                    in_unlabeled_fence = True
                    region_suppressed = _is_sentinel(prev_nonblank)

            if raw.strip():
                prev_nonblank = raw
            continue

        # ------------------------------------------------------------------ #
        # Inside labeled python fence (Rule 1)                                #
        # ------------------------------------------------------------------ #
        if in_labeled_fence:
            # Scan the raw line (python source -- Rule 1).
            # Note: Rule 2 python3 -c inside labeled fences is already handled
            # by Phase A above. Here we scan the raw python source lines.
            _scan_python_source(raw, idx, region_suppressed)
            if raw.strip():
                prev_nonblank = raw
            continue

        # ------------------------------------------------------------------ #
        # Inside unlabeled fence (Rule 4)                                     #
        # ------------------------------------------------------------------ #
        if in_unlabeled_fence:
            # Rule 2 python3 -c inside unlabeled fences is handled by Phase A.
            # Rule 3: heredoc opener inside unlabeled fence.
            m_heredoc = _HEREDOC_RE.match(raw)
            if m_heredoc:
                in_heredoc = True
                heredoc_marker = m_heredoc.group(2)
                region_suppressed = _is_sentinel(prev_nonblank)

            if raw.strip():
                prev_nonblank = raw
            continue

        # ------------------------------------------------------------------ #
        # Outside fences -- Rule 3 heredoc opener in prose                   #
        # ------------------------------------------------------------------ #
        m_heredoc = _HEREDOC_RE.match(raw)
        if m_heredoc:
            in_heredoc = True
            heredoc_marker = m_heredoc.group(2)
            region_suppressed = _is_sentinel(prev_nonblank)

        if raw.strip():
            prev_nonblank = raw

    return violations


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------


def _is_hard_excluded(rel: str) -> bool:
    """Return True if *rel* (relative path string) is hard-excluded."""
    for prefix in _HARD_EXCLUDE_PREFIXES:
        if rel.startswith(prefix):
            return True
    return False


def _expand_glob(root: Path, glob: str) -> list[Path]:
    if "*" in glob:
        return sorted(p for p in root.glob(glob) if p.is_file())
    p = root / glob
    return [p] if p.is_file() else []


def discover_files(roots: list[Path], staged: bool = False) -> list[Path]:
    """Discover corpus files under *roots*.

    When *staged* is True, the first element of *roots* is used as the
    repository root and only git-staged blobs matching the corpus globs
    are returned.  Otherwise, all matching files under each root are
    returned.
    """
    if staged:
        root = roots[0] if roots else Path.cwd()
        rel_paths = _staged_paths(root)
        out: list[Path] = []
        for rel in rel_paths:
            if _is_hard_excluded(rel):
                continue
            p = root / rel
            if p.is_file():
                out.append(p)
        return out

    seen: set[Path] = set()
    out2: list[Path] = []
    for root in roots:
        for glob in _SCAN_GLOBS:
            for p in _expand_glob(root, glob):
                rp = p.resolve()
                try:
                    rel = str(p.relative_to(root))
                except ValueError:
                    rel = str(p)
                if _is_hard_excluded(rel):
                    continue
                if rp in seen:
                    continue
                seen.add(rp)
                out2.append(p)
    return sorted(out2, key=str)


def _matches_scan_glob(rel_path: str) -> bool:
    """Return True if *rel_path* matches any of the corpus globs.

    Delegates to the shared ``**``=zero-or-more-segments matcher. This replaces
    the former 3.13-only ``PurePath`` full-match call, which raised
    ``AttributeError`` on Python 3.12 (the floor of ``requires-python``) — the
    shared matcher is stdlib-only and behaves identically across versions.
    """
    return matches_any_glob(rel_path, _SCAN_GLOBS)


def _staged_paths(root: Path) -> list[str]:
    """Return relative paths of staged files matching the corpus globs."""
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            cwd=str(root),
            capture_output=True,
            check=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [ln for ln in out.stdout.splitlines() if ln and _matches_scan_glob(ln)]


def _read_staged_blob(rel: str, root: Path) -> str | None:
    """Read the staged blob for *rel* via ``git show :rel``."""
    try:
        out = subprocess.run(
            ["git", "show", f":{rel}"],
            cwd=str(root),
            capture_output=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    try:
        return out.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None


# ---------------------------------------------------------------------------
# Gate modes
# ---------------------------------------------------------------------------


def run_audit(root: Path) -> list[Violation]:
    """Scan the working-tree corpus under *root*."""
    violations: list[Violation] = []
    for p in discover_files([root]):
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            rel = p.relative_to(root)
        except ValueError:
            rel = p
        violations.extend(scan_text(text, rel))
    return violations


def run_staged_gate(root: Path) -> list[Violation]:
    """Pre-commit gate: scan staged in-scope files."""
    violations: list[Violation] = []
    for rel in _staged_paths(root):
        if _is_hard_excluded(rel):
            continue
        text = _read_staged_blob(rel, root)
        if text is None:
            continue
        violations.extend(scan_text(text, Path(rel)))
    return violations


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

_parser = argparse.ArgumentParser(
    prog="cortex-check-bare-python-import",
    description=(
        "Bare-Python cortex_command import scanner (L201). "
        "Flags bare-Python cortex_command import/from-import and dynamic-import "
        "forms inside python-source regions in skill prose and related corpus files. "
        "Use --staged for pre-commit and --audit for full working-tree scan."
    ),
)
_parser.add_argument(
    "--staged",
    action="store_true",
    help="Pre-commit path: scan staged blobs matching the corpus globs.",
)
_parser.add_argument(
    "--audit",
    action="store_true",
    help="Scan the full working-tree corpus.",
)
_parser.add_argument(
    "--root",
    type=str,
    default=None,
    help="Repository root (default: cwd).",
)
_parser.add_argument(
    "--json",
    dest="as_json",
    action="store_true",
    help="Emit violations as a JSON array.",
)
_parser.add_argument(
    "--self-test",
    action="store_true",
    help="Run inline self-test and exit.",
)


def main(argv: Optional[List[str]] = None) -> int:
    from cortex_command.backlog import _telemetry
    _telemetry.log_invocation("cortex-check-bare-python-import")

    args = _parser.parse_args(argv)

    if args.self_test:
        return _run_self_test()

    root = Path(args.root).resolve() if args.root else Path(os.getcwd()).resolve()

    if args.staged:
        violations = run_staged_gate(root)
    elif args.audit or args.root:
        violations = run_audit(root)
    else:
        print(
            "cortex-check-bare-python-import: no mode selected; "
            "pass --staged, --audit, or --root.",
            file=sys.stderr,
        )
        return 2

    if args.as_json:
        import json
        print(json.dumps([v.format_json_dict() for v in violations]))
    else:
        for v in violations:
            print(v.format_text(), file=sys.stderr)

    return 1 if violations else 0


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def _run_self_test() -> int:
    """Inline self-test; returns 0 on pass, 1 on fail."""
    failures: list[str] = []

    # --- positive case: labeled fence ---
    text1 = "```python\nimport cortex_command\n```\n"
    v1 = scan_text(text1, Path("test.md"))
    if not v1:
        failures.append("self-test 1 FAIL: labeled fence import not detected")

    # --- positive case: dynamic find_spec ---
    text2 = '```bash\npython3 -c "import importlib.util; importlib.util.find_spec(\'cortex_command\')"\n```\n'
    v2 = scan_text(text2, Path("test.md"))
    if not v2:
        failures.append("self-test 2 FAIL: find_spec not detected")

    # --- negative case: inline-code span ---
    text3 = '`python3 -c "import cortex_command"`\n'
    v3 = scan_text(text3, Path("test.md"))
    if v3:
        failures.append("self-test 3 FAIL: inline-code span should not flag")

    # --- negative case: sentinel suppression ---
    text4 = "<!-- bare-python-lint:ignore-next -->\n```python\nimport cortex_command\n```\n"
    v4 = scan_text(text4, Path("test.md"))
    if v4:
        failures.append("self-test 4 FAIL: sentinel-suppressed region should not flag")

    for f in failures:
        print(f, file=sys.stderr)
    if not failures:
        print("cortex-check-bare-python-import self-test: PASS", file=sys.stderr)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
