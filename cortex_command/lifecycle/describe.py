#!/usr/bin/env python3
"""Render the wheel-owned lifecycle transition table as a generated doc.

``describe`` is the read-only renderer of the closed transition table
(``cortex_command.lifecycle.transition_table``): it projects the table's
``STATES`` / ``TRANSITIONS`` into a single markdown+JSON document so humans and
docs can read the state machine, kept in sync by a CI-diffed golden (the parity
test regenerates and byte-diffs against the committed doc — a stale doc fails).

It follows ``cortex_command.lifecycle.generate_kept_pauses`` exactly: a pure
``generate_md(data)`` over deterministically-sorted rows, a ``_load()`` that
reads the source of truth (here the wheel-owned table, not a TOML file), a
``main(argv)`` with ``--write`` writing the doc + a stderr progress line and the
else-branch writing stdout, source-tree-relative paths anchored at
``Path(__file__).resolve().parents[2]``, and a
``<!-- generated — do not hand-edit -->`` header. Emission is a single doc whose
markdown carries an embedded ``json`` code block, so "markdown+JSON" is one
committed artifact with one golden.

``describe`` is one of the served machine verbs (``next`` / ``advance`` /
``describe``) that, per the feature's single-log-resolver coherence requirement,
locate a feature's ``events.log`` through
``cortex_command.lifecycle.log_resolver``. Composing a feature slug into that
path is the real injection surface, so — like every sibling verb — this module
opens with ``_reject_unsafe_slug`` and applies it BEFORE any filesystem access
in the optional ``--feature`` mode (which resolves and reports the feature's
main-root-anchored log path). The static table render (the golden) is
feature-independent and takes no slug.

Usage:
    python3 -m cortex_command.lifecycle.describe            # markdown+JSON to stdout
    python3 -m cortex_command.lifecycle.describe --write     # write the golden doc
    python3 -m cortex_command.lifecycle.describe --feature <slug>   # JSON + log context
    CORTEX_COMMAND_FORCE_SOURCE=1 cortex-lifecycle-describe
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

from cortex_command.lifecycle import transition_table as tt

# cortex_command/lifecycle/describe.py -> repo root is parents[2].
_REPO_ROOT = Path(__file__).resolve().parents[2]
_OUTPUT_FILE = _REPO_ROOT / "docs" / "lifecycle-transition-table.md"

_HEADER = "<!-- generated — do not hand-edit; re-run `cortex-lifecycle-describe --write` -->"

_EMDASH = "—"


def _reject_unsafe_slug(feature: str) -> Optional[dict]:
    """Return an error envelope when *feature* is empty or carries a path
    separator / ``..`` — a path-traversal guard applied BEFORE any filesystem
    access. Returns None when the slug is safe to use as a directory component.
    """
    if not feature or "/" in feature or "\\" in feature or ".." in feature:
        return {
            "state": "error",
            "message": f"unsafe feature slug {feature!r}: no path separators or '..'",
        }
    return None


def _load(
    transitions: Optional[tuple] = None, states: Optional[tuple] = None
) -> dict:
    """Project the closed transition table into JSON-ready plain-dict rows.

    The ``_load()`` analog of ``generate_kept_pauses._load()``: it reads the
    single source of truth (the wheel-owned ``transition_table`` module) instead
    of a TOML file, and returns a ``{"states": [...], "transitions": [...]}``
    payload of plain dicts (frozen dataclasses flattened) that ``generate_md`` /
    ``generate_json`` render purely. Accepts injected ``transitions`` / ``states``
    for the parity test's negative controls; defaults to the live table.
    """
    transitions = tt.TRANSITIONS if transitions is None else transitions
    states = tt.STATES if states is None else states
    state_rows = [
        {
            "name": s.name,
            "terminal": s.terminal,
            "legacy_display_phase": s.legacy_display_phase,
        }
        for s in states
    ]
    tx_rows = []
    for t in transitions:
        tx_rows.append(
            {
                "id": t.id,
                "owning_verb": t.owning_verb,
                "decision_state": t.decision_state,
                "from_state": t.from_state,
                "to_state": t.to_state,
                "edge_kind": t.edge_kind,
                "emits": list(t.emits),
                "guard": (
                    None
                    if t.guard is None
                    else {
                        "precondition": t.guard.precondition,
                        "reads": list(t.guard.reads),
                    }
                ),
                "pause": (
                    None
                    if t.pause is None
                    else {"slug": t.pause.slug, "kind": t.pause.kind}
                ),
                "param_selectors": list(t.param_selectors),
                "notes": t.notes,
            }
        )
    return {"states": state_rows, "transitions": tx_rows}


def generate_json(data: dict) -> str:
    """Render the table payload as a deterministic JSON string.

    Pure function over the parsed data (mirrors ``generate_kept_pauses``'s pure
    ``generate_md``): states sorted by ``name``, transitions by ``id``, dict keys
    sorted — so output is byte-stable regardless of declaration order.
    """
    payload = {
        "states": sorted(data["states"], key=lambda s: s["name"]),
        "transitions": sorted(data["transitions"], key=lambda t: t["id"]),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)


def _cell(value: str) -> str:
    """Render a markdown table cell, escaping ``|`` and defaulting to an em-dash."""
    if not value:
        return _EMDASH
    return value.replace("|", "\\|")


def generate_md(data: dict) -> str:
    """Render the transition-table doc (markdown with an embedded JSON block).

    Pure function over the parsed data (mirrors
    ``generate_kept_pauses.generate_md``): deterministic, no I/O. States are
    sorted by ``name`` and transitions by ``id`` so the output is stable
    regardless of the table's declaration order.
    """
    states = sorted(data["states"], key=lambda s: s["name"])
    transitions = sorted(data["transitions"], key=lambda t: t["id"])
    lines: list[str] = [
        _HEADER,
        "",
        "# Lifecycle transition table",
        "",
        "Human-readable rendering of the closed, wheel-owned lifecycle state "
        "machine — the single source of truth in "
        "`cortex_command/lifecycle/transition_table.py`. Generated by the "
        "`describe` verb (`cortex-lifecycle-describe --write`); a CI golden "
        "diffs this committed doc against a fresh regeneration, so it can never "
        "silently drift from the table. The table is closed and append-only: "
        "consumer config may only select among enum-validated parameters, never "
        "add a state or reorder an edge. Guards are advisory (the authoritative "
        "check re-runs inside `advance` at act time).",
        "",
        "## States",
        "",
        "| State | Terminal | Legacy display phase |",
        "|-------|----------|----------------------|",
    ]
    for s in states:
        lines.append(
            f"| `{s['name']}` | {'yes' if s['terminal'] else 'no'} | "
            f"`{s['legacy_display_phase']}` |"
        )
    lines += [
        "",
        "## Transitions",
        "",
        "One row per B1 verb decision arm. `Edge` is the move kind; `Guard` is "
        "the advisory precondition (`—` when the arm is taken unconditionally on "
        "its discriminant); `Pause` names the kept-pause slug/kind an arm holds "
        "for; `Emits` is the legacy event vocabulary the owning verb writes.",
        "",
        "| ID | Owning verb | Decision | From → To | Edge | Emits | Guard | "
        "Pause | Params | Notes |",
        "|----|-------------|----------|-----------|------|-------|-------|"
        "-------|--------|-------|",
    ]
    for t in transitions:
        emits = ", ".join(f"`{e}`" for e in t["emits"]) or _EMDASH
        guard = t["guard"]
        guard_disp = _cell(guard["precondition"]) if guard else _EMDASH
        pause = t["pause"]
        pause_disp = f"`{pause['slug']}` ({pause['kind']})" if pause else _EMDASH
        params = ", ".join(f"`{p}`" for p in t["param_selectors"]) or _EMDASH
        lines.append(
            f"| `{t['id']}` | `{t['owning_verb']}` | `{t['decision_state']}` | "
            f"`{t['from_state']}` → `{t['to_state']}` | {t['edge_kind']} | "
            f"{emits} | {guard_disp} | {pause_disp} | {params} | "
            f"{_cell(t['notes'])} |"
        )
    lines += [
        "",
        "## JSON",
        "",
        "Machine-readable rendering of the same table (states sorted by name, "
        "transitions by id).",
        "",
        "```json",
        generate_json(data),
        "```",
    ]
    return "\n".join(lines) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    write = "--write" in argv

    # Optional feature-scoped mode: resolve and report the feature's
    # main-root-anchored events.log. Guard the slug BEFORE any path composition —
    # this is the path-traversal injection surface (a slug like ``../../x`` would
    # otherwise resolve outside cortex/lifecycle/).
    feature: Optional[str] = None
    if "--feature" in argv:
        idx = argv.index("--feature")
        feature = argv[idx + 1] if idx + 1 < len(argv) else ""
        guard = _reject_unsafe_slug(feature)
        if guard is not None:
            sys.stdout.write(json.dumps(guard) + "\n")
            return 0

    data = _load()
    md = generate_md(data)

    if write:
        _OUTPUT_FILE.write_text(md, encoding="utf-8")
        rel = _OUTPUT_FILE.relative_to(_REPO_ROOT)
        print(
            f"Wrote {rel} "
            f"({len(data['transitions'])} transitions, {len(data['states'])} states)",
            file=sys.stderr,
        )
    elif feature is not None:
        # Feature-scoped: emit the JSON rendering plus the resolved log context.
        # The .exists() probe is the guarded filesystem access.
        from cortex_command.lifecycle.log_resolver import resolve_events_log

        log = resolve_events_log(feature)
        payload = json.loads(generate_json(data))
        payload["feature"] = {
            "slug": feature,
            "events_log": str(log),
            "log_exists": log.exists(),
        }
        sys.stdout.write(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        )
    else:
        sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
