"""cortex-append-glossary-term — the file I/O for requirements-gather's
per-term glossary write.

requirements-gather/SKILL.md's "Glossary writes" section describes a
probe-before-classify, append-after-gate flow against
`cortex/requirements/glossary.md`'s `## Language` section: before the binary
classifier and user-confirmation gate ever run, the skill must check whether
the term is already documented (a found entry short-circuits classify/gate
entirely — it was vetted the first time it was written); only an absent term
reaches classify/gate, and only a term that passes both is ever written.
This verb owns both mechanical halves of that flow — the read-only probe and
the guarded write — as two modes of one call, selected by whether
`--definition` is given:

  - `--term` alone (no `--definition`) is a pure probe: read-only, never
    writes, reports whether the term is already documented.
  - `--term` + `--definition` is the guarded write: append when absent,
    replace when present and `--replace` is given, otherwise a safe no-op
    that reports the existing text back.

The skill keeps every judgment call the verb cannot make — the binary
classifier (is this term genuinely project-specific vocabulary?), the
user-confirmation gate, and, on a conflict between an existing entry and a
new candidate, which of keep/replace/flag-as-ambiguity the user picked. It
calls this verb only at the two points those judgments allow a filesystem
operation: the up-front probe (always safe — read-only) and the write
(only after classify+gate pass, or after the user picks "replace").

File shape: a lazily-created `cortex/requirements/glossary.md` with a
`## Language` H2 whose body is one bold-led bullet per term:

    - **{term}**: {definition}

This is the only section this verb reads or writes. The
add-project-glossary-at-cortex-requirements spec names three further
sections (`## Relationships`, `## Example dialogue`, `## Flagged
ambiguities`) as existing-reasoning territory critical-review must not read;
nothing in this repo's producer/consumer machinery populates them, so this
verb does not create or touch them — a human curates those manually if they
ever add content there.

Term matching is case-insensitive on the bold term text (`Phase Transition`
and `phase transition` are the same entry) so a differently-cased re-ask
during a later interview does not create a duplicate bullet.

States:
  found     — (probe mode only) the term is already documented; `definition`
              carries its existing text. No write occurs.
  not-found — (probe mode only) the term is not yet documented. No write
              occurs — classify/gate must run before any write is attempted.
  appended  — (write mode) the term was absent; a new bullet was written
              (creating the file and/or the `## Language` section first if
              this is the first entry). `definition` echoes the
              just-written text.
  existed   — (write mode) the term was already present and `--replace` was
              not given; the file is left untouched. `definition` carries
              the EXISTING bullet's text (not the caller's candidate) so the
              caller can compare the two and drive its keep/replace/
              flag-ambiguity choice. Reachable even after a probe reported
              `not-found`, if another write raced between the two calls —
              this is the safety net that keeps write mode from ever
              silently clobbering an entry without `--replace`.
  replaced  — (write mode) the term was already present and `--replace` was
              given; its bullet's definition was rewritten in place.
              `definition` echoes the new text.
  error     — an unexpected exception (unresolvable project root, glossary
              I/O failure) escaped the call; `message` carries the
              diagnostic. Never raises — see `append_glossary_term`.

This verb never emits an events.log row: per the originating spec's
Non-Requirements, glossary writes are audited post-hoc via
`git log -- cortex/requirements/glossary.md`, not an events-registry entry.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from cortex_command.backlog import _telemetry
from cortex_command.common import (
    CortexProjectRootError,
    _resolve_user_project_root_from_cwd,
    atomic_write,
)

KNOWN_STATES = ("found", "not-found", "appended", "existed", "replaced", "error")

GLOSSARY_RELPATH = Path("cortex") / "requirements" / "glossary.md"
LANGUAGE_HEADING = "## Language"


def _entry_pattern(term: str) -> re.Pattern:
    return re.compile(r"^-\s+\*\*" + re.escape(term) + r"\*\*:\s*(.*)$", re.IGNORECASE)


def _resolve_glossary_path(
    glossary_path: Optional[Path], project_root: Optional[Path]
) -> Path:
    if glossary_path is not None:
        return glossary_path
    root = project_root or _resolve_user_project_root_from_cwd()
    return root / GLOSSARY_RELPATH


def _section_bounds(lines: List[str], heading: str) -> Optional[Tuple[int, int]]:
    """Return `(start, end)` exclusive body bounds of `heading`, else None.

    `start` is the index right after the heading line; `end` is the index of
    the next H1/H2 line, or `len(lines)`.
    """
    for i, line in enumerate(lines):
        if line.strip() == heading:
            end = len(lines)
            for j in range(i + 1, len(lines)):
                s = lines[j].strip()
                if s.startswith("# ") or s.startswith("## "):
                    end = j
                    break
            return i + 1, end
    return None


def _insert_bullet(lines: List[str], start: int, end: int, bullet: str) -> List[str]:
    """Insert `bullet` as the last line of the `[start, end)` section body.

    Walks back past trailing blank lines so the bullet lands directly after
    the section's last existing bullet (or directly after the heading, if
    the section was empty) rather than after a blank-line gap that precedes
    the next heading.
    """
    insert_at = end
    while insert_at > start and lines[insert_at - 1].strip() == "":
        insert_at -= 1
    return lines[:insert_at] + [bullet] + lines[insert_at:]


def _find_existing(text: str, term: str) -> Optional[str]:
    """Return the existing bullet's definition text, or None if absent."""
    lines = text.splitlines()
    pattern = _entry_pattern(term)
    bounds = _section_bounds(lines, LANGUAGE_HEADING)
    if bounds is None:
        return None
    start, end = bounds
    for i in range(start, end):
        m = pattern.match(lines[i].strip())
        if m:
            return m.group(1)
    return None


def append_glossary_term(
    term: str,
    definition: Optional[str] = None,
    *,
    glossary_path: Optional[Path] = None,
    project_root: Optional[Path] = None,
    replace: bool = False,
) -> dict:
    """Probe (definition=None) or guarded-write (definition given) `term`.

    Never raises — every failure mode is returned as an `"error"` state (see
    the module docstring).
    """
    try:
        path = _resolve_glossary_path(glossary_path, project_root)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            text = ""

        if definition is None:
            existing = _find_existing(text, term)
            if existing is None:
                return {"state": "not-found", "term": term}
            return {"state": "found", "term": term, "definition": existing}

        lines = text.splitlines()
        pattern = _entry_pattern(term)
        bullet = f"- **{term}**: {definition}"

        bounds = _section_bounds(lines, LANGUAGE_HEADING)
        if bounds is not None:
            start, end = bounds
            for i in range(start, end):
                m = pattern.match(lines[i].strip())
                if m:
                    if not replace:
                        return {
                            "state": "existed",
                            "term": term,
                            "definition": m.group(1),
                        }
                    lines[i] = bullet
                    atomic_write(path, "\n".join(lines) + "\n")
                    return {"state": "replaced", "term": term, "definition": definition}
            new_lines = _insert_bullet(lines, start, end, bullet)
            atomic_write(path, "\n".join(new_lines) + "\n")
            return {"state": "appended", "term": term, "definition": definition}

        # No `## Language` section yet — append one (creating the file
        # itself too, if it did not exist) at the end of the document.
        block: List[str] = []
        if text.strip():
            block.append(text.rstrip("\n"))
            block.append("")
        else:
            block.append("# Glossary")
            block.append("")
        block.append(LANGUAGE_HEADING)
        block.append("")
        block.append(bullet)
        atomic_write(path, "\n".join(block) + "\n")
        return {"state": "appended", "term": term, "definition": definition}
    except CortexProjectRootError as exc:
        return {
            "state": "error",
            "message": f"could not resolve the project root: {exc}",
        }
    except OSError as exc:
        return {"state": "error", "message": f"glossary I/O failed: {exc}"}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-append-glossary-term",
        description=(
            "Probe or guarded-write cortex/requirements/glossary.md's "
            "## Language section for --term, emitting a {state, ...} JSON "
            "struct on stdout (always exit 0). Omit --definition for a "
            "read-only probe (found/not-found); pass it for a guarded write "
            "(appended/existed/replaced)."
        ),
    )
    parser.add_argument("--term", required=True, help="The glossary term (bold text).")
    parser.add_argument(
        "--definition",
        default=None,
        help=(
            "The candidate definition text. Omit to run a read-only probe "
            "instead of a write."
        ),
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help=(
            "When the term already exists, overwrite its definition in "
            "place instead of returning state 'existed' untouched."
        ),
    )
    parser.add_argument(
        "--glossary-path",
        default=None,
        help=(
            "Explicit glossary.md path (ADR-0019 caller-passed input). "
            "Takes precedence over --project-root."
        ),
    )
    parser.add_argument(
        "--project-root",
        default=None,
        help=(
            "Project root under which cortex/requirements/glossary.md is "
            "resolved; defaults to auto-resolution from cwd."
        ),
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _telemetry.log_invocation("cortex-append-glossary-term")
    args = _build_parser().parse_args(argv)
    glossary_path = Path(args.glossary_path) if args.glossary_path else None
    project_root = Path(args.project_root) if args.project_root else None
    result = append_glossary_term(
        args.term,
        args.definition,
        glossary_path=glossary_path,
        project_root=project_root,
        replace=args.replace,
    )
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
