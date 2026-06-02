"""AST-based argparse surface extractor for cortex-* console scripts.

Reads ``[project.scripts]`` from ``pyproject.toml`` via ``tomllib``, resolves
each ``module:attr`` target to a source path via ``importlib.util.find_spec``
(no imports — avoids side-effects), parses the source with ``ast``, and walks
for ``argparse.ArgumentParser(...)`` constructors and
``.add_argument(...)`` / ``.add_subparsers(...)`` / subparser ``.add_parser(...)``
calls.

Error codes emitted by this module:
  E101  missing required flag --X for cortex-Y
  E102  unknown flag --X for cortex-Y
  E103  missing required subcommand for cortex-Y
  E201  cannot AST-parse module source for cortex-X at path Y
  E202  ambiguous main parser for cortex-X (tied add_argument counts)

The ``extract_surface()`` function is the primary public API.  All other
callables are internal helpers.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import shlex
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ParserSurface:
    """Static representation of one ArgumentParser's accepted surface."""

    binary: str
    """The console-script binary name (e.g. ``cortex-create-backlog-item``)."""

    module_path: Path
    """Absolute path to the source file."""

    required_flags: set[str] = field(default_factory=set)
    """Long- and short-form flags declared with ``required=True``."""

    optional_flags: set[str] = field(default_factory=set)
    """Long- and short-form flags NOT declared required (or with a default)."""

    subcommands: dict[str, "ParserSurface"] = field(default_factory=dict)
    """Subcommand name → ParserSurface for each ``.add_parser(name)`` call."""

    extraction_status: Literal["ok", "ast_error", "ambiguous", "not_argparse"] = "ok"
    """Extraction outcome for this entry."""


@dataclass
class ExtractionError:
    """Non-fatal error emitted during surface extraction."""

    binary: str
    code: str  # E201 or E202
    message: str

    def format_text(self) -> str:
        return f"{self.code} {self.message}"


@dataclass(frozen=True)
class Violation:
    """A lint violation produced by ``validate()``.

    Shape mirrors ``cortex_command.parity_check.Violation`` so that downstream
    consumers can treat both interchangeably.
    """

    path: str
    line: int
    col: int
    code: str
    message: str

    def format_text(self) -> str:
        return f"{self.path}:{self.line}:{self.col}: {self.code} {self.message}"

    def format_json_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "line": self.line,
            "col": self.col,
            "code": self.code,
            "message": self.message,
        }


@dataclass
class _LedgerEntry:
    """One parsed row from the exception ledger table."""

    binary: str
    flag_or_subcommand: str
    path_glob: str
    category: str
    rationale: str
    lifecycle_id: str
    added_date: str


_LEDGER_ALLOWED_CATEGORIES: frozenset[str] = frozenset(
    {
        "non-argparse-module",
        "migration-note",
        "template-fragment",
        "intentional-omission",
    }
)

_LEDGER_FORBIDDEN_RATIONALE_LITERALS: frozenset[str] = frozenset(
    {"internal", "misc", "tbd", "n/a", "pending", "temporary"}
)


class ExceptionLedger:
    """Exception ledger parsed from ``bin/.contract-lint-exceptions.md``.

    The ledger suppresses violations whose ``(binary, flag-or-subcommand,
    path-glob)`` triple matches a registered entry.  Matching uses exact
    comparison for *binary* and *flag-or-subcommand* (with ``*`` as a
    wildcard) and ``fnmatch.fnmatch`` for *path-glob* against the
    violation path relative to the repo root.
    """

    def __init__(self, entries: list[_LedgerEntry] | None = None) -> None:
        self._entries: list[_LedgerEntry] = entries or []

    def match(self, binary: str, flag_or_subcommand: str, path: str) -> bool:
        """Return True if the triple ``(binary, flag_or_subcommand, path)`` is suppressed.

        Parameters
        ----------
        binary:
            The cortex-* binary name.
        flag_or_subcommand:
            The flag or subcommand token being checked (e.g., ``--status``,
            ``<subcommand>``).
        path:
            The file path of the invocation (may be absolute or relative).
        """
        import fnmatch

        for entry in self._entries:
            # Binary match: exact or wildcard ``*``.
            if entry.binary != "*" and entry.binary != binary:
                continue
            # Flag/subcommand match: exact or wildcard ``*``.
            if entry.flag_or_subcommand != "*" and entry.flag_or_subcommand != flag_or_subcommand:
                continue
            # Path match: fnmatch against the provided path string.
            if entry.path_glob != "*" and not fnmatch.fnmatch(path, entry.path_glob):
                continue
            return True
        return False

    @classmethod
    def empty(cls) -> "ExceptionLedger":
        """Return an empty ledger (suppresses nothing).

        Kept for backwards compatibility — many test callsites use this.
        """
        return cls(entries=[])


def parse_exception_ledger(path: Path) -> "ExceptionLedger":
    """Parse the markdown-table exception ledger at *path*.

    Columns (7): ``binary | flag-or-subcommand | path-glob | category |
    rationale | lifecycle_id | added_date``.

    Rows that fail validation are silently skipped (callers wishing to
    surface validation errors should call :func:`validate_exception_ledger`
    instead, which returns :class:`Violation` objects).

    Returns an :class:`ExceptionLedger` populated with all *valid* entries.
    """
    entries: list[_LedgerEntry] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ExceptionLedger(entries=[])

    saw_header = False
    saw_separator = False

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            # Reset table state when leaving a table block.
            if saw_header or saw_separator:
                saw_header = False
                saw_separator = False
            continue

        cells = [c.strip() for c in stripped.strip("|").split("|")]

        if not saw_header:
            # Detect the canonical header row (case-insensitive).
            normalized = [c.lower().replace("-", "_") for c in cells]
            if normalized == [
                "binary",
                "flag_or_subcommand",
                "path_glob",
                "category",
                "rationale",
                "lifecycle_id",
                "added_date",
            ]:
                saw_header = True
            continue

        if not saw_separator:
            # Separator row: all cells consist of ``-``, ``:``, and space only.
            if all(set(c) <= set("-: ") and "-" in c for c in cells):
                saw_separator = True
            else:
                saw_header = False
            continue

        # Data row.
        if len(cells) != 7:
            continue

        binary, flag_or_subcommand, path_glob, category, rationale, lifecycle_id, added_date = cells
        # Strip backtick decoration commonly used in markdown tables.
        binary = binary.strip("`").strip()
        flag_or_subcommand = flag_or_subcommand.strip("`").strip()
        path_glob = path_glob.strip("`").strip()
        category = category.strip("`").strip()
        rationale = rationale.strip()
        lifecycle_id = lifecycle_id.strip("`").strip()
        added_date = added_date.strip("`").strip()

        # Validate (same rules as validate_exception_ledger); skip invalid rows.
        if category not in _LEDGER_ALLOWED_CATEGORIES:
            continue
        if len(rationale) < 30:
            continue
        if rationale.lower() in _LEDGER_FORBIDDEN_RATIONALE_LITERALS:
            continue

        entries.append(
            _LedgerEntry(
                binary=binary,
                flag_or_subcommand=flag_or_subcommand,
                path_glob=path_glob,
                category=category,
                rationale=rationale,
                lifecycle_id=lifecycle_id,
                added_date=added_date,
            )
        )

    return ExceptionLedger(entries=entries)


def validate_exception_ledger(path: Path) -> list[Violation]:
    """Validate every entry in the exception ledger at *path*.

    Returns a list of :class:`Violation` objects for each failing entry.
    Error codes:

    - ``E301`` — rationale is fewer than 30 characters after strip.
    - ``E302`` — rationale uses a forbidden literal (``tbd``, ``n/a``, etc.).
    - ``E303`` — category is not in the closed set.

    A missing file returns an empty list (no file = no entries to validate).
    """
    violations: list[Violation] = []
    source = str(path)

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []

    saw_header = False
    saw_separator = False

    for idx, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped.startswith("|"):
            if saw_header or saw_separator:
                saw_header = False
                saw_separator = False
            continue

        cells = [c.strip() for c in stripped.strip("|").split("|")]

        if not saw_header:
            normalized = [c.lower().replace("-", "_") for c in cells]
            if normalized == [
                "binary",
                "flag_or_subcommand",
                "path_glob",
                "category",
                "rationale",
                "lifecycle_id",
                "added_date",
            ]:
                saw_header = True
            continue

        if not saw_separator:
            if all(set(c) <= set("-: ") and "-" in c for c in cells):
                saw_separator = True
            else:
                saw_header = False
            continue

        # Data row.
        if len(cells) != 7:
            continue

        binary, flag_or_subcommand, path_glob, category, rationale, lifecycle_id, added_date = cells
        category = category.strip("`").strip()
        rationale = rationale.strip()

        # E303: unknown category.
        if category not in _LEDGER_ALLOWED_CATEGORIES:
            violations.append(
                Violation(
                    path=source,
                    line=idx,
                    col=1,
                    code="E303",
                    message=(
                        f"unknown category {category!r} — must be one of "
                        f"{sorted(_LEDGER_ALLOWED_CATEGORIES)}"
                    ),
                )
            )
            continue

        # E302: forbidden rationale literal (checked before length so the
        # message is the most informative one for short forbidden literals).
        if rationale.lower() in _LEDGER_FORBIDDEN_RATIONALE_LITERALS:
            violations.append(
                Violation(
                    path=source,
                    line=idx,
                    col=1,
                    code="E302",
                    message=f"ledger rationale uses forbidden literal {rationale!r}",
                )
            )
            continue

        # E301: rationale too short.
        if len(rationale) < 30:
            violations.append(
                Violation(
                    path=source,
                    line=idx,
                    col=1,
                    code="E301",
                    message=(
                        f"ledger rationale too short "
                        f"({len(rationale)} chars, need ≥30)"
                    ),
                )
            )
            continue

    return violations


@dataclass
class Invocation:
    """A detected cortex-* invocation in the scan corpus."""

    path: Path
    """File where the invocation was found."""

    line: int
    """1-based line number."""

    col: int
    """0-based column offset of the binary name."""

    binary: str
    """The cortex-* binary name matched (e.g. ``cortex-foo``)."""

    tail_tokens: list[str]
    """Whitespace-separated tokens after the binary name.

    Templated placeholders (``{{...}}``, ``{...}``, ``<...>``) are kept
    as opaque strings.  Empty when the binary appears alone (bare name).
    """

    fence_kind: Literal["fenced", "inline"]
    """How the invocation was found: inside a fenced code block or an
    inline-code span."""

    preceding_line: str | None
    """The raw text of the immediately preceding non-blank line, or None
    if no such line exists.  Used by the sentinel-marker check."""


# ---------------------------------------------------------------------------
# Scan corpus globs and exclusions
# ---------------------------------------------------------------------------

_SCAN_GLOBS: tuple[str, ...] = (
    "skills/**/*.md",
    "hooks/**",
    "justfile",
    "docs/**/*.md",
    "tests/**/*.md",
    "CLAUDE.md",
    "cortex/requirements/**/*.md",
)


def _glob_to_regex(glob: str) -> re.Pattern[str]:
    """Translate a ``_SCAN_GLOBS`` entry to a compiled regex.

    ``**`` is treated as *zero or more* path segments, so
    ``skills/**/*.md`` matches both ``skills/foo.md`` (depth-1, zero mid-dirs)
    and ``skills/a/b/foo.md`` (depth-≥3).  Safe on Python 3.12+.

    Safe on Python 3.12+: does not use ``PurePath`` pattern methods added in
    3.13, and avoids the bare-``**`` semantics of ``Path.match`` / ``root.glob``
    which vary by version and treat ``**`` as exactly one segment on 3.12.
    """

    def _esc_segment(s: str) -> str:
        """Regex-escape a glob segment, then convert ``*`` → ``[^/]*``."""
        return re.escape(s).replace(r"\*", "[^/]*")

    if glob.endswith("/**"):
        # e.g. "hooks/**" → match anything (at any depth) under hooks/
        prefix = re.escape(glob[:-3])
        return re.compile(rf"^{prefix}/.+$")

    if "**" not in glob:
        # No wildcard — exact match with single-* support.
        return re.compile(rf"^{_esc_segment(glob)}$")

    # Glob contains **/ (zero-or-more path segments).
    # Split on "**/" to get anchored prefix/suffix pieces; each piece may
    # still contain single-* wildcards.
    segments = glob.split("**/")
    regex_parts = [_esc_segment(s) for s in segments]
    # "**/" between two parts → zero or more "<name>/" repetitions.
    pattern = "(?:[^/]+/)*".join(regex_parts)
    return re.compile(rf"^{pattern}$")


# Pre-compile scan-scope patterns once at import time.
_SCAN_GLOB_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    _glob_to_regex(g) for g in _SCAN_GLOBS
)


def _in_scan_scope(rel: str) -> bool:
    """Return True iff *rel* (repo-relative POSIX path) matches any ``_SCAN_GLOBS`` entry.

    Uses a regex-based recursive-glob matcher that treats ``**`` as zero or
    more path segments, so depth-1, depth-2, and depth-≥3 in-scope paths are
    all admitted — unlike ``PurePath.match`` which treats ``**`` as exactly one
    segment on Python 3.12.
    """
    for pat in _SCAN_GLOB_PATTERNS:
        if pat.match(rel):
            return True
    return False


# Hard exclusion patterns — checked against path relative to root.
# Paths matching any of these prefixes (or exact names) are skipped.
_HARD_EXCLUDE_PREFIXES: tuple[str, ...] = (
    "cortex/research/archive/",
    "cortex/lifecycle/",
    # Intentional violation fixtures used by the contract-lint self-tests;
    # scanning them against the live corpus would always produce false failures.
    "tests/fixtures/contract/",
)

_HARD_EXCLUDE_EXACT: frozenset[str] = frozenset(
    {
        "CHANGELOG.md",
    }
)

_HARD_EXCLUDE_GLOBS: tuple[str, ...] = (
    "bin/.audit-*-allowlist.md",
    "bin/.parity-exceptions.md",
)

# Regex for cortex-* binary names.
_BINARY_RE = re.compile(r"cortex-[a-z][a-z0-9-]*")

# Fence delimiter regex (backtick or tilde runs of ≥3).
_FENCE_RE = re.compile(r"^(`{3,}|~{3,})")

# Inline code span regex — matches `...` (single-backtick) spans on a line.
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")

# Templated placeholder patterns kept as opaque tokens.
_PLACEHOLDER_RE = re.compile(r"(\{\{[^}]+\}\}|\{[^}]+\}|<[^>]+>)")

# ---------------------------------------------------------------------------
# Command-position predicate helpers (R1)
# ---------------------------------------------------------------------------

# Extension suffix: token immediately followed by '.' + alpha run (e.g. .sh, .py, .json).
_EXT_SUFFIX_RE = re.compile(r"^\.[a-zA-Z]+")

# Shell separators that place a token in command position when they appear in
# the left-context (after optional whitespace).
_SHELL_SEP_RE = re.compile(
    r"(?:"
    r"\|\|"           # ||
    r"|&&"            # &&
    r"|\|"            # |
    r"|;"             # ;
    r"|\$\("          # $(
    r"|`"             # backtick
    r"|\("            # (
    r"|\{"            # {
    r"|\bthen\b"      # then
    r"|\bdo\b"        # do
    r"|\belse\b"      # else
    r")\s*$"
)

# Shell prompt prefix stripped before command-position check.
_PROMPT_PREFIX_RE = re.compile(r"^[$%]\s+")

# Probe commands that make a token a probe-operand (not an invocation):
# 'command -v', 'command -V', 'which', 'type', 'hash'.
# 'command <tok>' (bare, no flag) is NOT a probe — it executes.
_PROBE_HEAD_RE = re.compile(
    r"(?:^|(?<=\s))"
    r"(?:"
    r"command\s+-[vV]"  # command -v / command -V
    r"|which"           # which
    r"|type"            # type
    r"|hash"            # hash
    r")\s+$"
)

# Path-segment prefix: character immediately before the token is '/'.
_PATH_PREFIX_CHARS = frozenset("/")

# argv token: a flag (starts with '-') or a non-whitespace word after whitespace.
# Used to determine whether a path-prefixed token is a real run vs. a bare path tail.
_ARGV_TOKEN_RE = re.compile(r"^\s+\S")

# Env-var prefix chain: one or more VAR=VALUE assignments (possibly with a
# preceding shell-prompt) that make the following token the command word.
# Matches the entire left-context when it is only env assignments + optional prompt.
_ENV_PREFIX_RE = re.compile(r"^(?:[$%]\s+)?(?:[A-Za-z_][A-Za-z0-9_]*=[^\s]* +)+$")

# Bare 'command' builtin (no flag): executes its first positional argument.
# Matches left-context that ends with whitespace-separated 'command'.
_BARE_COMMAND_RE = re.compile(r"(?:^|[\s|;&({\`])command\s+$")


def _is_invocation(left: str, token: str, right: str) -> bool:
    """Return True if the matched token is a genuine command invocation.

    Parameters
    ----------
    left:
        Text immediately before the token in the span/line (left-context).
    token:
        The matched cortex-* binary name.
    right:
        Text immediately after the token in the span/line (right-context / raw tail).

    Rule precedence: rejection rules (extension, probe, =-RHS) take priority
    over command-position acceptance — see R1 spec.
    """
    # ------------------------------------------------------------------
    # Rule 1a: Extension-suffix rejection.
    # Token is immediately followed by '.' + alpha-run → path filename.
    # This is unconditional; wins over command-position acceptance.
    # ------------------------------------------------------------------
    if _EXT_SUFFIX_RE.match(right):
        return False

    # ------------------------------------------------------------------
    # Rule 1b: Path-prefix handling.
    # Token is immediately preceded by '/'.
    # - If NOT followed by argv tokens: bare path tail → reject.
    # - If followed by argv tokens: path-prefixed real run (e.g.
    #   bin/cortex-worktree-create --base-branch main) → accept after
    #   checking higher-priority rejection rules 3/4.
    # ------------------------------------------------------------------
    _path_prefixed_with_argv = False
    if left and left[-1] in _PATH_PREFIX_CHARS:
        has_argv = bool(_ARGV_TOKEN_RE.match(right))
        if not has_argv:
            return False
        _path_prefixed_with_argv = True

    # ------------------------------------------------------------------
    # Rule 3: Probe-operand rejection.
    # The left-context ends with a probe head (which/type/hash/command -v).
    # This must win over command-position acceptance.
    # ------------------------------------------------------------------
    if _PROBE_HEAD_RE.search(left):
        return False

    # ------------------------------------------------------------------
    # Rule 4: =-RHS bare-value rejection.
    # Token is the immediate RHS of '=' with no intervening space.
    # Exempt: '=(' and '=`' (command-substitution forms are real runs).
    # Exempt: space-separated env-prefix form ('FOO=1 cortex-…').
    # ------------------------------------------------------------------
    if left and left[-1] == "=" and right[:1] not in ("(", "`"):
        return False

    # Path-prefixed with argv tokens is a real run (rules 3/4 did not reject).
    if _path_prefixed_with_argv:
        return True

    # ------------------------------------------------------------------
    # Rule 2: Command-position acceptance.
    # Accept when the normalized left-context is empty (span/line start)
    # or ends with a shell separator.
    # Also accept: env-var prefix chain ('FOO=1 cortex-…') and bare
    # 'command' builtin ('command cortex-…').
    # ------------------------------------------------------------------
    # Strip shell-prompt prefix ('$ ' / '% ') from the left edge.
    stripped_left = _PROMPT_PREFIX_RE.sub("", left)
    # Span/line start (possibly after prompt strip).
    if not stripped_left or not stripped_left.strip():
        return True
    # After a shell separator.
    if _SHELL_SEP_RE.search(stripped_left):
        return True
    # Env-var prefix chain: 'FOO=1 ', 'A=x B=y ', etc.
    if _ENV_PREFIX_RE.match(stripped_left):
        return True
    # Bare 'command' builtin (no -v/-V flag).
    if _BARE_COMMAND_RE.search(stripped_left):
        return True

    # Not in command position — not an invocation.
    return False


def _is_hard_excluded(rel: str) -> bool:
    """Return True if ``rel`` (relative path string) is hard-excluded."""
    for prefix in _HARD_EXCLUDE_PREFIXES:
        if rel.startswith(prefix):
            return True
    if rel in _HARD_EXCLUDE_EXACT:
        return True
    # Check glob-like patterns for bin/ exclusions.
    p = Path(rel)
    for pat in _HARD_EXCLUDE_GLOBS:
        if p.match(pat):
            return True
    return False


def _gather_corpus_paths(root: Path) -> list[Path]:
    """Return deduplicated paths under ``root`` matching the scan globs."""
    seen: set[Path] = set()
    out: list[Path] = []
    for glob in _SCAN_GLOBS:
        for p in root.glob(glob):
            if not p.is_file():
                continue
            rp = p.resolve()
            if rp in seen:
                continue
            try:
                rel = str(p.relative_to(root))
            except ValueError:
                rel = str(p)
            if _is_hard_excluded(rel):
                continue
            seen.add(rp)
            out.append(p)
    return sorted(out, key=lambda p: str(p))


def _tokenize_tail(tail: str) -> list[str]:
    """Split ``tail`` (text after the binary name) into tokens.

    Preserves templated placeholders as opaque tokens.  Uses simple
    whitespace splitting after extracting placeholder spans.
    """
    tokens: list[str] = []
    # Walk through the tail, extracting placeholder and regular tokens.
    pos = 0
    tail = tail.strip()
    while pos < len(tail):
        # Try matching a placeholder at current position.
        m = _PLACEHOLDER_RE.match(tail, pos)
        if m:
            tokens.append(m.group(0))
            pos = m.end()
            # Skip whitespace after placeholder.
            while pos < len(tail) and tail[pos].isspace():
                pos += 1
            continue
        # Find the next whitespace or placeholder boundary.
        end = pos
        while end < len(tail):
            if tail[end].isspace():
                break
            # Stop before a placeholder start.
            if tail[end] in ('{', '<') and _PLACEHOLDER_RE.match(tail, end):
                break
            end += 1
        if end > pos:
            tokens.append(tail[pos:end])
        # Skip whitespace.
        pos = end
        while pos < len(tail) and tail[pos].isspace():
            pos += 1
    return tokens


def _scan_file_for_invocations(path: Path) -> list[Invocation]:
    """Scan a single file and return all detected invocations."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    lines = text.splitlines()
    invocations: list[Invocation] = []

    # Fence state machine (ported from prescriptive_prose.py:113-156).
    in_fence = False
    fence_delim: str | None = None

    # Track the preceding non-blank line for each line.
    prev_nonblank: str | None = None

    # The non-blank line that immediately preceded the opening fence delimiter.
    # Used as `preceding_line` for all invocations inside the fence so that
    # a sentinel placed before the fence (not inside it) is correctly detected.
    fence_preceding: str | None = None

    # Buffer for backslash continuation within fenced blocks.
    pending_fenced_line: str | None = None
    pending_fenced_lineno: int = 0
    pending_fenced_preceding: str | None = None

    def _emit_fenced(combined: str, lineno: int, preceding: str | None) -> None:
        """Detect invocations in a fenced-block line (already continuation-joined)."""
        for m in _BINARY_RE.finditer(combined):
            binary = m.group(0)
            left_ctx = combined[:m.start()]
            raw_tail = combined[m.end():]
            # R1: Command-position guard — skip if not a genuine invocation.
            if not _is_invocation(left_ctx, binary, raw_tail):
                continue
            col = m.start()
            tail_tokens = _tokenize_tail(raw_tail)
            # Symmetric with inline: skip bare-name (no tail tokens) matches.
            if not tail_tokens:
                continue
            invocations.append(Invocation(
                path=path,
                line=lineno,
                col=col,
                binary=binary,
                tail_tokens=tail_tokens,
                fence_kind="fenced",
                preceding_line=preceding,
            ))

    for idx, raw in enumerate(lines, start=1):
        # --- Fence state machine ---
        m_fence = _FENCE_RE.match(raw)
        if m_fence:
            if not in_fence:
                in_fence = True
                fence_delim = m_fence.group(1)[0] * len(m_fence.group(1))
                # Capture the non-blank line that preceded the opening fence.
                # This is what the sentinel check must see: a comment placed
                # before the fence block should suppress invocations inside it.
                fence_preceding = prev_nonblank
                # Flush any pending continuation line.
                if pending_fenced_line is not None:
                    _emit_fenced(pending_fenced_line, pending_fenced_lineno, pending_fenced_preceding)
                    pending_fenced_line = None
            else:
                # Closing fence: delimiter must match the opening character and
                # length must be ≥ opening length.
                opener_char = fence_delim[0]
                opener_len = len(fence_delim)
                raw_stripped = raw.rstrip()
                if (
                    raw_stripped
                    and all(c == opener_char for c in raw_stripped)
                    and len(raw_stripped) >= opener_len
                ):
                    # Flush any pending continuation.
                    if pending_fenced_line is not None:
                        _emit_fenced(pending_fenced_line, pending_fenced_lineno, pending_fenced_preceding)
                        pending_fenced_line = None
                    in_fence = False
                    fence_delim = None
            if raw.strip():
                prev_nonblank = raw
            continue

        if in_fence:
            # Handle backslash continuation within fenced blocks.
            stripped = raw.rstrip("\n\r")
            if stripped.endswith("\\"):
                # Line continues — accumulate.
                content = stripped[:-1]
                if pending_fenced_line is None:
                    pending_fenced_line = content
                    pending_fenced_lineno = idx
                    # Use fence_preceding so the sentinel placed before the
                    # opening fence is visible to the validator.
                    pending_fenced_preceding = fence_preceding
                else:
                    pending_fenced_line += content
            else:
                # No continuation — flush accumulated + current.
                if pending_fenced_line is not None:
                    combined = pending_fenced_line + stripped
                    _emit_fenced(combined, pending_fenced_lineno, pending_fenced_preceding)
                    pending_fenced_line = None
                else:
                    # Pass fence_preceding (the line before the opening fence)
                    # rather than prev_nonblank (which is the fence delimiter itself).
                    _emit_fenced(stripped, idx, fence_preceding)
            if raw.strip():
                prev_nonblank = raw
            continue

        # --- Outside fenced blocks: scan inline-code spans ---
        for m_inline in _INLINE_CODE_RE.finditer(raw):
            span_content = m_inline.group(1)
            span_start = m_inline.start(1)
            # Find cortex-* binary in the span.
            for m_bin in _BINARY_RE.finditer(span_content):
                binary = m_bin.group(0)
                left_ctx = span_content[:m_bin.start()]
                raw_tail = span_content[m_bin.end():]
                # R1: Command-position guard — skip if not a genuine invocation.
                if not _is_invocation(left_ctx, binary, raw_tail):
                    continue
                col = span_start + m_bin.start()
                tail_tokens = _tokenize_tail(raw_tail)
                # Edge Case 5 / symmetric with fenced: bare-name (no tail tokens) skipped.
                if not tail_tokens:
                    continue
                invocations.append(Invocation(
                    path=path,
                    line=idx,
                    col=col,
                    binary=binary,
                    tail_tokens=tail_tokens,
                    fence_kind="inline",
                    preceding_line=prev_nonblank,
                ))

        if raw.strip():
            prev_nonblank = raw

    # Flush any unclosed continuation at EOF.
    if pending_fenced_line is not None:
        _emit_fenced(pending_fenced_line, pending_fenced_lineno, pending_fenced_preceding)

    return invocations


def scan_corpus(
    root: Path,
    paths: Iterable[Path] | None = None,
) -> list[Invocation]:
    """Walk the scan corpus and return all detected cortex-* invocations.

    Parameters
    ----------
    root:
        Repository root used to resolve scan globs and exclusions.
    paths:
        Explicit path list to scan instead of the default glob walk.
        Hard-exclusion filtering is still applied.  Useful for staged-mode
        scanning where the caller already has the path list.

    Returns
    -------
    list[Invocation]
        All invocations found in fenced code blocks or inline-code spans.
        Prose mentions (bare binary name outside code context) are omitted.
    """
    if paths is not None:
        candidates: list[Path] = []
        seen: set[Path] = set()
        for p in paths:
            rp = p.resolve()
            if rp in seen:
                continue
            try:
                rel = str(p.relative_to(root))
            except ValueError:
                rel = str(p)
            if _is_hard_excluded(rel):
                continue
            seen.add(rp)
            candidates.append(p)
    else:
        candidates = _gather_corpus_paths(root)

    all_invocations: list[Invocation] = []
    for p in candidates:
        all_invocations.extend(_scan_file_for_invocations(p))
    return all_invocations


# ---------------------------------------------------------------------------
# tomllib helpers (mirrors cortex_command/parity_check.py:gather_entry_point_names)
# ---------------------------------------------------------------------------


def _load_project_scripts(pyproject_path: Path) -> dict[str, str]:
    """Return the ``[project.scripts]`` mapping or empty dict on any error."""
    if not pyproject_path.is_file():
        return {}
    try:
        with open(pyproject_path, "rb") as fh:
            data = tomllib.load(fh)
        scripts = data.get("project", {}).get("scripts", {})
        return scripts if isinstance(scripts, dict) else {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Module path resolution (importlib.util — no import)
# ---------------------------------------------------------------------------


def _resolve_module_path(module_attr: str) -> Path | None:
    """Resolve ``module.path:attr`` to an absolute source path.

    Uses ``importlib.util.find_spec()`` which does NOT import the module;
    reads ``spec.origin`` for the file path.  Returns ``None`` if the spec
    cannot be found or has no origin.
    """
    if ":" not in module_attr:
        return None
    module_name, _attr = module_attr.split(":", 1)
    try:
        spec = importlib.util.find_spec(module_name)
    except (ModuleNotFoundError, ValueError):
        return None
    if spec is None or spec.origin is None:
        return None
    return Path(spec.origin)


# ---------------------------------------------------------------------------
# AST walking helpers
# ---------------------------------------------------------------------------


def _is_argument_parser_call(node: ast.Call) -> bool:
    """Return True if ``node`` looks like ``argparse.ArgumentParser(...)``."""
    func = node.func
    if isinstance(func, ast.Attribute):
        # argparse.ArgumentParser(...)
        if func.attr == "ArgumentParser":
            return True
    elif isinstance(func, ast.Name):
        # ArgumentParser(...) after ``from argparse import ArgumentParser``
        if func.id == "ArgumentParser":
            return True
    return False


def _method_name(node: ast.Call) -> str | None:
    """Return the method name if the call is a method call, else None."""
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _extract_string_arg(args: list[ast.expr], keywords: list[ast.keyword],
                         keyword_name: str, positional_index: int = 0) -> str | None:
    """Extract a string literal from positional or keyword argument."""
    # Try keyword first
    for kw in keywords:
        if kw.arg == keyword_name:
            if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                return kw.value.value
    # Try positional
    if positional_index < len(args):
        a = args[positional_index]
        if isinstance(a, ast.Constant) and isinstance(a.value, str):
            return a.value
    return None


def _is_required(keywords: list[ast.keyword]) -> bool:
    """Return True if ``required=True`` is explicitly in the keyword args."""
    for kw in keywords:
        if kw.arg == "required":
            if isinstance(kw.value, ast.Constant):
                return bool(kw.value.value)
    return False


def _extract_flags_from_add_argument(node: ast.Call) -> tuple[list[str], bool]:
    """Return (flag_names, is_required) from an ``add_argument(...)`` call.

    Only collects long-form ``--flag`` and short-form ``-f`` names.
    Positional arguments (no leading ``-``) are ignored for flag validation.
    """
    flags: list[str] = []
    for arg in node.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            val = arg.value
            if val.startswith("-"):
                flags.append(val)
    required = _is_required(node.keywords)
    return flags, required


# ---------------------------------------------------------------------------
# Multi-parser disambiguation
# ---------------------------------------------------------------------------


@dataclass
class _ParserNode:
    """Tracks an ArgumentParser variable assignment and its add_argument count."""

    assign_target: str | None  # variable name, e.g. "parser", or None for inline
    add_argument_count: int = 0
    flags_required: list[tuple[list[str], bool]] = field(default_factory=list)
    subparser_var: str | None = None
    # Subparser choices: name -> list of (flags, required) pairs
    subparser_choices: dict[str, list[tuple[list[str], bool]]] = field(default_factory=dict)


def _collect_parser_nodes(tree: ast.Module) -> list[_ParserNode]:
    """Walk the AST and collect ArgumentParser instances.

    Strategy:
    - Walk all nodes looking for ``argparse.ArgumentParser(...)`` constructor calls.
    - Track variable assignments so we can identify which ``.add_argument``
      calls belong to which parser.
    - Also track ``.add_subparsers()`` and subparser ``.add_parser(...)`` calls.

    This is necessarily heuristic for complex modules; the spec says to pick
    the parser with the most ``.add_argument`` calls as the main parser.
    """
    # Phase 1: find all ArgumentParser assignments and inline constructions.
    # We do a single flat walk; subparser tracking is best-effort.
    parsers: list[_ParserNode] = []
    # Map var_name -> _ParserNode for assignment-based tracking.
    var_to_parser: dict[str, _ParserNode] = {}
    # Map subparsers_var -> parser_node for add_subparsers tracking.
    subparsers_var_to_parser: dict[str, _ParserNode] = {}
    # Map subparser_choice_var -> (parent_parser_node, choice_name).
    subparser_choice_to_parser: dict[str, tuple[_ParserNode, str]] = {}

    for node in ast.walk(tree):
        # --- ArgumentParser constructor assignments ---
        if isinstance(node, ast.Assign):
            # Handle: parser = argparse.ArgumentParser(...)
            if isinstance(node.value, ast.Call) and _is_argument_parser_call(node.value):
                target_names: list[str] = []
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        target_names.append(t.id)
                pn = _ParserNode(assign_target=target_names[0] if target_names else None)
                parsers.append(pn)
                for name in target_names:
                    var_to_parser[name] = pn
            # Handle: sub = subparsers.add_parser("name") or similar
            elif isinstance(node.value, ast.Call):
                mn = _method_name(node.value)
                if mn == "add_parser":
                    choice_name = _extract_string_arg(node.value.args, node.value.keywords, "name", 0)
                    # Identify which parent's subparsers object this is called on.
                    func_val = node.value.func
                    if isinstance(func_val, ast.Attribute) and isinstance(func_val.value, ast.Name):
                        sp_var = func_val.value.id
                        if sp_var in subparsers_var_to_parser and choice_name:
                            parent_pn = subparsers_var_to_parser[sp_var]
                            if choice_name not in parent_pn.subparser_choices:
                                parent_pn.subparser_choices[choice_name] = []
                            # Track the variable assigned for this subparser.
                            for t in node.targets:
                                if isinstance(t, ast.Name):
                                    subparser_choice_to_parser[t.id] = (parent_pn, choice_name)
                # Handle: subparsers = parser.add_subparsers(...)
                elif mn == "add_subparsers":
                    func_val = node.value.func
                    if isinstance(func_val, ast.Attribute) and isinstance(func_val.value, ast.Name):
                        parser_var = func_val.value.id
                        if parser_var in var_to_parser:
                            pn = var_to_parser[parser_var]
                            for t in node.targets:
                                if isinstance(t, ast.Name):
                                    subparsers_var_to_parser[t.id] = pn
                                    pn.subparser_var = t.id

        # --- Augmented assignment / annotated assignment with ArgumentParser ---
        elif isinstance(node, ast.AnnAssign):
            if node.value and isinstance(node.value, ast.Call) and _is_argument_parser_call(node.value):
                target_name: str | None = None
                if isinstance(node.target, ast.Name):
                    target_name = node.target.id
                pn = _ParserNode(assign_target=target_name)
                parsers.append(pn)
                if target_name:
                    var_to_parser[target_name] = pn

        # --- Return statements with ArgumentParser constructor ---
        elif isinstance(node, ast.Return):
            if node.value and isinstance(node.value, ast.Call) and _is_argument_parser_call(node.value):
                # Could be ``return argparse.ArgumentParser(...)``; track as unnamed.
                pn = _ParserNode(assign_target=None)
                parsers.append(pn)

        # --- method calls: add_argument, add_subparsers ---
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            mn = _method_name(call)
            if mn == "add_argument":
                func_val = call.func
                if isinstance(func_val, ast.Attribute) and isinstance(func_val.value, ast.Name):
                    receiver = func_val.value.id
                    flags, req = _extract_flags_from_add_argument(call)
                    if flags:
                        if receiver in var_to_parser:
                            var_to_parser[receiver].add_argument_count += 1
                            var_to_parser[receiver].flags_required.append((flags, req))
                        elif receiver in subparser_choice_to_parser:
                            parent_pn, choice_name = subparser_choice_to_parser[receiver]
                            parent_pn.subparser_choices[choice_name].append((flags, req))
            elif mn == "add_subparsers":
                func_val = call.func
                if isinstance(func_val, ast.Attribute) and isinstance(func_val.value, ast.Name):
                    parser_var = func_val.value.id
                    if parser_var in var_to_parser:
                        # Inline (not assigned): just note it.
                        pass

    # Phase 2: handle inline add_argument on return-type parsers or chained.
    # For unnamed (return-based) parsers, attribute calls are harder to track;
    # we do best-effort by looking for any add_argument calls whose receiver
    # is not tracked.

    return parsers


def _pick_main_parser(parsers: list[_ParserNode]) -> tuple[_ParserNode | None, bool]:
    """Pick the main parser (most add_argument calls).

    Returns (parser_node, is_ambiguous).  ``is_ambiguous`` is True iff there
    are ≥2 parsers tied for the maximum count.
    """
    if not parsers:
        return None, False
    max_count = max(p.add_argument_count for p in parsers)
    candidates = [p for p in parsers if p.add_argument_count == max_count]
    if len(candidates) > 1:
        return candidates[0], True
    return candidates[0], False


# ---------------------------------------------------------------------------
# Surface builder
# ---------------------------------------------------------------------------


def _build_surface(binary: str, module_path: Path, main_pn: _ParserNode) -> ParserSurface:
    """Build a ParserSurface from a _ParserNode."""
    required_flags: set[str] = set()
    optional_flags: set[str] = set()

    for flags, req in main_pn.flags_required:
        for flag in flags:
            if req:
                required_flags.add(flag)
            else:
                optional_flags.add(flag)

    # Subcommands
    subcommands: dict[str, ParserSurface] = {}
    for choice_name, choice_flags in main_pn.subparser_choices.items():
        sub_required: set[str] = set()
        sub_optional: set[str] = set()
        for flags, req in choice_flags:
            for flag in flags:
                if req:
                    sub_required.add(flag)
                else:
                    sub_optional.add(flag)
        subcommands[choice_name] = ParserSurface(
            binary=binary,
            module_path=module_path,
            required_flags=sub_required,
            optional_flags=sub_optional,
            extraction_status="ok",
        )

    return ParserSurface(
        binary=binary,
        module_path=module_path,
        required_flags=required_flags,
        optional_flags=optional_flags,
        subcommands=subcommands,
        extraction_status="ok",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_surface(
    root: Path | None = None,
) -> tuple[dict[str, ParserSurface], list[ExtractionError]]:
    """Extract the argparse surface for all ``cortex-*`` console scripts.

    Reads ``[project.scripts]`` from ``pyproject.toml`` at ``root``,
    resolves each entry to a source path via ``importlib.util.find_spec``,
    parses with ``ast``, and returns a mapping of binary name → ParserSurface.

    Returns:
        (surface_map, extraction_errors)
        ``surface_map`` contains entries for all scripts, including those with
        ``extraction_status != "ok"``.  ``extraction_errors`` lists E201/E202
        errors for diagnostics.
    """
    if root is None:
        root = Path.cwd()
    root = root.resolve()

    pyproject = root / "pyproject.toml"
    scripts = _load_project_scripts(pyproject)

    surface_map: dict[str, ParserSurface] = {}
    errors: list[ExtractionError] = []

    for binary, module_attr in sorted(scripts.items()):
        if not binary.startswith("cortex-"):
            continue

        # Resolve to source path
        module_path = _resolve_module_path(module_attr)
        if module_path is None:
            # Can't resolve — treat as not_argparse without emitting E201
            # (the module may not be importlib-visible, e.g. wrong venv).
            placeholder_path = root / "cortex_command" / "_unresolved.py"
            surface_map[binary] = ParserSurface(
                binary=binary,
                module_path=placeholder_path,
                extraction_status="not_argparse",
            )
            continue

        # Read and parse source
        try:
            source = module_path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(ExtractionError(
                binary=binary,
                code="E201",
                message=f"cannot AST-parse module source for {binary} at path {module_path}: {exc}",
            ))
            surface_map[binary] = ParserSurface(
                binary=binary,
                module_path=module_path,
                extraction_status="ast_error",
            )
            continue

        try:
            tree = ast.parse(source, filename=str(module_path))
        except SyntaxError as exc:
            errors.append(ExtractionError(
                binary=binary,
                code="E201",
                message=f"cannot AST-parse module source for {binary} at path {module_path}: {exc}",
            ))
            surface_map[binary] = ParserSurface(
                binary=binary,
                module_path=module_path,
                extraction_status="ast_error",
            )
            continue

        # Walk for parser nodes
        parser_nodes = _collect_parser_nodes(tree)

        if not parser_nodes:
            # No ArgumentParser found — module uses different argv handling.
            surface_map[binary] = ParserSurface(
                binary=binary,
                module_path=module_path,
                extraction_status="not_argparse",
            )
            continue

        main_pn, is_ambiguous = _pick_main_parser(parser_nodes)

        if is_ambiguous:
            errors.append(ExtractionError(
                binary=binary,
                code="E202",
                message=f"ambiguous main parser for {binary} (tied add_argument counts)",
            ))
            surface_map[binary] = ParserSurface(
                binary=binary,
                module_path=module_path,
                extraction_status="ambiguous",
            )
            continue

        assert main_pn is not None
        surface = _build_surface(binary, module_path, main_pn)
        surface_map[binary] = surface

    return surface_map, errors


# ---------------------------------------------------------------------------
# Convenience wrapper (for backwards compat with the spec's single-return form)
# ---------------------------------------------------------------------------


def extract_surface_map(root: Path | None = None) -> dict[str, ParserSurface]:
    """Return only the surface map (discards extraction errors).

    Convenience wrapper used by tests and callers that don't need to inspect
    individual extraction errors.
    """
    surface_map, _errors = extract_surface(root)
    return surface_map


# ---------------------------------------------------------------------------
# Sentinel marker
# ---------------------------------------------------------------------------

_SENTINEL_RE = re.compile(r"<!--\s*contract-lint:ignore-next\s*-->")


def _has_sentinel(preceding_line: str | None) -> bool:
    """Return True if the preceding non-blank line matches the sentinel marker.

    The sentinel pattern is ``<!-- contract-lint:ignore-next -->`` with
    optional internal whitespace (``\\s*`` on each side of the keyword).
    An HTML comment placed on any line immediately before a fenced code
    block or inline invocation suppresses the next invocation from
    violation emission.
    """
    if preceding_line is None:
        return False
    return bool(_SENTINEL_RE.search(preceding_line))


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


def validate(
    invocations: list[Invocation],
    surface: dict[str, ParserSurface],
    exceptions: ExceptionLedger,
) -> list[Violation]:
    """Validate a list of invocations against the extracted parser surfaces.

    For each invocation the validator:

    1. Skips if the preceding non-blank line contains the sentinel marker.
    2. Skips if the binary is not in ``surface`` or the surface has a non-ok
       extraction status (module is not argparse-shaped or had an extraction
       error).
    3. Tokenizes ``tail_tokens`` with ``shlex.split(comments=False)`` when not
       already split (the scanner delivers pre-tokenized tokens, so this is a
       safety re-split on joined strings — in practice the list is already
       split and is joined then re-split to normalise shell quoting).
    4. Classifies tokens as:
       - subcommand: a positional that matches a subcommand choice in the
         resolved surface (only when the parser has subcommands).
       - flag: any token starting with ``-``.
       - value: any other token (flag value, positional argument).
    5. Skips value-shape validation on templated placeholders
       (``{{...}}``, ``{...}``, ``<...>``).
    6. Validates:
       (a) Every observed flag exists in the accepted set → E102.
       (b) Every ``required=True`` flag is present → E101.
       (c) The resolved surface has subcommands and none is supplied AND the
           subparser is required → E103.

    Exception-ledger suppression is applied per flag/subcommand.
    """
    violations: list[Violation] = []

    for inv in invocations:
        # Sentinel marker suppression.
        if _has_sentinel(inv.preceding_line):
            continue

        # Skip if binary has no surface (not in [project.scripts] — not the
        # lint's concern; could be a third-party CLI).
        surf = surface.get(inv.binary)
        if surf is None:
            continue

        # Binary is in [project.scripts] but extraction failed/skipped. Require
        # an explicit ledger entry to suppress; otherwise emit E104 so the
        # operator either documents the exemption or fixes the parser.
        if surf.extraction_status != "ok":
            if not exceptions.match(inv.binary, "*", str(inv.path)):
                violations.append(
                    Violation(
                        path=str(inv.path),
                        line=inv.line,
                        col=inv.col,
                        code="E104",
                        message=(
                            f"{inv.binary} extraction_status="
                            f"{surf.extraction_status} requires an explicit "
                            f"bin/.contract-lint-exceptions.md entry to suppress"
                        ),
                    )
                )
            continue

        path_str = str(inv.path)

        # Re-tokenize via shlex for shell-quoting normalisation.  The scanner
        # stores tokens pre-split, so join then re-split is idempotent for
        # well-formed input but normalises quoted values.
        raw_tail = " ".join(inv.tail_tokens)
        try:
            tokens = shlex.split(raw_tail, comments=False)
        except ValueError:
            # Unclosed quote or similar — fall back to pre-split tokens.
            tokens = list(inv.tail_tokens)

        # Resolve subcommand: look for the first positional that matches a
        # known subcommand choice.
        resolved_surface = surf
        found_subcommand: str | None = None
        if surf.subcommands:
            for tok in tokens:
                if not tok.startswith("-") and not _PLACEHOLDER_RE.fullmatch(tok):
                    if tok in surf.subcommands:
                        found_subcommand = tok
                        resolved_surface = surf.subcommands[tok]
                        break

        # Collect observed flags from the token list.
        observed_flags: list[str] = []
        for tok in tokens:
            if tok.startswith("-") and not _PLACEHOLDER_RE.fullmatch(tok):
                # Strip value part from --flag=value form.
                flag_part = tok.split("=", 1)[0]
                observed_flags.append(flag_part)

        # Accepted flag set for the resolved surface.
        accepted_flags: set[str] = (
            resolved_surface.required_flags | resolved_surface.optional_flags
        )

        # (a) Unknown flags → E102.
        for flag in observed_flags:
            if flag not in accepted_flags:
                if not exceptions.match(inv.binary, flag, path_str):
                    violations.append(Violation(
                        path=path_str,
                        line=inv.line,
                        col=inv.col,
                        code="E102",
                        message=f"unknown flag {flag} for {inv.binary}",
                    ))

        # (b) Missing required flags → E101.
        for req_flag in sorted(resolved_surface.required_flags):
            # Check whether any observed flag matches (long or short form).
            # For simplicity, exact match only (--flag); short-form aliases
            # are in optional_flags/required_flags as declared in the parser.
            if req_flag not in observed_flags:
                # Skip if any token is a placeholder (could supply the flag).
                has_placeholder_flags = any(
                    _PLACEHOLDER_RE.fullmatch(tok) for tok in tokens
                )
                if not has_placeholder_flags:
                    if not exceptions.match(inv.binary, req_flag, path_str):
                        violations.append(Violation(
                            path=path_str,
                            line=inv.line,
                            col=inv.col,
                            code="E101",
                            message=f"missing required flag {req_flag} for {inv.binary}",
                        ))

        # (c) Missing required subcommand → E103.
        if surf.subcommands and found_subcommand is None:
            # Check if any token is a placeholder (could be the subcommand).
            has_placeholder_positional = any(
                _PLACEHOLDER_RE.fullmatch(tok)
                for tok in tokens
                if not tok.startswith("-")
            )
            if not has_placeholder_positional:
                if not exceptions.match(inv.binary, "<subcommand>", path_str):
                    violations.append(Violation(
                        path=path_str,
                        line=inv.line,
                        col=inv.col,
                        code="E103",
                        message=f"missing required subcommand for {inv.binary}",
                    ))

    return violations


# ---------------------------------------------------------------------------
# Staged-mode helpers
# ---------------------------------------------------------------------------


def _staged_paths(root: Path) -> list[str]:
    """Return relative paths of staged files."""
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=str(root),
            capture_output=True,
            check=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [ln for ln in out.stdout.splitlines() if ln]


def _read_staged_blob(rel_path: str, root: Path) -> bytes | None:
    """Return the staged blob bytes for ``rel_path``, or None."""
    try:
        out = subprocess.run(
            ["git", "show", f":{rel_path}"],
            cwd=str(root),
            capture_output=True,
            check=True,
        )
        return out.stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _scan_staged(root: Path) -> list[Invocation]:
    """Scan staged files and return invocations from their staged blobs."""
    import tempfile

    invocations: list[Invocation] = []
    for rel in _staged_paths(root):
        # Filter to scan-glob paths only.  _in_scan_scope uses a regex-based
        # recursive matcher that treats ** as zero-or-more segments, so
        # depth-1 and depth-≥3 in-scope files are admitted correctly on
        # Python 3.12+ (PurePath.match treats ** as exactly one segment).
        if not _in_scan_scope(rel):
            continue
        if _is_hard_excluded(rel):
            continue

        blob = _read_staged_blob(rel, root)
        if blob is None:
            continue

        # Write blob to a temp file so _scan_file_for_invocations can read it.
        rel_path = Path(rel)
        suffix = rel_path.suffix or ".md"
        with tempfile.NamedTemporaryFile(
            suffix=suffix, delete=False, mode="wb"
        ) as fh:
            fh.write(blob)
            tmp_path = Path(fh.name)

        try:
            file_invs = _scan_file_for_invocations(tmp_path)
            # Fix up path to the real relative path.
            real_path = root / rel
            patched: list[Invocation] = []
            for inv in file_invs:
                patched.append(Invocation(
                    path=real_path,
                    line=inv.line,
                    col=inv.col,
                    binary=inv.binary,
                    tail_tokens=inv.tail_tokens,
                    fence_kind=inv.fence_kind,
                    preceding_line=inv.preceding_line,
                ))
            invocations.extend(patched)
        finally:
            try:
                tmp_path.unlink()
            except OSError:
                pass

    return invocations


# ---------------------------------------------------------------------------
# CLI (full implementation for Task 3)
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    import argparse as _argparse

    p = _argparse.ArgumentParser(
        prog="cortex-check-contract",
        description="Skill-prose to CLI argparse contract lint",
    )
    p.add_argument("--root", default=None,
                   help="Repository root (default: cwd)")
    p.add_argument("--json", dest="as_json", action="store_true",
                   help="Emit violations as a JSON array")
    p.add_argument("--self-test", action="store_true",
                   help="Run inline self-test fixtures and exit")
    p.add_argument("--validate-exceptions", action="store_true",
                   help="Validate the exception ledger format and exit")

    mode_group = p.add_mutually_exclusive_group()
    mode_group.add_argument("--staged", action="store_true",
                            help="Scan git-staged blobs only")
    mode_group.add_argument("--audit", action="store_true",
                            help="Scan the full repo corpus")

    args = p.parse_args(argv)

    # --- --self-test mode ---
    if args.self_test:
        return _run_self_test()

    # --- --validate-exceptions mode ---
    if args.validate_exceptions:
        root = Path(args.root).resolve() if args.root else Path.cwd().resolve()
        ledger_path = root / "bin" / ".contract-lint-exceptions.md"
        violations = validate_exception_ledger(ledger_path)
        if args.as_json:
            print(json.dumps([v.format_json_dict() for v in violations]))
        else:
            for v in violations:
                print(v.format_text())
        return 1 if violations else 0

    root = Path(args.root).resolve() if args.root else Path.cwd().resolve()

    # --- Extract surface ---
    surface_map, extraction_errors = extract_surface(root)

    # Configuration error: every module failed to extract.
    if surface_map and all(
        s.extraction_status in ("ast_error",) for s in surface_map.values()
    ):
        for err in extraction_errors:
            print(err.format_text(), file=sys.stderr)
        return 2

    # Emit extraction errors to stderr (non-fatal).
    for err in extraction_errors:
        print(err.format_text(), file=sys.stderr)

    # --- Gather invocations ---
    if args.staged:
        invocations = _scan_staged(root)
    else:
        # Default to audit (full corpus) when neither --staged nor --audit is
        # given, so bare invocation without flags still works.
        invocations = scan_corpus(root)

    # --- Validate ---
    ledger_path = root / "bin" / ".contract-lint-exceptions.md"
    ledger = parse_exception_ledger(ledger_path)
    violations = validate(invocations, surface_map, ledger)

    # --- Emit ---
    if args.as_json:
        print(json.dumps([v.format_json_dict() for v in violations]))
    else:
        for v in violations:
            print(v.format_text())

    return 1 if violations else 0


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def _run_self_test() -> int:
    """Run inline self-test fixtures; return 0 on pass, 1 on fail."""
    import tempfile
    import textwrap

    failures: list[str] = []

    # -----------------------------------------------------------------------
    # Fixture A: AST extraction — verify _collect_parser_nodes / _build_surface
    # -----------------------------------------------------------------------
    sample_source = textwrap.dedent("""
        import argparse
        def main():
            parser = argparse.ArgumentParser()
            parser.add_argument("--status", required=True)
            parser.add_argument("--type", required=True)
            parser.add_argument("--title", required=True)
            parser.add_argument("--priority", default="low")
    """)

    try:
        tree = ast.parse(sample_source)
    except SyntaxError as exc:
        failures.append(f"self-test A: sample parse failed: {exc}")
    else:
        pnodes = _collect_parser_nodes(tree)
        if not pnodes:
            failures.append("self-test A: no parser nodes found in sample")
        else:
            main_pn, ambiguous = _pick_main_parser(pnodes)
            if ambiguous:
                failures.append("self-test A: unexpected ambiguity in sample parser")
            elif main_pn is None:
                failures.append("self-test A: main_pn is None for sample")
            else:
                surf = _build_surface("cortex-test", Path("/dev/null"), main_pn)
                if "--status" not in surf.required_flags:
                    failures.append(f"self-test A: --status not in required_flags: {surf.required_flags}")
                if "--type" not in surf.required_flags:
                    failures.append(f"self-test A: --type not in required_flags: {surf.required_flags}")
                if "--title" not in surf.required_flags:
                    failures.append(f"self-test A: --title not in required_flags: {surf.required_flags}")
                if "--priority" not in surf.optional_flags:
                    failures.append(f"self-test A: --priority not in optional_flags: {surf.optional_flags}")

    # -----------------------------------------------------------------------
    # Build a synthetic surface for fixtures B–E (scanner + validator).
    # cortex-selftest requires --status (required) and --type (required);
    # --title is optional.
    # -----------------------------------------------------------------------
    synth_surf = ParserSurface(
        binary="cortex-selftest",
        module_path=Path("/dev/null"),
        required_flags={"--status", "--type"},
        optional_flags={"--title"},
        extraction_status="ok",
    )
    surface_map: dict[str, ParserSurface] = {"cortex-selftest": synth_surf}
    ledger = ExceptionLedger.empty()

    # -----------------------------------------------------------------------
    # Fixture B: fenced code invocation with valid flags → no violations.
    # -----------------------------------------------------------------------
    fence_valid_md = textwrap.dedent("""\
        ```
        cortex-selftest --status ok --type bug
        ```
    """)
    with tempfile.NamedTemporaryFile(
        suffix=".md", delete=False, mode="w", encoding="utf-8"
    ) as fh_b:
        fh_b.write(fence_valid_md)
        path_b = Path(fh_b.name)
    try:
        invs_b = _scan_file_for_invocations(path_b)
        viols_b = validate(invs_b, surface_map, ledger)
        if not invs_b:
            failures.append("self-test B: fenced invocation not detected")
        if viols_b:
            failures.append(f"self-test B: unexpected violations: {viols_b}")
    finally:
        path_b.unlink(missing_ok=True)

    # -----------------------------------------------------------------------
    # Fixture C: fenced code invocation with missing required flag → E101.
    # -----------------------------------------------------------------------
    fence_invalid_md = textwrap.dedent("""\
        ```
        cortex-selftest --title hello
        ```
    """)
    with tempfile.NamedTemporaryFile(
        suffix=".md", delete=False, mode="w", encoding="utf-8"
    ) as fh_c:
        fh_c.write(fence_invalid_md)
        path_c = Path(fh_c.name)
    try:
        invs_c = _scan_file_for_invocations(path_c)
        viols_c = validate(invs_c, surface_map, ledger)
        e101_codes = [v for v in viols_c if v.code == "E101"]
        if not invs_c:
            failures.append("self-test C: fenced invocation not detected")
        if len(e101_codes) < 2:
            failures.append(
                f"self-test C: expected ≥2 E101 violations, got {viols_c}"
            )
    finally:
        path_c.unlink(missing_ok=True)

    # -----------------------------------------------------------------------
    # Fixture D: inline-code invocation with valid flags → no violations.
    # -----------------------------------------------------------------------
    inline_valid_md = "Run `cortex-selftest --status ok --type bug` to check.\n"
    with tempfile.NamedTemporaryFile(
        suffix=".md", delete=False, mode="w", encoding="utf-8"
    ) as fh_d:
        fh_d.write(inline_valid_md)
        path_d = Path(fh_d.name)
    try:
        invs_d = _scan_file_for_invocations(path_d)
        viols_d = validate(invs_d, surface_map, ledger)
        if not invs_d:
            failures.append("self-test D: inline-code invocation not detected")
        if viols_d:
            failures.append(f"self-test D: unexpected violations: {viols_d}")
    finally:
        path_d.unlink(missing_ok=True)

    # -----------------------------------------------------------------------
    # Fixture E: prose mention only → scanner must skip it (no invocations).
    # -----------------------------------------------------------------------
    prose_only_md = "The cortex-selftest helper is documented elsewhere.\n"
    with tempfile.NamedTemporaryFile(
        suffix=".md", delete=False, mode="w", encoding="utf-8"
    ) as fh_e:
        fh_e.write(prose_only_md)
        path_e = Path(fh_e.name)
    try:
        invs_e = _scan_file_for_invocations(path_e)
        if invs_e:
            failures.append(
                f"self-test E: prose mention must not produce invocations, got {invs_e}"
            )
    finally:
        path_e.unlink(missing_ok=True)

    if failures:
        for f in failures:
            print(f"FAIL {f}", file=sys.stderr)
        return 1
    print("self-test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
