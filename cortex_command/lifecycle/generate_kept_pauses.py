#!/usr/bin/env python3
"""Render skills/lifecycle/references/kept-pauses.md from the declarative
kept-pause taxonomy data file (kept-pauses-data.toml).

The TOML data file is the durable source of truth: one ``[[pause]]`` row per
``<!-- pause: <slug> <kind> -->`` marker across ``skills/lifecycle`` and
``skills/refine``. This module renders a human-readable inventory from it. It is
a source-tree tool (like the parity test it feeds), so it resolves both the data
file and the output relative to this file's position in the repo, not to any
user project root.

Usage:
    python3 -m cortex_command.lifecycle.generate_kept_pauses           # print to stdout
    python3 -m cortex_command.lifecycle.generate_kept_pauses --write   # write kept-pauses.md
    CORTEX_COMMAND_FORCE_SOURCE=1 cortex-generate-kept-pauses
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

# cortex_command/lifecycle/generate_kept_pauses.py -> repo root is parents[2].
_REPO_ROOT = Path(__file__).resolve().parents[2]
_REFERENCES = _REPO_ROOT / "skills" / "lifecycle" / "references"
_DATA_FILE = _REFERENCES / "kept-pauses-data.toml"
_OUTPUT_FILE = _REFERENCES / "kept-pauses.md"

_HEADER = "<!-- generated — do not hand-edit; re-run `cortex-generate-kept-pauses` -->"

_EMDASH = "—"


def generate_md(entries: list[dict]) -> str:
    """Render the kept-pauses inventory markdown from parsed pause entries.

    Pure function over the parsed data (mirrors
    ``cortex_command.backlog.generate_index.generate_md``): deterministic,
    no I/O. Entries are sorted by ``(file, id)`` so output is stable
    regardless of data-file row order.
    """
    rows = sorted(entries, key=lambda e: (e["file"], e["id"]))
    lines: list[str] = [
        _HEADER,
        "",
        "# Kept user pauses",
        "",
        "Canonical inventory of the deliberate, in-scope user-facing pauses across "
        "the lifecycle and refine skills. Generated from "
        "`skills/lifecycle/references/kept-pauses-data.toml` — one row per "
        "`<!-- pause: <slug> <kind> -->` marker. The `suppressed_by` column names a "
        "`lifecycle.config.md` key or `judgment` (model-conditional rendering), "
        "orthogonal to kind.",
        "",
        "| Pause | Kind | Suppressed by | Location | Rationale |",
        "|-------|------|---------------|----------|-----------|",
    ]
    for e in rows:
        suppressed = e.get("suppressed_by")
        supp_disp = f"`{suppressed}`" if suppressed else _EMDASH
        anchor = e.get("anchor", "")
        loc = f"`{e['file']}`" + (f" — {anchor}" if anchor else "")
        lines.append(
            f"| `{e['id']}` | {e['kind']} | {supp_disp} | {loc} | {e['rationale']} |"
        )
    return "\n".join(lines) + "\n"


def _load(data_file: Path = _DATA_FILE) -> list[dict]:
    """Parse the pause taxonomy TOML into a list of ``[[pause]]`` tables."""
    with data_file.open("rb") as fh:
        data = tomllib.load(fh)
    return data.get("pause", [])


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    write = "--write" in argv
    entries = _load()
    md = generate_md(entries)
    if write:
        _OUTPUT_FILE.write_text(md, encoding="utf-8")
        rel = _OUTPUT_FILE.relative_to(_REPO_ROOT)
        print(f"Wrote {rel} ({len(entries)} pauses)", file=sys.stderr)
    else:
        sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
