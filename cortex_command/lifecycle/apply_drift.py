"""``cortex-lifecycle-apply-drift`` — apply a review's requirements-drift edits.

Review §3a used to have the orchestrator hand-append the reviewer's lines to
the end of a requirements section. Nothing ever replaced or removed a line, so
every ``detected`` review grew a requirements doc. This verb makes the drift
contract an *edit*: each ``## Suggested Requirements Update`` entry names the
existing text it changes (``Replace``) and the text that takes its place
(``With``). An append happens only when the entry says the rule has no
existing home (``Replace: None``).

Entry format, one per drifted file, under ``## Suggested Requirements Update``
in ``cortex/lifecycle/<feature>/review.md``::

    - **File**: cortex/requirements/<doc>.md
    - **Section**: <an existing heading in that file>
    - **Replace**: <exact existing text> | None
    - **With**: <the replacement text> | None

``With: None`` deletes the ``Replace`` text. A value may span lines; it runs to
the next field or heading. ``**File**:`` keeps its shape because
``stage_artifacts`` and ``complete_route`` read it to stage the edited docs.

Output: one JSON struct on stdout, always exit 0::

    {"state": "applied"|"rejected"|"no-section"|"error", "entries": [...], "message": "..."}

``applied`` covers a re-run too: an entry whose ``With`` text is already in the
section and whose ``Replace`` text is gone reports ``already-applied``.
``rejected`` writes nothing — every entry is checked before any file changes —
and ``message`` says what the reviewer must fix. A ``Replace`` that no longer
matches (a concurrent edit, or a paraphrase) is a rejection, never a fallback
append.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from cortex_command.backlog import _telemetry
from cortex_command.common import _resolve_user_project_root_from_cwd

DRIFT_HEADING = "## Suggested Requirements Update"
REQUIREMENTS_DIR = Path("cortex") / "requirements"
FIELDS = ("File", "Section", "Replace", "With")

_FIELD_LINE = re.compile(r"^\s*(?:[-*]\s+)?\*\*(File|Section|Replace|With)\*\*:\s?(.*)$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
# A rule states the current behaviour. A date or "amended" marks change
# history, which belongs in git, not in a doc every lifecycle phase re-reads.
_HISTORY = re.compile(r"\b20\d\d-\d\d-\d\d\b|\bamended\b", re.IGNORECASE)


def _drift_section(review_text: str) -> Optional[List[str]]:
    out: List[str] = []
    found = False
    for line in review_text.splitlines():
        if line.strip().startswith("## "):
            if found:
                break
            found = line.strip() == DRIFT_HEADING
            continue
        if found:
            out.append(line)
    return out if found else None


def _clean(value_lines: List[str]) -> str:
    """Join a field's lines, dropping blank edges and one wrapping code fence."""
    lines = list(value_lines)
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if len(lines) >= 2 and lines[0].strip().startswith("```") and lines[-1].strip() == "```":
        lines = lines[1:-1]
    text = "\n".join(lines)
    return text.strip() if "\n" not in text else text


def _unquote(text: str) -> str:
    """Drop one pair of wrapping backticks — reviewers often quote a value in them."""
    if len(text) >= 2 and text[0] == text[-1] == "`" and "\n" not in text:
        return text[1:-1]
    return text


def parse_entries(review_text: str) -> Optional[List[Dict[str, str]]]:
    """Return the drift entries, or ``None`` when the section is absent."""
    section = _drift_section(review_text)
    if section is None:
        return None
    entries: List[Dict[str, List[str]]] = []
    current: Optional[Dict[str, List[str]]] = None
    field: Optional[str] = None
    fenced = False
    for line in section:
        m = None if fenced else _FIELD_LINE.match(line)
        if m:
            name, rest = m.group(1), m.group(2)
            if name == "File" or current is None:
                current = {}
                entries.append(current)
            current[name] = [rest]
            field = name
        elif field is not None and current is not None:
            # Outside a code fence a blank line ends a value that has content,
            # so the last field never swallows the Verdict JSON block below it.
            if not fenced and not line.strip() and any(v.strip() for v in current[field]):
                field = None
                continue
            if line.strip().startswith("```"):
                fenced = not fenced
            current[field].append(line)
    return [{k: _clean(v) for k, v in e.items()} for e in entries]


def _is_none(value: str) -> bool:
    return value.strip().strip("`\"'.").lower() in ("", "none")


def _section_span(lines: List[str], section: str) -> Optional[Tuple[int, int]]:
    """Line span ``[start, end)`` of the body under the heading named ``section``."""
    want = section.lstrip("#").strip().strip("`").lower()
    for i, line in enumerate(lines):
        m = _HEADING.match(line)
        if not m or m.group(2).strip().lower() != want:
            continue
        level = len(m.group(1))
        end = len(lines)
        for j in range(i + 1, len(lines)):
            n = _HEADING.match(lines[j])
            if n and len(n.group(1)) <= level:
                end = j
                break
        return i + 1, end
    return None


def _plan_entry(entry: Dict[str, str], root: Path, texts: Dict[Path, str]) -> Tuple[str, str]:
    """Check one entry and stage its edit in ``texts``. Returns ``(result, detail)``."""
    missing = [f for f in FIELDS if f not in entry]
    if missing:
        return "rejected", f"entry is missing field(s): {', '.join(missing)}"
    rel = entry["File"].strip().strip("`")
    path = (root / rel).resolve()
    allowed = (root / REQUIREMENTS_DIR).resolve()
    if allowed not in path.parents or path.suffix != ".md":
        return "rejected", f"File `{rel}` is not a doc under {REQUIREMENTS_DIR}/"
    if path not in texts:
        if not path.is_file():
            return "rejected", f"File `{rel}` does not exist"
        texts[path] = path.read_text(encoding="utf-8")

    replace = None if _is_none(entry["Replace"]) else entry["Replace"]
    with_ = None if _is_none(entry["With"]) else entry["With"]
    if replace is None and with_ is None:
        return "rejected", f"`{rel}`: Replace and With are both None — nothing to do"
    if with_ is not None and _HISTORY.search(with_):
        return "rejected", (
            f"`{rel}`: With carries change history (a date or 'amended'). "
            "State the current rule only"
        )

    lines = texts[path].split("\n")
    span = _section_span(lines, entry["Section"])
    if span is None:
        return "rejected", f"`{rel}`: no heading named `{entry['Section']}`"
    start, end = span
    body = "\n".join(lines[start:end])

    if replace is None:
        with_ = _unquote(with_)
        if with_ in body:
            return "already-applied", rel
        tail = end
        while tail > start and not lines[tail - 1].strip():
            tail -= 1
        lines[tail:tail] = with_.split("\n")
    else:
        # The doc may hold the backticks literally, so try the value as written first.
        if replace not in body and _unquote(replace) in body:
            replace, with_ = _unquote(replace), _unquote(with_) if with_ is not None else None
        count = body.count(replace)
        if count == 0:
            if with_ is not None and with_ in body:
                return "already-applied", rel
            return "rejected", (
                f"`{rel}` § {entry['Section']}: the Replace text is not in that section. "
                "Quote the existing text exactly, or use Replace: None for a rule with no existing home"
            )
        if count > 1:
            return "rejected", (
                f"`{rel}` § {entry['Section']}: the Replace text matches {count} places. "
                "Quote more of it"
            )
        body = body.replace(replace, with_ or "", 1)
        lines[start:end] = body.split("\n")
    texts[path] = "\n".join(lines)
    return "applied", rel


def apply_drift(feature: str, project_root: Optional[Path] = None) -> dict:
    root = (project_root or _resolve_user_project_root_from_cwd()).resolve()
    review = root / "cortex" / "lifecycle" / feature / "review.md"
    if not review.is_file():
        return {"state": "error", "message": f"{review} not found"}
    entries = parse_entries(review.read_text(encoding="utf-8", errors="replace"))
    if entries is None:
        return {"state": "no-section", "message": f"review.md has no `{DRIFT_HEADING}` section"}
    if not entries:
        return {
            "state": "rejected",
            "entries": [],
            "message": f"`{DRIFT_HEADING}` has no File / Section / Replace / With entry",
        }

    texts: Dict[Path, str] = {}
    results = []
    problems = []
    for entry in entries:
        result, detail = _plan_entry(entry, root, texts)
        results.append(
            {"file": entry.get("File", ""), "section": entry.get("Section", ""), "result": result}
        )
        if result == "rejected":
            problems.append(detail)
    if problems:
        return {"state": "rejected", "entries": results, "message": "; ".join(problems)}

    for path, text in texts.items():
        if text != path.read_text(encoding="utf-8"):
            path.write_text(text, encoding="utf-8")
    return {"state": "applied", "entries": results}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-lifecycle-apply-drift",
        description=(
            "Apply the File / Section / Replace / With entries under review.md's "
            "'## Suggested Requirements Update' to the named requirements docs. "
            "Writes nothing unless every entry checks out. Emits a {state, entries, "
            "message} JSON struct on stdout (always exit 0)."
        ),
    )
    parser.add_argument("--feature", required=True, metavar="SLUG", help="Lifecycle feature slug.")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _telemetry.log_invocation("cortex-lifecycle-apply-drift")
    args = _build_parser().parse_args(argv)
    try:
        result = apply_drift(args.feature)
    except Exception as exc:  # noqa: BLE001 — always emit a JSON struct, never a traceback
        result = {"state": "error", "message": repr(exc)}
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
