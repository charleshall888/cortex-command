"""Wiring guard for the dev-router triage offload.

Originally (#343) this pinned two consumer-keyed references extracted from
``skills/dev/SKILL.md``. ``references/triage-rendering.md`` has since been
retired: the block rendering it described is mechanical (group by epic, pick a
badge from ``status``, pick a recommendation sentence from ``spec:`` presence),
so it moved into the ``cortex-backlog-triage`` verb, which returns the rendered
markdown. Prose the model re-read on every triage became code with tests.

What still needs guarding is the same thing the original test guarded — that
the logic does not silently drift back into the skill body — plus the new
seam: the skill must invoke the verb, and the verb must still render.

The *runtime* missed-read / read-but-not-applied failure stays deliberately out
of scope: it is untestable in a static check, so this gate is honest rather
than self-sealing.
"""

from __future__ import annotations

import inspect
import json
import pathlib

from cortex_command.backlog import triage as triage_mod


# Full-span negative control: rendering-rule tokens that must NOT be resident
# in the skill body. Some are historical (the retired criticality-heuristics
# block); the rest are the triage-rendering rules now owned by the verb.
_MOVED_TOKENS = (
    # criticality-heuristics block
    "Payments, billing, financial data",
    "### Heuristic Signals",
    "### Forming the Suggestion",
    "No elevated signals",
    # triage-rendering block
    "Flat Ready List",
    "Per-epic workflow recommendation",
    "Suppress children",
    "Suppress epics",
    "No active child tickets found",
    # rendering rules that moved into the verb with the reference
    "Block 1: Epic sections",
    "Block 2: Flat ready list",
    "priority/type badges",
)

# The stub headings that must survive as anchors.
_STUB_HEADINGS = ("## Step 2: Criticality Pre-Assessment",)


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[1]


def _skill_path() -> pathlib.Path:
    return _repo_root() / "skills" / "dev" / "SKILL.md"


def _skill_lines() -> list[str]:
    return _skill_path().read_text(encoding="utf-8").splitlines()


def test_retired_reference_is_gone_from_both_trees() -> None:
    """triage-rendering.md must not come back in either tree."""
    root = _repo_root()
    for path in (
        root / "skills" / "dev" / "references" / "triage-rendering.md",
        root
        / "plugins"
        / "cortex-core"
        / "skills"
        / "dev"
        / "references"
        / "triage-rendering.md",
    ):
        assert not path.exists(), (
            f"{path} is back — the triage rendering rules belong to "
            "cortex-backlog-triage, not to prose re-read on every triage"
        )


def test_skill_invokes_the_triage_verb() -> None:
    """The dev router must route triage through the composite verb."""
    text = _skill_path().read_text(encoding="utf-8")
    assert "cortex-backlog-triage" in text, (
        "skills/dev/SKILL.md no longer invokes cortex-backlog-triage; Step 3 "
        "would have no way to reach the backend, index, or epic map"
    )


def test_verb_renders_the_blocks() -> None:
    """The verb must still emit rendered markdown, not just structured data."""
    source = inspect.getsource(triage_mod.main)
    assert '"blocks"' in source, (
        "cortex-backlog-triage no longer returns a rendered 'blocks' field; the "
        "skill has no rendering rules of its own to fall back on"
    )
    render_src = inspect.getsource(triage_mod.render) + inspect.getsource(
        triage_mod._render_epic_block
    ) + inspect.getsource(triage_mod._recommendation)
    for token in ("## Epics", "## Ready", "/cortex-core:refine", "/cortex-overnight:overnight"):
        assert token in render_src, (
            f"the renderer lost the {token!r} anchor — the block protocol regressed"
        )


def test_envelope_carries_no_unread_structured_mirrors(
    tmp_path, monkeypatch, capsys
) -> None:
    """``blocks`` is the product; ``epics``/``flat`` mirrors must not come back.

    Both were emitted beside ``blocks`` and read by nothing: every version of
    ``skills/dev/SKILL.md`` acts on ``state`` and prints ``blocks``. On a
    467-item repo they were 45,891 of the envelope's 54,046 chars — the caller
    parsed 6.9x what it used — and ``epics`` had drifted into contradicting
    ``blocks``, still carrying the closed children the rendering drops.

    Asserted against the emitted JSON rather than ``main``'s source: the first
    cut of this guard grepped for ``"epics"`` and matched the degraded
    epic-map fallback ``{"epics": {}}``, an internal literal with nothing to do
    with the envelope. Re-adding a structured field is not forbidden; adding one
    with no consumer is.
    """
    backlog = tmp_path / "cortex" / "backlog"
    backlog.mkdir(parents=True)
    (tmp_path / ".git").mkdir()
    items = [
        {"schema_version": "1", "id": 1, "title": "Ready thing", "status": "backlog",
         "priority": "high", "type": "feature", "spec": None, "parent": None,
         "blocked_by": [], "tags": [], "uuid": None},
    ]
    (backlog / "index.json").write_text(json.dumps(items), encoding="utf-8")
    (backlog / "index-full.json").write_text(json.dumps(items), encoding="utf-8")
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)

    assert triage_mod.main(["--no-regen"]) == 0
    envelope = json.loads(capsys.readouterr().out)

    assert envelope["state"] == "ok"
    assert set(envelope) == {"state", "backend", "index", "blocks"}, (
        "cortex-backlog-triage grew an envelope field — name its consumer, or "
        "the caller parses JSON nothing reads"
    )
    assert "Ready thing" in envelope["blocks"]


def test_stub_headings_survive() -> None:
    lines = {ln.strip() for ln in _skill_lines()}
    for heading in _STUB_HEADINGS:
        assert heading in lines, f"stub heading must be kept as an anchor: {heading}"


def test_moved_content_absent_from_body_negative_control() -> None:
    """Full-span negative control: no moved token remains resident in the body."""
    text = _skill_path().read_text(encoding="utf-8")
    resident = [tok for tok in _MOVED_TOKENS if tok in text]
    assert not resident, (
        f"rendering logic is resident in skills/dev/SKILL.md again: {resident}. "
        "It belongs in cortex_command/backlog/triage.py."
    )
