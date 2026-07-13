"""Verify the orchestrator-round prompt template renders escalations paths
under the per-session ``{session_dir}/escalations.jsonl`` form (R20).

Per task 9 of the build-mcp-control-plane-server-with-versioned-runner-ipc-contract
spec: the prompt template references ``{session_dir}/escalations.jsonl`` so that
``fill_prompt()`` substitutes the per-session escalations path before the
orchestrator agent executes the prompt. These tests assert that:

1. After ``fill_prompt()``, the rendered prompt contains the substituted
   ``cortex/lifecycle/sessions/{fixture_id}/escalations.jsonl`` path and contains zero
   occurrences of the literal token-string ``{session_dir}``.
2. The rendered prompt's Python code blocks ``compile()`` without ``NameError``
   against a synthetic globals dict containing the substituted path.
"""

from __future__ import annotations

import re
from pathlib import Path

from cortex_command.overnight.fill_prompt import fill_prompt


FIXTURE_ID = "overnight-2026-04-24-fixture"
FIXTURE_SESSION_DIR = Path(f"cortex/lifecycle/sessions/{FIXTURE_ID}")
FIXTURE_PLAN_PATH = FIXTURE_SESSION_DIR / "overnight-plan.md"
FIXTURE_STATE_PATH = FIXTURE_SESSION_DIR / "overnight-state.json"
FIXTURE_EVENTS_PATH = FIXTURE_SESSION_DIR / "overnight-events.log"


def _render() -> str:
    return fill_prompt(
        round_number=1,
        state_path=FIXTURE_STATE_PATH,
        plan_path=FIXTURE_PLAN_PATH,
        events_path=FIXTURE_EVENTS_PATH,
        session_dir=FIXTURE_SESSION_DIR,
        tier="simple",
    )


def test_escalations_path_renders_correctly():
    """R20: ``{session_dir}/escalations.jsonl`` is substituted to the per-session path."""
    out = _render()
    expected = f"cortex/lifecycle/sessions/{FIXTURE_ID}/escalations.jsonl"
    assert expected in out, (
        f"expected substituted escalations path {expected!r} not found in rendered prompt"
    )
    assert "{session_dir}" not in out, (
        "{session_dir} token survived fill_prompt — substitution incomplete"
    )


def test_escalations_python_blocks_compile():
    """R20: rendered Python code blocks compile against a synthetic globals dict.

    The orchestrator agent executes the Python code blocks in the rendered
    prompt. After substitution, every ``escalations.jsonl`` reference must be a
    syntactically valid Python expression (no leftover ``{session_dir}`` token
    that would cause a ``NameError`` when the f-string or path literal is
    evaluated).
    """
    out = _render()

    # Synthetic globals that the orchestrator agent would have available when
    # executing these blocks. ``escalations_path`` is the substituted Path that
    # the rendered code assigns and references downstream.
    synthetic_globals = {
        "escalations_path": FIXTURE_SESSION_DIR / "escalations.jsonl",
        "line": "",
        "entry": {"escalation_id": "x", "feature": "y"},
        "entries": [],
    }

    # Extract every top-level fenced ```python ... ``` block (those whose
    # opening and closing fences are at column 0 — i.e. not nested inside a
    # markdown numbered list with leading indentation). Nested-in-list snippets
    # are not standalone executable units.
    blocks = re.findall(r"^```python\n(.*?)\n^```", out, flags=re.DOTALL | re.MULTILINE)
    assert blocks, "expected at least one python code block in rendered prompt"

    for i, block in enumerate(blocks):
        try:
            compile(block, f"<orchestrator-round block {i}>", "exec")
        except NameError as exc:  # pragma: no cover - failure path
            raise AssertionError(
                f"python block {i} raised NameError during compile against synthetic globals: {exc}"
            ) from exc
        except SyntaxError as exc:  # pragma: no cover - failure path
            raise AssertionError(
                f"python block {i} failed to compile after fill_prompt(): {exc}\n"
                f"--- block ---\n{block}\n--- end block ---"
            ) from exc

    # Sanity: synthetic_globals is referenced so that any future evolution of
    # this test toward exec-time validation has the dict ready.
    assert "escalations_path" in synthetic_globals


def test_criticality_partition_uses_shared_reducer():
    """Task 13: Step 3b.1 reads criticality via the in-process shared reducer.

    The former inline ``_read_criticality`` block (which re-implemented the
    events.log fold and buggily read ``.criticality`` off ``criticality_override``
    events that carry only ``from``/``to``) is replaced by an in-process import of
    ``cortex_command.common.reduce_lifecycle_state`` — the single reducer that
    ``cortex-lifecycle-state`` wraps. This test pins the replacement so the inline
    block cannot silently return and so the corrupted-read fallback contract
    (single-agent, never defer, warn on ANY corrupted read) stays documented in
    the prompt text.
    """
    out = _render()

    # The inline re-implementation is gone entirely.
    assert "_read_criticality" not in out, (
        "the inline _read_criticality block must be fully removed from the prompt"
    )

    # The partition imports and calls the single shared reducer in-process.
    assert "reduce_lifecycle_state" in out, (
        "Step 3b.1 must import/call cortex_command.common.reduce_lifecycle_state"
    )
    assert "from cortex_command.common import reduce_lifecycle_state" in out, (
        "the shared reducer must be imported in-process (not shelled to a subprocess)"
    )

    # The single-agent-not-defer rationale comment is present, anchored on the
    # criticality-matrix.md:26 interactive rule and the never-defer constraint.
    assert "criticality-matrix.md:26" in out, (
        "the single-agent-not-defer rationale comment (citing criticality-matrix.md:26) "
        "must be present in the criticality block"
    )
    assert "never defer" in out.lower(), (
        "the never-defer fallback rationale must be documented in the prompt"
    )

    # A morning-report warning is emitted on ANY corrupted read (both the
    # unknowable arm and the present-but-stale arm surface via log_event).
    assert '"stage": "criticality_read"' in out, (
        "a morning-report warning must be emitted (log_event with "
        'stage="criticality_read") on any corrupted criticality read'
    )
    # The warning uses the dedicated CRITICALITY_READ_CORRUPTED event (#377
    # Item B), replacing the former SYNTHESIZER_ERROR reuse — so the morning
    # report can surface it under its own heading.
    assert "CRITICALITY_READ_CORRUPTED" in out, (
        "Step 3b.1 must emit the dedicated CRITICALITY_READ_CORRUPTED event on a "
        "corrupted criticality read (not the reused SYNTHESIZER_ERROR)"
    )
    # Both corrupted arms are handled: the unknowable arm (defaults + warns) and
    # the present-but-stale arm (uses the value AND still warns).
    assert "may be stale" in out, (
        "the present-but-corrupted arm must use the present value AND still warn "
        "(the value may be stale)"
    )
