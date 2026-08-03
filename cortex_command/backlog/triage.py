"""Composite backlog-triage verb for ``/cortex-core:dev`` Step 3.

``cortex-backlog-triage`` replaces the four-round-trip triage opening
(``cortex-read-backlog-backend`` → ``cortex-generate-backlog-index`` →
``cortex-build-epic-map`` → read the dev-skill triage reference) with one
call that also *renders* both triage blocks. The rendering is fully
mechanical — grouping, badge selection, and the per-epic recommendation
sentence are decided by item status and the presence of ``spec:`` — so it
belongs in a verb rather than in prose the model re-reads on every triage.

Output is one JSON object::

    {"state": "ok", "backend": ..., "blocks": "<markdown>", "epics": {...},
     "flat": [...], "index": "regenerated"|"stale"}

The caller prints ``blocks`` and asks which item to pick up. Non-local
backends short-circuit with ``state: "external-backend"`` — the local index is
not authoritative there, so nothing is regenerated and no blocks are rendered.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from cortex_command.backlog import _telemetry
from cortex_command.backlog.build_epic_map import build_epic_map, normalize_parent
from cortex_command.backlog.generate_index import _is_deferred
from cortex_command.common import _resolve_user_project_root_from_cwd
from cortex_command.lifecycle_config import resolve_backlog_backend
from cortex_command.backlog.readiness import is_item_ready


_PRIORITY_ORDER = ("critical", "high", "medium", "low")
_HELD_STATUSES = frozenset({"in_progress", "implementing", "review", "in-progress"})


def _ready_set(items: list[dict]) -> list[dict]:
    """Return the ``## Refined`` ∪ ``## Backlog`` set, in priority order.

    Mirrors ``generate_index``'s two section passes exactly — same eligible
    statuses, same parked exclusion (tag or status), same blocker treatment —
    so triage and the written index can never disagree about what is ready.
    """
    all_ns = [SimpleNamespace(**rec) for rec in items]
    ready: list[dict] = []
    for item in items:
        status = item.get("status")
        if _is_deferred(item):
            continue
        if status == "refined":
            eligible = {"refined"}
        elif status in ("backlog", "open", "blocked"):
            eligible = {"backlog", "open", "blocked"}
        else:
            continue
        ok, _ = is_item_ready(
            SimpleNamespace(**item),
            all_ns,
            eligible_statuses=eligible,
            treat_external_blockers_as="blocking",
        )
        if ok:
            ready.append(item)
    ready.sort(key=lambda i: _PRIORITY_ORDER.index(i.get("priority", "medium"))
               if i.get("priority") in _PRIORITY_ORDER else len(_PRIORITY_ORDER))
    return ready


def _is_refined(item: dict) -> bool:
    spec = item.get("spec")
    return bool(spec) and spec not in ("null", "~", "None")


def _recommendation(item: dict) -> str:
    """Route one item by readiness, on a single line with no embedded newline.

    ``idea`` is checked first because it is a readiness statement — an idea has
    nothing to spec yet. Every other type is governed by ``spec:`` presence, so
    the flat Ready row and the per-child epic mark can never disagree.
    """
    if item.get("type", "feature") == "idea":
        return "`/cortex-core:discovery`"
    return "`/cortex-core:build`" if _is_refined(item) else "`/cortex-core:refine`"


def _resolve_child(child: dict, by_id: dict[int, dict]) -> dict:
    """Resolve an epic child to its full record — the envelope carries no type."""
    return by_id.get(child["id"]) or child


def _render_epic_block(epic_id: str, epic: dict, by_id: dict[int, dict]) -> list[str]:
    """Render one epic section: the non-workable title, every child, a verdict."""
    title = epic.get("title") or by_id.get(int(epic_id), {}).get("title", "")
    lines = [f"### Epic {epic_id} — {title} _(epic, not directly workable)_", ""]

    children = epic.get("children", [])
    for child in children:
        full = by_id.get(child["id"], {})
        marks = [_recommendation(_resolve_child(child, by_id))]
        if full.get("status") == "blocked" or full.get("blocked_by"):
            marks.append("[blocked]")
        lines.append(
            f"- **{child['id']}** {child['title']} — {child.get('status', '?')} "
            + " ".join(marks)
        )

    recommendable = [
        c for c in children
        if c.get("status") not in _HELD_STATUSES
        and not (by_id.get(c["id"], {}).get("status") == "blocked"
                 or by_id.get(c["id"], {}).get("blocked_by"))
    ]
    active = [c for c in children if c.get("status") not in _HELD_STATUSES]
    lines.append("")
    if not active:
        lines.append(
            "No active child tickets — consider `/cortex-core:discovery` to "
            "decompose this epic."
        )
        return lines

    blocked_n = len(active) - len(recommendable)
    if blocked_n:
        lines.append(
            f"Note: {blocked_n} blocked — recommendations apply to the "
            f"remaining {len(recommendable)}."
        )
    if not recommendable:
        return lines
    # Idea-ness is evaluated over EVERY recommendable child, not just the
    # unrefined ones, so this footer applies `_recommendation`'s own precedence:
    # `idea` is a readiness statement checked BEFORE `spec:` presence. A refined
    # idea — an idea carrying a spec — still routes to `/cortex-core:discovery`
    # on its row, so partitioning on refinement first would drop it out of the
    # idea bucket and let it license an overnight sentence its own row
    # contradicts. Overnight's readiness scan will not honor a discovery topic
    # at any refinement level.
    is_idea = {
        c["id"]: _resolve_child(c, by_id).get("type", "feature") == "idea"
        for c in recommendable
    }
    ideas = [c for c in recommendable if is_idea[c["id"]]]
    unrefined_work = [
        c for c in recommendable if not is_idea[c["id"]] and not _is_refined(c)
    ]
    if unrefined_work:
        listed = ", ".join(f"{c['id']} {c['title']}" for c in unrefined_work)
        lines.append(
            "Run `/cortex-core:refine` on each unrefined child, one at a time "
            f"(each needs interactive spec approval before the next): {listed}."
        )
    elif not ideas:
        # Ideas are not overnight-routable at any refinement level, so their
        # absence — not merely the absence of refine work — licenses the
        # overnight sentence.
        lines.append(
            "Run `/cortex-overnight:overnight` — it will auto-select them via "
            "its own readiness scan."
        )
    return lines


def render(items: list[dict], epic_map: dict) -> tuple[str, list[dict]]:
    """Render both triage blocks and return ``(markdown, flat_items)``.

    Block 1 is one section per epic present in the ready set, in priority
    order, listing every child regardless of status. Block 2 is the remaining
    ready items minus epics and minus anything already shown as a child.
    """
    by_id = {i["id"]: i for i in items}
    ready = _ready_set(items)
    epics = epic_map.get("epics", {})

    lines: list[str] = []
    ready_epic_ids = [
        str(i["id"]) for i in ready
        if i.get("type") == "epic" and str(i["id"]) in epics
    ]

    # Only children of epics actually rendered in Block 1 may be suppressed
    # from Block 2. Deriving this from every epic in the map would silently
    # hide a ready child whose parent epic is closed — the map now carries
    # closed epics, and a closed epic never reaches ready_epic_ids, so such a
    # child would appear in no block at all. That is precisely the
    # late-arriving child this epic exists to surface.
    child_ids = {
        c["id"]
        for epic_id in ready_epic_ids
        for c in epics[epic_id].get("children", [])
    }
    if ready_epic_ids:
        lines += ["## Epics", ""]
        for epic_id in ready_epic_ids:
            lines += _render_epic_block(epic_id, epics[epic_id], by_id)
            lines.append("")

    flat = [
        i for i in ready
        if i.get("type") != "epic" and i["id"] not in child_ids
    ]
    if flat:
        lines += ["## Ready", ""]
        for item in flat:
            lines.append(
                f"- `{item.get('priority', '?')}` `{item.get('type', '?')}` "
                f"**{item['id']}** {item['title']} → {_recommendation(item)}"
            )
    if not lines:
        lines = [
            "Backlog is clear — no ready items. Check blocked items or create "
            "new ones with `/cortex-backlog:backlog add`."
        ]
    return "\n".join(lines).rstrip() + "\n", flat


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-backlog-triage",
        description=(
            "Compose /cortex-core:dev's backlog triage in one call: resolve "
            "the backend, regenerate the index, build the epic map, and render "
            "both triage blocks as markdown. Prints one JSON envelope; always "
            "exits 0 except on an unresolvable project root."
        ),
    )
    parser.add_argument(
        "--no-regen",
        action="store_true",
        help="Read the existing index.json without regenerating it first.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    _telemetry.log_invocation("cortex-backlog-triage")
    args = _build_parser().parse_args(argv)
    try:
        root = _resolve_user_project_root_from_cwd()
    except Exception as exc:  # noqa: BLE001 — always emit a JSON struct
        sys.stdout.write(json.dumps({"state": "error", "message": str(exc)}) + "\n")
        return 1

    backend = resolve_backlog_backend(root)
    if backend != "cortex-backlog":
        sys.stdout.write(
            json.dumps(
                {
                    "state": "external-backend",
                    "backend": backend,
                    "message": (
                        f"Backlog backend is {backend!r} — the local index is "
                        f"not authoritative. Point the user at that backend and "
                        f"route through /cortex-core:refine or "
                        f"/cortex-core:discovery without touching the index."
                    ),
                }
            )
            + "\n"
        )
        return 0

    index_state = "stale"
    if not args.no_regen:
        try:
            from cortex_command.backlog import generate_index

            generate_index.main()
            index_state = "regenerated"
        except Exception:  # noqa: BLE001 — fall back to the on-disk index
            index_state = "stale"

    backlog_dir = root / "cortex" / "backlog"
    index_path = backlog_dir / "index.json"
    try:
        items = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        sys.stdout.write(
            json.dumps(
                {
                    "state": "no-index",
                    "backend": backend,
                    "message": (
                        f"Could not read {index_path}: {exc}. Suggest "
                        f"`/cortex-backlog:backlog reindex`, or "
                        f"`/cortex-backlog:backlog add` if the backlog is empty."
                    ),
                }
            )
            + "\n"
        )
        return 0

    # The epic map is built from the full corpus so a closed epic is still
    # recognizable as an epic; the ready set above stays active-only. Falling
    # back to `items` keeps a repo whose index predates index-full.json
    # working, just with the old active-only blind spot.
    try:
        full_items = json.loads(
            (backlog_dir / "index-full.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        full_items = items

    try:
        epic_map = build_epic_map(full_items)
    except Exception:  # noqa: BLE001 — a bad map degrades to the flat list
        epic_map = {"epics": {}}

    blocks, flat = render(items, epic_map)
    sys.stdout.write(
        json.dumps(
            {
                "state": "ok",
                "backend": backend,
                "index": index_state,
                "blocks": blocks,
                "flat": [
                    {"id": i["id"], "title": i["title"], "type": i.get("type"),
                     "priority": i.get("priority"), "refined": _is_refined(i)}
                    for i in flat
                ],
                "epics": epic_map.get("epics", {}),
            }
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
