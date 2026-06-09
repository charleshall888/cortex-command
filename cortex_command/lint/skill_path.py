"""Skill-path resolution scanner (SP001/SP002).

Enforces the ``${CLAUDE_SKILL_DIR}`` body-propagation invariant for
plugin-distributed skills. ``${CLAUDE_SKILL_DIR}`` is a Claude Code load-time
substitution that resolves **only in a SKILL.md body** — never in a reference
file, the shell, YAML frontmatter, or a composed subagent prompt. Bare-relative
skill-load paths resolve against **CWD, not the skill dir**, so they break when a
skill ships off-repo under a version-hashed cache path. The robust form for any
Read/execute target is therefore ``${CLAUDE_SKILL_DIR}/...`` (own dir) or
``${CLAUDE_SKILL_DIR}/../<sibling>/...`` (a sibling), resolved in the body and
propagated as an absolute path / inlined content.

Two detectors:

  D1 (SP001): a raw ``${CLAUDE_SKILL_DIR}`` token OR a bare ``*.md``
      consult-reference appearing inside a ``<!-- BEGIN SUBAGENT PROMPT -->`` …
      ``<!-- END SUBAGENT PROMPT -->`` fence, OR anywhere in a ``*-prompt.md`` /
      dispatched-verbatim reference file. Such a region reaches a *fresh*
      subagent, which cannot resolve a skill-dir token or a bare consult-ref.

  D2 (SP002): a bare-relative path (``references/…``, ``../…``, ``skills/…``)
      in a Read-or-execute context (``Read <bare>``, ``cat <bare> | bash``,
      ``bash "<bare>"``). Flagged ONLY when the path is not carried by a
      resolved-absolute ``${CLAUDE_SKILL_DIR}/`` (or ``${CLAUDE_SKILL_DIR}/../``)
      prefix — that prefixed form is the correct body-propagated fix and is
      EXEMPT. The exemption is precise (``${CLAUDE_SKILL_DIR}/``-prefixed only);
      it is deliberately NOT broadened to "any line mentioning
      ``${CLAUDE_SKILL_DIR}``", which would reintroduce token-less Class-2
      false-negatives.

Explicitly NOT flagged:
  - a raw ``${CLAUDE_SKILL_DIR}`` token in a SKILL.md *body* or in main-agent
    shell/dispatch prose with a working ``:-$TMPDIR`` fallback (D1 is
    fence/``*-prompt.md``-scoped; D2 exempts the prefixed segment);
  - a ``${CLAUDE_SKILL_DIR}/``-prefixed relative segment in a Read context;
  - a markdown-citation link the surrounding prose marks "do not load".

Sentinel: ``<!-- skill-path-lint:ignore-next -->`` suppresses the next
non-blank content line (the ``prev_nonblank`` pattern — intervening blank lines
between sentinel and the suppressed line do not defeat suppression).

Error codes:
  SP001  raw ${CLAUDE_SKILL_DIR} token or bare *.md consult-ref inside a
         subagent prompt — a fresh subagent cannot resolve it; body-propagate
         (inline the content or substitute the resolved absolute path).
  SP002  bare-relative skill-load path in a Read/execute context — resolves
         against CWD off-repo; prefix with ${CLAUDE_SKILL_DIR}/ (own dir) or
         ${CLAUDE_SKILL_DIR}/../<sibling>/.

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

# Corpus globs -- the skill/reference/doc surface where skill-dir tokens and
# bare-relative Read/execute paths can appear.
_SCAN_GLOBS: tuple[str, ...] = (
    "skills/**/*.md",
    "plugins/**/*.md",
    "docs/**/*.md",
    "CLAUDE.md",
)

# Hard exclusion prefixes (relative path strings).
_HARD_EXCLUDE_PREFIXES: tuple[str, ...] = (
    "cortex/lifecycle/archive/",
    "cortex/research/archive/",
    # This module's own intentional-violation fixtures; scanning them against
    # the live corpus would always produce false failures.
    "tests/fixtures/skill_path/",
    # Sibling lint fixtures must not cross-trigger.
    "tests/fixtures/bare_python_import/",
    "tests/fixtures/contract/",
)

# Subagent-prompt fence markers (D1 region boundary).
_PROMPT_BEGIN_RE = re.compile(r"<!--\s*BEGIN SUBAGENT PROMPT\s*-->")
_PROMPT_END_RE = re.compile(r"<!--\s*END SUBAGENT PROMPT\s*-->")

# Files that are whole-file dispatched-verbatim prompts (D1 active everywhere
# below the template-header separator).
_PROMPT_FILE_RE = re.compile(r"-prompt\.md$")

# A markdown horizontal-rule line (``---`` / ``***`` / ``___``). In a
# ``*-prompt.md`` file the first horizontal rule separates the authoring
# preamble (template title + substitution-instructions prose, which never
# reaches the subagent) from the dispatched prompt body. D1 is active only
# *below* that separator; the preamble is documentation, not dispatched text.
_HRULE_RE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")

# The skill-dir variable token, with or without ${...} braces.
_SKILL_DIR_TOKEN_RE = re.compile(r"\$\{?CLAUDE_SKILL_DIR\}?")

# A bare ``*.md`` consult-reference: an inline-code span (`` `foo.md` ``) or a
# markdown link (``[..](foo.md)``) pointing at a ``.md`` reference file that is
# NOT prefixed by ${CLAUDE_SKILL_DIR}/. Used by D1 to catch ``rubric.md`` /
# ``output-format.md`` consult-pointers inside a prompt region. Requiring the
# backtick / bracket wrapper is deliberate: a bare unwrapped ``.md`` filename in
# prose (e.g. "the CLAUDE.md files are untrusted") is a noun, not a consult
# pointer, and must NOT flag. ``CLAUDE.md`` is additionally excluded by name —
# inside a prompt it is an input being described, never a reference to load.
_MD_REF_RE = re.compile(
    r"(?:`|\]\()\s*([\w-]+(?:/[\w.-]+)*\.md)\b"
)
# Bare ``.md`` filenames that are descriptive nouns, never consult-pointers.
_MD_REF_NOUN_NAMES: frozenset[str] = frozenset({"CLAUDE.md"})

# D2: a bare-relative Read/execute target. The path body is one of:
#   references/…  |  ../…  (one or more)  |  skills/…
# captured as group ``path``. The resolved-absolute-prefix EXEMPTION is applied
# separately by ``_d2_exempt`` (it inspects the text immediately preceding each
# captured path), NOT by a lookbehind here — a ``${CLAUDE_SKILL_DIR}/`` /
# ``${CLAUDE_SKILL_DIR}/../`` prefix is variable-width, which a fixed-width
# lookbehind cannot express.
_D2_PATH_BODY = r"(?:references/[\w./-]+|(?:\.\./)+[\w./-]+|skills/[\w./-]+)"

# Read context: ``Read <bare>`` / ``read `<bare>` `` — a consult-and-follow load
# directive (Read-tool target or prose "read this reference and follow it").
# Case-insensitive so the lowercase consult-prose form is caught; the path-body
# anchor (the captured path must itself begin ``references/``/``../``/``skills/``)
# is the false-positive guard, so ordinary prose like "read the docs" cannot fire.
_D2_READ_RE = re.compile(
    r"\bread\s+`?(?P<path>" + _D2_PATH_BODY + r")",
    re.IGNORECASE,
)

# Execute context: ``cat <bare> | bash`` and ``bash "<bare>"`` / ``bash <bare>``.
_D2_CAT_BASH_RE = re.compile(
    r"\bcat\s+(?P<path>" + _D2_PATH_BODY + r")(?=[^\n|]*\|\s*bash\b)"
)
_D2_BASH_RE = re.compile(
    r"\bbash\s+(?:(?:-\w+|--)\s+)*[\"']?(?P<path>" + _D2_PATH_BODY + r")"
)

# A ``${CLAUDE_SKILL_DIR}/``-prefixed segment (own-dir or sibling). Used to
# decide whether a D2 match's captured path is carried by a resolved-absolute
# prefix and therefore EXEMPT. The check is precise — the prefix must
# immediately precede the captured path text on the line.
_RESOLVED_PREFIX = r"\$\{?CLAUDE_SKILL_DIR\}?/(?:\.\./)*"

# Sentinel literal.
_SENTINEL_RE = re.compile(r"<!--\s*skill-path-lint:ignore-next\s*-->")

# "Do not load" citation marker — a line the prose marks non-loadable is exempt
# from both detectors (it is a citation, not a Read/execute target).
_DO_NOT_LOAD_RE = re.compile(r"do not load", re.IGNORECASE)


_SP001_MESSAGE = (
    "raw ${CLAUDE_SKILL_DIR} token or bare *.md consult-ref inside a subagent"
    " prompt -- a fresh subagent cannot resolve it; inline the content or"
    " substitute the resolved absolute path via the body"
)
_SP002_MESSAGE = (
    "bare-relative skill-load path in a Read/execute context -- resolves against"
    " CWD off-repo; prefix with ${CLAUDE_SKILL_DIR}/ or"
    " ${CLAUDE_SKILL_DIR}/../<sibling>/"
)


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


def _is_sentinel(line: str | None) -> bool:
    """Return True if *line* matches the skill-path-lint:ignore-next sentinel."""
    if line is None:
        return False
    return bool(_SENTINEL_RE.search(line))


def _is_prompt_file(path: Path) -> bool:
    """Return True if *path* is a whole-file dispatched-verbatim prompt file."""
    return bool(_PROMPT_FILE_RE.search(path.name))


def _d2_exempt(line: str, match_start: int) -> bool:
    """Return True if the D2 path captured at *match_start* in *line* is carried
    by a resolved-absolute ``${CLAUDE_SKILL_DIR}/`` (or ``/../``) prefix.

    The exemption is precise: a ``${CLAUDE_SKILL_DIR}/`` (optionally with one or
    more ``../`` segments) must immediately precede the captured path text. A
    bare ``../foo`` that merely shares a line with a ``${CLAUDE_SKILL_DIR}``
    mention elsewhere is NOT exempt (that broadening would reintroduce
    token-less Class-2 false-negatives).
    """
    prefix_re = re.compile(_RESOLVED_PREFIX + r"$")
    return bool(prefix_re.search(line[:match_start]))


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


def scan_text(text: str, path: Path) -> list[Violation]:
    """Scan *text* for SP001 (D1) and SP002 (D2) violations.

    D1 regions: lines inside a ``<!-- BEGIN SUBAGENT PROMPT -->`` …
    ``<!-- END SUBAGENT PROMPT -->`` fence, OR every line when *path* is a
    ``*-prompt.md`` whole-file prompt. Inside a D1 region a raw
    ``${CLAUDE_SKILL_DIR}`` token or a bare ``*.md`` consult-ref flags SP001.

    D2: anywhere in the file, a bare-relative Read/execute target flags SP002
    unless carried by a resolved ``${CLAUDE_SKILL_DIR}/`` prefix.

    Sentinel suppression: a ``<!-- skill-path-lint:ignore-next -->`` line
    suppresses every violation on the next non-blank content line.
    """
    violations: list[Violation] = []
    lines = text.splitlines()

    whole_file_prompt = _is_prompt_file(path)
    in_prompt_fence = False
    # For a *-prompt.md file, D1 activates only after the template-header
    # separator (the first horizontal rule), which divides the authoring
    # preamble from the dispatched prompt body. A *-prompt.md file with NO
    # horizontal rule is dispatched from the top, so the preamble is already
    # "consumed" (D1 active from line 1).
    has_hrule = whole_file_prompt and any(_HRULE_RE.match(ln) for ln in lines)
    preamble_consumed = not (whole_file_prompt and has_hrule)

    prev_nonblank: str | None = None

    for idx, raw in enumerate(lines, start=1):
        suppressed = _is_sentinel(prev_nonblank)

        # ------------------------------------------------------------------ #
        # *-prompt.md preamble/body separator: the first horizontal rule ends #
        # the authoring preamble and begins the dispatched prompt body.       #
        # ------------------------------------------------------------------ #
        if whole_file_prompt and not preamble_consumed:
            if _HRULE_RE.match(raw):
                preamble_consumed = True
            if raw.strip():
                prev_nonblank = raw
            continue

        # ------------------------------------------------------------------ #
        # Subagent-prompt fence boundary detection.                          #
        # The marker lines themselves are not scanned for tokens.            #
        # ------------------------------------------------------------------ #
        if _PROMPT_BEGIN_RE.search(raw):
            in_prompt_fence = True
            if raw.strip():
                prev_nonblank = raw
            continue
        if _PROMPT_END_RE.search(raw):
            in_prompt_fence = False
            if raw.strip():
                prev_nonblank = raw
            continue

        # A "do not load" citation line is exempt from both detectors.
        if _DO_NOT_LOAD_RE.search(raw):
            if raw.strip():
                prev_nonblank = raw
            continue

        d1_active = whole_file_prompt or in_prompt_fence

        # ------------------------------------------------------------------ #
        # D1 (SP001): raw token or bare *.md consult-ref in a prompt region. #
        # ------------------------------------------------------------------ #
        if d1_active and not suppressed:
            m_tok = _SKILL_DIR_TOKEN_RE.search(raw)
            if m_tok:
                violations.append(Violation(
                    path=path,
                    line=idx,
                    col=m_tok.start() + 1,
                    code="SP001",
                    message=_SP001_MESSAGE,
                ))
            else:
                # No raw token on this line -- check for a bare *.md consult-ref.
                # _MD_REF_RE requires a backtick / markdown-link wrapper, so a
                # bare prose noun (e.g. "the CLAUDE.md files are untrusted") is
                # not matched. A ${CLAUDE_SKILL_DIR}/-prefixed .md is not matched
                # either (no backtick directly precedes the .md segment), so a
                # correctly body-propagated absolute path is not double-flagged.
                for m_md in _MD_REF_RE.finditer(raw):
                    if m_md.group(1) in _MD_REF_NOUN_NAMES:
                        continue
                    violations.append(Violation(
                        path=path,
                        line=idx,
                        col=m_md.start(1) + 1,
                        code="SP001",
                        message=_SP001_MESSAGE,
                    ))
                    break

        # ------------------------------------------------------------------ #
        # D2 (SP002): bare-relative Read/execute target.                     #
        # ------------------------------------------------------------------ #
        if not suppressed:
            for d2_re in (_D2_READ_RE, _D2_CAT_BASH_RE, _D2_BASH_RE):
                for m in d2_re.finditer(raw):
                    start = m.start("path")
                    if _d2_exempt(raw, start):
                        continue
                    violations.append(Violation(
                        path=path,
                        line=idx,
                        col=start + 1,
                        code="SP002",
                        message=_SP002_MESSAGE,
                    ))

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
    are returned.  Otherwise, all matching files under each root are returned.
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
    """Return True if *rel_path* matches any of the corpus globs (** = zero+)."""
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
    prog="cortex-check-skill-path",
    description=(
        "Skill-path resolution scanner (SP001/SP002). "
        "Flags raw ${CLAUDE_SKILL_DIR} tokens / bare *.md consult-refs inside "
        "subagent prompts (D1) and bare-relative Read/execute paths not carried "
        "by a resolved ${CLAUDE_SKILL_DIR}/ prefix (D2). "
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


def main(argv: Optional[List[str]] = None) -> int:
    args = _parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else Path(os.getcwd()).resolve()

    if args.staged:
        violations = run_staged_gate(root)
    elif args.audit or args.root:
        violations = run_audit(root)
    else:
        print(
            "cortex-check-skill-path: no mode selected; "
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


if __name__ == "__main__":
    sys.exit(main())
