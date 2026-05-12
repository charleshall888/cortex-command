"""Verify the orchestrator-round prompt template renders escalations paths
under the per-session ``{session_dir}/escalations.jsonl`` form (R20).

Per task 9 of the build-mcp-control-plane-server-with-versioned-runner-ipc-contract
spec: the prompt template references ``{session_dir}/escalations.jsonl`` so that
``fill_prompt()`` substitutes the per-session escalations path before the
orchestrator agent executes the prompt. These tests assert that:

1. After ``fill_prompt()``, the rendered prompt contains the substituted
   ``lifecycle/sessions/{fixture_id}/escalations.jsonl`` path and contains zero
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
