"""Composite backlog-triage verb for ``/cortex-core:dev`` Step 3.

``cortex-backlog-triage`` replaces the four-round-trip triage opening
(``cortex-read-backlog-backend`` → ``cortex-generate-backlog-index`` →
``cortex-build-epic-map`` → read the dev-skill triage reference) with one
call that also *renders* both triage blocks. The rendering is fully
mechanical — grouping, badge selection, the dependency waves, and the per-epic
recommendation sentences are decided by item status, ``blocked_by``, and the
presence of ``spec:`` — so it belongs in a verb rather than in prose the model
re-reads on every triage.

An epic section shows only what can still be acted on. Closed children are
reduced to a count on the section's summary line; they carry no route mark and
appear in no footer, because a route mark on shipped work is a direct
instruction to redo it.

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
from cortex_command.common import TERMINAL_STATUSES, _resolve_user_project_root_from_cwd
from cortex_command.lifecycle_config import resolve_backlog_backend
from cortex_command.backlog.readiness import is_item_ready


_PRIORITY_ORDER = ("critical", "high", "medium", "low")


def _norm_status(item: dict) -> str:
    """Normalize an item's status to lowercase, hyphen-spelled.

    The corpus carries both spellings of every multi-word status
    (``in_progress``/``in-progress``) because two writers disagree upstream.
    Collapsing here means every status set below is written once, in one
    spelling, instead of each set carrying its own variant list — the failure
    mode that let ``complete``/``done`` half-work.
    """
    return str(item.get("status") or "").strip().lower().replace("_", "-")


#: In-flight: someone is on it. Not pickable, but resumable, so still listed.
_HELD_STATUSES = frozenset({"in-progress", "implementing", "review"})
#: Finished. Normalized from the canonical set so ``done`` and ``complete``
#: — both live in real data — can never be classified differently.
_CLOSED_STATUSES = frozenset(
    s.strip().lower().replace("_", "-") for s in TERMINAL_STATUSES
)

WORKABLE, HELD, PARKED, CLOSED = "workable", "in flight", "parked", "closed"
#: Row order within an epic, and the order of the counts line. ``CLOSED`` is
#: absent from the row groups on purpose — it is counted, never listed.
_ROW_GROUPS = (WORKABLE, HELD, PARKED)
_COUNT_GROUPS = (WORKABLE, HELD, PARKED, CLOSED)


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

    Status is deliberately absent: both callers hand this only ``WORKABLE``
    items — the epic block classifies first and never routes a closed, held, or
    parked child, and ``_ready_set`` restricts the flat block to
    ``refined``/``backlog``/``open``/``blocked``. Re-checking status here would
    duplicate a gate that has to exist upstream anyway, since a closed child
    must not be *listed* either.
    """
    if item.get("type", "feature") == "idea":
        return "`/cortex-core:discovery`"
    return "`/cortex-core:build`" if _is_refined(item) else "`/cortex-core:refine`"


def _classify(item: dict) -> str:
    """Bucket one child into ``WORKABLE``/``HELD``/``PARKED``/``CLOSED``.

    Precedence is closed → held → parked → workable. Closed wins over a stray
    ``deferred`` tag: a finished ticket that was once parked is history, not a
    parked decision.
    """
    status = _norm_status(item)
    if status in _CLOSED_STATUSES:
        return CLOSED
    if status in _HELD_STATUSES:
        return HELD
    if _is_deferred(item):
        return PARKED
    return WORKABLE


def _resolve_child(child: dict, by_id: dict[int, dict]) -> dict:
    """Resolve an epic child to its full record — the envelope carries no type."""
    return by_id.get(child["id"]) or child


def _blocker_lookup(items: list[dict]) -> dict[str, dict]:
    """Index items by every spelling a ``blocked_by`` ref may use.

    Mirrors ``readiness._build_status_lookup``: bare id, zero-padded id, and
    uuid. Values are the whole record rather than the status so callers can
    classify with :func:`_classify` instead of re-deriving terminality.
    """
    lookup: dict[str, dict] = {}
    for item in items:
        item_id = str(item.get("id"))
        lookup[item_id] = item
        lookup[item_id.zfill(3)] = item
        uuid = item.get("uuid")
        if uuid:
            lookup[str(uuid)] = item
    return lookup


def _open_blockers(
    item: dict, lookup: dict[str, dict]
) -> tuple[list[int], list[str]]:
    """Return ``(internal_ids, foreign_refs)`` of this item's *unresolved* blockers.

    A blocker that resolved to a closed item is dropped — it is satisfied, and
    the old renderer's "any ``blocked_by`` entry means blocked" rule marked
    items blocked forever behind work that had shipped. ``foreign_refs`` holds
    refs that resolve to nothing local (cross-repo references, dangling ids);
    they are unresolvable here, so they are reported verbatim rather than
    guessed at.
    """
    internal: list[int] = []
    foreign: list[str] = []
    for ref in item.get("blocked_by") or []:
        ref_s = str(ref).strip()
        if not ref_s:
            continue
        target = lookup.get(ref_s)
        if target is None and ref_s.isdigit():
            target = lookup.get(ref_s.zfill(3))
        if target is None:
            foreign.append(ref_s)
            continue
        if _classify(target) == CLOSED:
            continue
        internal.append(target["id"])
    return internal, foreign


def _waves(
    ids: list[int], deps: dict[int, set[int]]
) -> tuple[list[list[int]], list[int]]:
    """Kahn-layer *ids* into parallel-safe waves; return ``(waves, cyclic)``.

    Wave *n* is everything whose dependencies all land in waves ``< n``, so a
    wave is exactly the set that can be started at once.

    A dependency cycle — including an item that blocks itself — stalls the loop
    with nothing schedulable. The remainder is returned separately rather than
    appended as a final wave: a wave *claims* its members are parallel-safe, and
    a cycle is the one case where that claim is false. Silently folding it in
    would emit a confident recommendation over broken data, which is the failure
    class this whole renderer exists to remove.
    """
    remaining = list(ids)
    settled: set[int] = set()
    waves: list[list[int]] = []
    while remaining:
        layer = [i for i in remaining if deps.get(i, set()) <= settled]
        if not layer:
            return waves, remaining
        waves.append(layer)
        settled.update(layer)
        remaining = [i for i in remaining if i not in settled]
    return waves, []


def _counts(buckets: dict[str, list[dict]]) -> str:
    """Summarize the whole child set in one line — the progress signal.

    Filtering closed children out of the rows would otherwise delete the
    "how far along is this epic" reading that the full list used to carry.
    """
    return " · ".join(
        f"{len(buckets[group])} {group}" for group in _COUNT_GROUPS if buckets[group]
    )


def _join(ids: list[int]) -> str:
    """Join parallel-safe ids with the legend's ``·`` separator."""
    return " · ".join(str(i) for i in ids)


def _render_epic_block(
    epic_id: str, epic: dict, by_id: dict[int, dict], lookup: dict[str, dict]
) -> list[str]:
    """Render one epic section: a counts line, pickable rows, an ordering footer.

    Closed children are counted and never listed — a shipped ticket carrying a
    route mark in a pick-your-next-task prompt is a direct instruction to redo
    finished work. ``deferred`` children *are* listed but never routed: parked
    is a decision to revisit, not work to pick up, so an operator scanning the
    epic should see it without being told to refine it.
    """
    title = epic.get("title") or by_id.get(int(epic_id), {}).get("title", "")
    lines = [f"### Epic {epic_id} — {title}"]

    children = [_resolve_child(c, by_id) for c in epic.get("children", [])]
    buckets: dict[str, list[dict]] = {g: [] for g in _COUNT_GROUPS}
    for child in children:
        buckets[_classify(child)].append(child)
    for group in _COUNT_GROUPS:
        buckets[group].sort(key=lambda c: c.get("id") or 0)

    if not children:
        return lines + [
            "",
            "No child tickets — consider `/cortex-core:discovery` to decompose "
            "this epic.",
        ]

    lines += ["", _counts(buckets)]
    if not any(buckets[g] for g in _ROW_GROUPS):
        # Every child closed. The epic *was* decomposed, so the discovery line
        # above would misread; what is actually actionable is closing the epic.
        return lines + ["", "Nothing left to pick up — this epic looks finished."]

    workable = buckets[WORKABLE]
    workable_ids = [c["id"] for c in workable]
    blockers = {c["id"]: _open_blockers(c, lookup) for c in workable}
    within = set(workable_ids)
    deps = {
        cid: {b for b in internal if b in within}
        for cid, (internal, _foreign) in blockers.items()
    }

    lines.append("")
    for child in workable:
        internal, foreign = blockers[child["id"]]
        marks = [_recommendation(child)]
        refs = [str(i) for i in internal] + foreign
        if refs:
            marks.append(f"[blocked by {', '.join(refs)}]")
        elif _norm_status(child) == "blocked":
            marks.append("[blocked]")
        lines.append(
            f"- **{child['id']}** {child['title']} — {_norm_status(child) or '?'} "
            + " ".join(marks)
        )
    for child in buckets[HELD] + buckets[PARKED]:
        status = _norm_status(child)
        # No route verb: neither an in-flight nor a parked child is something to
        # pick up. The status word usually says which it is on its own; the mark
        # exists for the tag-parked item whose status still reads `backlog`.
        self_describing = status in _HELD_STATUSES or status == "deferred"
        mark = "" if self_describing else f" [{_classify(child)}]"
        lines.append(f"- **{child['id']}** {child['title']} — {status or '?'}{mark}")

    if not workable:
        return lines

    # Startable is read off the dependency map directly, not off `_waves`'
    # first layer: a cycle has no schedulable layer at all, and taking wave 0
    # on faith would have reported two mutually-blocking children as ready to
    # start together.
    startable = [
        cid for cid in workable_ids if not deps[cid] and not blockers[cid][1]
    ]
    is_idea = {c["id"]: c.get("type", "feature") == "idea" for c in workable}
    refined = {c["id"]: _is_refined(c) for c in workable}

    # Idea-ness is evaluated over EVERY workable child, not just the unrefined
    # ones, so these footers apply `_recommendation`'s own precedence: `idea` is
    # a readiness statement checked BEFORE `spec:` presence. A refined idea — an
    # idea carrying a spec — still routes to `/cortex-core:discovery` on its
    # row, so partitioning on refinement first would drop it out of the idea
    # bucket and let it license an overnight sentence its own row contradicts.
    # Overnight's readiness scan will not honor a discovery topic at any
    # refinement level.
    unrefined = [c["id"] for c in workable if not refined[c["id"]] and not is_idea[c["id"]]]
    buildable = [i for i in startable if refined[i] and not is_idea[i]]
    # Ideas are not overnight-routable at any refinement level, so their
    # absence — not merely the absence of refine work — licenses the offer.
    overnight = not unrefined and not any(is_idea.values())

    footer: list[str] = []
    # Only the dependency-connected subgraph is worth drawing. Every other
    # workable child is a wave-0 singleton, so including them made the line a
    # second copy of the row list — on a 13-child epic, eleven of the ids
    # carried no ordering information at all.
    connected = {cid for cid, d in deps.items() if d}
    connected.update(b for d in deps.values() for b in d)
    chain, cyclic = _waves([i for i in workable_ids if i in connected], deps)
    if len(chain) > 1:
        footer.append("Order: " + " → ".join(_join(w) for w in chain))
    if len(cyclic) == 1:
        # A lone straggler can only have stalled on itself: every other id
        # settled, so its one unsettled dependency is its own.
        footer.append(
            f"{cyclic[0]} lists itself in `blocked_by` — it cannot start until "
            "that is edited."
        )
    elif cyclic:
        # Wider than the cycle itself: anything downstream of it stalls too, and
        # is equally unstartable.
        footer.append(
            f"Circular `blocked_by` among {_join(sorted(cyclic))} — none can "
            "start until that is edited."
        )
    if buildable:
        verb = "Build in parallel" if len(buildable) > 1 else "Build"
        # Folded onto the build line rather than given its own: both name the
        # same set, and the offer is an alternative to building them by hand.
        # Withheld when nothing is startable — overnight's own readiness scan
        # would select nothing, so offering it there is a dead instruction.
        tail = (
            " — or `/cortex-overnight:overnight` to auto-select "
            + ("them" if len(buildable) > 1 else "it")
            if overnight
            else ""
        )
        footer.append(f"{verb}: {_join(buildable)}{tail}")
    if unrefined:
        # Every wave, not just wave 0: `Order:` constrains *building*. Writing a
        # spec for a ticket whose blocker has not shipped is fine, so refine
        # targets carry no ordering among themselves — the parallelism the
        # legend promises.
        verb = "Refine in parallel" if len(unrefined) > 1 else "Refine"
        # When every row is a refine target the ids are a verbatim repeat of the
        # rows; the only thing the line still adds is the parallel-safety claim,
        # which needs no list to make.
        listed = (
            "every workable row above"
            if len(unrefined) == len(workable) and len(unrefined) > 1
            else _join(unrefined)
        )
        footer.append(f"{verb}: {listed}")
    if footer:
        lines += [""] + footer
    return lines


#: Prepended once above the epic sections. Every clause here used to be paid
#: per epic — the "not directly workable" title suffix on each heading, and the
#: spec-approval caveat inside each refine sentence.
_EPIC_LEGEND = (
    "Pick a child, not the epic. `·` separates ids that can run in parallel, "
    "`→` sequences them. Closed children are counted, not listed. `Refine` "
    "targets carry no ordering — parallelize them across sessions, though one "
    "session must approve each spec before starting the next."
)


def render(items: list[dict], epic_map: dict) -> tuple[str, list[dict]]:
    """Render both triage blocks and return ``(markdown, flat_items)``.

    Block 1 is one section per epic present in the ready set, in priority
    order, listing the children that can still be acted on — workable, in
    flight, or parked — with the closed ones reduced to a count. Block 2 is the
    remaining ready items minus epics and minus anything already shown as a
    child.

    *items* should be the full non-archived corpus, not the active-only index:
    every closed child then resolves to a real record, so ``type`` reaches
    ``_recommendation`` and a ``blocked_by`` pointing at shipped work resolves
    as satisfied instead of as an unknown external blocker. Passing the
    active-only index still works — it just restores both blind spots.
    """
    by_id = {i["id"]: i for i in items}
    lookup = _blocker_lookup(items)
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
        lines += ["## Epics", "", _EPIC_LEGEND, ""]
        for epic_id in ready_epic_ids:
            lines += _render_epic_block(epic_id, epics[epic_id], by_id, lookup)
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

    # Rendered over the full corpus, not `items`: the epic map's child envelope
    # carries no `type` and no `blocked_by`, so an active-only `by_id` left
    # every closed child unresolvable — silently disabling the `idea` route and
    # making a satisfied blocker look like an unknown external one. `_ready_set`
    # gates on status, so widening the input cannot widen either block's
    # membership.
    blocks, flat = render(full_items, epic_map)
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
