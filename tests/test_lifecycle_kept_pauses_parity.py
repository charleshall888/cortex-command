"""Marker-set parity + freshness + per-kind semantic checks for kept pauses.

The kept-pause taxonomy has a single durable source of truth,
``skills/lifecycle/references/kept-pauses-data.toml`` — one ``[[pause]]`` row per
``<!-- pause: <slug> <kind> -->`` marker across ``skills/lifecycle`` and
``skills/refine``. The human-readable inventory
``skills/lifecycle/references/kept-pauses.md`` is GENERATED from that data file by
the ``cortex-generate-kept-pauses`` generator (``generate_md``); never hand-edit
it. This test replaces the retired line-anchored inventory-bullet scheme
(``LINE_TOLERANCE`` / rough ``file:line`` anchors).

Three invariants:

(a) **Set-equality** — the set of marker slugs parsed from prose equals the set
    of ``id`` values in the data file. An orphan marker (no data row) and a data
    row with no marker both fail. Each marker's kind must also match its data row.

(b) **Freshness** — regenerating the inventory in-memory from the data file (via
    the generator's pure ``generate_md``) must byte-match the committed
    ``kept-pauses.md``. A stale committed doc fails.

(c) **Per-kind semantic sub-checks**, anchored on each marker's line:
      * ``phase-exit-wait`` -> a section/step heading within ``PROXIMITY_WINDOW``
        lines of the marker.
      * config-``suppressed_by`` (a real ``lifecycle.config.md`` key, not
        ``judgment``) -> the suppression wiring token near the marker.
      * ``question`` / ``relayed-consent`` -> an ``AskUserQuestion`` literal, or
        (for a prose-ask / relayed-consent site) one of a small documented
        allowlist of ask-verb / approval-surface tokens, near the marker.
    (c) restores invariant #1 of the retired line-anchored test — every consent
    pause points to a real interaction site — for the two highest-stakes kinds,
    which set-equality alone does not cover.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from cortex_command.lifecycle.generate_kept_pauses import generate_md

REPO_ROOT = Path(__file__).resolve().parent.parent
KEPT_PAUSES_MD = REPO_ROOT / "skills" / "lifecycle" / "references" / "kept-pauses.md"
KEPT_PAUSES_DATA = (
    REPO_ROOT / "skills" / "lifecycle" / "references" / "kept-pauses-data.toml"
)
SKILL_DIRS = ("skills/lifecycle", "skills/refine")

# `<!-- pause: <slug> <kind> -->` marker. Strict slug (kebab) + kind classes so
# the literal `<!-- pause: <slug> <kind> -->` placeholder text inside
# kept-pauses.md / kept-pauses-data.toml prose never matches.
_MARKER_RE = re.compile(r"<!--\s*pause:\s+([a-z][a-z0-9-]*)\s+([a-z][a-z-]*[a-z])\s+-->")

_KINDS = {"question", "phase-exit-wait", "config-conditional", "relayed-consent"}

# Proximity window (lines above/below a marker) for the semantic sub-checks.
# Markers are authored immediately adjacent to their interaction site; the max
# observed marker->token distance in the corpus is 2 lines. Kept deliberately
# small so the check stays discriminating.
PROXIMITY_WINDOW = 8

# Section/step heading (validates phase-exit-wait markers).
_HEADING_RE = re.compile(r"^#{1,6}\s+\S")

# Consent-proximity allowlist (case-insensitive substrings): the canonical
# interaction literal plus a small, documented set of prose-ask / approval-
# surface verb phrases, for the sites that pause via prose rather than a literal
# `AskUserQuestion` call (disambiguation pickers, the empty-topic prompt, the
# batch-failure / test-command / open-decision asks). Deliberately specific verb
# phrases — bare "ask"/"prompt" would be too loose to be a meaningful signal.
_CONSENT_TOKENS = (
    "askuserquestion",   # canonical interaction literal
    "ask the user",      # prose-ask (batch failure, test-command, open decision)
    "ask which",         # prose-ask disambiguation picker (orphan PR, resume feature)
    "prompt the user",   # prose-ask empty-topic prompt (refine)
    "approval surface",  # relayed-consent approval site
    "approve",           # approval verb (relayed-consent)
)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _iter_markers() -> list[tuple[str, str, Path, int]]:
    """Return (slug, kind, path, line_num) for every prose pause marker.

    Scans ``*.md`` under skills/lifecycle and skills/refine, excluding the
    generated inventory (which echoes the marker syntax in prose).
    """
    out: list[tuple[str, str, Path, int]] = []
    kept_pauses_md = KEPT_PAUSES_MD.resolve()
    for skill_dir in SKILL_DIRS:
        for md_path in sorted((REPO_ROOT / skill_dir).rglob("*.md")):
            if md_path.resolve() == kept_pauses_md:
                continue
            text = md_path.read_text(encoding="utf-8")
            for idx, line in enumerate(text.splitlines(), start=1):
                m = _MARKER_RE.search(line)
                if m:
                    out.append((m.group(1), m.group(2), md_path, idx))
    return out


def _load_data() -> list[dict]:
    """Parse the pause taxonomy TOML into a list of ``[[pause]]`` tables."""
    with KEPT_PAUSES_DATA.open("rb") as fh:
        return tomllib.load(fh).get("pause", [])


# ---------------------------------------------------------------------------
# Pure check helpers (shared by the live checks and the negative controls)
# ---------------------------------------------------------------------------


def _parity_diff(marker_ids: set[str], data_ids: set[str]) -> tuple[set[str], set[str]]:
    """Return (orphan markers, missing markers) between the two id sets."""
    return marker_ids - data_ids, data_ids - marker_ids


def _window_text(lines: list[str], anchor: int) -> str:
    """Return the text of the ±PROXIMITY_WINDOW lines around 1-indexed ``anchor``."""
    lo = max(0, anchor - 1 - PROXIMITY_WINDOW)
    hi = min(len(lines), anchor + PROXIMITY_WINDOW)
    return "\n".join(lines[lo:hi])


def _config_wiring_tokens(suppressed_by: str) -> set[str]:
    """Candidate wiring tokens for a config-``suppressed_by`` key.

    Accepts the raw key, its hyphen->space and dot->space variants, and (for a
    dotted key like ``backlog.backend``) the final segment (``backend``) — the
    forms in which the suppressing config key actually surfaces in skill prose.
    """
    base = suppressed_by.lower()
    toks = {base, base.replace("-", " ")}
    if "." in base:
        toks.add(base.replace(".", " "))
        toks.add(base.rsplit(".", 1)[-1])
    return toks


def _semantic_problem(
    slug: str, kind: str, suppressed_by: str | None, lines: list[str], line: int
) -> str | None:
    """Return a problem string if the marker lacks its semantic anchor, else None.

    Applies every check that fits the row (a config-suppressed ``question`` gets
    both the config-wiring and the consent-proximity check).
    """
    window = _window_text(lines, line)
    window_lc = window.lower()

    if kind == "phase-exit-wait":
        if not any(_HEADING_RE.match(ln) for ln in window.splitlines()):
            return (
                f"{slug} (phase-exit-wait) has no section/step heading within "
                f"±{PROXIMITY_WINDOW} lines of the marker"
            )

    if suppressed_by and suppressed_by != "judgment":
        toks = _config_wiring_tokens(suppressed_by)
        if not any(t in window_lc for t in toks):
            return (
                f"{slug} (suppressed_by={suppressed_by!r}) lacks a suppression "
                f"wiring token {sorted(toks)} within ±{PROXIMITY_WINDOW} lines "
                f"of the marker"
            )

    if kind in ("question", "relayed-consent"):
        if not any(t in window_lc for t in _CONSENT_TOKENS):
            return (
                f"{slug} ({kind}) has no interaction token "
                f"{list(_CONSENT_TOKENS)} within ±{PROXIMITY_WINDOW} lines of "
                f"the marker (expected an AskUserQuestion literal or an "
                f"allowlisted prose-ask / approval-surface token)"
            )

    return None


# ---------------------------------------------------------------------------
# (a) Set-equality + kind consistency
# ---------------------------------------------------------------------------


def test_marker_set_equals_data_set() -> None:
    """Exact set-equality between prose marker slugs and data-file ids."""
    marker_ids = {slug for slug, _kind, _path, _line in _iter_markers()}
    data_ids = {row["id"] for row in _load_data()}
    assert marker_ids, "No pause markers parsed — the marker regex may have drifted"
    orphan, missing = _parity_diff(marker_ids, data_ids)
    assert not orphan and not missing, (
        f"orphan markers (no data row): {sorted(orphan)}; "
        f"data rows without a marker: {sorted(missing)}"
    )


def test_marker_kinds_valid_and_match_data() -> None:
    """Every marker kind is a known kind, is unique, and matches its data row."""
    data_by_id = {row["id"]: row for row in _load_data()}
    problems: list[str] = []
    seen: dict[str, str] = {}
    for slug, kind, path, line in _iter_markers():
        rel = f"{path.relative_to(REPO_ROOT)}:{line}"
        if kind not in _KINDS:
            problems.append(f"{rel} marker {slug!r} has unknown kind {kind!r}")
        if slug in seen:
            problems.append(f"duplicate marker slug {slug!r} at {rel} and {seen[slug]}")
        seen[slug] = rel
        row = data_by_id.get(slug)
        if row is not None and row.get("kind") != kind:
            problems.append(
                f"{rel} marker {slug!r} kind {kind!r} != data-file kind "
                f"{row.get('kind')!r}"
            )
    assert not problems, "\n".join(problems)


# ---------------------------------------------------------------------------
# (b) Freshness
# ---------------------------------------------------------------------------


def test_committed_inventory_is_fresh() -> None:
    """The committed kept-pauses.md byte-matches a fresh regeneration."""
    expected = generate_md(_load_data())
    actual = KEPT_PAUSES_MD.read_text(encoding="utf-8")
    assert actual == expected, (
        "kept-pauses.md is stale — regenerate with "
        "`CORTEX_COMMAND_FORCE_SOURCE=1 cortex-generate-kept-pauses --write` "
        "(or `just kept-pauses`) and commit the result."
    )


# ---------------------------------------------------------------------------
# (c) Per-kind semantic sub-checks
# ---------------------------------------------------------------------------


def test_markers_have_semantic_anchors() -> None:
    """Each marker's kind-appropriate interaction/heading/wiring anchor exists."""
    marker_loc = {slug: (path, line) for slug, _kind, path, line in _iter_markers()}
    problems: list[str] = []
    for row in _load_data():
        slug = row["id"]
        loc = marker_loc.get(slug)
        if loc is None:
            # Missing marker is owned by the set-equality test; skip here.
            continue
        path, line = loc
        lines = path.read_text(encoding="utf-8").splitlines()
        problem = _semantic_problem(
            slug, row["kind"], row.get("suppressed_by"), lines, line
        )
        if problem is not None:
            problems.append(f"{path.relative_to(REPO_ROOT)}:{line} — {problem}")
    assert not problems, "\n".join(problems)


# ---------------------------------------------------------------------------
# Negative controls — assert each check actually fails on bad input.
# These use synthetic in-memory corpora / id sets; they never touch the tree.
# ---------------------------------------------------------------------------


def test_negative_marker_without_data_row() -> None:
    """A marker slug with no data row is reported as an orphan."""
    orphan, missing = _parity_diff({"real-pause", "ghost-marker"}, {"real-pause"})
    assert orphan == {"ghost-marker"} and not missing


def test_negative_data_row_without_marker() -> None:
    """A data row with no marker is reported as missing."""
    orphan, missing = _parity_diff({"real-pause"}, {"real-pause", "ghost-row"})
    assert missing == {"ghost-row"} and not orphan


def test_negative_stale_committed_doc() -> None:
    """A hand-edited (drifted) inventory does not match a fresh regeneration."""
    fresh = generate_md(_load_data())
    stale = fresh.replace("`plan-approval`", "`plan-approval-TAMPERED`", 1)
    assert stale != fresh, "sentinel replacement did not apply"
    assert fresh != stale  # the freshness comparison would fail on this drift


def test_negative_config_wiring_deleted() -> None:
    """A config-suppressed marker whose wiring prose was deleted is flagged."""
    lines = [
        "<!-- pause: sample config-conditional -->",
        "Some prose that no longer mentions the suppressing config key at all.",
    ]
    problem = _semantic_problem(
        "sample", "config-conditional", "branch-mode", lines, 1
    )
    assert problem is not None and "suppression wiring token" in problem


def test_negative_relayed_consent_no_interaction_token() -> None:
    """A relayed-consent marker with no nearby interaction token is flagged."""
    lines = [
        "<!-- pause: sample relayed-consent -->",
        "Prose describing the plan with no interaction verb or literal nearby.",
    ]
    problem = _semantic_problem("sample", "relayed-consent", None, lines, 1)
    assert problem is not None and "interaction token" in problem


def test_negative_phase_exit_no_heading() -> None:
    """A phase-exit-wait marker with no nearby heading is flagged."""
    lines = [
        "Ordinary prose above the marker with no heading in sight.",
        "<!-- pause: sample phase-exit-wait -->",
        "Ordinary prose below the marker, still no heading.",
    ]
    problem = _semantic_problem("sample", "phase-exit-wait", None, lines, 2)
    assert problem is not None and "heading" in problem
