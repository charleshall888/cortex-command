"""Permanent structural census of raw per-feature ``events.log`` writers.

This test replaces the manual writer re-audit (374 spec R1 acceptance *a*) with a
standing structural gate: it scans ``cortex_command/`` and ``plugins/`` for *raw*
per-feature ``events.log`` write expressions and fails if any hit is outside the
explicit ``ALLOWLIST`` maintained below. events.log is the loop's only durable
state, so ALL per-feature emission must funnel through the one shared locked
primitive (``lifecycle_event._append_event_atomic`` — flock + ``O_APPEND``);
Tasks 1-3 removed the last raw per-feature writers outside the sanctioned set
(``critical_review``, ``discovery``, ``refine``, ``complexity_escalator`` now
route through ``log_event``/``log_event_at``). This census keeps it that way.

SCOPE BOUNDARY (do not overclaim). The census scans raw-write *syntax* only:

  * append-mode ``open(<events.log>, "a")`` bare appends,
  * ``os.replace`` targeting an events.log path,
  * ``NamedTemporaryFile`` + replace onto events.log,
  * direct use of the private ``_append_event_atomic`` primitive.

It is *blind* to ``log_event``/``log_event_at``-routed emission by construction:
``overnight/advance_lifecycle.py`` and ``pipeline/review_dispatch.py`` emit via
``log_event`` and were never census hits, so a ``log_event``-routed independent
transition-decision is invisible here. Fold-completion of those two decision
authorities is NOT this test's job — it gets its own positive test in Task 17a.
This census only proves that no writer reaches the events.log bytes through raw
syntax outside the sanctioned primitive family.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCAN_ROOTS = ("cortex_command", "plugins")

# Sanctioned raw per-feature events.log writers, keyed by repo-relative module
# path. Every census hit MUST resolve to a module in this map, and (stale-entry
# guard below) every module in this map must still be a live hit — so the
# allowlist shrinks structurally as writers fold (spec R15), never rots.
ALLOWLIST: dict[str, str] = {
    "cortex_command/lifecycle_event.py": (
        "Canonical shared primitive. Defines and calls _append_event_atomic "
        "(sibling-lockfile flock + O_APPEND, one bounded row per call) — the "
        "single locked appender every per-feature emission funnels through."
    ),
    "cortex_command/lifecycle/wontfix_cli.py": (
        "Sanctioned sibling. Appends the byte-faithful feature_wontfix marker "
        "to the archived events.log via the shared _append_event_atomic "
        "primitive (ADR-0020 hand-written exempt event; writes to the "
        "archived path log_event's cwd-resolution cannot address)."
    ),
    "cortex_command/lifecycle/record_pr_opened.py": (
        "Sanctioned sibling. Appends the ADR-0020 exempt pr_opened row "
        "(schema_version-first shape) via the shared _append_event_atomic "
        "primitive, bypassing log_event's uniform {ts,event,feature,...} "
        "shape on purpose while keeping the shared flock discipline."
    ),
}

# Different-file sinks the 374 exploration confirmed are NOT the per-feature
# events.log (spec: explicitly excluded). Encoded as {(relpath, lineno): why}.
# The events.log target discriminator already skips them (none carries an
# ``events_log``/``events.log`` token), so this map is a documented assertion
# that the discriminator keeps separating them — see the sanity test below.
EXCLUDED_SINKS: dict[tuple[str, int], str] = {
    ("cortex_command/overnight/events.py", 242):
        "overnight session log (overnight-events.log) — not per-feature.",
    ("cortex_command/overnight/auth.py", 233):
        "overnight auth event log — not per-feature.",
    ("cortex_command/backlog/update_item.py", 178):
        "backlog item's {stem}.events.jsonl — not the lifecycle events.log.",
    ("cortex_command/backlog/create_item.py", 103):
        "backlog item's {stem}.events.jsonl — not the lifecycle events.log.",
}

# --------------------------------------------------------------------------- #
# Scan
# --------------------------------------------------------------------------- #

# Target-side signal that a raw-write expression addresses a per-feature
# events.log (variable ``events_log``/``events_log_path``/``feature_events_log``
# or a literal ``"events.log"``). The distinct sink variables the excluded
# different-file sinks use (``log_path``, ``event_log_path``, ``events_path``)
# do NOT match, which is what keeps them out of the census.
_EVENTS_LOG_TARGET = re.compile(r"events_log|events\.log")

# Append-mode builtin open on an events.log target: open(...) + an "a"/"ab"/"a+"
# mode literal on the same statement (all such appends are single-line here).
_APPEND_OPEN = re.compile(r"\bopen\s*\(")
_APPEND_MODE = re.compile(r"""["']a[b+]?["']""")

# os.replace / raw O_APPEND os.open targeting an events.log path.
_OS_REPLACE = re.compile(r"\bos\.replace\s*\(")
_OS_OPEN_APPEND = re.compile(r"\bos\.open\s*\(")
_O_APPEND = re.compile(r"\bO_APPEND\b")

# Direct use of the private shared primitive (a call, not the def/import/prose).
_APPEND_EVENT_CALL = re.compile(r"\b_append_event_atomic\s*\(")
_DEF_LINE = re.compile(r"^\s*def\s")

_NAMED_TEMPFILE = re.compile(r"\bNamedTemporaryFile\s*\(")


def _iter_source_files():
    """Yield (relpath, absolute Path) for every non-test .py under the scan roots."""
    for root in _SCAN_ROOTS:
        base = _REPO_ROOT / root
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            parts = path.relative_to(_REPO_ROOT).parts
            if "tests" in parts or path.name.startswith("test_"):
                continue
            if path.resolve() == Path(__file__).resolve():
                continue
            yield "/".join(path.relative_to(_REPO_ROOT).parts), path


def _scan_hits() -> list[tuple[str, int, str, str]]:
    """Return raw per-feature events.log write hits as (relpath, lineno, kind, line)."""
    hits: list[tuple[str, int, str, str]] = []
    for relpath, path in _iter_source_files():
        lines = path.read_text(encoding="utf-8").splitlines()

        # A module is a NamedTemporaryFile+replace writer only if it ALSO
        # os.replace's onto an events.log target; collect that fact first.
        module_replaces_events_log = any(
            _OS_REPLACE.search(ln) and _EVENTS_LOG_TARGET.search(ln) for ln in lines
        )

        for idx, line in enumerate(lines, start=1):
            key = (relpath, idx)

            # (D) Direct private-primitive use — any call site is a raw writer.
            if _APPEND_EVENT_CALL.search(line) and not _DEF_LINE.match(line):
                hits.append((relpath, idx, "_append_event_atomic", line.strip()))
                continue

            has_events_target = bool(_EVENTS_LOG_TARGET.search(line))

            # (A) Append-mode open on an events.log path.
            if (
                _APPEND_OPEN.search(line)
                and _APPEND_MODE.search(line)
                and has_events_target
                and key not in EXCLUDED_SINKS
            ):
                hits.append((relpath, idx, "append-open", line.strip()))
                continue

            # (B) os.replace targeting events.log.
            if _OS_REPLACE.search(line) and has_events_target and key not in EXCLUDED_SINKS:
                hits.append((relpath, idx, "os.replace", line.strip()))
                continue

            # (E) Raw O_APPEND os.open targeting events.log.
            if (
                _OS_OPEN_APPEND.search(line)
                and _O_APPEND.search(line)
                and has_events_target
                and key not in EXCLUDED_SINKS
            ):
                hits.append((relpath, idx, "os.open-O_APPEND", line.strip()))
                continue

            # (C) NamedTemporaryFile in a module that replaces onto events.log.
            if (
                _NAMED_TEMPFILE.search(line)
                and module_replaces_events_log
                and key not in EXCLUDED_SINKS
            ):
                hits.append((relpath, idx, "NamedTemporaryFile+replace", line.strip()))
                continue

    return hits


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def test_no_unsanctioned_raw_events_log_writers():
    """Every raw per-feature events.log write hit resolves to an ALLOWLIST module."""
    hits = _scan_hits()
    offenders = [h for h in hits if h[0] not in ALLOWLIST]
    assert not offenders, (
        "Unsanctioned raw per-feature events.log writer(s) found — route them "
        "through lifecycle_event.log_event / log_event_at, or (if genuinely a "
        "new sanctioned writer) add the module to ALLOWLIST with a rationale:\n"
        + "\n".join(f"  {r}:{n}  [{kind}]  {line}" for r, n, kind, line in offenders)
    )


def test_allowlist_has_no_stale_entries():
    """Every ALLOWLIST module is still a live raw writer (no rot; R15 shrink discipline)."""
    hit_modules = {h[0] for h in _scan_hits()}
    stale = sorted(set(ALLOWLIST) - hit_modules)
    assert not stale, (
        "ALLOWLIST entries no longer contain any raw events.log write — remove "
        "them so the allowlist shrinks as writers fold (spec R15):\n"
        + "\n".join(f"  {m}" for m in stale)
    )


def test_excluded_sinks_are_not_classified_as_hits():
    """The enumerated different-file sinks stay out of the census (discriminator sanity)."""
    hit_keys = {(r, n) for r, n, _kind, _line in _scan_hits()}
    misclassified = sorted(k for k in EXCLUDED_SINKS if k in hit_keys)
    assert not misclassified, (
        "A different-file sink was classified as a per-feature events.log writer "
        "(the events.log target discriminator regressed):\n"
        + "\n".join(f"  {r}:{n}  {EXCLUDED_SINKS[(r, n)]}" for r, n in misclassified)
    )


def test_acceptance_b_no_append_mode_events_log_open():
    """Spec R1 acceptance (b): no append-mode open on an events_log target.

    Runs the acceptance's literal pattern recursively over ``cortex_command/``
    (``-r`` added so the directory argument recurses; grep exit 1 == no match).
    """
    proc = subprocess.run(
        ["grep", "-rEn", r'open\([^)]*events_log[^)]*"a"', "cortex_command/"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1 and proc.stdout == "", (
        "append-mode open() on an events_log target found (bare unlocked append "
        "— route through the locked primitive):\n" + proc.stdout
    )
