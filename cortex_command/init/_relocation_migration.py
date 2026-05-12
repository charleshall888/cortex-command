"""One-time migration script: prepend ``cortex/`` to bare path references.

Rewrites three artifact classes in-place:

1. **Backlog YAML fields** — ``discovery_source:``, ``spec:``, ``plan:``,
   ``research:`` lines in ``backlog/*.md`` whose values start with
   ``lifecycle/``, ``backlog/``, or ``research/`` (without the ``cortex/``
   prefix).

2. **Critical-review residue JSON** — every ``"artifact"`` key in
   ``lifecycle/*/critical-review-residue.json`` (active + archive) that lacks
   the ``cortex/`` prefix.

3. **Research decomposed.md prose cross-refs** — ``lifecycle/<slug>/`` or
   ``backlog/<id>`` references inside ``research/*/decomposed.md`` (active +
   archive) that have no leading ``cortex/``.

All three branches are **idempotent**: values already starting with
``cortex/lifecycle/``, ``cortex/backlog/``, or ``cortex/research/`` are left
untouched.

Usage (run from repo root)::

    python -m cortex_command.init._relocation_migration

Or directly::

    python cortex_command/init/_relocation_migration.py

Deletion of this script is deferred to a follow-up commit per spec DR-7.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_YAML_FIELDS = ("discovery_source", "spec", "plan", "research")

# Matches a YAML field line whose value starts with lifecycle/, backlog/, or
# research/ WITHOUT a cortex/ prefix.  Uses re.sub on the stripped portion.
_YAML_FIELD_RE = re.compile(
    r"^((?:"
    + "|".join(_YAML_FIELDS)
    + r"): )(?!cortex/)((?:lifecycle|backlog|research)/)",
)

# Matches bare lifecycle/<slug>/ in prose (not already preceded by cortex/).
_PROSE_LIFECYCLE_RE = re.compile(r"(?<![/\w])lifecycle/([a-zA-Z0-9_-])")

# Matches bare backlog/<digits> in prose (not already preceded by cortex/).
_PROSE_BACKLOG_RE = re.compile(r"(?<![/\w])backlog/(\d)")


def _prefix_yaml_line(line: str) -> str:
    """Return *line* with ``cortex/`` prepended to the field value if needed.

    Uses :func:`re.sub` so that the replacement captures the full match and
    inserts ``cortex/`` between group 1 (the key prefix) and group 2 (the
    bare path root).  The pattern anchors to the line start so only YAML
    field values — not body prose — are touched.
    """
    return _YAML_FIELD_RE.sub(r"\1cortex/\2", line)


def _prefix_artifact_value(value: str) -> str:
    """Return *value* with ``cortex/`` prepended if it lacks the prefix."""
    if isinstance(value, str) and re.match(
        r"^(lifecycle|backlog|research)/", value
    ):
        return "cortex/" + value
    return value


def _migrate_artifact_keys(obj: object) -> tuple[object, bool]:
    """Recursively rewrite ``"artifact"`` string values in *obj*.

    Returns ``(new_obj, changed)`` where *changed* is True if any value was
    modified.  Handles dicts and lists; leaves all other types untouched.
    """
    if isinstance(obj, dict):
        changed = False
        new_obj: dict = {}
        for k, v in obj.items():
            if k == "artifact" and isinstance(v, str):
                new_v = _prefix_artifact_value(v)
                new_obj[k] = new_v
                if new_v != v:
                    changed = True
            else:
                new_v2, sub_changed = _migrate_artifact_keys(v)
                new_obj[k] = new_v2
                if sub_changed:
                    changed = True
        return new_obj, changed
    if isinstance(obj, list):
        changed = False
        new_list = []
        for item in obj:
            new_item, sub_changed = _migrate_artifact_keys(item)
            new_list.append(new_item)
            if sub_changed:
                changed = True
        return new_list, changed
    return obj, False


def _prefix_prose_line(line: str) -> str:
    """Return *line* with ``cortex/`` prepended to bare lifecycle/ and backlog/ refs."""
    line = _PROSE_LIFECYCLE_RE.sub(r"cortex/lifecycle/\1", line)
    line = _PROSE_BACKLOG_RE.sub(r"cortex/backlog/\1", line)
    return line


# ---------------------------------------------------------------------------
# Branch 1: backlog YAML fields
# ---------------------------------------------------------------------------


def migrate_backlog(repo_root: Path) -> int:
    """Rewrite YAML fields in ``backlog/*.md``.

    Returns the number of lines changed across all files.
    """
    backlog_dir = repo_root / "backlog"
    if not backlog_dir.is_dir():
        return 0

    total_changes = 0
    for md_file in sorted(backlog_dir.glob("*.md")):
        original = md_file.read_text(encoding="utf-8")
        lines = original.splitlines(keepends=True)
        new_lines = [_prefix_yaml_line(ln) for ln in lines]
        changed = sum(a != b for a, b in zip(lines, new_lines))
        if changed:
            md_file.write_text("".join(new_lines), encoding="utf-8")
            total_changes += changed
    return total_changes


# ---------------------------------------------------------------------------
# Branch 2: critical-review-residue.json artifact keys
# ---------------------------------------------------------------------------


def migrate_residue_json(repo_root: Path) -> int:
    """Rewrite ``"artifact"`` keys in all ``critical-review-residue.json`` files.

    Walks both active (``lifecycle/*/``) and archive (``lifecycle/archive/*/``)
    directories.

    Returns the number of files changed.
    """
    lifecycle_dir = repo_root / "lifecycle"
    if not lifecycle_dir.is_dir():
        return 0

    files_changed = 0
    for residue_file in sorted(lifecycle_dir.rglob("critical-review-residue.json")):
        try:
            original_text = residue_file.read_text(encoding="utf-8")
        except OSError:
            continue

        try:
            data = json.loads(original_text)
        except json.JSONDecodeError:
            continue

        data, changed = _migrate_artifact_keys(data)

        if changed:
            new_text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
            residue_file.write_text(new_text, encoding="utf-8")
            files_changed += 1

    return files_changed


# ---------------------------------------------------------------------------
# Branch 3: research/*/decomposed.md prose cross-refs
# ---------------------------------------------------------------------------


def migrate_decomposed(repo_root: Path) -> int:
    """Rewrite prose cross-refs in ``research/*/decomposed.md`` files.

    Walks both active (``research/*/``) and archive (``research/archive/*/``)
    directories.

    Returns the number of lines changed across all files.
    """
    research_dir = repo_root / "research"
    if not research_dir.is_dir():
        return 0

    total_changes = 0
    for decomposed_file in sorted(research_dir.rglob("decomposed.md")):
        original = decomposed_file.read_text(encoding="utf-8")
        lines = original.splitlines(keepends=True)
        new_lines = [_prefix_prose_line(ln) for ln in lines]
        changed = sum(a != b for a, b in zip(lines, new_lines))
        if changed:
            decomposed_file.write_text("".join(new_lines), encoding="utf-8")
            total_changes += changed

    return total_changes


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(repo_root: Path | None = None) -> None:
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent.parent

    backlog_changes = migrate_backlog(repo_root)
    residue_changes = migrate_residue_json(repo_root)
    decomposed_changes = migrate_decomposed(repo_root)

    print(
        f"Migration complete:\n"
        f"  backlog YAML lines changed:          {backlog_changes}\n"
        f"  residue JSON files changed:          {residue_changes}\n"
        f"  decomposed.md prose lines changed:   {decomposed_changes}"
    )


if __name__ == "__main__":
    main()
