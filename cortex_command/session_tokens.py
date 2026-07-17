"""cortex-session-tokens — report the harness's own runtime cost from `usage` records.

Reads Claude Code session transcripts (``~/.claude/projects/<slug>/<session>.jsonl``
for the orchestrator, ``<session>/subagents/*.jsonl`` for its subagents) and
reports billed requests, token flows, and dollar cost per session — reading the
``usage`` object on each assistant record and **classifying nothing** (#392).

The 2026-07-16 token-economics investigation produced four wrong headline
numbers; the errors sorted perfectly: every number read straight from ``usage``
held, every number requiring the analyst to *classify* content was wrong. This
verb therefore hard-codes the robust rules and refuses the fragile ones:

* **Dedup by billed ``message.id``** (fall back to ``requestId``, then the
  record ``uuid``) before any sum — one billed API response is logged as
  several JSONL records (one per content block), each carrying the same
  cumulative ``usage``; summing lines overcounts ~2.7x.
* **Price from a table, never from memory** — per-Mtok prices below are from
  the published pricing reference (2026-07 sticker prices); cache-write bills
  1.25x input at 5m TTL and 2x at 1h TTL, cache-read 0.1x. The per-TTL split is
  read from ``usage.cache_creation``; when the breakdown is absent the bare
  ``cache_creation_input_tokens`` total is charged at the 1h rate (the
  conservative bound, matching the verified prototype at
  ``cortex/research/token-economics-2026-07-16/analyze.py``).
* **A model outside the table is counted but never silently priced** — its
  requests surface as ``unpriced_requests`` and contribute no dollars, rather
  than being guessed at some family's rate.
* **Split orchestrator vs subagents by file path**, never by record fields.
* **Emit nothing that requires interpreting a command string** — no purpose
  bucketing, no verb attribution, no thinking inference.

Beyond the per-session report, two read-straight-from-usage aggregates the
investigation found durable are included: the log-log power-law fit of
cache_read against request count (``cache_read ∝ requests^k`` — the one stable
law of context carry), and the subagent tail (p50/p90/p99 of turns and cost —
where the runaways hide).

Output: human-readable summary by default, ``--json`` for the full structure.
Exit 1 when the project directory cannot be found; else exit 0.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import List, Optional

# ---------------------------------------------------------------------------
# Price table — per-Mtok dollars (2026-07 sticker prices, published reference).
# inp/out are base input/output; cw5/cw1h are cache writes at 5m/1h TTL
# (1.25x / 2x input); cr is cache read (0.1x input). Sonnet 5 carries an
# introductory $2/$10 through 2026-08-31 — the table bills the sticker price.
# ---------------------------------------------------------------------------

PRICE: dict[str, dict[str, float]] = {
    "fable": {"inp": 10.0, "out": 50.0, "cw5": 12.5, "cw1h": 20.0, "cr": 1.0},
    "mythos": {"inp": 10.0, "out": 50.0, "cw5": 12.5, "cw1h": 20.0, "cr": 1.0},
    "opus": {"inp": 5.0, "out": 25.0, "cw5": 6.25, "cw1h": 10.0, "cr": 0.5},
    "sonnet": {"inp": 3.0, "out": 15.0, "cw5": 3.75, "cw1h": 6.0, "cr": 0.3},
    "haiku": {"inp": 1.0, "out": 5.0, "cw5": 1.25, "cw1h": 2.0, "cr": 0.1},
}


def _family(model: Optional[str]) -> Optional[str]:
    """Match *model* to a PRICE family by substring, or None (→ unpriced)."""
    lowered = (model or "").lower()
    for key in PRICE:
        if key in lowered:
            return key
    return None


def _cost(usage: dict, model: Optional[str]) -> Optional[float]:
    """Dollar cost of one billed request, or None for an out-of-table model."""
    family = _family(model)
    if family is None:
        return None
    p = PRICE[family]
    cc = usage.get("cache_creation") or {}
    w1h = cc.get("ephemeral_1h_input_tokens", 0)
    w5 = cc.get("ephemeral_5m_input_tokens", 0)
    if not (w1h or w5):
        # Breakdown absent: charge the bare total at the 1h rate (conservative).
        w1h = usage.get("cache_creation_input_tokens", 0)
    return (
        usage.get("input_tokens", 0) * p["inp"]
        + usage.get("output_tokens", 0) * p["out"]
        + w1h * p["cw1h"]
        + w5 * p["cw5"]
        + usage.get("cache_read_input_tokens", 0) * p["cr"]
    ) / 1e6


# ---------------------------------------------------------------------------
# Transcript scanning
# ---------------------------------------------------------------------------


def scan_file(path: Path) -> List[dict]:
    """Read one transcript into deduped billed-request rows.

    Keeps the FIRST record per billed id (``message.id`` → ``requestId`` →
    record ``uuid``) — the content-block duplicates carry byte-identical
    cumulative ``usage``, so first-wins matches the verified prototype.
    Tolerant: unreadable file → ``[]``; a torn line is skipped.
    """
    rows: List[dict] = []
    seen: set = set()
    try:
        handle = open(path, encoding="utf-8", errors="ignore")
    except OSError:
        return rows
    with handle:
        for line in handle:
            try:
                d = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(d, dict) or d.get("type") != "assistant":
                continue
            m = d.get("message") or {}
            usage = m.get("usage")
            if not isinstance(usage, dict):
                continue
            mid = m.get("id") or d.get("requestId") or d.get("uuid")
            if mid in seen:
                continue
            seen.add(mid)
            model = m.get("model")
            rows.append({"model": model, "usage": usage, "cost": _cost(usage, model)})
    return rows


def _aggregate(rows: List[dict]) -> dict:
    """Fold deduped rows into the per-scope sums the report serves."""
    agg = {
        "requests": len(rows),
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_5m_tokens": 0,
        "cache_write_1h_tokens": 0,
        "peak_context_tokens": 0,
        "cost_usd": 0.0,
        "unpriced_requests": 0,
    }
    for row in rows:
        u = row["usage"]
        inp = u.get("input_tokens", 0)
        read = u.get("cache_read_input_tokens", 0)
        cc = u.get("cache_creation") or {}
        w1h = cc.get("ephemeral_1h_input_tokens", 0)
        w5 = cc.get("ephemeral_5m_input_tokens", 0)
        if not (w1h or w5):
            w1h = u.get("cache_creation_input_tokens", 0)
        agg["input_tokens"] += inp
        agg["output_tokens"] += u.get("output_tokens", 0)
        agg["cache_read_tokens"] += read
        agg["cache_write_5m_tokens"] += w5
        agg["cache_write_1h_tokens"] += w1h
        agg["peak_context_tokens"] = max(agg["peak_context_tokens"], inp + read + w5 + w1h)
        if row["cost"] is None:
            agg["unpriced_requests"] += 1
        else:
            agg["cost_usd"] += row["cost"]
    agg["cost_usd"] = round(agg["cost_usd"], 4)
    return agg


# ---------------------------------------------------------------------------
# The two durable read-straight-from-usage aggregates
# ---------------------------------------------------------------------------


def loglog_fit(xs: List[float], ys: List[float]) -> Optional[dict]:
    """Least-squares fit of ``log(y) = k*log(x) + c`` → ``{k, r, n}``.

    The power-law exponent for ``y ∝ x^k`` plus the correlation coefficient.
    Pairs with a non-positive member are dropped (log-undefined); returns None
    below 3 usable pairs or when either axis is constant.
    """
    pairs = [(math.log(x), math.log(y)) for x, y in zip(xs, ys) if x > 0 and y > 0]
    n = len(pairs)
    if n < 3:
        return None
    lx = [p[0] for p in pairs]
    ly = [p[1] for p in pairs]
    mx = sum(lx) / n
    my = sum(ly) / n
    sxx = sum((v - mx) ** 2 for v in lx)
    syy = sum((v - my) ** 2 for v in ly)
    sxy = sum((a - mx) * (b - my) for a, b in pairs)
    if sxx == 0 or syy == 0:
        return None
    k = sxy / sxx
    r = sxy / math.sqrt(sxx * syy)
    return {"k": round(k, 3), "r": round(r, 3), "n": n}


def _percentile(sorted_values: List[float], q: float) -> float:
    """Nearest-rank percentile over pre-sorted values (q in [0, 100])."""
    if not sorted_values:
        return 0.0
    rank = max(1, math.ceil(q / 100 * len(sorted_values)))
    return sorted_values[rank - 1]


def _tail(values: List[float]) -> dict:
    """p50/p90/p99 summary of *values* (the subagent-runaway view)."""
    ordered = sorted(values)
    return {
        "p50": _percentile(ordered, 50),
        "p90": _percentile(ordered, 90),
        "p99": _percentile(ordered, 99),
    }


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------


def default_project_dir() -> Path:
    """The Claude Code project dir for the CWD (path slug: ``/`` and ``.`` → ``-``)."""
    slug = str(Path.cwd().resolve()).replace("/", "-").replace(".", "-")
    return Path.home() / ".claude" / "projects" / slug


def build_report(project_dir: Path, session_id: Optional[str] = None) -> dict:
    """Scan *project_dir* (optionally one session) into the full report dict."""
    if session_id:
        transcripts = [project_dir / f"{session_id}.jsonl"]
    else:
        transcripts = sorted(
            project_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime
        )

    sessions: List[dict] = []
    all_sub_rows: List[List[dict]] = []
    for transcript in transcripts:
        main_rows = scan_file(transcript)
        sub_files = sorted((project_dir / transcript.stem / "subagents").glob("*.jsonl"))
        sub_rows_per_file = [scan_file(p) for p in sub_files]
        sub_rows_per_file = [rows for rows in sub_rows_per_file if rows]
        if not main_rows and not sub_rows_per_file:
            continue
        all_sub_rows.extend(sub_rows_per_file)
        flat_sub = [row for rows in sub_rows_per_file for row in rows]
        main_agg = _aggregate(main_rows)
        sub_agg = _aggregate(flat_sub)
        sessions.append({
            "session": transcript.stem,
            "main": main_agg,
            "subagents": {"agents": len(sub_rows_per_file), **sub_agg},
            "total_cost_usd": round(main_agg["cost_usd"] + sub_agg["cost_usd"], 4),
        })

    totals = {
        "sessions": len(sessions),
        "cost_usd": round(sum(s["total_cost_usd"] for s in sessions), 4),
        "unpriced_requests": sum(
            s["main"]["unpriced_requests"] + s["subagents"]["unpriced_requests"]
            for s in sessions
        ),
    }

    # cache_read ∝ requests^k across orchestrator sessions; ∝ turns^k inside
    # subagents (one point per subagent file; turns = its billed requests).
    fits = {
        "orchestrator_cache_read_vs_requests": loglog_fit(
            [float(s["main"]["requests"]) for s in sessions],
            [float(s["main"]["cache_read_tokens"]) for s in sessions],
        ),
        "subagent_cache_read_vs_turns": loglog_fit(
            [float(len(rows)) for rows in all_sub_rows],
            [float(_aggregate(rows)["cache_read_tokens"]) for rows in all_sub_rows],
        ),
    }

    sub_turns = [float(len(rows)) for rows in all_sub_rows]
    sub_costs = [round(_aggregate(rows)["cost_usd"], 4) for rows in all_sub_rows]
    subagent_tail = {
        "agents": len(all_sub_rows),
        "turns": _tail(sub_turns),
        "cost_usd": _tail(sub_costs),
    }

    return {
        "project_dir": str(project_dir),
        "sessions": sessions,
        "totals": totals,
        "fits": fits,
        "subagent_tail": subagent_tail,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _fmt_tokens(n: int) -> str:
    return f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.0f}k" if n >= 1e3 else str(n)


def _render_human(report: dict) -> str:
    lines = [f"project: {report['project_dir']}"]
    for s in report["sessions"]:
        m, sub = s["main"], s["subagents"]
        lines.append(
            f"  {s['session'][:24]:<24} req {m['requests']:>4}  "
            f"read {_fmt_tokens(m['cache_read_tokens']):>7}  "
            f"write {_fmt_tokens(m['cache_write_5m_tokens'] + m['cache_write_1h_tokens']):>7}  "
            f"out {_fmt_tokens(m['output_tokens']):>7}  "
            f"peak {_fmt_tokens(m['peak_context_tokens']):>7}  "
            f"agents {sub['agents']:>3}  ${s['total_cost_usd']:.2f}"
        )
    t = report["totals"]
    lines.append(f"total: {t['sessions']} sessions, ${t['cost_usd']:.2f}")
    if t["unpriced_requests"]:
        lines.append(
            f"WARNING: {t['unpriced_requests']} requests on models outside the "
            "price table contributed $0.00 — totals understate true cost"
        )
    for name, fit in report["fits"].items():
        if fit is not None:
            lines.append(f"fit {name}: k={fit['k']} r={fit['r']} n={fit['n']}")
    tail = report["subagent_tail"]
    if tail["agents"]:
        lines.append(
            f"subagent tail (n={tail['agents']}): turns p50/p90/p99 = "
            f"{tail['turns']['p50']:.0f}/{tail['turns']['p90']:.0f}/{tail['turns']['p99']:.0f}, "
            f"cost = ${tail['cost_usd']['p50']:.2f}/${tail['cost_usd']['p90']:.2f}/"
            f"${tail['cost_usd']['p99']:.2f}"
        )
    return "\n".join(lines) + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-session-tokens",
        description=(
            "Report the harness's own runtime token cost from session-transcript "
            "usage records: dedup by billed message.id, price from a table, "
            "split orchestrator vs subagents by file path, classify nothing."
        ),
    )
    parser.add_argument(
        "--project-dir", default=None, metavar="PATH",
        help="Claude Code project dir (~/.claude/projects/<slug>); defaults to "
             "the CWD's project dir.",
    )
    parser.add_argument(
        "--session", default=None, metavar="ID",
        help="Limit the report to one session id (transcript basename).",
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit the full report as JSON."
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    project_dir = Path(args.project_dir) if args.project_dir else default_project_dir()
    if not project_dir.is_dir():
        sys.stderr.write(
            f"cortex-session-tokens: no project dir at {project_dir} — pass "
            "--project-dir, or run from the repo whose sessions you want.\n"
        )
        return 1
    report = build_report(project_dir, session_id=args.session)
    if args.json:
        sys.stdout.write(json.dumps(report, separators=(",", ":")) + "\n")
    else:
        sys.stdout.write(_render_human(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
