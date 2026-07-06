"""cortex-list-requirements — the requirements orchestrator's `list` inventory.

Replaces `requirements/SKILL.md` step 1's hand-executed scan of
`cortex/requirements/*.md` (build a file/scope/last-gathered/requirement-count
table, excluding `glossary.md`) with a deterministic verb. The skill still
owns rendering the returned rows into a table and the absent-directory
copy — this verb only reads the filesystem and computes the four columns.

Column derivation:
  file              — repo-relative path, `cortex/requirements/<name>.md`.
  scope             — `"project"` for `project.md`; the filename stem
                      (the area slug) for every other doc.
  last_gathered     — the date parsed from the doc's leading
                      `> Last gathered: {YYYY-MM-DD}` blockquote (both
                      templates in requirements-write/SKILL.md open with this
                      line). A trailing `(updated ...)` annotation, as seen in
                      this repo's own `project.md`, is ignored — only the
                      first YYYY-MM-DD token counts. `null` when the doc has
                      no such line (malformed/hand-edited doc).
  requirement_count — count of markdown bullet-list lines (`^\\s*-\\s+`)
                      anywhere in the doc. Chosen over an H2/H3 count: every
                      doc following the templates carries a FIXED number of
                      H2s (8 for project, 7 for area) regardless of content,
                      so an H2 count would be a constant, not a signal: it
                      would never distinguish a thin doc from a thorough one.
                      Bullets are where both templates put their actual
                      content (bold-led bullets for principles/constraints,
                      nested bullets for Functional/Non-Functional
                      Requirements and Edge Cases), so a bullet count varies
                      meaningfully doc-to-doc and is a reasonable proxy for
                      "how much has been captured" without requiring a
                      section-aware parser.

`glossary.md` is excluded unconditionally (it is the producer-managed
vocabulary artifact, not a scope-level requirements doc — see
requirements/SKILL.md's `list` argument-shape note).

States:
  ok                  — `rows` is the (possibly empty) list of table rows,
                        one per non-glossary `cortex/requirements/*.md` file,
                        sorted by filename.
  absent              — the resolved requirements directory does not exist.
                        `rows` is `[]`; the skill owns the user-facing copy
                        for this case (requirements/SKILL.md step 1).
  project-root-error  — neither `--requirements-dir` nor `--project-root` was
                        given and the project root could not be resolved
                        from cwd; `message` carries the diagnostic.
  error               — an unexpected exception escaped `list_requirements`
                        itself; `main` catches it here so the CLI always
                        emits a JSON struct and exits 0 rather than a
                        traceback.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import List, Optional

from cortex_command.backlog import _telemetry
from cortex_command.common import (
    CortexProjectRootError,
    _resolve_user_project_root_from_cwd,
)

KNOWN_STATES = ("ok", "absent", "project-root-error", "error")

GLOSSARY_NAME = "glossary.md"
_LAST_GATHERED_RE = re.compile(r"^>\s*Last gathered:\s*(\d{4}-\d{2}-\d{2})")
_BULLET_RE = re.compile(r"^\s*-\s+")


def _scope_for(stem: str) -> str:
    return "project" if stem == "project" else stem


def _last_gathered(text: str) -> Optional[str]:
    for line in text.splitlines():
        m = _LAST_GATHERED_RE.match(line.strip())
        if m:
            return m.group(1)
    return None


def _requirement_count(text: str) -> int:
    return sum(1 for line in text.splitlines() if _BULLET_RE.match(line))


def list_requirements(
    requirements_dir: Optional[Path] = None,
    project_root: Optional[Path] = None,
) -> dict:
    """Return the `{state, rows}` inventory for `requirements_dir`.

    `requirements_dir`, when given, is used verbatim (ADR-0019 caller-passed
    input — no project-root resolution occurs). Otherwise `project_root`
    (or its own auto-resolution from cwd) is resolved and
    `<root>/cortex/requirements` is scanned.
    """
    if requirements_dir is None:
        try:
            root = project_root or _resolve_user_project_root_from_cwd()
        except CortexProjectRootError as exc:
            return {
                "state": "project-root-error",
                "message": f"could not resolve the project root: {exc}",
            }
        requirements_dir = root / "cortex" / "requirements"

    if not requirements_dir.is_dir():
        return {"state": "absent", "rows": []}

    rows: List[dict] = []
    for path in sorted(requirements_dir.glob("*.md")):
        if path.name == GLOSSARY_NAME:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        rows.append(
            {
                "file": f"cortex/requirements/{path.name}",
                "scope": _scope_for(path.stem),
                "last_gathered": _last_gathered(text),
                "requirement_count": _requirement_count(text),
            }
        )
    return {"state": "ok", "rows": rows}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-list-requirements",
        description=(
            "Enumerate cortex/requirements/*.md (excluding glossary.md) and "
            "emit a {state, rows} JSON struct on stdout (always exit 0). "
            "Each row carries file, scope, last_gathered, and "
            "requirement_count."
        ),
    )
    parser.add_argument(
        "--requirements-dir",
        default=None,
        help=(
            "Explicit cortex/requirements/ directory to scan (ADR-0019 "
            "caller-passed input). Takes precedence over --project-root."
        ),
    )
    parser.add_argument(
        "--project-root",
        default=None,
        help=(
            "Project root under which cortex/requirements/ is resolved; "
            "defaults to auto-resolution from cwd."
        ),
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _telemetry.log_invocation("cortex-list-requirements")
    args = _build_parser().parse_args(argv)
    requirements_dir = Path(args.requirements_dir) if args.requirements_dir else None
    project_root = Path(args.project_root) if args.project_root else None
    try:
        result = list_requirements(requirements_dir, project_root)
    except Exception as exc:  # noqa: BLE001 — always emit a JSON struct, never a traceback
        result = {"state": "error", "message": repr(exc)}
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
